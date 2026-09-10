"""Bounded, read-only Ahrefs evidence ingestion.

The adapter deliberately has no HTTP or MCP dependency.  A caller supplies a
transport with ``request(endpoint, params)``; production wiring can therefore
keep credentials in the connector while tests use deterministic fixtures.
Only approved, non-production scopes may be collected.  Raw responses are
optional local artifacts and are sanitized before they are written.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Protocol, Sequence
from urllib.parse import urlsplit


SOURCE = "AHREFS"
SOURCE_CLASS = "THIRD_PARTY_ESTIMATE"
CONTENT_GAP_ENDPOINT = "content-gap"
ORGANIC_KEYWORDS_ENDPOINT = "site-explorer-organic-keywords"
COMPETITORS_ENDPOINT = "site-explorer-organic-competitors"

CAPABILITY_GAP = "CAPABILITY_GAP"
CAPABILITY_STATUS = {
    ORGANIC_KEYWORDS_ENDPOINT: "AVAILABLE",
    COMPETITORS_ENDPOINT: "AVAILABLE",
    CONTENT_GAP_ENDPOINT: "UNAVAILABLE",
}

_SENSITIVE_KEY_RE = re.compile(
    r"(?:authorization|bearer|api[_-]?key|access[_-]?token|client[_-]?secret|secret|password|credential|token)",
    re.IGNORECASE,
)
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TRANSIENT_STATUS = {408, 425, 429}
_RETRYABLE_STATUS = _TRANSIENT_STATUS | set(range(500, 600))
_ENDPOINT_ROW_KEYS = {
    ORGANIC_KEYWORDS_ENDPOINT: "keywords",
    COMPETITORS_ENDPOINT: "competitors",
}


class AhrefsTransport(Protocol):
    def request(self, endpoint: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        """Perform one provider request without writing provider state."""


class AhrefsTransportError(RuntimeError):
    """Transport error carrying a provider status without raw response data."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class AhrefsSchemaError(ValueError):
    """Provider response cannot be normalized safely."""


@dataclass(frozen=True)
class AhrefsQueryBudget:
    """Conservative client-side run limits.

    The defaults are based on the observed 50-unit minimum per returned row
    during the 2026-09-10 probes.  They are intentionally lower than provider
    export defaults and are not an owner-approved production budget.
    """

    max_requests_per_run: int = 4
    max_units_per_run: int = 500
    max_rows_per_endpoint: int = 5
    max_pages: int = 2
    timeout_seconds: int = 30
    max_retries: int = 1
    estimated_units_per_row: int = 50

    def __post_init__(self) -> None:
        for name in (
            "max_requests_per_run",
            "max_units_per_run",
            "max_rows_per_endpoint",
            "max_pages",
            "timeout_seconds",
            "estimated_units_per_row",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries must not be negative")
        if self.max_retries + 1 > self.max_requests_per_run:
            raise ValueError("max_retries exceeds request budget for one endpoint")

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class AhrefsQuery:
    endpoint: str
    target: str
    country: str
    date: str
    select: tuple[str, ...]
    mode: str = "domain"
    protocol: str = "both"
    limit: int = 1
    traffic_mode: str = "adaptive"
    volume_mode: str = "monthly"
    date_compared: str | None = None
    scope_id: str = ""

    def __post_init__(self) -> None:
        if self.endpoint not in CAPABILITY_STATUS:
            raise ValueError(f"unsupported Ahrefs endpoint: {self.endpoint}")
        if not self.target or not self.country or not self.date:
            raise ValueError("target, country, and date are required")
        if not self.select:
            raise ValueError("select must contain at least one field")
        if self.limit <= 0:
            raise ValueError("limit must be positive")
        if self.mode not in {"exact", "prefix", "domain", "subdomains"}:
            raise ValueError("invalid target mode")
        if self.protocol not in {"both", "http", "https"}:
            raise ValueError("invalid protocol")


@dataclass
class AhrefsIngestionResult:
    status: str
    records: list[dict[str, Any]]
    manifest: dict[str, Any]
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        return self.status == "READY"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_date(value: Any) -> date | None:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _host(value: str) -> str:
    parsed = urlsplit(value if "://" in value else f"https://{value}")
    return (parsed.hostname or "").lower().rstrip(".")


def _canonical(value: Any) -> Any:
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _semantic_hash(record: Mapping[str, Any]) -> str:
    content = {key: value for key, value in record.items() if key not in {"content_hash", "retrieved_at"}}
    encoded = json.dumps(_canonical(content), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _safe_source_reference(query: AhrefsQuery) -> dict[str, Any]:
    return {
        "endpoint": query.endpoint,
        "target": query.target,
        "country": query.country,
        "date": query.date,
        "mode": query.mode,
        "protocol": query.protocol,
        "select": list(query.select),
        "traffic_mode": query.traffic_mode,
        "volume_mode": query.volume_mode,
        "date_compared": query.date_compared,
    }


def _field(row: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in row:
            return row[name]
    return None


def _nonnegative_number(value: Any, field_name: str) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise AhrefsSchemaError(f"invalid {field_name}")
    return value


def _safe_url(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise AhrefsSchemaError("invalid URL")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise AhrefsSchemaError("unsafe URL")
    if "@" in parsed.query or "@" in parsed.fragment:
        raise AhrefsSchemaError("unsafe URL")
    return value


def _freshness_state(as_of: str, retrieved_at: datetime) -> str:
    observed = _safe_date(as_of)
    if observed is None:
        return "UNKNOWN"
    age = (retrieved_at.date() - observed).days
    if age < 0:
        return "UNKNOWN"
    return "FRESH" if age <= 30 else "STALE"


def _dedup_key(endpoint: str, query: AhrefsQuery, row: Mapping[str, Any]) -> tuple[Any, ...]:
    if endpoint == ORGANIC_KEYWORDS_ENDPOINT:
        return (
            endpoint,
            query.country,
            query.target,
            row.get("keyword"),
            _field(row, "best_position_url", "url"),
            query.date,
        )
    return (
        endpoint,
        query.country,
        query.target,
        _field(row, "competitor_domain", "competitor_url", "competitor"),
        query.date,
    )


def _validate_scope(scope: Mapping[str, Any], query: AhrefsQuery) -> list[str]:
    errors: list[str] = []
    if scope.get("approval_state") != "APPROVED":
        errors.append("SCOPE_NOT_APPROVED")
    if not scope.get("approval_ref"):
        errors.append("SCOPE_APPROVAL_REF_MISSING")
    if scope.get("environment") not in {"preview", "uat"}:
        errors.append("PRODUCTION_ENVIRONMENT_BLOCKED")
    if scope.get("source_class") not in {None, SOURCE_CLASS}:
        errors.append("SOURCE_CLASS_CONFLICT")
    if scope.get("estimation_flag") not in {None, True}:
        errors.append("ESTIMATE_CLASSIFICATION_CONFLICT")
    if scope.get("country_database") and scope.get("country_database") != query.country:
        errors.append("COUNTRY_SCOPE_MISMATCH")
    allowed_targets = set()
    for item in scope.get("scopes", []) or []:
        if isinstance(item, Mapping) and item.get("target"):
            allowed_targets.add(_host(str(item["target"])))
    target_host = _host(query.target)
    if allowed_targets and not any(target_host == allowed or target_host.endswith(f".{allowed}") for allowed in allowed_targets):
        errors.append("TARGET_OUTSIDE_SCOPE")
    return errors


def _extract_rows(endpoint: str, response: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    key = _ENDPOINT_ROW_KEYS.get(endpoint)
    if key and isinstance(response.get(key), list):
        return [row for row in response[key] if isinstance(row, Mapping)]
    for candidate in ("rows", "data", "results"):
        value = response.get(candidate)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, Mapping)]
    raise AhrefsSchemaError("response row envelope is missing")


def _response_error(response: Mapping[str, Any]) -> tuple[int | None, str] | None:
    error = response.get("error")
    if not error:
        return None
    if isinstance(error, Mapping):
        code = error.get("status_code", error.get("status"))
        try:
            code = int(code) if code is not None else None
        except (TypeError, ValueError):
            code = None
        category = str(error.get("code", error.get("type", "PROVIDER_ERROR")))
    else:
        code = None
        category = "PROVIDER_ERROR"
    return code, category


def _retryable(status_code: int | None) -> bool:
    return status_code in _RETRYABLE_STATUS


def _sanitize(value: Any, *, key: str = "") -> Any:
    if _SENSITIVE_KEY_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, str) and re.search(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]{8,}", value):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {str(k): _sanitize(v, key=str(k)) for k, v in value.items() if not _SENSITIVE_KEY_RE.search(str(k))}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    return value


def _provider_units(response: Mapping[str, Any]) -> int | None:
    usage = response.get("apiUsageCosts") or response.get("api_usage_costs")
    if not isinstance(usage, Mapping):
        return None
    for key in ("units-cost-total-actual", "units_cost_total_actual", "units-cost-total", "units_used", "units"):
        value = usage.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
    return None


def _next_page(response: Mapping[str, Any]) -> Any:
    for key in ("next_page", "next_cursor", "next_page_token", "page_token"):
        value = response.get(key)
        if value not in (None, "", False):
            return value
    return None


def _normalize_row(endpoint: str, query: AhrefsQuery, row: Mapping[str, Any], retrieved_at: datetime) -> dict[str, Any]:
    if endpoint == ORGANIC_KEYWORDS_ENDPOINT:
        keyword = row.get("keyword")
        if not isinstance(keyword, str) or not keyword.strip():
            raise AhrefsSchemaError("organic keyword row requires keyword")
        normalized = {
            "source": SOURCE,
            "source_class": SOURCE_CLASS,
            "endpoint": endpoint,
            "retrieved_at": _iso(retrieved_at),
            "as_of_date": query.date,
            "country_database": query.country,
            "target": query.target,
            "mode": query.mode,
            "metric": "organic_keyword",
            "keyword": keyword,
            "url": _safe_url(_field(row, "best_position_url", "url")),
            "position": _nonnegative_number(_field(row, "best_position"), "position"),
            "volume": _nonnegative_number(row.get("volume"), "volume"),
            "difficulty": _nonnegative_number(_field(row, "keyword_difficulty", "difficulty"), "difficulty"),
            "traffic_estimate": _nonnegative_number(_field(row, "sum_traffic", "traffic"), "traffic_estimate"),
            "competitor": None,
            "source_reference": _safe_source_reference(query),
            "freshness_state": _freshness_state(query.date, retrieved_at),
            "estimation_flag": True,
            "collection_status": "READY",
            "coverage": "COMPLETE_WITHIN_SCOPE",
        }
    else:
        competitor = _field(row, "competitor_domain", "competitor_url", "competitor")
        if not isinstance(competitor, str) or not competitor.strip():
            raise AhrefsSchemaError("competitor row requires competitor_domain or competitor_url")
        normalized = {
            "source": SOURCE,
            "source_class": SOURCE_CLASS,
            "endpoint": endpoint,
            "retrieved_at": _iso(retrieved_at),
            "as_of_date": query.date,
            "country_database": query.country,
            "target": query.target,
            "mode": query.mode,
            "metric": "organic_competitor",
            "keyword": None,
            "url": _safe_url(row.get("competitor_url")),
            "position": None,
            "volume": _nonnegative_number(_field(row, "volume_target", "volume_competitor"), "volume"),
            "difficulty": _nonnegative_number(_field(row, "keyword_difficulty_target", "keyword_difficulty"), "difficulty"),
            "traffic_estimate": _nonnegative_number(_field(row, "traffic", "traffic_target"), "traffic_estimate"),
            "competitor": competitor,
            "source_reference": _safe_source_reference(query),
            "freshness_state": _freshness_state(query.date, retrieved_at),
            "estimation_flag": True,
            "collection_status": "READY",
            "coverage": "COMPLETE_WITHIN_SCOPE",
        }
    normalized["content_hash"] = _semantic_hash(normalized)
    return normalized


def normalize_ahrefs_response(
    endpoint: str,
    query: AhrefsQuery,
    response: Mapping[str, Any],
    *,
    retrieved_at: datetime | None = None,
    max_rows: int = 5,
) -> tuple[list[dict[str, Any]], dict[str, int | bool], list[str]]:
    """Normalize one bounded response without network access or side effects."""

    if endpoint not in {ORGANIC_KEYWORDS_ENDPOINT, COMPETITORS_ENDPOINT}:
        raise AhrefsSchemaError(f"normalization unavailable for {endpoint}")
    if not isinstance(response, Mapping):
        raise AhrefsSchemaError("provider response must be an object")
    failure = _response_error(response)
    if failure:
        raise AhrefsTransportError(f"provider response classified as {failure[1]}", status_code=failure[0])
    rows = _extract_rows(endpoint, response)
    now = retrieved_at or _now_utc()
    accepted: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen: set[tuple[Any, ...]] = set()
    duplicate_rows = 0
    malformed_rows = 0
    for row in rows:
        if len(accepted) >= max_rows:
            break
        key = _dedup_key(endpoint, query, row)
        if key in seen:
            duplicate_rows += 1
            continue
        seen.add(key)
        try:
            accepted.append(_normalize_row(endpoint, query, row, now))
        except AhrefsSchemaError:
            malformed_rows += 1
    if duplicate_rows:
        warnings.append("DUPLICATE_ROWS_DROPPED")
    if malformed_rows:
        warnings.append("MALFORMED_ROWS_DROPPED")
    metadata: dict[str, int | bool] = {
        "returned_rows": len(rows),
        "accepted_rows": len(accepted),
        "truncated_rows": max(0, len(rows) - len(accepted) - duplicate_rows - malformed_rows),
        "duplicate_rows": duplicate_rows,
        "malformed_rows": malformed_rows,
        "truncated": len(rows) > max_rows,
    }
    return accepted, metadata, warnings


def _transport_request(transport: Any, endpoint: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
    if hasattr(transport, "request"):
        response = transport.request(endpoint, params)
    else:
        response = transport(endpoint, params)
    if not isinstance(response, Mapping):
        raise AhrefsSchemaError("transport response must be an object")
    return response


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_sanitize(value), ensure_ascii=False, sort_keys=True, indent=2) + "\n")


def _validate_run_id(run_id: str) -> None:
    if not _SAFE_ID_RE.fullmatch(run_id):
        raise ValueError("run_id must be a safe opaque identifier")


def ingest_ahrefs(
    queries: Sequence[AhrefsQuery],
    *,
    scope: Mapping[str, Any],
    transport: AhrefsTransport | Callable[[str, Mapping[str, Any]], Mapping[str, Any]],
    budget: AhrefsQueryBudget | None = None,
    run_id: str | None = None,
    git_sha: str | None = None,
    started_at: datetime | None = None,
    output_dir: str | Path | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> AhrefsIngestionResult:
    """Collect bounded Ahrefs evidence into local artifacts only.

    The function never writes to the provider.  An ``output_dir`` is optional;
    when supplied it receives only sanitized raw/normalized JSON and a manifest.
    """

    if not queries:
        raise ValueError("at least one query is required")
    run_id = run_id or f"ahrefs-{uuid.uuid4().hex}"
    _validate_run_id(run_id)
    budget = budget or AhrefsQueryBudget()
    started = started_at or _now_utc()
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    warnings: list[str] = []
    seen_hashes: set[str] = set()
    request_count = 0
    retry_count = 0
    units_observed = 0
    units_known = True
    endpoint_manifest: dict[str, dict[str, Any]] = {}
    all_raw: dict[str, list[Mapping[str, Any]]] = {}
    all_normalized: dict[str, list[dict[str, Any]]] = {}

    for query in queries:
        details = endpoint_manifest.setdefault(query.endpoint, {
            "endpoint": query.endpoint,
            "target": query.target,
            "country_database": query.country,
            "mode": query.mode,
            "requested_rows": min(query.limit, budget.max_rows_per_endpoint),
            "returned_rows": 0,
            "accepted_rows": 0,
            "truncated_rows": 0,
            "request_count": 0,
            "pages": 0,
            "retries": 0,
            "units_observed": 0,
            "status": "READY",
            "warnings": [],
        })
        scope_errors = _validate_scope(scope, query)
        if scope_errors:
            details["status"] = "NOT_AVAILABLE"
            details["warnings"].extend(scope_errors)
            errors.append({"endpoint": query.endpoint, "code": scope_errors[0]})
            continue
        if CAPABILITY_STATUS.get(query.endpoint) == "UNAVAILABLE":
            details["status"] = "NOT_AVAILABLE"
            details["warnings"].append(CAPABILITY_GAP)
            warnings.append(f"{query.endpoint}:{CAPABILITY_GAP}")
            continue

        page_token: Any = None
        endpoint_records: list[dict[str, Any]] = []
        endpoint_seen: set[tuple[Any, ...]] = set()
        for page_number in range(1, budget.max_pages + 1):
            if len(endpoint_records) >= budget.max_rows_per_endpoint:
                details["truncated"] = True
                break
            request_limit = min(query.limit, budget.max_rows_per_endpoint - len(endpoint_records))
            estimated = request_limit * budget.estimated_units_per_row
            if units_observed + estimated > budget.max_units_per_run:
                details["status"] = "PARTIAL"
                details["warnings"].append("BUDGET_EXCEEDED")
                errors.append({"endpoint": query.endpoint, "code": "BUDGET_EXCEEDED"})
                break
            if request_count >= budget.max_requests_per_run:
                details["status"] = "PARTIAL"
                details["warnings"].append("REQUEST_BUDGET_EXCEEDED")
                errors.append({"endpoint": query.endpoint, "code": "REQUEST_BUDGET_EXCEEDED"})
                break
            params: dict[str, Any] = {
                "target": query.target,
                "country": query.country,
                "date": query.date,
                "mode": query.mode,
                "protocol": query.protocol,
                "select": ",".join(query.select),
                "limit": request_limit,
                "traffic_mode": query.traffic_mode,
                "volume_mode": query.volume_mode,
                "timeout": budget.timeout_seconds,
            }
            if query.date_compared:
                params["date_compared"] = query.date_compared
            if page_token is not None:
                params["page"] = page_number
                params["page_token"] = page_token
            response: Mapping[str, Any] | None = None
            for attempt in range(budget.max_retries + 1):
                if request_count >= budget.max_requests_per_run:
                    break
                request_count += 1
                details["request_count"] += 1
                try:
                    response = _transport_request(transport, query.endpoint, params)
                    provider_error = _response_error(response)
                    if provider_error:
                        raise AhrefsTransportError("provider request failed", status_code=provider_error[0])
                    break
                except (AhrefsTransportError, TimeoutError, ConnectionError) as exc:
                    status_code = getattr(exc, "status_code", None)
                    if not _retryable(status_code) or attempt >= budget.max_retries:
                        details["status"] = "NOT_AVAILABLE" if status_code in {401, 403} else "FAILED"
                        code = "AUTH_OR_PERMISSION" if status_code in {401, 403} else "PROVIDER_FAILURE"
                        errors.append({"endpoint": query.endpoint, "code": code})
                        response = None
                        break
                    retry_count += 1
                    details["retries"] += 1
                    sleep_fn(min(2.0, 0.5 * (2**attempt)))
            if response is None:
                if details["status"] == "READY" and request_count >= budget.max_requests_per_run:
                    details["status"] = "PARTIAL"
                    details["warnings"].append("REQUEST_BUDGET_EXCEEDED")
                    errors.append({"endpoint": query.endpoint, "code": "REQUEST_BUDGET_EXCEEDED"})
                break
            provider_units = _provider_units(response)
            if provider_units is None:
                units_known = False
            else:
                units_observed += provider_units
                details["units_observed"] += provider_units
                if units_observed > budget.max_units_per_run:
                    details["status"] = "PARTIAL"
                    details["warnings"].append("UNIT_BUDGET_EXCEEDED")
                    errors.append({"endpoint": query.endpoint, "code": "UNIT_BUDGET_EXCEEDED"})
                    break
            try:
                raw_rows = _extract_rows(query.endpoint, response)
            except AhrefsSchemaError:
                details["status"] = "FAILED"
                details["warnings"].append("SCHEMA_DRIFT")
                errors.append({"endpoint": query.endpoint, "code": "SCHEMA_DRIFT"})
                break
            all_raw.setdefault(query.endpoint, []).extend(raw_rows[: budget.max_rows_per_endpoint])
            try:
                normalized, metadata, row_warnings = normalize_ahrefs_response(
                    query.endpoint,
                    query,
                    response,
                    retrieved_at=started,
                    max_rows=budget.max_rows_per_endpoint,
                )
            except AhrefsTransportError as exc:
                details["status"] = "NOT_AVAILABLE" if exc.status_code in {401, 403} else "FAILED"
                errors.append({"endpoint": query.endpoint, "code": "PROVIDER_FAILURE"})
                break
            details["returned_rows"] += int(metadata["returned_rows"])
            details["truncated_rows"] += int(metadata["truncated_rows"])
            if metadata.get("truncated"):
                details["truncated"] = True
            details["warnings"].extend(row_warnings)
            if row_warnings and details["status"] == "READY":
                details["status"] = "PARTIAL"
            for record in normalized:
                key = _dedup_key(query.endpoint, query, {
                    "keyword": record.get("keyword"),
                    "best_position_url": record.get("url"),
                    "competitor_domain": record.get("competitor"),
                })
                if key in endpoint_seen:
                    details["warnings"].append("DUPLICATE_ROWS_DROPPED")
                    continue
                endpoint_seen.add(key)
                endpoint_records.append(record)
                if len(endpoint_records) >= budget.max_rows_per_endpoint:
                    break
            page_token = _next_page(response)
            details["pages"] += 1
            if not page_token:
                break
            if page_number == budget.max_pages:
                details["truncated"] = True
                details["warnings"].append("MAX_PAGES_REACHED")
        if details["truncated_rows"] or details.get("truncated"):
            details["status"] = "PARTIAL"
            details["coverage"] = "TRUNCATED"
        else:
            details["coverage"] = "COMPLETE_WITHIN_SCOPE"
        details["accepted_rows"] = len(endpoint_records)
        if any(record["freshness_state"] == "STALE" for record in endpoint_records):
            details["status"] = "STALE"
        all_normalized[query.endpoint] = endpoint_records
        for record in endpoint_records:
            if record["content_hash"] not in seen_hashes:
                seen_hashes.add(record["content_hash"])
                records.append(record)

    completed = _now_utc()
    statuses = [item["status"] for item in endpoint_manifest.values()]
    if all(status == "READY" for status in statuses) and not errors and not warnings:
        status = "READY"
    elif any(item in {"READY", "PARTIAL"} for item in statuses):
        status = "PARTIAL"
    elif any(item == "NOT_AVAILABLE" for item in statuses):
        status = "NOT_AVAILABLE"
    else:
        status = "FAILED"
    if any(item.get("status") == "STALE" for item in endpoint_manifest.values()):
        status = "STALE"
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "started_at": _iso(started),
        "completed_at": _iso(completed),
        "source": SOURCE,
        "source_class": SOURCE_CLASS,
        "endpoint": list(endpoint_manifest),
        "target": sorted({query.target for query in queries}),
        "country_database": sorted({query.country for query in queries}),
        "mode": sorted({query.mode for query in queries}),
        "requested_rows": sum(int(item["requested_rows"]) for item in endpoint_manifest.values()),
        "returned_rows": sum(int(item["returned_rows"]) for item in endpoint_manifest.values()),
        "accepted_rows": len(records),
        "truncated_rows": sum(int(item["truncated_rows"]) for item in endpoint_manifest.values()),
        "request_count": request_count,
        "retry_count": retry_count,
        "units_observed": units_observed if units_known else None,
        "budget_limit": budget.as_dict(),
        "freshness": sorted({record["freshness_state"] for record in records}) or ["UNKNOWN"],
        "status": status,
        "warnings": sorted(set(warnings + [warning for item in endpoint_manifest.values() for warning in item["warnings"]])),
        "git_sha": git_sha,
        "coverage": {endpoint: item.get("coverage", "UNKNOWN") for endpoint, item in endpoint_manifest.items()},
        "endpoints": endpoint_manifest,
    }

    if output_dir is not None:
        root = Path(output_dir) / run_id / "ahrefs"
        _write_json(root / "run_manifest.json", manifest)
        for endpoint, raw_rows in all_raw.items():
            _write_json(root / "raw" / f"{endpoint}.json", {"rows": raw_rows})
        for endpoint, endpoint_records in all_normalized.items():
            _write_json(root / "normalized" / f"{endpoint}.json", {"records": endpoint_records})

    return AhrefsIngestionResult(status=status, records=records, manifest=manifest, errors=errors, warnings=warnings)


__all__ = [
    "AhrefsIngestionResult",
    "AhrefsQuery",
    "AhrefsQueryBudget",
    "AhrefsSchemaError",
    "AhrefsTransportError",
    "COMPETITORS_ENDPOINT",
    "CONTENT_GAP_ENDPOINT",
    "ORGANIC_KEYWORDS_ENDPOINT",
    "SOURCE_CLASS",
    "ingest_ahrefs",
    "normalize_ahrefs_response",
]
