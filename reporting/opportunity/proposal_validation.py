"""Deterministic, offline validation for the opportunity proposal contracts.

The validator is deliberately a pure boundary: it reads checked-in schemas and
accepts JSON-like mappings plus optional immutable evidence/review context.  It
never imports a source adapter, opens a network connection, or writes a
production artifact.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence
from urllib.parse import parse_qsl, urlsplit

try:
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover - runtime guidance, not a branch to skip
    raise RuntimeError(
        "WP1 validation requires the bundled Python runtime with jsonschema"
    ) from exc


ROOT = Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"

_AHREFS_SCHEMA = "ahrefs_scope.v1.proposal.json"
_OPPORTUNITY_SCHEMA = "opportunity_contract.v1.proposal.json"

_SOURCE_FIELDS = {
    "business_evidence_ref": ("BUSINESS", "BUSINESS_ACTUAL"),
    "ahrefs_evidence_ref": ("AHREFS", "THIRD_PARTY_ESTIMATE"),
    "gsc_evidence_ref": ("GSC", "FIRST_PARTY_SEARCH_ACTUAL"),
    "ga4_evidence_ref": ("GA4", "FIRST_PARTY_BEHAVIOR_DIAGNOSTIC"),
    "sf_evidence_ref": ("SF", "TECHNICAL_CRAWL_EVIDENCE"),
    "serp_evidence_ref": ("SERP", "LIVE_SERP_SNAPSHOT"),
    "geo_evidence_ref": ("WORKDUO", "MONITORED_GEO_SAMPLE"),
    "crux_evidence_ref": ("CRUX", "FIELD_UX_EVIDENCE"),
}

_SCORE_DIMENSIONS = (
    "demand_score",
    "traction_score",
    "business_score",
    "attainability_score",
    "geo_score",
    "execution_score",
)

_SCORE_ROLE = {
    "demand_score": "demand",
    "traction_score": "traction",
    "business_score": "business_relevance",
    "attainability_score": "attainability",
    "geo_score": "geo",
    "execution_score": "effort",
}

_PROFILE_WEIGHTS = {
    "SEO_EXISTING": {
        "demand_score": 20,
        "traction_score": 15,
        "business_score": 30,
        "attainability_score": 20,
        "geo_score": 0,
        "execution_score": 15,
    },
    "SEO_NEW": {
        "demand_score": 25,
        "traction_score": 0,
        "business_score": 30,
        "attainability_score": 25,
        "geo_score": 0,
        "execution_score": 20,
    },
    "GEO": {
        "demand_score": 10,
        "traction_score": 5,
        "business_score": 30,
        "attainability_score": 15,
        "geo_score": 30,
        "execution_score": 10,
    },
}

_ACTION_PROFILE = {
    "CREATE_NEW": "SEO_NEW",
    "GEO_ENHANCE": "GEO",
}

_FRESHNESS_MAX_DAYS = {
    "AHREFS": 30,
    "GSC": 7,
    "GA4": 7,
    "SF": 14,
    "SERP": 7,
    "WORKDUO": 7,
    "CRUX": 14,
    "BUSINESS": 35,
}

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PERIOD_RE = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")
_SAFE_REF_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_SECRET_REF_RE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|bearer)"
)
_PII_QUERY_RE = re.compile(r"(?i)(?:email|e-mail|phone|tel|mobile|name|customer|lead)")


@dataclass(frozen=True)
class ValidationError:
    """Stable machine-readable validation error without raw input echoing."""

    code: str
    field: str
    message: str
    severity: str = "ERROR"
    rule: Optional[str] = None
    expected: Any = None
    actual: Any = None

    def as_dict(self) -> dict[str, Any]:
        value = {
            "code": self.code,
            "field": self.field,
            "message": self.message,
            "severity": self.severity,
        }
        if self.rule is not None:
            value["rule"] = self.rule
        if self.expected is not None:
            value["expected"] = self.expected
        if self.actual is not None:
            value["actual"] = self.actual
        return value


@dataclass
class ValidationResult:
    """Validation outcome returned by both public validators."""

    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    @property
    def valid(self) -> bool:
        """Alias kept small and convenient for later callers."""

        return self.is_valid

    def as_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [error.as_dict() for error in self.errors],
            "warnings": [warning.as_dict() for warning in self.warnings],
        }

    def __bool__(self) -> bool:
        return self.is_valid


def _error(
    errors: list[ValidationError],
    code: str,
    field_name: str,
    message: str,
    *,
    rule: Optional[str] = None,
    expected: Any = None,
    actual: Any = None,
) -> None:
    errors.append(
        ValidationError(
            code=code,
            field=field_name,
            message=message,
            rule=rule,
            expected=expected,
            actual=actual,
        )
    )


def _warning(
    warnings: list[ValidationError],
    code: str,
    field_name: str,
    message: str,
    *,
    rule: Optional[str] = None,
) -> None:
    warnings.append(
        ValidationError(
            code=code,
            field=field_name,
            message=message,
            severity="WARNING",
            rule=rule,
        )
    )


@lru_cache(maxsize=None)
def _schema(name: str) -> dict[str, Any]:
    schema = json.loads((CONTRACTS / name).read_text())
    Draft202012Validator.check_schema(schema)
    return schema


def _field_path(path: Iterable[Any]) -> str:
    parts = [str(part) for part in path]
    return ".".join(parts) if parts else "$"


def _structural_errors(payload: Any, schema_name: str) -> list[ValidationError]:
    validator = Draft202012Validator(_schema(schema_name))
    output: list[ValidationError] = []
    for error in sorted(validator.iter_errors(payload), key=lambda item: tuple(map(str, item.absolute_path))):
        field_name = _field_path(error.absolute_path)
        _error(
            output,
            "SCHEMA_VIOLATION",
            field_name,
            "Payload violates the proposal schema.",
            rule=str(error.validator),
        )
    return output


def _valid_date(value: Any) -> bool:
    return isinstance(value, str) and bool(_DATE_RE.fullmatch(value)) and _safe_date(value) is not None


def _safe_date(value: str) -> Optional[date]:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _safe_datetime(value: str) -> Optional[datetime]:
    if not isinstance(value, str) or "T" not in value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _format_errors(payload: Any, schema: Mapping[str, Any]) -> list[ValidationError]:
    errors: list[ValidationError] = []

    def walk(value: Any, node: Mapping[str, Any], path: tuple[Any, ...] = ()) -> None:
        fmt = node.get("format")
        field_name = _field_path(path)
        if fmt == "date" and value is not None and not _valid_date(value):
            _error(errors, "INVALID_DATE", field_name, "Expected a real ISO calendar date.", rule="format=date")
        elif fmt == "date-time" and value is not None and _safe_datetime(value) is None:
            _error(
                errors,
                "INVALID_DATETIME",
                field_name,
                "Expected a timezone-aware ISO date-time.",
                rule="format=date-time",
            )
        if isinstance(value, Mapping):
            properties = node.get("properties", {})
            for key, child in properties.items():
                if key in value:
                    walk(value[key], child, path + (key,))
            for child in node.get("allOf", []):
                walk(value, child, path)
        elif isinstance(value, list) and isinstance(node.get("items"), Mapping):
            for index, item in enumerate(value):
                walk(item, node["items"], path + (index,))

    if isinstance(payload, Mapping):
        walk(payload, schema)
    return errors


def _parse_decision_at(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)
    return _safe_datetime(value)


def _context_records(value: Any, id_fields: Sequence[str]) -> dict[str, dict[str, Any]]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        if all(isinstance(item, Mapping) for item in value.values()):
            result = {}
            for key, item in value.items():
                record = dict(item)
                record.setdefault(id_fields[0], str(key))
                result[str(key)] = record
            return result
        if any(field_name in value for field_name in id_fields):
            value = [value]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        result = {}
        for item in value:
            if not isinstance(item, Mapping):
                continue
            identifier = next((item.get(name) for name in id_fields if item.get(name)), None)
            if identifier is not None:
                result[str(identifier)] = dict(item)
        return result
    return {}


def _context(
    context: Optional[Mapping[str, Any]],
    *,
    evidence: Any = None,
    review_events: Any = None,
    scope_approvals: Any = None,
    business_overlays: Any = None,
    decision_at: Any = None,
) -> dict[str, Any]:
    base = dict(context or {})
    if evidence is not None:
        base["evidence"] = evidence
    if review_events is not None:
        base["review_events"] = review_events
    if scope_approvals is not None:
        base["scope_approvals"] = scope_approvals
    if business_overlays is not None:
        base["business_overlays"] = business_overlays
    if decision_at is not None:
        base["decision_at"] = decision_at
    base["evidence"] = _context_records(base.get("evidence"), ("evidence_id", "id", "ref"))
    base["review_events"] = _context_records(base.get("review_events"), ("review_event_id", "id", "ref"))
    base["scope_approvals"] = _context_records(base.get("scope_approvals"), ("approval_ref", "id", "ref"))
    base["business_overlays"] = _context_records(base.get("business_overlays"), ("override_ref", "id", "ref"))
    base["decision_at"] = _parse_decision_at(base.get("decision_at"))
    return base


def _host(value: Any) -> Optional[str]:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        return None
    if "://" in value or "/" in value or "@" in value:
        return None
    host = value.rstrip(".").lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]*[a-z0-9]", host):
        return None
    return host


def _url_is_safe(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.username or parsed.password or any(char.isspace() for char in value):
        return False
    if _SECRET_REF_RE.search(value):
        return False
    for key, query_value in parse_qsl(parsed.query, keep_blank_values=True):
        if _PII_QUERY_RE.search(key) or _PII_QUERY_RE.search(query_value):
            return False
    try:
        return bool(parsed.hostname)
    except ValueError:
        return False


def _url_errors(payload: Mapping[str, Any]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for field_name in ("existing_url", "target_url"):
        value = payload.get(field_name)
        if value is not None and not _url_is_safe(value):
            _error(errors, "INVALID_URL", field_name, "URL must be an https/http URL without credentials or PII-like query data.")
    for index, value in enumerate(payload.get("existing_urls", []) or []):
        if not _url_is_safe(value):
            _error(errors, "INVALID_URL", f"existing_urls.{index}", "URL must be an https/http URL without credentials or PII-like query data.")
    return errors


def _safe_ref(value: Any) -> bool:
    return isinstance(value, str) and bool(_SAFE_REF_RE.fullmatch(value)) and not _SECRET_REF_RE.search(value)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _canonical_value(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("non-finite number")
        if value.is_integer():
            return int(value)
    return value


def candidate_content_hash(payload: Mapping[str, Any]) -> str:
    excluded = {"content_hash", "created_at", "updated_at", "status", "review_state", "review_event_ref"}
    canonical = {key: value for key, value in payload.items() if key not in excluded}
    encoded = json.dumps(
        _canonical_value(canonical),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _scope_approved(context: Mapping[str, Any], ref: Any) -> bool:
    record = context.get("scope_approvals", {}).get(str(ref))
    if not record:
        return False
    return record.get("status") in {"APPROVED", "VALID"} and bool(record.get("authenticated", record.get("reviewer_id")))


def _business_approved(context: Mapping[str, Any], ref: Any) -> bool:
    record = context.get("business_overlays", {}).get(str(ref))
    if not record:
        return False
    return record.get("status") in {"APPROVED", "VALID"} and bool(record.get("authenticated", record.get("reviewer_id")))


def _validate_ahrefs(payload: Mapping[str, Any], context: Mapping[str, Any], errors: list[ValidationError]) -> None:
    if payload.get("source_class") != "THIRD_PARTY_ESTIMATE":
        _error(errors, "SOURCE_CLASS_CONFLICT", "source_class", "Ahrefs proposal must remain a third-party estimate.")
    if payload.get("estimation_flag") is not True:
        _error(errors, "ESTIMATE_CLASSIFICATION_CONFLICT", "estimation_flag", "Ahrefs estimates must set estimation_flag=true.")

    scopes = payload.get("scopes") or []
    for index, scope in enumerate(scopes):
        prefix = f"scopes.{index}"
        target = _host(scope.get("target"))
        allowed = {_host(item) for item in scope.get("allowed_hosts", [])}
        excluded = {_host(item) for item in scope.get("excluded_hosts", [])}
        if target is None:
            _error(errors, "INVALID_IDENTIFIER", f"{prefix}.target", "Scope target must be a host identifier.")
            continue
        if target in excluded:
            _error(errors, "SCOPE_TARGET_NOT_ALLOWED", f"{prefix}.target", "Scope target is explicitly excluded.")
        mode = scope.get("mode")
        matched = target in allowed
        if mode == "domain":
            matched = matched or any(target.endswith("." + host) for host in allowed if host)
        elif mode == "subdomains":
            matched = matched or any(target == host or target.endswith("." + host) for host in allowed if host)
        if not matched:
            _error(errors, "SCOPE_TARGET_NOT_ALLOWED", f"{prefix}.target", "Scope target must be covered by allowed_hosts.")
        if any(host is None for host in allowed | excluded):
            _error(errors, "INVALID_IDENTIFIER", prefix, "Scope host lists must contain host identifiers.")

    historical = payload.get("historical_semantics") or {}
    requested = _safe_date(historical.get("requested_date"))
    compared = historical.get("compared_date")
    compared_date = _safe_date(compared) if compared is not None else None
    if requested and compared_date and compared_date >= requested:
        _error(errors, "INVALID_DATE_ORDER", "historical_semantics.compared_date", "Compared date must precede requested date.")
    retrieved = _safe_datetime(payload.get("retrieved_at"))
    snapshot = _safe_date(payload.get("snapshot_date"))
    if retrieved and snapshot and snapshot > retrieved.astimezone(retrieved.tzinfo).date():
        _error(errors, "INVALID_DATE_ORDER", "snapshot_date", "Snapshot date cannot be after retrieved_at.")
    if retrieved and requested and requested > retrieved.astimezone(retrieved.tzinfo).date():
        _error(errors, "INVALID_DATE_ORDER", "historical_semantics.requested_date", "Requested date cannot be after retrieved_at.")

    decision_at = context.get("decision_at")
    if decision_at and retrieved and retrieved > decision_at:
        _error(errors, "FUTURE_TIMESTAMP", "retrieved_at", "Retrieved time cannot be after decision_at.")
    if decision_at and snapshot and (decision_at.date() - snapshot).days > 30:
        _error(errors, "STALE_EVIDENCE_POLICY_VIOLATION", "snapshot_date", "Snapshot exceeds the proposal freshness window.")

    if "capabilities" in context:
        capability_values = context.get("capabilities") or []
        if isinstance(capability_values, Mapping):
            capability_values = capability_values.keys()
        available = {str(value) for value in capability_values}
        for ref in payload.get("required_capability_refs", []) or []:
            if ref not in available:
                _error(errors, "CAPABILITY_MISSING", "required_capability_refs", "Required capability is not present in the supplied offline capability context.", expected=ref)

    if payload.get("approval_state") == "APPROVED":
        if not payload.get("approval_ref") or not _scope_approved(context, payload.get("approval_ref")):
            _error(errors, "APPROVAL_EVIDENCE_MISSING", "approval_ref", "Approved scope requires an authenticated local approval record.")
    for index, competitor in enumerate(payload.get("competitors") or []):
        if not _scope_approved(context, competitor.get("approval_ref")):
            _error(errors, "APPROVAL_EVIDENCE_MISSING", f"competitors.{index}.approval_ref", "Competitor scope requires an independent approval record.")


def _evidence_index(context: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    return context.get("evidence", {})


def _record_family(record: Mapping[str, Any]) -> str:
    return str(record.get("family") or record.get("source_class") or record.get("source") or "UNKNOWN")


def _record_roles(record: Mapping[str, Any]) -> set[str]:
    roles = record.get("roles", record.get("evidence_roles", []))
    if isinstance(roles, str):
        roles = [roles]
    return {str(role) for role in roles if role}


def _source_matches(record: Mapping[str, Any], expected_source: str, expected_class: str) -> bool:
    source = str(record.get("source", "")).upper()
    source_class = str(record.get("source_class", ""))
    source_aliases = {
        "AHREFS": {"AHREFS"},
        "GSC": {"GSC", "GOOGLE SEARCH CONSOLE"},
        "GA4": {"GA4"},
        "SF": {"SF", "SCREAMING FROG"},
        "SERP": {"SERP", "GOOGLE SEARCH"},
        "WORKDUO": {"WORKDUO"},
        "CRUX": {"CRUX"},
        "BUSINESS": {"BUSINESS", "BUSINESS ACTUAL"},
    }
    return source in source_aliases.get(expected_source, {expected_source}) and source_class == expected_class


def _record_is_fresh(record: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    state = record.get("freshness_state")
    collection = record.get("collection_status")
    if state is not None and state != "FRESH":
        return False
    if collection is not None and collection != "READY":
        return False
    decision_at = context.get("decision_at")
    if decision_at is None:
        return True
    source = str(record.get("source", "")).upper()
    max_days = _FRESHNESS_MAX_DAYS.get(source)
    if max_days is None:
        return True
    candidate_date = record.get("as_of") or record.get("period_end") or record.get("window_end")
    observed = _safe_date(candidate_date) if isinstance(candidate_date, str) else candidate_date
    if observed is None:
        return False
    if observed > decision_at.date():
        return False
    return (decision_at.date() - observed).days <= max_days


def _validate_evidence(
    payload: Mapping[str, Any],
    context: Mapping[str, Any],
    errors: list[ValidationError],
    warnings: list[ValidationError],
) -> tuple[dict[str, dict[str, Any]], set[str], set[str], set[str]]:
    refs = payload.get("evidence_refs") or []
    if len(refs) != len(set(refs)):
        _error(errors, "DUPLICATE_EVIDENCE_REF", "evidence_refs", "Evidence references must be unique.")
    evidence = _evidence_index(context)
    resolved: dict[str, dict[str, Any]] = {}
    conflicts: set[str] = set()
    stale: set[str] = set()
    for ref in dict.fromkeys(refs):
        record = evidence.get(str(ref))
        if not record:
            _error(errors, "EVIDENCE_REF_MISSING", f"evidence_refs[{ref}]", "Evidence reference does not resolve in the immutable context.")
            continue
        resolved[str(ref)] = record
        if not _safe_ref(ref):
            _error(errors, "INVALID_IDENTIFIER", "evidence_refs", "Evidence references must be safe opaque identifiers.")
        if record.get("conflict") or record.get("freshness_state") == "CONFLICTING":
            conflicts.add(str(ref))
        if not _record_is_fresh(record, context):
            stale.add(str(ref))
    if conflicts:
        declared = set(payload.get("conflicting_evidence_refs") or [])
        if conflicts != declared:
            _error(errors, "EVIDENCE_CONFLICT", "conflicting_evidence_refs", "Declared conflicts must match resolved conflicting evidence.")
    if stale and payload.get("status") in {"VALIDATED", "APPROVED"}:
        _error(errors, "STALE_EVIDENCE_POLICY_VIOLATION", "evidence_refs", "Required evidence is stale, partial, or unavailable.")
    elif stale:
        _warning(warnings, "STALE_EVIDENCE_POLICY_VIOLATION", "evidence_refs", "Candidate references include stale or partial evidence.")

    expected_count = len(resolved)
    if payload.get("evidence_count") != expected_count:
        _error(errors, "EVIDENCE_COUNT_MISMATCH", "evidence_count", "evidence_count must equal unique resolved evidence references.", expected=expected_count)
    families = {_record_family(record) for record in resolved.values()}
    if payload.get("independent_family_count") != len(families):
        _error(errors, "EVIDENCE_FAMILY_COUNT_MISMATCH", "independent_family_count", "Independent family count must match resolved evidence families.", expected=len(families))

    missing_roles = set(payload.get("missing_evidence_roles") or [])
    required_roles = set(payload.get("required_evidence_roles") or [])
    covered_roles = set().union(*(_record_roles(record) for record in resolved.values())) if resolved else set()
    for role in sorted(required_roles - missing_roles - covered_roles):
        _error(errors, "MISSING_REQUIRED_EVIDENCE", "required_evidence_roles", "A required evidence role is not covered.", expected=role)
    for role in sorted(missing_roles & covered_roles):
        _error(errors, "EVIDENCE_STATE_CONFLICT", "missing_evidence_roles", "A role cannot be both missing and covered.", expected=role)

    for field_name, (expected_source, expected_class) in _SOURCE_FIELDS.items():
        ref = payload.get(field_name)
        if ref is None:
            continue
        record = resolved.get(str(ref))
        if record is None:
            _error(errors, "EVIDENCE_REF_MISSING", field_name, "Source evidence reference must resolve.")
            continue
        if not _source_matches(record, expected_source, expected_class):
            _error(errors, "SOURCE_CLASS_CONFLICT", field_name, "Source evidence class does not match the contract role.")
    return resolved, families, conflicts, stale


def _validate_score_explanations(
    payload: Mapping[str, Any],
    resolved: Mapping[str, Mapping[str, Any]],
    profile: str,
    errors: list[ValidationError],
) -> None:
    explanations = payload.get("score_explanations") or {}
    weights = _PROFILE_WEIGHTS.get(profile, {})
    for dimension in _SCORE_DIMENSIONS:
        band = payload.get(dimension)
        weight = weights.get(dimension, 0)
        explanation = explanations.get(dimension)
        if weight == 0:
            if band is not None:
                _error(errors, "INACTIVE_SCORE_DIMENSION", dimension, "A weight-zero score dimension must be null.")
            continue
        if band is None:
            continue
        if not isinstance(explanation, Mapping) or not explanation.get("rationale"):
            _error(errors, "MISSING_SCORE_EVIDENCE", dimension, "Every active score band needs a rationale and evidence refs.")
            continue
        refs = explanation.get("evidence_refs") or []
        if not refs:
            _error(errors, "MISSING_SCORE_EVIDENCE", dimension, "Every active score band needs supporting evidence refs.")
        for ref in refs:
            if ref not in resolved:
                _error(errors, "EVIDENCE_REF_MISSING", f"score_explanations.{dimension}.evidence_refs", "Score evidence ref must resolve and belong to evidence_refs.")


def _validate_score(payload: Mapping[str, Any], resolved: Mapping[str, Mapping[str, Any]], errors: list[ValidationError]) -> Optional[str]:
    profile = payload.get("score_profile")
    if profile not in _PROFILE_WEIGHTS:
        _error(errors, "UNKNOWN_SCORING_PROFILE", "score_profile", "Unknown scoring profile.")
        return None
    weights = _PROFILE_WEIGHTS[profile]
    if sum(weights.values()) != 100:
        _error(errors, "POLICY_GAP", "score_profile", "Scoring profile weights must sum to 100.")
    _validate_score_explanations(payload, resolved, profile, errors)
    observed = 0.0
    missing_weight = 0
    role_coverage = set().union(*(_record_roles(record) for record in resolved.values())) if resolved else set()
    missing_roles = set(payload.get("missing_evidence_roles") or [])
    for dimension in _SCORE_DIMENSIONS:
        band = payload.get(dimension)
        weight = weights[dimension]
        if weight == 0:
            continue
        if band is None:
            missing_weight += weight
            continue
        if not isinstance(band, int) or isinstance(band, bool) or not 0 <= band <= 4:
            _error(errors, "SCORE_OUT_OF_RANGE", dimension, "Score bands must be integers from 0 through 4.")
            continue
        observed += weight * band / 4
        role = _SCORE_ROLE[dimension]
        if role not in role_coverage or role in missing_roles:
            _error(errors, "MISSING_DATA_NOT_ZERO", dimension, "Missing evidence cannot be represented as score zero.")
    expected_lower = math.floor(observed)
    expected_upper = math.ceil(observed + missing_weight)
    if payload.get("score_lower_bound") != expected_lower:
        _error(errors, "SCORE_MISMATCH", "score_lower_bound", "Lower bound does not match the profile formula.", expected=expected_lower)
    if payload.get("score_upper_bound") != expected_upper:
        _error(errors, "SCORE_MISMATCH", "score_upper_bound", "Upper bound does not match the profile formula.", expected=expected_upper)
    expected_score = None if missing_weight else math.floor(observed + 0.5)
    if payload.get("opportunity_score") != expected_score:
        _error(errors, "SCORE_MISMATCH", "opportunity_score", "Opportunity score does not match the profile formula.", expected=expected_score)
    return profile


def _validate_opportunity_semantics(
    payload: Mapping[str, Any],
    context: Mapping[str, Any],
    errors: list[ValidationError],
    warnings: list[ValidationError],
) -> None:
    period = payload.get("period")
    if not isinstance(period, str) or not _PERIOD_RE.fullmatch(period):
        _error(errors, "INVALID_PERIOD", "period", "Period must use YYYY-MM.")
    elif _safe_date(period + "-01") is None:
        _error(errors, "INVALID_PERIOD", "period", "Period must be a real calendar month.")
    for field_name in ("evidence_refs", "required_evidence_roles", "missing_evidence_roles", "conflicting_evidence_refs", "rule_ids", "related_opportunity_ids", "dependency_ids"):
        for value in payload.get(field_name, []) or []:
            if not _safe_ref(value):
                _error(errors, "INVALID_IDENTIFIER", field_name, "Identifiers must be safe opaque values.")
    if not _SAFE_REF_RE.fullmatch(str(payload.get("opportunity_id", ""))):
        _error(errors, "INVALID_IDENTIFIER", "opportunity_id", "Opportunity ID must be a safe opaque identifier.")

    try:
        computed_hash = candidate_content_hash(payload)
    except (TypeError, ValueError):
        _error(errors, "SCHEMA_VIOLATION", "content_hash", "Candidate content contains an unsupported non-finite value.")
    else:
        if payload.get("content_hash") != computed_hash:
            _error(errors, "CONTENT_HASH_MISMATCH", "content_hash", "content_hash does not match the canonical candidate content.")

    created = _safe_datetime(payload.get("created_at"))
    updated = _safe_datetime(payload.get("updated_at"))
    decision_at = context.get("decision_at")
    if created and updated and created > updated:
        _error(errors, "INVALID_DATE_ORDER", "created_at", "created_at must not be after updated_at.")
    if decision_at:
        for field_name, value in (("created_at", created), ("updated_at", updated)):
            if value and value > decision_at:
                _error(errors, "FUTURE_TIMESTAMP", field_name, "Candidate timestamp cannot be after decision_at.")

    revision = payload.get("revision")
    supersedes = payload.get("supersedes_opportunity_revision")
    if revision == 1 and supersedes is not None:
        _error(errors, "INVALID_REVISION_CHAIN", "supersedes_opportunity_revision", "Revision 1 cannot supersede another revision.")
    if isinstance(revision, int) and revision > 1 and supersedes != revision - 1:
        _error(errors, "INVALID_REVISION_CHAIN", "supersedes_opportunity_revision", "Revision must reference the immediate previous revision.")

    resolved, families, conflicts, stale = _validate_evidence(payload, context, errors, warnings)
    profile = _validate_score(payload, resolved, errors)
    action = payload.get("recommended_action")
    expected_profile = _ACTION_PROFILE.get(action, "SEO_EXISTING")
    if action not in {"MONITOR", "DO_NOTHING"} and profile and profile != expected_profile:
        _error(errors, "INVALID_ACTION_FOR_OPPORTUNITY", "score_profile", "Score profile must match the recommended action.", expected=expected_profile)
    if action == "CREATE_NEW" and (payload.get("existing_url") or payload.get("existing_urls")):
        _error(errors, "CREATE_NEW_EXISTING_URL_CONFLICT", "existing_url", "CREATE_NEW cannot carry an existing matching URL.")
    if action in {"UPDATE_EXISTING", "TECHNICAL_FIX", "INTERNAL_LINK", "SERP_SNIPPET_OPTIMIZE", "GEO_ENHANCE", "AUTHORITY_BUILD"} and payload.get("status") in {"VALIDATED", "APPROVED"}:
        if not payload.get("existing_url"):
            _error(errors, "INVALID_ACTION_FOR_OPPORTUNITY", "existing_url", "This action requires a validated existing URL.")
    if action == "CONSOLIDATE" and payload.get("status") in {"VALIDATED", "APPROVED"}:
        if len(payload.get("existing_urls") or []) < 2 or not payload.get("target_url"):
            _error(errors, "INVALID_ACTION_FOR_OPPORTUNITY", "existing_urls", "CONSOLIDATE requires source URLs and a survivor URL.")
        if not payload.get("measurement_plan_ref"):
            _error(errors, "POLICY_GAP", "measurement_plan_ref", "A consolidation migration/rollback plan must be referenced before validation.")
    if action in {"MONITOR", "DO_NOTHING"} and not payload.get("review_at"):
        _error(errors, "INVALID_ACTION_FOR_OPPORTUNITY", "review_at", "MONITOR and DO_NOTHING require a review date.")
    if action == "DO_NOTHING" and (payload.get("validation_state") in {"INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE"} or payload.get("missing_evidence_roles") or payload.get("conflicting_evidence_refs")):
        _error(errors, "INVALID_ACTION_FOR_OPPORTUNITY", "status", "Insufficient or conflicting evidence cannot be hidden as DO_NOTHING.")

    missing_roles = set(payload.get("missing_evidence_roles") or [])
    required_roles = set(payload.get("required_evidence_roles") or [])
    if payload.get("status") == "DISCOVERED" and len(families) < 1:
        _error(errors, "MISSING_REQUIRED_EVIDENCE", "evidence_refs", "DISCOVERED requires at least one resolved evidence family.")
    if payload.get("status") in {"CANDIDATE", "VALIDATED", "APPROVED"} and len(families) < 2:
        _error(errors, "MISSING_REQUIRED_EVIDENCE", "independent_family_count", "This state requires at least two independent evidence families.")
    if payload.get("status") in {"VALIDATED", "APPROVED"}:
        if missing_roles or conflicts or stale:
            _error(errors, "MISSING_REQUIRED_EVIDENCE", "missing_evidence_roles", "Validated records cannot retain missing, conflicting, or stale evidence.")
        covered_roles = set().union(*(_record_roles(record) for record in resolved.values())) if resolved else set()
        if required_roles - covered_roles:
            _error(errors, "MISSING_REQUIRED_EVIDENCE", "required_evidence_roles", "Validated records must cover every required role.")
        if payload.get("validation_state") != "PASS":
            _error(errors, "INVALID_VALIDATION_STATE", "validation_state", "VALIDATED and APPROVED records require validation_state=PASS.")
        if payload.get("confidence") not in {"MEDIUM", "HIGH"}:
            _error(errors, "CONFIDENCE_EVIDENCE_MISMATCH", "confidence", "Validated records require MEDIUM or HIGH confidence.")
    if conflicts:
        if payload.get("validation_state") != "CONFLICTING_EVIDENCE":
            _error(errors, "EVIDENCE_CONFLICT", "validation_state", "Conflicting evidence requires CONFLICTING_EVIDENCE state.")
        if payload.get("confidence") not in {"LOW", "NOT_ASSESSABLE"}:
            _error(errors, "CONFIDENCE_EVIDENCE_MISMATCH", "confidence", "Conflicting evidence cannot be HIGH confidence.")
    if missing_roles or stale:
        if payload.get("validation_state") not in {"INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE"}:
            _error(errors, "CONFIDENCE_EVIDENCE_MISMATCH", "validation_state", "Missing or stale evidence must remain visibly insufficient.")
        if payload.get("confidence") not in {"LOW", "NOT_ASSESSABLE"} and payload.get("status") in {"VALIDATED", "APPROVED"}:
            _error(errors, "CONFIDENCE_EVIDENCE_MISMATCH", "confidence", "Insufficient evidence cannot be HIGH confidence.")

    if payload.get("confidence") == "HIGH":
        if len(families) < 2 or conflicts or stale or not context.get("entity_mappings_confirmed", False) or not context.get("alternative_explanations_addressed", False):
            _error(errors, "CONFIDENCE_EVIDENCE_MISMATCH", "confidence", "HIGH confidence requires independent fresh evidence and explicit mapping/alternative checks.")

    business_score = payload.get("business_score")
    if business_score is not None:
        if not payload.get("business_evidence_ref") or not payload.get("business_override_ref"):
            _error(errors, "MISSING_BUSINESS_EVIDENCE", "business_score", "Business score requires business evidence and an approved overlay.")
        elif not _business_approved(context, payload.get("business_override_ref")):
            _error(errors, "MISSING_BUSINESS_EVIDENCE", "business_override_ref", "Business overlay is missing or not approved.")

    if payload.get("status") == "APPROVED":
        review_ref = payload.get("review_event_ref")
        review = context.get("review_events", {}).get(str(review_ref))
        if not review or not review.get("reviewer_id") or not review.get("authenticated", False) or review.get("engine_identity", False):
            _error(errors, "APPROVAL_EVIDENCE_MISSING", "review_event_ref", "APPROVED requires an authenticated human review event.")
        else:
            if review.get("decision") != "APPROVED":
                _error(errors, "INVALID_REVIEW_STATE", "review_event_ref", "Review event decision must be APPROVED.")
            if review.get("candidate_revision") != payload.get("revision"):
                _error(errors, "INVALID_REVIEW_STATE", "review_event_ref", "Review event must bind the exact candidate revision.")
            if review.get("candidate_hash") != payload.get("content_hash"):
                _error(errors, "INVALID_REVIEW_STATE", "review_event_ref", "Review event must bind the exact candidate hash.")
        if not _scope_approved(context, payload.get("scope_approval_ref")):
            _error(errors, "APPROVAL_EVIDENCE_MISSING", "scope_approval_ref", "APPROVED requires an approved scope record.")
        if not payload.get("measurement_plan_ref"):
            _error(errors, "APPROVAL_EVIDENCE_MISSING", "measurement_plan_ref", "APPROVED requires a measurement plan reference.")


def validate_ahrefs_scope(
    payload: Any,
    *,
    context: Optional[Mapping[str, Any]] = None,
    decision_at: Any = None,
) -> ValidationResult:
    """Validate an Ahrefs scope proposal using only local JSON-like input."""

    ctx = _context(context, decision_at=decision_at)
    errors = _structural_errors(payload, _AHREFS_SCHEMA)
    warnings: list[ValidationError] = []
    if isinstance(payload, Mapping):
        errors.extend(_format_errors(payload, _schema(_AHREFS_SCHEMA)))
        _validate_ahrefs(payload, ctx, errors)
    return ValidationResult(errors=errors, warnings=warnings)


def validate_opportunity(
    payload: Any,
    *,
    context: Optional[Mapping[str, Any]] = None,
    evidence: Any = None,
    review_events: Any = None,
    scope_approvals: Any = None,
    business_overlays: Any = None,
    decision_at: Any = None,
) -> ValidationResult:
    """Validate an opportunity proposal and optional immutable local context."""

    ctx = _context(
        context,
        evidence=evidence,
        review_events=review_events,
        scope_approvals=scope_approvals,
        business_overlays=business_overlays,
        decision_at=decision_at,
    )
    errors = _structural_errors(payload, _OPPORTUNITY_SCHEMA)
    warnings: list[ValidationError] = []
    if isinstance(payload, Mapping):
        errors.extend(_format_errors(payload, _schema(_OPPORTUNITY_SCHEMA)))
        errors.extend(_url_errors(payload))
        _validate_opportunity_semantics(payload, ctx, errors, warnings)
    return ValidationResult(errors=errors, warnings=warnings)


__all__ = [
    "ValidationError",
    "ValidationResult",
    "candidate_content_hash",
    "validate_ahrefs_scope",
    "validate_opportunity",
]
