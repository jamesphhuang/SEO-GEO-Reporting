"""Offline append-only Evidence Store.

The store is deliberately local and boring: one canonical JSON object per line,
opened in append mode. A revision is a new record; no method rewrites a prior
line or silently resolves a candidate to the latest evidence.
"""

from __future__ import annotations

import copy
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from .store.errors import ImmutableStoreError
from .store.registry import RegistryLookup
from .store.serialization import SerializationError, canonical_line, content_hash

EVIDENCE_RECORD_TYPE = "EVIDENCE"
FRESHNESS_STATES = frozenset({"READY", "PARTIAL", "STALE", "FAILED", "NOT_AVAILABLE"})
SOURCE_CLASSES = {
    "AHREFS": "THIRD_PARTY_ESTIMATE",
    "GSC": "FIRST_PARTY_SEARCH_ACTUAL",
    "GA4": "FIRST_PARTY_BEHAVIOR_DIAGNOSTIC",
    "SF": "TECHNICAL_CRAWL_EVIDENCE",
    "SERP": "LIVE_SERP_SNAPSHOT",
    "WORKDUO": "MONITORED_GEO_SAMPLE",
    "CRUX": "FIELD_UX_EVIDENCE",
    "BUSINESS": "FORMAL_BUSINESS_ACTUAL",
}


def _parse_date(value: Any, field: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ImmutableStoreError("INVALID_DATE", "date must be ISO-8601 text", field)
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ImmutableStoreError("INVALID_DATE", "date is not ISO-8601", field) from exc


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ImmutableStoreError("INVALID_DATETIME", "timestamp must be ISO-8601 text", field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ImmutableStoreError("INVALID_DATETIME", "timestamp is not ISO-8601", field) from exc
    if parsed.tzinfo is None:
        raise ImmutableStoreError("NAIVE_DATETIME", "timestamp must include a timezone", field)
    return parsed


def _prepare(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ImmutableStoreError("INVALID_RECORD", "record must be a mapping")
    value = copy.deepcopy(dict(record))
    value.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    supplied = value.get("content_hash")
    try:
        calculated = content_hash(value)
    except SerializationError as exc:
        raise ImmutableStoreError("NONFINITE_NUMBER", "record contains a non-finite number") from exc
    if supplied is not None and supplied != calculated:
        raise ImmutableStoreError("HASH_MISMATCH", "content_hash does not match semantic fields", "content_hash")
    value["content_hash"] = calculated
    return value


class EvidenceStore:
    """A revisioned, append-only evidence log with deterministic lookups."""

    def __init__(self, root: str | os.PathLike[str], *, registry: Optional[Mapping[str, Any]] = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "evidence.jsonl"
        self.registry = RegistryLookup(registry)
        self._records: dict[tuple[str, int], dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ImmutableStoreError("STORE_CORRUPTION", f"invalid JSON at line {line_number}") from exc
                prepared = _prepare(record)
                self._validate(prepared)
                key = (prepared.get("evidence_id", ""), prepared.get("revision", 0))
                if key in self._records:
                    raise ImmutableStoreError("STORE_CORRUPTION", "duplicate revision in evidence log")
                self._records[key] = prepared

    def _validate(self, record: Mapping[str, Any]) -> None:
        required = ("record_type", "evidence_id", "revision", "source", "source_class", "metric", "value", "unit", "period_start", "period_end", "as_of", "retrieved_at", "freshness_state", "collection_status", "source_reference", "contract_version", "content_hash")
        for field in required:
            if field not in record:
                raise ImmutableStoreError("MISSING_FIELD", f"required field is missing: {field}", field)
        if record["record_type"] != EVIDENCE_RECORD_TYPE:
            raise ImmutableStoreError("INVALID_RECORD_TYPE", "record_type must be EVIDENCE", "record_type")
        if not isinstance(record["evidence_id"], str) or not record["evidence_id"]:
            raise ImmutableStoreError("INVALID_ID", "evidence_id must be non-empty text", "evidence_id")
        revision = record["revision"]
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ImmutableStoreError("INVALID_REVISION", "revision must be a positive integer", "revision")
        source = record["source"]
        if source not in SOURCE_CLASSES or record["source_class"] != SOURCE_CLASSES[source]:
            raise ImmutableStoreError("INVALID_SOURCE_SEMANTICS", "source_class does not match source role", "source_class")
        if record["freshness_state"] not in FRESHNESS_STATES:
            raise ImmutableStoreError("INVALID_FRESHNESS_STATE", "freshness_state is not supported", "freshness_state")
        if record["value"] is not None and not isinstance(record["value"], (str, int, float, bool, list, dict)):
            raise ImmutableStoreError("INVALID_VALUE", "value must be JSON scalar/object/array or null", "value")
        if record["freshness_state"] in {"FAILED", "NOT_AVAILABLE"} and record["value"] is not None:
            raise ImmutableStoreError("INVALID_VALUE", "failed or unavailable evidence must preserve a null value", "value")
        start = _parse_date(record["period_start"], "period_start")
        end = _parse_date(record["period_end"], "period_end")
        as_of = _parse_date(record["as_of"], "as_of")
        retrieved = _parse_datetime(record["retrieved_at"], "retrieved_at")
        if start > end or end > as_of or as_of > retrieved.date():
            raise ImmutableStoreError("INVALID_DATE_ORDER", "period and retrieval dates are out of order")
        _parse_datetime(record["created_at"], "created_at")
        if not isinstance(record["source_reference"], str) or not record["source_reference"]:
            raise ImmutableStoreError("MISSING_PROVENANCE", "source_reference is required", "source_reference")
        refs = record.get("entity_refs", [])
        if not isinstance(refs, list):
            raise ImmutableStoreError("INVALID_ENTITY_REFS", "entity_refs must be an array", "entity_refs")
        seen: set[tuple[str, str]] = set()
        for index, ref in enumerate(refs):
            if not isinstance(ref, Mapping) or not isinstance(ref.get("entity_type"), str) or not isinstance(ref.get("entity_id"), str):
                raise ImmutableStoreError("INVALID_ENTITY_REF", "entity reference must contain entity_type and entity_id", f"entity_refs[{index}]")
            key = (ref["entity_type"], ref["entity_id"])
            if key in seen:
                raise ImmutableStoreError("DUPLICATE_ENTITY_REF", "entity_refs must be unique", f"entity_refs[{index}]")
            seen.add(key)
            self.registry.require(*key, f"entity_refs[{index}]")
        if "topic_refs" in record:
            for index, topic_id in enumerate(record["topic_refs"]):
                self.registry.require("TOPIC", topic_id, f"topic_refs[{index}]")
        if record.get("supersedes_evidence_id") is not None and record.get("supersedes_evidence_id") != record["evidence_id"]:
            raise ImmutableStoreError("INVALID_SUPERSEDES", "supersedes_evidence_id must be the same logical evidence id", "supersedes_evidence_id")

    def append_evidence(self, record: Mapping[str, Any]) -> dict[str, Any]:
        prepared = _prepare(record)
        self._validate(prepared)
        key = (prepared["evidence_id"], prepared["revision"])
        existing = self._records.get(key)
        if existing is not None:
            if existing["content_hash"] == prepared["content_hash"]:
                return {**copy.deepcopy(existing), "idempotent": True}
            raise ImmutableStoreError("REVISION_CONFLICT", "same logical revision has a different content hash")
        revisions = sorted(revision for evidence_id, revision in self._records if evidence_id == prepared["evidence_id"])
        expected = (revisions[-1] + 1) if revisions else 1
        if prepared["revision"] != expected:
            raise ImmutableStoreError("REVISION_GAP", "revision must append exactly after the current tip", "revision")
        if prepared["revision"] == 1:
            if prepared.get("supersedes_evidence_id") is not None or prepared.get("supersedes_revision") is not None:
                raise ImmutableStoreError("INVALID_SUPERSEDES", "revision 1 cannot supersede another revision")
        elif prepared.get("supersedes_evidence_id") != prepared["evidence_id"] or prepared.get("supersedes_revision") != prepared["revision"] - 1:
            raise ImmutableStoreError("INVALID_SUPERSEDES", "a revision must supersede the immediately prior revision")
        line = canonical_line(prepared)
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(line)
            handle.flush()
            os.fsync(handle.fileno())
        self._records[key] = copy.deepcopy(prepared)
        return copy.deepcopy(prepared)

    def get_evidence(self, evidence_id: str, revision: Optional[int] = None) -> Optional[dict[str, Any]]:
        if revision is None:
            revisions = [r for eid, r in self._records if eid == evidence_id]
            if not revisions:
                return None
            revision = max(revisions)
        record = self._records.get((evidence_id, revision))
        return copy.deepcopy(record) if record is not None else None

    def history(self, evidence_id: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._records[(evidence_id, revision)]) for revision in sorted(r for eid, r in self._records if eid == evidence_id)]

    def list_evidence(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._records[key]) for key in sorted(self._records)]

    def resolve_reference(self, evidence_id: str, revision: int, expected_hash: str) -> dict[str, Any]:
        record = self.get_evidence(evidence_id, revision)
        if record is None:
            raise ImmutableStoreError("MISSING_EVIDENCE_REVISION", "pinned evidence revision does not exist")
        if record["content_hash"] != expected_hash:
            raise ImmutableStoreError("CANDIDATE_EVIDENCE_DRIFT", "pinned evidence hash does not match stored revision")
        return record


__all__ = ["EvidenceStore", "FRESHNESS_STATES", "SOURCE_CLASSES", "EVIDENCE_RECORD_TYPE"]
