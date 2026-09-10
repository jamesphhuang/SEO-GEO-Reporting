"""Versioned, explainable ordinal scoring for SEO candidates."""

from __future__ import annotations

import math
from typing import Any, Iterable, Mapping, Optional

from .models import OpportunityEvaluationInput, RuleDecision
from .rules_seo import _number, _records, _value

SCORE_PROFILE_VERSION = "scoring-proposal-1"
PROFILES = {
    "SEO_EXISTING": {"demand_score": 20, "traction_score": 15, "business_score": 30, "attainability_score": 20, "geo_score": 0, "execution_score": 15},
    "SEO_NEW": {"demand_score": 25, "traction_score": 0, "business_score": 30, "attainability_score": 25, "geo_score": 0, "execution_score": 20},
}


def _refs(records: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted({str(record.get("evidence_id")) for record in records if record.get("evidence_id")})


def _band_explanation(band: Optional[int], rationale: str, records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    return {"rationale": rationale, "evidence_refs": _refs(records)}


def _demand(ahrefs: list[dict[str, Any]]) -> tuple[Optional[int], str, list[dict[str, Any]]]:
    for record in ahrefs:
        volume = _number(_value(record, "volume"))
        if volume is None:
            continue
        if volume <= 0:
            return 0, "Observed Ahrefs volume is zero for the representative term.", [record]
        if volume < 100:
            return 1, "Representative Ahrefs volume is in the 1–99 band.", [record]
        if volume < 500:
            return 2, "Representative Ahrefs volume is in the 100–499 band.", [record]
        if volume < 2000:
            return 3, "Representative Ahrefs volume is in the 500–1999 band.", [record]
        return 4, "Representative Ahrefs volume is at least 2000.", [record]
    return None, "Ahrefs demand evidence is missing or not numeric; missing is not zero.", []


def _traction(gsc: list[dict[str, Any]]) -> tuple[Optional[int], str, list[dict[str, Any]]]:
    for record in gsc:
        impressions = _number(_value(record, "impressions"))
        position = _number(_value(record, "position"))
        if impressions is None or position is None:
            continue
        if impressions < 100:
            return (0 if impressions == 0 and record.get("coverage") == "COMPLETE_WITHIN_SCOPE" else None), "GSC traction is below the meaningful-impression threshold; preserve zero only for an exact complete bucket.", [record]
        if 4 <= position <= 15:
            return 4, "GSC position shows page-level headroom in positions 4–15 with meaningful impressions.", [record]
        if position <= 3:
            return (3 if _number(_value(record, "ctr")) is not None else 0), "GSC position is already near the top; only explicit CTR/decay headroom can support a non-zero band.", [record]
        if position <= 20:
            return 3, "GSC position is in the 16–20 band with meaningful impressions.", [record]
        if position <= 40:
            return 2, "GSC position is in the 21–40 band with meaningful impressions.", [record]
        return 1, "GSC has impressions but position is beyond the primary headroom bands.", [record]
    return None, "GSC traction evidence is missing or incomplete; missing is not zero.", []


def _explicit_band(records: list[dict[str, Any]], field: str, fallback: Optional[int] = None) -> tuple[Optional[int], str, list[dict[str, Any]]]:
    for record in records:
        value = record.get(field)
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 4:
            return value, f"Normalized evidence supplied explicit {field}={value}.", [record]
    return fallback, f"{field} is not supplied by normalized evidence; missing is not zero.", []


def score_candidate(bundle: OpportunityEvaluationInput, decision: RuleDecision) -> dict[str, Any]:
    records = [dict(record) for record in bundle.evidence]
    ahrefs = _records(records, "AHREFS", decision.target_url)
    gsc = _records(records, "GSC", decision.target_url)
    sf = _records(records, "SF", decision.target_url)
    profile = "SEO_NEW" if decision.recommended_action == "CREATE_NEW" else "SEO_EXISTING"
    weights = PROFILES[profile]
    demand, demand_reason, demand_records = _demand(ahrefs)
    traction, traction_reason, traction_records = _traction(gsc)
    attainability, attainability_reason, attainability_records = _explicit_band(records, "attainability_band")
    execution, execution_reason, execution_records = _explicit_band(sf, "execution_band")
    bands: dict[str, Optional[int]] = {
        "demand_score": demand,
        "traction_score": None if weights["traction_score"] == 0 else traction,
        "business_score": None,
        "attainability_score": attainability,
        "geo_score": None,
        "execution_score": execution,
    }
    explanations = {
        "demand_score": _band_explanation(demand, demand_reason, demand_records),
        "traction_score": _band_explanation(bands["traction_score"], traction_reason, traction_records),
        "business_score": _band_explanation(None, "Business Actual is outside WP5 source scope; no business score is imputed.", []),
        "attainability_score": _band_explanation(attainability, attainability_reason, attainability_records),
        "geo_score": _band_explanation(None, "GEO is outside WP5 source scope; the GEO dimension remains inactive.", []),
        "execution_score": _band_explanation(execution, execution_reason, execution_records),
    }
    observed = 0.0
    missing_weight = 0
    for name, weight in weights.items():
        band = bands[name]
        if band is None:
            missing_weight += weight
        else:
            observed += weight * band / 4
    return {
        **bands,
        "score_profile": profile,
        "score_profile_version": bundle.score_profile_version,
        "opportunity_score": None if missing_weight else math.floor(observed + 0.5),
        "score_lower_bound": math.floor(observed),
        "score_upper_bound": math.ceil(observed + missing_weight),
        "score_explanations": explanations,
    }


__all__ = ["PROFILES", "SCORE_PROFILE_VERSION", "score_candidate"]
