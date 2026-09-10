"""Read-only, deterministic opportunity preview projection for WP9.

The projection is deliberately a reporting boundary.  It accepts already pinned
WP4--WP8 records, copies the records, and exposes their states without evaluating
rules, recomputing a score, or writing a production destination.  The renderer
is suitable for a local UAT artifact only.
"""

from __future__ import annotations

import copy
import hashlib
import html
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from .proposal_validation import ValidationError, ValidationResult
from .store.serialization import canonical_json


CONTRACT_VERSION = "opportunity_preview.v1.proposal"
RENDERER_VERSION = "opportunity-preview-1"
PREVIEW_ENVIRONMENT = "UAT"
GROUPS = (
    ("QUICK_WINS", "Quick Wins"),
    ("CONTENT_GAPS", "Content Gaps"),
    ("GEO_GAPS", "GEO Gaps"),
    ("CONTENT_DECAY_TECHNICAL_UNLOCK", "Content Decay / Technical Unlock"),
)
SOURCE_LABELS = {
    "AHREFS": "Ahrefs third-party estimate",
    "GSC": "GSC first-party search actual",
    "GA4": "GA4 behavior diagnostic",
    "SF": "Screaming Frog technical crawl",
    "SERP": "SERP observed snapshot",
    "WORKDUO": "GEO monitored fixed sample",
    "GEO": "GEO monitored fixed sample",
    "BUSINESS": "Business evidence",
}
_FORMULA_PREFIX = re.compile(r"^[=+\-@]")
_MISSING_STATES = frozenset({"MISSING", "NOT_AVAILABLE", "UNKNOWN", "UNRESOLVED"})
_FRESHNESS_STATES = frozenset({"READY", "PARTIAL", "STALE", "FAILED", "NOT_AVAILABLE"})


class PreviewProjectionError(ValueError):
    """Raised when a preview input cannot be safely projected."""

    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


@dataclass(frozen=True)
class OpportunityPreviewInput:
    """Typed convenience wrapper for callers that prefer an input object."""

    candidates: tuple[Mapping[str, Any], ...]
    evidence: Mapping[str, Any] | Sequence[Mapping[str, Any]] = ()
    ga4_diagnostics: Mapping[str, Any] | Sequence[Mapping[str, Any]] = ()
    serp_validations: Mapping[str, Any] | Sequence[Mapping[str, Any]] = ()
    geo_diagnostics: Mapping[str, Any] | Sequence[Mapping[str, Any]] = ()
    uat_dataset_id: str = "WP9_SYNTHETIC_UAT"
    max_candidates: int = 20


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _index_records(records: Mapping[str, Any] | Sequence[Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    if records is None:
        return {}
    if isinstance(records, Mapping):
        # A single diagnostic mapping is accepted as well as an id -> record map.
        if any(key in records for key in ("candidate_id", "diagnostic_id", "validation_id", "evidence_id")):
            records = [records]
        else:
            output: dict[str, dict[str, Any]] = {}
            for key, value in records.items():
                item = _unwrap_record(value)
                if item is not None:
                    output[str(key)] = item
                    for item_key in ("candidate_id", "diagnostic_id", "validation_id", "evidence_id"):
                        if item.get(item_key):
                            output[str(item[item_key])] = item
            return output
    if not isinstance(records, (list, tuple)):
        raise PreviewProjectionError("INVALID_RECORDS", "records must be a mapping or sequence")
    output = {}
    for value in records:
        item = _unwrap_record(value)
        if item is None:
            continue
        for key in ("candidate_id", "diagnostic_id", "validation_id", "evidence_id"):
            if item.get(key):
                output[str(item[key])] = item
    return output


def _unwrap_record(value: Any) -> Optional[dict[str, Any]]:
    """Accept mappings and the result objects exposed by WP6--WP8."""

    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if isinstance(value, Mapping):
        if isinstance(value.get("diagnostic"), Mapping):
            value = value["diagnostic"]
        elif isinstance(value.get("validation"), Mapping):
            value = value["validation"]
        return copy.deepcopy(dict(value))
    return None


def _candidate_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    item = value.get("candidate") if isinstance(value.get("candidate"), Mapping) else value
    if not isinstance(item, Mapping):
        raise PreviewProjectionError("INVALID_CANDIDATE", "candidate must be a mapping")
    result = copy.deepcopy(dict(item))
    candidate_id = result.get("candidate_id") or result.get("opportunity_id")
    revision = result.get("revision", result.get("candidate_revision"))
    if not isinstance(candidate_id, str) or not candidate_id:
        raise PreviewProjectionError("MISSING_CANDIDATE_ID", "candidate_id is required", "candidate_id")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise PreviewProjectionError("INVALID_CANDIDATE_REVISION", "candidate revision must be a positive integer", "revision")
    result["candidate_id"] = candidate_id
    result["revision"] = revision
    refs = result.get("evidence_refs", ())
    if not isinstance(refs, (list, tuple)):
        raise PreviewProjectionError("INVALID_EVIDENCE_REFS", "evidence_refs must be a list", "evidence_refs")
    if not refs:
        raise PreviewProjectionError("MISSING_EVIDENCE_REFERENCE", "candidate must pin at least one evidence revision", "evidence_refs")
    return result


def _pin(value: Any, evidence_index: Mapping[str, Mapping[str, Any]]) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    record: Optional[dict[str, Any]] = None
    if isinstance(value, str):
        record = copy.deepcopy(dict(evidence_index.get(value, {}))) if value in evidence_index else None
        if record:
            value = {"evidence_id": record.get("evidence_id"), "revision": record.get("revision"), "content_hash": record.get("content_hash")}
        else:
            raise PreviewProjectionError("UNRESOLVED_EVIDENCE_PIN", "evidence reference does not resolve exactly", "evidence_refs")
    if not isinstance(value, Mapping):
        raise PreviewProjectionError("INVALID_EVIDENCE_PIN", "evidence ref must be a mapping", "evidence_refs")
    pin = {key: value.get(key) for key in ("evidence_id", "revision", "content_hash")}
    if not isinstance(pin["evidence_id"], str) or not pin["evidence_id"]:
        raise PreviewProjectionError("MISSING_EVIDENCE_ID", "evidence_id is required", "evidence_refs")
    if not isinstance(pin["revision"], int) or isinstance(pin["revision"], bool) or pin["revision"] < 1:
        raise PreviewProjectionError("INVALID_EVIDENCE_REVISION", "evidence revision must be a positive integer", "evidence_refs")
    if not isinstance(pin["content_hash"], str) or not re.fullmatch(r"[a-f0-9]{64}", pin["content_hash"]):
        raise PreviewProjectionError("INVALID_EVIDENCE_HASH", "evidence content_hash must be a SHA-256 hex value", "evidence_refs")
    record = record or copy.deepcopy(dict(evidence_index.get(pin["evidence_id"], {}))) if pin["evidence_id"] in evidence_index else record
    if record and (record.get("revision") != pin["revision"] or record.get("content_hash") != pin["content_hash"]):
        # A latest record must never silently satisfy a historical pin.
        record = None
    return pin, record


def _group_id(candidate: Mapping[str, Any]) -> str:
    opportunity_type = str(candidate.get("opportunity_type", "")).upper()
    action = str(candidate.get("recommended_action", "")).upper()
    if opportunity_type in {"GEO", "GEO_GAP", "GEO_ENHANCE", "GEO_PROMPT_GAP", "GEO_CITATION_GAP", "GEO_ENTITY_GAP"} or action in {"GEO_ENHANCE", "GEO_CREATE"}:
        return "GEO_GAPS"
    if opportunity_type in {"CONTENT_GAP", "SEO_NEW", "CREATE_NEW", "CONTENT_OPPORTUNITY"} or action == "CREATE_NEW":
        return "CONTENT_GAPS"
    if opportunity_type in {"CONTENT_DECAY", "TECHNICAL_UNLOCK", "TECHNICAL_ISSUE", "SF_TECHNICAL"} or action in {"FIX_TECHNICAL", "REFRESH_CONTENT", "REPAIR_TECHNICAL"}:
        return "CONTENT_DECAY_TECHNICAL_UNLOCK"
    return "QUICK_WINS"


def _score(candidate: Mapping[str, Any]) -> Any:
    value = candidate.get("opportunity_score", candidate.get("score"))
    if isinstance(value, Mapping):
        value = value.get("value", value.get("total"))
    return value


def _priority(candidate: Mapping[str, Any]) -> Any:
    return candidate.get("priority_band", candidate.get("score_band", candidate.get("priority")))


def _freshness(record: Mapping[str, Any]) -> dict[str, Any]:
    for key in ("period_start", "period_end", "as_of"):
        value = record.get(key)
        if value is not None:
            try:
                date.fromisoformat(str(value))
            except ValueError as exc:
                raise PreviewProjectionError("INVALID_EVIDENCE_DATE", f"{key} must be an ISO-8601 date", key) from exc
    retrieved_at = record.get("retrieved_at")
    if retrieved_at is not None:
        try:
            parsed = datetime.fromisoformat(str(retrieved_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise PreviewProjectionError("INVALID_EVIDENCE_DATETIME", "retrieved_at must be ISO-8601", "retrieved_at") from exc
        if parsed.tzinfo is None:
            raise PreviewProjectionError("NAIVE_EVIDENCE_DATETIME", "retrieved_at must include a timezone", "retrieved_at")
    state = record.get("freshness_state")
    if state is None and record.get("freshness") and isinstance(record.get("freshness"), Mapping):
        state = record["freshness"].get("state", record["freshness"].get("freshness_state"))
    state = str(state or "NOT_AVAILABLE").upper()
    if state not in _FRESHNESS_STATES:
        state = "NOT_AVAILABLE"
    return {
        "period_start": record.get("period_start"),
        "period_end": record.get("period_end"),
        "as_of": record.get("as_of"),
        "retrieved_at": record.get("retrieved_at"),
        "freshness_state": state,
        "collection_status": record.get("collection_status", "NOT_AVAILABLE"),
        "is_current": state == "READY" and str(record.get("collection_status", "SUCCESS")).upper() in {"SUCCESS", "READY"},
    }


def _source_key(record: Mapping[str, Any]) -> str:
    source = str(record.get("source", record.get("source_class", "UNKNOWN"))).upper()
    if source in {"WORKDUO", "GEO", "MONITORED_GEO_SAMPLE"} or "GEO" in source:
        return "GEO"
    for key in SOURCE_LABELS:
        if key in source:
            return key
    return source or "UNKNOWN"


def _evidence_layer(refs: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for ref, record in zip(refs, records):
        key = _source_key(record)
        grouped.setdefault(key, []).append({
            "evidence_ref": copy.deepcopy(dict(ref)),
            "metric": record.get("metric"),
            "unit": record.get("unit"),
            "value": record.get("value"),
            "is_estimate": record.get("source_class") == "THIRD_PARTY_ESTIMATE" or key == "AHREFS",
            "freshness": _freshness(record),
        })
    layers: dict[str, Any] = {}
    for key, rows in sorted(grouped.items()):
        layers[key] = {
            "source_role": key,
            "label": SOURCE_LABELS.get(key, key),
            "status": "AVAILABLE" if any(row["freshness"]["collection_status"] in {"SUCCESS", "READY"} for row in rows) else "NOT_AVAILABLE",
            "is_estimate": any(row["is_estimate"] for row in rows),
            "evidence_refs": [row["evidence_ref"] for row in rows],
            "evidence": rows,
            "missing": False,
        }
    for key in SOURCE_LABELS:
        if key not in layers and key != "GEO":
            layers[key] = {"source_role": key, "label": SOURCE_LABELS[key], "status": "NOT_AVAILABLE", "is_estimate": key == "AHREFS", "evidence_refs": [], "evidence": [], "missing": True}
    if "GEO" not in layers:
        layers["GEO"] = {"source_role": "GEO", "label": SOURCE_LABELS["GEO"], "status": "NOT_AVAILABLE", "is_estimate": False, "evidence_refs": [], "evidence": [], "missing": True}
    return layers


def _diagnostic_layer(candidate: Mapping[str, Any], key: str, diagnostic: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    source = copy.deepcopy(dict(diagnostic)) if isinstance(diagnostic, Mapping) else None
    if source is None:
        embedded = candidate.get("ga4_diagnostic" if key == "GA4" else "serp_validation" if key == "SERP" else "geo_diagnostic")
        source = copy.deepcopy(dict(embedded)) if isinstance(embedded, Mapping) else None
    if source is None:
        return {"status": "NOT_AVAILABLE", "missing": True, "evidence_refs": []}
    refs = source.get("ga4_evidence_refs" if key == "GA4" else "serp_evidence_refs" if key == "SERP" else "geo_evidence_refs", [])
    output: dict[str, Any] = {"missing": False, "evidence_refs": copy.deepcopy(refs) if isinstance(refs, list) else []}
    if key == "GA4":
        output.update({
            "status": source.get("diagnostic_status", "NOT_AVAILABLE"),
            "conversion_boundary": "DIAGNOSTIC_ONLY",
            "cta_is_conversion": False,
            "business_outcome": "NOT_AVAILABLE",
            "signals": copy.deepcopy(source.get("signals", {})),
            "missing": bool(source.get("missing_evidence")),
            "conflicts": copy.deepcopy(source.get("conflicts", [])),
            "freshness": copy.deepcopy(source.get("freshness", [])),
        })
    elif key == "SERP":
        output.update({
            "status": source.get("validation_status", "SERP_NOT_CHECKED"),
            "observed_intent": source.get("observed_intent"),
            "observed_page_type": source.get("observed_page_type"),
            "feature_states": copy.deepcopy(source.get("feature_states", source.get("features", {}))),
            "conflicts": copy.deepcopy(source.get("conflict_reasons", source.get("conflicts", []))),
            "missing": bool(source.get("missing_evidence")),
            "freshness": copy.deepcopy(source.get("freshness", [])),
            "approval_transition_allowed": False,
        })
    else:
        output.update({
            "status": source.get("diagnostic_status", "GEO_NOT_CHECKED"),
            "mention_state": source.get("mention_state", "NOT_AVAILABLE"),
            "citation_state": source.get("citation_state", "NOT_AVAILABLE"),
            "comparability": copy.deepcopy(source.get("comparability", {"status": "NOT_AVAILABLE"})),
            "conflicts": copy.deepcopy(source.get("conflicts", [])),
            "missing": bool(source.get("missing_evidence")),
            "freshness": copy.deepcopy(source.get("freshness", [])),
            "market_coverage": "NOT_AVAILABLE",
            "approval_transition_allowed": False,
        })
    return output


def _safe_refs(candidate: Mapping[str, Any], evidence_index: Mapping[str, Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    refs: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    unresolved: list[str] = []
    for raw in candidate.get("evidence_refs", []):
        try:
            pin, record = _pin(raw, evidence_index)
        except PreviewProjectionError:
            if isinstance(raw, str):
                unresolved.append(raw)
                continue
            raise
        refs.append(pin)
        if record:
            records.append(record)
        else:
            records.append({"source": "UNKNOWN", "collection_status": "NOT_AVAILABLE", "freshness_state": "NOT_AVAILABLE"})
    return refs, records, unresolved


def _row(candidate: Mapping[str, Any], refs: Sequence[Mapping[str, Any]], records: Sequence[Mapping[str, Any]], diagnostics: Mapping[str, Mapping[str, Any]], *, uat_candidate_id: str) -> dict[str, Any]:
    score = _score(candidate)
    score_payload = score if isinstance(score, Mapping) else {"value": score, "profile": candidate.get("score_profile"), "bounds": candidate.get("score_bounds", candidate.get("bounds")), "preserved": True, "recomputed": False}
    missing = list(candidate.get("missing_evidence_roles", candidate.get("missing", [])) or [])
    policy = list(candidate.get("policy_gaps", []) or [])
    capability = list(candidate.get("capability_gaps", []) or [])
    conflicts = list(candidate.get("conflicting_evidence_refs", candidate.get("conflicts", []) or []) or [])
    for key in ("GA4", "SERP", "GEO"):
        conflicts.extend(diagnostics.get(key, {}).get("conflicts", []) or [])
    row = {
        "candidate_id": uat_candidate_id,
        "source_candidate_id": candidate["candidate_id"],
        "candidate_revision": candidate["revision"],
        "topic_ref": copy.deepcopy(candidate.get("topic_ref", candidate.get("topic_cluster_id"))),
        "group_id": _group_id(candidate),
        "opportunity_type": candidate.get("opportunity_type", "UNKNOWN"),
        "recommended_action": candidate.get("recommended_action", "DO_NOTHING"),
        "target_url": candidate.get("target_url"),
        "existing_urls": copy.deepcopy(candidate.get("existing_urls", [])),
        "priority_band": _priority(candidate),
        "score": copy.deepcopy(score_payload),
        "confidence": copy.deepcopy(candidate.get("confidence", "NOT_ASSESSABLE")),
        "status": candidate.get("status", "CANDIDATE"),
        "review_state": candidate.get("review_state", "NOT_REVIEWED"),
        "approval_transition_allowed": False,
        "rationale": candidate.get("rationale", ""),
        "estimate": {"available": any(record.get("source_class") == "THIRD_PARTY_ESTIMATE" for record in records), "source": "AHREFS" if any(_source_key(record) == "AHREFS" for record in records) else None},
        "gaps": {"missing": sorted({str(value) for value in missing}), "policy": sorted({str(value) for value in policy}), "capability": sorted({str(value) for value in capability})},
        "conflicts": sorted({str(value) for value in conflicts}),
        "evidence_refs": copy.deepcopy(list(refs)),
        "evidence_timeline": [_freshness(record) | {"evidence_id": ref["evidence_id"], "revision": ref["revision"]} for ref, record in zip(refs, records)],
        "source_layers": _evidence_layer(refs, records),
        "diagnostics": {
            "GA4": diagnostics.get("GA4", {"status": "NOT_AVAILABLE", "missing": True, "evidence_refs": []}),
            "SERP": diagnostics.get("SERP", {"status": "SERP_NOT_CHECKED", "missing": True, "evidence_refs": []}),
            "GEO": diagnostics.get("GEO", {"status": "GEO_NOT_CHECKED", "missing": True, "evidence_refs": []}),
        },
    }
    # A CTA may be displayed as a behavior signal, but the preview must not
    # create a formal conversion field or a business outcome.
    row["ga4_governance"] = {"role": "FIRST_PARTY_BEHAVIOR_DIAGNOSTIC", "conversion_boundary": "DIAGNOSTIC_ONLY", "cta_is_conversion": False}
    row["geo_governance"] = {"role": "MONITORED_FIXED_SAMPLE", "market_wide_claim": False}
    return row


def _normalize_input(value: Any, **kwargs: Any) -> tuple[Sequence[Mapping[str, Any]], Any, Any, Any, Any, str, int]:
    if isinstance(value, OpportunityPreviewInput):
        return value.candidates, value.evidence, value.ga4_diagnostics, value.serp_validations, value.geo_diagnostics, value.uat_dataset_id, value.max_candidates
    if isinstance(value, Mapping):
        candidates = value.get("candidates", value.get("candidate_records", []))
        return candidates, value.get("evidence", kwargs.get("evidence")), value.get("ga4_diagnostics", kwargs.get("ga4_diagnostics")), value.get("serp_validations", kwargs.get("serp_validations")), value.get("geo_diagnostics", kwargs.get("geo_diagnostics")), str(value.get("uat_dataset_id", kwargs.get("uat_dataset_id", "WP9_SYNTHETIC_UAT"))), int(value.get("max_candidates", kwargs.get("max_candidates", 20)))
    return value, kwargs.get("evidence"), kwargs.get("ga4_diagnostics"), kwargs.get("serp_validations"), kwargs.get("geo_diagnostics"), str(kwargs.get("uat_dataset_id", "WP9_SYNTHETIC_UAT")), int(kwargs.get("max_candidates", 20))


def project_opportunity_preview(value: Any, *, evidence: Any = None, ga4_diagnostics: Any = None, serp_validations: Any = None, geo_diagnostics: Any = None, uat_dataset_id: str = "WP9_SYNTHETIC_UAT", max_candidates: int = 20) -> dict[str, Any]:
    """Project pinned candidate revisions into a local UAT report.

    No score, confidence, state, or source metric is calculated here.  Candidates
    are sorted by the persisted WP5 score only; missing scores sort last.
    """

    candidates, embedded_evidence, embedded_ga4, embedded_serp, embedded_geo, dataset_id, cap = _normalize_input(value, evidence=evidence, ga4_diagnostics=ga4_diagnostics, serp_validations=serp_validations, geo_diagnostics=geo_diagnostics, uat_dataset_id=uat_dataset_id, max_candidates=max_candidates)
    if not isinstance(candidates, (list, tuple)):
        raise PreviewProjectionError("INVALID_CANDIDATES", "candidates must be a sequence", "candidates")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 1 or cap > 100:
        raise PreviewProjectionError("INVALID_PREVIEW_CAP", "max_candidates must be between 1 and 100", "max_candidates")
    evidence_index = _index_records(embedded_evidence)
    ga4_index = _index_records(embedded_ga4)
    serp_index = _index_records(embedded_serp)
    geo_index = _index_records(embedded_geo)
    normalized: list[dict[str, Any]] = []
    for raw in candidates:
        candidate = _candidate_payload(raw)
        refs, records, unresolved = _safe_refs(candidate, evidence_index)
        if unresolved:
            candidate.setdefault("missing_evidence_roles", [])
            candidate["missing_evidence_roles"] = list(candidate["missing_evidence_roles"]) + ["UNRESOLVED_EVIDENCE_PIN"]
        source_id = candidate["candidate_id"]
        diagnostic_map = {
            "GA4": _diagnostic_layer(candidate, "GA4", ga4_index.get(source_id)),
            "SERP": _diagnostic_layer(candidate, "SERP", serp_index.get(source_id)),
            "GEO": _diagnostic_layer(candidate, "GEO", geo_index.get(source_id)),
        }
        # Give each preview row a deterministic UAT identity separate from the
        # candidate/store identity so fixture records cannot be mistaken for
        # production rows.
        uat_id = "UAT_" + hashlib.sha256(canonical_json({"dataset": dataset_id, "candidate_id": source_id, "revision": candidate["revision"]}).encode("utf-8")).hexdigest()[:20]
        normalized.append(_row(candidate, refs, records, diagnostic_map, uat_candidate_id=uat_id))
    normalized.sort(key=lambda row: (-(row["score"]["value"] if isinstance(row["score"].get("value"), (int, float)) and not isinstance(row["score"].get("value"), bool) else float("-inf")), row["source_candidate_id"], row["candidate_revision"]))
    visible = normalized[:cap]
    visible_ids = {row["candidate_id"] for row in visible}
    group_rows = {group_id: [row for row in visible if row["group_id"] == group_id] for group_id, _ in GROUPS}
    groups = []
    for group_id, label in GROUPS:
        all_count = sum(1 for row in normalized if row["group_id"] == group_id)
        groups.append({"group_id": group_id, "label": label, "total_count": all_count, "visible_count": len(group_rows[group_id]), "rows": group_rows[group_id]})
    semantic = {
        "record_type": "OPPORTUNITY_PREVIEW",
        "contract_version": CONTRACT_VERSION,
        "environment": PREVIEW_ENVIRONMENT,
        "uat_dataset_id": dataset_id,
        "renderer_version": RENDERER_VERSION,
        "candidate_count": len(normalized),
        "first_screen": {"max_candidates": cap, "candidate_ids": [row["candidate_id"] for row in visible], "truncated": len(normalized) > cap},
        "groups": groups,
        "candidates": normalized,
        "governance": {"read_only_projection": True, "score_recomputed": False, "confidence_recomputed": False, "source_metrics_combined": False, "auto_approval": False, "production_mutation": False, "recommendations_written": False, "next_steps_written": False},
    }
    preview_seed = {"uat_dataset_id": dataset_id, "candidate_ids": [(row["source_candidate_id"], row["candidate_revision"]) for row in normalized], "renderer_version": RENDERER_VERSION}
    payload = {
        **semantic,
        "preview_id": "UAT_PREVIEW_" + _hash(preview_seed)[:20],
        "generated_at": None,
        "semantic_hash": _hash(semantic),
    }
    return copy.deepcopy(payload)


def _display(value: Any) -> str:
    text = "" if value is None else str(value)
    return html.escape(text, quote=True)


def sanitize_cell(value: Any) -> str:
    """Return a safe text cell for UAT exports, including formula-like input."""

    text = "" if value is None else str(value)
    return "'" + text if _FORMULA_PREFIX.match(text) else text


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = ["# Opportunity preview / UAT report", "", f"- Preview: `{payload.get('preview_id')}`", f"- Dataset: `{payload.get('uat_dataset_id')}`", f"- Candidates: `{payload.get('candidate_count', 0)}`; first screen: `{len((payload.get('first_screen') or {}).get('candidate_ids', []))}`", "", "## Candidate review"]
    for group in payload.get("groups", []):
        lines.extend(["", f"### {sanitize_cell(group.get('label'))}", "", "| Candidate | Type | Score | Confidence | Status | Missing / conflicts |", "| --- | --- | ---: | --- | --- | --- |"])
        rows = group.get("rows", [])
        if not rows:
            lines.append("| — | — | — | — | — | NOT_AVAILABLE |")
        for row in rows:
            score = (row.get("score") or {}).get("value")
            gaps = ", ".join((row.get("gaps") or {}).get("missing", [])) or ", ".join(row.get("conflicts", [])) or "none"
            lines.append("| `{}` | `{}` | `{}` | `{}` | `{}` | {} |".format(*(sanitize_cell(value) for value in (row.get("candidate_id"), row.get("opportunity_type"), score if score is not None else "NOT_AVAILABLE", row.get("confidence"), row.get("status"), gaps))))
    return "\n".join(lines) + "\n"


def _html(payload: Mapping[str, Any]) -> str:
    rows: list[str] = []
    for group in payload.get("groups", []):
        rows.append(f"<section class=\"group\"><h2>{_display(group.get('label'))}</h2><div class=\"table-wrap\"><table><thead><tr><th>Candidate</th><th>Type</th><th>Score</th><th>Confidence</th><th>Status</th><th>Missing / conflicts</th><th>Rationale</th></tr></thead><tbody>")
        if not group.get("rows"):
            rows.append("<tr><td colspan=\"7\">NOT_AVAILABLE</td></tr>")
        for row in group.get("rows", []):
            score = (row.get("score") or {}).get("value")
            gaps = ", ".join((row.get("gaps") or {}).get("missing", [])) or ", ".join(row.get("conflicts", [])) or "none"
            rows.append("<tr><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>".format(*(_display(sanitize_cell(value)) for value in (row.get("candidate_id"), row.get("opportunity_type"), score if score is not None else "NOT_AVAILABLE", row.get("confidence"), row.get("status"), gaps, row.get("rationale")))))
        rows.append("</tbody></table></div></section>")
    header = "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Opportunity preview / UAT report</title><style>body{font:14px system-ui,sans-serif;color:#17202a;margin:24px;line-height:1.4}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:720px}th,td{border:1px solid #d9dee5;padding:8px;text-align:left;vertical-align:top}th{background:#f2f5f8}.group{margin:24px 0}.meta{color:#536170}@media(max-width:375px){body{margin:12px;font-size:12px}.group{margin:16px 0}th,td{padding:6px}}</style></head><body><h1>Opportunity preview / UAT report</h1>"
    meta = f"<p class=\"meta\">Preview: {_display(payload.get('preview_id'))} · Dataset: {_display(payload.get('uat_dataset_id'))} · Candidates: {_display(payload.get('candidate_count'))}</p>"
    return header + meta + "".join(rows) + "</body></html>"


def render_opportunity_preview(value: Any, *, format: str = "json") -> str:
    """Render a projected payload as canonical JSON, Markdown, or local HTML."""

    payload = project_opportunity_preview(value) if not isinstance(value, Mapping) or value.get("record_type") != "OPPORTUNITY_PREVIEW" else copy.deepcopy(dict(value))
    if format == "json":
        return canonical_json(payload)
    if format in {"markdown", "md"}:
        return _markdown(payload)
    if format == "html":
        return _html(payload)
    raise ValueError("format must be json, markdown, or html")


def validate_opportunity_preview(payload: Any) -> ValidationResult:
    errors: list[ValidationError] = []
    if not isinstance(payload, Mapping):
        return ValidationResult(errors=[ValidationError("SCHEMA_VIOLATION", "$", "preview must be an object")])
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        schema_path = Path(__file__).resolve().parents[2] / "contracts/opportunity_preview.v1.proposal.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        for error in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload):
            errors.append(ValidationError("SCHEMA_VIOLATION", ".".join(map(str, error.absolute_path)) or "$", "preview violates the proposal schema", rule=str(error.validator)))
    except Exception as exc:
        errors.append(ValidationError("SCHEMA_VALIDATION_ERROR", "$", str(exc)))
    if payload.get("environment") != PREVIEW_ENVIRONMENT:
        errors.append(ValidationError("PRODUCTION_PREVIEW", "environment", "WP9 preview must be UAT"))
    governance = payload.get("governance") or {}
    for field in ("read_only_projection", "score_recomputed", "confidence_recomputed", "auto_approval", "production_mutation"):
        expected = True if field == "read_only_projection" else False
        if governance.get(field) is not expected:
            errors.append(ValidationError("GOVERNANCE_VIOLATION", f"governance.{field}", f"{field} does not satisfy WP9 policy"))
    try:
        semantic = {key: value for key, value in payload.items() if key not in {"preview_id", "generated_at", "semantic_hash"}}
        if payload.get("semantic_hash") != _hash(semantic):
            errors.append(ValidationError("SEMANTIC_HASH_MISMATCH", "semantic_hash", "preview semantic hash mismatch"))
    except Exception as exc:
        errors.append(ValidationError("SEMANTIC_HASH_ERROR", "semantic_hash", str(exc)))
    return ValidationResult(errors=errors)


# Small aliases make the pure projection discoverable without coupling callers
# to one particular naming convention.
project_preview = project_opportunity_preview
preview_report_projection = project_opportunity_preview
render_preview = render_opportunity_preview
build_opportunity_preview = project_opportunity_preview
render_uat_preview = render_opportunity_preview


__all__ = [
    "CONTRACT_VERSION", "RENDERER_VERSION", "GROUPS", "OpportunityPreviewInput", "PreviewProjectionError",
    "project_opportunity_preview", "project_preview", "preview_report_projection", "build_opportunity_preview", "render_opportunity_preview", "render_preview", "render_uat_preview",
    "sanitize_cell", "validate_opportunity_preview",
]
