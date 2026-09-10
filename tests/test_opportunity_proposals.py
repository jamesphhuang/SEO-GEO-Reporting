import copy
import json
import unittest
from pathlib import Path

from reporting.opportunity.proposal_validation import (
    candidate_content_hash,
    validate_ahrefs_scope,
    validate_opportunity,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "opportunity"
EXAMPLES = ROOT / "docs" / "opportunity-intelligence" / "examples"


def load_json(path):
    return json.loads(path.read_text())


def ahrefs_fixture():
    return load_json(EXAMPLES / "ahrefs_scope.synthetic.json")


def opportunity_fixture():
    return load_json(EXAMPLES / "opportunity.synthetic.json")


def context_fixture():
    return load_json(FIXTURES / "evidence_context.json")


def refresh_hash(payload):
    payload["content_hash"] = candidate_content_hash(payload)
    return payload


def validated_fixture():
    payload = opportunity_fixture()
    payload["evidence_refs"].append("SYNTHETIC_BUSINESS")
    payload.update(
        business_evidence_ref="SYNTHETIC_BUSINESS",
        business_override_ref="SYNTHETIC_BUSINESS_OVERRIDE",
        scope_approval_ref="SYNTHETIC_SCOPE_APPROVAL",
        measurement_plan_ref="SYNTHETIC_PLAN",
        business_score=3,
        missing_evidence_roles=[],
        status="VALIDATED",
        validation_state="PASS",
        confidence="MEDIUM",
        evidence_count=6,
        independent_family_count=5,
        opportunity_score=83,
        score_lower_bound=82,
        score_upper_bound=83,
    )
    payload["score_explanations"]["business_score"] = {
        "rationale": "Synthetic approved business overlay",
        "evidence_refs": ["SYNTHETIC_BUSINESS"],
    }
    return refresh_hash(payload)


def approved_fixture():
    payload = validated_fixture()
    payload.update(
        status="APPROVED",
        review_state="APPROVED",
        review_event_ref="SYNTHETIC_REVIEW",
    )
    return refresh_hash(payload)


class AhrefsScopeValidationTests(unittest.TestCase):
    def test_pending_synthetic_scope_is_valid(self):
        result = validate_ahrefs_scope(ahrefs_fixture())
        self.assertTrue(result.is_valid, result.as_dict())

    def test_source_class_and_estimate_flag_are_enforced(self):
        payload = ahrefs_fixture()
        payload["source_class"] = "FIRST_PARTY_ACTUAL"
        payload["estimation_flag"] = False
        result = validate_ahrefs_scope(payload)
        codes = {error.code for error in result.errors}
        self.assertIn("SOURCE_CLASS_CONFLICT", codes)
        self.assertIn("ESTIMATE_CLASSIFICATION_CONFLICT", codes)

    def test_explicit_date_and_timezone_aware_datetime(self):
        invalid_date = ahrefs_fixture()
        invalid_date["snapshot_date"] = "2026-99-99"
        invalid_datetime = ahrefs_fixture()
        invalid_datetime["retrieved_at"] = "2026-09-10T00:00:00"
        self.assertIn("INVALID_DATE", {error.code for error in validate_ahrefs_scope(invalid_date).errors})
        self.assertIn("INVALID_DATETIME", {error.code for error in validate_ahrefs_scope(invalid_datetime).errors})

    def test_historical_date_order_and_stale_snapshot_fail_closed(self):
        payload = ahrefs_fixture()
        payload["historical_semantics"]["compared_date"] = "2026-09-10"
        result = validate_ahrefs_scope(payload, decision_at="2026-09-10T00:00:00Z")
        self.assertIn("INVALID_DATE_ORDER", {error.code for error in result.errors})

        stale = ahrefs_fixture()
        stale["snapshot_date"] = "2026-01-01"
        result = validate_ahrefs_scope(stale, decision_at="2026-09-10T00:00:00Z")
        self.assertIn("STALE_EVIDENCE_POLICY_VIOLATION", {error.code for error in result.errors})

    def test_approved_scope_requires_local_approval_context(self):
        payload = ahrefs_fixture()
        payload.update(approval_state="APPROVED", approval_ref="SYNTHETIC_SCOPE_APPROVAL")
        result = validate_ahrefs_scope(payload)
        self.assertIn("APPROVAL_EVIDENCE_MISSING", {error.code for error in result.errors})

        context = context_fixture()
        self.assertTrue(validate_ahrefs_scope(payload, context=context).is_valid)

    def test_optional_capability_context_fails_closed(self):
        payload = ahrefs_fixture()
        result = validate_ahrefs_scope(payload, context={"capabilities": []})
        self.assertIn("CAPABILITY_MISSING", {error.code for error in result.errors})


class OpportunityPositiveTests(unittest.TestCase):
    def setUp(self):
        self.context = context_fixture()

    def test_existing_page_candidate_is_valid_with_resolved_context(self):
        result = validate_opportunity(opportunity_fixture(), context=self.context)
        self.assertTrue(result.is_valid, result.as_dict())

    def test_discovered_state_is_valid_with_one_observation_family(self):
        payload = opportunity_fixture()
        payload["status"] = "DISCOVERED"
        payload["independent_family_count"] = 4
        result = validate_opportunity(payload, context=self.context)
        self.assertTrue(result.is_valid, result.as_dict())

    def test_new_content_candidate_uses_seo_new_without_fake_traction_zero(self):
        payload = opportunity_fixture()
        payload.update(
            opportunity_type="CONTENT_GAP",
            existing_url=None,
            existing_urls=[],
            target_url=None,
            recommended_action="CREATE_NEW",
            evidence_refs=["SYNTHETIC_AHREFS", "SYNTHETIC_SERP", "SYNTHETIC_SF"],
            gsc_evidence_ref=None,
            sf_evidence_ref="SYNTHETIC_SF",
            serp_evidence_ref="SYNTHETIC_SERP",
            score_profile="SEO_NEW",
            demand_score=3,
            traction_score=None,
            business_score=None,
            attainability_score=3,
            geo_score=None,
            execution_score=4,
            opportunity_score=None,
            score_lower_bound=57,
            score_upper_bound=88,
            evidence_count=3,
            independent_family_count=3,
            required_evidence_roles=["demand", "technical", "intent", "business_relevance"],
            missing_evidence_roles=["business_relevance", "scope_approval"],
        )
        payload["score_explanations"]["traction_score"] = {"rationale": "Not active for SEO_NEW", "evidence_refs": []}
        payload["score_explanations"]["execution_score"]["evidence_refs"] = ["SYNTHETIC_SF"]
        refresh_hash(payload)
        result = validate_opportunity(payload, context=self.context)
        self.assertTrue(result.is_valid, result.as_dict())

    def test_geo_candidate_uses_geo_profile_and_sample(self):
        payload = opportunity_fixture()
        payload.update(
            opportunity_type="GEO_GAP",
            recommended_action="GEO_ENHANCE",
            evidence_refs=["SYNTHETIC_AHREFS", "SYNTHETIC_GSC", "SYNTHETIC_SF", "SYNTHETIC_SERP", "SYNTHETIC_GEO"],
            geo_evidence_ref="SYNTHETIC_GEO",
            score_profile="GEO",
            demand_score=3,
            traction_score=2,
            business_score=None,
            attainability_score=3,
            geo_score=3,
            execution_score=4,
            opportunity_score=None,
            score_lower_bound=53,
            score_upper_bound=84,
            evidence_count=5,
            independent_family_count=5,
            missing_evidence_roles=["business_relevance", "scope_approval"],
        )
        payload["score_explanations"]["geo_score"] = {
            "rationale": "Synthetic fixed GEO cohort gap",
            "evidence_refs": ["SYNTHETIC_GEO"],
        }
        payload["score_explanations"]["execution_score"]["evidence_refs"] = ["SYNTHETIC_SF"]
        refresh_hash(payload)
        result = validate_opportunity(payload, context=self.context)
        self.assertTrue(result.is_valid, result.as_dict())

    def test_validated_and_approved_mock_human_records_are_valid(self):
        validated = validated_fixture()
        result = validate_opportunity(validated, context=self.context)
        self.assertTrue(result.is_valid, result.as_dict())

        approved = approved_fixture()
        context = copy.deepcopy(self.context)
        context["review_events"] = {
            "SYNTHETIC_REVIEW": {
                "reviewer_id": "mock-human-reviewer",
                "authenticated": True,
                "decision": "APPROVED",
                "candidate_revision": 1,
                "candidate_hash": approved["content_hash"],
                "approved_action": "UPDATE_EXISTING",
            }
        }
        result = validate_opportunity(approved, context=context)
        self.assertTrue(result.is_valid, result.as_dict())


class OpportunityNegativeSemanticTests(unittest.TestCase):
    def setUp(self):
        self.base = opportunity_fixture()
        self.context = context_fixture()

    def assertInvalid(self, payload, *codes, context=None):
        result = validate_opportunity(payload, context=context or self.context)
        found = {error.code for error in result.errors}
        for code in codes:
            self.assertIn(code, found, result.as_dict())
        self.assertFalse(result.is_valid)

    def test_fixture_inventory_is_explicit(self):
        cases = load_json(FIXTURES / "negative_cases.json")["cases"]
        self.assertGreaterEqual(len(cases), 12)
        self.assertIn("missing_is_not_zero", cases)
        self.assertIn("conflicting_evidence_high_confidence", cases)

    def test_invalid_period_and_datetime(self):
        payload = copy.deepcopy(self.base)
        payload["period"] = "2026-13"
        self.assertInvalid(payload, "INVALID_PERIOD", "SCHEMA_VIOLATION")
        payload = copy.deepcopy(self.base)
        payload["created_at"] = "2026-09-10T00:00:00"
        self.assertInvalid(payload, "INVALID_DATETIME")

    def test_missing_and_duplicate_evidence_are_distinct(self):
        payload = copy.deepcopy(self.base)
        payload["evidence_refs"].append("SYNTHETIC_AHREFS")
        self.assertInvalid(payload, "DUPLICATE_EVIDENCE_REF")
        payload = copy.deepcopy(self.base)
        context = copy.deepcopy(self.context)
        del context["evidence"]["SYNTHETIC_SERP"]
        self.assertInvalid(payload, "EVIDENCE_REF_MISSING", "EVIDENCE_COUNT_MISMATCH", context=context)

    def test_evidence_count_and_source_class_are_checked(self):
        payload = copy.deepcopy(self.base)
        payload["evidence_count"] = 2
        self.assertInvalid(payload, "EVIDENCE_COUNT_MISMATCH")
        context = copy.deepcopy(self.context)
        context["evidence"]["SYNTHETIC_AHREFS"]["source_class"] = "FIRST_PARTY_ACTUAL"
        self.assertInvalid(self.base, "SOURCE_CLASS_CONFLICT", context=context)

    def test_score_mismatch_unknown_profile_and_profile_switch_fail(self):
        payload = copy.deepcopy(self.base)
        payload["score_upper_bound"] = 1
        self.assertInvalid(payload, "SCORE_MISMATCH")
        payload = copy.deepcopy(self.base)
        payload["score_profile"] = "UNKNOWN"
        self.assertInvalid(payload, "UNKNOWN_SCORING_PROFILE", "SCHEMA_VIOLATION")
        payload = copy.deepcopy(self.base)
        payload["recommended_action"] = "CREATE_NEW"
        payload["existing_url"] = None
        payload["existing_urls"] = []
        self.assertInvalid(payload, "INVALID_ACTION_FOR_OPPORTUNITY")

    def test_missing_is_not_zero_and_stale_evidence_cannot_validate(self):
        payload = copy.deepcopy(self.base)
        payload["business_score"] = 0
        self.assertInvalid(payload, "MISSING_DATA_NOT_ZERO", "MISSING_BUSINESS_EVIDENCE")

        validated = validated_fixture()
        context = copy.deepcopy(self.context)
        context["evidence"]["SYNTHETIC_GSC"]["freshness_state"] = "STALE"
        self.assertInvalid(validated, "STALE_EVIDENCE_POLICY_VIOLATION", context=context)

    def test_conflict_high_confidence_and_approval_without_human_fail(self):
        payload = copy.deepcopy(self.base)
        payload["confidence"] = "HIGH"
        payload["validation_state"] = "CONFLICTING_EVIDENCE"
        context = copy.deepcopy(self.context)
        context["evidence"]["SYNTHETIC_GSC"]["conflict"] = True
        self.assertInvalid(payload, "EVIDENCE_CONFLICT", "CONFIDENCE_EVIDENCE_MISMATCH", context=context)

        approved = approved_fixture()
        self.assertInvalid(approved, "APPROVAL_EVIDENCE_MISSING")

    def test_create_new_existing_url_and_unsafe_url_fail(self):
        payload = copy.deepcopy(self.base)
        payload["recommended_action"] = "CREATE_NEW"
        self.assertInvalid(payload, "CREATE_NEW_EXISTING_URL_CONFLICT", "INVALID_ACTION_FOR_OPPORTUNITY")
        payload = copy.deepcopy(self.base)
        payload["existing_url"] = "https://user:password@example.com/page?email=synthetic@example.com"
        refresh_hash(payload)
        self.assertInvalid(payload, "INVALID_URL")

    def test_future_timestamp_and_review_hash_fail_closed(self):
        payload = copy.deepcopy(self.base)
        payload["updated_at"] = "2026-09-11T00:00:00Z"
        self.assertInvalid(payload, "FUTURE_TIMESTAMP")

        approved = approved_fixture()
        context = copy.deepcopy(self.context)
        context["review_events"] = {
            "SYNTHETIC_REVIEW": {
                "reviewer_id": "mock-human-reviewer",
                "authenticated": True,
                "decision": "APPROVED",
                "candidate_revision": 1,
                "candidate_hash": "0" * 64,
            }
        }
        self.assertInvalid(approved, "INVALID_REVIEW_STATE", context=context)


if __name__ == "__main__":
    unittest.main()
