"""Offline normalization for GA4 landing-page behavior evidence.

This module accepts already-collected JSON-like rows.  It deliberately has no
transport, credential, Sheets, or GA4 API dependency.  URL identity is resolved
through the WP3 registry and all output is suitable for the WP4 EvidenceStore.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping
from urllib.parse import urlsplit

from reporting.opportunity.entities import RegistryInputError, normalize_url


ROOT = Path(__file__).resolve().parents[2]
GA4_SCOPE = json.loads((ROOT / "contracts/ga4_scope.v1.json").read_text(encoding="utf-8"))
SOURCE_CLASS = "FIRST_PARTY_BEHAVIOR_DIAGNOSTIC"
SUPPORTED_METRICS = {
    "sessions": "count",
    "users": "count",
    "engaged_sessions": "count",
    "engagement_rate": "ratio",
    "average_engagement_time": "seconds",
    "event_count": "count",
}
FRESHNESS_STATES = {"READY", "PARTIAL", "STALE", "FAILED", "NOT_AVAILABLE"}
COLLECTION_STATES = {"SUCCESS", "PARTIAL", "FAILED", "NOT_AVAILABLE"}


class GA4EvidenceInputError(ValueError):
    """Raised when a normalized GA4 row cannot be safely scoped or joined."""

    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GA4EvidenceInputError("INVALID_FIELD", f"{field} must be non-empty text", field)
    return value.strip()


def _parse_date(value: Any, field: str) -> date:
    try:
        return date.fromisoformat(_text(value, field))
    except ValueError as exc:
        raise GA4EvidenceInputError("INVALID_DATE", f"{field} must be an ISO date", field) from exc


def _parse_datetime(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, field).replace("Z", "+00:00"))
    except ValueError as exc:
        raise GA4EvidenceInputError("INVALID_DATETIME", f"{field} must be ISO-8601 date-time", field) from exc
    if parsed.tzinfo is None:
        raise GA4EvidenceInputError("NAIVE_DATETIME", f"{field} must include a timezone", field)
    return parsed


def _site_for(property_id: str, hostname: str) -> tuple[str, Mapping[str, Any]]:
    for site_key, site in GA4_SCOPE["sites"].items():
        if str(site.get("property_id")) == property_id and str(site.get("hostname", "")).casefold() == hostname.casefold():
            return site_key, site
    raise GA4EvidenceInputError("OUT_OF_SCOPE", "property_id and hostname are not an approved GA4 site scope", "property_id")


def _landing_url(record: Mapping[str, Any], hostname: str) -> str:
    raw = record.get("landing_page") or record.get("landingPage") or record.get("url")
    raw = _text(raw, "landing_page")
    if raw.startswith("/"):
        raw = f"https://{hostname}{raw}"
    try:
        parsed = urlsplit(raw)
    except ValueError as exc:
        raise GA4EvidenceInputError("INVALID_URL", "landing_page is not a valid URL/path", "landing_page") from exc
    if parsed.hostname is None or parsed.hostname.casefold() != hostname.casefold():
        raise GA4EvidenceInputError("URL_HOST_MISMATCH", "landing_page host must match the approved GA4 hostname", "landing_page")
    try:
        return normalize_url(raw)
    except RegistryInputError as exc:
        raise GA4EvidenceInputError(exc.code, str(exc), "landing_page") from exc


def resolve_registry_url(registry: Mapping[str, Any], normalized_url: str) -> tuple[str, Mapping[str, Any]]:
    """Resolve an exact normalized URL; no fuzzy title or redirect matching."""

    rows = (registry.get("entities") or {}).get("URL", [])
    matches = [row for row in rows if row.get("normalized_url") == normalized_url]
    if len(matches) != 1:
        code = "UNRESOLVED_ENTITY" if not matches else "AMBIGUOUS_ENTITY"
        raise GA4EvidenceInputError(code, "GA4 landing URL does not resolve to exactly one canonical URL", "landing_page")
    row = matches[0]
    url_id = row.get("url_id")
    if not isinstance(url_id, str) or not url_id:
        raise GA4EvidenceInputError("UNRESOLVED_ENTITY", "canonical URL row has no stable url_id", "url_id")
    return url_id, row


def _stable_evidence_id(value: Mapping[str, Any]) -> str:
    semantic = {
        key: value[key]
        for key in sorted(value)
        if key not in {"evidence_id", "revision", "content_hash", "created_at", "retrieved_at"}
    }
    encoded = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return "GA4_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _validate_value(metric: str, value: Any, freshness_state: str, coverage: str) -> None:
    if freshness_state in {"FAILED", "NOT_AVAILABLE"}:
        if value is not None:
            raise GA4EvidenceInputError("INVALID_VALUE", "FAILED/NOT_AVAILABLE evidence must retain null value", "value")
        return
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)) or value < 0:
        raise GA4EvidenceInputError("INVALID_VALUE", "GA4 value must be finite and non-negative", "value")
    if metric in {"sessions", "users", "engaged_sessions", "event_count"} and (not isinstance(value, int) or isinstance(value, bool)):
        raise GA4EvidenceInputError("INVALID_COUNT", "count metrics must be integers", "value")
    if metric == "engagement_rate" and value > 1:
        raise GA4EvidenceInputError("INVALID_RATIO", "engagement_rate must be a ratio from 0 through 1", "value")
    if metric == "event_count" and value == 0 and coverage not in {"COMPLETE_WITHIN_SCOPE", "COMPLETE"}:
        raise GA4EvidenceInputError("ZERO_WITHOUT_COMPLETE_COVERAGE", "event zero requires explicit complete scope coverage", "coverage")


def normalize_ga4_record(record: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize one synthetic or adapter-produced GA4 row for WP4 storage."""

    if not isinstance(record, Mapping):
        raise GA4EvidenceInputError("INVALID_RECORD", "GA4 evidence must be a mapping")
    property_id = _text(record.get("property_id"), "property_id")
    hostname = _text(record.get("hostname"), "hostname")
    site_key, site = _site_for(property_id, hostname)
    channel = _text(record.get("channel"), "channel")
    if channel not in GA4_SCOPE["channels"]:
        raise GA4EvidenceInputError("OUT_OF_SCOPE", "channel is not in the approved GA4 scope", "channel")
    quality_scope = str(record.get("quality_scope", "PAGE_LEVEL")).upper()
    if quality_scope not in {"PAGE_LEVEL", "SITE_WIDE_CONTEXT"}:
        raise GA4EvidenceInputError("INVALID_QUALITY_SCOPE", "quality_scope must be PAGE_LEVEL or SITE_WIDE_CONTEXT", "quality_scope")
    if quality_scope == "SITE_WIDE_CONTEXT":
        normalized_url = None
        url_id = None
        url_row = {"canonical_topic_refs": []}
    else:
        normalized_url = _landing_url(record, hostname)
        url_id, url_row = resolve_registry_url(registry, normalized_url)
    metric = _text(record.get("metric"), "metric")
    if metric not in SUPPORTED_METRICS:
        raise GA4EvidenceInputError("UNSUPPORTED_METRIC", f"unsupported GA4 diagnostic metric: {metric}", "metric")
    freshness_state = str(record.get("freshness_state", "READY")).upper()
    collection_status = str(record.get("collection_status", "SUCCESS")).upper()
    if freshness_state not in FRESHNESS_STATES:
        raise GA4EvidenceInputError("INVALID_FRESHNESS_STATE", "freshness_state is unsupported", "freshness_state")
    if collection_status not in COLLECTION_STATES:
        raise GA4EvidenceInputError("INVALID_COLLECTION_STATUS", "collection_status is unsupported", "collection_status")
    coverage = str(record.get("coverage", "UNKNOWN")).upper()
    value = record.get("value")
    _validate_value(metric, value, freshness_state, coverage)
    period_start = _parse_date(record.get("period_start"), "period_start")
    period_end = _parse_date(record.get("period_end"), "period_end")
    as_of = _parse_date(record.get("as_of"), "as_of")
    retrieved_at = _parse_datetime(record.get("retrieved_at"), "retrieved_at")
    if period_start > period_end or period_end > as_of or as_of > retrieved_at.date():
        raise GA4EvidenceInputError("INVALID_DATE_ORDER", "period_start <= period_end <= as_of <= retrieved_at date is required")
    if metric == "event_count":
        event_name = record.get("event_name")
        event_classification = record.get("event_classification", "UNMAPPED_EVENT")
        if event_name is not None:
            event_name = _text(event_name, "event_name")
        event_classification = _text(event_classification, "event_classification")
    else:
        event_name = None
        event_classification = None
    segment = {"site": site_key, "hostname": site["hostname"], "channel": channel}
    output: dict[str, Any] = {
        "record_type": "EVIDENCE",
        "evidence_id": record.get("evidence_id") or _stable_evidence_id({**record, "normalized_url": normalized_url, "url_id": url_id}),
        "revision": int(record.get("revision", 1)),
        "source": "GA4",
        "source_class": SOURCE_CLASS,
        "metric": metric,
        "value": value,
        "unit": SUPPORTED_METRICS[metric],
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "as_of": as_of.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "freshness_state": freshness_state,
        "collection_status": collection_status,
        "source_reference": _text(record.get("source_reference", "synthetic-ga4"), "source_reference"),
        "contract_version": _text(record.get("contract_version", "ga4_quality.v1.proposal"), "contract_version"),
        "entity_refs": ([{"entity_type": "URL", "entity_id": url_id}] if url_id else []),
        "topic_refs": list(url_row.get("canonical_topic_refs", [])),
        "supersedes_evidence_id": record.get("supersedes_evidence_id"),
        "supersedes_revision": record.get("supersedes_revision"),
        "created_at": str(record.get("created_at") or retrieved_at.isoformat()),
        "property_id": property_id,
        "hostname": hostname,
        "channel": channel,
        "segment": json.dumps(segment, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        "scope_id": f"GA4_{site_key}",
        "normalized_url": normalized_url,
        "url_id": url_id,
        "quality_scope": quality_scope,
        "coverage": coverage,
        "sampling": record.get("sampling"),
        "subject_to_thresholding": record.get("subject_to_thresholding"),
        "source_timezone": site["source_timezone"],
        "event_name": event_name,
        "event_classification": event_classification,
    }
    if output["revision"] < 1:
        raise GA4EvidenceInputError("INVALID_REVISION", "revision must be positive", "revision")
    if output["supersedes_evidence_id"] is not None and output["supersedes_evidence_id"] != output["evidence_id"]:
        raise GA4EvidenceInputError("INVALID_SUPERSEDES", "supersedes_evidence_id must match evidence_id")
    return output


def normalize_ga4_records(records: Iterable[Mapping[str, Any]], registry: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [normalize_ga4_record(record, registry) for record in records]


__all__ = [
    "GA4EvidenceInputError",
    "GA4_SCOPE",
    "SOURCE_CLASS",
    "SUPPORTED_METRICS",
    "normalize_ga4_record",
    "normalize_ga4_records",
    "resolve_registry_url",
]
