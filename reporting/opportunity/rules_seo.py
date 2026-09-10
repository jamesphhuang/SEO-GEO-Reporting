"""Deterministic offline SEO opportunity rules.

Rules consume normalized evidence only. They return hypotheses and explicit
missing/conflict states; they never call Ahrefs, GSC, Screaming Frog, or write
production outputs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Optional

from .models import EngineInputError, OpportunityEvaluationInput, RuleDecision, SUPPORTED_SOURCES

RULE_VERSION = "rules-proposal-1"
MEANINGFUL_IMPRESSIONS = 100
CTR_IMPRESSIONS = 500
DECAY_WINDOWS = 6
DECAY_RELATIVE_CHANGE = 0.20


def _record_id(record: Mapping[str, Any]) -> str:
    value = record.get("evidence_id") or record.get("id")
    if not isinstance(value, str) or not value:
        raise EngineInputError("every evidence revision requires evidence_id")
    return value


def _source(record: Mapping[str, Any]) -> str:
    return str(record.get("source", "")).upper()


def _state(record: Mapping[str, Any]) -> str:
    return str(record.get("freshness_state", "UNKNOWN")).upper()


def _value(record: Mapping[str, Any], metric: str, default: Any = None) -> Any:
    metrics = record.get("metrics")
    if isinstance(metrics, Mapping) and metric in metrics:
        return metrics[metric]
    if record.get("metric") == metric:
        return record.get("value", default)
    if metric in record:
        return record.get(metric)
    return default


def _number(value: Any) -> Optional[float]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _topic_matches(record: Mapping[str, Any], topic_id: str) -> bool:
    if record.get("topic_id") == topic_id or record.get("topic_cluster_id") == topic_id:
        return True
    refs = record.get("topic_refs") or record.get("canonical_topic_refs") or []
    if isinstance(refs, str):
        refs = [refs]
    return topic_id in refs


def _url_matches(record: Mapping[str, Any], target_url: Optional[str]) -> bool:
    if target_url is None:
        return True
    candidates = [record.get("url"), record.get("target_url"), record.get("normalized_url"), record.get("landing_url")]
    candidates.extend(record.get("urls") or [] if isinstance(record.get("urls"), list) else [])
    values = {str(value) for value in candidates if value}
    # Topic-level Ahrefs/GSC observations have no URL.  They remain eligible
    # for a URL-level hypothesis; only an explicit, different URL excludes a
    # record.
    return not values or target_url in values


def _topic_records(bundle: OpportunityEvaluationInput) -> list[dict[str, Any]]:
    topic_id = str(bundle.topic.get("topic_id") or bundle.topic.get("topic_cluster_id") or "")
    if not topic_id:
        raise EngineInputError("topic requires topic_id")
    records: list[dict[str, Any]] = []
    for raw in bundle.evidence:
        record = dict(raw)
        if not _record_id(record):
            continue
        source = _source(record)
        if source not in SUPPORTED_SOURCES:
            raise EngineInputError(f"unsupported WP5 source: {source or 'UNKNOWN'}")
        if _topic_matches(record, topic_id) or not (record.get("topic_id") or record.get("topic_refs") or record.get("canonical_topic_refs")):
            records.append(record)
    return records


def _records(records: Iterable[Mapping[str, Any]], source: str, target_url: Optional[str] = None) -> list[dict[str, Any]]:
    return [dict(record) for record in records if _source(record) == source and _url_matches(record, target_url)]


def _fresh(records: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [dict(record) for record in records if _state(record) == "READY" and str(record.get("collection_status", "SUCCESS")).upper() in {"SUCCESS", "READY"}]


def _ids(records: Iterable[Mapping[str, Any]]) -> list[str]:
    return sorted({_record_id(record) for record in records})


def _existing_urls(bundle: OpportunityEvaluationInput) -> list[str]:
    explicit = bundle.topic.get("existing_urls") or ([] if not bundle.topic.get("existing_url") else [bundle.topic.get("existing_url")])
    if explicit:
        return sorted({str(value) for value in explicit if value})
    topic_id = str(bundle.topic.get("topic_id") or bundle.topic.get("topic_cluster_id"))
    urls = []
    for row in (bundle.registry.get("entities", {}).get("URL", []) if isinstance(bundle.registry.get("entities"), Mapping) else []):
        refs = row.get("canonical_topic_refs", [])
        if topic_id in refs and row.get("normalized_url"):
            urls.append(str(row["normalized_url"]))
    return sorted(set(urls))


def _mapping_confirmed(bundle: OpportunityEvaluationInput) -> bool:
    return bundle.entity_mappings_confirmed and bundle.mapping_review_state.upper() == "APPROVED"


def _review_at(bundle: OpportunityEvaluationInput) -> str:
    try:
        value = datetime.fromisoformat(bundle.decision_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EngineInputError("decision_at must be timezone-aware ISO-8601") from exc
    if value.tzinfo is None:
        raise EngineInputError("decision_at must be timezone-aware ISO-8601")
    return (value + timedelta(days=28)).isoformat()


def _decision(
    bundle: OpportunityEvaluationInput,
    opportunity_type: str,
    action: str,
    rule_id: str,
    *,
    matched: Iterable[str] = (),
    failed: Iterable[str] = (),
    missing: Iterable[str] = (),
    required: Iterable[str] = (),
    evidence: Iterable[Mapping[str, Any]] = (),
    target_url: Optional[str] = None,
    existing_urls: Iterable[str] = (),
    conflicts: Iterable[str] = (),
    policy_gaps: Iterable[str] = (),
    rationale: str,
    status_hint: str = "CANDIDATE",
    review_at: Optional[str] = None,
) -> RuleDecision:
    return RuleDecision(
        opportunity_type=opportunity_type,
        recommended_action=action,
        rule_id=rule_id,
        matched_conditions=sorted(set(matched)),
        failed_conditions=sorted(set(failed)),
        missing_evidence_roles=sorted(set(missing)),
        required_evidence_roles=sorted(set(required)),
        conflicting_evidence_refs=sorted(set(conflicts)),
        evidence_ids=_ids(evidence),
        target_url=target_url,
        existing_urls=sorted(set(existing_urls)),
        policy_gaps=sorted(set(policy_gaps)),
        rationale=rationale,
        review_at=review_at,
        status_hint=status_hint,
    )


def _technical_unlock(bundle: OpportunityEvaluationInput, records: list[dict[str, Any]], target_url: Optional[str], existing_urls: list[str]) -> Optional[RuleDecision]:
    sf = _records(records, "SF", target_url)
    demand = _records(records, "AHREFS", target_url) + _records(records, "GSC", target_url)
    if not sf:
        return None
    issues = [issue for record in sf for issue in (record.get("issues") or []) if isinstance(issue, Mapping)]
    severe = [issue for issue in issues if str(issue.get("severity", "")).upper() in {"CRITICAL", "HIGH"}]
    if not severe:
        return None
    if not demand:
        return _decision(bundle, "DO_NOTHING", "MONITOR", "SEO-TECH-001", failed=["technical_issue_has_no_search_intersection"], missing=["demand"], required=["technical", "demand"], evidence=sf, target_url=target_url, existing_urls=existing_urls, rationale="Technical issues were observed, but no matching Ahrefs or GSC search evidence intersects the affected URL; monitor rather than create a technical opportunity.", review_at=_review_at(bundle))
    matching = _fresh(demand + sf)
    missing = [] if len(matching) == len(demand) + len(sf) else ["freshness"]
    return _decision(bundle, "TECHNICAL_UNLOCK", "TECHNICAL_FIX", "SEO-TECH-001", matched=["url_specific_technical_issue", "search_demand_intersection"], missing=missing, required=["technical", "demand"], evidence=sf + demand, target_url=target_url, existing_urls=existing_urls, rationale="A URL-specific technical issue intersects a topic with observed search demand; fixability should be evaluated before content work.")


def _ctr_opportunity(bundle: OpportunityEvaluationInput, records: list[dict[str, Any]], target_url: Optional[str], existing_urls: list[str]) -> Optional[RuleDecision]:
    gsc = _records(records, "GSC", target_url)
    sf = _records(records, "SF", target_url)
    if not gsc or not sf:
        return None
    windows: list[Mapping[str, Any]] = []
    for record in gsc:
        if isinstance(record.get("windows"), list):
            windows.extend(item for item in record["windows"] if isinstance(item, Mapping))
    current = next((window for window in windows if window.get("role") == "current"), None)
    previous = next((window for window in windows if window.get("role") == "previous"), None)
    current = current or next((record.get("current") for record in gsc if isinstance(record.get("current"), Mapping)), None)
    previous = previous or next((record.get("previous") for record in gsc if isinstance(record.get("previous"), Mapping)), None)
    issue_records = [record for record in sf if any(str(issue.get("type", "")).upper() in {"TITLE", "META", "SNIPPET"} for issue in (record.get("issues") or []) if isinstance(issue, Mapping))]
    if not current or not previous or not issue_records:
        return None
    impressions = _number(current.get("impressions"))
    current_ctr = _number(current.get("ctr"))
    previous_ctr = _number(previous.get("ctr"))
    current_position = _number(current.get("position"))
    previous_position = _number(previous.get("position"))
    if None in (impressions, current_ctr, previous_ctr, current_position, previous_position):
        return _decision(bundle, "DO_NOTHING", "MONITOR", "SEO-CTR-001", failed=["complete_two_window_ctr_metrics"], missing=["traction"], required=["traction", "technical"], evidence=gsc + issue_records, target_url=target_url, existing_urls=existing_urls, rationale="CTR hypothesis cannot be evaluated without two complete comparable GSC windows and a URL-level title or meta observation.", review_at=_review_at(bundle))
    decline = previous_ctr > 0 and current_ctr <= previous_ctr * (1 - DECAY_RELATIVE_CHANGE)
    position_stable = abs(current_position - previous_position) <= 1
    if impressions < CTR_IMPRESSIONS or not position_stable or not decline:
        return None
    return _decision(bundle, "CTR_OPPORTUNITY", "SERP_SNIPPET_OPTIMIZE", "SEO-CTR-001", matched=["high_impressions", "stable_position", "ctr_underperformance", "title_or_meta_issue"], required=["traction", "technical"], evidence=gsc + issue_records, target_url=target_url, existing_urls=existing_urls, rationale="Title/meta truncation overlaps with a high-impression, low-CTR URL and should be investigated; this is a hypothesis, not a causal claim.")


def _content_decay(bundle: OpportunityEvaluationInput, records: list[dict[str, Any]], target_url: Optional[str], existing_urls: list[str]) -> Optional[RuleDecision]:
    gsc = _records(records, "GSC", target_url)
    sf = _records(records, "SF", target_url)
    windows = [window for record in gsc for window in (record.get("windows") or []) if isinstance(window, Mapping)]
    if not windows:
        return None
    if len(windows) < DECAY_WINDOWS:
        return _decision(bundle, "CONTENT_DECAY", "MONITOR", "SEO-DECAY-001", failed=["six_complete_months"], missing=["historical_traction"], required=["traction"], evidence=gsc + sf, target_url=target_url, existing_urls=existing_urls, rationale="Content decay requires six complete comparable GSC months; the available history is too short for a decay conclusion.", review_at=_review_at(bundle))
    ordered = sorted(windows, key=lambda window: str(window.get("period_end", "")))
    before = [_number(window.get("clicks")) for window in ordered[-4:-2]]
    recent = [_number(window.get("clicks")) for window in ordered[-2:]]
    if any(value is None for value in before + recent):
        return _decision(bundle, "CONTENT_DECAY", "MONITOR", "SEO-DECAY-001", failed=["complete_click_history"], missing=["traction"], required=["traction"], evidence=gsc + sf, target_url=target_url, existing_urls=existing_urls, rationale="Content decay requires complete clicks or impressions for each comparable month.", review_at=_review_at(bundle))
    baseline = sum(before) / len(before)
    current = sum(recent) / len(recent)
    if baseline <= 0 or current > baseline * (1 - DECAY_RELATIVE_CHANGE):
        return None
    return _decision(bundle, "CONTENT_DECAY", "UPDATE_EXISTING", "SEO-DECAY-001", matched=["six_month_window", "two_period_deterioration"], required=["traction"], evidence=gsc + sf, target_url=target_url, existing_urls=existing_urls, rationale="GSC clicks deteriorated across the required multi-period observation window; seasonality and content-change explanations require review.")


def _quick_win(bundle: OpportunityEvaluationInput, records: list[dict[str, Any]], target_url: Optional[str], existing_urls: list[str]) -> Optional[RuleDecision]:
    ahrefs = _records(records, "AHREFS", target_url)
    gsc = _records(records, "GSC", target_url)
    sf = _records(records, "SF", target_url)
    if not ahrefs or not gsc or not existing_urls:
        return None
    volume = next((_number(_value(record, "volume")) for record in ahrefs if _number(_value(record, "volume")) is not None), None)
    impressions = next((_number(_value(record, "impressions")) for record in gsc if _number(_value(record, "impressions")) is not None), None)
    position = next((_number(_value(record, "position")) for record in gsc if _number(_value(record, "position")) is not None), None)
    missing = []
    if volume is None:
        missing.append("demand")
    if impressions is None or position is None:
        missing.append("traction")
    if not sf:
        missing.append("technical")
    if not _mapping_confirmed(bundle):
        missing.append("mapping_review")
    # SERP is intentionally outside WP5's allowed source scope.
    missing.append("intent")
    if missing:
        return _decision(bundle, "QUICK_WIN", "UPDATE_EXISTING", "SEO-QUICK-001", matched=["existing_asset"], failed=["required_quick_win_conditions"], missing=missing, required=["demand", "traction", "technical", "intent"], evidence=ahrefs + gsc + sf, target_url=target_url, existing_urls=existing_urls, rationale="The topic has a possible existing-page headroom signal, but one or more required cross-source gates remain unresolved; keep it as a candidate for investigation.")
    return _decision(bundle, "QUICK_WIN", "UPDATE_EXISTING", "SEO-QUICK-001", matched=["market_demand", "ranking_headroom", "existing_asset", "technical_check"], required=["demand", "traction", "technical", "intent"], evidence=ahrefs + gsc + sf, target_url=target_url, existing_urls=existing_urls, rationale="Ahrefs demand, GSC ranking headroom, an existing canonical URL, and a non-blocking SF check support an update hypothesis; live SERP intent validation remains a later gate.")


def _content_gap_policy(bundle: OpportunityEvaluationInput, records: list[dict[str, Any]], target_url: Optional[str], existing_urls: list[str]) -> RuleDecision:
    return _decision(bundle, "CONTENT_GAP", "CREATE_NEW", "SEO-GAP-001", policy_gaps=["DERIVED_COMPETITIVE_GAP_POLICY_UNAPPROVED", "AHREFS_CONTENT_GAP_UNAVAILABLE"], required=["demand", "competitor", "inventory"], missing=["competitor", "inventory"], evidence=_records(records, "AHREFS"), target_url=None, existing_urls=[], rationale="Ahrefs dedicated Content Gap is unavailable and the proposal contract does not define an approved derived competitive gap; no Content Gap candidate is emitted.", status_hint="POLICY_GAP")


def evaluate_rules(bundle: OpportunityEvaluationInput) -> tuple[Optional[RuleDecision], list[str]]:
    records = _topic_records(bundle)
    existing_urls = _existing_urls(bundle)
    target_url = existing_urls[0] if existing_urls else None
    requested = bundle.requested_type
    if requested == "CONTENT_GAP":
        decision = _content_gap_policy(bundle, records, target_url, existing_urls)
        return decision, decision.policy_gaps
    ordered = []
    if requested in (None, "TECHNICAL_UNLOCK"):
        ordered.append(_technical_unlock(bundle, records, target_url, existing_urls))
    if requested in (None, "CTR_OPPORTUNITY"):
        ordered.append(_ctr_opportunity(bundle, records, target_url, existing_urls))
    if requested in (None, "CONTENT_DECAY"):
        ordered.append(_content_decay(bundle, records, target_url, existing_urls))
    if requested in (None, "QUICK_WIN"):
        ordered.append(_quick_win(bundle, records, target_url, existing_urls))
    for decision in ordered:
        if decision is not None:
            return decision, decision.policy_gaps
    if requested and requested not in {"DO_NOTHING", "CONTENT_GAP"}:
        return _decision(bundle, requested, "MONITOR", f"SEO-{requested}-UNAVAILABLE", missing=["required_evidence"], rationale=f"The {requested} rule did not have sufficient matching normalized evidence; monitor rather than manufacture an opportunity.", review_at=_review_at(bundle)), []
    fresh = _fresh(records)
    if not fresh:
        return _decision(bundle, "DO_NOTHING", "MONITOR", "SEO-DO-NOTHING-001", failed=["current_evidence_available"], missing=["required_evidence"], required=[], evidence=records, rationale="No current Ahrefs, GSC, or SF evidence is available for a defensible decision; monitor and collect the missing evidence.", review_at=_review_at(bundle)), []
    return _decision(bundle, "DO_NOTHING", "DO_NOTHING", "SEO-DO-NOTHING-001", matched=["no_supported_opportunity_rule"], required=[], evidence=fresh, rationale="Current cross-source evidence does not meet any supported opportunity gate; preserve a no-action result with a review date.", review_at=_review_at(bundle)), []


__all__ = ["DECAY_WINDOWS", "RULE_VERSION", "evaluate_rules"]
