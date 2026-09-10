"""Stable JSON/Markdown preview for SERP validation proposals."""

from __future__ import annotations

import json
from typing import Any, Mapping


def serp_validation_preview(value: Any, *, format: str = "json") -> str:
    payload = value.as_dict() if hasattr(value, "as_dict") else value
    if not isinstance(payload, Mapping):
        raise TypeError("SERP preview requires a mapping")
    record = payload.get("validation", payload)
    if format == "json":
        return json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if format != "markdown":
        raise ValueError("format must be json or markdown")
    query = record.get("validation_query_text") or "(no approved validation query)"
    lines = [
        "# SERP validation preview", "",
        f"- Topic: `{record.get('topic_cluster_id')}`",
        f"- Candidate type: `{record.get('opportunity_type')}`; action: `{record.get('recommended_action')}`",
        f"- WP5 score/confidence: `{record.get('wp5_score')}` / `{record.get('wp5_confidence')}`",
        f"- GA4 diagnostic: `{(record.get('ga4_diagnostic') or {}).get('diagnostic_status', 'NOT_PROVIDED')}`",
        f"- Validation query: `{query}`",
        f"- Status: **{record.get('validation_status')}**; observed intent: `{record.get('observed_intent')}`",
        f"- Page types: `{json.dumps(record.get('page_type_distribution') or {}, ensure_ascii=False, sort_keys=True)}`",
        f"- SHOPLINE presence: `{record.get('owned_presence')}`; competitors: `{', '.join(record.get('competitor_presence') or []) or 'none'}`",
        f"- SERP features: `{json.dumps(record.get('serp_features') or {}, ensure_ascii=False, sort_keys=True)}`",
        f"- Conflicts: `{', '.join(record.get('conflict_reasons') or []) or 'none'}`",
        f"- Freshness: `{', '.join(record.get('missing_evidence') or []) or 'current or not reported'}`",
    ]
    return "\n".join(lines) + "\n"


__all__ = ["serp_validation_preview"]
