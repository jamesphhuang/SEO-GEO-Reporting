"""Offline, fixed-sample Workduo normalisation for WP8.

This module intentionally has no HTTP client or credential handling.  A caller
provides already collected (normally synthetic) rows and receives immutable
EvidenceStore-compatible records.  Prompt/topic identity is always resolved
through the canonical registry; no text similarity or model inference is used.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime
from typing import Any, Iterable, Mapping, Optional

from reporting.opportunity.entities import RegistryInputError, normalize_domain, normalize_text, normalize_url

SOURCE = "WORKDUO"
SOURCE_CLASS = "MONITORED_GEO_SAMPLE"
SOURCE_ROLE = "MONITORED_FIXED_SAMPLE"
CONTRACT_VERSION = "geo_observation.v1.proposal"
FRESHNESS_STATES = {"READY", "PARTIAL", "STALE", "FAILED", "NOT_AVAILABLE"}
COLLECTION_STATES = {"SUCCESS", "PARTIAL", "FAILED", "NOT_AVAILABLE"}
CAPABILITY_STATES = {"OBSERVED", "NOT_OBSERVED", "NOT_AVAILABLE", "UNKNOWN"}
SAMPLE_STATUSES = {"ACTIVE", "RETIRED", "DRAFT"}


class WorkduoInputError(ValueError):
    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkduoInputError("INVALID_FIELD", f"{field} must be non-empty text", field)
    return value.strip()


def _date(value: Any, field: str) -> str:
    text = _text(value, field)
    try:
        return date.fromisoformat(text).isoformat()
    except ValueError as exc:
        raise WorkduoInputError("INVALID_DATE", f"{field} must be an ISO date", field) from exc


def _datetime(value: Any, field: str) -> str:
    text = _text(value, field).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise WorkduoInputError("INVALID_DATETIME", f"{field} must be ISO-8601", field) from exc
    if parsed.tzinfo is None:
        raise WorkduoInputError("NAIVE_DATETIME", f"{field} must include a timezone", field)
    return parsed.isoformat()


def _entities(registry: Mapping[str, Any], kind: str) -> list[Mapping[str, Any]]:
    return list((registry.get("entities") or {}).get(kind, []))


def _row(registry: Mapping[str, Any], kind: str, key: str, value: str) -> Optional[Mapping[str, Any]]:
    return next((row for row in _entities(registry, kind) if row.get(key) == value), None)


def _stable_hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _prompt_ref(raw: Any, registry: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(raw, str):
        prompt_id = raw
        supplied = {}
    elif isinstance(raw, Mapping):
        prompt_id = raw.get("prompt_id") or raw.get("entity_id")
        supplied = raw
    else:
        raise WorkduoInputError("UNMAPPED_PROMPT", "prompt_ref must identify a canonical PROMPT", "prompt_ref")
    prompt_id = _text(prompt_id, "prompt_id")
    row = _row(registry, "PROMPT", "prompt_id", prompt_id)
    if row is None:
        raise WorkduoInputError("UNMAPPED_PROMPT", "prompt is not in the canonical registry", "prompt_ref")
    if supplied.get("prompt_text") is not None and normalize_text(str(supplied["prompt_text"])) != row.get("normalized_text"):
        raise WorkduoInputError("PROMPT_IDENTITY_MISMATCH", "prompt text does not exactly match the canonical prompt", "prompt_text")
    if supplied.get("prompt_version") is not None and str(supplied["prompt_version"]) != str(row.get("prompt_version")):
        raise WorkduoInputError("PROMPT_VERSION_MISMATCH", "prompt version does not match the canonical prompt", "prompt_version")
    return {"entity_type": "PROMPT", "entity_id": prompt_id, "revision": int(supplied.get("revision", row.get("revision", 1))), "prompt_version": row.get("prompt_version"), "locale": row.get("locale"), "region": row.get("region"), "platform": row.get("platform"), "canonical_topic_refs": list(row.get("canonical_topic_refs") or [])}


def normalize_sample_definition(record: Mapping[str, Any], registry: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a fixed prompt cohort and return its deterministic registry row."""
    if not isinstance(record, Mapping):
        raise WorkduoInputError("INVALID_RECORD", "sample definition must be a mapping")
    sample_id = _text(record.get("sample_id"), "sample_id")
    version = _text(record.get("sample_version", record.get("version")), "sample_version")
    status = str(record.get("status", "ACTIVE")).upper()
    if status not in SAMPLE_STATUSES:
        raise WorkduoInputError("INVALID_SAMPLE_STATUS", "sample status is unsupported", "status")
    raw_prompts = record.get("prompt_refs", record.get("prompts"))
    if not isinstance(raw_prompts, (list, tuple)) or not raw_prompts:
        raise WorkduoInputError("EMPTY_SAMPLE", "fixed sample must contain at least one prompt", "prompt_refs")
    prompts = [_prompt_ref(item, registry) for item in raw_prompts]
    if len({item["entity_id"] for item in prompts}) != len(prompts):
        raise WorkduoInputError("DUPLICATE_PROMPT", "sample prompt population must be unique", "prompt_refs")
    locale = _text(record.get("locale", prompts[0].get("locale") or "UNKNOWN"), "locale")
    market = _text(record.get("market", record.get("region", prompts[0].get("region") or "UNKNOWN")), "market")
    platform = _text(record.get("platform", "UNKNOWN"), "platform")
    model_scope = _text(record.get("model_scope", "UNKNOWN"), "model_scope")
    effective_from = _date(record.get("effective_from"), "effective_from")
    effective_to = record.get("effective_to")
    if effective_to is not None:
        effective_to = _date(effective_to, "effective_to")
        if effective_to < effective_from:
            raise WorkduoInputError("INVALID_DATE_ORDER", "effective_to must be on or after effective_from")
    methodology = _text(record.get("provider_methodology", "fixed_prompt_cohort"), "provider_methodology")
    canonical = {
        "record_type": "GEO_SAMPLE",
        "sample_id": sample_id,
        "sample_version": version,
        "revision": int(record.get("revision", 1)),
        "status": status,
        "prompt_refs": prompts,
        "prompt_population": sorted(item["entity_id"] for item in prompts),
        "market": market,
        "locale": locale,
        "platform": platform,
        "model_scope": model_scope,
        "provider": _text(record.get("provider", "WORKDUO"), "provider"),
        "provider_methodology": methodology,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "source_role": SOURCE_ROLE,
        "synthetic": bool(record.get("synthetic", True)),
    }
    canonical["sample_hash"] = _stable_hash({key: value for key, value in canonical.items() if key != "sample_hash"})
    return canonical


def _capability(value: Any, field: str, default: str = "UNKNOWN") -> str:
    state = str(value if value is not None else default).upper()
    if state not in CAPABILITY_STATES:
        raise WorkduoInputError("INVALID_CAPABILITY_STATE", f"{field} capability state is unsupported", field)
    return state


def _resolve_owned(value: Any, registry: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    if value is None:
        return None, None
    raw = _text(value, "owned_url")
    try:
        normalized = normalize_url(raw)
    except RegistryInputError as exc:
        raise WorkduoInputError(exc.code, str(exc), "owned_url") from exc
    row = next((item for item in _entities(registry, "URL") if item.get("normalized_url") == normalized), None)
    if row is None:
        return None, normalized
    return str(row["url_id"]), normalized


def _competitor(value: Any, registry: Mapping[str, Any]) -> tuple[Optional[str], Optional[str]]:
    if value is None:
        return None, None
    domain = normalize_domain(_text(value, "competitor_domain"))
    row = next((item for item in _entities(registry, "COMPETITOR") if item.get("domain") == domain), None)
    return (str(row["competitor_id"]) if row else None), domain


def normalize_workduo_observation(record: Mapping[str, Any], registry: Mapping[str, Any], *, sample_definition: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """Normalize one Workduo observation; unsupported fields remain explicit."""
    if not isinstance(record, Mapping):
        raise WorkduoInputError("INVALID_RECORD", "Workduo observation must be a mapping")
    sample_id = _text(record.get("sample_id"), "sample_id")
    sample_version = _text(record.get("sample_version", record.get("sample_revision", "")), "sample_version")
    sample_revision = int(record.get("sample_revision", 1))
    if sample_definition is not None:
        if sample_definition.get("sample_id") != sample_id or str(sample_definition.get("sample_version")) != sample_version:
            raise WorkduoInputError("SAMPLE_SCOPE_MISMATCH", "observation does not belong to supplied fixed sample")
        if int(sample_definition.get("revision", 1)) != sample_revision:
            raise WorkduoInputError("SAMPLE_REVISION_MISMATCH", "observation sample revision differs from definition")
    prompt = _prompt_ref(record.get("prompt_ref", record.get("prompt_id")), registry)
    topic_id = record.get("topic_id") or record.get("topic_ref")
    allowed_topics = set(prompt.get("canonical_topic_refs") or [])
    if topic_id is not None:
        topic_id = str(topic_id.get("entity_id")) if isinstance(topic_id, Mapping) else str(topic_id)
        if _row(registry, "TOPIC", "topic_id", topic_id) is None or topic_id not in allowed_topics:
            raise WorkduoInputError("UNMAPPED_TOPIC", "topic is not explicitly mapped to the canonical prompt", "topic_id")
    elif len(allowed_topics) == 1:
        topic_id = next(iter(allowed_topics))
    else:
        raise WorkduoInputError("UNMAPPED_TOPIC", "observation has no unambiguous canonical topic", "topic_id")
    locale = _text(record.get("locale", prompt.get("locale") or "UNKNOWN"), "locale")
    market = _text(record.get("market", record.get("region", prompt.get("region") or "UNKNOWN")), "market")
    platform = _text(record.get("platform", "UNKNOWN"), "platform")
    model_scope = _text(record.get("model_scope", "UNKNOWN"), "model_scope")
    freshness = str(record.get("freshness_state", "READY")).upper()
    collection = str(record.get("collection_status", "SUCCESS")).upper()
    if freshness not in FRESHNESS_STATES: raise WorkduoInputError("INVALID_FRESHNESS_STATE", "unsupported freshness_state", "freshness_state")
    if collection not in COLLECTION_STATES: raise WorkduoInputError("INVALID_COLLECTION_STATUS", "unsupported collection_status", "collection_status")
    period_start = _date(record.get("period_start"), "period_start"); period_end = _date(record.get("period_end"), "period_end"); as_of = _date(record.get("as_of"), "as_of"); retrieved_at = _datetime(record.get("retrieved_at"), "retrieved_at")
    if period_start > period_end or period_end > as_of or as_of > retrieved_at[:10]: raise WorkduoInputError("INVALID_DATE_ORDER", "period_start <= period_end <= as_of <= retrieved_at date is required")
    mention = _capability(record.get("mention_state", record.get("mention")), "mention_state")
    citation = _capability(record.get("citation_state", record.get("citation")), "citation_state")
    citation_url = record.get("citation_url")
    citation_url_id = None
    citation_url_match_state = "NOT_AVAILABLE"
    if citation_url is not None:
        citation = "OBSERVED"
        try:
            normalized_citation = normalize_url(_text(citation_url, "citation_url"))
        except RegistryInputError as exc:
            raise WorkduoInputError(exc.code, str(exc), "citation_url") from exc
        citation_url = normalized_citation
        citation_row = next((item for item in _entities(registry, "URL") if item.get("normalized_url") == normalized_citation), None)
        if citation_row is not None:
            citation_url_id = str(citation_row["url_id"]); citation_url_match_state = "CANONICAL"
        else:
            citation_url_match_state = "UNMAPPED_URL"
    owned_url_id, normalized_owned_url = _resolve_owned(record.get("owned_url"), registry)
    competitor_id, competitor_domain = _competitor(record.get("competitor_domain"), registry)
    unknown_domains = [] if competitor_id else ([competitor_domain] if competitor_domain else [])
    failure = freshness in {"FAILED", "NOT_AVAILABLE"} or collection in {"FAILED", "NOT_AVAILABLE"}
    observation = {
        "observation_id": str(record.get("observation_id") or "GEOOBS_" + _stable_hash({"sample_id": sample_id, "sample_version": sample_version, "prompt_id": prompt["entity_id"], "topic_id": topic_id, "period_end": period_end, "platform": platform, "model_scope": model_scope})[:24]),
        "sample_id": sample_id, "sample_version": sample_version, "sample_revision": sample_revision,
        "sample_hash": sample_definition.get("sample_hash") if sample_definition else record.get("sample_hash"),
        "prompt_ref": {"entity_type": "PROMPT", "entity_id": prompt["entity_id"], "revision": prompt["revision"]},
        "topic_ref": {"entity_type": "TOPIC", "entity_id": topic_id},
        "market": market, "locale": locale, "platform": platform, "model_scope": model_scope,
        "provider": _text(record.get("provider", "WORKDUO"), "provider"), "provider_methodology": _text(record.get("provider_methodology", "fixed_prompt_cohort"), "provider_methodology"),
        "mention_state": mention, "citation_state": citation, "citation_url": citation_url, "citation_url_id": citation_url_id, "citation_url_match_state": citation_url_match_state,
        "owned_url_id": owned_url_id, "owned_url": normalized_owned_url,
        "competitor_id": competitor_id, "competitor_domain": competitor_domain, "unknown_domains": sorted(set(unknown_domains)),
        "visibility_metric_name": record.get("visibility_metric_name"), "visibility_metric_definition": record.get("visibility_metric_definition"), "visibility_value": None if failure else record.get("visibility_value"),
        "freshness_state": freshness, "collection_status": collection, "period_start": period_start, "period_end": period_end, "as_of": as_of, "retrieved_at": retrieved_at,
        "capabilities": {"mention": mention, "citation": citation},
        "source_role": SOURCE_ROLE, "source_reference": _text(record.get("source_reference", "synthetic-workduo"), "source_reference"),
    }
    # EvidenceStore's canonical entity index is intentionally limited to the
    # stable typed keys it can resolve.  Keep PROMPT identity pinned inside the
    # observation payload while using topic/URL/competitor refs for store joins.
    entity_refs = [observation["topic_ref"]]
    if owned_url_id: entity_refs.append({"entity_type": "URL", "entity_id": owned_url_id})
    if citation_url_id and citation_url_id != owned_url_id: entity_refs.append({"entity_type": "URL", "entity_id": citation_url_id})
    if competitor_id: entity_refs.append({"entity_type": "COMPETITOR", "entity_id": competitor_id})
    return {
        "record_type": "EVIDENCE", "evidence_id": str(record.get("evidence_id") or "GEO_" + _stable_hash(observation)[:24]), "revision": int(record.get("revision", 1)),
        "source": SOURCE, "source_class": SOURCE_CLASS, "source_role": SOURCE_ROLE, "metric": "geo_observation", "value": None if failure else observation, "unit": "observation",
        "period_start": period_start, "period_end": period_end, "as_of": as_of, "retrieved_at": retrieved_at, "freshness_state": freshness, "collection_status": collection,
        "source_reference": observation["source_reference"], "contract_version": _text(record.get("contract_version", CONTRACT_VERSION), "contract_version"), "entity_refs": entity_refs, "topic_refs": [topic_id],
        "supersedes_evidence_id": record.get("supersedes_evidence_id"), "supersedes_revision": record.get("supersedes_revision"), "created_at": str(record.get("created_at") or retrieved_at),
        "sample_id": sample_id, "sample_version": sample_version, "sample_revision": sample_revision, "sample_hash": observation["sample_hash"], "observation": observation,
    }


def normalize_workduo_records(records: Iterable[Mapping[str, Any]], registry: Mapping[str, Any], *, sample_definition: Optional[Mapping[str, Any]] = None) -> list[dict[str, Any]]:
    return [normalize_workduo_observation(row, registry, sample_definition=sample_definition) for row in records]


# Short aliases kept for adapter callers that use the source name as the verb.
normalize_workduo = normalize_workduo_observation
normalize_sample = normalize_sample_definition


def collect_workduo(requests: Iterable[Mapping[str, Any]], *, transport: Any = None, registry: Mapping[str, Any], sample_definition: Mapping[str, Any], max_observations: int = 100) -> list[dict[str, Any]]:
    """Collect through an injected offline transport only; enforce a hard bound."""
    if transport is None or not hasattr(transport, "observe"):
        raise WorkduoInputError("TRANSPORT_REQUIRED", "WP8 collection requires an injected offline transport")
    output: list[dict[str, Any]] = []
    for request in list(requests)[:max_observations]:
        try:
            raw = transport.observe(request)
            output.append(normalize_workduo_observation(raw, registry, sample_definition=sample_definition))
        except Exception as exc:
            output.append(normalize_workduo_observation({**dict(request), "sample_id": sample_definition["sample_id"], "sample_version": sample_definition["sample_version"], "sample_revision": sample_definition.get("revision", 1), "prompt_ref": request.get("prompt_ref"), "topic_id": request.get("topic_id"), "freshness_state": "FAILED", "collection_status": "FAILED", "mention_state": "NOT_AVAILABLE", "citation_state": "NOT_AVAILABLE", "period_start": request.get("period_start"), "period_end": request.get("period_end"), "as_of": request.get("as_of"), "retrieved_at": request.get("retrieved_at"), "provider_error_code": type(exc).__name__}, registry, sample_definition=sample_definition))
    return output


__all__ = ["SOURCE", "SOURCE_CLASS", "SOURCE_ROLE", "CONTRACT_VERSION", "WorkduoInputError", "normalize_sample_definition", "normalize_sample", "normalize_workduo_observation", "normalize_workduo", "normalize_workduo_records", "collect_workduo"]
