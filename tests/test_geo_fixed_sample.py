import copy
import json
import tempfile
import unittest
from pathlib import Path

from reporting.opportunity import EvidenceStore
from reporting.opportunity.geo_diagnostics import GEODiagnosticStore, evaluate_geo_fixed_sample, validate_geo_diagnostic
from reporting.opportunity.geo_preview import geo_diagnostic_preview
from reporting.sources.workduo import WorkduoInputError, normalize_sample_definition, normalize_workduo_observation


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "tests/fixtures/opportunity_registry/synthetic_registry.json").read_text())
FIXTURES = json.loads((ROOT / "tests/fixtures/opportunity_geo/scenarios.json").read_text())
PROMPT = "PROMPT_3ef40bd7136bf0938928a2b7"
TOPIC = "TOPIC_ECOMMERCE_PLATFORM_COMPARISON"
URL = "https://shopline.tw/example/ecommerce-platform/"


class GEOFixedSampleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.sample = normalize_sample_definition(FIXTURES["sample"], REGISTRY)
        self.evidence_store = EvidenceStore(self.temp.name, registry=REGISTRY)
        candidate = self.evidence_store.append_evidence({"record_type": "EVIDENCE", "evidence_id": "WP8_CANDIDATE", "revision": 1, "source": "GSC", "source_class": "FIRST_PARTY_SEARCH_ACTUAL", "metric": "clicks", "value": 10, "unit": "count", "period_start": "2026-09-01", "period_end": "2026-09-07", "as_of": "2026-09-08", "retrieved_at": "2026-09-08T03:00:00+00:00", "freshness_state": "READY", "collection_status": "SUCCESS", "source_reference": "synthetic-wp8", "contract_version": "synthetic-wp8.v1", "entity_refs": [{"entity_type": "URL", "entity_id": "URL_cccdba54dc688385652d561d"}], "topic_refs": [TOPIC], "created_at": "2026-09-08T03:00:00+00:00"})
        self.candidate_ref = {"evidence_id": candidate["evidence_id"], "revision": 1, "content_hash": candidate["content_hash"]}

    def tearDown(self): self.temp.cleanup()

    def raw(self, name="A_stable", **overrides):
        scenario = copy.deepcopy(FIXTURES["scenarios"][name]); scenario.update(overrides)
        version = scenario.get("sample_version", "v1")
        row = {"sample_id": "WP8_FIXED_TW", "sample_version": version, "sample_revision": scenario.get("sample_revision", 1), "prompt_ref": {"prompt_id": scenario.get("prompt_id", PROMPT)}, "topic_id": scenario.get("topic_id", TOPIC), "market": "TW", "locale": "zh-TW", "platform": "synthetic", "model_scope": "UNKNOWN", "mention_state": scenario.get("mention_state", "OBSERVED"), "citation_state": scenario.get("citation_state", "NOT_OBSERVED"), "period_start": scenario.get("period_start", "2026-09-01"), "period_end": scenario.get("period_end", "2026-09-07"), "as_of": scenario.get("as_of", "2026-09-09"), "retrieved_at": scenario.get("retrieved_at", "2026-09-10T03:00:00+00:00"), "freshness_state": scenario.get("freshness_state", "READY"), "collection_status": scenario.get("collection_status", "SUCCESS"), "source_reference": "synthetic-wp8", "provider_methodology": "fixed_prompt_cohort"}
        if scenario.get("owned", False): row["owned_url"] = URL
        if scenario.get("competitor_domain"): row["competitor_domain"] = scenario["competitor_domain"]
        if scenario.get("citation_url"): row["citation_url"] = scenario["citation_url"]
        return row

    def stored(self, name="A_stable", **overrides):
        sample = self.sample
        if FIXTURES["scenarios"][name].get("sample_definition_revision") == 2:
            sample = normalize_sample_definition({**FIXTURES["sample"], "sample_version": "v2", "revision": 2}, REGISTRY)
        return self.evidence_store.append_evidence(normalize_workduo_observation(self.raw(name, **overrides), REGISTRY, sample_definition=sample))

    def inp(self, rows, **overrides):
        value = {"candidate_id": "CAND_WP8_001", "candidate_revision": 1, "topic_cluster_id": TOPIC, "target_url": URL, "evaluation_period": "2026-09", "decision_at": "2026-09-10T04:00:00+00:00", "registry": REGISTRY, "sample_definition": self.sample, "geo_evidence": rows, "candidate_evidence_refs": [self.candidate_ref], "wp5_score": 73, "wp5_confidence": "LOW", "candidate_status": "CANDIDATE", "candidate_review_state": "NOT_REVIEWED"}
        value.update(overrides); return value

    def test_sample_definition_is_versioned_and_exact(self):
        self.assertEqual(self.sample["source_role"], "MONITORED_FIXED_SAMPLE")
        with self.assertRaises(WorkduoInputError): normalize_sample_definition({**FIXTURES["sample"], "prompt_refs": [{"prompt_id": "PROMPT_UNKNOWN"}]}, REGISTRY)

    def test_observation_pins_prompt_topic_scope_and_hash(self):
        row = self.stored(); self.assertEqual(row["source_class"], "MONITORED_GEO_SAMPLE"); self.assertEqual(row["observation"]["prompt_ref"]["entity_id"], PROMPT); self.assertEqual(len(row["content_hash"]), 64)

    def test_explicit_date_and_timezone_aware_datetime(self):
        with self.assertRaises(WorkduoInputError): normalize_workduo_observation(self.raw(period_start="2026-99-01"), REGISTRY, sample_definition=self.sample)
        with self.assertRaises(WorkduoInputError): normalize_workduo_observation(self.raw(retrieved_at="2026-09-10T03:00:00"), REGISTRY, sample_definition=self.sample)

    def test_stable_and_decline_are_distinct_visibility_states(self):
        stable = evaluate_geo_fixed_sample(self.inp([self.stored("A_stable")])).diagnostic
        decline = evaluate_geo_fixed_sample(self.inp([self.stored("B_decline")])).diagnostic
        self.assertEqual(stable["owned_visibility"], "PRESENT"); self.assertEqual(decline["owned_visibility"], "ABSENT")

    def test_sample_revision_change_blocks_comparison(self):
        row = self.stored("D_sample_revision_changed")
        diagnostic = evaluate_geo_fixed_sample(self.inp([row])).diagnostic
        self.assertIn("COMPARABILITY_GAP", diagnostic["conflicts"])

    def test_missing_and_stale_never_become_zero_or_current(self):
        missing = evaluate_geo_fixed_sample(self.inp([self.stored("E_missing")])).diagnostic
        stale = evaluate_geo_fixed_sample(self.inp([self.stored("F_stale")])).diagnostic
        self.assertIn("geo_observation", missing["missing_evidence"]); self.assertIn("fresh_current_geo_evidence", stale["missing_evidence"]); self.assertNotEqual(stale["freshness"][0]["is_current"], True)

    def test_mention_and_citation_are_independent(self):
        row = self.stored("H_mention_without_citation"); diagnostic = evaluate_geo_fixed_sample(self.inp([row])).diagnostic
        self.assertEqual(diagnostic["mention_state"], "OBSERVED"); self.assertEqual(diagnostic["citation_state"], "NOT_OBSERVED")
        citation = evaluate_geo_fixed_sample(self.inp([self.stored("I_citation_present")])).diagnostic
        self.assertEqual(citation["citation_state"], "OBSERVED")

    def test_capability_gap_is_explicit(self):
        diagnostic = evaluate_geo_fixed_sample(self.inp([self.stored("G_no_citation_capability")])).diagnostic
        self.assertIn("CAPABILITY_GAP", diagnostic["conflicts"]); self.assertEqual(diagnostic["citation_state"], "NOT_AVAILABLE")

    def test_unknown_competitor_does_not_create_entity(self):
        diagnostic = evaluate_geo_fixed_sample(self.inp([self.stored("L_unknown_competitor")])).diagnostic
        self.assertIn("UNKNOWN_COMPETITOR_DOMAIN", diagnostic["conflicts"]); self.assertEqual(diagnostic["competitor_presence"], [])

    def test_unmapped_prompt_and_topic_fail_closed(self):
        unknown_prompt = self.raw("J_unmapped_prompt")
        with self.assertRaises(WorkduoInputError): normalize_workduo_observation(unknown_prompt, REGISTRY, sample_definition=self.sample)
        unknown_topic = self.raw("K_unmapped_topic")
        with self.assertRaises(WorkduoInputError): normalize_workduo_observation(unknown_topic, REGISTRY, sample_definition=self.sample)

    def test_serp_conflict_is_preserved_and_score_unchanged(self):
        diagnostic = evaluate_geo_fixed_sample(self.inp([self.stored("M_serp_strong_geo_weak")], serp_validation={"validation_status": "SERP_VALIDATED"})).diagnostic
        self.assertIn("CROSS_CHANNEL_CONFLICT", diagnostic["conflicts"]); self.assertEqual(diagnostic["wp5_score"], 73); self.assertFalse(diagnostic["approval_transition_allowed"])

    def test_ga4_is_context_only(self):
        diagnostic = evaluate_geo_fixed_sample(self.inp([self.stored("N_ga4_healthy_geo_weak")], ga4_diagnostic={"diagnostic_status": "QUALITY_HEALTHY"})).diagnostic
        self.assertEqual(diagnostic["ga4_diagnostic"]["diagnostic_status"], "QUALITY_HEALTHY"); self.assertEqual(diagnostic["wp5_score"], 73)

    def test_provider_failure_is_not_empty_success(self):
        row = self.stored("P_provider_failure"); self.assertIsNone(row["value"]); self.assertEqual(row["collection_status"], "FAILED")
        diagnostic = evaluate_geo_fixed_sample(self.inp([row])).diagnostic; self.assertIn("PROVIDER_FAILURE", diagnostic["conflicts"])

    def test_unknown_model_scope_is_preserved(self):
        diagnostic = evaluate_geo_fixed_sample(self.inp([self.stored("A_stable")])).diagnostic; self.assertEqual(diagnostic["model_scope"], "UNKNOWN")

    def test_content_hash_and_validation(self):
        diagnostic = evaluate_geo_fixed_sample(self.inp([self.stored("A_stable")])).diagnostic
        result = validate_geo_diagnostic(diagnostic); self.assertTrue(result.is_valid, result.as_dict())
        tampered = dict(diagnostic); tampered["wp5_score"] = 1; self.assertFalse(validate_geo_diagnostic(tampered).is_valid)

    def test_preview_is_deterministic(self):
        diagnostic = evaluate_geo_fixed_sample(self.inp([self.stored("O_deterministic")])).diagnostic
        self.assertEqual(geo_diagnostic_preview(diagnostic), geo_diagnostic_preview(diagnostic)); self.assertIn("GEO fixed sample", geo_diagnostic_preview(diagnostic, format="markdown"))

    def test_immutable_store_pins_revisions_and_history(self):
        diagnostic_store = GEODiagnosticStore(self.temp.name, evidence_store=self.evidence_store, registry=REGISTRY)
        first = evaluate_geo_fixed_sample(self.inp([self.stored("A_stable")]), diagnostic_store=diagnostic_store, persist=True)
        self.assertTrue(first.persisted); self.assertEqual(len(diagnostic_store.history(first.diagnostic["diagnostic_id"])), 1)
        second = evaluate_geo_fixed_sample(self.inp([self.stored("I_citation_present")], diagnostic_revision=2), diagnostic_store=diagnostic_store, persist=True)
        self.assertTrue(second.persisted); self.assertEqual([row["revision"] for row in diagnostic_store.history(first.diagnostic["diagnostic_id"])], [1, 2])

    def test_no_auto_candidate_creation_or_approval(self):
        diagnostic = evaluate_geo_fixed_sample(self.inp([self.stored("B_decline")])).diagnostic
        self.assertEqual(diagnostic["candidate_status"], "CANDIDATE"); self.assertEqual(diagnostic["candidate_review_state"], "NOT_REVIEWED"); self.assertFalse(diagnostic["approval_transition_allowed"])

    def test_evidence_pinning_contains_revision_and_hash(self):
        diagnostic = evaluate_geo_fixed_sample(self.inp([self.stored("A_stable")])).diagnostic
        self.assertTrue(all(set(ref) == {"evidence_id", "revision", "content_hash"} for ref in diagnostic["geo_evidence_refs"] + diagnostic["candidate_evidence_refs"]))

    def test_fixed_sample_provider_role_is_not_business_outcome(self):
        diagnostic = evaluate_geo_fixed_sample(self.inp([self.stored("A_stable")])).diagnostic
        self.assertEqual(diagnostic["source_role"], "MONITORED_FIXED_SAMPLE"); self.assertNotIn("revenue", diagnostic); self.assertNotIn("market_share", diagnostic)

    def test_failed_evidence_retains_history_without_rewrite(self):
        diagnostic_store = GEODiagnosticStore(self.temp.name, evidence_store=self.evidence_store, registry=REGISTRY)
        first = evaluate_geo_fixed_sample(self.inp([self.stored("A_stable")]), diagnostic_store=diagnostic_store, persist=True)
        old = diagnostic_store.get_diagnostic(first.diagnostic["diagnostic_id"], 1)["content_hash"]
        evaluate_geo_fixed_sample(self.inp([self.stored("P_provider_failure")], diagnostic_revision=2), diagnostic_store=diagnostic_store, persist=True)
        self.assertEqual(diagnostic_store.get_diagnostic(first.diagnostic["diagnostic_id"], 1)["content_hash"], old)


if __name__ == "__main__": unittest.main()
