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

__all__ = [
    "ValidationError",
    "ValidationResult",
    "validate_ahrefs_scope",
    "validate_opportunity",
    "CandidateStore",
    "EvidenceStore",
    "ImmutableStoreError",
    "RunManifestStore",
]
