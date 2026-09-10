"""Deterministic, shortlist-only interpretation of pinned SERP snapshots.

Collection and interpretation are separate boundaries.  This module consumes
normalised ``SERP`` Evidence records only; it never calls a search provider or
invents a query.  A validation record is an append-only diagnostic artifact and
does not change the WP5 score, confidence, or candidate review state.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

from .candidate_store import CandidateStore
from .evidence import EvidenceStore
from .entities import RegistryInputError, normalize_url
from .store.errors import ImmutableStoreError
from .store.serialization import canonical_line, canonical_json, content_hash
from reporting.sources.serp import SOURCE_CLASS, resolve_query_ref
from .proposal_validation import ValidationError, ValidationResult


CONTRACT_VERSION = "serp_validation.v1.proposal"
RULE_VERSION = "serp-validation-proposal-1"
VALIDATION_STATUSES = frozenset({"SERP_VALIDATED", "SERP_CONFLICT", "SERP_NOT_CHECKED"})
PAGE_TYPES = frozenset({
    "informational_article", "commercial_comparison", "category_product",
    "homepage", "tool", "video", "forum", "official_documentation", "faq", "unknown",
})
INTENTS = frozenset({"INFORMATIONAL", "COMMERCIAL_INVESTIGATION", "TRANSACTIONAL", "NAVIGATIONAL", "MIXED", "UNKNOWN"})
CONFLICT_REASONS = frozenset({
    "INTENT_MISMATCH", "PAGE_TYPE_MISMATCH", "OWNED_ASSET_MISMATCH",
    "SERP_FEATURE_CROWDING", "COMPETITOR_DOMINANCE", "INSUFFICIENT_SERP_EVIDENCE",
    "UNKNOWN_COMPETITOR_DOMAIN", "UNRESOLVED_TARGET_URL", "QUERY_SCOPE_MISMATCH",
    "QUERY_NOT_APPROVED", "MISSING_VALIDATION_QUERY", "STALE_SERP_EVIDENCE",
})
CURRENT_MAX_AGE_DAYS = 7


class SERPValidationInputError(ValueError):
    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


@dataclass(frozen=True)
class SERPValidationInput:
    candidate_id: str
    candidate_revision: int
    topic_cluster_id: str
    target_url: str
    evaluation_period: str
    decision_at: str
    registry: Mapping[str, Any]
    canonical_url_id: Optional[str] = None
    opportunity_type: str = "SEO_EXISTING"
    recommended_action: str = "OPTIMIZE_EXISTING"
    existing_urls: tuple[str, ...] = ()
    expected_intent: Optional[str] = None
    expected_page_type: Optional[str] = None
    validation_query: Optional[Mapping[str, Any]] = None
    serp_evidence: tuple[Mapping[str, Any], ...] = ()
    candidate_evidence_refs: tuple[Mapping[str, Any], ...] = ()
    wp5_score: Optional[int] = None
    wp5_confidence: str = "NOT_ASSESSABLE"
    candidate_status: str = "CANDIDATE"
    candidate_review_state: str = "NOT_REVIEWED"
    ga4_diagnostic: Optional[Mapping[str, Any]] = None
    device: str = "DESKTOP"
    search_scope: str = "COUNTRY"
    rule_version: str = RULE_VERSION

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], *, candidate_store: Optional[CandidateStore] = None) -> "SERPValidationInput":
        if not isinstance(value, Mapping):
            raise SERPValidationInputError("INVALID_INPUT", "validation input must be a mapping")
        values = dict(value)
        if candidate_store is not None and values.get("candidate_id"):
            candidate = candidate_store.get_candidate(str(values["candidate_id"]), values.get("candidate_revision"))
            if candidate:
                values.setdefault("candidate_revision", candidate.get("revision"))
                values.setdefault("topic_cluster_id", (candidate.get("topic_ref") or {}).get("entity_id"))
                values.setdefault("target_url", candidate.get("target_url"))
                values.setdefault("candidate_evidence_refs", candidate.get("evidence_refs", []))
                values.setdefault("wp5_score", candidate.get("score"))
                values.setdefault("wp5_confidence", candidate.get("confidence", "NOT_ASSESSABLE"))
                values.setdefault("candidate_status", candidate.get("status", "CANDIDATE"))
                values.setdefault("candidate_review_state", candidate.get("review_state", "NOT_REVIEWED"))
        required = ("candidate_id", "candidate_revision", "topic_cluster_id", "target_url", "evaluation_period", "decision_at", "registry")
        missing = [name for name in required if values.get(name) in (None, "")]
        if missing:
            raise SERPValidationInputError("MISSING_FIELD", "missing validation fields: " + ", ".join(missing))
        revision = values["candidate_revision"]
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise SERPValidationInputError("INVALID_REVISION", "candidate_revision must be a positive integer", "candidate_revision")
        try:
            parsed = datetime.fromisoformat(str(values["decision_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise SERPValidationInputError("INVALID_DATETIME", "decision_at must be ISO-8601", "decision_at") from exc
        if parsed.tzinfo is None:
            raise SERPValidationInputError("NAIVE_DATETIME", "decision_at must include a timezone", "decision_at")
        evidence = values.get("serp_evidence", ())
        refs = values.get("candidate_evidence_refs", ())
        if isinstance(evidence, Mapping): evidence = tuple(evidence.values())
        if isinstance(refs, Mapping): refs = tuple(refs.values())
        if not isinstance(evidence, (list, tuple)) or not isinstance(refs, (list, tuple)):
            raise SERPValidationInputError("INVALID_EVIDENCE", "evidence fields must be arrays")
        return cls(
            candidate_id=str(values["candidate_id"]), candidate_revision=revision,
            topic_cluster_id=str(values["topic_cluster_id"]), target_url=str(values["target_url"]),
            canonical_url_id=(str(values["canonical_url_id"]) if values.get("canonical_url_id") else None),
            evaluation_period=str(values["evaluation_period"]), decision_at=str(values["decision_at"]),
            registry=values["registry"], opportunity_type=str(values.get("opportunity_type", "SEO_EXISTING")),
            recommended_action=str(values.get("recommended_action", "OPTIMIZE_EXISTING")),
            existing_urls=tuple(str(item) for item in values.get("existing_urls", ()) or ()),
            expected_intent=(str(values["expected_intent"]).upper() if values.get("expected_intent") else None),
            expected_page_type=(str(values["expected_page_type"]).lower() if values.get("expected_page_type") else None),
            validation_query=dict(values["validation_query"]) if isinstance(values.get("validation_query"), Mapping) else None,
            serp_evidence=tuple(dict(item) for item in evidence if isinstance(item, Mapping)),
            candidate_evidence_refs=tuple(dict(item) for item in refs if isinstance(item, Mapping)),
            wp5_score=values.get("wp5_score"), wp5_confidence=str(values.get("wp5_confidence", "NOT_ASSESSABLE")),
            candidate_status=str(values.get("candidate_status", "CANDIDATE")),
            candidate_review_state=str(values.get("candidate_review_state", "NOT_REVIEWED")),
            ga4_diagnostic=dict(values["ga4_diagnostic"]) if isinstance(values.get("ga4_diagnostic"), Mapping) else None,
            device=str(values.get("device", "DESKTOP")).upper(), search_scope=str(values.get("search_scope", "COUNTRY")).upper(),
            rule_version=str(values.get("rule_version", RULE_VERSION)),
        )


@dataclass
class SERPValidationResult:
    validation: Optional[dict[str, Any]]
    persisted: bool = False
    persistence_error: Optional[str] = None
    errors: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.validation is not None and not self.errors

    def as_dict(self) -> dict[str, Any]:
        return {"validation": self.validation, "persisted": self.persisted, "persistence_error": self.persistence_error, "errors": list(self.errors)}


def _ref(value: Mapping[str, Any], field: str) -> dict[str, Any]:
    if not isinstance(value.get("evidence_id"), str) or not value.get("evidence_id") or not isinstance(value.get("revision"), int) or value.get("revision", 0) < 1 or not isinstance(value.get("content_hash"), str) or len(value.get("content_hash", "")) != 64:
        raise SERPValidationInputError("MISSING_EVIDENCE_PIN", f"{field} must pin evidence_id, revision and content_hash", field)
    return {"evidence_id": value["evidence_id"], "revision": value["revision"], "content_hash": value["content_hash"]}


def _topic(registry: Mapping[str, Any], topic_id: str) -> Mapping[str, Any]:
    for row in (registry.get("entities") or {}).get("TOPIC", []):
        if row.get("topic_id") == topic_id: return row
    raise SERPValidationInputError("UNRESOLVED_TOPIC", "topic is not in the canonical registry", "topic_cluster_id")


def _registry_url(registry: Mapping[str, Any], value: str) -> Optional[Mapping[str, Any]]:
    try: normalized = normalize_url(value)
    except RegistryInputError: return None
    for row in (registry.get("entities") or {}).get("URL", []):
        if row.get("normalized_url") == normalized: return row
    return None


def _page_type(result_type: str) -> str:
    return {"article": "informational_article", "comparison": "commercial_comparison", "category": "category_product", "product": "category_product", "homepage": "homepage", "tool": "tool", "video": "video", "forum": "forum", "official_documentation": "official_documentation", "faq": "faq"}.get(result_type, "unknown")


def _intent(result_type: str) -> str:
    return {"article": "INFORMATIONAL", "comparison": "COMMERCIAL_INVESTIGATION", "category": "TRANSACTIONAL", "product": "TRANSACTIONAL", "homepage": "NAVIGATIONAL", "tool": "TRANSACTIONAL", "official_documentation": "INFORMATIONAL", "faq": "INFORMATIONAL", "video": "INFORMATIONAL", "forum": "INFORMATIONAL"}.get(result_type, "UNKNOWN")


def _dominant(counts: Mapping[str, int], total: int) -> str:
    if not total: return "UNKNOWN"
    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    if len(ordered) > 1 and ordered[0][1] / total < 0.6: return "MIXED"
    return ordered[0][0]


def _input_signature(value: SERPValidationInput, refs: list[dict[str, Any]], query: Optional[Mapping[str, Any]]) -> str:
    seed = {"candidate_id": value.candidate_id, "candidate_revision": value.candidate_revision, "query": query, "serp_refs": refs, "rule_version": value.rule_version}
    return hashlib.sha256(canonical_json(seed).encode("utf-8")).hexdigest()


def _fresh(evidence: Mapping[str, Any], decision_day: date) -> bool:
    if str(evidence.get("freshness_state", "")).upper() != "READY" or str(evidence.get("collection_status", "")).upper() != "SUCCESS": return False
    observed = evidence.get("as_of")
    try: return 0 <= (decision_day - date.fromisoformat(str(observed))).days <= CURRENT_MAX_AGE_DAYS
    except (TypeError, ValueError): return False


def evaluate_serp_validation(value: Any, *, validation_store: Optional["SERPValidationStore"] = None, persist: bool = False, candidate_store: Optional[CandidateStore] = None) -> SERPValidationResult:
    try: inp = value if isinstance(value, SERPValidationInput) else SERPValidationInput.from_mapping(value, candidate_store=candidate_store)
    except SERPValidationInputError as exc: return SERPValidationResult(None, errors=[f"{exc.code}:{exc.field}"])
    conflicts: set[str] = set(); missing: list[str] = []; trace: list[dict[str, Any]] = []
    try:
        candidate_pins = [_ref(ref, "candidate_evidence_refs") for ref in inp.candidate_evidence_refs]
    except SERPValidationInputError as exc:
        return SERPValidationResult(None, errors=[f"{exc.code}:{exc.field}"])
    if not candidate_pins:
        return SERPValidationResult(None, errors=["MISSING_EVIDENCE_PIN:candidate_evidence_refs"])
    try:
        topic = _topic(inp.registry, inp.topic_cluster_id)
    except SERPValidationInputError as exc:
        return SERPValidationResult(None, errors=[f"{exc.code}:{exc.field}"])
    expected_intent = inp.expected_intent or str(topic.get("search_intent", "UNKNOWN")).upper()
    query = None
    if inp.validation_query is None:
        missing.append("validation_query"); conflicts.add("MISSING_VALIDATION_QUERY")
    else:
        try:
            query, query_row = resolve_query_ref(inp.registry, inp.validation_query)
            if query.get("locale") != inp.validation_query.get("locale", query.get("locale")) or query.get("country") != inp.validation_query.get("country", query.get("country")):
                conflicts.add("QUERY_SCOPE_MISMATCH")
        except Exception as exc:
            conflicts.add("QUERY_SCOPE_MISMATCH" if getattr(exc, "code", "") == "QUERY_SCOPE_MISMATCH" else "QUERY_NOT_APPROVED")
            missing.append("validation_query")
    try:
        target_row = _registry_url(inp.registry, inp.target_url)
    except Exception:
        target_row = None
    if target_row is None:
        conflicts.add("UNRESOLVED_TARGET_URL")
    elif inp.canonical_url_id and target_row.get("url_id") != inp.canonical_url_id:
        conflicts.add("OWNED_ASSET_MISMATCH")
    if inp.existing_urls:
        normalized_existing = {_registry_url(inp.registry, url).get("normalized_url") for url in inp.existing_urls if _registry_url(inp.registry, url)}
        try: normalized_target = normalize_url(inp.target_url)
        except RegistryInputError: normalized_target = None
        if normalized_target not in normalized_existing:
            conflicts.add("OWNED_ASSET_MISMATCH")
    if inp.recommended_action == "CREATE_NEW" and target_row is not None:
        conflicts.add("OWNED_ASSET_MISMATCH")
    pinned: list[dict[str, Any]] = []
    snapshots: list[Mapping[str, Any]] = []
    try:
        decision_day = date.fromisoformat(inp.decision_at[:10])
    except ValueError:
        return SERPValidationResult(None, errors=["INVALID_DATETIME:decision_at"])
    for raw in inp.serp_evidence:
        try: ref = _ref(raw, "serp_evidence")
        except SERPValidationInputError: continue
        pinned.append(ref)
        if raw.get("source") != "SERP" or raw.get("source_class") != SOURCE_CLASS or raw.get("metric") != "serp_snapshot": continue
        if not _fresh(raw, decision_day):
            conflicts.add("STALE_SERP_EVIDENCE"); missing.append("fresh_serp_evidence"); continue
        snap = raw.get("value")
        if not isinstance(snap, Mapping): continue
        if query and (snap.get("query_ref") != query or snap.get("country") != query.get("country") or snap.get("locale") != query.get("locale") or snap.get("device") != inp.device or snap.get("search_scope") != inp.search_scope):
            conflicts.add("QUERY_SCOPE_MISMATCH"); continue
        snapshots.append(snap)
    snapshot = snapshots[-1] if snapshots else None
    counts: dict[str, int] = {}; intent_counts: dict[str, int] = {}; owned = 0; competitors: set[str] = set(); unknown_domains: set[str] = set()
    features: dict[str, str] = {}
    if snapshot is None or not isinstance(snapshot.get("organic_results"), list) or not snapshot.get("organic_results"):
        missing.append("serp_snapshot"); conflicts.add("INSUFFICIENT_SERP_EVIDENCE")
    else:
        results = snapshot["organic_results"]
        for result in results:
            kind = _page_type(str(result.get("result_type", "unknown"))); counts[kind] = counts.get(kind, 0) + 1
            intent = _intent(str(result.get("result_type", "unknown"))); intent_counts[intent] = intent_counts.get(intent, 0) + 1
            if result.get("owned"): owned += 1
            competitors.update(result.get("competitor_ids") or [])
            if result.get("competitor_match_state") == "UNMAPPED_DOMAIN" and not result.get("owned"):
                unknown_domains.add(str(result.get("domain")))
        features = dict(snapshot.get("serp_features") or {})
        if unknown_domains: conflicts.add("UNKNOWN_COMPETITOR_DOMAIN")
        if owned == 0 and competitors: conflicts.add("COMPETITOR_DOMINANCE")
        if inp.expected_page_type and _dominant(counts, len(results)) != inp.expected_page_type: conflicts.add("PAGE_TYPE_MISMATCH")
        observed_intent = _dominant(intent_counts, len(results))
        if expected_intent not in {"UNKNOWN", "MIXED"} and observed_intent not in {expected_intent, "MIXED"}: conflicts.add("INTENT_MISMATCH")
        if "featured_snippet" in features or "paa" in features or "ai_overview" in features or "aio" in features:
            if any(state == "OBSERVED" for state in features.values()): conflicts.add("SERP_FEATURE_CROWDING")
    observed_intent = _dominant(intent_counts, sum(intent_counts.values()))
    if query is None or "QUERY_SCOPE_MISMATCH" in conflicts or "QUERY_NOT_APPROVED" in conflicts or "MISSING_VALIDATION_QUERY" in conflicts:
        status = "SERP_NOT_CHECKED"
    elif conflicts:
        status = "SERP_CONFLICT" if "INSUFFICIENT_SERP_EVIDENCE" not in conflicts or snapshots else "SERP_NOT_CHECKED"
    elif snapshot is None:
        status = "SERP_NOT_CHECKED"
    else: status = "SERP_VALIDATED"
    owned_presence = "PRESENT" if owned else ("ABSENT" if snapshot is not None else "NOT_AVAILABLE")
    freshness = []
    for raw in inp.serp_evidence:
        try: ref = _ref(raw, "serp_evidence")
        except SERPValidationInputError: continue
        freshness.append({"evidence_id": ref["evidence_id"], "revision": ref["revision"], "period_end": raw.get("period_end"), "as_of": raw.get("as_of"), "retrieved_at": raw.get("retrieved_at"), "freshness_state": raw.get("freshness_state"), "collection_status": raw.get("collection_status"), "is_current": _fresh(raw, decision_day)})
    validation_id = "SV_" + hashlib.sha256(canonical_json({"candidate_id": inp.candidate_id, "candidate_revision": inp.candidate_revision, "query": query, "refs": pinned}).encode()).hexdigest()[:24]
    result = {
        "record_type": "SERP_VALIDATION", "contract_version": CONTRACT_VERSION, "validation_id": validation_id,
        "revision": 1, "candidate_id": inp.candidate_id, "candidate_revision": inp.candidate_revision,
        "topic_cluster_id": inp.topic_cluster_id, "opportunity_type": inp.opportunity_type, "recommended_action": inp.recommended_action,
        "target_url": inp.target_url, "canonical_url_id": inp.canonical_url_id or (target_row or {}).get("url_id"), "existing_urls": list(inp.existing_urls), "validation_query_ref": query,
        "validation_query_text": query.get("text") if query else None, "serp_evidence_refs": pinned,
        "candidate_evidence_refs": candidate_pins,
        "validation_status": status, "observed_intent": observed_intent, "expected_intent": expected_intent,
        "page_type_distribution": dict(sorted(counts.items())), "owned_presence": owned_presence,
        "competitor_presence": sorted(competitors), "unknown_domains": sorted(unknown_domains), "serp_features": features,
        "conflict_reasons": sorted(conflicts), "missing_evidence": sorted(set(missing)),
        "freshness": freshness,
        "serp_scope": {"country": (snapshot or {}).get("country") or (query or {}).get("country"), "locale": (snapshot or {}).get("locale") or (query or {}).get("locale"), "device": inp.device, "search_scope": inp.search_scope},
        "rule_trace": [{"rule_id": "SERP_SCOPE", "rule_version": inp.rule_version, "matched_conditions": ["canonical_query" if query else "no_query"], "failed_conditions": sorted(conflicts), "snapshot_refs": pinned, "candidate_refs": candidate_pins}],
        "snapshot_hashes": sorted(str(row.get("snapshot_hash")) for row in snapshots if row.get("snapshot_hash")),
        "validation_confidence": "MEDIUM" if status == "SERP_VALIDATED" else ("LOW" if status == "SERP_CONFLICT" else "NOT_ASSESSABLE"),
        "wp5_score": inp.wp5_score, "wp5_confidence": inp.wp5_confidence, "candidate_status": inp.candidate_status,
        "candidate_review_state": inp.candidate_review_state, "approval_transition_allowed": False,
        "ga4_diagnostic": copy.deepcopy(inp.ga4_diagnostic), "input_signature": _input_signature(inp, pinned, query),
        "created_at": inp.decision_at, "updated_at": inp.decision_at,
    }
    result["content_hash"] = content_hash(result)
    persisted = False; persistence_error = None
    if persist and validation_store:
        try: validation_store.append_validation(result); persisted = True
        except Exception as exc: persistence_error = str(exc)
    return SERPValidationResult(result, persisted=persisted, persistence_error=persistence_error)


def validate_serp_validation(payload: Any, *, context: Optional[Mapping[str, Any]] = None) -> ValidationResult:
    """Validate the proposal schema and immutable governance invariants."""
    errors: list[ValidationError] = []
    if not isinstance(payload, Mapping):
        return ValidationResult(errors=[ValidationError("INVALID_INPUT", "$", "SERP validation must be an object")])
    try:
        from jsonschema import Draft202012Validator
        schema_path = Path(__file__).resolve().parents[2] / "contracts" / "serp_validation.v1.proposal.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for item in Draft202012Validator(schema).iter_errors(payload):
            errors.append(ValidationError("SCHEMA_VIOLATION", ".".join(str(part) for part in item.absolute_path) or "$", "Payload violates the SERP validation proposal schema.", rule=str(item.validator)))
    except ImportError:
        errors.append(ValidationError("MISSING_VALIDATOR", "$", "jsonschema runtime is required"))
    if payload.get("approval_transition_allowed") is not False:
        errors.append(ValidationError("AUTO_APPROVAL_FORBIDDEN", "approval_transition_allowed", "SERP validation cannot approve a candidate automatically"))
    if payload.get("validation_status") not in VALIDATION_STATUSES:
        errors.append(ValidationError("INVALID_STATUS", "validation_status", "validation status is outside the three-state contract"))
    if payload.get("wp5_score") is not None and context and context.get("wp5_score") != payload.get("wp5_score"):
        errors.append(ValidationError("WP5_SCORE_MUTATION", "wp5_score", "SERP validation must preserve the supplied WP5 score"))
    return ValidationResult(errors=errors)


class SERPValidationStore:
    """Append-only validation artifact store; revisions never rewrite history."""
    def __init__(self, root: str | os.PathLike[str], *, evidence_store: EvidenceStore, registry: Optional[Mapping[str, Any]] = None) -> None:
        self.root = Path(root); self.root.mkdir(parents=True, exist_ok=True); self.path = self.root / "serp_validations.jsonl"
        self.evidence_store = evidence_store; self.registry = registry or evidence_store.registry.registry; self._records: dict[tuple[str, int], dict[str, Any]] = {}; self._load()
    def _load(self) -> None:
        if not self.path.exists(): return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line: continue
            row = json.loads(line)
            if row.get("content_hash") != content_hash(row):
                raise ImmutableStoreError("HASH_MISMATCH", "validation content hash does not match persisted fields")
            for ref in row.get("serp_evidence_refs", []) + row.get("candidate_evidence_refs", []):
                self.evidence_store.resolve_reference(ref["evidence_id"], ref["revision"], ref["content_hash"])
            self._records[(row["validation_id"], row["revision"])] = row
    def append_validation(self, value: Mapping[str, Any]) -> dict[str, Any]:
        row = copy.deepcopy(dict(value)); vid = row.get("validation_id"); rev = row.get("revision")
        if not isinstance(vid, str) or not isinstance(rev, int) or rev < 1: raise ImmutableStoreError("INVALID_REVISION", "validation_id and revision are required")
        for ref in row.get("serp_evidence_refs", []) + row.get("candidate_evidence_refs", []):
            self.evidence_store.resolve_reference(ref["evidence_id"], ref["revision"], ref["content_hash"])
        row["content_hash"] = content_hash(row)
        existing = self._records.get((vid, rev))
        if existing:
            if existing["content_hash"] == row["content_hash"]: return {**copy.deepcopy(existing), "idempotent": True}
            raise ImmutableStoreError("REVISION_CONFLICT", "same validation revision has a different content hash")
        revisions = sorted(r for v, r in self._records if v == vid); expected = revisions[-1] + 1 if revisions else 1
        if rev != expected: raise ImmutableStoreError("REVISION_GAP", "validation revisions must be contiguous")
        if rev > 1 and (row.get("supersedes_validation_id") != vid or row.get("supersedes_revision") != rev - 1): raise ImmutableStoreError("INVALID_SUPERSEDES", "revision must supersede immediately prior validation")
        with self.path.open("a", encoding="utf-8") as handle: handle.write(canonical_line(row)); handle.flush(); os.fsync(handle.fileno())
        self._records[(vid, rev)] = copy.deepcopy(row); return copy.deepcopy(row)
    def history(self, validation_id: str) -> list[dict[str, Any]]: return [copy.deepcopy(self._records[key]) for key in sorted(self._records) if key[0] == validation_id]
    def get_validation(self, validation_id: str, revision: Optional[int] = None) -> Optional[dict[str, Any]]:
        rows = self.history(validation_id); return rows[-1] if rows and revision is None else next((row for row in rows if row["revision"] == revision), None)


__all__ = ["CONTRACT_VERSION", "SERPValidationInput", "SERPValidationInputError", "SERPValidationResult", "SERPValidationStore", "evaluate_serp_validation", "validate_serp_validation", "VALIDATION_STATUSES"]
