"""Stable, offline preview rendering for GA4 quality diagnostics."""

from __future__ import annotations

import json
from typing import Any, Mapping


def diagnostic_preview(value: Mapping[str, Any], *, format: str = "json") -> str:
    """Render a deterministic diagnostic preview without changing its record."""

    if not isinstance(value, Mapping):
        raise TypeError("diagnostic preview requires a mapping")
    if format == "json":
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if format != "markdown":
        raise ValueError("format must be json or markdown")
    signals = value.get("signals") or {}
    lines = [
        "# GA4 quality diagnostic preview",
        "",
        f"- Candidate: `{value.get('candidate_id')}` revision `{value.get('candidate_revision')}`",
        f"- Topic: `{value.get('topic_cluster_id')}`",
        f"- URL: `{value.get('target_url')}`",
        f"- Status: **{value.get('diagnostic_status')}** (confidence: {value.get('diagnostic_confidence')})",
        f"- Traffic: `{signals.get('traffic_signal')}`; engagement: `{signals.get('engagement_signal')}`",
        f"- CTA: `{signals.get('cta_signal')}` (event count: {signals.get('cta_event_count')})",
        f"- WP5 score preserved: `{value.get('wp5_score')}`; conversion boundary: `{value.get('conversion_boundary')}`",
    ]
    conflicts = value.get("conflicts") or []
    missing = value.get("missing_evidence") or []
    if conflicts:
        lines.extend(["", "Conflicts:", *[f"- `{item}`" for item in conflicts]])
    if missing:
        lines.extend(["", "Missing evidence:", *[f"- `{item}`" for item in missing]])
    return "\n".join(lines)


__all__ = ["diagnostic_preview"]
