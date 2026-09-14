"""Offline, append-only outcome tracking for reviewed opportunity actions.

WP11 is a measurement boundary.  It evaluates pinned synthetic observations
against an approved measurement plan; it never changes a Candidate, Score,
Confidence, Review, Bridge, or a production destination.  The implementation
is intentionally usable with plain mappings so replay jobs and tests can feed
the exact same payload without a source adapter or a clock.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
from zoneinfo import ZoneInfo

from .proposal_validation import ValidationError, ValidationResult
from .store.errors import ImmutableStoreError
from .store.serialization import canonical_json, canonical_line, content_hash


CONTRACT_VERSION = "outcome_tracking.v1.proposal"
IMPLEMENTATION_CONTRACT_VERSION = "implementation_event.v1.proposal"
RULE_VERSION = "outcome-tracking-proposal-1"
RECORD_TYPE = "OUTCOME_TRACK"
IMPLEMENTATION_RECORD_TYPE = "IMPLEMENTATION_EVENT"
REPORTING_TIMEZONE = "Asia/Taipei"
OUTCOME_STATES = frozenset({"WON", "PARTIAL_WIN", "NO_CHANGE", "LOST", "INSUFFICIENT_DATA"})
CHECKPOINTS = frozenset({"30D", "60D", "90D"})
TRACKING_STATUSES = frozenset({"EVALUATED", "NOT_ELIGIBLE", "OBSERVATION_ONLY"})
IMPLEMENTATION_EVENTS = frozenset({"IMPLEMENTED", "CANCELLED", "MONITORING_ONLY"})
ACTION_STATUSES = frozenset({"NOT_STARTED", "IN_PROGRESS", "COMPLETED", "CANCELLED"})
FRESHNESS_STATES = frozenset({"READY", "PARTIAL", "STALE", "FAILED", "NOT_AVAILABLE", "MISSING", "NOT_COMPARABLE"})
SOURCE_ROLES = {
    "GSC": "FIRST_PARTY_SEARCH_ACTUAL",
    "GA4": "FIRST_PARTY_BEHAVIOR_DIAGNOSTIC",
    "GEO": "MONITORED_FIXED_SAMPLE",
    "WORKDUO": "MONITORED_FIXED_SAMPLE",
    "SERP": "LIVE_SERP_SNAPSHOT",
    "SF": "TECHNICAL_CRAWL_EVIDENCE",
    "CRUX": "FIELD_UX_EVIDENCE",
    "BUSINESS": "BUSINESS_ACTUAL",
}
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_HASH = re.compile(r"^[a-f0-9]{64}$")


class OutcomeInputError(ValueError):
    """Raised for an unsafe outcome tracking input."""

    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


def _sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _parse_datetime(value: Any, field_name: str = "datetime") -> datetime:
    if not isinstance(value, str):
        raise OutcomeInputError("INVALID_DATETIME", f"{field_name} must be ISO-8601 text", field_name)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise OutcomeInputError("INVALID_DATETIME", f"{field_name} must be ISO-8601 text", field_name) from exc
    if parsed.tzinfo is None:
        raise OutcomeInputError("NAIVE_DATETIME", f"{field_name} must include a timezone", field_name)
    return parsed


def _parse_date(value: Any, field_name: str) -> date:
    if not isinstance(value, str):
        raise OutcomeInputError("INVALID_DATE", f"{field_name} must be an ISO date", field_name)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise OutcomeInputError("INVALID_DATE", f"{field_name} must be an ISO date", field_name) from exc


def _ref(value: Any, field_name: str = "evidence_ref") -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise OutcomeInputError("MISSING_EVIDENCE_PIN", f"{field_name} must pin an evidence revision", field_name)
    evidence_id, revision, evidence_hash = value.get("evidence_id"), value.get("revision"), value.get("content_hash")
    if not isinstance(evidence_id, str) or not _SAFE_REF.fullmatch(evidence_id):
        raise OutcomeInputError("INVALID_EVIDENCE_ID", f"{field_name}.evidence_id is invalid", field_name)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise OutcomeInputError("INVALID_EVIDENCE_REVISION", f"{field_name}.revision must be positive", field_name)
    if not isinstance(evidence_hash, str) or not _HASH.fullmatch(evidence_hash):
        raise OutcomeInputError("INVALID_EVIDENCE_HASH", f"{field_name}.content_hash must be SHA-256", field_name)
    return {"evidence_id": evidence_id, "revision": revision, "content_hash": evidence_hash}


def _refs(values: Any, field_name: str = "evidence_refs") -> list[dict[str, Any]]:
    if values is None:
        return []
    if not isinstance(values, (list, tuple)):
        raise OutcomeInputError("INVALID_EVIDENCE_REFS", f"{field_name} must be a list", field_name)
    result = [_ref(value, f"{field_name}[{index}]") for index, value in enumerate(values)]
    keys = [(item["evidence_id"], item["revision"]) for item in result]
    if len(keys) != len(set(keys)):
        raise OutcomeInputError("DUPLICATE_EVIDENCE_REFERENCE", f"{field_name} must be unique", field_name)
    return result


def _hash_pin(value: Any, field_name: str) -> tuple[str, int, str]:
    if not isinstance(value, Mapping):
        raise OutcomeInputError("MISSING_LINEAGE_PIN", f"{field_name} must be an exact revision/hash pin", field_name)
    ident = value.get("id") or value.get(field_name.removesuffix("_ref")) or value.get(field_name.replace("_ref", "_id"))
    revision = value.get("revision")
    hashed = value.get("content_hash") or value.get("hash")
    if not isinstance(ident, str) or not _SAFE_REF.fullmatch(ident):
        raise OutcomeInputError("INVALID_LINEAGE_ID", f"{field_name}.id is invalid", field_name)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise OutcomeInputError("INVALID_LINEAGE_REVISION", f"{field_name}.revision must be positive", field_name)
    if not isinstance(hashed, str) or not _HASH.fullmatch(hashed):
        raise OutcomeInputError("INVALID_LINEAGE_HASH", f"{field_name}.content_hash must be SHA-256", field_name)
    return ident, revision, hashed


def _lineage(value: Mapping[str, Any], prefix: str) -> tuple[str, int, str]:
    if prefix in value and isinstance(value[prefix], Mapping):
        return _hash_pin(value[prefix], prefix)
    return _hash_pin({"id": value.get(f"{prefix}_id"), "revision": value.get(f"{prefix}_revision"), "content_hash": value.get(f"{prefix}_hash", value.get(f"{prefix}_content_hash"))}, prefix)


def _candidate_payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if isinstance(value, Mapping) and isinstance(value.get("candidate"), Mapping):
        value = value["candidate"]
    if not isinstance(value, Mapping):
        raise OutcomeInputError("INVALID_CANDIDATE", "candidate must be a mapping", "candidate")
    result = copy.deepcopy(dict(value))
    candidate_id = result.get("candidate_id") or result.get("opportunity_id")
    revision = result.get("revision", result.get("candidate_revision"))
    candidate_hash = result.get("content_hash", result.get("candidate_hash"))
    if not isinstance(candidate_id, str) or not _SAFE_REF.fullmatch(candidate_id):
        raise OutcomeInputError("INVALID_CANDIDATE_ID", "candidate_id is invalid", "candidate_id")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise OutcomeInputError("INVALID_CANDIDATE_REVISION", "candidate revision must be positive", "revision")
    if not isinstance(candidate_hash, str) or not _HASH.fullmatch(candidate_hash):
        raise OutcomeInputError("MISSING_CANDIDATE_HASH", "candidate content_hash is required", "content_hash")
    if content_hash(result) != candidate_hash:
        raise OutcomeInputError("CANDIDATE_HASH_MISMATCH", "candidate revision hash does not match", "content_hash")
    result.update(candidate_id=candidate_id, revision=revision, content_hash=candidate_hash)
    return result


def _unwrap(value: Any, key: str) -> Optional[dict[str, Any]]:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if isinstance(value, Mapping) and isinstance(value.get(key), Mapping):
        value = value[key]
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else None


def _pin_record(value: Any, key: str, prefix: str) -> tuple[str, int, str]:
    payload = _unwrap(value, key)
    if payload is None:
        raise OutcomeInputError("INVALID_LINEAGE", f"{prefix} must be a mapping", prefix)
    return _lineage(payload, prefix)


def _window(completed_day: date, checkpoint: str) -> tuple[date, date]:
    if checkpoint == "BASELINE":
        end = completed_day - timedelta(days=1)
    else:
        days = int(checkpoint[:-1])
        end = completed_day + timedelta(days=days)
    # A 28-complete-day inclusive window.  The execution day is never in it.
    return end - timedelta(days=27), end


def expected_window(completed_at: str | datetime, checkpoint: str) -> dict[str, str]:
    """Return the source-of-truth 28-day window for baseline or 30/60/90D."""
    parsed = completed_at if isinstance(completed_at, datetime) else _parse_datetime(completed_at, "completed_at")
    local_day = parsed.astimezone(ZoneInfo(REPORTING_TIMEZONE)).date()
    checkpoint = str(checkpoint).upper()
    if checkpoint != "BASELINE" and checkpoint not in CHECKPOINTS:
        raise OutcomeInputError("INVALID_CHECKPOINT", "checkpoint must be BASELINE, 30D, 60D or 90D", "checkpoint")
    start, end = _window(local_day, checkpoint)
    return {"period_start": start.isoformat(), "period_end": end.isoformat(), "timezone": REPORTING_TIMEZONE, "complete_days": 28}


@dataclass(frozen=True)
class MeasurementPlan:
    primary_metric: str
    target_delta: float
    tolerance: float = 0.0
    minimum_sample: int = 1
    comparison_method: str = "RELATIVE_DELTA"
    direction: str = "INCREASE"
    support_metrics: tuple[str, ...] = ()
    guardrails: tuple[Mapping[str, Any], ...] = ()
    scope: str = "PAGE_LEVEL"
    source_population: Optional[str] = None
    attribution_limitations: tuple[str, ...] = ()
    planned_effort: Optional[str] = None
    attribution_contract_ref: Optional[str] = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "MeasurementPlan":
        if not isinstance(value, Mapping):
            raise OutcomeInputError("MISSING_MEASUREMENT_PLAN", "measurement_plan is required", "measurement_plan")
        primary = value.get("primary_metric") or value.get("primary_metric_id")
        if not isinstance(primary, str) or not primary:
            raise OutcomeInputError("MISSING_PRIMARY_METRIC", "primary_metric is required", "measurement_plan.primary_metric")
        target = value.get("target_delta")
        if not isinstance(target, (int, float)) or isinstance(target, bool):
            raise OutcomeInputError("MISSING_TARGET_DELTA", "target_delta must be numeric", "measurement_plan.target_delta")
        tolerance = value.get("tolerance", 0.0)
        minimum = value.get("minimum_sample", 1)
        if not isinstance(tolerance, (int, float)) or isinstance(tolerance, bool) or tolerance < 0:
            raise OutcomeInputError("INVALID_TOLERANCE", "tolerance must be non-negative", "measurement_plan.tolerance")
        if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
            raise OutcomeInputError("INVALID_MINIMUM_SAMPLE", "minimum_sample must be positive", "measurement_plan.minimum_sample")
        method = str(value.get("comparison_method", "RELATIVE_DELTA")).upper()
        if method not in {"RELATIVE_DELTA", "ABSOLUTE_DELTA"}:
            raise OutcomeInputError("INVALID_COMPARISON_METHOD", "comparison_method is unsupported", "measurement_plan.comparison_method")
        direction = str(value.get("direction", value.get("expected_direction", "INCREASE"))).upper()
        if direction not in {"INCREASE", "DECREASE", "STABLE"}:
            raise OutcomeInputError("INVALID_DIRECTION", "direction must be INCREASE, DECREASE or STABLE", "measurement_plan.direction")
        support = value.get("support_metrics", value.get("independent_support_metrics", ())) or ()
        if isinstance(support, str):
            support = (support,)
        if not isinstance(support, (list, tuple)) or any(not isinstance(item, str) or not item for item in support):
            raise OutcomeInputError("INVALID_SUPPORT_METRICS", "support_metrics must be metric names", "measurement_plan.support_metrics")
        guardrails = value.get("guardrails", ()) or ()
        if not isinstance(guardrails, (list, tuple)):
            raise OutcomeInputError("INVALID_GUARDRAILS", "guardrails must be a list", "measurement_plan.guardrails")
        limitations = value.get("attribution_limitations", ()) or ()
        if isinstance(limitations, str):
            limitations = (limitations,)
        contract_ref = value.get("attribution_contract_ref")
        if contract_ref is not None and (not isinstance(contract_ref, str) or not _SAFE_REF.fullmatch(contract_ref)):
            raise OutcomeInputError("INVALID_ATTRIBUTION_CONTRACT", "attribution_contract_ref must be an opaque reference", "measurement_plan.attribution_contract_ref")
        return cls(primary, float(target), float(tolerance), minimum, method, direction, tuple(support), tuple(copy.deepcopy(item) for item in guardrails), str(value.get("scope", "PAGE_LEVEL")), value.get("source_population"), tuple(str(item) for item in limitations), value.get("planned_effort"), contract_ref)

    def as_dict(self) -> dict[str, Any]:
        return {
            "primary_metric": self.primary_metric,
            "target_delta": self.target_delta,
            "tolerance": self.tolerance,
            "minimum_sample": self.minimum_sample,
            "comparison_method": self.comparison_method,
            "direction": self.direction,
            "support_metrics": list(self.support_metrics),
            "guardrails": copy.deepcopy(list(self.guardrails)),
            "scope": self.scope,
            "source_population": self.source_population,
            "attribution_limitations": list(self.attribution_limitations),
            "planned_effort": self.planned_effort,
            "attribution_contract_ref": self.attribution_contract_ref,
        }


@dataclass(frozen=True)
class MetricObservation:
    metric: str
    source: str
    value: Optional[float]
    period_start: str
    period_end: str
    evidence_ref: Mapping[str, Any]
    status: str = "READY"
    freshness_state: str = "READY"
    unit: Optional[str] = None
    scope: str = "PAGE_LEVEL"
    entity_ref: Optional[str] = None
    source_population: Optional[str] = None
    methodology: Optional[str] = None
    sample_size: Optional[int] = None
    timezone: str = REPORTING_TIMEZONE
    sample_version: Optional[str] = None
    sample_revision: Optional[int] = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any], field_name: str = "observation") -> "MetricObservation":
        if not isinstance(value, Mapping):
            raise OutcomeInputError("INVALID_OBSERVATION", f"{field_name} must be a mapping", field_name)
        metric = value.get("metric") or value.get("metric_id")
        source = str(value.get("source", "")).upper()
        if not isinstance(metric, str) or not metric or source not in SOURCE_ROLES:
            raise OutcomeInputError("INVALID_METRIC_IDENTITY", f"{field_name} requires metric and supported source", field_name)
        status = str(value.get("status", value.get("collection_status", "READY"))).upper()
        freshness = str(value.get("freshness_state", status)).upper()
        if status not in FRESHNESS_STATES and status not in {"SUCCESS", "READY"}:
            raise OutcomeInputError("INVALID_OBSERVATION_STATUS", f"{field_name}.status is unsupported", f"{field_name}.status")
        value_raw = value.get("value")
        if value_raw is not None and (not isinstance(value_raw, (int, float)) or isinstance(value_raw, bool)):
            raise OutcomeInputError("INVALID_METRIC_VALUE", f"{field_name}.value must be numeric or null", f"{field_name}.value")
        sample_size = value.get("sample_size", value.get("sample"))
        if sample_size is not None and (not isinstance(sample_size, int) or isinstance(sample_size, bool) or sample_size < 0):
            raise OutcomeInputError("INVALID_SAMPLE_SIZE", f"{field_name}.sample_size must be non-negative", f"{field_name}.sample_size")
        start, end = value.get("period_start"), value.get("period_end")
        _parse_date(start, f"{field_name}.period_start")
        _parse_date(end, f"{field_name}.period_end")
        return cls(str(metric), source, float(value_raw) if isinstance(value_raw, float) else value_raw, str(start), str(end), _ref(value.get("evidence_ref", value.get("evidence")), f"{field_name}.evidence_ref"), status if status != "SUCCESS" else "READY", freshness, value.get("unit"), str(value.get("scope", "PAGE_LEVEL")), value.get("entity_ref", value.get("url_id")), value.get("source_population"), value.get("methodology"), sample_size, str(value.get("timezone", REPORTING_TIMEZONE)), value.get("sample_version"), value.get("sample_revision"))

    def as_dict(self) -> dict[str, Any]:
        return {"metric": self.metric, "source": self.source, "source_role": SOURCE_ROLES[self.source], "value": self.value, "period_start": self.period_start, "period_end": self.period_end, "evidence_ref": copy.deepcopy(dict(self.evidence_ref)), "status": self.status, "freshness_state": self.freshness_state, "unit": self.unit, "scope": self.scope, "entity_ref": self.entity_ref, "source_population": self.source_population, "methodology": self.methodology, "sample_size": self.sample_size, "timezone": self.timezone, "sample_version": self.sample_version, "sample_revision": self.sample_revision}


@dataclass(frozen=True)
class ImplementationAnchor:
    implementation_event_id: str
    revision: int
    candidate_id: str
    candidate_revision: int
    candidate_hash: str
    review_id: str
    review_revision: int
    review_hash: str
    bridge_id: str
    bridge_revision: int
    bridge_hash: str
    action: str
    target_url: Optional[str]
    event_type: str
    completed_at: str
    deployment_ref: str
    change_ref: str
    created_at: str
    human_execution_owner: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        return {"record_type": IMPLEMENTATION_RECORD_TYPE, "contract_version": IMPLEMENTATION_CONTRACT_VERSION, "implementation_event_id": self.implementation_event_id, "revision": self.revision, "candidate_id": self.candidate_id, "candidate_revision": self.candidate_revision, "candidate_hash": self.candidate_hash, "review_id": self.review_id, "review_revision": self.review_revision, "review_hash": self.review_hash, "bridge_id": self.bridge_id, "bridge_revision": self.bridge_revision, "bridge_hash": self.bridge_hash, "action": self.action, "target_url": self.target_url, "event_type": self.event_type, "completed_at": self.completed_at, "deployment_ref": self.deployment_ref, "change_ref": self.change_ref, "human_execution_owner": self.human_execution_owner, "production_mutation": False, "created_at": self.created_at}


def _anchor_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, ImplementationAnchor):
        result = value.as_dict()
    elif hasattr(value, "as_dict"):
        result = value.as_dict()
    elif isinstance(value, Mapping) and isinstance(value.get("implementation_event"), Mapping):
        result = copy.deepcopy(dict(value["implementation_event"]))
    elif isinstance(value, Mapping):
        result = copy.deepcopy(dict(value))
    else:
        raise OutcomeInputError("INVALID_IMPLEMENTATION_ANCHOR", "implementation anchor must be a mapping", "implementation_anchor")
    required = ("implementation_event_id", "revision", "candidate_id", "candidate_revision", "candidate_hash", "review_id", "review_revision", "review_hash", "bridge_id", "bridge_revision", "bridge_hash", "action", "event_type", "completed_at", "deployment_ref", "change_ref", "created_at")
    result.setdefault("record_type", IMPLEMENTATION_RECORD_TYPE)
    result.setdefault("contract_version", IMPLEMENTATION_CONTRACT_VERSION)
    if "event_type" not in result and result.get("status") is not None:
        status = str(result["status"]).upper()
        result["event_type"] = {"COMPLETED": "IMPLEMENTED", "MONITOR": "MONITORING_ONLY"}.get(status, status)
    for field_name in required:
        if field_name not in result:
            raise OutcomeInputError("MISSING_IMPLEMENTATION_FIELD", f"implementation anchor is missing {field_name}", field_name)
    if result.get("event_type") not in IMPLEMENTATION_EVENTS:
        raise OutcomeInputError("INVALID_IMPLEMENTATION_EVENT", "unsupported implementation event type", "event_type")
    for field_name in ("implementation_event_id", "candidate_id", "review_id", "bridge_id", "action", "deployment_ref", "change_ref"):
        if not isinstance(result.get(field_name), str) or not _SAFE_REF.fullmatch(result[field_name]):
            raise OutcomeInputError("INVALID_IMPLEMENTATION_REFERENCE", f"{field_name} must be an opaque reference", field_name)
    for field_name in ("revision", "candidate_revision", "review_revision", "bridge_revision"):
        if not isinstance(result.get(field_name), int) or isinstance(result[field_name], bool) or result[field_name] < 1:
            raise OutcomeInputError("INVALID_IMPLEMENTATION_REVISION", f"{field_name} must be positive", field_name)
    for field_name in ("candidate_hash", "review_hash", "bridge_hash"):
        if not isinstance(result.get(field_name), str) or not _HASH.fullmatch(result[field_name]):
            raise OutcomeInputError("INVALID_LINEAGE_HASH", f"{field_name} must be SHA-256", field_name)
    _parse_datetime(result["completed_at"], "completed_at")
    _parse_datetime(result["created_at"], "created_at")
    if result.get("production_mutation") not in (None, False):
        raise OutcomeInputError("PRODUCTION_BOUNDARY", "implementation anchor cannot mutate production", "production_mutation")
    result["production_mutation"] = False
    result["content_hash"] = content_hash(result)
    if value is not None and isinstance(value, Mapping) and value.get("content_hash") not in (None, result["content_hash"]):
        raise OutcomeInputError("HASH_MISMATCH", "implementation anchor content_hash mismatch", "content_hash")
    return result


def create_implementation_anchor(value: ImplementationAnchor | Mapping[str, Any], *, persist: bool = False, store: Optional["OutcomeStore"] = None) -> dict[str, Any]:
    result = _anchor_payload(value)
    if persist and store is not None:
        return store.append_implementation(result)
    return result


def validate_implementation_anchor(value: Any) -> ValidationResult:
    try:
        result = _anchor_payload(value)
        schema_errors = _schema_errors("implementation_event.v1.proposal.json", result)
        return ValidationResult(errors=schema_errors)
    except OutcomeInputError as exc:
        return ValidationResult(errors=[ValidationError(exc.code, exc.field, str(exc))])


def _schema_errors(name: str, payload: Mapping[str, Any]) -> list[ValidationError]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        root = Path(__file__).resolve().parents[2]
        schema = json.loads((root / "contracts" / name).read_text(encoding="utf-8"))
        return [ValidationError("SCHEMA_VIOLATION", ".".join(map(str, item.absolute_path)) or "$", "proposal violates schema", rule=str(item.validator)) for item in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload)]
    except Exception as exc:
        return [ValidationError("SCHEMA_VALIDATION_ERROR", "$", str(exc))]


def _obs_values(values: Any, field_name: str) -> list[MetricObservation]:
    if isinstance(values, Mapping):
        values = list(values.values())
    if not isinstance(values, (list, tuple)):
        raise OutcomeInputError("INVALID_OBSERVATIONS", f"{field_name} must be a list", field_name)
    return [MetricObservation.from_mapping(item, f"{field_name}[{index}]") for index, item in enumerate(values)]


def _metric_for(observations: Sequence[MetricObservation], metric: str) -> Optional[MetricObservation]:
    matches = [item for item in observations if item.metric == metric]
    return matches[0] if matches else None


def _same_scope(before: MetricObservation, after: MetricObservation, plan: MeasurementPlan) -> tuple[bool, Optional[str]]:
    fields = (("source", before.source, after.source), ("scope", before.scope, after.scope), ("entity_ref", before.entity_ref, after.entity_ref), ("source_population", before.source_population, after.source_population), ("methodology", before.methodology, after.methodology), ("timezone", before.timezone, after.timezone))
    for field_name, old, new in fields:
        if old != new:
            return False, f"SCOPE_MISMATCH:{field_name}"
    if before.source in {"GEO", "WORKDUO"} and (before.sample_version != after.sample_version or before.sample_revision != after.sample_revision):
        return False, "GEO_SAMPLE_REVISION_MISMATCH"
    if before.source in {"GEO", "WORKDUO"} and (not before.sample_version or not after.sample_version or before.sample_revision is None or after.sample_revision is None):
        return False, "GEO_SAMPLE_REVISION_MISSING"
    if plan.scope and before.scope != plan.scope:
        return False, "MEASUREMENT_SCOPE_MISMATCH"
    if plan.source_population and before.source_population != plan.source_population:
        return False, "SOURCE_POPULATION_MISMATCH"
    if before.source == "SERP" and before.period_end != after.period_end:
        # SERP observations are timestamped snapshots, not period metrics.
        return False, "SERP_SNAPSHOT_NOT_PERIOD_COMPARABLE"
    return True, None


def _delta(before: float, after: float, method: str) -> Optional[float]:
    if method == "ABSOLUTE_DELTA":
        return after - before
    if before == 0:
        return None
    return (after - before) / abs(before)


def _target_met(delta: Optional[float], plan: MeasurementPlan) -> Optional[bool]:
    if delta is None:
        return None
    if plan.direction == "INCREASE":
        return delta >= plan.target_delta
    if plan.direction == "DECREASE":
        return delta <= -abs(plan.target_delta)
    return abs(delta) <= plan.tolerance


def _guardrail_breached(delta: Optional[float], guardrail: Mapping[str, Any]) -> bool:
    if delta is None:
        return True
    direction = str(guardrail.get("direction", "MAX_INCREASE")).upper()
    threshold = guardrail.get("max_delta", guardrail.get("tolerance", guardrail.get("target_delta", 0)))
    try:
        threshold = float(threshold)
    except (TypeError, ValueError):
        return True
    if direction in {"MAX_INCREASE", "NOT_DECREASE"}:
        return delta > threshold if direction == "MAX_INCREASE" else delta < -abs(threshold)
    if direction in {"MAX_DECREASE", "NOT_INCREASE"}:
        return delta < -abs(threshold) if direction == "MAX_DECREASE" else delta > abs(threshold)
    return abs(delta) > threshold


def _neutral_text(state: str, checkpoint: str) -> str:
    return f"Observed {state} at {checkpoint}; this is an evidence comparison and does not establish causation."


@dataclass
class OutcomeEvaluationResult:
    outcome: Optional[dict[str, Any]]
    validation: ValidationResult
    persisted: bool = False
    persistence_error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.validation.is_valid and self.outcome is not None

    @property
    def record(self) -> Optional[dict[str, Any]]:
        return self.outcome

    def as_dict(self) -> dict[str, Any]:
        return {"outcome": copy.deepcopy(self.outcome), "validation": self.validation.as_dict(), "persisted": self.persisted, "persistence_error": self.persistence_error}


@dataclass(frozen=True)
class OutcomeTrackingInput:
    """Typed wrapper for callers that prefer the WP11 input contract."""

    candidate: Mapping[str, Any]
    review: Mapping[str, Any]
    bridge: Mapping[str, Any]
    implementation_anchor: Mapping[str, Any]
    measurement_plan: Mapping[str, Any]
    baseline_observations: tuple[Mapping[str, Any], ...]
    follow_up_observations: tuple[Mapping[str, Any], ...]
    baseline_window: Optional[Mapping[str, Any]] = None
    follow_up_window: Optional[Mapping[str, Any]] = None
    checkpoint: str = "30D"
    evaluated_at: Optional[str] = None
    revision: int = 1

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "OutcomeTrackingInput":
        return cls(candidate=value.get("candidate", {}), review=value.get("review", {}), bridge=value.get("bridge", {}), implementation_anchor=value.get("implementation_anchor", value.get("implementation_event", {})), measurement_plan=value.get("measurement_plan", {}), baseline_observations=tuple(value.get("baseline_observations", value.get("baseline", ())) or ()), follow_up_observations=tuple(value.get("follow_up_observations", value.get("after", value.get("followup", ()))) or ()), baseline_window=value.get("baseline_window"), follow_up_window=value.get("follow_up_window", value.get("after_window")), checkpoint=str(value.get("checkpoint", "30D")), evaluated_at=value.get("evaluated_at"), revision=int(value.get("revision", 1)))

    def as_mapping(self) -> dict[str, Any]:
        return {"candidate": self.candidate, "review": self.review, "bridge": self.bridge, "implementation_anchor": self.implementation_anchor, "measurement_plan": self.measurement_plan, "baseline_observations": list(self.baseline_observations), "follow_up_observations": list(self.follow_up_observations), "baseline_window": self.baseline_window, "follow_up_window": self.follow_up_window, "checkpoint": self.checkpoint, "evaluated_at": self.evaluated_at, "revision": self.revision}


def _error(code: str, field: str, message: str) -> OutcomeEvaluationResult:
    return OutcomeEvaluationResult(None, ValidationResult(errors=[ValidationError(code, field, message)]))


def evaluate_outcome(value: Mapping[str, Any] | Any, *, checkpoint: Optional[str] = None, outcome_store: Optional["OutcomeStore"] = None, persist: bool = False, evaluated_at: Optional[str] = None) -> OutcomeEvaluationResult:
    """Evaluate one checkpoint without querying a source or mutating upstream records."""
    try:
        if isinstance(value, OutcomeTrackingInput):
            value = value.as_mapping()
        if not isinstance(value, Mapping):
            raise OutcomeInputError("INVALID_INPUT", "outcome input must be a mapping")
        candidate = _candidate_payload(value.get("candidate", value))
        review = _unwrap(value.get("review"), "review") or (copy.deepcopy(dict(value["review"])) if isinstance(value.get("review"), Mapping) else None)
        bridge = _unwrap(value.get("bridge"), "bridge") or (copy.deepcopy(dict(value["bridge"])) if isinstance(value.get("bridge"), Mapping) else None)
        if review is None or bridge is None:
            return _error("IMPLEMENTATION_ANCHOR_REQUIRED", "implementation_anchor", "a reviewed bridge and implementation anchor are required before formal outcome evaluation")
        anchor_raw = value.get("implementation_anchor", value.get("implementation_event"))
        if anchor_raw is None:
            return _error("IMPLEMENTATION_ANCHOR_REQUIRED", "implementation_anchor", "APPROVE alone does not mean IMPLEMENTED")
        anchor = _anchor_payload(anchor_raw)
        if anchor["event_type"] != "IMPLEMENTED":
            status = "OBSERVATION_ONLY" if anchor["event_type"] == "MONITORING_ONLY" else "NOT_ELIGIBLE"
            return OutcomeEvaluationResult({"record_type": RECORD_TYPE, "contract_version": CONTRACT_VERSION, "tracking_status": status, "outcome_state": "INSUFFICIENT_DATA", "formal_evaluation": False, "implementation_event_id": anchor["implementation_event_id"], "candidate_id": candidate["candidate_id"], "candidate_revision": candidate["revision"], "candidate_hash": candidate["content_hash"], "reason": "action is not an implemented action; no formal outcome is asserted", "production_mutation": False}, ValidationResult(warnings=[ValidationError("FORMAL_OUTCOME_BLOCKED", "implementation_anchor.event_type", "outcome tracking remains observation-only", severity="WARNING")]))
        if anchor["candidate_id"] != candidate["candidate_id"] or anchor["candidate_revision"] != candidate["revision"] or anchor["candidate_hash"] != candidate["content_hash"]:
            return _error("CANDIDATE_REVISION_MISMATCH", "implementation_anchor", "implementation anchor must bind the exact Candidate revision and hash")
        if str(review.get("decision")) != "APPROVE" or review.get("candidate_id") != candidate["candidate_id"] or review.get("candidate_revision") != candidate["revision"] or review.get("candidate_hash") != candidate["content_hash"] or anchor["review_id"] != review.get("review_id") or anchor["review_revision"] != review.get("revision") or anchor["review_hash"] != review.get("content_hash"):
            return _error("REVIEW_REVISION_MISMATCH", "review", "outcome tracking requires exact human approval for this Candidate revision")
        if bridge.get("review_id") != review.get("review_id") or bridge.get("review_revision") != review.get("revision") or bridge.get("candidate_hash") != candidate["content_hash"] or anchor["bridge_id"] != bridge.get("bridge_id") or anchor["bridge_revision"] != bridge.get("revision") or anchor["bridge_hash"] != bridge.get("content_hash"):
            return _error("BRIDGE_REVISION_MISMATCH", "bridge", "implementation anchor must retain the exact Bridge lineage")
        plan = MeasurementPlan.from_mapping(value.get("measurement_plan", bridge.get("measurement_plan", {})))
        checkpoint_value = str(checkpoint or value.get("checkpoint", "30D")).upper()
        if checkpoint_value not in CHECKPOINTS:
            raise OutcomeInputError("INVALID_CHECKPOINT", "checkpoint must be 30D, 60D or 90D", "checkpoint")
        completed_at = anchor["completed_at"]
        baseline_expected = expected_window(completed_at, "BASELINE")
        follow_expected = expected_window(completed_at, checkpoint_value)
        baseline = _obs_values(value.get("baseline_observations", value.get("baseline", ())), "baseline_observations")
        follow = _obs_values(value.get("follow_up_observations", value.get("after", value.get("followup", ()))), "follow_up_observations")
        evidence_records = value.get("evidence_records") or value.get("evidence")
        if isinstance(evidence_records, Mapping):
            evidence_records = list(evidence_records.values())
        if evidence_records:
            exact: dict[tuple[str, int], str] = {}
            for evidence in evidence_records:
                if isinstance(evidence, Mapping) and evidence.get("evidence_id") is not None and evidence.get("revision") is not None:
                    exact[(str(evidence["evidence_id"]), int(evidence["revision"]))] = str(evidence.get("content_hash", ""))
            for observation in [*baseline, *follow]:
                pin_key = (observation.evidence_ref["evidence_id"], observation.evidence_ref["revision"])
                if pin_key in exact and exact[pin_key] != observation.evidence_ref["content_hash"]:
                    return _error("BASELINE_EVIDENCE_HASH_MISMATCH", "evidence_ref", "observation pin does not resolve to the supplied immutable evidence revision")
        baseline_window = dict(value.get("baseline_window") or baseline_expected)
        follow_window = dict(value.get("follow_up_window") or value.get("after_window") or follow_expected)
        for name, actual, expected in (("baseline_window", baseline_window, baseline_expected), ("follow_up_window", follow_window, follow_expected)):
            if actual.get("period_start") != expected["period_start"] or actual.get("period_end") != expected["period_end"] or actual.get("timezone", REPORTING_TIMEZONE) != REPORTING_TIMEZONE:
                return _error("INCOMPLETE_PERIOD", name, "window must be the exact 28 complete days defined by OUTCOME_TRACKING.md")
        metrics = [plan.primary_metric, *plan.support_metrics, *[str(item.get("metric")) for item in plan.guardrails if isinstance(item, Mapping) and item.get("metric")]]
        metrics = list(dict.fromkeys(metrics))
        comparisons: list[dict[str, Any]] = []
        evidence_refs: list[dict[str, Any]] = []
        conflicts: list[str] = []
        missing: list[str] = []
        target_results: dict[str, Optional[bool]] = {}
        guardrail_breach = False
        for metric in metrics:
            before, after = _metric_for(baseline, metric), _metric_for(follow, metric)
            if before is None or after is None:
                missing.append(metric)
                comparisons.append({"metric": metric, "status": "MISSING", "delta": None, "target_met": None})
                continue
            evidence_refs.extend([dict(before.evidence_ref), dict(after.evidence_ref)])
            if before.source == "BUSINESS" and not plan.attribution_contract_ref:
                conflicts.append("BUSINESS_ATTRIBUTION_CONTRACT_REQUIRED")
                comparisons.append({"metric": metric, "source": before.source, "status": "NOT_COMPARABLE", "delta": None, "target_met": None, "reason": "business outcome requires a separately approved attribution contract"})
                continue
            if before.source == "GA4" and any(token in before.metric.lower() for token in ("conversion", "lead", "sql", "revenue")):
                conflicts.append("GA4_DIAGNOSTIC_ONLY")
                comparisons.append({"metric": metric, "source": before.source, "status": "NOT_COMPARABLE", "delta": None, "target_met": None, "reason": "GA4 is behavior diagnostic evidence, not a formal conversion"})
                continue
            if before.status in {"MISSING", "FAILED", "NOT_AVAILABLE", "STALE", "NOT_COMPARABLE"} or after.status in {"MISSING", "FAILED", "NOT_AVAILABLE", "STALE", "NOT_COMPARABLE"} or before.freshness_state in {"STALE", "FAILED", "NOT_AVAILABLE", "MISSING"} or after.freshness_state in {"STALE", "FAILED", "NOT_AVAILABLE", "MISSING"} or before.value is None or after.value is None:
                missing.append(metric)
                comparisons.append({"metric": metric, "source": before.source, "status": "INSUFFICIENT_DATA", "delta": None, "target_met": None})
                continue
            if before.sample_size is not None and before.sample_size < plan.minimum_sample or after.sample_size is not None and after.sample_size < plan.minimum_sample:
                missing.append(metric)
                comparisons.append({"metric": metric, "source": before.source, "status": "INSUFFICIENT_SAMPLE", "delta": None, "target_met": None})
                continue
            comparable, reason = _same_scope(before, after, plan)
            if not comparable:
                conflicts.append(reason or "NOT_COMPARABLE")
                comparisons.append({"metric": metric, "source": before.source, "status": "NOT_COMPARABLE", "delta": None, "target_met": None, "reason": reason})
                continue
            delta = _delta(float(before.value), float(after.value), plan.comparison_method)
            target = _target_met(delta, plan)
            target_results[metric] = target
            comparisons.append({"metric": metric, "source": before.source, "status": "COMPLETE" if delta is not None else "NOT_COMPARABLE", "baseline": before.value, "follow_up": after.value, "delta": delta, "target_met": target})
            guardrail = next((item for item in plan.guardrails if isinstance(item, Mapping) and item.get("metric") == metric), None)
            if guardrail is not None and _guardrail_breached(delta, guardrail):
                guardrail_breach = True
                conflicts.append(f"GUARDRAIL_BREACH:{metric}")
        support_values = [target_results.get(metric) for metric in plan.support_metrics]
        primary_met = target_results.get(plan.primary_metric)
        blocking_conflicts = [item for item in conflicts if not item.startswith("GUARDRAIL_BREACH:")]
        primary_comparison = next((item for item in comparisons if item.get("metric") == plan.primary_metric), {})
        primary_delta = primary_comparison.get("delta")
        all_within_tolerance = bool(primary_delta is not None and abs(primary_delta) <= plan.tolerance and all((next((item.get("delta") for item in comparisons if item.get("metric") == metric), None) is not None and abs(float(next(item.get("delta") for item in comparisons if item.get("metric") == metric))) <= plan.tolerance) for metric in plan.support_metrics))
        if missing or blocking_conflicts or primary_met is None or not plan.support_metrics or any(item is None for item in support_values):
            state = "INSUFFICIENT_DATA"
            tracking_status = "EVALUATED"
        elif guardrail_breach:
            state = "LOST"
            tracking_status = "EVALUATED"
        elif all_within_tolerance:
            state = "NO_CHANGE"
            tracking_status = "EVALUATED"
        elif primary_met is False and plan.direction != "STABLE":
            state = "LOST"
            tracking_status = "EVALUATED"
        elif primary_met is True and all(item is True for item in support_values) and not conflicts:
            state = "WON"
            tracking_status = "EVALUATED"
        elif primary_met is True or any(item is True for item in support_values):
            state = "PARTIAL_WIN"
            tracking_status = "EVALUATED"
        else:
            state = "NO_CHANGE"
            tracking_status = "EVALUATED"
        if len(set(item.source for item in baseline if item.metric in metrics)) < 1:
            conflicts.append("NO_SOURCE_EVIDENCE")
        event_date = evaluated_at or (follow_expected["period_end"] + "T23:59:59+08:00")
        _parse_datetime(event_date, "evaluated_at")
        track_id = str(value.get("outcome_track_id") or "OUT_" + _sha({"candidate_id": candidate["candidate_id"], "checkpoint": checkpoint_value, "implementation_event_id": anchor["implementation_event_id"]})[:24])
        revision = value.get("revision", 1)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise OutcomeInputError("INVALID_OUTCOME_REVISION", "revision must be positive", "revision")
        record: dict[str, Any] = {
            "record_type": RECORD_TYPE, "contract_version": CONTRACT_VERSION, "outcome_track_id": track_id, "revision": revision, "supersedes_outcome_revision": revision - 1 if revision > 1 else None,
            "candidate_id": candidate["candidate_id"], "candidate_revision": candidate["revision"], "candidate_hash": candidate["content_hash"], "review_id": review["review_id"], "review_revision": review["revision"], "review_hash": review["content_hash"], "bridge_id": bridge["bridge_id"], "bridge_revision": bridge["revision"], "bridge_hash": bridge["content_hash"], "implementation_event_id": anchor["implementation_event_id"], "implementation_revision": anchor["revision"], "implementation_hash": anchor["content_hash"],
            "action": anchor["action"], "target_url": anchor.get("target_url"), "completed_at": anchor["completed_at"], "checkpoint": checkpoint_value, "checkpoint_due_date": follow_expected["period_end"], "tracking_status": tracking_status, "formal_evaluation": True, "outcome_state": state,
            "measurement_plan": plan.as_dict(), "baseline_window": baseline_window, "follow_up_window": follow_window, "baseline_observations": [item.as_dict() for item in baseline], "follow_up_observations": [item.as_dict() for item in follow], "comparisons": comparisons, "evidence_refs": _dedupe_refs(evidence_refs), "missing_metrics": sorted(set(missing)), "conflicts": sorted(set(conflicts)), "limitations": list(plan.attribution_limitations) + ["Observed comparison only; no causal or ROI claim."], "primary_metric": plan.primary_metric, "support_metrics": list(plan.support_metrics), "candidate_score": copy.deepcopy(candidate.get("score", candidate.get("opportunity_score"))), "candidate_confidence": candidate.get("confidence"), "human_review_decision": review.get("decision"), "bridge_status": bridge.get("status"), "causal_claim": False, "production_mutation": False, "policy_version": RULE_VERSION, "evaluated_at": event_date, "created_at": event_date,
        }
        record["observed_outcome_text"] = _neutral_text(state, checkpoint_value)
        record["content_hash"] = content_hash(record)
        validation = validate_outcome_record(record)
        if not validation.is_valid:
            return OutcomeEvaluationResult(None, validation)
        if persist and outcome_store is not None:
            try:
                stored = outcome_store.append_outcome(record)
                return OutcomeEvaluationResult(stored, validation, persisted=True)
            except Exception as exc:
                return OutcomeEvaluationResult(record, validation, persisted=False, persistence_error=str(exc))
        return OutcomeEvaluationResult(record, validation)
    except OutcomeInputError as exc:
        return _error(exc.code, exc.field, str(exc))
    except Exception as exc:
        return _error("INVALID_OUTCOME_INPUT", "record", str(exc))


def _dedupe_refs(values: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: dict[tuple[str, int], dict[str, Any]] = {}
    for item in values:
        key = (item["evidence_id"], item["revision"])
        output[key] = dict(item)
    return [output[key] for key in sorted(output)]


def validate_outcome_record(value: Any) -> ValidationResult:
    if not isinstance(value, Mapping):
        return ValidationResult(errors=[ValidationError("SCHEMA_VIOLATION", "$", "outcome must be a mapping")])
    errors = _schema_errors("outcome_tracking.v1.proposal.json", value)
    if value.get("outcome_state") not in OUTCOME_STATES:
        errors.append(ValidationError("INVALID_OUTCOME_STATE", "outcome_state", "outcome state must use the five approved states"))
    if value.get("causal_claim") is not False:
        errors.append(ValidationError("CAUSAL_CLAIM_FORBIDDEN", "causal_claim", "outcome tracking is observational"))
    if value.get("production_mutation") is not False:
        errors.append(ValidationError("PRODUCTION_BOUNDARY", "production_mutation", "outcome tracking cannot mutate production"))
    try:
        if value.get("content_hash") != content_hash(value):
            errors.append(ValidationError("CONTENT_HASH_MISMATCH", "content_hash", "outcome content hash mismatch"))
    except Exception as exc:
        errors.append(ValidationError("CONTENT_HASH_ERROR", "content_hash", str(exc)))
    return ValidationResult(errors=errors)


class OutcomeStore:
    """Local append-only store for implementation anchors and outcomes."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.outcomes_path = self.root / "outcomes.jsonl"
        self.implementations_path = self.root / "implementation_events.jsonl"
        self._outcomes: dict[tuple[str, int], dict[str, Any]] = {}
        self._implementations: dict[tuple[str, int], dict[str, Any]] = {}
        self._load(self.outcomes_path, self._outcomes, validate_outcome_record)
        self._load(self.implementations_path, self._implementations, validate_implementation_anchor)

    def _load(self, path: Path, target: dict[tuple[str, int], dict[str, Any]], validator: Any) -> None:
        if not path.exists():
            return
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ImmutableStoreError("STORE_CORRUPTION", f"invalid JSON at line {line_number}") from exc
            result = validator(record)
            if not result.is_valid:
                raise ImmutableStoreError("STORE_CORRUPTION", result.errors[0].message)
            ident = record.get("outcome_track_id", record.get("implementation_event_id"))
            key = (ident, record.get("revision", 0))
            if key in target:
                raise ImmutableStoreError("STORE_CORRUPTION", "duplicate immutable revision")
            target[key] = copy.deepcopy(record)

    def _append(self, path: Path, target: dict[tuple[str, int], dict[str, Any]], record: Mapping[str, Any], validator: Any, ident_field: str) -> dict[str, Any]:
        prepared = copy.deepcopy(dict(record))
        if ident_field == "outcome_track_id":
            calculated = content_hash(prepared)
            if prepared.get("content_hash") not in (None, calculated):
                raise ImmutableStoreError("HASH_MISMATCH", "outcome content_hash does not match semantic fields")
            prepared["content_hash"] = calculated
        else:
            prepared = _anchor_payload(prepared)
        result = validator(prepared)
        if not result.is_valid:
            raise ImmutableStoreError("INVALID_RECORD", result.errors[0].message)
        key = (prepared[ident_field], prepared["revision"])
        existing = target.get(key)
        if existing is not None:
            if existing["content_hash"] == prepared["content_hash"]:
                return {**copy.deepcopy(existing), "idempotent": True}
            raise ImmutableStoreError("REVISION_CONFLICT", "same logical revision has a different content hash")
        history = sorted(rev for ident, rev in target if ident == prepared[ident_field])
        expected = history[-1] + 1 if history else 1
        if prepared["revision"] != expected:
            raise ImmutableStoreError("REVISION_GAP", "revision must append exactly after the current tip")
        if ident_field == "outcome_track_id" and history:
            previous = target[(prepared[ident_field], history[-1])]
            for field_name in ("candidate_id", "candidate_revision", "candidate_hash", "implementation_event_id", "implementation_revision", "implementation_hash"):
                if previous.get(field_name) != prepared.get(field_name):
                    raise ImmutableStoreError("LINEAGE_DRIFT", "outcome history cannot inherit a different Candidate or implementation event")
        if prepared["revision"] > 1:
            supersedes = prepared.get("supersedes_outcome_revision", prepared.get("supersedes_implementation_revision", prepared.get("supersedes_revision")))
            if supersedes != prepared["revision"] - 1:
                raise ImmutableStoreError("INVALID_SUPERSEDES", "revision must supersede the immediately prior revision")
        with path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(canonical_line(prepared))
            handle.flush()
            os.fsync(handle.fileno())
        target[key] = copy.deepcopy(prepared)
        return copy.deepcopy(prepared)

    def append_implementation(self, record: Mapping[str, Any]) -> dict[str, Any]:
        return self._append(self.implementations_path, self._implementations, record, validate_implementation_anchor, "implementation_event_id")

    def append_outcome(self, record: Mapping[str, Any]) -> dict[str, Any]:
        return self._append(self.outcomes_path, self._outcomes, record, validate_outcome_record, "outcome_track_id")

    append = append_outcome
    append_record = append_outcome

    def get_outcome(self, outcome_track_id: str, revision: Optional[int] = None) -> Optional[dict[str, Any]]:
        revisions = [rev for ident, rev in self._outcomes if ident == outcome_track_id]
        if revision is None:
            revision = max(revisions) if revisions else None
        if revision is None:
            return None
        value = self._outcomes.get((outcome_track_id, revision))
        return copy.deepcopy(value) if value is not None else None

    def history(self, outcome_track_id: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._outcomes[key]) for key in sorted(self._outcomes) if key[0] == outcome_track_id]

    def list(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._outcomes[key]) for key in sorted(self._outcomes)]

    def get_implementation(self, implementation_event_id: str, revision: Optional[int] = None) -> Optional[dict[str, Any]]:
        revisions = [rev for ident, rev in self._implementations if ident == implementation_event_id]
        if revision is None:
            revision = max(revisions) if revisions else None
        if revision is None:
            return None
        value = self._implementations.get((implementation_event_id, revision))
        return copy.deepcopy(value) if value is not None else None


def evaluate_outcomes(value: Mapping[str, Any], *, outcome_store: Optional[OutcomeStore] = None, persist: bool = False, evaluated_at: Optional[str] = None) -> dict[str, OutcomeEvaluationResult]:
    """Evaluate all requested checkpoints in deterministic 30/60/90 order."""
    if isinstance(value, OutcomeTrackingInput):
        value = value.as_mapping()
    return {checkpoint: evaluate_outcome(value, checkpoint=checkpoint, outcome_store=outcome_store, persist=persist, evaluated_at=evaluated_at) for checkpoint in ("30D", "60D", "90D") if checkpoint in value.get("checkpoints", ("30D", "60D", "90D"))}


# Naming aliases keep the proposal boundary discoverable alongside WP4–WP10 APIs.
OutcomeTrackingResult = OutcomeEvaluationResult
OutcomeTrackingStore = OutcomeStore
ImplementationEvent = ImplementationAnchor
validate_outcome = validate_outcome_record


__all__ = [
    "ACTION_STATUSES", "CHECKPOINTS", "CONTRACT_VERSION", "FRESHNESS_STATES", "IMPLEMENTATION_CONTRACT_VERSION", "IMPLEMENTATION_EVENTS", "ImplementationAnchor", "ImplementationEvent", "MeasurementPlan", "MetricObservation", "OutcomeEvaluationResult", "OutcomeInputError", "OutcomeStore", "OutcomeTrackingInput", "OutcomeTrackingResult", "OutcomeTrackingStore", "OUTCOME_STATES", "RECORD_TYPE", "REPORTING_TIMEZONE", "create_implementation_anchor", "evaluate_outcome", "evaluate_outcomes", "expected_window", "validate_implementation_anchor", "validate_outcome", "validate_outcome_record",
]
