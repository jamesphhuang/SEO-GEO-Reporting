import copy
import json
import tempfile
import unittest
from pathlib import Path

from reporting.opportunity import (
    CandidateStore,
    EvidenceStore,
    GA4DiagnosticStore,
    diagnostic_preview,
    evaluate_ga4_diagnostic,
)
from reporting.opportunity.store.serialization import content_hash
from reporting.sources.ga4_quality import GA4EvidenceInputError, normalize_ga4_record


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "tests/fixtures/opportunity_registry/synthetic_registry.json").read_text(encoding="utf-8"))
FIXTURES = json.loads((ROOT / "tests/fixtures/opportunity_ga4/scenarios.json").read_text(encoding="utf-8"))
URL_ID = "URL_cccdba54dc688385652d561d"
TOPIC_ID = "TOPIC_ECOMMERCE_PLATFORM_COMPARISON"
TARGET_URL = "https://shopline.tw/example/ecommerce-platform/"


class GA4QualityDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.evidence_store = EvidenceStore(self.temp.name, registry=REGISTRY)
        self.candidate_store = CandidateStore(self.temp.name, evidence_store=self.evidence_store, registry=REGISTRY)
        self.candidate_evidence = self.evidence_store.append_evidence(self._candidate_evidence())
        self.candidate = self.candidate_store.append_candidate({
            "record_type": "CANDIDATE",
            "candidate_id": "CAND_SEO_001",
            "revision": 1,
            "topic_ref": {"entity_type": "TOPIC", "entity_id": TOPIC_ID},
            "target_url": TARGET_URL,
            "evidence_refs": [{"evidence_id": self.candidate_evidence["evidence_id"], "revision": 1, "content_hash": self.candidate_evidence["content_hash"]}],
            "score": 73,
            "confidence": "LOW",
            "status": "CANDIDATE",
            "review_state": "NOT_REVIEWED",
            "created_at": "2026-09-10T03:10:00+00:00",
        })

    def tearDown(self):
        self.temp.cleanup()

    def _candidate_evidence(self):
        return {
            "record_type": "EVIDENCE", "evidence_id": "WP6_CAND_EVIDENCE", "revision": 1,
            "source": "GSC", "source_class": "FIRST_PARTY_SEARCH_ACTUAL", "metric": "clicks", "value": 120,
            "unit": "count", "period_start": "2026-09-01", "period_end": "2026-09-07", "as_of": "2026-09-07",
            "retrieved_at": "2026-09-08T03:00:00+00:00", "freshness_state": "READY", "collection_status": "SUCCESS",
            "source_reference": "synthetic-wp6-candidate", "contract_version": "synthetic-wp6.v1",
            "entity_refs": [{"entity_type": "URL", "entity_id": URL_ID}], "topic_refs": [TOPIC_ID],
            "created_at": "2026-09-08T03:01:00+00:00",
        }

    def _raw(self, **overrides):
        value = copy.deepcopy(FIXTURES["base"])
        value.update(overrides)
        return value

    def _raw_scenario(self, name):
        values = []
        scenario = FIXTURES["scenarios"][name]
        for record in scenario.get("records", []):
            value = self._raw(**record)
            values.append(value)
        return values

    def _stored_rows(self, raw_rows):
        rows = []
        for raw in raw_rows:
            normalized = normalize_ga4_record(raw, REGISTRY)
            rows.append(self.evidence_store.append_evidence(normalized))
        return rows

    def _input(self, rows, **overrides):
        value = {
            "candidate_id": self.candidate["candidate_id"],
            "candidate_revision": 1,
            "topic_cluster_id": TOPIC_ID,
            "canonical_url_id": URL_ID,
            "target_url": TARGET_URL,
            "evaluation_period": "2026-09",
            "decision_at": "2026-09-10T04:00:00+00:00",
            "registry": REGISTRY,
            "ga4_evidence": rows,
            "candidate_evidence_refs": self.candidate["evidence_refs"],
            "wp5_score": self.candidate["score"],
            "wp5_confidence": self.candidate["confidence"],
            "expected_channel": "Organic Search",
            "quality_scope": "PAGE_LEVEL",
        }
        value.update(overrides)
        return value

    def test_normalizer_scopes_and_pins_page_url(self):
        row = normalize_ga4_record(self._raw(metric="sessions", value=10), REGISTRY)
        self.assertEqual(row["source_class"], "FIRST_PARTY_BEHAVIOR_DIAGNOSTIC")
        self.assertEqual(row["url_id"], URL_ID)
        self.assertEqual(row["entity_refs"], [{"entity_type": "URL", "entity_id": URL_ID}])
        self.assertNotIn("user_id", row)
        self.assertNotIn("query_string", row)

    def test_normalizer_rejects_unregistered_or_pii_url(self):
        with self.assertRaises(GA4EvidenceInputError) as unresolved:
            normalize_ga4_record(self._raw(landing_page="https://shopline.tw/unregistered-page", metric="sessions", value=10), REGISTRY)
        self.assertEqual(unresolved.exception.code, "UNRESOLVED_ENTITY")
        with self.assertRaises(GA4EvidenceInputError):
            normalize_ga4_record(self._raw(landing_page="https://shopline.tw/example/ecommerce-platform/?email=fixture@example.com", metric="sessions", value=10), REGISTRY)

    def test_normalizer_enforces_property_hostname_and_retains_sampling_metadata(self):
        with self.assertRaises(GA4EvidenceInputError) as out_of_scope:
            normalize_ga4_record(self._raw(property_id="399614424"), REGISTRY)
        self.assertEqual(out_of_scope.exception.code, "OUT_OF_SCOPE")
        row = normalize_ga4_record(self._raw(metric="sessions", value=0, sampling="NONE", subject_to_thresholding=False), REGISTRY)
        self.assertEqual(row["sampling"], "NONE")
        self.assertFalse(row["subject_to_thresholding"])
        with self.assertRaises(GA4EvidenceInputError):
            normalize_ga4_record(self._raw(metric="event_count", value=0, coverage="PARTIAL"), REGISTRY)

    def test_healthy_and_directional_quality_states(self):
        healthy = evaluate_ga4_diagnostic(self._input(self._stored_rows(self._raw_scenario("A_healthy"))))
        self.assertTrue(healthy.is_valid, healthy.as_dict())
        self.assertEqual(healthy.diagnostic["diagnostic_status"], "QUALITY_HEALTHY")
        self.assertNotIn("ENGAGEMENT_DECLINING", healthy.diagnostic["diagnostic_types"])
        self.assertEqual(healthy.diagnostic["diagnostic_confidence"], "MEDIUM")
        declining_sessions = evaluate_ga4_diagnostic(self._input(self._stored_rows(self._raw_scenario("B_sessions_declining_engagement_stable"))))
        self.assertEqual(declining_sessions.diagnostic["diagnostic_status"], "QUALITY_MIXED")
        self.assertIn("TRAFFIC_DECLINING", declining_sessions.diagnostic["diagnostic_types"])
        declining_engagement = evaluate_ga4_diagnostic(self._input(self._stored_rows(self._raw_scenario("C_sessions_stable_engagement_declining"))))
        self.assertEqual(declining_engagement.diagnostic["diagnostic_status"], "QUALITY_MIXED")

    def test_both_declining_is_quality_weak(self):
        raw_rows = self._raw_scenario("B_sessions_declining_engagement_stable")
        raw_rows[-1]["value"] = 0.40
        result = evaluate_ga4_diagnostic(self._input(self._stored_rows(raw_rows)))
        self.assertEqual(result.diagnostic["diagnostic_status"], "QUALITY_WEAK")
        self.assertIn("TRAFFIC_DECLINING", result.diagnostic["diagnostic_types"])
        self.assertIn("ENGAGEMENT_DECLINING", result.diagnostic["diagnostic_types"])

    def test_missing_and_stale_are_explicit_not_zero_or_current(self):
        missing = evaluate_ga4_diagnostic(self._input(self._stored_rows(self._raw_scenario("D_missing"))))
        self.assertEqual(missing.diagnostic["diagnostic_status"], "INSUFFICIENT_GA4_EVIDENCE")
        self.assertIn("engagement_rate", missing.diagnostic["missing_evidence"])
        self.assertNotEqual(missing.diagnostic["signals"]["engagement_signal"], "STABLE")
        stale = evaluate_ga4_diagnostic(self._input(self._stored_rows(self._raw_scenario("E_stale"))))
        self.assertEqual(stale.diagnostic["diagnostic_status"], "INSUFFICIENT_GA4_EVIDENCE")
        self.assertIn("fresh_current_ga4_evidence", stale.diagnostic["missing_evidence"])

    def test_wrong_channel_and_sitewide_context_never_become_page_quality(self):
        wrong = evaluate_ga4_diagnostic(self._input(self._stored_rows(self._raw_scenario("F_wrong_channel"))))
        self.assertEqual(wrong.diagnostic["diagnostic_status"], "CONFLICTING_GA4_EVIDENCE")
        self.assertIn("WRONG_CHANNEL_SEGMENT", wrong.diagnostic["conflicts"])
        sitewide_raw = self._raw_scenario("G_sitewide_only")
        sitewide = evaluate_ga4_diagnostic(self._input(self._stored_rows(sitewide_raw), quality_scope="SITE_WIDE_CONTEXT"))
        self.assertEqual(sitewide.diagnostic["diagnostic_status"], "CONFLICTING_GA4_EVIDENCE")
        self.assertIn("SITE_WIDE_CONTEXT_ONLY", sitewide.diagnostic["conflicts"])

    def test_cta_is_diagnostic_only_and_does_not_create_conversion(self):
        rows = self._stored_rows(self._raw_scenario("A_healthy") + self._raw_scenario("I_cta_diagnostic_only"))
        result = evaluate_ga4_diagnostic(self._input(rows))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.diagnostic["signals"]["cta_signal"], "CTA_SIGNAL_PRESENT")
        self.assertIn("CTA_SIGNAL_PRESENT", result.diagnostic["diagnostic_types"])
        self.assertEqual(result.diagnostic["signals"]["cta_event_count"], 3)
        self.assertEqual(result.diagnostic["conversion_boundary"], "DIAGNOSTIC_ONLY")
        self.assertNotIn("lead", result.diagnostic)
        self.assertNotIn("sql", result.diagnostic)
        self.assertNotIn("revenue", result.diagnostic)
        self.assertNotIn("cvr", result.diagnostic)

    def test_zero_cta_is_weak_signal_when_complete(self):
        rows = self._stored_rows(self._raw_scenario("A_healthy") + [{**self._raw_scenario("I_cta_diagnostic_only")[0], "value": 0}])
        result = evaluate_ga4_diagnostic(self._input(rows))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.diagnostic["signals"]["cta_signal"], "CTA_SIGNAL_WEAK")
        self.assertIn("CTA_SIGNAL_WEAK", result.diagnostic["diagnostic_types"])

    def test_gsc_conflict_and_ai_attribution_gap_are_preserved(self):
        rows = self._stored_rows(self._raw_scenario("A_healthy"))
        result = evaluate_ga4_diagnostic(self._input(rows, acquisition_context={"gsc_clicks_previous": 1000, "gsc_clicks_current": 700}))
        self.assertEqual(result.diagnostic["diagnostic_status"], "CONFLICTING_GA4_EVIDENCE")
        self.assertIn("GSC_GA4_ACQUISITION_BEHAVIOR_CONFLICT", result.diagnostic["conflicts"])
        ai = evaluate_ga4_diagnostic(self._input(rows, expected_channel="AI Assistant", acquisition_context={"ai_assistant_sessions": 10, "external_leads": 2}))
        self.assertEqual(ai.diagnostic["diagnostic_status"], "CONFLICTING_GA4_EVIDENCE")
        self.assertIn("AI_ASSISTANT_ATTRIBUTION_UNRESOLVED", ai.diagnostic["conflicts"])

    def test_wp5_score_and_candidate_review_state_are_preserved(self):
        result = evaluate_ga4_diagnostic(self._input(self._stored_rows(self._raw_scenario("A_healthy"))))
        self.assertEqual(result.diagnostic["wp5_score"], 73)
        self.assertEqual(result.diagnostic["wp5_confidence"], "LOW")
        self.assertTrue(result.diagnostic["wp5_score_preserved"])
        self.assertEqual(self.candidate["status"], "CANDIDATE")
        self.assertEqual(self.candidate["review_state"], "NOT_REVIEWED")

    def test_candidate_and_diagnostic_stores_pin_exact_revisions_and_history(self):
        diagnostic_store = GA4DiagnosticStore(self.temp.name, evidence_store=self.evidence_store, registry=REGISTRY)
        first_rows = self._stored_rows(self._raw_scenario("A_healthy"))
        first = evaluate_ga4_diagnostic(self._input(first_rows), diagnostic_store=diagnostic_store, persist=True)
        self.assertTrue(first.persisted, first.as_dict())
        self.assertEqual(len(diagnostic_store.history(first.diagnostic["diagnostic_id"])), 1)
        old_hash = first.diagnostic["content_hash"]
        changed = self._raw_scenario("A_healthy")
        changed[-1]["value"] = 0.70
        changed[-1]["evidence_id"] = first_rows[-1]["evidence_id"]
        changed[-1]["revision"] = 2
        changed[-1]["supersedes_evidence_id"] = first_rows[-1]["evidence_id"]
        changed[-1]["supersedes_revision"] = 1
        second_rows = first_rows[:-1] + self._stored_rows([changed[-1]])
        second = evaluate_ga4_diagnostic(self._input(second_rows), diagnostic_store=diagnostic_store, persist=True)
        self.assertTrue(second.persisted, second.as_dict())
        history = diagnostic_store.history(first.diagnostic["diagnostic_id"])
        self.assertEqual([item["revision"] for item in history], [1, 2])
        self.assertEqual(history[0]["content_hash"], old_hash)
        self.assertEqual(len(history[0]["ga4_evidence_refs"]), 4)
        self.assertEqual(history[1]["revision"], 2)

    def test_deterministic_replay_and_preview(self):
        rows = self._stored_rows(self._raw_scenario("A_healthy"))
        first = evaluate_ga4_diagnostic(self._input(rows))
        second = evaluate_ga4_diagnostic(self._input(rows))
        self.assertEqual(first.diagnostic, second.diagnostic)
        self.assertEqual(diagnostic_preview(first.diagnostic), diagnostic_preview(second.diagnostic))
        self.assertIn("GA4 quality diagnostic preview", diagnostic_preview(first.diagnostic, format="markdown"))

    def test_invalid_pin_or_hash_cannot_persist(self):
        rows = self._stored_rows(self._raw_scenario("A_healthy"))
        rows[0]["content_hash"] = "0" * 64
        result = evaluate_ga4_diagnostic(self._input(rows), diagnostic_store=GA4DiagnosticStore(self.temp.name, evidence_store=self.evidence_store, registry=REGISTRY), persist=True)
        self.assertFalse(result.is_valid)
        self.assertIsNone(result.diagnostic)

    def test_ga4_evidence_hash_is_stable_and_schema_record_is_proposal_only(self):
        row = normalize_ga4_record(self._raw(metric="sessions", value=10), REGISTRY)
        stored = self.evidence_store.append_evidence(row)
        self.assertEqual(stored["content_hash"], content_hash(stored))
        self.assertEqual(stored["source"], "GA4")
        self.assertEqual(stored["source_class"], "FIRST_PARTY_BEHAVIOR_DIAGNOSTIC")
        schema = json.loads((ROOT / "contracts/ga4_quality_diagnostics.v1.proposal.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["x-proposal-status"], "DRAFT_NOT_APPROVED")
        self.assertFalse(schema["x-production-activation"])


if __name__ == "__main__":
    unittest.main()
