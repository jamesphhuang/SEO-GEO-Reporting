"""Offline canonical entity registry primitives for Opportunity Intelligence.

The registry stores identity and explicit mappings only.  Source metrics remain
evidence owned by their adapters; this module never calls a source, infers a
topic, or writes a production destination.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import unquote_plus, urlsplit, urlunsplit

from .proposal_validation import ValidationError, ValidationResult


REGISTRY_VERSION = "canonical-registry.v1"
NORMALIZATION_VERSION = "unicode-nfc-width-casefold-v1"
URL_POLICY_VERSION = "url-sanitization.v1"
MAPPING_VERSION = "mapping.v1"

ENTITY_TYPES = (
    "TOPIC",
    "KEYWORD",
    "QUERY",
    "PROMPT",
    "URL",
    "COMPETITOR",
    "BUSINESS_THEME",
)

ID_FIELDS = {
    "TOPIC": "topic_id",
    "KEYWORD": "keyword_id",
    "QUERY": "query_id",
    "PROMPT": "prompt_id",
    "URL": "url_id",
    "COMPETITOR": "competitor_id",
    "BUSINESS_THEME": "business_theme_id",
}

RELATION_ENDPOINTS = {
    "TOPIC_HAS_KEYWORD": ("TOPIC", "KEYWORD"),
    "TOPIC_HAS_QUERY": ("TOPIC", "QUERY"),
    "TOPIC_HAS_PROMPT": ("TOPIC", "PROMPT"),
    "TOPIC_HAS_URL": ("TOPIC", "URL"),
    "TOPIC_HAS_COMPETITOR": ("TOPIC", "COMPETITOR"),
    "TOPIC_HAS_BUSINESS_THEME": ("TOPIC", "BUSINESS_THEME"),
    "URL_CANONICALIZES_TO": ("URL", "URL"),
    "KEYWORD_ALIASES_KEYWORD": ("KEYWORD", "KEYWORD"),
}

PROVENANCE_METHODS = ("MANUAL", "CURATED", "RULE_BASED", "IMPORTED")
REVIEW_STATES = ("CANDIDATE", "APPROVED", "REJECTED")
MAPPING_CONFIDENCE = ("HIGH", "MEDIUM", "LOW", "UNKNOWN")
TOPIC_STATUSES = ("CANDIDATE", "ACTIVE", "DEPRECATED", "REVIEW_REQUIRED")
BUSINESS_THEMES = (
    "ONLINE_STORE",
    "POS",
    "OMO",
    "CRM",
    "PAYMENTS",
    "LOGISTICS",
    "SOCIAL_COMMERCE",
    "GROUP_BUYING",
    "AI_AUTOMATION",
    "MERCHANT_GROWTH",
    "ENTERPRISE_RETAIL",
    "UNMAPPED",
)

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9._:-]{0,127}$")
_SAFE_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_PII_KEY_RE = re.compile(r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization|bearer|email|phone|mobile|customer)", re.IGNORECASE)
_PII_QUERY_RE = re.compile(r"(?:email|e-mail|phone|tel|mobile|name|customer|lead)", re.IGNORECASE)

_TRACKING_QUERY_NAMES = {
    "gclid",
    "fbclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
}


class RegistryInputError(ValueError):
    """Input normalization failure with a stable machine-readable code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _require_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RegistryInputError("INVALID_NORMALIZED_VALUE", f"{field_name} must be non-empty text")
    return value


def _normalize_width(value: str) -> str:
    chars: list[str] = []
    for char in value:
        codepoint = ord(char)
        if 0xFF01 <= codepoint <= 0xFF5E:
            chars.append(chr(codepoint - 0xFEE0))
        elif codepoint == 0x3000:
            chars.append(" ")
        else:
            chars.append(char)
    return "".join(chars)


def normalize_text(value: str) -> str:
    """Normalize text without language guessing or synonym/繁簡 merging."""

    text = _require_text(value, "text")
    text = unicodedata.normalize("NFC", _normalize_width(text))
    text = " ".join(text.split())
    if not text:
        raise RegistryInputError("INVALID_NORMALIZED_VALUE", "normalized text is empty")
    return text.casefold()


def _normalize_aliases(values: Iterable[str]) -> list[str]:
    aliases = {normalize_text(value) for value in values}
    return sorted(aliases)


def _validate_id(value: str, field_name: str) -> str:
    value = _require_text(value, field_name)
    if not _ID_RE.fullmatch(value):
        raise RegistryInputError("INVALID_NORMALIZED_VALUE", f"{field_name} is not a stable identifier")
    return value


def _stable_id(prefix: str, identity: Mapping[str, Any]) -> str:
    payload = json.dumps(identity, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def normalize_domain(value: str) -> str:
    """Normalize a domain only; never merge www/non-www or parent/child names."""

    candidate = _require_text(value, "domain").strip()
    parsed = urlsplit(candidate if "://" in candidate else f"//{candidate}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RegistryInputError("INVALID_DOMAIN", "domain port is invalid") from exc
    if parsed.username or parsed.password or port is not None:
        raise RegistryInputError("INVALID_DOMAIN", "domain must not contain credentials or a port")
    if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
        raise RegistryInputError("INVALID_DOMAIN", "domain must not contain a path, query, or fragment")
    host = parsed.hostname
    if not host or any(char.isspace() for char in host):
        raise RegistryInputError("INVALID_DOMAIN", "domain host is invalid")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise RegistryInputError("INVALID_DOMAIN", "domain host is not valid IDNA") from exc
    host = host.casefold().rstrip(".")
    if "." not in host or host.startswith(".") or host.endswith("."):
        raise RegistryInputError("INVALID_DOMAIN", "domain must contain a valid host")
    return host


def _query_without_tracking(query: str) -> str:
    kept: list[str] = []
    for part in query.split("&"):
        if not part:
            continue
        key = part.split("=", 1)[0]
        decoded_key = unquote_plus(key).casefold()
        if decoded_key.startswith("utm_") or decoded_key in _TRACKING_QUERY_NAMES:
            continue
        if _PII_QUERY_RE.search(decoded_key):
            raise RegistryInputError("INVALID_URL_IDENTITY", "URL query contains a PII-like parameter")
        kept.append(part)
    return "&".join(kept)


def normalize_url(value: str) -> str:
    """Return a deterministic safe URL identity without live redirect resolution.

    Path case, trailing slash, www/non-www, http/https, and semantic query
    parameters remain distinct unless an explicit future mapping relation says
    otherwise.  Only the versioned tracking allowlist is removed.
    """

    raw = _require_text(value, "url").strip()
    if any(ord(char) < 32 or char.isspace() for char in raw):
        raise RegistryInputError("INVALID_URL_IDENTITY", "URL contains whitespace or control characters")
    parsed = urlsplit(raw)
    scheme = parsed.scheme.casefold()
    if scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise RegistryInputError("INVALID_URL_IDENTITY", "URL must be an http(s) URL without userinfo")
    host = parsed.hostname
    if not host:
        raise RegistryInputError("INVALID_URL_IDENTITY", "URL host is missing")
    try:
        host = host.encode("idna").decode("ascii").casefold().rstrip(".")
        port = parsed.port
    except (UnicodeError, ValueError) as exc:
        raise RegistryInputError("INVALID_URL_IDENTITY", "URL host or port is invalid") from exc
    if not host or host.startswith(".") or host.endswith("."):
        raise RegistryInputError("INVALID_URL_IDENTITY", "URL host is invalid")
    if ":" in host and not host.startswith("["):
        netloc = f"[{host}]"
    else:
        netloc = host
    if port is not None and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        netloc = f"{netloc}:{port}"
    path = parsed.path or "/"
    query = _query_without_tracking(parsed.query)
    return urlunsplit((scheme, netloc, path, query, ""))


def make_topic(
    topic_name: str,
    *,
    topic_id: str | None = None,
    status: str = "CANDIDATE",
    version: str = "1",
    search_intent: str = "UNKNOWN",
    funnel_stage: str = "UNKNOWN",
    business_theme_refs: Sequence[str] = (),
    primary_keyword_ref: str | None = None,
    aliases: Sequence[str] = (),
    created_at: str | None = None,
    updated_at: str | None = None,
    synthetic: bool = True,
) -> dict[str, Any]:
    if status not in TOPIC_STATUSES:
        raise RegistryInputError("INVALID_NORMALIZED_VALUE", "unknown topic status")
    normalized = normalize_text(topic_name)
    topic_id = topic_id or _stable_id("TOPIC", {"normalized_name": normalized, "version": version})
    output: dict[str, Any] = {
        "topic_id": _validate_id(topic_id, "topic_id"),
        "topic_name": topic_name,
        "normalized_name": normalized,
        "status": status,
        "version": _require_text(version, "version"),
        "search_intent": search_intent,
        "funnel_stage": funnel_stage,
        "business_theme_refs": sorted(set(business_theme_refs)),
        "primary_keyword_ref": primary_keyword_ref,
        "aliases": _normalize_aliases(aliases),
        "synthetic": bool(synthetic),
    }
    if created_at is not None:
        output["created_at"] = created_at
    if updated_at is not None:
        output["updated_at"] = updated_at
    return output


def make_keyword(
    text: str,
    *,
    locale: str = "zh-TW",
    country_database: str = "TW",
    keyword_id: str | None = None,
    source_refs: Sequence[str] = (),
    canonical_topic_refs: Sequence[str] = (),
    aliases: Sequence[str] = (),
    synthetic: bool = True,
) -> dict[str, Any]:
    normalized = normalize_text(text)
    identity = {"normalized_text": normalized, "locale": locale, "country_database": country_database, "normalization_version": NORMALIZATION_VERSION}
    return {
        "keyword_id": _validate_id(keyword_id or _stable_id("KW", identity), "keyword_id"),
        "text": text,
        "normalized_text": normalized,
        "locale": locale,
        "country_database": country_database,
        "source_refs": sorted(set(source_refs)),
        "canonical_topic_refs": sorted(set(canonical_topic_refs)),
        "aliases": _normalize_aliases(aliases),
        "normalization_version": NORMALIZATION_VERSION,
        "synthetic": bool(synthetic),
    }


def make_query(
    text: str,
    *,
    locale: str = "zh-TW",
    country_database: str = "TW",
    query_id: str | None = None,
    source_refs: Sequence[str] = (),
    canonical_topic_refs: Sequence[str] = (),
    synthetic: bool = True,
) -> dict[str, Any]:
    normalized = normalize_text(text)
    identity = {"normalized_text": normalized, "locale": locale, "country_database": country_database, "normalization_version": NORMALIZATION_VERSION}
    return {
        "query_id": _validate_id(query_id or _stable_id("QUERY", identity), "query_id"),
        "text": text,
        "normalized_text": normalized,
        "locale": locale,
        "country_database": country_database,
        "source_refs": sorted(set(source_refs)),
        "canonical_topic_refs": sorted(set(canonical_topic_refs)),
        "normalization_version": NORMALIZATION_VERSION,
        "synthetic": bool(synthetic),
    }


def make_prompt(
    prompt_text: str,
    *,
    project_id: str,
    provider_query_id: str,
    prompt_version: str,
    region: str,
    locale: str = "zh-TW",
    platform: str = "synthetic",
    source: str = "WORKDUO",
    prompt_id: str | None = None,
    canonical_topic_refs: Sequence[str] = (),
    synthetic: bool = True,
) -> dict[str, Any]:
    normalized = normalize_text(prompt_text)
    identity = {
        "project_id": project_id,
        "provider_query_id": provider_query_id,
        "prompt_version": prompt_version,
        "region": region,
        "locale": locale,
        "normalization_version": NORMALIZATION_VERSION,
    }
    return {
        "prompt_id": _validate_id(prompt_id or _stable_id("PROMPT", identity), "prompt_id"),
        "prompt_text": prompt_text,
        "normalized_text": normalized,
        "project_id": _require_text(project_id, "project_id"),
        "provider_query_id": _require_text(provider_query_id, "provider_query_id"),
        "prompt_version": _require_text(prompt_version, "prompt_version"),
        "region": _require_text(region, "region"),
        "locale": _require_text(locale, "locale"),
        "platform": _require_text(platform, "platform"),
        "source": _require_text(source, "source"),
        "canonical_topic_refs": sorted(set(canonical_topic_refs)),
        "normalization_version": NORMALIZATION_VERSION,
        "synthetic": bool(synthetic),
    }


def make_url(
    observed_url: str,
    *,
    url_id: str | None = None,
    source_refs: Sequence[str] = (),
    canonical_topic_refs: Sequence[str] = (),
    synthetic: bool = True,
) -> dict[str, Any]:
    normalized = normalize_url(observed_url)
    return {
        "url_id": _validate_id(url_id or _stable_id("URL", {"normalized_url": normalized, "policy": URL_POLICY_VERSION}), "url_id"),
        "observed_url": observed_url,
        "normalized_url": normalized,
        "source_refs": sorted(set(source_refs)),
        "canonical_topic_refs": sorted(set(canonical_topic_refs)),
        "url_policy_version": URL_POLICY_VERSION,
        "synthetic": bool(synthetic),
    }


def make_competitor(
    display_name: str,
    *,
    domain: str,
    competitor_id: str | None = None,
    aliases: Sequence[str] = (),
    scope: str = "synthetic",
    parent_competitor_ref: str | None = None,
    canonical_topic_refs: Sequence[str] = (),
    synthetic: bool = True,
) -> dict[str, Any]:
    normalized_domain = normalize_domain(domain)
    identity = {"domain": normalized_domain, "scope": scope}
    return {
        "competitor_id": _validate_id(competitor_id or _stable_id("COMP", identity), "competitor_id"),
        "display_name": _require_text(display_name, "display_name"),
        "domain": normalized_domain,
        "aliases": _normalize_aliases(aliases),
        "scope": _require_text(scope, "scope"),
        "parent_competitor_ref": parent_competitor_ref,
        "canonical_topic_refs": sorted(set(canonical_topic_refs)),
        "synthetic": bool(synthetic),
    }


def make_business_theme(
    theme_id: str,
    *,
    display_name: str | None = None,
    business_theme_id: str | None = None,
    aliases: Sequence[str] = (),
    synthetic: bool = True,
) -> dict[str, Any]:
    if theme_id not in BUSINESS_THEMES:
        raise RegistryInputError("INVALID_NORMALIZED_VALUE", "unknown business theme")
    return {
        "business_theme_id": _validate_id(business_theme_id or f"THEME_{theme_id}", "business_theme_id"),
        "theme_id": theme_id,
        "display_name": display_name or theme_id,
        "aliases": _normalize_aliases(aliases),
        "synthetic": bool(synthetic),
    }


def make_relation(
    relation_type: str,
    *,
    source_entity_type: str,
    source_entity_id: str,
    target_entity_type: str,
    target_entity_id: str,
    mapping_method: str = "CURATED",
    mapping_confidence: str = "UNKNOWN",
    review_state: str = "CANDIDATE",
    reviewed_by_id: str | None = None,
    evidence_refs: Sequence[str] = (),
    mapping_version: str = MAPPING_VERSION,
    valid_from: str | None = None,
    valid_to: str | None = None,
    relation_id: str | None = None,
    synthetic: bool = True,
) -> dict[str, Any]:
    if relation_type not in RELATION_ENDPOINTS:
        raise RegistryInputError("INVALID_RELATION_TYPE", "unknown relation type")
    if (source_entity_type, target_entity_type) != RELATION_ENDPOINTS[relation_type]:
        raise RegistryInputError("INVALID_RELATION_TYPE", "relation endpoints do not match relation type")
    if mapping_method not in PROVENANCE_METHODS or mapping_method == "LLM_INFERRED":
        raise RegistryInputError("INVALID_PROVENANCE", "relation provenance is not allowed")
    if mapping_confidence not in MAPPING_CONFIDENCE or review_state not in REVIEW_STATES:
        raise RegistryInputError("INVALID_NORMALIZED_VALUE", "relation review metadata is invalid")
    if review_state in {"APPROVED", "REJECTED"} and not reviewed_by_id:
        raise RegistryInputError("UNAPPROVED_RELATION", "reviewed relation requires opaque reviewer id")
    if review_state == "APPROVED" and mapping_method == "RULE_BASED":
        raise RegistryInputError("UNAPPROVED_RELATION", "rule-based mapping cannot self-approve")
    identity = {
        "relation_type": relation_type,
        "source_entity_type": source_entity_type,
        "source_entity_id": source_entity_id,
        "target_entity_type": target_entity_type,
        "target_entity_id": target_entity_id,
        "mapping_version": mapping_version,
    }
    return {
        "relation_id": _validate_id(relation_id or _stable_id("REL", identity), "relation_id"),
        **identity,
        "mapping_method": mapping_method,
        "mapping_confidence": mapping_confidence,
        "review_state": review_state,
        "reviewed_by_id": reviewed_by_id,
        "evidence_refs": sorted(set(evidence_refs)),
        "valid_from": valid_from,
        "valid_to": valid_to,
        "synthetic": bool(synthetic),
    }


def _entity_id(entity_type: str, entity: Mapping[str, Any]) -> str | None:
    return entity.get(ID_FIELDS.get(entity_type, "")) if isinstance(entity, Mapping) else None


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonicalize(item) for item in value]
    return value


def _strip_runtime_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _strip_runtime_fields(item)
            for key, item in value.items()
            if key not in {"semantic_hash", "created_at", "updated_at"}
        }
    if isinstance(value, list):
        return [_strip_runtime_fields(item) for item in value]
    return value


def _canonical_registry(registry: Mapping[str, Any], *, semantic: bool = False) -> dict[str, Any]:
    value = copy.deepcopy(dict(registry))
    if semantic:
        value = _strip_runtime_fields(value)
    entities = value.get("entities", {})
    if isinstance(entities, Mapping):
        unordered_fields = (
            "aliases",
            "source_refs",
            "canonical_topic_refs",
            "business_theme_refs",
            "evidence_refs",
        )
        for items in entities.values():
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, Mapping):
                        for field_name in unordered_fields:
                            if isinstance(item.get(field_name), list):
                                item[field_name] = sorted(item[field_name])
        value["entities"] = {
            entity_type: sorted(
                (copy.deepcopy(item) for item in items),
                key=lambda item: str(_entity_id(entity_type, item) or ""),
            )
            for entity_type, items in sorted(entities.items())
        }
    if isinstance(value.get("relations"), list):
        for relation in value["relations"]:
            if isinstance(relation, Mapping) and isinstance(relation.get("evidence_refs"), list):
                relation["evidence_refs"] = sorted(relation["evidence_refs"])
        value["relations"] = sorted(value["relations"], key=lambda item: str(item.get("relation_id", "")))
    if isinstance(value.get("metadata"), Mapping) and isinstance(value["metadata"].get("policy_gaps"), list):
        value["metadata"]["policy_gaps"] = sorted(value["metadata"]["policy_gaps"])
    return _canonicalize(value)


def serialize_registry(registry: Mapping[str, Any]) -> str:
    """Serialize registry content deterministically, including metadata hash."""

    return json.dumps(_canonical_registry(registry), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def registry_semantic_hash(registry: Mapping[str, Any]) -> str:
    semantic = _canonical_registry(registry, semantic=True)
    payload = json.dumps(semantic, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_registry(
    entities: Mapping[str, Sequence[Mapping[str, Any]]],
    relations: Sequence[Mapping[str, Any]] = (),
    *,
    registry_id: str = "REGISTRY_SYNTHETIC_V1",
    mapping_version: str = MAPPING_VERSION,
    synthetic: bool = True,
    source: str = "fixture-only",
    policy_gaps: Sequence[str] = (
        "HTTP_HTTPS_EQUIVALENCE_UNRESOLVED",
        "WWW_REDIRECT_EQUIVALENCE_UNRESOLVED",
        "TRAILING_SLASH_EQUIVALENCE_UNRESOLVED",
    ),
) -> dict[str, Any]:
    grouped = {entity_type: [copy.deepcopy(dict(item)) for item in entities.get(entity_type, ())] for entity_type in ENTITY_TYPES}
    registry: dict[str, Any] = {
        "registry_version": REGISTRY_VERSION,
        "normalization_version": NORMALIZATION_VERSION,
        "mapping_version": mapping_version,
        "metadata": {
            "registry_id": _validate_id(registry_id, "registry_id"),
            "id_strategy": "typed-sha256-v1; explicit topic IDs permitted",
            "synthetic": bool(synthetic),
            "source": _require_text(source, "source"),
            "policy_gaps": sorted(set(policy_gaps)),
            "revision_manifest": {
                "revision_id": mapping_version,
                "supersedes_revision": None,
                "change_type": "INITIAL",
            },
        },
        "entities": grouped,
        "relations": [copy.deepcopy(dict(relation)) for relation in relations],
    }
    registry["metadata"]["semantic_hash"] = registry_semantic_hash(registry)
    return registry


def _add_error(errors: list[ValidationError], code: str, field: str, message: str, *, actual: Any = None) -> None:
    errors.append(ValidationError(code=code, field=field, message=message, actual=actual))


def _iter_strings(value: Any, key: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, Mapping):
        for child_key, child_value in value.items():
            yield from _iter_strings(child_value, str(child_key))
    elif isinstance(value, list):
        for child in value:
            yield from _iter_strings(child, key)
    elif isinstance(value, str):
        yield key, value


def validate_registry(registry: Mapping[str, Any]) -> ValidationResult:
    """Validate identity, relation, review, and deterministic reference rules."""

    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []
    if not isinstance(registry, Mapping):
        _add_error(errors, "INVALID_NORMALIZED_VALUE", "$", "registry must be an object")
        return ValidationResult(errors=errors, warnings=warnings)
    if registry.get("registry_version") != REGISTRY_VERSION:
        _add_error(errors, "INVALID_NORMALIZED_VALUE", "registry_version", "unsupported registry version")
    entities = registry.get("entities")
    if not isinstance(entities, Mapping):
        _add_error(errors, "INVALID_NORMALIZED_VALUE", "entities", "entities must be grouped by entity type")
        return ValidationResult(errors=errors, warnings=warnings)
    all_ids: dict[tuple[str, str], Mapping[str, Any]] = {}
    for key in entities:
        if key not in ENTITY_TYPES:
            _add_error(errors, "UNKNOWN_ENTITY_TYPE", f"entities.{key}", "unknown entity type", actual=key)
    for entity_type in ENTITY_TYPES:
        items = entities.get(entity_type, [])
        if not isinstance(items, list):
            _add_error(errors, "INVALID_NORMALIZED_VALUE", f"entities.{entity_type}", "entity collection must be an array")
            continue
        id_field = ID_FIELDS[entity_type]
        seen: dict[str, Mapping[str, Any]] = {}
        for index, entity in enumerate(items):
            field = f"entities.{entity_type}[{index}]"
            if not isinstance(entity, Mapping):
                _add_error(errors, "INVALID_NORMALIZED_VALUE", field, "entity must be an object")
                continue
            entity_id = entity.get(id_field)
            if not isinstance(entity_id, str) or not _ID_RE.fullmatch(entity_id):
                _add_error(errors, "INVALID_NORMALIZED_VALUE", f"{field}.{id_field}", "invalid stable entity id")
                continue
            if entity_id in seen:
                if _canonicalize(seen[entity_id]) == _canonicalize(entity):
                    _add_error(errors, "DUPLICATE_ENTITY_ID", f"{field}.{id_field}", "duplicate entity id", actual=entity_id)
                else:
                    _add_error(errors, "CANONICAL_VALUE_CONFLICT", f"{field}.{id_field}", "same entity id has conflicting canonical values", actual=entity_id)
            else:
                seen[entity_id] = entity
            all_ids[(entity_type, entity_id)] = entity
            if entity.get("synthetic") is not True:
                _add_error(errors, "INVALID_NORMALIZED_VALUE", f"{field}.synthetic", "WP3 fixtures must mark entities synthetic")
            try:
                if entity_type in {"KEYWORD", "QUERY", "PROMPT"} and entity.get("normalized_text") != normalize_text(entity.get("text", entity.get("prompt_text", ""))):
                    _add_error(errors, "INVALID_NORMALIZED_VALUE", f"{field}.normalized_text", "normalized text does not match deterministic policy")
                if entity_type == "URL" and entity.get("normalized_url") != normalize_url(entity.get("observed_url", "")):
                    _add_error(errors, "INVALID_URL_IDENTITY", f"{field}.normalized_url", "normalized URL does not match deterministic policy")
                if entity_type == "COMPETITOR" and entity.get("domain") != normalize_domain(entity.get("domain", "")):
                    _add_error(errors, "INVALID_DOMAIN", f"{field}.domain", "domain is not normalized")
            except RegistryInputError as exc:
                _add_error(errors, exc.code, field, str(exc))
            if entity_type == "BUSINESS_THEME" and entity.get("theme_id") not in BUSINESS_THEMES:
                _add_error(errors, "INVALID_NORMALIZED_VALUE", f"{field}.theme_id", "unknown business theme")
    metadata = registry.get("metadata", {})
    if not isinstance(metadata, Mapping):
        _add_error(errors, "INVALID_NORMALIZED_VALUE", "metadata", "metadata must be an object")
    else:
        for key, value in _iter_strings(registry):
            if _PII_KEY_RE.search(key):
                _add_error(errors, "SENSITIVE_METADATA", key, "sensitive credential or PII field is forbidden")
        policy_gaps = metadata.get("policy_gaps", [])
        if not isinstance(policy_gaps, list) or any(not isinstance(gap, str) or not gap for gap in policy_gaps):
            _add_error(errors, "POLICY_GAP", "metadata.policy_gaps", "policy gaps must be explicit non-empty strings")
        revision_manifest = metadata.get("revision_manifest")
        if not isinstance(revision_manifest, Mapping) or not revision_manifest.get("revision_id"):
            _add_error(errors, "INVALID_NORMALIZED_VALUE", "metadata.revision_manifest", "revision manifest is required")
        elif revision_manifest.get("revision_id") != registry.get("mapping_version"):
            _add_error(errors, "CANONICAL_VALUE_CONFLICT", "metadata.revision_manifest.revision_id", "revision must match mapping_version")
    relations = registry.get("relations", [])
    if not isinstance(relations, list):
        _add_error(errors, "INVALID_NORMALIZED_VALUE", "relations", "relations must be an array")
        return ValidationResult(errors=errors, warnings=warnings)
    relation_ids: set[str] = set()
    for index, relation in enumerate(relations):
        field = f"relations[{index}]"
        if not isinstance(relation, Mapping):
            _add_error(errors, "INVALID_NORMALIZED_VALUE", field, "relation must be an object")
            continue
        relation_id = relation.get("relation_id")
        if not isinstance(relation_id, str) or not _ID_RE.fullmatch(relation_id):
            _add_error(errors, "INVALID_NORMALIZED_VALUE", f"{field}.relation_id", "invalid relation id")
        elif relation_id in relation_ids:
            _add_error(errors, "DUPLICATE_ENTITY_ID", f"{field}.relation_id", "duplicate relation id", actual=relation_id)
        else:
            relation_ids.add(relation_id)
        relation_type = relation.get("relation_type")
        expected = RELATION_ENDPOINTS.get(relation_type)
        if expected is None:
            _add_error(errors, "INVALID_RELATION_TYPE", f"{field}.relation_type", "unknown relation type", actual=relation_type)
            continue
        source_type, target_type = relation.get("source_entity_type"), relation.get("target_entity_type")
        if (source_type, target_type) != expected:
            _add_error(errors, "INVALID_RELATION_TYPE", field, "relation endpoint types do not match relation type")
        for endpoint, endpoint_type in (("source_entity_id", source_type), ("target_entity_id", target_type)):
            endpoint_id = relation.get(endpoint)
            if (endpoint_type, endpoint_id) not in all_ids:
                _add_error(errors, "DANGLING_REFERENCE", f"{field}.{endpoint}", "relation endpoint does not exist", actual=endpoint_id)
        if source_type == target_type and relation.get("source_entity_id") == relation.get("target_entity_id"):
            _add_error(errors, "INVALID_RELATION_TYPE", field, "self relation is not allowed")
        method = relation.get("mapping_method")
        if method not in PROVENANCE_METHODS:
            _add_error(errors, "INVALID_PROVENANCE", f"{field}.mapping_method", "unsupported relation provenance")
        review_state = relation.get("review_state")
        if review_state not in REVIEW_STATES:
            _add_error(errors, "INVALID_NORMALIZED_VALUE", f"{field}.review_state", "unsupported review state")
        if review_state in {"APPROVED", "REJECTED"} and not relation.get("reviewed_by_id"):
            _add_error(errors, "UNAPPROVED_RELATION", f"{field}.reviewed_by_id", "reviewed relation requires opaque reviewer id")
        if review_state == "APPROVED" and method == "RULE_BASED":
            _add_error(errors, "UNAPPROVED_RELATION", field, "rule-based relation cannot self-approve")
        evidence_refs = relation.get("evidence_refs", [])
        if not isinstance(evidence_refs, list) or len(evidence_refs) != len(set(evidence_refs)):
            _add_error(errors, "DUPLICATE_ENTITY_ID", f"{field}.evidence_refs", "evidence references must be unique")
        valid_from, valid_to = relation.get("valid_from"), relation.get("valid_to")
        if valid_from and valid_to and valid_from > valid_to:
            _add_error(errors, "INVALID_NORMALIZED_VALUE", field, "relation validity range is reversed")
    ref_fields = {
        "TOPIC": [("primary_keyword_ref", "KEYWORD"), ("business_theme_refs", "BUSINESS_THEME")],
        "KEYWORD": [("canonical_topic_refs", "TOPIC")],
        "QUERY": [("canonical_topic_refs", "TOPIC")],
        "PROMPT": [("canonical_topic_refs", "TOPIC")],
        "URL": [("canonical_topic_refs", "TOPIC")],
        "COMPETITOR": [("canonical_topic_refs", "TOPIC"), ("parent_competitor_ref", "COMPETITOR")],
    }
    for entity_type, fields in ref_fields.items():
        for index, entity in enumerate(entities.get(entity_type, [])):
            for field_name, target_type in fields:
                refs = entity.get(field_name)
                refs = [refs] if isinstance(refs, str) else refs or []
                for ref in refs:
                    if (target_type, ref) not in all_ids:
                        _add_error(errors, "DANGLING_REFERENCE", f"entities.{entity_type}[{index}].{field_name}", "entity reference does not exist", actual=ref)
    expected_hash = registry_semantic_hash(registry)
    actual_hash = metadata.get("semantic_hash") if isinstance(metadata, Mapping) else None
    if actual_hash is not None and actual_hash != expected_hash:
        _add_error(errors, "CANONICAL_VALUE_CONFLICT", "metadata.semantic_hash", "semantic hash does not match registry content")
    return ValidationResult(errors=errors, warnings=warnings)


__all__ = [
    "BUSINESS_THEMES",
    "ENTITY_TYPES",
    "MAPPING_VERSION",
    "NORMALIZATION_VERSION",
    "REGISTRY_VERSION",
    "RELATION_ENDPOINTS",
    "URL_POLICY_VERSION",
    "RegistryInputError",
    "build_registry",
    "make_business_theme",
    "make_competitor",
    "make_keyword",
    "make_prompt",
    "make_query",
    "make_relation",
    "make_topic",
    "make_url",
    "normalize_domain",
    "normalize_text",
    "normalize_url",
    "registry_semantic_hash",
    "serialize_registry",
    "validate_registry",
]
