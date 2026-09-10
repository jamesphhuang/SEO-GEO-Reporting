import copy
import json
import tempfile
import unittest
from pathlib import Path

from reporting.opportunity import candidate_preview, evaluate_topic
from reporting.opportunity.candidate_store import CandidateStore
from reporting.opportunity.evidence import EvidenceStore
from reporting.opportunity.models import EngineInputError


ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = json.loads((ROOT / "tests/fixtures/opportunity_engine/scenarios.json").read_text(encoding="utf-8"))
REGISTRY = json.loads((ROOT / "tests/fixtures/opportunity_registry/synthetic_registry.json").read_text(encoding="utf-8"))


def bundle(name, **overrides):
    value = copy.deepcopy(SCENARIOS["base"])
    value["registry"] = REGISTRY
    value.update(copy.deepcopy(SCENARIOS["scenarios"][name]))
    value.update(overrides)
    return value


class OpportunityEngineTests(unittest.TestCase):
    def test_quick_win_is_candidate_but_serp_gate_stays_visible(self):
        result = evaluate_topic(bundle("quick_win"))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.proposal["opportunity_type"], "QUICK_WIN")
        self.assertEqual(result.proposal["recommended_action"], "UPDATE_EXISTING")
        self.assertEqual(result.proposal["serp_state"], "SERP_NOT_CHECKED")
        self.assertIn("intent", result.proposal["missing_evidence_roles"])
        self.assertNotEqual(result.proposal["status"], "APPROVED")

    def test_ahrefs_only_demand_is_insufficient_and_missing_is_not_zero(self):
        result = evaluate_topic(bundle("high_demand_insufficient"))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.proposal["confidence"], "LOW")
        self.assertIsNone(result.proposal["opportunity_score"])
        self.assertIsNone(result.proposal["traction_score"])
        self.assertEqual(result.proposal["independent_family_count"], 1)

    def test_score_and_confidence_are_independent(self):
        result = evaluate_topic(bundle("quick_win"))
        self.assertIsNone(result.proposal["opportunity_score"])
        self.assertEqual(result.proposal["confidence"], "LOW")
        self.assertNotEqual(result.proposal["confidence"], result.proposal["opportunity_score"])

    def test_ctr_hypothesis_requires_two_windows_and_sf_issue(self):
        result = evaluate_topic(bundle("ctr_hypothesis"))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.proposal["opportunity_type"], "CTR_OPPORTUNITY")
        self.assertEqual(result.proposal["recommended_action"], "SERP_SNIPPET_OPTIMIZE")

    def test_content_gap_is_policy_gap_without_candidate(self):
        result = evaluate_topic(bundle("content_gap_policy"))
        self.assertIsNone(result.candidate)
        self.assertEqual(result.policy_gaps, ["AHREFS_CONTENT_GAP_UNAVAILABLE", "DERIVED_COMPETITIVE_GAP_POLICY_UNAPPROVED"])
        self.assertIn("POLICY_GAP", {error.code for error in result.validation.errors})

    def test_content_decay_has_six_month_gate(self):
        result = evaluate_topic(bundle("content_decay"))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.proposal["opportunity_type"], "CONTENT_DECAY")
        self.assertEqual(result.proposal["recommended_action"], "UPDATE_EXISTING")

    def test_technical_unlock_needs_url_specific_issue_and_demand(self):
        result = evaluate_topic(bundle("technical_unlock"))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.proposal["opportunity_type"], "TECHNICAL_UNLOCK")
        self.assertEqual(result.proposal["recommended_action"], "TECHNICAL_FIX")

    def test_do_nothing_path_remains_explicit(self):
        result = evaluate_topic(bundle("do_nothing"))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.proposal["opportunity_type"], "DO_NOTHING")
        self.assertEqual(result.proposal["recommended_action"], "DO_NOTHING")
        self.assertIsNotNone(result.proposal["review_at"])

    def test_conflict_is_low_confidence_and_pinned(self):
        result = evaluate_topic(bundle("conflicting"))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.proposal["validation_state"], "CONFLICTING_EVIDENCE")
        self.assertEqual(result.proposal["confidence"], "LOW")
        self.assertEqual(result.proposal["conflicting_evidence_refs"], ["SYN_CONFLICT_A"])

    def test_stale_evidence_cannot_be_current(self):
        result = evaluate_topic(bundle("stale"))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.proposal["validation_state"], "INSUFFICIENT_EVIDENCE")
        self.assertEqual(result.proposal["confidence"], "LOW")
        self.assertIn("freshness", result.proposal["missing_evidence_roles"])

    def test_unapproved_mapping_remains_insufficient(self):
        result = evaluate_topic(bundle("quick_win", mapping_review_state="CANDIDATE", entity_mappings_confirmed=False))
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.proposal["validation_state"], "INSUFFICIENT_EVIDENCE")
        self.assertIn("mapping_review", result.proposal["missing_evidence_roles"])

    def test_evidence_revision_and_content_hash_are_pinned(self):
        value = bundle("quick_win")
        first = evaluate_topic(value)
        second_value = copy.deepcopy(value)
        second_value["evidence"][0]["revision"] = 2
        second_value["evidence"][0]["content_hash"] = "a999999999999999999999999999999999999999999999999999999999999999"
        second = evaluate_topic(second_value)
        self.assertEqual(first.proposal["content_hash"], evaluate_topic(value).proposal["content_hash"])
        self.assertEqual(first.proposal["content_hash"], second.proposal["content_hash"])
        self.assertEqual(first.proposal["evidence_refs"], second.proposal["evidence_refs"])

    def test_preview_is_deterministic(self):
        result = evaluate_topic(bundle("quick_win"))
        self.assertEqual(candidate_preview(result), candidate_preview(result))
        self.assertIn("# SEO opportunity preview", candidate_preview(result, format="markdown"))

    def test_unsupported_source_fails_closed(self):
        value = bundle("quick_win")
        value["evidence"].append({"evidence_id": "SYN_BAD", "source": "GA4", "topic_refs": ["TOPIC_ECOMMERCE_PLATFORM_COMPARISON"]})
        with self.assertRaises(EngineInputError):
            evaluate_topic(value)

    def test_no_candidate_is_persisted_when_contract_validation_fails(self):
        value = bundle("quick_win")
        value["evaluation_period"] = "2026-13"
        result = evaluate_topic(value)
        self.assertIsNone(result.candidate)
        self.assertFalse(result.is_valid)


class CandidateStoreIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.evidence = EvidenceStore(self.temp.name, registry=REGISTRY)
        self.ahrefs = self.evidence.append_evidence(self._record("STORE_A", "AHREFS", "THIRD_PARTY_ESTIMATE", "volume", 1200, "KEYWORD", "KW_4f80a917de460dcca989e026"))
        self.gsc = self.evidence.append_evidence(self._record("STORE_G", "GSC", "FIRST_PARTY_SEARCH_ACTUAL", "impressions", 1000, "KEYWORD", "KW_4f80a917de460dcca989e026", extra={"impressions": 1000, "position": 8}))
        self.sf = self.evidence.append_evidence(self._record("STORE_S", "SF", "TECHNICAL_CRAWL_EVIDENCE", "crawl", 1, "URL", "URL_cccdba54dc688385652d561d", extra={"issues": [], "url": "https://shopline.tw/example/ecommerce-platform/"}))
        self.store = CandidateStore(self.temp.name, evidence_store=self.evidence, registry=REGISTRY)

    def tearDown(self):
        self.temp.cleanup()

    def _record(self, evidence_id, source, source_class, metric, value, entity_type, entity_id, *, extra=None, revision=1, supersedes=None):
        value = {
            "record_type": "EVIDENCE", "evidence_id": evidence_id, "revision": revision,
            "source": source, "source_class": source_class, "metric": metric, "value": value,
            "unit": "synthetic", "period_start": "2026-08-01", "period_end": "2026-08-31", "as_of": "2026-08-31",
            "retrieved_at": "2026-09-01T03:00:00+00:00", "freshness_state": "READY", "collection_status": "SUCCESS",
            "source_reference": "synthetic-wp5", "contract_version": "synthetic-wp5.v1",
            "entity_refs": [{"entity_type": entity_type, "entity_id": entity_id}], "topic_refs": ["TOPIC_ECOMMERCE_PLATFORM_COMPARISON"],
            "supersedes_evidence_id": supersedes, "supersedes_revision": (revision - 1 if supersedes else None), "created_at": "2026-09-01T03:01:00+00:00"
        }
        value.update(extra or {})
        return value

    def _bundle(self):
        value = bundle("quick_win")
        value["evidence"] = [self.ahrefs, self.gsc, self.sf]
        return value

    def test_candidate_store_persists_pinned_revisions(self):
        result = evaluate_topic(self._bundle(), candidate_store=self.store, persist=True)
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertTrue(result.persisted, result.persistence_error)
        self.assertEqual(result.candidate["evidence_refs"][0]["revision"], 1)
        self.assertEqual(self.store.resolve_candidate_evidence(result.candidate["candidate_id"])[0]["revision"], 1)
        self.assertNotEqual(result.candidate["content_hash"], result.proposal["content_hash"])

    def test_changed_evidence_appends_new_candidate_revision(self):
        first = evaluate_topic(self._bundle(), candidate_store=self.store, persist=True)
        gsc2 = self.evidence.append_evidence(self._record("STORE_G", "GSC", "FIRST_PARTY_SEARCH_ACTUAL", "impressions", 1100, "KEYWORD", "KW_4f80a917de460dcca989e026", extra={"impressions": 1100, "position": 8}, revision=2, supersedes="STORE_G"))
        value = self._bundle()
        value["evidence"] = [self.ahrefs, gsc2, self.sf]
        second = evaluate_topic(value, candidate_store=self.store, persist=True)
        self.assertTrue(second.persisted, second.persistence_error)
        self.assertEqual(second.proposal["revision"], 2)
        self.assertEqual([item["revision"] for item in self.store.history(first.candidate["candidate_id"])], [1, 2])
