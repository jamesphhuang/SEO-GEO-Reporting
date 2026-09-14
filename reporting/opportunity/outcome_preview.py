"""Deterministic read-only projection for WP11 outcome checkpoints."""

from __future__ import annotations

import copy
import hashlib
import html
import json
from datetime import date, datetime
from typing import Any, Mapping, Optional, Sequence

from .outcomes import CHECKPOINTS, OUTCOME_STATES
from .store.serialization import canonical_json


RENDERER_VERSION = "outcome-preview-1"


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _record(value: Any) -> Optional[dict[str, Any]]:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if isinstance(value, Mapping) and isinstance(value.get("outcome"), Mapping):
        value = value["outcome"]
    return copy.deepcopy(dict(value)) if isinstance(value, Mapping) else None


def outcome_preview(outcomes: Mapping[str, Any] | Sequence[Mapping[str, Any]] | Any, *, dataset_id: str = "WP11_SYNTHETIC_UAT") -> dict[str, Any]:
    """Return a stable JSON-like view; this function never writes a file."""
    if isinstance(outcomes, Mapping) and any(key in outcomes for key in ("outcome_track_id", "record_type", "outcome_state")):
        rows = [_record(outcomes)]
    elif isinstance(outcomes, Mapping):
        rows = [_record(item) for item in outcomes.values()]
    elif isinstance(outcomes, (list, tuple)):
        rows = [_record(item) for item in outcomes]
    else:
        rows = [_record(outcomes)]
    rows = [row for row in rows if row is not None]
    rows.sort(key=lambda row: (str(row.get("candidate_id", "")), str(row.get("checkpoint", "")), int(row.get("revision", 0))))
    checkpoints: dict[str, list[dict[str, Any]]] = {checkpoint: [] for checkpoint in ("30D", "60D", "90D")}
    for row in rows:
        checkpoint = str(row.get("checkpoint", "")).upper()
        if checkpoint in checkpoints:
            checkpoints[checkpoint].append({
                "outcome_track_id": row.get("outcome_track_id"),
                "revision": row.get("revision"),
                "candidate_id": row.get("candidate_id"),
                "candidate_revision": row.get("candidate_revision"),
                "candidate_hash": row.get("candidate_hash"),
                "review_id": row.get("review_id"),
                "review_revision": row.get("review_revision"),
                "bridge_id": row.get("bridge_id"),
                "implementation_event_id": row.get("implementation_event_id"),
                "completed_at": row.get("completed_at"),
                "checkpoint_due_date": row.get("checkpoint_due_date"),
                "tracking_status": row.get("tracking_status"),
                "outcome_state": row.get("outcome_state"),
                "comparisons": copy.deepcopy(row.get("comparisons", [])),
                "missing_metrics": sorted(row.get("missing_metrics", [])),
                "conflicts": sorted(row.get("conflicts", [])),
                "limitations": list(row.get("limitations", [])),
                "evidence_refs": copy.deepcopy(row.get("evidence_refs", [])),
                "causal_claim": False,
            })
    payload: dict[str, Any] = {"record_type": "OUTCOME_PREVIEW", "contract_version": "outcome_tracking.v1.proposal", "renderer_version": RENDERER_VERSION, "dataset_id": dataset_id, "checkpoints": checkpoints, "production_mutation": 0}
    payload["semantic_hash"] = _hash(payload)
    return payload


def render_outcome_preview(value: Mapping[str, Any] | Sequence[Mapping[str, Any]] | Any, *, format: str = "json", dataset_id: str = "WP11_SYNTHETIC_UAT") -> str:
    projection = outcome_preview(value, dataset_id=dataset_id)
    if format.lower() == "json":
        return json.dumps(projection, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if format.lower() not in {"markdown", "md"}:
        raise ValueError("format must be json or markdown")
    lines = [f"# Outcome tracking preview ({html.escape(dataset_id)})", "", "Offline observation projection; it contains no causal or production decision.", ""]
    for checkpoint in ("30D", "60D", "90D"):
        lines.append(f"## {checkpoint}")
        rows = projection["checkpoints"][checkpoint]
        if not rows:
            lines.extend(["", "No checkpoint record.", ""])
            continue
        lines.extend(["", "| Candidate | State | Tracking | Missing | Conflicts |", "| --- | --- | --- | --- | --- |"])
        for row in rows:
            lines.append("| {candidate} | {state} | {tracking} | {missing} | {conflicts} |".format(candidate=html.escape(str(row.get("candidate_id", ""))), state=html.escape(str(row.get("outcome_state", ""))), tracking=html.escape(str(row.get("tracking_status", ""))), missing=html.escape(", ".join(row.get("missing_metrics", [])) or "—"), conflicts=html.escape(", ".join(row.get("conflicts", [])) or "—")))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def checkpoint_preview(value: Any, *, dataset_id: str = "WP11_SYNTHETIC_UAT") -> dict[str, Any]:
    """Alias used by report projections and downstream handoff code."""
    return outcome_preview(value, dataset_id=dataset_id)


project_outcome_preview = outcome_preview
render_checkpoint_preview = render_outcome_preview


__all__ = ["RENDERER_VERSION", "checkpoint_preview", "outcome_preview", "project_outcome_preview", "render_checkpoint_preview", "render_outcome_preview"]
