"""Offline source normalizers used by opportunity diagnostics.

Exports are lazy so importing a source adapter never creates a package-level
cycle through the opportunity package's diagnostic integrations.
"""

__all__ = [
    "GA4EvidenceInputError", "normalize_ga4_record", "normalize_ga4_records",
    "SERPCollectionPolicy", "SERPInputError", "collect_serp", "normalize_serp_snapshot", "resolve_query_ref",
    "WorkduoInputError", "normalize_sample_definition", "normalize_sample", "normalize_workduo_observation", "normalize_workduo", "normalize_workduo_records", "collect_workduo",
]


def __getattr__(name):
    if name in {"GA4EvidenceInputError", "normalize_ga4_record", "normalize_ga4_records"}:
        from .ga4_quality import GA4EvidenceInputError, normalize_ga4_record, normalize_ga4_records
        return {"GA4EvidenceInputError": GA4EvidenceInputError, "normalize_ga4_record": normalize_ga4_record, "normalize_ga4_records": normalize_ga4_records}[name]
    if name in {"SERPCollectionPolicy", "SERPInputError", "collect_serp", "normalize_serp_snapshot", "resolve_query_ref"}:
        from .serp import SERPCollectionPolicy, SERPInputError, collect_serp, normalize_serp_snapshot, resolve_query_ref
        return {"SERPCollectionPolicy": SERPCollectionPolicy, "SERPInputError": SERPInputError, "collect_serp": collect_serp, "normalize_serp_snapshot": normalize_serp_snapshot, "resolve_query_ref": resolve_query_ref}[name]
    if name in {"WorkduoInputError", "normalize_sample_definition", "normalize_sample", "normalize_workduo_observation", "normalize_workduo", "normalize_workduo_records", "collect_workduo"}:
        from .workduo import WorkduoInputError, normalize_sample_definition, normalize_sample, normalize_workduo_observation, normalize_workduo, normalize_workduo_records, collect_workduo
        return {"WorkduoInputError": WorkduoInputError, "normalize_sample_definition": normalize_sample_definition, "normalize_sample": normalize_sample, "normalize_workduo_observation": normalize_workduo_observation, "normalize_workduo": normalize_workduo, "normalize_workduo_records": normalize_workduo_records, "collect_workduo": collect_workduo}[name]
    raise AttributeError(name)
