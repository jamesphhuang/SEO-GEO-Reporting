import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from reporting.opportunity.review import (
    DECISIONS,
    HumanReviewStore,
    create_human_review,
    validate_human_review,
)
from reporting.opportunity.review_bridge import (
    CANDIDATE_ACTIONS,
    RecommendationBridgeStore,
    build_recommendation_bridge,
    project_review_status,
    validate_recommendation_bridge,
)
from reporting.opportunity.store.serialization import content_hash


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(
    (ROOT / "tests/fixtures/opportunity_review/scenarios.json").read_text(encoding="utf-8")
)
DECISION_AT = FIXTURE["metadata"]["sample_dates"]["decision_at"]
REVIEWER = {
    "actor_type": "HUMAN",
    "actor_ref": "reviewer_wp10",
    "authenticated": True,
    "identity_source": "UAT_REVIEW_SURFACE",
}


def candidate(letter):
    return copy.deepcopy(next(item["candidate"] for item in FIXTURE["scenarios"] if item["id"] == letter))


def recalculate(candidate_value):
    candidate_value["content_hash"] = content_hash(candidate_value)
    return candidate_value


def review_for(candidate_value, decision="APPROVE", **kwargs):
    values = {
        "reviewer": REVIEWER,
        "decision": decision,
        "reason_code": kwargs.pop("reason_code", "WP10_UAT_REVIEW"),
        "decision_at": DECISION_AT,
    }
    values.update(kwargs)
    return create_human_review(candidate_value, **values)


class OpportunityReviewTests(unittest.TestCase):
    def test_fixture_is_synthetic_and_covers_a_to_p(self):
        self.assertTrue(FIXTURE["metadata"]["synthetic"])
        self.assertEqual([item["id"] for item in FIXTURE["scenarios"]], list("ABCDEFGHIJKLMNOP"))
        self.assertEqual(FIXTURE["metadata"]["production_mutation"], 0)

    def test_proposal_schemas_are_valid_draft_2020_12(self):
        for name in ("human_review.v1.proposal.json", "recommendation_bridge.v1.proposal.json"):
            schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            self.assertEqual(schema["x-proposal-status"], "DRAFT_NOT_APPROVED")
            self.assertFalse(schema["x-production-activation"])

    def test_all_review_decisions_are_distinct_from_candidate_actions(self):
        self.assertEqual(DECISIONS, frozenset({"APPROVE", "REJECT", "NEEDS_MORE_EVIDENCE", "DEFER", "RETURN_FOR_REVIEW"}))
        self.assertIn("DO_NOTHING", CANDIDATE_ACTIONS)
        self.assertNotEqual("DO_NOTHING", "REJECT")
        self.assertNotEqual("MONITOR", "DEFER")

    def test_authenticated_human_approval_creates_bridge(self):
        value = candidate("A")
        before = copy.deepcopy(value)
        review = review_for(value)
        self.assertTrue(review.is_valid, review.as_dict())
        bridge = build_recommendation_bridge(value, review.review)
        self.assertTrue(bridge.is_valid, bridge.as_dict())
        self.assertEqual(bridge.bridge["review_decision"], "APPROVE")
        self.assertEqual(bridge.bridge["approval_meaning"], "RECOMMENDATION_WORKFLOW_ENTRY_ONLY")
        self.assertEqual(bridge.bridge["candidate_score"], value["score"])
        self.assertEqual(bridge.bridge["candidate_confidence"], value["confidence"])
        self.assertEqual(bridge.bridge["validation_state"], "PASS")
        self.assertEqual(value, before)

    def test_review_and_bridge_pin_candidate_revision_and_hash(self):
        value = candidate("A")
        review = review_for(value)
        self.assertEqual(review.review["candidate_revision"], 1)
        self.assertEqual(review.review["candidate_hash"], value["content_hash"])
        bridge = build_recommendation_bridge(value, review.review)
        self.assertEqual(bridge.bridge["candidate_revision"], 1)
        self.assertEqual(bridge.bridge["candidate_hash"], value["content_hash"])

    def test_evidence_and_diagnostic_pins_are_retained(self):
        value = candidate("A")
        diagnostic = {"evidence_id": "EVID_WP10_A_GA4", "revision": 2, "content_hash": "b" * 64}
        review = review_for(value, ga4_diagnostic_ref=diagnostic, serp_validation_ref=value["evidence_refs"][1])
        self.assertTrue(review.is_valid, review.as_dict())
        bridge = build_recommendation_bridge(value, review.review)
        self.assertTrue(bridge.is_valid, bridge.as_dict())
        self.assertEqual(bridge.bridge["ga4_diagnostic_ref"], diagnostic)
        self.assertEqual(bridge.bridge["candidate_evidence_refs"], value["evidence_refs"])

    def test_reject_preserves_candidate_and_creates_no_bridge(self):
        value = candidate("B")
        before = copy.deepcopy(value)
        review = review_for(value, decision="REJECT")
        self.assertTrue(review.is_valid)
        bridge = build_recommendation_bridge(value, review.review)
        self.assertFalse(bridge.is_valid)
        self.assertEqual(bridge.validation.errors[0].code, "HUMAN_APPROVAL_REQUIRED")
        self.assertEqual(value, before)

    def test_no_review_cannot_create_bridge(self):
        result = build_recommendation_bridge(candidate("C"), None)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.validation.errors[0].code, "INVALID_REVIEW")

    def test_system_or_ai_actor_cannot_satisfy_human_gate(self):
        value = candidate("D")
        for actor in (
            {"actor_type": "SYSTEM", "actor_ref": "system", "authenticated": True, "identity_source": "RULE_ENGINE"},
            {"actor_type": "HUMAN", "actor_ref": "AI_ASSISTED", "authenticated": True, "identity_source": "UAT_REVIEW_SURFACE"},
        ):
            result = create_human_review(value, reviewer=actor, decision="APPROVE", reason_code="BAD_ACTOR", decision_at=DECISION_AT)
            self.assertFalse(result.is_valid)
            self.assertIsNone(result.review)

    def test_revision_change_does_not_inherit_old_approval(self):
        value = candidate("E")
        review = review_for(value)
        changed = copy.deepcopy(value)
        changed["revision"] = 2
        changed["score"] = 77
        recalculate(changed)
        result = build_recommendation_bridge(changed, review.review)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.validation.errors[0].code, "CANDIDATE_REVISION_MISMATCH")

    def test_evidence_hash_mismatch_blocks_bridge(self):
        value = candidate("F")
        review = review_for(value, candidate_evidence_refs=[
            {"evidence_id": value["evidence_refs"][0]["evidence_id"], "revision": 1, "content_hash": "f" * 64},
            value["evidence_refs"][1],
        ])
        self.assertTrue(review.is_valid)
        result = build_recommendation_bridge(value, review.review)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.validation.errors[0].code, "EVIDENCE_PIN_MISMATCH")

    def test_conflict_requires_adjudication_and_is_preserved(self):
        value = candidate("G")
        review = review_for(value)
        blocked = build_recommendation_bridge(value, review.review)
        self.assertFalse(blocked.is_valid)
        self.assertEqual(blocked.validation.errors[0].code, "CONFLICT_ADJUDICATION_REQUIRED")
        review = review_for(value, conflict_adjudication_ref="ADJ_WP10_G_SERP")
        bridge = build_recommendation_bridge(value, review.review)
        self.assertTrue(bridge.is_valid, bridge.as_dict())
        self.assertEqual(bridge.bridge["conflicts"], ["SERP_CONFLICT"])

    def test_geo_weak_can_be_rejected_without_erasing_conflict(self):
        value = candidate("H")
        review = review_for(value, decision="REJECT")
        self.assertTrue(review.is_valid)
        self.assertFalse(build_recommendation_bridge(value, review.review).is_valid)
        self.assertIn("GEO_WEAK", value["conflicts"])

    def test_do_nothing_is_reviewable(self):
        value = candidate("I")
        self.assertEqual(value["recommended_action"], "DO_NOTHING")
        review = review_for(value)
        bridge = build_recommendation_bridge(value, review.review)
        self.assertTrue(bridge.is_valid, bridge.as_dict())
        self.assertEqual(bridge.bridge["candidate_action"], "DO_NOTHING")

    def test_needs_more_evidence_never_creates_bridge(self):
        value = candidate("J")
        review = review_for(value, decision="NEEDS_MORE_EVIDENCE")
        self.assertTrue(review.is_valid)
        result = build_recommendation_bridge(value, review.review)
        self.assertFalse(result.is_valid)
        self.assertEqual(result.validation.errors[0].code, "HUMAN_APPROVAL_REQUIRED")

    def test_stale_and_missing_evidence_are_fail_closed(self):
        stale = candidate("K")
        stale_review = review_for(stale)
        stale_result = build_recommendation_bridge(stale, stale_review.review)
        self.assertFalse(stale_result.is_valid)
        self.assertEqual(stale_result.validation.errors[0].code, "STALE_EVIDENCE_BLOCKED")
        missing = candidate("P")
        missing_review = review_for(missing)
        missing_result = build_recommendation_bridge(missing, missing_review.review)
        self.assertFalse(missing_result.is_valid)
        self.assertEqual(missing_result.validation.errors[0].code, "MISSING_REQUIRED_EVIDENCE")

    def test_serp_not_checked_policy_gap_and_capability_gap_block(self):
        for field, value, code in (
            ("serp_status", "SERP_NOT_CHECKED", "SERP_VALIDATION_REQUIRED"),
            ("policy_gaps", ["CONTENT_GAP_POLICY_UNAPPROVED"], "POLICY_GAP_BLOCKED"),
            ("capability_gaps", ["CITATION_NOT_CAPTURED"], "CAPABILITY_GAP_BLOCKED"),
        ):
            candidate_value = candidate("A")
            candidate_value[field] = value
            recalculate(candidate_value)
            review = review_for(candidate_value)
            result = build_recommendation_bridge(candidate_value, review.review)
            self.assertFalse(result.is_valid)
            self.assertEqual(result.validation.errors[0].code, code)

    def test_review_store_is_append_only_and_retains_history(self):
        value = candidate("L")
        with tempfile.TemporaryDirectory() as temp:
            store = HumanReviewStore(temp)
            first = review_for(value, notes="first decision")
            first_stored = store.append_review(first.review)
            second = review_for(value, revision=2, review_id=first_stored["review_id"], decision="RETURN_FOR_REVIEW", notes="new evidence needed")
            second_stored = store.append_review(second.review)
            history = store.history(first_stored["review_id"])
            self.assertEqual([row["revision"] for row in history], [1, 2])
            self.assertEqual(history[0]["decision"], "APPROVE")
            self.assertEqual(second_stored["supersedes_review_revision"], 1)
            self.assertEqual(store.get_review(first_stored["review_id"], 1)["notes"], "first decision")
            with self.assertRaises(Exception):
                store.append_review({**first_stored, "notes": "tampered"})

    def test_superseded_review_cannot_be_used_as_current_approval(self):
        value = candidate("L")
        with tempfile.TemporaryDirectory() as temp:
            store = HumanReviewStore(temp)
            first = review_for(value)
            store.append_review(first.review)
            second = review_for(value, revision=2, review_id=first.review["review_id"], decision="REJECT")
            store.append_review(second.review)
            result = build_recommendation_bridge(value, first.review, review_store=store)
            self.assertFalse(result.is_valid)
            self.assertEqual(result.validation.errors[0].code, "SUPERSEDED_REVIEW")

    def test_bridge_store_is_append_only_and_revisioned(self):
        value = candidate("M")
        first_review = review_for(value)
        second_review = review_for(value, revision=2, review_id=first_review.review["review_id"], notes="re-approved after review")
        with tempfile.TemporaryDirectory() as temp:
            review_store = HumanReviewStore(Path(temp) / "reviews")
            review_store.append_review(first_review.review)
            review_store.append_review(second_review.review)
            bridge_store = RecommendationBridgeStore(Path(temp) / "bridges")
            first = build_recommendation_bridge(value, first_review.review, bridge_store=bridge_store, persist=True)
            self.assertTrue(first.persisted, first.as_dict())
            second = build_recommendation_bridge(value, second_review.review, revision=2, bridge_store=bridge_store, persist=True)
            self.assertTrue(second.persisted, second.as_dict())
            history = bridge_store.history(first.bridge["bridge_id"])
            self.assertEqual([row["revision"] for row in history], [1, 2])
            self.assertEqual(history[0]["content_hash"], first.bridge["content_hash"])
            self.assertEqual(history[0]["review_revision"], 1)

    def test_deterministic_bridge_hash_for_same_pins(self):
        value = candidate("N")
        review = review_for(value)
        left = build_recommendation_bridge(value, review.review)
        right = build_recommendation_bridge(value, review.review)
        self.assertTrue(left.is_valid and right.is_valid)
        self.assertEqual(left.bridge, right.bridge)
        self.assertEqual(left.bridge["content_hash"], right.bridge["content_hash"])

    def test_human_note_does_not_recompute_candidate_semantics(self):
        value = candidate("O")
        before = copy.deepcopy(value)
        review = review_for(value, notes="Human-authored review note")
        bridge = build_recommendation_bridge(value, review.review, human_text="Keep the existing page brief.", text_provenance="HUMAN_AUTHORED")
        self.assertTrue(bridge.is_valid, bridge.as_dict())
        self.assertEqual(value["score"], before["score"])
        self.assertEqual(value["confidence"], before["confidence"])
        self.assertEqual(value["evidence_refs"], before["evidence_refs"])
        self.assertEqual(review.review["notes_provenance"], "HUMAN_AUTHORED")

    def test_ai_draft_stays_draft_only_until_human_review(self):
        value = candidate("A")
        result = build_recommendation_bridge(value, None, human_text="AI draft", text_provenance="DRAFT_ONLY")
        self.assertFalse(result.is_valid)
        approved = build_recommendation_bridge(value, review_for(value).review, human_text="AI draft", text_provenance="DRAFT_ONLY")
        self.assertTrue(approved.is_valid)
        self.assertEqual(approved.bridge["text_provenance"], "DRAFT_ONLY")
        self.assertEqual(approved.bridge["approval_meaning"], "RECOMMENDATION_WORKFLOW_ENTRY_ONLY")

    def test_review_projection_is_read_only_and_distinguishes_status(self):
        value = candidate("A")
        review = review_for(value)
        bridge = build_recommendation_bridge(value, review.review)
        projection = project_review_status(value, review.review, bridge.bridge)
        self.assertEqual(projection["review_status"], "APPROVED")
        self.assertEqual(projection["recommendation_bridge_status"], "BRIDGE_READY")
        self.assertTrue(projection["read_only_projection"])
        self.assertFalse(projection["next_steps_written"])

    def test_bridge_never_writes_next_steps_or_production(self):
        value = candidate("P")
        # P is intentionally missing GA4, so use A for a successful bridge.
        value = candidate("A")
        bridge = build_recommendation_bridge(value, review_for(value).review)
        self.assertTrue(bridge.is_valid)
        self.assertFalse(bridge.bridge["next_steps_written"])
        self.assertFalse(bridge.bridge["production_mutation"])
        self.assertNotIn("next_step", bridge.bridge)
        invalid = dict(bridge.bridge)
        invalid["next_step"] = "write production task"
        self.assertFalse(validate_recommendation_bridge(invalid).is_valid)

    def test_invalid_revision_and_hash_fail_closed(self):
        value = candidate("A")
        bad = copy.deepcopy(value)
        bad["score"] = 1
        result = review_for(bad)
        self.assertFalse(result.is_valid)
        self.assertTrue(any(error.code == "CANDIDATE_HASH_MISMATCH" for error in result.validation.errors))
        review = review_for(value)
        tampered = dict(review.review)
        tampered["candidate_hash"] = "f" * 64
        self.assertFalse(validate_human_review(tampered).is_valid)


if __name__ == "__main__":
    unittest.main()
