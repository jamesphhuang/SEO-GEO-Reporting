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
    "SERPValidationInput",
    "SERPValidationInputError",
    "SERPValidationResult",
    "SERPValidationStore",
    "evaluate_serp_validation",
    "validate_serp_validation",
    "serp_validation_preview",
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
    raise AttributeError(name)
