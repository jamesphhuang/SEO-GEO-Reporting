"""Offline, deterministic GA4 quality diagnostics for WP5 candidates.

Diagnostics are deliberately separate from the WP5 opportunity score and from
formal business outcomes.  The module can replay pinned evidence and optionally
append a diagnostic revision to a local immutable JSONL store.
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

from .candidate_store import CandidateStore
from .evidence import EvidenceStore
from .proposal_validation import ValidationError, ValidationResult
from .store.errors import ImmutableStoreError
from .store.registry import RegistryLookup
from .store.serialization import SerializationError, canonical_line, canonical_json, content_hash
from .entities import RegistryInputError, normalize_url
from reporting.sources.ga4_quality import SOURCE_CLASS, SUPPORTED_METRICS, resolve_registry_url


DIAGNOSTIC_CONTRACT_VERSION = "1.0.0-proposal"
DIAGNOSTIC_RULE_VERSION = "ga4-quality-proposal-1"
DIAGNOSTIC_STATUSES = frozenset({"QUALITY_HEALTHY", "QUALITY_WEAK", "QUALITY_MIXED", "INSUFFICIENT_GA4_EVIDENCE", "CONFLICTING_GA4_EVIDENCE"})
CONVERSION_BOUNDARY = "DIAGNOSTIC_ONLY"
ORGANIC_CHANNEL = "Organic Search"
CURRENT_MAX_AGE_DAYS = 7


class GA4DiagnosticInputError(ValueError):
    """Raised when a GA4 diagnostic input cannot be joined or replayed safely."""

    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


@dataclass(frozen=True)
class GA4DiagnosticInput:
    candidate_id: str
    candidate_revision: int
    topic_cluster_id: str
    canonical_url_id: str
    target_url: str
    evaluation_period: str
    decision_at: str
    registry: Mapping[str, Any]
    ga4_evidence: tuple[Mapping[str, Any], ...]
    candidate_evidence_refs: tuple[Mapping[str, Any], ...] = ()
    wp5_score: Optional[int] = None
    wp5_confidence: str = "NOT_ASSESSABLE"
    acquisition_context: Mapping[str, Any] = field(default_factory=dict)
    expected_channel: str = ORGANIC_CHANNEL
    quality_scope: str = "PAGE_LEVEL"
    diagnostic_rule_version: str = DIAGNOSTIC_RULE_VERSION

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GA4DiagnosticInput":
        if not isinstance(value, Mapping):
            raise GA4DiagnosticInputError("INVALID_INPUT", "diagnostic input must be a mapping")
        required = ("candidate_id", "candidate_revision", "topic_cluster_id", "canonical_url_id", "target_url", "evaluation_period", "decision_at", "registry")
        missing = [name for name in required if not value.get(name)]
        if missing:
            raise GA4DiagnosticInputError("MISSING_FIELD", "missing diagnostic fields: " + ", ".join(missing))
        revision = value["candidate_revision"]
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise GA4DiagnosticInputError("INVALID_REVISION", "candidate_revision must be a positive integer", "candidate_revision")
        try:
            decision = datetime.fromisoformat(str(value["decision_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise GA4DiagnosticInputError("INVALID_DATETIME", "decision_at must be ISO-8601", "decision_at") from exc
        if decision.tzinfo is None:
            raise GA4DiagnosticInputError("NAIVE_DATETIME", "decision_at must include a timezone", "decision_at")
        ga4 = value.get("ga4_evidence", ())
        if isinstance(ga4, Mapping):
            ga4 = tuple(ga4.values())
        if not isinstance(ga4, (list, tuple)):
            raise GA4DiagnosticInputError("INVALID_EVIDENCE", "ga4_evidence must be a list or mapping", "ga4_evidence")
        candidate_refs = value.get("candidate_evidence_refs", ())
        if not isinstance(candidate_refs, (list, tuple)):
            raise GA4DiagnosticInputError("INVALID_EVIDENCE", "candidate_evidence_refs must be a list", "candidate_evidence_refs")
        return cls(
            candidate_id=str(value["candidate_id"]),
            candidate_revision=revision,
            topic_cluster_id=str(value["topic_cluster_id"]),
            canonical_url_id=str(value["canonical_url_id"]),
            target_url=str(value["target_url"]),
            evaluation_period=str(value["evaluation_period"]),
            decision_at=str(value["decision_at"]),
            registry=value["registry"],
            ga4_evidence=tuple(dict(item) for item in ga4 if isinstance(item, Mapping)),
            candidate_evidence_refs=tuple(dict(item) for item in candidate_refs if isinstance(item, Mapping)),
            wp5_score=value.get("wp5_score"),
            wp5_confidence=str(value.get("wp5_confidence", "NOT_ASSESSABLE")),
            acquisition_context=dict(value.get("acquisition_context") or {}),
            expected_channel=str(value.get("expected_channel", ORGANIC_CHANNEL)),
            quality_scope=str(value.get("quality_scope", "PAGE_LEVEL")),
            diagnostic_rule_version=str(value.get("diagnostic_rule_version", DIAGNOSTIC_RULE_VERSION)),
        )


@dataclass
class GA4DiagnosticResult:
    diagnostic: Optional[dict[str, Any]]
    validation: ValidationResult
    persisted: bool = False
    persistence_error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.validation.is_valid

    def as_dict(self) -> dict[str, Any]:
        return {
            "diagnostic": self.diagnostic,
            "validation": self.validation.as_dict(),
            "persisted": self.persisted,
            "persistence_error": self.persistence_error,
        }


def _ref(value: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    evidence_id = value.get("evidence_id")
    revision = value.get("revision")
    evidence_hash = value.get("content_hash")
    if not isinstance(evidence_id, str) or not evidence_id or not isinstance(revision, int) or isinstance(revision, bool) or revision < 1 or not isinstance(evidence_hash, str) or len(evidence_hash) != 64:
        raise GA4DiagnosticInputError("MISSING_EVIDENCE_PIN", f"{field_name} must pin evidence_id, revision and content_hash", field_name)
    return {"evidence_id": evidence_id, "revision": revision, "content_hash": evidence_hash}


def _date(value: Any) -> date:
    return date.fromisoformat(str(value))


def _fresh(record: Mapping[str, Any], decision_at: date) -> bool:
    if str(record.get("freshness_state", "")).upper() != "READY" or str(record.get("collection_status", "SUCCESS")).upper() not in {"SUCCESS", "READY"}:
        return False
    observed = record.get("as_of") or record.get("period_end")
    try:
        return observed is not None and 0 <= (decision_at - _date(observed)).days <= CURRENT_MAX_AGE_DAYS
    except (TypeError, ValueError):
        return False


def _canonical_url(input_value: GA4DiagnosticInput) -> Mapping[str, Any]:
    try:
        normalized = normalize_url(input_value.target_url)
    except RegistryInputError as exc:
        raise GA4DiagnosticInputError(exc.code, str(exc), "target_url") from exc
    try:
        url_id, row = resolve_registry_url(input_value.registry, normalized)
    except Exception as exc:
        if isinstance(exc, GA4DiagnosticInputError):
            raise
        raise GA4DiagnosticInputError("UNRESOLVED_ENTITY", "target_url does not resolve in canonical registry", "target_url") from exc
    if url_id != input_value.canonical_url_id:
        raise GA4DiagnosticInputError("CANONICAL_URL_MISMATCH", "canonical_url_id does not match exact normalized URL", "canonical_url_id")
    if input_value.topic_cluster_id not in (row.get("canonical_topic_refs") or []):
        raise GA4DiagnosticInputError("TOPIC_URL_MAPPING_CONFLICT", "canonical URL is not mapped to the supplied topic", "topic_cluster_id")
    return row


def _metric_rows(input_value: GA4DiagnosticInput, decision_day: date) -> tuple[list[dict[str, Any]], list[str], list[str]]:
    rows: list[dict[str, Any]] = []
    missing: list[str] = []
    conflicts: list[str] = []
    for raw in input_value.ga4_evidence:
        row = dict(raw)
        if row.get("source") != "GA4" or row.get("source_class") != SOURCE_CLASS:
            conflicts.append("GA4_SOURCE_CLASS_MISMATCH")
            continue
        if input_value.quality_scope == "PAGE_LEVEL" and row.get("url_id") != input_value.canonical_url_id:
            conflicts.append("GA4_URL_JOIN_MISMATCH")
            continue
        if row.get("channel") != input_value.expected_channel:
            conflicts.append("WRONG_CHANNEL_SEGMENT")
            continue
        if input_value.quality_scope == "PAGE_LEVEL" and not row.get("normalized_url"):
            conflicts.append("SITE_WIDE_CONTEXT_ONLY")
            continue
        if row.get("metric") not in SUPPORTED_METRICS:
            conflicts.append("UNSUPPORTED_GA4_METRIC")
            continue
        row["_is_current"] = _fresh(row, decision_day)
        rows.append(row)
    if input_value.quality_scope == "SITE_WIDE_CONTEXT" and rows:
        conflicts.append("SITE_WIDE_CONTEXT_ONLY")
    if not rows:
        missing.append("page_level_organic_ga4_evidence")
    stale = [row for row in rows if not row["_is_current"]]
    if stale:
        missing.append("fresh_current_ga4_evidence")
    return rows, sorted(set(missing)), sorted(set(conflicts))


def _values(rows: list[dict[str, Any]], metric: str) -> dict[str, tuple[Any, list[str]]]:
    output: dict[str, tuple[Any, list[str]]] = {}
    for row in rows:
        if row.get("metric") != metric or not row.get("_is_current"):
            continue
        period = str(row.get("period_end"))
        refs = list(output.get(period, (None, []))[1])
        refs.append(str(row.get("evidence_id")))
        value = row.get("value")
        if period in output and output[period][0] != value:
            raise GA4DiagnosticInputError("CONFLICTING_GA4_EVIDENCE", f"conflicting current GA4 {metric} values for {period}", metric)
        output[period] = (value, sorted(set(refs)))
    return output


def _trend(values: dict[str, tuple[Any, list[str]]]) -> tuple[str, Optional[str], list[str]]:
    periods = sorted(values)
    if len(periods) < 2:
        return "INSUFFICIENT_HISTORY", None, sorted({ref for _, refs in values.values() for ref in refs})
    previous, current = periods[-2], periods[-1]
    old, refs_old = values[previous]
    new, refs_new = values[current]
    if old is None or new is None:
        return "UNKNOWN", current, sorted(set(refs_old + refs_new))
    signal = "STABLE" if new == old else ("INCREASING" if new > old else "DECLINING")
    return signal, current, sorted(set(refs_old + refs_new))


def _acquisition_conflict(context: Mapping[str, Any], traffic_signal: str, conflicts: list[str], rule_trace: list[str]) -> None:
    if not context:
        return
    if any(key in context for key in ("ai_assistant_sessions", "external_leads", "sql", "revenue")):
        conflicts.append("AI_ASSISTANT_ATTRIBUTION_UNRESOLVED")
        rule_trace.append("AI Assistant and external business populations are not divided into a CVR")
    current = context.get("gsc_clicks_current")
    previous = context.get("gsc_clicks_previous")
    if isinstance(current, (int, float)) and isinstance(previous, (int, float)):
        gsc_signal = "STABLE" if current == previous else ("INCREASING" if current > previous else "DECLINING")
        if traffic_signal not in {"INSUFFICIENT_HISTORY", "UNKNOWN"} and gsc_signal != traffic_signal:
            conflicts.append("GSC_GA4_ACQUISITION_BEHAVIOR_CONFLICT")
            rule_trace.append("GSC clicks and GA4 Organic Search sessions are retained as separate signals")


def _diagnostic_id(input_value: GA4DiagnosticInput) -> str:
    seed = {"candidate_id": input_value.candidate_id, "candidate_revision": input_value.candidate_revision, "canonical_url_id": input_value.canonical_url_id, "evaluation_period": input_value.evaluation_period}
    return "G4D_" + hashlib.sha256(canonical_json(seed).encode("utf-8")).hexdigest()[:24]


def _input_signature(input_value: GA4DiagnosticInput) -> str:
    refs = [_ref(row, "ga4_evidence") for row in input_value.ga4_evidence]
    seed = {"diagnostic_id": _diagnostic_id(input_value), "ga4_refs": sorted(refs, key=lambda item: (item["evidence_id"], item["revision"])), "candidate_refs": list(input_value.candidate_evidence_refs), "rule": input_value.diagnostic_rule_version}
    return hashlib.sha256(canonical_json(seed).encode("utf-8")).hexdigest()


def validate_ga4_diagnostic(payload: Any, *, context: Optional[Mapping[str, Any]] = None) -> ValidationResult:
    """Validate proposal shape and safety invariants without network access."""

    errors: list[ValidationError] = []
    if not isinstance(payload, Mapping):
        return ValidationResult(errors=[ValidationError("SCHEMA_VIOLATION", "$", "Diagnostic must be a mapping")])
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        schema = json.loads((Path(__file__).resolve().parents[2] / "contracts/ga4_quality_diagnostics.v1.proposal.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        errors.extend(ValidationError("SCHEMA_VIOLATION", ".".join(map(str, error.absolute_path)) or "$", "Diagnostic violates the proposal schema.", rule=str(error.validator)) for error in validator.iter_errors(payload))
    except Exception as exc:
        errors.append(ValidationError("SCHEMA_VALIDATION_ERROR", "$", str(exc)))
    if payload.get("conversion_boundary") != CONVERSION_BOUNDARY:
        errors.append(ValidationError("CONVERSION_POLICY_GAP", "conversion_boundary", "GA4 diagnostics must remain DIAGNOSTIC_ONLY"))
    if payload.get("wp5_score_preserved") is not True:
        errors.append(ValidationError("WP5_SCORE_MUTATION", "wp5_score_preserved", "WP6 must preserve WP5 score"))
    if payload.get("diagnostic_status") not in DIAGNOSTIC_STATUSES:
        errors.append(ValidationError("INVALID_DIAGNOSTIC_STATUS", "diagnostic_status", "Unknown diagnostic status"))
    try:
        diagnostic_hash = content_hash(payload)
        if payload.get("content_hash") != diagnostic_hash:
            errors.append(ValidationError("CONTENT_HASH_MISMATCH", "content_hash", "Diagnostic content hash mismatch"))
    except (SerializationError, TypeError, ValueError):
        errors.append(ValidationError("NONFINITE_NUMBER", "content_hash", "Diagnostic contains an unsupported value"))
    for field_name in ("ga4_evidence_refs", "candidate_evidence_refs"):
        seen: set[tuple[str, int]] = set()
        for index, item in enumerate(payload.get(field_name, []) or []):
            try:
                item_ref = _ref(item, f"{field_name}[{index}]")
            except GA4DiagnosticInputError as exc:
                errors.append(ValidationError(exc.code, f"{field_name}[{index}]", str(exc)))
                continue
            key = (item_ref["evidence_id"], item_ref["revision"])
            if key in seen:
                errors.append(ValidationError("DUPLICATE_EVIDENCE_REFERENCE", field_name, "Evidence refs must be unique"))
            seen.add(key)
            if context and context.get("evidence_store") is not None:
                try:
                    context["evidence_store"].resolve_reference(item_ref["evidence_id"], item_ref["revision"], item_ref["content_hash"])
                except Exception:
                    errors.append(ValidationError("EVIDENCE_PIN_INVALID", field_name, "Pinned evidence does not resolve exactly"))
    return ValidationResult(errors=errors)


class GA4DiagnosticStore:
    """Append-only local diagnostic store with exact evidence pinning."""

    def __init__(self, root: str | os.PathLike[str], *, evidence_store: EvidenceStore, registry: Mapping[str, Any]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "ga4_diagnostics.jsonl"
        self.evidence_store = evidence_store
        self.registry = RegistryLookup(registry)
        self._records: dict[tuple[str, int], dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ImmutableStoreError("STORE_CORRUPTION", f"invalid diagnostic JSON at line {line_number}") from exc
            prepared = self._prepare(record)
            self._validate(prepared)
            key = (prepared["diagnostic_id"], prepared["revision"])
            if key in self._records:
                raise ImmutableStoreError("STORE_CORRUPTION", "duplicate diagnostic revision")
            self._records[key] = prepared

    def _prepare(self, record: Mapping[str, Any]) -> dict[str, Any]:
        value = copy.deepcopy(dict(record))
        value.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        try:
            calculated = content_hash(value)
        except SerializationError as exc:
            raise ImmutableStoreError("NONFINITE_NUMBER", "diagnostic contains a non-finite number") from exc
        if value.get("content_hash") is not None and value["content_hash"] != calculated:
            raise ImmutableStoreError("HASH_MISMATCH", "diagnostic content hash mismatch", "content_hash")
        value["content_hash"] = calculated
        return value

    def _validate(self, record: Mapping[str, Any]) -> None:
        required = ("record_type", "diagnostic_id", "revision", "candidate_id", "candidate_revision", "canonical_url_id", "ga4_evidence_refs", "candidate_evidence_refs", "diagnostic_status", "conversion_boundary", "content_hash", "created_at")
        for field_name in required:
            if field_name not in record:
                raise ImmutableStoreError("MISSING_FIELD", f"required diagnostic field is missing: {field_name}", field_name)
        if record["record_type"] != "GA4_DIAGNOSTIC" or record["conversion_boundary"] != CONVERSION_BOUNDARY:
            raise ImmutableStoreError("INVALID_DIAGNOSTIC_CONTRACT", "invalid diagnostic record type or conversion boundary")
        if not isinstance(record["revision"], int) or isinstance(record["revision"], bool) or record["revision"] < 1:
            raise ImmutableStoreError("INVALID_REVISION", "diagnostic revision must be positive")
        if not self.registry.has("URL", record["canonical_url_id"]):
            raise ImmutableStoreError("UNRESOLVED_ENTITY", "diagnostic canonical_url_id is not in registry", "canonical_url_id")
        for field_name in ("ga4_evidence_refs", "candidate_evidence_refs"):
            refs = record[field_name]
            if not isinstance(refs, list):
                raise ImmutableStoreError("INVALID_EVIDENCE_REFERENCE", f"{field_name} must be a list")
            for index, ref in enumerate(refs):
                if not isinstance(ref, Mapping) or not isinstance(ref.get("evidence_id"), str) or not isinstance(ref.get("revision"), int) or not isinstance(ref.get("content_hash"), str):
                    raise ImmutableStoreError("MISSING_EVIDENCE_REVISION", "diagnostic evidence refs must pin id, revision and hash", f"{field_name}[{index}]")
                self.evidence_store.resolve_reference(ref["evidence_id"], ref["revision"], ref["content_hash"])
        try:
            parsed = datetime.fromisoformat(str(record["created_at"]).replace("Z", "+00:00"))
        except ValueError as exc:
            raise ImmutableStoreError("INVALID_DATETIME", "diagnostic created_at is not ISO-8601") from exc
        if parsed.tzinfo is None:
            raise ImmutableStoreError("NAIVE_DATETIME", "diagnostic created_at must include timezone")

    def append_diagnostic(self, record: Mapping[str, Any]) -> dict[str, Any]:
        prepared = self._prepare(record)
        self._validate(prepared)
        key = (prepared["diagnostic_id"], prepared["revision"])
        existing = self._records.get(key)
        if existing is not None:
            if existing["content_hash"] == prepared["content_hash"]:
                return {**copy.deepcopy(existing), "idempotent": True}
            raise ImmutableStoreError("REVISION_CONFLICT", "same diagnostic revision has a different content hash")
        revisions = sorted(revision for diagnostic_id, revision in self._records if diagnostic_id == prepared["diagnostic_id"])
        expected = revisions[-1] + 1 if revisions else 1
        if prepared["revision"] != expected:
            raise ImmutableStoreError("REVISION_GAP", "diagnostic revisions must append contiguously")
        if prepared["revision"] == 1:
            if prepared.get("supersedes_diagnostic_revision") is not None:
                raise ImmutableStoreError("INVALID_SUPERSEDES", "revision 1 cannot supersede")
        elif prepared.get("supersedes_diagnostic_revision") != prepared["revision"] - 1:
            raise ImmutableStoreError("INVALID_SUPERSEDES", "diagnostic revision must supersede prior revision")
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(canonical_line(prepared))
            handle.flush()
            os.fsync(handle.fileno())
        self._records[key] = copy.deepcopy(prepared)
        return copy.deepcopy(prepared)

    def get_diagnostic(self, diagnostic_id: str, revision: Optional[int] = None) -> Optional[dict[str, Any]]:
        if revision is None:
            revisions = [value for did, value in self._records if did == diagnostic_id]
            if not revisions:
                return None
            revision = max(revisions)
        value = self._records.get((diagnostic_id, revision))
        return copy.deepcopy(value) if value is not None else None

    def history(self, diagnostic_id: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._records[(diagnostic_id, revision)]) for revision in sorted(revision for did, revision in self._records if did == diagnostic_id)]


def _build_diagnostic(input_value: GA4DiagnosticInput, *, revision: int, supersedes: Optional[int]) -> dict[str, Any]:
    _canonical_url(input_value)
    decision_day = _date(input_value.decision_at[:10])
    rows, missing, conflicts = _metric_rows(input_value, decision_day)
    rule_trace: list[str] = ["Join GA4 landing_page to the exact WP3 canonical URL revision", "Use Organic Search page-level evidence only for SEO candidate quality"]
    current_rows = [row for row in rows if row["_is_current"]]
    sessions = _values(rows, "sessions")
    engagement = _values(rows, "engagement_rate")
    traffic_signal, current_period, traffic_refs = _trend(sessions)
    engagement_signal, _, engagement_refs = _trend(engagement)
    if not sessions:
        missing.append("sessions")
    if not engagement:
        missing.append("engagement_rate")
    if current_rows and any(row.get("freshness_state") not in {"READY"} for row in current_rows):
        missing.append("fresh_current_ga4_evidence")
    cta_rows = [row for row in current_rows if row.get("metric") == "event_count"]
    cta_rows = [row for row in cta_rows if row.get("event_classification") == "CTA_INTERACTION"]
    unmapped_events = [row for row in current_rows if row.get("metric") == "event_count" and row.get("event_classification") != "CTA_INTERACTION"]
    if unmapped_events:
        conflicts.append("CTA_EVENT_MAPPING_UNRESOLVED")
    if cta_rows:
        cta_value = sum(row["value"] for row in cta_rows if isinstance(row.get("value"), int))
        cta_signal = "CTA_SIGNAL_PRESENT" if cta_value > 0 else "CTA_SIGNAL_WEAK"
    else:
        cta_value = None
        cta_signal = "CTA_SIGNAL_NOT_AVAILABLE"
        # CTA rows are optional diagnostic evidence.  Their absence must not
        # turn otherwise complete traffic/engagement evidence into missing
        # quality evidence; the explicit signal preserves that absence.
    _acquisition_conflict(input_value.acquisition_context, traffic_signal, conflicts, rule_trace)
    conflicts = sorted(set(conflicts))
    missing = sorted(set(missing))
    if conflicts:
        status = "CONFLICTING_GA4_EVIDENCE"
    elif missing or not current_rows:
        status = "INSUFFICIENT_GA4_EVIDENCE"
    elif traffic_signal == "DECLINING" and engagement_signal == "DECLINING":
        status = "QUALITY_WEAK"
        rule_trace.append("Both Organic Search sessions and engagement rate declined across comparable periods")
    elif traffic_signal == "DECLINING" or engagement_signal == "DECLINING":
        status = "QUALITY_MIXED"
        rule_trace.append("One behavior signal declined while the other remained stable or increased")
    else:
        status = "QUALITY_HEALTHY"
        rule_trace.append("No declining page-level Organic Search behavior signal was observed")
    diagnostic_types = [status]
    if traffic_signal == "DECLINING":
        diagnostic_types.append("TRAFFIC_DECLINING")
    if engagement_signal == "DECLINING":
        diagnostic_types.append("ENGAGEMENT_DECLINING")
    if engagement_signal == "STABLE":
        diagnostic_types.append("ENGAGEMENT_STABLE")
    if cta_signal in {"CTA_SIGNAL_PRESENT", "CTA_SIGNAL_WEAK"}:
        diagnostic_types.append(cta_signal)
    if status in {"QUALITY_HEALTHY", "QUALITY_WEAK", "QUALITY_MIXED"} and not conflicts and not missing:
        diagnostic_confidence = "MEDIUM"
    else:
        diagnostic_confidence = "LOW"
    refs = [_ref(row, "ga4_evidence") for row in input_value.ga4_evidence]
    refs = sorted(refs, key=lambda item: (item["evidence_id"], item["revision"]))
    freshness = [
        {"evidence_id": row.get("evidence_id"), "revision": row.get("revision"), "period_end": row.get("period_end"), "as_of": row.get("as_of"), "retrieved_at": row.get("retrieved_at"), "freshness_state": row.get("freshness_state"), "collection_status": row.get("collection_status"), "channel": row.get("channel"), "url_id": row.get("url_id")}
        for row in sorted(input_value.ga4_evidence, key=lambda item: str(item.get("evidence_id")))
    ]
    diagnostic: dict[str, Any] = {
        "record_type": "GA4_DIAGNOSTIC",
        "contract_version": DIAGNOSTIC_CONTRACT_VERSION,
        "diagnostic_id": _diagnostic_id(input_value),
        "revision": revision,
        "supersedes_diagnostic_revision": supersedes,
        "candidate_id": input_value.candidate_id,
        "candidate_revision": input_value.candidate_revision,
        "topic_cluster_id": input_value.topic_cluster_id,
        "canonical_url_id": input_value.canonical_url_id,
        "target_url": input_value.target_url,
        "evaluation_period": input_value.evaluation_period,
        "quality_scope": input_value.quality_scope,
        "channel": input_value.expected_channel,
        "source_role": SOURCE_CLASS,
        "ga4_evidence_refs": refs,
        "candidate_evidence_refs": sorted([_ref(row, "candidate_evidence_refs") for row in input_value.candidate_evidence_refs], key=lambda item: (item["evidence_id"], item["revision"])),
        "diagnostic_status": status,
        "diagnostic_types": sorted(set(diagnostic_types)),
        "diagnostic_confidence": diagnostic_confidence,
        "signals": {
            "traffic_signal": traffic_signal,
            "engagement_signal": engagement_signal,
            "cta_signal": cta_signal,
            "cta_event_count": cta_value,
            "current_period": current_period,
            "traffic_evidence_refs": traffic_refs,
            "engagement_evidence_refs": engagement_refs,
        },
        "conflicts": conflicts,
        "missing_evidence": missing,
        "freshness": freshness,
        "rule_trace": rule_trace,
        "conversion_boundary": CONVERSION_BOUNDARY,
        "wp5_score": input_value.wp5_score,
        "wp5_confidence": input_value.wp5_confidence,
        "wp5_score_preserved": True,
        "created_at": input_value.decision_at,
        "updated_at": input_value.decision_at,
    }
    diagnostic["content_hash"] = content_hash(diagnostic)
    return diagnostic


def evaluate_ga4_diagnostic(
    value: GA4DiagnosticInput | Mapping[str, Any],
    *,
    candidate_store: Optional[CandidateStore] = None,
    diagnostic_store: Optional[GA4DiagnosticStore] = None,
    evidence_store: Optional[EvidenceStore] = None,
    persist: bool = False,
) -> GA4DiagnosticResult:
    """Evaluate a pinned candidate and synthetic GA4 evidence offline."""

    if evidence_store is None and diagnostic_store is not None:
        evidence_store = diagnostic_store.evidence_store
    raw = dict(value) if isinstance(value, Mapping) else None
    if candidate_store is not None:
        if raw is None:
            raw = {field_name: getattr(value, field_name) for field_name in ("candidate_id", "candidate_revision", "topic_cluster_id", "canonical_url_id", "target_url", "evaluation_period", "decision_at", "registry", "ga4_evidence", "candidate_evidence_refs", "wp5_score", "wp5_confidence", "acquisition_context", "expected_channel", "quality_scope", "diagnostic_rule_version")}
        candidate = candidate_store.get_candidate(str(raw.get("candidate_id")), int(raw.get("candidate_revision", 1)))
        if candidate is None:
            validation = ValidationResult(errors=[ValidationError("MISSING_CANDIDATE", "candidate_id", "Candidate revision does not resolve in CandidateStore")])
            return GA4DiagnosticResult(None, validation)
        if not raw.get("candidate_evidence_refs"):
            raw["candidate_evidence_refs"] = candidate.get("evidence_refs", [])
        if not raw.get("topic_cluster_id"):
            raw["topic_cluster_id"] = (candidate.get("topic_ref") or {}).get("entity_id")
        if not raw.get("target_url"):
            raw["target_url"] = candidate.get("target_url")
        if raw.get("wp5_score") is None:
            raw["wp5_score"] = candidate.get("score")
        if not raw.get("wp5_confidence") or raw.get("wp5_confidence") == "NOT_ASSESSABLE":
            raw["wp5_confidence"] = candidate.get("confidence", "NOT_ASSESSABLE")
        evidence_store = evidence_store or candidate_store.evidence_store
    try:
        input_value = GA4DiagnosticInput.from_mapping(raw) if raw is not None else value
        if not isinstance(input_value, GA4DiagnosticInput):
            raise GA4DiagnosticInputError("INVALID_INPUT", "diagnostic input must be GA4DiagnosticInput or mapping")
        _canonical_url(input_value)
        if not input_value.ga4_evidence:
            raise GA4DiagnosticInputError("MISSING_GA4_EVIDENCE", "at least one GA4 evidence revision is required", "ga4_evidence")
        for row in input_value.ga4_evidence:
            _ref(row, "ga4_evidence")
        for row in input_value.candidate_evidence_refs:
            _ref(row, "candidate_evidence_refs")
        signature = _input_signature(input_value)
        revision = 1
        supersedes = None
        if diagnostic_store is not None:
            history = diagnostic_store.history(_diagnostic_id(input_value))
            if history and history[-1].get("input_signature") != signature:
                revision = int(history[-1]["revision"]) + 1
                supersedes = revision - 1
            elif history:
                revision = int(history[-1]["revision"])
        diagnostic = _build_diagnostic(input_value, revision=revision, supersedes=supersedes)
        diagnostic["input_signature"] = signature
        diagnostic["content_hash"] = content_hash(diagnostic)
        validation = validate_ga4_diagnostic(diagnostic, context={"evidence_store": evidence_store} if evidence_store else None)
        if not validation.is_valid:
            return GA4DiagnosticResult(None, validation)
        persisted = False
        persistence_error = None
        output = copy.deepcopy(diagnostic)
        if persist:
            if diagnostic_store is None:
                persistence_error = "persist=True requires diagnostic_store"
            else:
                try:
                    output = diagnostic_store.append_diagnostic(diagnostic)
                    persisted = True
                except Exception as exc:
                    persistence_error = f"{type(exc).__name__}: {exc}"
        return GA4DiagnosticResult(output, validation, persisted, persistence_error)
    except (GA4DiagnosticInputError, RegistryInputError) as exc:
        return GA4DiagnosticResult(None, ValidationResult(errors=[ValidationError(getattr(exc, "code", "INVALID_INPUT"), getattr(exc, "field", "record"), str(exc))]))


__all__ = [
    "DIAGNOSTIC_CONTRACT_VERSION",
    "DIAGNOSTIC_RULE_VERSION",
    "GA4DiagnosticInput",
    "GA4DiagnosticResult",
    "GA4DiagnosticStore",
    "evaluate_ga4_diagnostic",
    "validate_ga4_diagnostic",
]
