"""Offline append-only Candidate Store with exact evidence pinning."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from .evidence import EvidenceStore
from .store.errors import ImmutableStoreError
from .store.registry import RegistryLookup
from .store.serialization import SerializationError, canonical_line, content_hash


def _prepare(record: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise ImmutableStoreError("INVALID_RECORD", "record must be a mapping")
    value = copy.deepcopy(dict(record))
    value.setdefault("created_at", datetime.now(timezone.utc).isoformat())
    try:
        calculated = content_hash(value)
    except SerializationError as exc:
        raise ImmutableStoreError("NONFINITE_NUMBER", "record contains a non-finite number") from exc
    if value.get("content_hash") is not None and value["content_hash"] != calculated:
        raise ImmutableStoreError("HASH_MISMATCH", "content_hash does not match semantic fields", "content_hash")
    value["content_hash"] = calculated
    return value


class CandidateStore:
    def __init__(self, root: str | os.PathLike[str], *, evidence_store: EvidenceStore, registry: Optional[Mapping[str, Any]] = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "candidates.jsonl"
        self.evidence_store = evidence_store
        self.registry = RegistryLookup(registry) if registry is not None else evidence_store.registry
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
                key = (prepared.get("candidate_id", ""), prepared.get("revision", 0))
                if key in self._records:
                    raise ImmutableStoreError("STORE_CORRUPTION", "duplicate revision in candidate log")
                self._records[key] = prepared

    def _validate(self, record: Mapping[str, Any]) -> None:
        required = ("record_type", "candidate_id", "revision", "topic_ref", "evidence_refs", "status", "review_state", "content_hash", "created_at")
        for field in required:
            if field not in record:
                raise ImmutableStoreError("MISSING_FIELD", f"required field is missing: {field}", field)
        if record["record_type"] != "CANDIDATE":
            raise ImmutableStoreError("INVALID_RECORD_TYPE", "record_type must be CANDIDATE", "record_type")
        if not isinstance(record["candidate_id"], str) or not record["candidate_id"]:
            raise ImmutableStoreError("INVALID_ID", "candidate_id must be non-empty text", "candidate_id")
        if not isinstance(record["revision"], int) or isinstance(record["revision"], bool) or record["revision"] < 1:
            raise ImmutableStoreError("INVALID_REVISION", "revision must be a positive integer", "revision")
        topic = record["topic_ref"]
        if not isinstance(topic, Mapping) or topic.get("entity_type") != "TOPIC" or not isinstance(topic.get("entity_id"), str):
            raise ImmutableStoreError("INVALID_ENTITY_REF", "topic_ref must identify a TOPIC", "topic_ref")
        self.registry.require("TOPIC", topic["entity_id"], "topic_ref")
        refs = record["evidence_refs"]
        if not isinstance(refs, list) or not refs:
            raise ImmutableStoreError("MISSING_EVIDENCE_REFERENCE", "candidate must pin at least one evidence revision", "evidence_refs")
        seen: set[tuple[str, int]] = set()
        for index, ref in enumerate(refs):
            if not isinstance(ref, Mapping) or not isinstance(ref.get("evidence_id"), str) or not isinstance(ref.get("revision"), int) or not isinstance(ref.get("content_hash"), str):
                raise ImmutableStoreError("MISSING_EVIDENCE_REVISION", "each evidence ref must include id, revision and content_hash", f"evidence_refs[{index}]")
            key = (ref["evidence_id"], ref["revision"])
            if key in seen:
                raise ImmutableStoreError("DUPLICATE_EVIDENCE_REFERENCE", "evidence refs must be unique", f"evidence_refs[{index}]")
            seen.add(key)
            self.evidence_store.resolve_reference(*key, ref["content_hash"])
        if not isinstance(record["created_at"], str):
            raise ImmutableStoreError("INVALID_DATETIME", "created_at must be ISO-8601 text", "created_at")
        try:
            parsed = datetime.fromisoformat(record["created_at"].replace("Z", "+00:00"))
        except ValueError as exc:
            raise ImmutableStoreError("INVALID_DATETIME", "created_at is not ISO-8601", "created_at") from exc
        if parsed.tzinfo is None:
            raise ImmutableStoreError("NAIVE_DATETIME", "created_at must include a timezone", "created_at")

    def append_candidate(self, record: Mapping[str, Any]) -> dict[str, Any]:
        prepared = _prepare(record)
        self._validate(prepared)
        key = (prepared["candidate_id"], prepared["revision"])
        existing = self._records.get(key)
        if existing is not None:
            if existing["content_hash"] == prepared["content_hash"]:
                return {**copy.deepcopy(existing), "idempotent": True}
            raise ImmutableStoreError("REVISION_CONFLICT", "same logical revision has a different content hash")
        revisions = sorted(revision for candidate_id, revision in self._records if candidate_id == prepared["candidate_id"])
        expected = (revisions[-1] + 1) if revisions else 1
        if prepared["revision"] != expected:
            raise ImmutableStoreError("REVISION_GAP", "revision must append exactly after the current tip", "revision")
        if prepared["revision"] == 1:
            if prepared.get("supersedes_candidate_id") is not None or prepared.get("supersedes_revision") is not None:
                raise ImmutableStoreError("INVALID_SUPERSEDES", "revision 1 cannot supersede another revision")
        elif prepared.get("supersedes_candidate_id") != prepared["candidate_id"] or prepared.get("supersedes_revision") != prepared["revision"] - 1:
            raise ImmutableStoreError("INVALID_SUPERSEDES", "candidate revision must supersede the immediately prior revision")
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(canonical_line(prepared))
            handle.flush()
            os.fsync(handle.fileno())
        self._records[key] = copy.deepcopy(prepared)
        return copy.deepcopy(prepared)

    def get_candidate(self, candidate_id: str, revision: Optional[int] = None) -> Optional[dict[str, Any]]:
        if revision is None:
            revisions = [r for cid, r in self._records if cid == candidate_id]
            if not revisions:
                return None
            revision = max(revisions)
        record = self._records.get((candidate_id, revision))
        return copy.deepcopy(record) if record is not None else None

    def history(self, candidate_id: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._records[(candidate_id, revision)]) for revision in sorted(r for cid, r in self._records if cid == candidate_id)]

    def list_candidates(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._records[key]) for key in sorted(self._records)]

    def resolve_candidate_evidence(self, candidate_id: str, revision: Optional[int] = None) -> list[dict[str, Any]]:
        candidate = self.get_candidate(candidate_id, revision)
        if candidate is None:
            raise ImmutableStoreError("MISSING_CANDIDATE", "candidate revision does not exist")
        return [self.evidence_store.resolve_reference(ref["evidence_id"], ref["revision"], ref["content_hash"]) for ref in candidate["evidence_refs"]]


__all__ = ["CandidateStore"]
