"""Named rule surface for the WP8 GEO fixed-sample layer.

The implementation lives in :mod:`geo_diagnostics`; this module keeps the
roadmap's explicit rules entry point stable for callers and reviewers.
"""

from .geo_diagnostics import (
    CAPABILITY_STATES,
    CURRENT_MAX_AGE_DAYS,
    GEOFixedSampleInput,
    GEODiagnosticResult,
    evaluate_geo_fixed_sample,
    evaluate_geo_diagnostic,
)

__all__ = ["CAPABILITY_STATES", "CURRENT_MAX_AGE_DAYS", "GEOFixedSampleInput", "GEODiagnosticResult", "evaluate_geo_fixed_sample", "evaluate_geo_diagnostic"]
