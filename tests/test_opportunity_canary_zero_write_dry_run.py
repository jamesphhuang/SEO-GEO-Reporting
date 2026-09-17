import copy
import hashlib
import json
import unittest
from pathlib import Path

from reporting.opportunity.canary_dry_run import (
    LIVE_WRITE_BLOCKERS,
    ZERO_WRITE_MODE,
    ZeroWriteBlocked,
    ZeroWriteTransportGuard,
    plan_zero_write,
    validate_durable_binding,
)
from reporting.opportunity.canary_writer import ALLOWED_FIELDS, PROTECTED_FIELDS, TARGET_TAB
from reporting.opportunity.review import create_human_review
from reporting.opportunity.review_bridge import build_recommendation_bridge
from reporting.opportunity.trusted_review_identity import (
    TrustedIdentityEvidence,
    TrustedReviewBinding,
    VerifiedProviderIdentity,
    reviewer_subject_ref,
)


ROOT = Path(__file__).resolve().parents[1]
REVIEW_FIXTURE = json.loads((ROOT / "tests/fixtures/opportunity_review/scenarios.json").read_text())
DECISION_AT = REVIEW_FIXTURE["metadata"]["sample_dates"]["decision_at"]
REVIEWER = {"actor_type": "HUMAN", "actor_ref": "reviewer_canary", "authenticated": True, "identity_source": "UAT_REVIEW_SURFACE"}


def trusted_context():
    value = {
        "binding_version": "trusted-review-identity-binding.v1",
        "provider": "GOOGLE_WORKSPACE",
        "reviewer_subject_ref": reviewer_subject_ref("synthetic-google-subject-a"),
        "workspace_domain": "shopline.com",
        "role": "RECOMMENDATION_APPROVER",
        "scope": "PHASE1_CANARY",
        "status": "ACTIVE",
        "binding_revision": 1,
        "provider_verification_method": "GOOGLE_OIDC_ID_TOKEN_V1",
        "same_person_writer_reviewer": True,
        "separation_of_duties_waiver": "APPROVED_PHASE1_CANARY_ONLY",
        "production_inheritance": False,
        "automatic_scope_expansion": False,
        "verified_at": "2026-09-17T09:00:00+08:00",
    }
    value["semantic_hash"] = digest(value)
    binding = TrustedReviewBinding.from_mapping(value)
    identity = VerifiedProviderIdentity.from_verified_google_claims(
        {"sub": "synthetic-google-subject-a", "hd": "shopline.com"},
        verified_at="2026-09-17T09:00:00+08:00",
    )
    evidence = TrustedIdentityEvidence.from_verified_provider_output(identity, binding)
    return {"binding": binding, "evidence": evidence}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def binding(**overrides):
    value = {
        "binding_version": "phase1-canary-environment-binding.v1",
        "environment": "PRODUCTION_CANARY",
        "drive_root_ref": "drive://folder/root",
        "canary_folder_ref": "drive://folder/canary",
        "opportunity_folder_ref": "drive://folder/opportunity",
        "workbook_ref": "drive://spreadsheet/workbook",
        "tab_name": TARGET_TAB,
        "audit_folder_ref": "drive://folder/audit",
        "principal_ref": "principal://authorized-user-oauth/runtime",
        "principal_type": "authorized-user OAuth",
        "acl_policy": {"domain": "shopline.com", "role": "reader", "status": "APPROVED"},
        "acl_verified": True,
        "recommendation_row_count": 0,
        "audit_binding": "VERIFIED",
        "trusted_review_identity": "NOT_VERIFIED",
        "verified_at": "2026-09-16T00:00:00+08:00",
        "production_activation": "NOT_AUTHORIZED",
        "secrets_persisted": False,
    }
    value.update(overrides)
    value["allowed_fields_hash"] = digest(list(ALLOWED_FIELDS))
    value["schema_hash"] = digest({"tab_name": TARGET_TAB, "fields": list(ALLOWED_FIELDS)})
    value["binding_semantic_hash"] = digest(value)
    return value


def operation(operation_id="OP_DRY_RUN_001", human_text="Publish the approved synthetic recommendation."):
    candidate = copy.deepcopy(next(item["candidate"] for item in REVIEW_FIXTURE["scenarios"] if item["id"] == "A"))
    review_result = create_human_review(candidate, reviewer=REVIEWER, decision="APPROVE", reason_code="CANARY_APPROVED", decision_at=DECISION_AT)
    assert review_result.is_valid, review_result.as_dict()
    bridge_result = build_recommendation_bridge(candidate, review_result.review, human_text=human_text, text_provenance="HUMAN_AUTHORED")
    assert bridge_result.is_valid, bridge_result.as_dict()
    return {
        "operation_id": operation_id,
        "candidate": candidate,
        "review": review_result.review,
        "bridge": bridge_result.bridge,
        "trusted_review_context": trusted_context(),
    }


class CanaryZeroWriteDryRunTests(unittest.TestCase):
    def test_valid_plan_is_non_executable_and_live_blocked(self):
        result = plan_zero_write([operation()], binding=binding())
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.state, "ZERO_WRITE_CONFIG_DRY_RUN")
        self.assertEqual(result.plan.transport_mode, ZERO_WRITE_MODE)
        self.assertEqual(set(result.plan.planned_fields), set(ALLOWED_FIELDS))
        self.assertEqual(set(result.plan.planned_fields) & set(PROTECTED_FIELDS), set())
        self.assertEqual(set(result.blockers), set(LIVE_WRITE_BLOCKERS))
        self.assertEqual(result.live_write_eligibility.startswith("BLOCKED_"), True)

    def test_binding_hash_mismatch_blocks(self):
        value = binding()
        value["workbook_ref"] = "drive://spreadsheet/wrong"
        result = plan_zero_write([operation()], binding=value)
        self.assertFalse(result.is_valid)
        self.assertIn("BINDING_HASH_MISMATCH", {item.code for item in result.validation.errors})

    def test_wrong_workbook_ref_blocks_after_rehash(self):
        value = binding(workbook_ref="drive://spreadsheet/wrong")
        result = plan_zero_write([operation()], binding=value, expected_workbook_ref="drive://spreadsheet/workbook")
        self.assertFalse(result.is_valid)
        self.assertIn("WORKBOOK_REF_MISMATCH", {item.code for item in result.validation.errors})

    def test_wrong_tab_blocks(self):
        value = binding(tab_name="Other")
        result = plan_zero_write([operation()], binding=value)
        self.assertFalse(result.is_valid)
        self.assertIn("TARGET_TAB_MISMATCH", {item.code for item in result.validation.errors})

    def test_schema_mismatch_blocks(self):
        value = binding()
        value["schema_hash"] = "0" * 64
        value["binding_semantic_hash"] = digest({k: v for k, v in value.items() if k != "binding_semantic_hash"})
        result = plan_zero_write([operation()], binding=value)
        self.assertFalse(result.is_valid)
        self.assertIn("SCHEMA_HASH_MISMATCH", {item.code for item in result.validation.errors})

    def test_nonzero_rows_blocks(self):
        value = binding(recommendation_row_count=1)
        value["binding_semantic_hash"] = digest({k: v for k, v in value.items() if k != "binding_semantic_hash"})
        result = plan_zero_write([operation()], binding=value)
        self.assertFalse(result.is_valid)
        self.assertIn("NONZERO_TARGET_ROWS", {item.code for item in result.validation.errors})

    def test_unauthorized_and_protected_fields_block(self):
        unauthorized = operation()
        unauthorized["payload_overrides"] = {"not_allowed": "x"}
        result = plan_zero_write([unauthorized], binding=binding())
        self.assertIn("PROTECTED_FIELD_MUTATION", {item.code for item in result.validation.errors})
        protected = operation()
        protected["protected_field_mutation"] = {"human_notes": "x"}
        result = plan_zero_write([protected], binding=binding())
        self.assertIn("PROTECTED_FIELD_MUTATION", {item.code for item in result.validation.errors})

    def test_operation_limit_blocks_without_truncation(self):
        result = plan_zero_write([operation(), operation("OP_DRY_RUN_002")], binding=binding())
        self.assertFalse(result.is_valid)
        self.assertIn("BLOCKED_OPERATION_LIMIT", {item.code for item in result.validation.errors})

    def test_same_input_is_deterministic_and_different_payload_changes_hash(self):
        first = plan_zero_write([operation()], binding=binding())
        second = plan_zero_write([operation()], binding=binding())
        changed = plan_zero_write([operation(human_text="A different approved synthetic recommendation.")], binding=binding())
        self.assertEqual(first.plan.idempotency_key, second.plan.idempotency_key)
        self.assertEqual(first.plan.payload_hash, second.plan.payload_hash)
        self.assertNotEqual(first.plan.idempotency_key, changed.plan.idempotency_key)
        self.assertNotEqual(first.plan.payload_hash, changed.plan.payload_hash)

    def test_kill_switch_blocks(self):
        result = plan_zero_write([operation()], binding=binding(), kill_switch=True)
        self.assertFalse(result.is_valid)
        self.assertIn("KILL_SWITCH_ENABLED", {item.code for item in result.validation.errors})

    def test_zero_write_guard_blocks_transport_and_audit_mutations(self):
        guard = ZeroWriteTransportGuard()
        for method in (guard.write, guard.append_cells, guard.update_cells, guard.values_append, guard.values_update, guard.batch_update, guard.write_audit_receipt, guard.mutate_acl, guard.mutate_drive):
            with self.assertRaises(ZeroWriteBlocked):
                method()
        self.assertEqual(len(guard.attempted_operations), 9)

    def test_contract_activation_and_trusted_identity_are_live_blockers(self):
        result = plan_zero_write([operation()], binding=binding(), trusted_review_identity_verified=False, production_contracts_approved=False)
        self.assertEqual(set(result.blockers), set(LIVE_WRITE_BLOCKERS))
        self.assertEqual(result.plan.production_activation, "NOT_AUTHORIZED")

    def test_missing_production_trusted_context_does_not_promote_live_write(self):
        value = operation()
        value["trusted_review_context"] = None
        result = plan_zero_write([value], binding=binding())
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertIn("TRUSTED_REVIEW_IDENTITY_NOT_VERIFIED", result.blockers)

    def test_durable_binding_validator_rejects_secret_like_fields(self):
        value = binding()
        value["access_token"] = "never"
        value["binding_semantic_hash"] = digest({k: v for k, v in value.items() if k != "binding_semantic_hash"})
        result = validate_durable_binding(value)
        self.assertFalse(result.is_valid)
        self.assertIn("SECRET_FIELD_PRESENT", {item.code for item in result.errors})

    def test_readback_and_audit_plans_are_descriptive_only(self):
        result = plan_zero_write([operation()], binding=binding())
        self.assertEqual(result.plan.readback_fields[0], "recommendation_id")
        self.assertEqual(result.plan.audit_name_template, "operation_<operation_id>.json")
        self.assertEqual(result.plan.audit_destination_ref, binding()["audit_folder_ref"])
        self.assertIsNone(result.plan.__dict__.get("write_intent"))


if __name__ == "__main__":
    unittest.main()
