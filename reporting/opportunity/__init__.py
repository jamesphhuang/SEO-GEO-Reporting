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
]
