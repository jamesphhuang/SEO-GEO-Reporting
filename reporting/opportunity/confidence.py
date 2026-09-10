"""Deterministic confidence independent of ordinal opportunity score."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from .models import OpportunityEvaluationInput, RuleDecision
from .rules_seo import _source, _state


def assess_confidence(bundle: OpportunityEvaluationInput, decision: RuleDecision) -> dict[str, Any]:
    records = [dict(record) for record in bundle.evidence if str(record.get("evidence_id")) in set(decision.evidence_ids)]
    families = {_source(record) for record in records if _source(record)}
    stale = [str(record.get("evidence_id")) for record in records if _state(record) != "READY" or str(record.get("collection_status", "SUCCESS")).upper() not in {"SUCCESS", "READY"}]
    reasons: list[str] = []
    if decision.conflicting_evidence_refs:
        reasons.append("unresolved conflicting evidence")
        return {"confidence": "LOW", "validation_state": "CONFLICTING_EVIDENCE", "independent_family_count": len(families), "reasons": reasons}
    if stale:
        reasons.append("required evidence is stale or collection is incomplete")
    if decision.missing_evidence_roles:
        reasons.append("required evidence role is missing: " + ", ".join(decision.missing_evidence_roles))
    if len(families) < 2:
        reasons.append("fewer than two independent source families")
    if not bundle.entity_mappings_confirmed or bundle.mapping_review_state.upper() != "APPROVED":
        reasons.append("canonical mapping is not confirmed")
    if stale or decision.missing_evidence_roles or len(families) < 2 or not bundle.entity_mappings_confirmed:
        return {"confidence": "LOW", "validation_state": "INSUFFICIENT_EVIDENCE", "independent_family_count": len(families), "reasons": reasons}
    if bundle.alternative_explanations_addressed and bundle.mapping_review_state.upper() == "APPROVED":
        return {"confidence": "HIGH", "validation_state": "PASS", "independent_family_count": len(families), "reasons": ["fresh independent families, confirmed mappings, and alternatives addressed"]}
    return {"confidence": "MEDIUM", "validation_state": "PASS", "independent_family_count": len(families), "reasons": ["fresh independent families and confirmed mappings; business overlay or alternative explanation may remain"]}


__all__ = ["assess_confidence"]
