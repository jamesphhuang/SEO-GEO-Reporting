"""Stable JSON/Markdown preview for GEO fixed-sample diagnostics."""

from __future__ import annotations

import json
from typing import Any, Mapping


def geo_diagnostic_preview(value: Any, *, format: str = "json") -> str:
    payload = value.as_dict() if hasattr(value, "as_dict") else value
    record = payload.get("diagnostic", payload) if isinstance(payload, Mapping) else payload
    if not isinstance(record, Mapping): raise TypeError("GEO preview requires a mapping")
    if format == "json": return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if format != "markdown": raise ValueError("format must be json or markdown")
    comparison = record.get("comparability") or {}
    lines = [
        "# GEO fixed sample diagnostic preview", "",
        f"- Candidate: `{record.get('candidate_id')}` revision `{record.get('candidate_revision')}`",
        f"- Topic: `{record.get('topic_cluster_id')}`; candidate type: `{record.get('opportunity_type', 'EXISTING')}`",
        f"- WP5 score/confidence: `{record.get('wp5_score')}` / `{record.get('wp5_confidence')}`",
        f"- Sample: `{record.get('sample_id')}` `{record.get('sample_version')}`; prompts: `{record.get('prompt_count', 0)}`; platform/model: `{record.get('platform_scope')}` / `{record.get('model_scope')}`",
        f"- Status: **{record.get('diagnostic_status')}**; owned visibility: `{record.get('owned_visibility')}`",
        f"- Mention: `{record.get('mention_state')}`; citation: `{record.get('citation_state')}`",
        f"- Comparability: `{comparison.get('status')}`; competitors: `{', '.join(record.get('competitor_presence') or []) or 'none'}`",
        f"- SERP: `{(record.get('serp_validation') or {}).get('validation_status', 'NOT_PROVIDED')}`; GA4: `{(record.get('ga4_diagnostic') or {}).get('diagnostic_status', 'NOT_PROVIDED')}`",
    ]
    if record.get("conflicts"): lines.extend(["", "Conflicts:", *[f"- `{item}`" for item in record["conflicts"]]])
    if record.get("missing_evidence"): lines.extend(["", "Missing evidence:", *[f"- `{item}`" for item in record["missing_evidence"]]])
    if record.get("capability_gaps"): lines.extend(["", "Capability gaps:", *[f"- `{item}`" for item in record["capability_gaps"]]])
    return "\n".join(lines) + "\n"


__all__ = ["geo_diagnostic_preview"]
