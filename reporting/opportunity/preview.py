"""Deterministic human-readable previews for offline opportunity results."""

from __future__ import annotations

import json
from typing import Any, Mapping


def candidate_preview(result: Any, *, format: str = "json") -> str:
    """Render a stable JSON or Markdown preview without writing any artifact."""

    payload = result.as_dict() if hasattr(result, "as_dict") else result
    if format == "json":
        return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if format != "markdown":
        raise ValueError("format must be json or markdown")
    candidate = payload.get("candidate") if isinstance(payload, Mapping) else None
    decision = payload.get("decision") if isinstance(payload, Mapping) else None
    if not candidate and not decision:
        return "# SEO opportunity preview\n\nNo candidate emitted."
    source = candidate or decision
    refs = source.get("evidence_refs", [])
    ref_text = ", ".join(
        str(item.get("evidence_id")) if isinstance(item, Mapping) else str(item)
        for item in refs
    ) or "none"
    lines = [
        "# SEO opportunity preview",
        "",
        f"- ID: `{source.get('opportunity_id') or source.get('candidate_id', 'N/A')}`",
        f"- Type: `{source.get('opportunity_type', 'N/A')}`",
        f"- Action: `{source.get('recommended_action', 'N/A')}`",
        f"- Status: `{source.get('status', 'N/A')}`",
        f"- Confidence: `{source.get('confidence', 'N/A')}`",
        f"- Evidence: `{ref_text}`",
    ]
    if payload.get("policy_gaps"):
        lines.extend(["", "Policy gaps: " + ", ".join(f"`{item}`" for item in payload["policy_gaps"])])
    return "\n".join(lines) + "\n"


__all__ = ["candidate_preview"]
