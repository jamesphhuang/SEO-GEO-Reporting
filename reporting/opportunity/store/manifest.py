"""Append-only local run manifests for deterministic offline replays."""

from __future__ import annotations

import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .errors import ImmutableStoreError
from .serialization import canonical_line, content_hash


class RunManifestStore:
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "run_manifest.jsonl"
        self._records: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ImmutableStoreError("STORE_CORRUPTION", f"invalid run manifest JSON at line {number}") from exc
                run_id = record.get("run_id")
                if not isinstance(run_id, str) or not run_id:
                    raise ImmutableStoreError("STORE_CORRUPTION", "run manifest row has no run_id")
                if run_id in self._records and self._records[run_id].get("content_hash") != record.get("content_hash"):
                    raise ImmutableStoreError("STORE_CORRUPTION", "conflicting run manifest revision")
                self._records[run_id] = record

    def append(self, manifest: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(manifest, Mapping) or not isinstance(manifest.get("run_id"), str) or not manifest["run_id"]:
            raise ImmutableStoreError("INVALID_RUN_MANIFEST", "run_id is required", "run_id")
        record = copy.deepcopy(dict(manifest))
        record.setdefault("record_type", "RUN_MANIFEST")
        record.setdefault("schema_version", "opportunity-store-run.v1")
        record.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        record["content_hash"] = content_hash(record)
        existing = self._records.get(record["run_id"])
        if existing is not None:
            if existing.get("content_hash") == record["content_hash"]:
                return {**copy.deepcopy(existing), "idempotent": True}
            raise ImmutableStoreError("REVISION_CONFLICT", "run_id already has a different manifest")
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(canonical_line(record))
            handle.flush()
            os.fsync(handle.fileno())
        self._records[record["run_id"]] = copy.deepcopy(record)
        return copy.deepcopy(record)

    def get(self, run_id: str) -> dict[str, Any] | None:
        return copy.deepcopy(self._records.get(run_id))

    def list(self) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._records[key]) for key in sorted(self._records)]


__all__ = ["RunManifestStore"]
