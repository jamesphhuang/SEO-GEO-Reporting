"""Offline SERP snapshot normalization and bounded collection boundaries.

The collector has no network implementation.  Callers inject a transport for
an explicitly approved, shortlist-only provider.  Normalization is shared by
fixtures and any future adapter so interpretation never calls a source.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Optional, Protocol
from urllib.parse import urlsplit

from reporting.opportunity.entities import RegistryInputError, normalize_url
from reporting.opportunity.store.serialization import canonical_json


SOURCE_ROLE = "LIVE / OBSERVED SERP VALIDATION EVIDENCE"
SOURCE_CLASS = "LIVE_SERP_SNAPSHOT"
CONTRACT_VERSION = "serp_snapshot.v1.proposal"
FRESHNESS_STATES = frozenset({"READY", "PARTIAL", "STALE", "FAILED", "NOT_AVAILABLE"})
COLLECTION_STATES = frozenset({"SUCCESS", "PARTIAL", "FAILED", "NOT_AVAILABLE"})
QUERY_ENTITY_TYPES = frozenset({"QUERY", "KEYWORD"})
RESULT_TYPES = frozenset({
    "article", "comparison", "category", "product", "homepage", "tool",
    "video", "forum", "official_documentation", "faq", "unknown",
})
FEATURE_STATES = frozenset({"OBSERVED", "NOT_OBSERVED", "NOT_AVAILABLE"})


class SERPInputError(ValueError):
    """Raised when a SERP row cannot be safely scoped or normalized."""

    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


class SERPTransport(Protocol):
    def search(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Return one provider response for one approved query request."""


@dataclass(frozen=True)
class SERPCollectionPolicy:
    """Conservative client-side limits; provider limits are never trusted."""

    max_candidates: int = 30
    max_queries: int = 30
    max_results_per_query: int = 30
    timeout_seconds: int = 30
    max_retries: int = 1


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SERPInputError("INVALID_FIELD", f"{field} must be non-empty text", field)
    return value.strip()


def _datetime(value: Any, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, field).replace("Z", "+00:00"))
    except ValueError as exc:
        raise SERPInputError("INVALID_DATETIME", f"{field} must be ISO-8601 date-time", field) from exc
    if parsed.tzinfo is None:
        raise SERPInputError("NAIVE_DATETIME", f"{field} must include a timezone", field)
    return parsed


def _entity_row(registry: Mapping[str, Any], entity_type: str, entity_id: str) -> Mapping[str, Any]:
    if entity_type not in QUERY_ENTITY_TYPES:
        raise SERPInputError("INVALID_QUERY_ENTITY", "validation query must be a QUERY or KEYWORD", "query_ref")
    id_field = "query_id" if entity_type == "QUERY" else "keyword_id"
    for row in (registry.get("entities") or {}).get(entity_type, []):
        if row.get(id_field) == entity_id:
            return row
    raise SERPInputError("UNRESOLVED_QUERY_ENTITY", "validation query is not in the canonical registry", "query_ref")


def resolve_query_ref(registry: Mapping[str, Any], query_ref: Mapping[str, Any]) -> tuple[dict[str, Any], Mapping[str, Any]]:
    if not isinstance(query_ref, Mapping):
        raise SERPInputError("INVALID_QUERY_ENTITY", "query_ref must be a mapping", "query_ref")
    entity_type = _text(query_ref.get("entity_type"), "query_ref.entity_type").upper()
    entity_id = _text(query_ref.get("entity_id"), "query_ref.entity_id")
    row = _entity_row(registry, entity_type, entity_id)
    expected_text = row.get("text") or row.get("normalized_text")
    actual_text = _text(query_ref.get("text"), "query_ref.text")
    if row.get("text") and actual_text != row.get("text"):
        raise SERPInputError("QUERY_TEXT_MISMATCH", "query text must match the canonical entity exactly", "query_ref.text")
    if not row.get("text") and actual_text.casefold() != str(expected_text).casefold():
        raise SERPInputError("QUERY_TEXT_MISMATCH", "query text does not match the canonical identity", "query_ref.text")
    for field, row_field in (("locale", "locale"), ("country", "country_database")):
        supplied = query_ref.get(field)
        expected = row.get(row_field)
        if supplied is not None and expected is not None and str(supplied) != str(expected):
            raise SERPInputError("QUERY_SCOPE_MISMATCH", f"query {field} does not match canonical identity", f"query_ref.{field}")
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "text": actual_text,
        "locale": query_ref.get("locale") or row.get("locale"),
        "country": query_ref.get("country") or row.get("country_database"),
    }, row


def _registry_url(registry: Mapping[str, Any], normalized_url: str) -> Optional[str]:
    rows = (registry.get("entities") or {}).get("URL", [])
    matches = [row for row in rows if row.get("normalized_url") == normalized_url]
    if len(matches) != 1:
        return None
    return matches[0].get("url_id")


def _approved_domains(registry: Mapping[str, Any]) -> tuple[set[str], dict[str, list[str]]]:
    owned: set[str] = set()
    for row in (registry.get("entities") or {}).get("URL", []):
        normalized = row.get("normalized_url")
        if isinstance(normalized, str):
            host = urlsplit(normalized).hostname
            if host:
                owned.add(host.casefold())
    competitors: dict[str, list[str]] = {}
    for row in (registry.get("entities") or {}).get("COMPETITOR", []):
        domain = row.get("domain")
        competitor_id = row.get("competitor_id")
        if isinstance(domain, str) and isinstance(competitor_id, str):
            competitors.setdefault(domain.casefold().rstrip("."), []).append(competitor_id)
    return owned, competitors


def _normalize_result(raw: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        raise SERPInputError("INVALID_RESULT", "organic result must be a mapping", "organic_results")
    rank = raw.get("rank", raw.get("position"))
    if isinstance(rank, bool) or not isinstance(rank, int) or rank < 1:
        raise SERPInputError("INVALID_RANK", "organic result rank must be a positive integer", "organic_results.rank")
    url = _text(raw.get("url"), "organic_results.url")
    try:
        parsed = urlsplit(url)
        if parsed.username or parsed.password or parsed.hostname is None:
            raise ValueError("unsafe URL")
        normalized = normalize_url(url)
    except (RegistryInputError, ValueError) as exc:
        raise SERPInputError("INVALID_RESULT_URL", "organic result URL is not a safe http(s) URL", "organic_results.url") from exc
    domain = parsed.hostname.casefold().rstrip(".")
    owned_domains, competitor_domains = _approved_domains(registry)
    result_type = str(raw.get("result_type", "unknown")).casefold()
    if result_type not in RESULT_TYPES:
        result_type = "unknown"
    competitor_ids = sorted(set(competitor_domains.get(domain, [])))
    output = {
        "rank": rank,
        "url": url,
        "normalized_url": normalized,
        "url_id": _registry_url(registry, normalized),
        "url_match_state": "CANONICAL" if _registry_url(registry, normalized) else "UNMAPPED_URL",
        "domain": domain,
        "title": raw.get("title") if isinstance(raw.get("title"), str) else None,
        "snippet": raw.get("snippet") if isinstance(raw.get("snippet"), str) else None,
        "result_type": result_type,
        "owned": domain in owned_domains,
        "competitor_ids": competitor_ids,
        "competitor_match_state": "NOT_APPLICABLE" if domain in owned_domains else ("APPROVED" if competitor_ids else "UNMAPPED_DOMAIN"),
    }
    return output


def _feature_states(raw: Any) -> dict[str, str]:
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        values = raw.items()
    elif isinstance(raw, (list, tuple)):
        values = ((item, "OBSERVED") for item in raw)
    else:
        raise SERPInputError("INVALID_FEATURES", "serp_features must be a mapping or list", "serp_features")
    output: dict[str, str] = {}
    for key, state in values:
        name = _text(key, "serp_features.name").casefold()
        status = str(state).upper()
        if status not in FEATURE_STATES:
            raise SERPInputError("INVALID_FEATURE_STATE", "SERP feature state is unsupported", "serp_features")
        output[name] = status
    return dict(sorted(output.items()))


def _snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    semantic = {key: value for key, value in snapshot.items() if key not in {"retrieved_at", "observed_at", "provider_response_id", "snapshot_hash"}}
    return hashlib.sha256(canonical_json(semantic).encode("utf-8")).hexdigest()


def _provider_provenance(value: Any, provider: str) -> dict[str, Any]:
    """Keep provenance useful while excluding credentials, cookies, and PII."""
    if value is None:
        return {"provider": provider, "adapter_version": "serp-offline-v1"}
    if not isinstance(value, Mapping):
        raise SERPInputError("INVALID_PROVENANCE", "provider provenance must be a mapping", "provider_provenance")
    blocked = re.compile(r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization|cookie|session|email|phone)")
    output: dict[str, Any] = {}
    for key, item in value.items():
        if blocked.search(str(key)):
            raise SERPInputError("SENSITIVE_PROVENANCE", "provider provenance cannot contain credentials or personal identifiers", "provider_provenance")
        if isinstance(item, (str, int, bool)) or item is None:
            output[str(key)] = item
    output.setdefault("provider", provider)
    return dict(sorted(output.items()))


def normalize_serp_snapshot(record: Mapping[str, Any], registry: Mapping[str, Any], *, max_results: int = 30) -> dict[str, Any]:
    """Normalize one provider/fixture response to a WP4 SERP Evidence record."""

    if not isinstance(record, Mapping):
        raise SERPInputError("INVALID_RECORD", "SERP snapshot must be a mapping")
    query_ref, query_row = resolve_query_ref(registry, record.get("query_ref") or record.get("validation_query"))
    retrieved = _datetime(record.get("retrieved_at") or record.get("observed_at"), "retrieved_at")
    country = _text(record.get("country") or query_ref.get("country"), "country")
    locale = _text(record.get("locale") or query_ref.get("locale"), "locale")
    if query_ref.get("country") and country != query_ref.get("country"):
        raise SERPInputError("QUERY_SCOPE_MISMATCH", "SERP country must match the canonical query", "country")
    if query_ref.get("locale") and locale != query_ref.get("locale"):
        raise SERPInputError("QUERY_SCOPE_MISMATCH", "SERP locale must match the canonical query", "locale")
    device = _text(record.get("device", "DESKTOP"), "device").upper()
    search_scope = _text(record.get("search_scope", "COUNTRY"), "search_scope").upper()
    provider = _text(record.get("provider", "synthetic-serp"), "provider")
    max_results = int(record.get("max_results", max_results))
    if max_results < 1 or max_results > 30:
        raise SERPInputError("INVALID_CAP", "max_results must be between 1 and 30", "max_results")
    freshness_state = str(record.get("freshness_state", "READY")).upper()
    collection_status = str(record.get("collection_status", "SUCCESS")).upper()
    if freshness_state not in FRESHNESS_STATES:
        raise SERPInputError("INVALID_FRESHNESS_STATE", "unsupported SERP freshness state", "freshness_state")
    if collection_status not in COLLECTION_STATES:
        raise SERPInputError("INVALID_COLLECTION_STATUS", "unsupported SERP collection status", "collection_status")
    raw_results = record.get("organic_results")
    if collection_status in {"FAILED", "NOT_AVAILABLE"} or freshness_state in {"FAILED", "NOT_AVAILABLE"}:
        raw_results = None
    elif raw_results is None:
        collection_status = "FAILED"
        freshness_state = "FAILED"
        raw_results = None
    elif not isinstance(raw_results, (list, tuple)):
        raise SERPInputError("INVALID_RESULTS", "organic_results must be a list", "organic_results")
    normalized_results: list[dict[str, Any]] = []
    provider_result_count = 0 if raw_results is None else len(raw_results)
    truncated = bool(record.get("truncated", False))
    if raw_results is not None:
        normalized_results = [_normalize_result(item, registry) for item in raw_results]
        ranks = [item["rank"] for item in normalized_results]
        if len(ranks) != len(set(ranks)):
            raise SERPInputError("DUPLICATE_RANK", "organic result ranks must be unique", "organic_results")
        normalized_results.sort(key=lambda item: item["rank"])
        if len(normalized_results) > max_results:
            normalized_results = normalized_results[:max_results]
            truncated = True
            collection_status = "PARTIAL"
    if raw_results == [] and collection_status == "SUCCESS":
        collection_status = "PARTIAL"
        freshness_state = "PARTIAL"
    features = _feature_states(record.get("serp_features"))
    snapshot: dict[str, Any] = {
        "query_ref": query_ref,
        "query_text": query_ref["text"],
        "country": country,
        "locale": locale,
        "device": device,
        "search_scope": search_scope,
        "provider": provider,
        "max_results": max_results,
        "provider_result_count": provider_result_count,
        "observed_result_count": len(normalized_results),
        "truncated": truncated,
        "organic_results": normalized_results if raw_results is not None else None,
        "serp_features": features,
        "retrieved_at": retrieved.isoformat(),
        "observed_at": retrieved.isoformat(),
        "collection_status": collection_status,
        "freshness_state": freshness_state,
        "coverage": str(record.get("coverage", "COMPLETE_WITHIN_SCOPE" if normalized_results else "PARTIAL")).upper(),
        "error_code": record.get("error_code"),
        "query_topic_refs": list(query_row.get("canonical_topic_refs", [])),
    }
    snapshot["snapshot_hash"] = _snapshot_hash(snapshot)
    semantic_id = {key: value for key, value in snapshot.items() if key not in {"retrieved_at", "observed_at", "snapshot_hash"}}
    evidence_id = record.get("evidence_id") or "SERP_" + hashlib.sha256(canonical_json(semantic_id).encode("utf-8")).hexdigest()[:24]
    revision = record.get("revision", 1)
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise SERPInputError("INVALID_REVISION", "SERP evidence revision must be positive", "revision")
    result: dict[str, Any] = {
        "record_type": "EVIDENCE",
        "evidence_id": evidence_id,
        "revision": revision,
        "source": "SERP",
        "source_class": SOURCE_CLASS,
        "source_role": SOURCE_ROLE,
        "metric": "serp_snapshot",
        "value": snapshot if raw_results is not None else None,
        "unit": "snapshot",
        "period_start": retrieved.date().isoformat(),
        "period_end": retrieved.date().isoformat(),
        "as_of": retrieved.date().isoformat(),
        "retrieved_at": retrieved.isoformat(),
        "observed_at": retrieved.isoformat(),
        "freshness_state": freshness_state,
        "collection_status": collection_status,
        "source_reference": _text(record.get("source_reference", "synthetic-serp"), "source_reference"),
        "contract_version": CONTRACT_VERSION,
        "entity_refs": [{"entity_type": query_ref["entity_type"], "entity_id": query_ref["entity_id"]}],
        "topic_refs": list(query_row.get("canonical_topic_refs", [])),
        "supersedes_evidence_id": record.get("supersedes_evidence_id"),
        "supersedes_revision": record.get("supersedes_revision"),
        "created_at": str(record.get("created_at") or retrieved.isoformat()),
        "query_ref": query_ref,
        "query_id": query_ref["entity_id"],
        "query_entity_type": query_ref["entity_type"],
        "query_text": query_ref["text"],
        "country": country,
        "locale": locale,
        "device": device,
        "search_scope": search_scope,
        "provider": provider,
        "provider_provenance": _provider_provenance(record.get("provider_provenance"), provider),
        "snapshot_hash": snapshot["snapshot_hash"],
        "max_results": max_results,
        "provider_result_count": provider_result_count,
        "observed_result_count": len(normalized_results),
        "truncated": truncated,
        "coverage": snapshot["coverage"],
        "error_code": snapshot["error_code"],
        "serp_features": features,
    }
    if result["supersedes_evidence_id"] is not None and result["supersedes_evidence_id"] != evidence_id:
        raise SERPInputError("INVALID_SUPERSEDES", "supersedes_evidence_id must match evidence_id", "supersedes_evidence_id")
    _datetime(result["created_at"], "created_at")
    return result


def _is_transient(error: BaseException | Mapping[str, Any]) -> bool:
    if isinstance(error, Mapping):
        code = str(error.get("error_code", "")).upper()
        status = error.get("status_code")
        return code in {"TIMEOUT", "TRANSIENT", "429"} or status == 429 or (isinstance(status, int) and status >= 500)
    return isinstance(error, TimeoutError)


def collect_serp(
    requests: Iterable[Mapping[str, Any]],
    *,
    transport: SERPTransport,
    registry: Mapping[str, Any],
    policy: SERPCollectionPolicy = SERPCollectionPolicy(),
) -> list[dict[str, Any]]:
    """Collect a bounded shortlist through an injected transport only."""

    request_rows = [dict(item) for item in requests]
    if len(request_rows) > policy.max_queries or len({row.get("candidate_id") for row in request_rows}) > policy.max_candidates:
        raise SERPInputError("BUDGET_EXCEEDED", "shortlist/query cap exceeded", "requests")
    output: list[dict[str, Any]] = []
    for request in request_rows:
        if not request.get("candidate_id"):
            raise SERPInputError("SHORTLIST_REQUIRED", "SERP collection requires a shortlisted candidate_id", "candidate_id")
        resolve_query_ref(registry, request.get("query_ref"))
        attempts = 0
        response: Optional[Mapping[str, Any]] = None
        last_error: Optional[Mapping[str, Any]] = None
        while attempts <= policy.max_retries:
            attempts += 1
            try:
                bounded_request = dict(request)
                bounded_request.setdefault("timeout_seconds", policy.timeout_seconds)
                response = transport.search(bounded_request)
                if not isinstance(response, Mapping):
                    raise SERPInputError("INVALID_PROVIDER_RESPONSE", "SERP transport must return a mapping")
                if _is_transient(response):
                    last_error = dict(response)
                    response = None
                    if attempts <= policy.max_retries:
                        continue
                    break
                break
            except Exception as exc:  # transport errors become explicit failure evidence
                error = {"error_code": getattr(exc, "code", type(exc).__name__).upper(), "status_code": getattr(exc, "status_code", None)}
                last_error = error
                if (not _is_transient(exc) and not _is_transient(error)) or attempts > policy.max_retries:
                    break
        if response is None:
            response = dict(request)
            response.update({"collection_status": "FAILED", "freshness_state": "FAILED", "organic_results": None, "error_code": (last_error or {}).get("error_code", "TRANSPORT_FAILURE")})
        else:
            response = dict(response)
            response.setdefault("collection_status", "SUCCESS")
            response.setdefault("freshness_state", "READY")
            response.setdefault("retrieved_at", request.get("retrieved_at"))
            response.setdefault("query_ref", request.get("query_ref"))
            response.setdefault("country", request.get("country"))
            response.setdefault("locale", request.get("locale"))
            response.setdefault("device", request.get("device", "DESKTOP"))
            response.setdefault("search_scope", request.get("search_scope", "COUNTRY"))
            response.setdefault("max_results", policy.max_results_per_query)
        output.append(normalize_serp_snapshot(response, registry, max_results=policy.max_results_per_query))
    return output


__all__ = [
    "COLLECTION_STATES", "CONTRACT_VERSION", "FEATURE_STATES", "FRESHNESS_STATES",
    "RESULT_TYPES", "SERPCollectionPolicy", "SERPInputError", "SOURCE_CLASS",
    "SOURCE_ROLE", "collect_serp", "normalize_serp_snapshot", "resolve_query_ref",
]
