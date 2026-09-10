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
    raise AttributeError(name)
