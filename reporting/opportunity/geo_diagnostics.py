"""Deterministic GEO fixed-sample diagnostics for WP8.

GEO observations enrich an existing WP5 candidate.  They do not create a
candidate, change its score/confidence, or transition its review state.
"""

from __future__ import annotations

import copy
import json
import hashlib
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Optional

from .candidate_store import CandidateStore
from .evidence import EvidenceStore
from .proposal_validation import ValidationError, ValidationResult
from .store.errors import ImmutableStoreError
from .store.registry import RegistryLookup
from .store.serialization import canonical_json, canonical_line, content_hash
from reporting.sources.workduo import SOURCE_CLASS, SOURCE_ROLE, normalize_sample_definition

CONTRACT_VERSION = "geo_diagnostic.v1.proposal"
RULE_VERSION = "geo-fixed-sample-diagnostic-1"
CURRENT_MAX_AGE_DAYS = 7
STATUSES = frozenset({"GEO_STRONG", "GEO_WEAK", "GEO_STABLE", "GEO_NOT_CHECKED", "GEO_CONFLICT", "INSUFFICIENT_GEO_EVIDENCE"})
VISIBILITY_STATES = frozenset({"PRESENT", "ABSENT", "NOT_AVAILABLE", "UNKNOWN"})
CAPABILITY_STATES = frozenset({"OBSERVED", "NOT_OBSERVED", "NOT_AVAILABLE", "UNKNOWN"})


class GEODiagnosticInputError(ValueError):
    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message); self.code = code; self.field = field


@dataclass(frozen=True)
class GEOFixedSampleInput:
    candidate_id: str
    candidate_revision: int
    topic_cluster_id: str
    target_url: str
    evaluation_period: str
    decision_at: str
    registry: Mapping[str, Any]
    sample_definition: Mapping[str, Any]
    geo_evidence: tuple[Mapping[str, Any], ...]
    candidate_evidence_refs: tuple[Mapping[str, Any], ...] = ()
    wp5_score: Optional[int] = None
    wp5_confidence: str = "NOT_ASSESSABLE"
    candidate_status: str = "CANDIDATE"
    candidate_review_state: str = "NOT_REVIEWED"
    serp_validation: Optional[Mapping[str, Any]] = None
    ga4_diagnostic: Optional[Mapping[str, Any]] = None
    opportunity_type: str = "SEO_EXISTING"
    diagnostic_revision: int = 1
    rule_version: str = RULE_VERSION

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, candidate_store: Optional[CandidateStore] = None) -> "GEOFixedSampleInput":
        if not isinstance(value, Mapping): raise GEODiagnosticInputError("INVALID_INPUT", "GEO input must be a mapping")
        values = dict(value)
        if candidate_store is not None and values.get("candidate_id"):
            candidate = candidate_store.get_candidate(str(values["candidate_id"]), values.get("candidate_revision"))
            if candidate:
                values.setdefault("candidate_revision", candidate.get("revision")); values.setdefault("topic_cluster_id", (candidate.get("topic_ref") or {}).get("entity_id")); values.setdefault("target_url", candidate.get("target_url")); values.setdefault("candidate_evidence_refs", candidate.get("evidence_refs", [])); values.setdefault("wp5_score", candidate.get("score")); values.setdefault("wp5_confidence", candidate.get("confidence", "NOT_ASSESSABLE")); values.setdefault("candidate_status", candidate.get("status", "CANDIDATE")); values.setdefault("candidate_review_state", candidate.get("review_state", "NOT_REVIEWED"))
        required = ("candidate_id", "candidate_revision", "topic_cluster_id", "target_url", "evaluation_period", "decision_at", "registry", "sample_definition")
        missing = [name for name in required if values.get(name) in (None, "")]
        if missing: raise GEODiagnosticInputError("MISSING_FIELD", "missing GEO diagnostic fields: " + ", ".join(missing))
        revision = values["candidate_revision"]
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1: raise GEODiagnosticInputError("INVALID_REVISION", "candidate_revision must be positive", "candidate_revision")
        try:
            parsed = datetime.fromisoformat(str(values["decision_at"]).replace("Z", "+00:00"))
        except ValueError as exc: raise GEODiagnosticInputError("INVALID_DATETIME", "decision_at must be ISO-8601", "decision_at") from exc
        if parsed.tzinfo is None: raise GEODiagnosticInputError("NAIVE_DATETIME", "decision_at must include timezone", "decision_at")
        rows = values.get("geo_evidence", ())
        refs = values.get("candidate_evidence_refs", ())
        if isinstance(rows, Mapping): rows = tuple(rows.values())
        if isinstance(refs, Mapping): refs = tuple(refs.values())
        if not isinstance(rows, (list, tuple)) or not isinstance(refs, (list, tuple)): raise GEODiagnosticInputError("INVALID_EVIDENCE", "evidence fields must be arrays")
        return cls(candidate_id=str(values["candidate_id"]), candidate_revision=revision, topic_cluster_id=str(values["topic_cluster_id"]), target_url=str(values["target_url"]), evaluation_period=str(values["evaluation_period"]), decision_at=str(values["decision_at"]), registry=values["registry"], sample_definition=values["sample_definition"], geo_evidence=tuple(dict(row) for row in rows if isinstance(row, Mapping)), candidate_evidence_refs=tuple(dict(row) for row in refs if isinstance(row, Mapping)), wp5_score=values.get("wp5_score"), wp5_confidence=str(values.get("wp5_confidence", "NOT_ASSESSABLE")), candidate_status=str(values.get("candidate_status", "CANDIDATE")), candidate_review_state=str(values.get("candidate_review_state", "NOT_REVIEWED")), serp_validation=dict(values["serp_validation"]) if isinstance(values.get("serp_validation"), Mapping) else None, ga4_diagnostic=dict(values["ga4_diagnostic"]) if isinstance(values.get("ga4_diagnostic"), Mapping) else None, opportunity_type=str(values.get("opportunity_type", "SEO_EXISTING")), diagnostic_revision=int(values.get("diagnostic_revision", 1)), rule_version=str(values.get("rule_version", RULE_VERSION)))


@dataclass
class GEODiagnosticResult:
    diagnostic: Optional[dict[str, Any]]
    persisted: bool = False
    persistence_error: Optional[str] = None
    errors: list[str] = field(default_factory=list)
    @property
    def is_valid(self) -> bool: return self.diagnostic is not None and not self.errors
    def as_dict(self) -> dict[str, Any]: return {"diagnostic": self.diagnostic, "persisted": self.persisted, "persistence_error": self.persistence_error, "errors": list(self.errors)}


def _ref(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    if not isinstance(value.get("evidence_id"), str) or not value.get("evidence_id") or not isinstance(value.get("revision"), int) or value.get("revision", 0) < 1 or not isinstance(value.get("content_hash"), str) or len(value.get("content_hash", "")) != 64:
        raise GEODiagnosticInputError("MISSING_EVIDENCE_PIN", f"{field} must pin evidence_id, revision and content_hash", field)
    return {"evidence_id": value["evidence_id"], "revision": value["revision"], "content_hash": value["content_hash"]}


def _current(row: Mapping[str, Any], decision_day: date) -> bool:
    if str(row.get("freshness_state", "")).upper() != "READY" or str(row.get("collection_status", "")).upper() not in {"SUCCESS", "READY"}: return False
    try:
        observed = date.fromisoformat(str(row.get("as_of") or row.get("period_end")))
        return 0 <= (decision_day - observed).days <= CURRENT_MAX_AGE_DAYS
    except (TypeError, ValueError): return False


def _sample_definition(value: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    if value.get("sample_hash"): return copy.deepcopy(dict(value))
    return normalize_sample_definition(value, registry)


def _sample_scope(sample: Mapping[str, Any], observation: Mapping[str, Any]) -> bool:
    for key in ("sample_id", "sample_version", "market", "locale", "platform", "model_scope"):
        if str(observation.get(key, "UNKNOWN")) != str(sample.get(key, "UNKNOWN")):
            return False
    return int(observation.get("sample_revision", 1)) == int(sample.get("sample_revision", sample.get("revision", 1)))


def _diagnostic_id(inp: GEOFixedSampleInput) -> str:
    seed = {"candidate_id": inp.candidate_id, "candidate_revision": inp.candidate_revision, "sample_id": inp.sample_definition.get("sample_id"), "sample_version": inp.sample_definition.get("sample_version"), "evaluation_period": inp.evaluation_period}
    return "GEO_" + hashlib.sha256(canonical_json(seed).encode()).hexdigest()[:24]


def evaluate_geo_fixed_sample(value: Any, *, diagnostic_store: Optional["GEODiagnosticStore"] = None, persist: bool = False, candidate_store: Optional[CandidateStore] = None) -> GEODiagnosticResult:
    try: inp = value if isinstance(value, GEOFixedSampleInput) else GEOFixedSampleInput.from_mapping(value, candidate_store=candidate_store)
    except GEODiagnosticInputError as exc: return GEODiagnosticResult(None, errors=[f"{exc.code}:{exc.field}"])
    try: sample = _sample_definition(inp.sample_definition, inp.registry)
    except Exception as exc: return GEODiagnosticResult(None, errors=[f"{getattr(exc, 'code', 'INVALID_SAMPLE')}:sample_definition"])
    conflicts: set[str] = set(); missing: set[str] = set(); refs: list[dict[str, Any]] = []; current: list[Mapping[str, Any]] = []; current_evidence_ids: set[str] = set(); stale: list[Mapping[str, Any]] = []; prompt_ids: set[str] = set(); historical_versions: set[str] = set()
    try: candidate_refs = [_ref(ref, "candidate_evidence_refs") for ref in inp.candidate_evidence_refs]
    except GEODiagnosticInputError as exc: return GEODiagnosticResult(None, errors=[f"{exc.code}:{exc.field}"])
    if not candidate_refs: return GEODiagnosticResult(None, errors=["MISSING_EVIDENCE_PIN:candidate_evidence_refs"])
    try: decision_day = date.fromisoformat(inp.decision_at[:10])
    except ValueError: return GEODiagnosticResult(None, errors=["INVALID_DATETIME:decision_at"])
    for raw in inp.geo_evidence:
        try: ref = _ref(raw, "geo_evidence")
        except GEODiagnosticInputError: continue
        refs.append(ref)
        if raw.get("source") != "WORKDUO" or raw.get("source_class") != SOURCE_CLASS or raw.get("metric") != "geo_observation": conflicts.add("GEO_SOURCE_CLASS_MISMATCH"); continue
        obs = raw.get("observation") if isinstance(raw.get("observation"), Mapping) else (raw.get("value") if isinstance(raw.get("value"), Mapping) else None)
        if obs is None:
            if str(raw.get("freshness_state")) in {"FAILED", "NOT_AVAILABLE"}: missing.add("geo_provider_result"); conflicts.add("PROVIDER_FAILURE")
            continue
        if str(raw.get("freshness_state", "")).upper() in {"FAILED", "NOT_AVAILABLE"} or str(raw.get("collection_status", "")).upper() in {"FAILED", "NOT_AVAILABLE"}:
            conflicts.add("PROVIDER_FAILURE")
        prompt_ref = obs.get("prompt_ref") or {}; prompt_id = prompt_ref.get("entity_id")
        if not prompt_id or not any(row.get("prompt_id") == prompt_id for row in (inp.registry.get("entities") or {}).get("PROMPT", [])): conflicts.add("UNMAPPED_PROMPT"); continue
        prompt_ids.add(str(prompt_id)); historical_versions.add(str(obs.get("sample_version")))
        if str(obs.get("topic_ref", {}).get("entity_id")) != inp.topic_cluster_id: conflicts.add("UNMAPPED_TOPIC"); continue
        if not _sample_scope(sample, obs): conflicts.add("COMPARABILITY_GAP"); continue
        if _current(raw, decision_day): current.append(obs); current_evidence_ids.add(ref["evidence_id"])
        else: stale.append(obs)
    if not refs: missing.add("geo_observation")
    if stale: missing.add("fresh_current_geo_evidence"); conflicts.add("STALE_GEO_EVIDENCE")
    if not current: missing.add("geo_observation"); status = "GEO_NOT_CHECKED" if not stale else "INSUFFICIENT_GEO_EVIDENCE"
    else:
        mention_states = {str(obs.get("mention_state", "UNKNOWN")) for obs in current}; citation_states = {str(obs.get("citation_state", "UNKNOWN")) for obs in current}
        if "NOT_AVAILABLE" in mention_states or "NOT_AVAILABLE" in citation_states: conflicts.add("CAPABILITY_GAP")
        if any(obs.get("unknown_domains") for obs in current): conflicts.add("UNKNOWN_COMPETITOR_DOMAIN")
        owned = [obs for obs in current if obs.get("owned_url_id")]
        competitors = {obs.get("competitor_id") for obs in current if obs.get("competitor_id")}
        if owned and competitors: status = "GEO_STRONG"
        elif owned: status = "GEO_STABLE" if len(current) > 1 else "GEO_STRONG"
        elif any(state == "NOT_AVAILABLE" for state in mention_states | citation_states): status = "INSUFFICIENT_GEO_EVIDENCE"
        else: status = "GEO_WEAK"
    if inp.serp_validation and inp.serp_validation.get("validation_status") == "SERP_VALIDATED" and status in {"GEO_WEAK", "INSUFFICIENT_GEO_EVIDENCE"}: conflicts.update({"CROSS_CHANNEL_CONFLICT", "MIXED_SIGNAL"})
    if inp.serp_validation and inp.serp_validation.get("validation_status") == "SERP_CONFLICT" and status == "GEO_STRONG": conflicts.add("CROSS_CHANNEL_CONFLICT")
    if len(historical_versions) > 1: conflicts.add("COMPARABILITY_GAP")
    if "COMPARABILITY_GAP" in conflicts: status = "GEO_CONFLICT"
    mention = "OBSERVED" if any(str(row.get("mention_state")) == "OBSERVED" for row in current) else ("NOT_OBSERVED" if current and all(str(row.get("mention_state")) == "NOT_OBSERVED" for row in current) else ("NOT_AVAILABLE" if current and any(str(row.get("mention_state")) == "NOT_AVAILABLE" for row in current) else "UNKNOWN"))
    citation = "OBSERVED" if any(str(row.get("citation_state")) == "OBSERVED" for row in current) else ("NOT_OBSERVED" if current and all(str(row.get("citation_state")) == "NOT_OBSERVED" for row in current) else ("NOT_AVAILABLE" if current and any(str(row.get("citation_state")) == "NOT_AVAILABLE" for row in current) else "UNKNOWN"))
    owned_presence = "PRESENT" if any(row.get("owned_url_id") for row in current) else ("ABSENT" if current and all(row.get("owned_url_id") is None for row in current) else "NOT_AVAILABLE")
    competitor_ids = sorted({str(row["competitor_id"]) for row in current if row.get("competitor_id")})
    unknown_domains = sorted({str(domain) for row in current for domain in (row.get("unknown_domains") or [])})
    diagnostic_id = _diagnostic_id(inp)
    freshness = [{"evidence_id": ref["evidence_id"], "revision": ref["revision"], "period_end": raw.get("period_end"), "as_of": raw.get("as_of"), "retrieved_at": raw.get("retrieved_at"), "freshness_state": raw.get("freshness_state"), "collection_status": raw.get("collection_status"), "is_current": ref["evidence_id"] in current_evidence_ids} for ref, raw in [(ref, raw) for ref, raw in zip(refs, inp.geo_evidence)]]
    capability_gaps = sorted({field for field, states in (("mention", {str(row.get("mention_state")) for row in current}), ("citation", {str(row.get("citation_state")) for row in current})) if "NOT_AVAILABLE" in states})
    result = {"record_type": "GEO_DIAGNOSTIC", "contract_version": CONTRACT_VERSION, "diagnostic_id": diagnostic_id, "revision": inp.diagnostic_revision, "supersedes_diagnostic_revision": inp.diagnostic_revision - 1 if inp.diagnostic_revision > 1 else None, "candidate_id": inp.candidate_id, "candidate_revision": inp.candidate_revision, "topic_ref": {"entity_type": "TOPIC", "entity_id": inp.topic_cluster_id}, "topic_cluster_id": inp.topic_cluster_id, "target_url": inp.target_url, "evaluation_period": inp.evaluation_period, "opportunity_type": inp.opportunity_type, "sample_ref": {"sample_id": sample.get("sample_id"), "sample_version": sample.get("sample_version"), "revision": sample.get("revision", 1), "sample_hash": sample.get("sample_hash")}, "sample_id": sample.get("sample_id"), "sample_version": sample.get("sample_version"), "sample_revision": sample.get("revision", 1), "sample_hash": sample.get("sample_hash"), "prompt_count": len(sample.get("prompt_population") or []), "prompt_refs": [{"entity_type": "PROMPT", "entity_id": item} for item in sorted(prompt_ids)], "platform_scope": sample.get("platform"), "model_scope": sample.get("model_scope"), "market": sample.get("market"), "locale": sample.get("locale"), "source_role": SOURCE_ROLE, "geo_evidence_refs": refs, "candidate_evidence_refs": candidate_refs, "diagnostic_status": status, "owned_visibility": owned_presence, "competitor_presence": competitor_ids, "unknown_domains": unknown_domains, "mention_state": mention, "citation_state": citation, "capability_gaps": capability_gaps, "policy_gaps": ["FIXED_SAMPLE_ONLY", "GEO_MARKET_WIDE_COVERAGE_UNAPPROVED"], "comparability": {"status": "COMPARABLE" if "COMPARABILITY_GAP" not in conflicts else "NOT_COMPARABLE", "sample_version": sample.get("sample_version"), "population": sample.get("prompt_population"), "platform": sample.get("platform"), "model_scope": sample.get("model_scope"), "market": sample.get("market"), "locale": sample.get("locale"), "provider_methodology": sample.get("provider_methodology")}, "conflicts": sorted(conflicts), "missing_evidence": sorted(missing), "freshness": freshness, "rule_trace": [{"rule_id": "GEO_FIXED_SAMPLE", "rule_version": inp.rule_version, "inputs": ["sample_ref", "prompt_refs", "geo_evidence_refs"], "matched_conditions": ["exact canonical PROMPT/TOPIC mappings", "candidate enrichment only"], "failed_conditions": sorted(conflicts), "evidence_refs": refs, "sample_ref": {"sample_id": sample.get("sample_id"), "sample_version": sample.get("sample_version"), "revision": sample.get("revision", 1)}}, {"rule_id": "GEO_CAPABILITY_SEPARATION", "rule_version": inp.rule_version, "inputs": ["mention_state", "citation_state"], "matched_conditions": ["mention and citation remain independent"], "failed_conditions": sorted(set(capability_gaps)), "evidence_refs": refs, "sample_ref": {"sample_id": sample.get("sample_id"), "sample_version": sample.get("sample_version")}}, {"rule_id": "GEO_COMPARABILITY", "rule_version": inp.rule_version, "inputs": ["sample_version", "prompt_population", "platform_scope", "model_scope", "market", "locale", "provider_methodology"], "matched_conditions": ["identical fixed-sample scope required"], "failed_conditions": ["COMPARABILITY_GAP"] if "COMPARABILITY_GAP" in conflicts else [], "evidence_refs": refs, "sample_ref": {"sample_id": sample.get("sample_id"), "sample_version": sample.get("sample_version")}}], "wp5_score": inp.wp5_score, "wp5_confidence": inp.wp5_confidence, "candidate_status": inp.candidate_status, "candidate_review_state": inp.candidate_review_state, "wp5_score_preserved": True, "approval_transition_allowed": False, "ga4_diagnostic": copy.deepcopy(inp.ga4_diagnostic), "serp_validation": copy.deepcopy(inp.serp_validation), "input_signature": hashlib.sha256(canonical_json({"diagnostic_id": diagnostic_id, "geo_refs": refs, "candidate_refs": candidate_refs, "rule": inp.rule_version}).encode()).hexdigest(), "created_at": inp.decision_at, "updated_at": inp.decision_at}
    result["content_hash"] = content_hash(result)
    persisted = False; persistence_error = None
    if persist and diagnostic_store:
        try: diagnostic_store.append_diagnostic(result); persisted = True
        except Exception as exc: persistence_error = str(exc)
    return GEODiagnosticResult(result, persisted=persisted, persistence_error=persistence_error)


def validate_geo_diagnostic(payload: Any, *, context: Optional[Mapping[str, Any]] = None) -> ValidationResult:
    errors: list[ValidationError] = []
    if not isinstance(payload, Mapping): return ValidationResult(errors=[ValidationError("INVALID_INPUT", "$", "GEO diagnostic must be an object")])
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        schema = json.loads((Path(__file__).resolve().parents[2] / "contracts/geo_diagnostic.v1.proposal.json").read_text(encoding="utf-8"))
        errors.extend(ValidationError("SCHEMA_VIOLATION", ".".join(map(str, error.absolute_path)) or "$", "Payload violates GEO proposal schema", rule=str(error.validator)) for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload))
    except Exception as exc: errors.append(ValidationError("SCHEMA_VALIDATION_ERROR", "$", str(exc)))
    if payload.get("approval_transition_allowed") is not False: errors.append(ValidationError("AUTO_APPROVAL_FORBIDDEN", "approval_transition_allowed", "GEO diagnostics cannot approve candidates"))
    if payload.get("wp5_score_preserved") is not True: errors.append(ValidationError("WP5_SCORE_MUTATION", "wp5_score_preserved", "GEO diagnostics must preserve WP5 score"))
    if payload.get("diagnostic_status") not in STATUSES: errors.append(ValidationError("INVALID_STATUS", "diagnostic_status", "unknown GEO status"))
    try:
        if payload.get("content_hash") != content_hash(payload): errors.append(ValidationError("CONTENT_HASH_MISMATCH", "content_hash", "GEO content hash mismatch"))
    except Exception as exc: errors.append(ValidationError("CONTENT_HASH_ERROR", "content_hash", str(exc)))
    if payload.get("source_role") != SOURCE_ROLE: errors.append(ValidationError("SOURCE_ROLE_GAP", "source_role", "Workduo must remain a monitored fixed sample"))
    for field_name in ("geo_evidence_refs", "candidate_evidence_refs"):
        seen: set[tuple[str, int]] = set()
        for index, ref in enumerate(payload.get(field_name) or []):
            try: pin = _ref(ref, f"{field_name}[{index}]")
            except GEODiagnosticInputError as exc: errors.append(ValidationError(exc.code, f"{field_name}[{index}]", str(exc))); continue
            key = (pin["evidence_id"], pin["revision"])
            if key in seen: errors.append(ValidationError("DUPLICATE_EVIDENCE_REFERENCE", field_name, "evidence refs must be unique"))
            seen.add(key)
            if context and context.get("evidence_store") is not None:
                try: context["evidence_store"].resolve_reference(pin["evidence_id"], pin["revision"], pin["content_hash"])
                except Exception: errors.append(ValidationError("EVIDENCE_PIN_INVALID", field_name, "pinned evidence does not resolve"))
    return ValidationResult(errors=errors)


# Stable names for callers that treat the layer as a generic GEO diagnostic.
evaluate_geo_diagnostic = evaluate_geo_fixed_sample
validate_geo = validate_geo_diagnostic


class GEODiagnosticStore:
    """Append-only diagnostic store with exact evidence pins and tamper checks."""
    def __init__(self, root: str | os.PathLike[str], *, evidence_store: EvidenceStore, registry: Mapping[str, Any]) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True); self.path = self.root / "geo_diagnostics.jsonl"; self.evidence_store = evidence_store; self.registry = RegistryLookup(registry); self._records: dict[tuple[str, int], dict[str, Any]] = {}; self._load()
    def _prepare(self, record: Mapping[str, Any]) -> dict[str, Any]:
        value = copy.deepcopy(dict(record)); calculated = content_hash(value)
        if value.get("content_hash") is not None and value["content_hash"] != calculated: raise ImmutableStoreError("HASH_MISMATCH", "diagnostic content hash mismatch")
        value["content_hash"] = calculated; return value
    def _validate(self, record: Mapping[str, Any]) -> None:
        for field_name in ("record_type", "diagnostic_id", "revision", "geo_evidence_refs", "candidate_evidence_refs", "content_hash", "created_at"):
            if field_name not in record: raise ImmutableStoreError("MISSING_FIELD", f"missing GEO field: {field_name}")
        if record["record_type"] != "GEO_DIAGNOSTIC" or record.get("source_role") != SOURCE_ROLE: raise ImmutableStoreError("INVALID_GEO_CONTRACT", "invalid GEO contract")
        if not isinstance(record["revision"], int) or record["revision"] < 1: raise ImmutableStoreError("INVALID_REVISION", "diagnostic revision must be positive")
        for field_name in ("geo_evidence_refs", "candidate_evidence_refs"):
            for ref in record[field_name]: self.evidence_store.resolve_reference(ref["evidence_id"], ref["revision"], ref["content_hash"])
        if not isinstance(record.get("approval_transition_allowed"), bool) or record["approval_transition_allowed"] is not False: raise ImmutableStoreError("AUTO_APPROVAL_FORBIDDEN", "GEO cannot approve candidate")
        try:
            parsed = datetime.fromisoformat(str(record["created_at"]).replace("Z", "+00:00"))
            if parsed.tzinfo is None: raise ValueError
        except ValueError as exc: raise ImmutableStoreError("INVALID_DATETIME", "created_at must be timezone-aware") from exc
    def _load(self) -> None:
        if not self.path.exists(): return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line: continue
            row = self._prepare(json.loads(line)); self._validate(row); key = (row["diagnostic_id"], row["revision"])
            if key in self._records: raise ImmutableStoreError("STORE_CORRUPTION", "duplicate GEO diagnostic revision")
            self._records[key] = row
    def append_diagnostic(self, record: Mapping[str, Any]) -> dict[str, Any]:
        prepared = self._prepare(record); self._validate(prepared); key = (prepared["diagnostic_id"], prepared["revision"]); existing = self._records.get(key)
        if existing:
            if existing["content_hash"] == prepared["content_hash"]: return {**copy.deepcopy(existing), "idempotent": True}
            raise ImmutableStoreError("REVISION_CONFLICT", "same GEO revision has a different hash")
        revisions = sorted(rev for did, rev in self._records if did == prepared["diagnostic_id"]); expected = revisions[-1] + 1 if revisions else 1
        if prepared["revision"] != expected: raise ImmutableStoreError("REVISION_GAP", "GEO revisions must append contiguously")
        if prepared["revision"] == 1 and prepared.get("supersedes_diagnostic_revision") is not None: raise ImmutableStoreError("INVALID_SUPERSEDES", "revision 1 cannot supersede")
        if prepared["revision"] > 1 and prepared.get("supersedes_diagnostic_revision") != prepared["revision"] - 1: raise ImmutableStoreError("INVALID_SUPERSEDES", "GEO revision must supersede previous revision")
        with self.path.open("a", encoding="utf-8", newline="") as handle: handle.write(canonical_line(prepared)); handle.flush(); os.fsync(handle.fileno())
        self._records[key] = copy.deepcopy(prepared); return copy.deepcopy(prepared)
    def get_diagnostic(self, diagnostic_id: str, revision: Optional[int] = None) -> Optional[dict[str, Any]]:
        rows = self.history(diagnostic_id)
        if revision is None: return rows[-1] if rows else None
        return next((row for row in rows if row["revision"] == revision), None)
    def history(self, diagnostic_id: str) -> list[dict[str, Any]]: return [copy.deepcopy(self._records[key]) for key in sorted(self._records) if key[0] == diagnostic_id]


__all__ = ["CONTRACT_VERSION", "RULE_VERSION", "STATUSES", "GEOFixedSampleInput", "GEODiagnosticInputError", "GEODiagnosticResult", "GEODiagnosticStore", "evaluate_geo_fixed_sample", "evaluate_geo_diagnostic", "validate_geo_diagnostic", "validate_geo"]
