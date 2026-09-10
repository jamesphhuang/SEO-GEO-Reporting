import copy
import json
import tempfile
import unittest
from pathlib import Path

from reporting.opportunity import EvidenceStore, CandidateStore
from reporting.opportunity.serp_preview import serp_validation_preview
from reporting.opportunity.serp_validation import SERPValidationStore, evaluate_serp_validation, validate_serp_validation
from reporting.opportunity.store.errors import ImmutableStoreError
from reporting.sources.serp import SERPCollectionPolicy, SERPInputError, collect_serp, normalize_serp_snapshot


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "tests/fixtures/opportunity_registry/synthetic_registry.json").read_text(encoding="utf-8"))
FIXTURES = json.loads((ROOT / "tests/fixtures/opportunity_serp/scenarios.json").read_text(encoding="utf-8"))
TOPIC = "TOPIC_ECOMMERCE_PLATFORM_COMPARISON"
URL_ID = "URL_cccdba54dc688385652d561d"
TARGET = "https://shopline.tw/example/ecommerce-platform/"
QUERY = FIXTURES["base"]["query_ref"]


class SERPValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.evidence = EvidenceStore(self.temp.name, registry=REGISTRY)
        self.candidates = CandidateStore(self.temp.name, evidence_store=self.evidence, registry=REGISTRY)
        candidate_evidence = self.evidence.append_evidence({
            "record_type": "EVIDENCE", "evidence_id": "WP7_CANDIDATE_EVIDENCE", "revision": 1,
            "source": "GSC", "source_class": "FIRST_PARTY_SEARCH_ACTUAL", "metric": "clicks", "value": 12, "unit": "count",
            "period_start": "2026-09-01", "period_end": "2026-09-07", "as_of": "2026-09-07", "retrieved_at": "2026-09-08T03:00:00+00:00",
            "freshness_state": "READY", "collection_status": "SUCCESS", "source_reference": "synthetic-wp7", "contract_version": "synthetic-wp7.v1",
            "entity_refs": [{"entity_type": "URL", "entity_id": URL_ID}], "topic_refs": [TOPIC], "created_at": "2026-09-08T03:01:00+00:00",
        })
        self.candidate = self.candidates.append_candidate({
            "record_type": "CANDIDATE", "candidate_id": "CAND_WP7_001", "revision": 1,
            "topic_ref": {"entity_type": "TOPIC", "entity_id": TOPIC}, "target_url": TARGET,
            "evidence_refs": [{"evidence_id": candidate_evidence["evidence_id"], "revision": 1, "content_hash": candidate_evidence["content_hash"]}],
            "score": 73, "confidence": "LOW", "status": "CANDIDATE", "review_state": "NOT_REVIEWED", "created_at": "2026-09-08T03:02:00+00:00",
        })

    def tearDown(self): self.temp.cleanup()

    def raw(self, name="A_quick_win_article", **overrides):
        raw = copy.deepcopy(FIXTURES["base"])
        records = FIXTURES["scenarios"][name].get("records", [])
        if records: raw.update(copy.deepcopy(records[0]))
        raw.update(overrides)
        return raw

    def stored(self, name="A_quick_win_article", **overrides):
        return self.evidence.append_evidence(normalize_serp_snapshot(self.raw(name, **overrides), REGISTRY))

    def input(self, rows=(), **overrides):
        value = {
            "candidate_id": self.candidate["candidate_id"], "candidate_revision": 1, "topic_cluster_id": TOPIC,
            "target_url": TARGET, "evaluation_period": "2026-09", "decision_at": "2026-09-10T04:00:00+00:00", "registry": REGISTRY,
            "opportunity_type": "SEO_EXISTING", "recommended_action": "OPTIMIZE_EXISTING", "expected_page_type": "commercial_comparison",
            "validation_query": QUERY, "serp_evidence": rows, "candidate_evidence_refs": self.candidate["evidence_refs"],
            "wp5_score": 73, "wp5_confidence": "LOW", "candidate_status": "CANDIDATE", "candidate_review_state": "NOT_REVIEWED",
        }
        value.update(overrides)
        return value

    def test_normalizer_pins_source_role_and_exact_identity(self):
        row = normalize_serp_snapshot(self.raw(), REGISTRY)
        self.assertEqual(row["source_class"], "LIVE_SERP_SNAPSHOT")
        self.assertEqual(row["source_role"], "LIVE / OBSERVED SERP VALIDATION EVIDENCE")
        self.assertEqual(row["entity_refs"], [{"entity_type": "QUERY", "entity_id": QUERY["entity_id"]}])
        self.assertEqual(row["value"]["query_text"], QUERY["text"])

    def test_query_scope_locale_and_url_are_exact(self):
        with self.assertRaises(SERPInputError): normalize_serp_snapshot(self.raw(query_ref={**QUERY, "text": "invented query"}), REGISTRY)
        with self.assertRaises(SERPInputError): normalize_serp_snapshot(self.raw(query_ref={**QUERY, "locale": "en-US"}), REGISTRY)
        row = normalize_serp_snapshot(self.raw(organic_results=[{"rank": 1, "url": "https://unknowncompetitor.example/a", "result_type": "comparison"}]), REGISTRY)
        self.assertEqual(row["value"]["organic_results"][0]["competitor_match_state"], "UNMAPPED_DOMAIN")
        self.assertEqual(row["value"]["organic_results"][0]["url_match_state"], "UNMAPPED_URL")

    def test_cap_features_and_not_available_are_explicit(self):
        results = [{"rank": n, "url": f"https://shopline.tw/example/ecommerce-platform/?x={n}", "result_type": "article"} for n in range(1, 33)]
        # Query URLs with query parameters are intentionally not canonical entities but remain safe evidence.
        row = normalize_serp_snapshot(self.raw(organic_results=results, serp_features={"aio": "NOT_AVAILABLE"}), REGISTRY, max_results=30)
        self.assertEqual(row["value"]["observed_result_count"], 30)
        self.assertTrue(row["value"]["truncated"])
        self.assertEqual(row["value"]["serp_features"]["aio"], "NOT_AVAILABLE")

    def test_collector_is_bounded_and_failed_provider_is_not_empty_success(self):
        class Flaky:
            def __init__(self): self.calls = 0
            def search(self, request):
                self.calls += 1
                if self.calls == 1: raise TimeoutError("fixture timeout")
                return self.raw
        transport = Flaky(); transport.raw = self.raw()
        rows = collect_serp([{"candidate_id": "CAND_WP7_001", "query_ref": QUERY, "retrieved_at": "2026-09-10T03:00:00+00:00", "country": "TW", "locale": "zh-TW"}], transport=transport, registry=REGISTRY)
        self.assertEqual(transport.calls, 2); self.assertEqual(rows[0]["collection_status"], "SUCCESS")
        with self.assertRaises(SERPInputError): collect_serp([{"query_ref": QUERY, "retrieved_at": "2026-09-10T03:00:00+00:00"}], transport=transport, registry=REGISTRY)

    def test_validation_scenarios_preserve_score_and_review_state(self):
        row = self.stored("E_shopline_strong")
        result = evaluate_serp_validation(self.input([row]))
        self.assertTrue(result.is_valid, result.as_dict()); self.assertEqual(result.validation["validation_status"], "SERP_VALIDATED")
        self.assertEqual(result.validation["wp5_score"], 73); self.assertFalse(result.validation["approval_transition_allowed"])

        mismatch = evaluate_serp_validation(self.input([self.stored("B_page_type_mismatch")]))
        self.assertEqual(mismatch.validation["validation_status"], "SERP_CONFLICT")
        self.assertIn("PAGE_TYPE_MISMATCH", mismatch.validation["conflict_reasons"])
        crowded = evaluate_serp_validation(self.input([self.stored("C_ctr_feature_crowding")]))
        self.assertIn("SERP_FEATURE_CROWDING", crowded.validation["conflict_reasons"])
        mixed = evaluate_serp_validation(self.input([self.stored("D_mixed_intent")], expected_page_type=None))
        self.assertEqual(mixed.validation["observed_intent"], "MIXED")

    def test_not_checked_missing_stale_and_unknown_domains_are_distinct(self):
        missing = evaluate_serp_validation(self.input([], validation_query=None))
        self.assertEqual(missing.validation["validation_status"], "SERP_NOT_CHECKED")
        self.assertNotEqual(missing.validation["validation_status"], "DO_NOTHING")
        stale = evaluate_serp_validation(self.input([self.stored("J_stale")]))
        self.assertEqual(stale.validation["validation_status"], "SERP_NOT_CHECKED")
        unknown = evaluate_serp_validation(self.input([self.stored("H_unmapped_competitor_domain")]))
        self.assertIn("UNKNOWN_COMPETITOR_DOMAIN", unknown.validation["conflict_reasons"])
        unavailable = evaluate_serp_validation(self.input([self.stored("I_feature_not_available")]))
        self.assertEqual(unavailable.validation["serp_features"]["paa"], "NOT_AVAILABLE")
        self.assertNotEqual(unavailable.validation["serp_features"]["paa"], "NOT_OBSERVED")

    def test_store_pins_and_preserves_revision_history(self):
        store = SERPValidationStore(self.temp.name, evidence_store=self.evidence, registry=REGISTRY)
        first_evidence = self.stored("E_shopline_strong")
        first = evaluate_serp_validation(self.input([first_evidence]))
        self.assertTrue(first.is_valid)
        first.validation["validation_id"] = "SV_HISTORY_001"; first.validation["content_hash"] = ""  # store recomputes
        first_row = store.append_validation(first.validation)
        second = copy.deepcopy(first_row); second["revision"] = 2; second["supersedes_validation_id"] = "SV_HISTORY_001"; second["supersedes_revision"] = 1; second["validation_status"] = "SERP_CONFLICT"
        store.append_validation(second)
        self.assertEqual([r["revision"] for r in store.history("SV_HISTORY_001")], [1, 2])
        self.assertNotEqual(store.history("SV_HISTORY_001")[0]["content_hash"], store.history("SV_HISTORY_001")[1]["content_hash"])

    def test_deterministic_and_preview(self):
        row = self.stored("K_deterministic")
        a = evaluate_serp_validation(self.input([row])).validation
        b = evaluate_serp_validation(self.input([row])).validation
        self.assertEqual(a["content_hash"], b["content_hash"])
        self.assertEqual(serp_validation_preview(a, format="json"), serp_validation_preview(a, format="json"))
        self.assertIn("SERP validation preview", serp_validation_preview(a, format="markdown"))

    def test_proposal_validator_and_tamper_reload_fail_closed(self):
        row = self.stored("E_shopline_strong")
        value = evaluate_serp_validation(self.input([row])).validation
        self.assertTrue(validate_serp_validation(value).is_valid)
        value["approval_transition_allowed"] = True
        self.assertFalse(validate_serp_validation(value).is_valid)
        store = SERPValidationStore(self.temp.name, evidence_store=self.evidence, registry=REGISTRY)
        value = evaluate_serp_validation(self.input([row])).validation
        value["validation_id"] = "SV_TAMPER_001"
        store.append_validation(value)
        path = Path(self.temp.name) / "serp_validations.jsonl"
        path.write_text(path.read_text(encoding="utf-8").replace("SERP_VALIDATED", "SERP_CONFLICT", 1), encoding="utf-8")
        with self.assertRaises(ImmutableStoreError): SERPValidationStore(self.temp.name, evidence_store=self.evidence, registry=REGISTRY)


if __name__ == "__main__": unittest.main()
