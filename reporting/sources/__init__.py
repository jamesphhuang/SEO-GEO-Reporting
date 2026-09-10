"""Offline source normalizers used by opportunity diagnostics."""

from .ga4_quality import GA4EvidenceInputError, normalize_ga4_record, normalize_ga4_records

__all__ = ["GA4EvidenceInputError", "normalize_ga4_record", "normalize_ga4_records"]
