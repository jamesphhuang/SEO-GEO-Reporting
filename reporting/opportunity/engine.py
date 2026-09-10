"""Offline SEO opportunity evaluation and Candidate Store integration.

The engine is intentionally a pure, replayable boundary.  It accepts already
normalised evidence revisions, evaluates the versioned WP5 rules, validates the
proposal through the WP1 contract, and optionally appends an immutable
Candidate Store record.  No source adapter or production output is called.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any, Mapping, Optional

from .candidate_store import CandidateStore
from .confidence import assess_confidence
from .models import EngineInputError, EvaluationResult, OpportunityEvaluationInput, RuleDecision
from .proposal_validation import ValidationError, ValidationResult, candidate_content_hash, validate_opportunity
from .rules_seo import evaluate_rules
from .scoring import score_candidate
from .store.registry import RegistryLookup
from .store.serialization import canonical_json, content_hash as store_content_hash


CONTRACT_VERSION = "1.0.0-proposal"
MAPPING_VERSION = "mapping.v1"


def _topic_id(bundle: OpportunityEvaluationInput) -> str:
    value = bundle.topic.get("topic_id") or bundle.topic.get("topic_cluster_id")
    if not isinstance(value, str) or not value:
        raise EngineInputError("topic requires topic_id")
    return value


def _topic_row(bundle: OpportunityEvaluationInput) -> dict[str, Any]:
    topic_id = _topic_id(bundle)
    rows = (bundle.registry.get("entities") or {}).get("TOPIC", [])
    for row in rows:
        if row.get("topic_id") == topic_id:
            return dict(row)
    raise EngineInputError(f"topic is not present in canonical registry: {topic_id}")


def _keyword(bundle: OpportunityEvaluationInput, topic: Mapping[str, Any]) -> Optional[str]:
    ref = topic.get("primary_keyword_ref")
    for row in (bundle.registry.get("entities") or {}).get("KEYWORD", []):
        if ref and row.get("keyword_id") == ref:
            return str(row.get("text") or row.get("normalized_text"))
    value = bundle.topic.get("primary_keyword")
    return str(value) if value else None


def _business_theme(bundle: OpportunityEvaluationInput, topic: Mapping[str, Any]) -> str:
    value = bundle.topic.get("business_theme")
    if value:
        return str(value)
    refs = topic.get("business_theme_refs") or []
    for row in (bundle.registry.get("entities") or {}).get("BUSINESS_THEME", []):
        if row.get("business_theme_id") in refs or row.get("theme_id") in refs:
            name = row.get("theme_id") or row.get("display_name")
            if name:
                return str(name)
    return "UNMAPPED"


def _asset_type(bundle: OpportunityEvaluationInput, topic: Mapping[str, Any]) -> str:
    value = bundle.topic.get("asset_type") or topic.get("asset_type")
    if value:
        return str(value)
    name = str(topic.get("topic_name", ""))
    return "COMPARISON" if "比較" in name else "ARTICLE"


def _iso_date(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    return str(value).replace("Z", "+00:00")[:10]


def _candidate_id(bundle: OpportunityEvaluationInput, topic: Mapping[str, Any], decision: RuleDecision) -> str:
    existing = list(decision.existing_urls)
    target_asset_key = decision.target_url or "|".join(existing) or _topic_id(bundle)
    seed = {
        "project_scope_id": bundle.project_scope_id,
        "topic_cluster_id": _topic_id(bundle),
        "primary_intent": topic.get("search_intent") or bundle.topic.get("intent") or "UNKNOWN",
        "primary_action": decision.recommended_action,
        "target_asset_key": target_asset_key,
    }
    return "OPP_" + hashlib.sha256(canonical_json(seed).encode("utf-8")).hexdigest()[:24]


def _selected_records(bundle: OpportunityEvaluationInput, decision: RuleDecision) -> list[dict[str, Any]]:
    wanted = set(decision.evidence_ids)
    return sorted(
        [dict(record) for record in bundle.evidence if str(record.get("evidence_id")) in wanted],
        key=lambda record: str(record.get("evidence_id")),
    )


def _fresh(record: Mapping[str, Any]) -> bool:
    return str(record.get("freshness_state", "")).upper() == "READY" and str(record.get("collection_status", "SUCCESS")).upper() in {"SUCCESS", "READY"}


def _source_field(source: str) -> str:
    return {
        "AHREFS": "ahrefs_evidence_ref",
        "GSC": "gsc_evidence_ref",
        "SF": "sf_evidence_ref",
    }.get(source, "")


def _augment_decision(decision: RuleDecision, records: list[dict[str, Any]]) -> None:
    stale = [str(record["evidence_id"]) for record in records if not _fresh(record)]
    conflicts = [str(record["evidence_id"]) for record in records if record.get("conflict") or str(record.get("freshness_state", "")).upper() == "CONFLICTING"]
    if stale and "freshness" not in decision.missing_evidence_roles:
        decision.missing_evidence_roles.append("freshness")
    decision.conflicting_evidence_refs = sorted(set(decision.conflicting_evidence_refs) | set(conflicts))
    if conflicts:
        decision.failed_conditions.append("conflicting_evidence_requires_review")
    decision.missing_evidence_roles = sorted(set(decision.missing_evidence_roles))
    decision.failed_conditions = sorted(set(decision.failed_conditions))


def _validator_context(bundle: OpportunityEvaluationInput, records: list[dict[str, Any]]) -> dict[str, Any]:
    evidence: dict[str, dict[str, Any]] = {}
    roles_by_source = {"AHREFS": ["demand"], "GSC": ["traction"], "SF": ["technical", "effort"]}
    for record in records:
        source = str(record.get("source", "")).upper()
        fresh = _fresh(record)
        projected = dict(record)
        projected.update(
            family=source,
            source=source,
            source_class=record.get("source_class"),
            roles=list(record.get("roles") or roles_by_source.get(source, [])),
            freshness_state="FRESH" if fresh else "STALE",
            collection_status="READY" if fresh else str(record.get("collection_status", "FAILED")),
            as_of=record.get("as_of") or record.get("period_end"),
            conflict=bool(record.get("conflict") or str(record.get("freshness_state", "")).upper() == "CONFLICTING"),
        )
        evidence[str(record["evidence_id"])] = projected
    return {
        "evidence": evidence,
        "decision_at": datetime.fromisoformat(bundle.decision_at.replace("Z", "+00:00")),
        "entity_mappings_confirmed": bundle.entity_mappings_confirmed and bundle.mapping_review_state.upper() == "APPROVED",
        "alternative_explanations_addressed": bundle.alternative_explanations_addressed,
    }


def _input_signature(bundle: OpportunityEvaluationInput, decision: RuleDecision, records: list[dict[str, Any]]) -> str:
    value = {
        "topic": _topic_id(bundle),
        "rule": decision.rule_id,
        "action": decision.recommended_action,
        "target_url": decision.target_url,
        "evidence": [
            {"evidence_id": record.get("evidence_id"), "revision": record.get("revision"), "content_hash": record.get("content_hash")}
            for record in records
        ],
    }
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _proposal(
    bundle: OpportunityEvaluationInput,
    topic: Mapping[str, Any],
    decision: RuleDecision,
    score: Mapping[str, Any],
    confidence: Mapping[str, Any],
    records: list[dict[str, Any]],
    *,
    revision: int,
    supersedes: Optional[int],
) -> dict[str, Any]:
    sources = {str(record.get("source", "")).upper(): str(record["evidence_id"]) for record in records}
    evidence_refs = sorted({str(record["evidence_id"]) for record in records})
    families = {str(record.get("source", "")).upper() for record in records if record.get("source")}
    action = decision.recommended_action
    existing_urls = list(decision.existing_urls)
    existing_url = existing_urls[0] if existing_urls else None
    target_url = decision.target_url
    status = "CANDIDATE" if len(families) >= 2 else "DISCOVERED"
    validation_state = str(confidence["validation_state"])
    if decision.conflicting_evidence_refs:
        validation_state = "CONFLICTING_EVIDENCE"
    required = sorted(set(decision.required_evidence_roles))
    missing = sorted(set(decision.missing_evidence_roles))
    if validation_state == "INSUFFICIENT_EVIDENCE" and not missing:
        missing = ["required_evidence"]
    if decision.opportunity_type == "DO_NOTHING" and action == "DO_NOTHING" and missing:
        action = "MONITOR"
    period = bundle.evaluation_period
    created_at = bundle.decision_at
    payload: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "opportunity_id": _candidate_id(bundle, topic, decision),
        "revision": revision,
        "supersedes_opportunity_revision": supersedes,
        "environment": bundle.environment,
        "period": period,
        "topic_cluster_id": _topic_id(bundle),
        "topic": str(topic.get("topic_name") or topic.get("normalized_name") or _topic_id(bundle)),
        "primary_keyword": _keyword(bundle, topic),
        "intent": str(topic.get("search_intent") or bundle.topic.get("intent") or "UNKNOWN"),
        "funnel": str(topic.get("funnel_stage") or bundle.topic.get("funnel") or "UNKNOWN"),
        "business_theme": _business_theme(bundle, topic),
        "asset_type": _asset_type(bundle, topic),
        "opportunity_type": decision.opportunity_type,
        "existing_url": existing_url,
        "existing_urls": existing_urls,
        "target_url": target_url,
        "recommended_action": action,
        "evidence_refs": evidence_refs,
        "business_evidence_ref": None,
        "ahrefs_evidence_ref": sources.get("AHREFS"),
        "gsc_evidence_ref": sources.get("GSC"),
        "ga4_evidence_ref": None,
        "sf_evidence_ref": sources.get("SF"),
        "serp_evidence_ref": None,
        "geo_evidence_ref": None,
        "crux_evidence_ref": None,
        **{name: score.get(name) for name in ("demand_score", "traction_score", "business_score", "attainability_score", "geo_score", "execution_score")},
        "score_profile": score["score_profile"],
        "score_profile_version": score["score_profile_version"],
        "opportunity_score": score["opportunity_score"],
        "score_lower_bound": score["score_lower_bound"],
        "score_upper_bound": score["score_upper_bound"],
        "score_explanations": score["score_explanations"],
        "confidence": confidence["confidence"],
        "evidence_count": len(evidence_refs),
        "independent_family_count": len(families),
        "status": status,
        "validation_state": validation_state,
        "review_state": "NOT_SUBMITTED",
        "review_event_ref": None,
        "business_override_ref": None,
        "scope_approval_ref": None,
        "measurement_plan_ref": None,
        "effort_days": None,
        "serp_state": "SERP_NOT_CHECKED",
        "required_evidence_roles": required,
        "missing_evidence_roles": missing,
        "conflicting_evidence_refs": sorted(set(decision.conflicting_evidence_refs)),
        "rule_ids": [decision.rule_id],
        "rule_version": bundle.rule_version,
        "mapping_version": str(bundle.registry.get("mapping_version") or MAPPING_VERSION),
        "freshness_policy_version": bundle.freshness_policy_version,
        "related_opportunity_ids": [],
        "dependency_ids": sorted(set(decision.policy_gaps)),
        "rationale": decision.rationale,
        "review_at": _iso_date(decision.review_at),
        "created_at": created_at,
        "updated_at": created_at,
    }
    payload["content_hash"] = candidate_content_hash(payload)
    return payload


def _storage_record(proposal: Mapping[str, Any], records: list[dict[str, Any]], signature: str) -> dict[str, Any]:
    refs = [
        {"evidence_id": record["evidence_id"], "revision": int(record["revision"]), "content_hash": record["content_hash"]}
        for record in records
    ]
    value = {
        "record_type": "CANDIDATE",
        "candidate_id": proposal["opportunity_id"],
        "revision": proposal["revision"],
        "topic_ref": {"entity_type": "TOPIC", "entity_id": proposal["topic_cluster_id"]},
        "evidence_refs": refs,
        "status": proposal["status"],
        "review_state": proposal["review_state"],
        "opportunity_type": proposal["opportunity_type"],
        "recommended_action": proposal["recommended_action"],
        "target_url": proposal["target_url"],
        "existing_urls": proposal["existing_urls"],
        "score": proposal["opportunity_score"],
        "score_lower_bound": proposal["score_lower_bound"],
        "score_upper_bound": proposal["score_upper_bound"],
        "confidence": proposal["confidence"],
        "validation_state": proposal["validation_state"],
        "rule_ids": proposal["rule_ids"],
        "rationale": proposal["rationale"],
        "proposal_content_hash": proposal["content_hash"],
        "input_signature": signature,
        "created_at": proposal["created_at"],
    }
    if proposal["revision"] > 1:
        value["supersedes_candidate_id"] = proposal["opportunity_id"]
        value["supersedes_revision"] = proposal["revision"] - 1
    return value


class OpportunityEngine:
    """Evaluate one synthetic/offline bundle and optionally persist a candidate."""

    def __init__(self, *, candidate_store: Optional[CandidateStore] = None, persist: bool = False) -> None:
        self.candidate_store = candidate_store
        self.persist = persist

    def evaluate(self, bundle: OpportunityEvaluationInput | Mapping[str, Any]) -> EvaluationResult:
        if not isinstance(bundle, OpportunityEvaluationInput):
            bundle = OpportunityEvaluationInput.from_mapping(bundle)
        lookup = RegistryLookup(bundle.registry)
        topic = _topic_row(bundle)
        lookup.require("TOPIC", _topic_id(bundle), "topic")
        decision, policy_gaps = evaluate_rules(bundle)
        if decision is None:
            raise EngineInputError("SEO rule evaluation returned no decision")
        records = _selected_records(bundle, decision)
        _augment_decision(decision, records)
        if policy_gaps:
            validation = ValidationResult(errors=[ValidationError(code="POLICY_GAP", field="opportunity_type", message="No candidate is emitted while the requested policy gap remains unresolved.")])
            return EvaluationResult(candidate=None, proposal=None, decision=decision, validation=validation, policy_gaps=sorted(set(policy_gaps)))
        score = score_candidate(bundle, decision)
        confidence = assess_confidence(bundle, decision)
        signature = _input_signature(bundle, decision, records)
        revision = 1
        supersedes = None
        candidate_id = _candidate_id(bundle, topic, decision)
        if self.candidate_store is not None:
            history = self.candidate_store.history(candidate_id)
            if history:
                latest = history[-1]
                if latest.get("input_signature") == signature:
                    revision = int(latest["revision"])
                else:
                    revision = int(latest["revision"]) + 1
                    supersedes = revision - 1
        proposal = _proposal(bundle, topic, decision, score, confidence, records, revision=revision, supersedes=supersedes)
        validation = validate_opportunity(proposal, context=_validator_context(bundle, records))
        if not validation.is_valid:
            return EvaluationResult(candidate=None, proposal=proposal, decision=decision, validation=validation, policy_gaps=[])
        persisted = False
        persistence_error = None
        storage_preview = _storage_record(proposal, records, signature)
        storage_preview["content_hash"] = store_content_hash(storage_preview)
        candidate: Optional[dict[str, Any]] = storage_preview
        if self.persist:
            if self.candidate_store is None:
                persistence_error = "persist=True requires candidate_store"
            else:
                try:
                    stored = self.candidate_store.append_candidate(storage_preview)
                    persisted = True
                    candidate = stored
                except Exception as exc:  # Store errors are returned as a reviewable result, never hidden.
                    persistence_error = f"{type(exc).__name__}: {exc}"
        return EvaluationResult(candidate=candidate, proposal=proposal, decision=decision, validation=validation, persisted=persisted, persistence_error=persistence_error)


def evaluate_topic(bundle: OpportunityEvaluationInput | Mapping[str, Any], *, candidate_store: Optional[CandidateStore] = None, persist: bool = False) -> EvaluationResult:
    return OpportunityEngine(candidate_store=candidate_store, persist=persist).evaluate(bundle)


__all__ = ["OpportunityEngine", "evaluate_topic"]
