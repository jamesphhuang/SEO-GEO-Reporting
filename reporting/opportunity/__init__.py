"""Offline opportunity contract validation primitives."""

from .proposal_validation import (
    ValidationError,
    ValidationResult,
    validate_ahrefs_scope,
    validate_opportunity,
)
from .candidate_store import CandidateStore
from .evidence import EvidenceStore
from .store.errors import ImmutableStoreError
from .store.manifest import RunManifestStore
from .engine import OpportunityEngine, evaluate_topic
from .models import EngineInputError, EvaluationResult, OpportunityEvaluationInput
from .preview import candidate_preview
from .ga4_diagnostics import (
    GA4DiagnosticInput,
    GA4DiagnosticResult,
    GA4DiagnosticStore,
    evaluate_ga4_diagnostic,
    validate_ga4_diagnostic,
)
from .ga4_preview import diagnostic_preview

__all__ = [
    "ValidationError",
    "ValidationResult",
    "validate_ahrefs_scope",
    "validate_opportunity",
    "CandidateStore",
    "EvidenceStore",
    "ImmutableStoreError",
    "RunManifestStore",
    "EngineInputError",
    "EvaluationResult",
    "OpportunityEvaluationInput",
    "OpportunityEngine",
    "candidate_preview",
    "evaluate_topic",
    "GA4DiagnosticInput",
    "GA4DiagnosticResult",
    "GA4DiagnosticStore",
    "evaluate_ga4_diagnostic",
    "validate_ga4_diagnostic",
    "diagnostic_preview",
    "GEOFixedSampleInput",
    "GEODiagnosticInputError",
    "GEODiagnosticResult",
    "GEODiagnosticStore",
    "evaluate_geo_fixed_sample",
    "evaluate_geo_diagnostic",
    "validate_geo_diagnostic",
    "validate_geo",
    "geo_diagnostic_preview",
    "SERPValidationInput",
    "SERPValidationInputError",
    "SERPValidationResult",
    "SERPValidationStore",
    "evaluate_serp_validation",
    "validate_serp_validation",
    "serp_validation_preview",
    "OpportunityPreviewInput",
    "PreviewProjectionError",
    "project_opportunity_preview",
    "build_opportunity_preview",
    "render_opportunity_preview",
    "render_uat_preview",
    "validate_opportunity_preview",
    "HumanReviewInput",
    "HumanReviewResult",
    "HumanReviewStore",
    "create_human_review",
    "validate_human_review",
    "RecommendationBridgeResult",
    "RecommendationBridgeStore",
    "build_recommendation_bridge",
    "validate_recommendation_bridge",
    "project_review_status",
    "ImplementationAnchor",
    "MeasurementPlan",
    "MetricObservation",
    "OutcomeEvaluationResult",
    "OutcomeInputError",
    "OutcomeStore",
    "OutcomeTrackingInput",
    "OutcomeTrackingResult",
    "OutcomeTrackingStore",
    "ImplementationEvent",
    "create_implementation_anchor",
    "evaluate_outcome",
    "evaluate_outcomes",
    "expected_window",
    "validate_implementation_anchor",
    "validate_outcome_record",
    "validate_outcome",
    "outcome_preview",
    "checkpoint_preview",
    "project_outcome_preview",
    "render_checkpoint_preview",
    "render_outcome_preview",
]


def __getattr__(name):
    if name in {
        "SERPValidationInput", "SERPValidationInputError", "SERPValidationResult",
        "SERPValidationStore", "evaluate_serp_validation", "validate_serp_validation",
    }:
        from .serp_validation import (
            SERPValidationInput, SERPValidationInputError, SERPValidationResult,
            SERPValidationStore, evaluate_serp_validation, validate_serp_validation,
        )
        return {
            "SERPValidationInput": SERPValidationInput,
            "SERPValidationInputError": SERPValidationInputError,
            "SERPValidationResult": SERPValidationResult,
            "SERPValidationStore": SERPValidationStore,
            "evaluate_serp_validation": evaluate_serp_validation,
            "validate_serp_validation": validate_serp_validation,
        }[name]
    if name == "serp_validation_preview":
        from .serp_preview import serp_validation_preview
        return serp_validation_preview
    if name in {"GEOFixedSampleInput", "GEODiagnosticInputError", "GEODiagnosticResult", "GEODiagnosticStore", "evaluate_geo_fixed_sample", "evaluate_geo_diagnostic", "validate_geo_diagnostic", "validate_geo"}:
        from .geo_diagnostics import GEOFixedSampleInput, GEODiagnosticInputError, GEODiagnosticResult, GEODiagnosticStore, evaluate_geo_fixed_sample, evaluate_geo_diagnostic, validate_geo_diagnostic, validate_geo
        return {"GEOFixedSampleInput": GEOFixedSampleInput, "GEODiagnosticInputError": GEODiagnosticInputError, "GEODiagnosticResult": GEODiagnosticResult, "GEODiagnosticStore": GEODiagnosticStore, "evaluate_geo_fixed_sample": evaluate_geo_fixed_sample, "evaluate_geo_diagnostic": evaluate_geo_diagnostic, "validate_geo_diagnostic": validate_geo_diagnostic, "validate_geo": validate_geo}[name]
    if name == "geo_diagnostic_preview":
        from .geo_preview import geo_diagnostic_preview
        return geo_diagnostic_preview
    if name in {"OpportunityPreviewInput", "PreviewProjectionError", "project_opportunity_preview", "build_opportunity_preview", "render_opportunity_preview", "render_uat_preview", "validate_opportunity_preview"}:
        from .report_projection import (
            OpportunityPreviewInput,
            PreviewProjectionError,
            build_opportunity_preview,
            project_opportunity_preview,
            render_opportunity_preview,
            render_uat_preview,
            validate_opportunity_preview,
        )
        return {
            "OpportunityPreviewInput": OpportunityPreviewInput,
            "PreviewProjectionError": PreviewProjectionError,
            "project_opportunity_preview": project_opportunity_preview,
            "build_opportunity_preview": build_opportunity_preview,
            "render_opportunity_preview": render_opportunity_preview,
            "render_uat_preview": render_uat_preview,
            "validate_opportunity_preview": validate_opportunity_preview,
        }[name]
    if name in {"HumanReviewInput", "HumanReviewResult", "HumanReviewStore", "create_human_review", "validate_human_review"}:
        from .review import HumanReviewInput, HumanReviewResult, HumanReviewStore, create_human_review, validate_human_review
        return {"HumanReviewInput": HumanReviewInput, "HumanReviewResult": HumanReviewResult, "HumanReviewStore": HumanReviewStore, "create_human_review": create_human_review, "validate_human_review": validate_human_review}[name]
    if name in {"RecommendationBridgeResult", "RecommendationBridgeStore", "build_recommendation_bridge", "validate_recommendation_bridge", "project_review_status"}:
        from .review_bridge import RecommendationBridgeResult, RecommendationBridgeStore, build_recommendation_bridge, validate_recommendation_bridge, project_review_status
        return {"RecommendationBridgeResult": RecommendationBridgeResult, "RecommendationBridgeStore": RecommendationBridgeStore, "build_recommendation_bridge": build_recommendation_bridge, "validate_recommendation_bridge": validate_recommendation_bridge, "project_review_status": project_review_status}[name]
    if name in {"ImplementationAnchor", "ImplementationEvent", "MeasurementPlan", "MetricObservation", "OutcomeEvaluationResult", "OutcomeInputError", "OutcomeStore", "OutcomeTrackingInput", "OutcomeTrackingResult", "OutcomeTrackingStore", "create_implementation_anchor", "evaluate_outcome", "evaluate_outcomes", "expected_window", "validate_implementation_anchor", "validate_outcome", "validate_outcome_record"}:
        from .outcomes import (ImplementationAnchor, ImplementationEvent, MeasurementPlan, MetricObservation, OutcomeEvaluationResult, OutcomeInputError, OutcomeStore, OutcomeTrackingInput, OutcomeTrackingResult, OutcomeTrackingStore, create_implementation_anchor, evaluate_outcome, evaluate_outcomes, expected_window, validate_implementation_anchor, validate_outcome, validate_outcome_record)
        return {"ImplementationAnchor": ImplementationAnchor, "ImplementationEvent": ImplementationEvent, "MeasurementPlan": MeasurementPlan, "MetricObservation": MetricObservation, "OutcomeEvaluationResult": OutcomeEvaluationResult, "OutcomeInputError": OutcomeInputError, "OutcomeStore": OutcomeStore, "OutcomeTrackingInput": OutcomeTrackingInput, "OutcomeTrackingResult": OutcomeTrackingResult, "OutcomeTrackingStore": OutcomeTrackingStore, "create_implementation_anchor": create_implementation_anchor, "evaluate_outcome": evaluate_outcome, "evaluate_outcomes": evaluate_outcomes, "expected_window": expected_window, "validate_implementation_anchor": validate_implementation_anchor, "validate_outcome": validate_outcome, "validate_outcome_record": validate_outcome_record}[name]
    if name in {"outcome_preview", "checkpoint_preview", "project_outcome_preview", "render_checkpoint_preview", "render_outcome_preview"}:
        from .outcome_preview import checkpoint_preview, outcome_preview, project_outcome_preview, render_checkpoint_preview, render_outcome_preview
        return {"outcome_preview": outcome_preview, "checkpoint_preview": checkpoint_preview, "project_outcome_preview": project_outcome_preview, "render_checkpoint_preview": render_checkpoint_preview, "render_outcome_preview": render_outcome_preview}[name]
    raise AttributeError(name)
