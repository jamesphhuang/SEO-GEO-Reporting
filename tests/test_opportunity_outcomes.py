import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from reporting.opportunity.outcome_preview import outcome_preview, render_outcome_preview
from reporting.opportunity.outcomes import (
    OutcomeStore,
    create_implementation_anchor,
    evaluate_outcome,
    expected_window,
    validate_implementation_anchor,
    validate_outcome_record,
)
from reporting.opportunity.review import create_human_review
from reporting.opportunity.review_bridge import build_recommendation_bridge
from reporting.opportunity.store.serialization import content_hash


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/opportunity_outcomes/scenarios.json").read_text(encoding="utf-8"))
REVIEWER = {"actor_type": "HUMAN", "actor_ref": "reviewer_wp11", "authenticated": True, "identity_source": "UAT_REVIEW_SURFACE"}


def candidate():
    data = json.loads((ROOT / "tests/fixtures/opportunity_review/scenarios.json").read_text(encoding="utf-8"))
    return copy.deepcopy(next(item["candidate"] for item in data["scenarios"] if item["id"] == "A"))


def lineage():
    value = candidate()
    review = create_human_review(value, reviewer=REVIEWER, decision="APPROVE", reason_code="WP11_MEASUREMENT", decision_at="2026-09-11T09:00:00+08:00")
    bridge = build_recommendation_bridge(value, review.review)
    anchor = create_implementation_anchor({
        "implementation_event_id": "IMP_WP11_A", "revision": 1,
        "candidate_id": value["candidate_id"], "candidate_revision": value["revision"], "candidate_hash": value["content_hash"],
        "review_id": review.review["review_id"], "review_revision": review.review["revision"], "review_hash": review.review["content_hash"],
        "bridge_id": bridge.bridge["bridge_id"], "bridge_revision": bridge.bridge["revision"], "bridge_hash": bridge.bridge["content_hash"],
        "action": value["recommended_action"], "target_url": value["target_url"], "event_type": "IMPLEMENTED",
        "completed_at": "2026-09-14T10:00:00+08:00", "deployment_ref": "DEP_WP11_A", "change_ref": "CHANGE_WP11_A", "created_at": "2026-09-14T10:00:00+08:00",
    })
    return value, review.review, bridge.bridge, anchor


def observation(metric, source, value, window, evidence_id, **extra):
    row = {
        "metric": metric, "source": source, "value": value,
        "period_start": window["period_start"], "period_end": window["period_end"],
        "evidence_ref": {"evidence_id": evidence_id, "revision": 1, "content_hash": "a" * 64},
        "status": "READY", "freshness_state": "READY", "scope": "PAGE_LEVEL", "entity_ref": "URL_WP11_A",
        "source_population": "SYNTHETIC_PAGE_POPULATION", "methodology": "WP11_SYNTHETIC", "sample_size": 100,
    }
    row.update(extra)
    return row


def measurement_plan(**overrides):
    value = {"primary_metric": "clicks", "target_delta": 0.20, "tolerance": 0.05, "minimum_sample": 1, "comparison_method": "RELATIVE_DELTA", "direction": "INCREASE", "support_metrics": ["impressions"], "guardrails": [], "scope": "PAGE_LEVEL", "attribution_limitations": ["No causal attribution"]}
    value.update(overrides)
    return value


def input_payload(**overrides):
    value, review, bridge, anchor = lineage()
    baseline_window = expected_window(anchor["completed_at"], "BASELINE")
    follow_window = expected_window(anchor["completed_at"], "30D")
    payload = {"candidate": value, "review": review, "bridge": bridge, "implementation_anchor": anchor, "measurement_plan": measurement_plan(), "baseline_window": baseline_window, "follow_up_window": follow_window, "baseline_observations": [observation("clicks", "GSC", 100, baseline_window, "E_WP11_BASE_CLICKS"), observation("impressions", "GSC", 1000, baseline_window, "E_WP11_BASE_IMPRESSIONS")], "follow_up_observations": [observation("clicks", "GSC", 130, follow_window, "E_WP11_AFTER_CLICKS"), observation("impressions", "GSC", 1200, follow_window, "E_WP11_AFTER_IMPRESSIONS")], "evaluated_at": "2026-10-15T09:00:00+08:00"}
    payload.update(overrides)
    return payload


class OutcomeTrackingTests(unittest.TestCase):
    def test_fixture_is_synthetic_and_covers_a_to_p(self):
        self.assertTrue(FIXTURE["metadata"]["synthetic"])
        self.assertEqual([item["id"] for item in FIXTURE["scenarios"]], list("ABCDEFGHIJKLMNOP"))
        self.assertEqual(FIXTURE["metadata"]["production_mutation"], 0)

    def test_proposal_schemas_are_draft_and_valid(self):
        for name in ("implementation_event.v1.proposal.json", "outcome_tracking.v1.proposal.json"):
            schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            self.assertEqual(schema["x-proposal-status"], "DRAFT_NOT_APPROVED")
            self.assertFalse(schema["x-production-activation"])

    def test_window_is_exactly_28_complete_days_in_asia_taipei(self):
        baseline = expected_window("2026-09-14T23:59:00+08:00", "BASELINE")
        self.assertEqual(baseline, {"period_start": "2026-08-17", "period_end": "2026-09-13", "timezone": "Asia/Taipei", "complete_days": 28})
        self.assertEqual(expected_window("2026-09-14T23:59:00+08:00", "30D")["period_start"], "2026-09-17")

    def test_exact_lineage_anchor_is_required_and_validated(self):
        _, _, _, anchor = lineage()
        self.assertTrue(validate_implementation_anchor(anchor).is_valid)
        changed = dict(anchor, candidate_hash="b" * 64)
        self.assertFalse(validate_implementation_anchor(changed).is_valid)

    def test_approval_without_implementation_has_no_formal_outcome(self):
        payload = input_payload()
        payload.pop("implementation_anchor")
        result = evaluate_outcome(payload)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.validation.errors[0].code, "IMPLEMENTATION_ANCHOR_REQUIRED")

    def test_implemented_primary_and_support_improvement_is_won(self):
        result = evaluate_outcome(input_payload())
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.outcome["outcome_state"], "WON")
        self.assertFalse(result.outcome["causal_claim"])
        self.assertEqual(result.outcome["candidate_score"], candidate()["score"])

    def test_complete_data_inside_tolerance_is_no_change(self):
        payload = input_payload(follow_up_observations=[observation("clicks", "GSC", 103, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_NOCHANGE_C"), observation("impressions", "GSC", 1005, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_NOCHANGE_I")])
        result = evaluate_outcome(payload)
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.outcome["outcome_state"], "NO_CHANGE")

    def test_mixed_signals_are_partial_and_preserved(self):
        payload = input_payload(measurement_plan=measurement_plan(support_metrics=["engaged_sessions"]), baseline_observations=[observation("clicks", "GSC", 100, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_MIX_B"), observation("engaged_sessions", "GA4", 100, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_MIX_GB")], follow_up_observations=[observation("clicks", "GSC", 130, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_MIX_A"), observation("engaged_sessions", "GA4", 80, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_MIX_GA")])
        result = evaluate_outcome(payload)
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.outcome["outcome_state"], "PARTIAL_WIN")

    def test_missing_is_not_zero_and_stale_is_insufficient(self):
        payload = input_payload(follow_up_observations=[observation("clicks", "GSC", None, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_MISSING_C", status="MISSING", freshness_state="MISSING"), observation("impressions", "GSC", 1200, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_MISSING_I")])
        result = evaluate_outcome(payload)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.outcome["outcome_state"], "INSUFFICIENT_DATA")
        self.assertIsNone(result.outcome["comparisons"][0]["delta"])

    def test_geo_revision_mismatch_is_not_comparable(self):
        payload = input_payload(measurement_plan=measurement_plan(primary_metric="visibility", support_metrics=["citations"]), baseline_observations=[observation("visibility", "GEO", 2, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_GEO_B", sample_version="S1", sample_revision=1), observation("citations", "GEO", 1, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_GEO_B2", sample_version="S1", sample_revision=1)], follow_up_observations=[observation("visibility", "GEO", 3, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_GEO_A", sample_version="S1", sample_revision=2), observation("citations", "GEO", 2, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_GEO_A2", sample_version="S1", sample_revision=2)])
        result = evaluate_outcome(payload)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.outcome["outcome_state"], "INSUFFICIENT_DATA")
        self.assertIn("GEO_SAMPLE_REVISION_MISMATCH", result.outcome["conflicts"])

    def test_serp_snapshot_is_not_period_metric(self):
        payload = input_payload(measurement_plan=measurement_plan(primary_metric="rank", support_metrics=["result_count"]), baseline_observations=[observation("rank", "SERP", 4, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_SERP_B"), observation("result_count", "SERP", 10, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_SERP_B2")], follow_up_observations=[observation("rank", "SERP", 2, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_SERP_A"), observation("result_count", "SERP", 10, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_SERP_A2")])
        result = evaluate_outcome(payload)
        self.assertTrue(result.is_valid)
        self.assertIn("SERP_SNAPSHOT_NOT_PERIOD_COMPARABLE", result.outcome["conflicts"])

    def test_guardrail_breach_is_lost_and_not_won(self):
        payload = input_payload(measurement_plan=measurement_plan(guardrails=[{"metric": "bounce_rate", "direction": "MAX_INCREASE", "max_delta": 0.05}], support_metrics=["impressions", "bounce_rate"]), baseline_observations=[observation("clicks", "GSC", 100, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_G1"), observation("impressions", "GSC", 1000, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_G2"), observation("bounce_rate", "GA4", 0.2, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_G3")], follow_up_observations=[observation("clicks", "GSC", 130, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_G4"), observation("impressions", "GSC", 1200, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_G5"), observation("bounce_rate", "GA4", 0.4, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_G6")])
        result = evaluate_outcome(payload)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.outcome["outcome_state"], "LOST")

    def test_do_nothing_and_monitor_do_not_fake_implementation(self):
        payload = input_payload()
        altered = dict(payload["implementation_anchor"], event_type="MONITORING_ONLY")
        altered.pop("content_hash", None)
        payload["implementation_anchor"] = create_implementation_anchor(altered)
        result = evaluate_outcome(payload)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.outcome["tracking_status"], "OBSERVATION_ONLY")
        self.assertFalse(result.outcome["formal_evaluation"])

    def test_business_and_ga4_conversion_are_not_formal_attribution(self):
        payload = input_payload(measurement_plan=measurement_plan(primary_metric="revenue", support_metrics=["lead_value"]), baseline_observations=[observation("revenue", "BUSINESS", 10, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_B1"), observation("lead_value", "GA4", 2, expected_window("2026-09-14T10:00:00+08:00", "BASELINE"), "E_B2")], follow_up_observations=[observation("revenue", "BUSINESS", 20, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_B3"), observation("lead_value", "GA4", 3, expected_window("2026-09-14T10:00:00+08:00", "30D"), "E_B4")])
        result = evaluate_outcome(payload)
        self.assertTrue(result.is_valid)
        self.assertEqual(result.outcome["outcome_state"], "INSUFFICIENT_DATA")
        self.assertIn("BUSINESS_ATTRIBUTION_CONTRACT_REQUIRED", result.outcome["conflicts"])

    def test_candidate_revision_and_bridge_revision_are_exact(self):
        payload = input_payload()
        altered = dict(payload["implementation_anchor"], bridge_revision=2)
        altered.pop("content_hash", None)
        payload["implementation_anchor"] = create_implementation_anchor(altered)
        result = evaluate_outcome(payload)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.validation.errors[0].code, "BRIDGE_REVISION_MISMATCH")

    def test_same_payload_is_deterministic_without_wall_clock(self):
        first = evaluate_outcome(input_payload()).outcome
        second = evaluate_outcome(input_payload()).outcome
        self.assertEqual(first, second)

    def test_outcome_schema_and_hash_are_valid(self):
        result = evaluate_outcome(input_payload())
        self.assertTrue(validate_outcome_record(result.outcome).is_valid, validate_outcome_record(result.outcome).as_dict())
        self.assertEqual(result.outcome["content_hash"], content_hash(result.outcome))

    def test_store_is_append_only_revisioned_and_idempotent(self):
        result = evaluate_outcome(input_payload())
        with tempfile.TemporaryDirectory() as temp:
            store = OutcomeStore(temp)
            first = store.append_outcome(result.outcome)
            idem = store.append_outcome(result.outcome)
            self.assertTrue(idem["idempotent"])
            changed = copy.deepcopy(result.outcome)
            changed["revision"] = 2
            changed["supersedes_outcome_revision"] = 1
            changed["checkpoint"] = "60D"
            changed["content_hash"] = content_hash(changed)
            second = store.append_outcome(changed)
            self.assertEqual([row["revision"] for row in store.history(first["outcome_track_id"])], [1, 2])
            self.assertEqual(second["supersedes_outcome_revision"], 1)
            with self.assertRaises(Exception):
                store.append_outcome(dict(changed, conflicts=["tampered"]))

    def test_new_candidate_revision_cannot_inherit_outcome_history(self):
        result = evaluate_outcome(input_payload())
        with tempfile.TemporaryDirectory() as temp:
            store = OutcomeStore(temp)
            store.append_outcome(result.outcome)
            changed = copy.deepcopy(result.outcome)
            changed["revision"] = 2
            changed["supersedes_outcome_revision"] = 1
            changed["candidate_revision"] = 2
            changed["candidate_hash"] = "b" * 64
            changed["content_hash"] = content_hash(changed)
            with self.assertRaises(Exception):
                store.append_outcome(changed)

    def test_preview_is_deterministic_and_read_only(self):
        result = evaluate_outcome(input_payload())
        before = copy.deepcopy(result.outcome)
        first = outcome_preview([result])
        second = outcome_preview([result])
        self.assertEqual(first, second)
        self.assertEqual(result.outcome, before)
        self.assertEqual(first["production_mutation"], 0)
        self.assertIn("# Outcome tracking preview", render_outcome_preview([result], format="markdown"))

    def test_no_production_or_live_source_tokens(self):
        self.assertEqual(FIXTURE["metadata"]["source"], "offline-only")
        source = (ROOT / "reporting/opportunity/outcomes.py").read_text(encoding="utf-8")
        self.assertNotIn("requests.get", source)
        self.assertNotIn("googleapiclient", source)


if __name__ == "__main__":
    unittest.main()
