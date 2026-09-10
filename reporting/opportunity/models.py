"""Small value objects for the offline SEO opportunity engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional


SUPPORTED_SOURCES = frozenset({"AHREFS", "GSC", "SF"})
SOURCE_CLASSES = {
    "AHREFS": "THIRD_PARTY_ESTIMATE",
    "GSC": "FIRST_PARTY_SEARCH_ACTUAL",
    "SF": "TECHNICAL_CRAWL_EVIDENCE",
}


class EngineInputError(ValueError):
    """Raised when an evaluation bundle is not safe to evaluate."""


@dataclass(frozen=True)
class OpportunityEvaluationInput:
    """All inputs needed for one deterministic evaluation run.

    Evidence is already normalized and immutable. The engine never calls a
    source adapter; callers must pass a registry and evidence revisions.
    """

    project_scope_id: str
    evaluation_period: str
    decision_at: str
    topic: Mapping[str, Any]
    registry: Mapping[str, Any]
    evidence: tuple[Mapping[str, Any], ...]
    environment: str = "preview"
    mapping_review_state: str = "APPROVED"
    entity_mappings_confirmed: bool = True
    alternative_explanations_addressed: bool = False
    rule_version: str = "rules-proposal-1"
    score_profile_version: str = "scoring-proposal-1"
    freshness_policy_version: str = "freshness-proposal-1"
    requested_type: Optional[str] = None

    @classmethod
    def from_mapping(cls, bundle: Mapping[str, Any]) -> "OpportunityEvaluationInput":
        if not isinstance(bundle, Mapping):
            raise EngineInputError("evaluation bundle must be a mapping")
        topic = bundle.get("topic")
        registry = bundle.get("registry")
        raw_evidence = bundle.get("evidence", ())
        if isinstance(raw_evidence, Mapping):
            raw_evidence = tuple(raw_evidence.values())
        if not isinstance(raw_evidence, (list, tuple)):
            raise EngineInputError("evidence must be a list or mapping")
        if isinstance(topic, str):
            topic = {"topic_id": topic}
        if not isinstance(topic, Mapping):
            raise EngineInputError("topic must be a mapping or topic id")
        if not isinstance(registry, Mapping):
            raise EngineInputError("registry is required for canonical topic resolution")
        values = dict(bundle)
        required = ("project_scope_id", "evaluation_period", "decision_at")
        missing = [name for name in required if not values.get(name)]
        if missing:
            raise EngineInputError("missing evaluation fields: " + ", ".join(missing))
        if values.get("environment", "preview") not in {"preview", "uat"}:
            raise EngineInputError("engine environment must be preview or uat")
        return cls(
            project_scope_id=str(values["project_scope_id"]),
            evaluation_period=str(values["evaluation_period"]),
            decision_at=str(values["decision_at"]),
            topic=dict(topic),
            registry=registry,
            evidence=tuple(dict(item) for item in raw_evidence if isinstance(item, Mapping)),
            environment=str(values.get("environment", "preview")),
            mapping_review_state=str(values.get("mapping_review_state", topic.get("mapping_review_state", "APPROVED"))),
            entity_mappings_confirmed=bool(values.get("entity_mappings_confirmed", True)),
            alternative_explanations_addressed=bool(values.get("alternative_explanations_addressed", False)),
            rule_version=str(values.get("rule_version", "rules-proposal-1")),
            score_profile_version=str(values.get("score_profile_version", "scoring-proposal-1")),
            freshness_policy_version=str(values.get("freshness_policy_version", "freshness-proposal-1")),
            requested_type=values.get("requested_type"),
        )


@dataclass
class RuleDecision:
    opportunity_type: str
    recommended_action: str
    rule_id: str
    matched_conditions: list[str] = field(default_factory=list)
    failed_conditions: list[str] = field(default_factory=list)
    missing_evidence_roles: list[str] = field(default_factory=list)
    required_evidence_roles: list[str] = field(default_factory=list)
    conflicting_evidence_refs: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    target_url: Optional[str] = None
    existing_urls: list[str] = field(default_factory=list)
    policy_gaps: list[str] = field(default_factory=list)
    rationale: str = ""
    review_at: Optional[str] = None
    status_hint: str = "CANDIDATE"

    @property
    def validation_state(self) -> str:
        if self.conflicting_evidence_refs:
            return "CONFLICTING_EVIDENCE"
        if self.missing_evidence_roles or self.failed_conditions:
            return "INSUFFICIENT_EVIDENCE"
        return "PASS"


@dataclass
class EvaluationResult:
    candidate: Optional[dict[str, Any]]
    proposal: Optional[dict[str, Any]]
    decision: Optional[RuleDecision]
    validation: Any
    persisted: bool = False
    persistence_error: Optional[str] = None
    policy_gaps: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return bool(self.validation and self.validation.is_valid)

    def as_dict(self) -> dict[str, Any]:
        return {
            "candidate": self.candidate,
            "proposal": self.proposal,
            "decision": self.decision.__dict__ if self.decision else None,
            "validation": self.validation.as_dict() if self.validation else None,
            "persisted": self.persisted,
            "persistence_error": self.persistence_error,
            "policy_gaps": list(self.policy_gaps),
        }


__all__ = [
    "EngineInputError",
    "EvaluationResult",
    "OpportunityEvaluationInput",
    "RuleDecision",
    "SOURCE_CLASSES",
    "SUPPORTED_SOURCES",
]
