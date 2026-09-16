import copy
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from reporting.opportunity.canary_writer import (
    ALLOWED_FIELDS,
    PROTECTED_FIELDS,
    TARGET_TAB,
    WRITER_ID,
    CanaryIdempotencyStore,
    GoogleSheetsTargetBinding,
    RecommendationAuditStore,
    RecommendationCanaryWriter,
    SyntheticRecommendationTransport,
    idempotency_key,
    validate_canary_contract,
)
from reporting.opportunity.review import create_human_review
from reporting.opportunity.review_bridge import build_recommendation_bridge
from reporting.opportunity.store.serialization import content_hash


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/opportunity_canary_writer/scenarios.json").read_text())
REVIEW_FIXTURE = json.loads((ROOT / "tests/fixtures/opportunity_review/scenarios.json").read_text())
DECISION_AT = REVIEW_FIXTURE["metadata"]["sample_dates"]["decision_at"]
REVIEWER = {"actor_type": "HUMAN", "actor_ref": "reviewer_canary", "authenticated": True, "identity_source": "UAT_REVIEW_SURFACE"}
TRUSTED = {"verified": True, "provider_ref": "synthetic://trusted-review-provider", "subject_ref": "synthetic://reviewer-canary"}


def candidate(letter="A"):
    return copy.deepcopy(next(item["candidate"] for item in REVIEW_FIXTURE["scenarios"] if item["id"] == letter))


def approved_operation(letter="A", operation_id="OP_CANARY_001", *, trusted=True, human_text="Publish the approved synthetic recommendation."):
    value = candidate(letter)
    review_result = create_human_review(value, reviewer=REVIEWER, decision="APPROVE", reason_code="CANARY_APPROVED", decision_at=DECISION_AT)
    assert review_result.is_valid, review_result.as_dict()
    bridge_result = build_recommendation_bridge(value, review_result.review, human_text=human_text, text_provenance="HUMAN_AUTHORED")
    assert bridge_result.is_valid, bridge_result.as_dict()
    return {
        "operation_id": operation_id,
        "candidate": value,
        "review": review_result.review,
        "bridge": bridge_result.bridge,
        "trusted_review_context": TRUSTED if trusted else None,
    }


def binding(**overrides):
    value = {
        "binding_id": "binding://canary/workbook",
        "environment": "UAT",
        "workbook_id_ref": "runtime://production-canary-workbook",
        "tab_name": TARGET_TAB,
        "allowed_fields": list(ALLOWED_FIELDS),
        "protected_fields": list(PROTECTED_FIELDS),
        "writer_principal_ref": "principal://authorized-user-oauth/runtime",
        "readback_required": True,
        "max_operations": 1,
        "created_at": "2026-09-16T09:00:00+08:00",
    }
    value.update(overrides)
    return value


class RecommendationCanaryWriterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.audit = RecommendationAuditStore(root / "95_Production Canary/Opportunity Intelligence/audit")
        self.idempotency = CanaryIdempotencyStore(root / "idempotency.jsonl")
        self.writer = RecommendationCanaryWriter(binding=binding(), audit_store=self.audit, idempotency_store=self.idempotency)

    def tearDown(self):
        self.temp.cleanup()

    def test_contract_and_fixture_are_synthetic_proposal_only(self):
        contract = json.loads((ROOT / "contracts/recommendation_canary_writer.v1.proposal.json").read_text())
        target = json.loads((ROOT / "contracts/google_sheets_target_binding.v1.proposal.json").read_text())
        Draft202012Validator.check_schema(contract)
        Draft202012Validator.check_schema(target)
        self.assertEqual(contract["x-proposal-status"], "DRAFT_NOT_APPROVED")
        self.assertFalse(contract["x-production-activation"])
        self.assertTrue(FIXTURE["metadata"]["synthetic"])
        self.assertEqual([item["id"] for item in FIXTURE["scenarios"]], list("ABCDEFGHIJKLMNOPQRSTUV"))

    def test_valid_canary_has_exact_allowlist_readback_and_audit(self):
        transport = SyntheticRecommendationTransport()
        result = self.writer.run([approved_operation()], transport=transport)
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.state, "CANARY_COMPLETE")
        self.assertEqual(result.readback_state, "READBACK_MATCHED")
        self.assertEqual(result.audit_receipt["target_tab"], TARGET_TAB)
        self.assertEqual(set(result.payload), set(ALLOWED_FIELDS))
        self.assertEqual(transport.write_calls, 1)
        self.assertEqual(result.production_mutation_count, 0)
        self.assertTrue((Path(self.temp.name) / "95_Production Canary/Opportunity Intelligence/audit/operation_OP_CANARY_001.json").exists())

    def test_contract_validator_does_not_promote_production(self):
        contract = json.loads((ROOT / "contracts/recommendation_canary_writer.v1.proposal.json").read_text())
        self.assertTrue(validate_canary_contract(contract).is_valid)
        changed = copy.deepcopy(contract)
        changed["x-production-activation"] = True
        self.assertFalse(validate_canary_contract(changed).is_valid)

    def test_more_than_one_operation_blocks_without_transport(self):
        transport = SyntheticRecommendationTransport()
        result = self.writer.run([approved_operation(), approved_operation(operation_id="OP_CANARY_002")], transport=transport)
        self.assertFalse(result.is_valid)
        self.assertIn("BLOCKED_OPERATION_LIMIT", {item.code for item in result.validation.errors})
        self.assertEqual(transport.write_calls, 0)

    def test_invalid_review_and_untrusted_review_block(self):
        operation = approved_operation()
        operation["review"]["decision"] = "REJECT"
        result = self.writer.run([operation], transport=SyntheticRecommendationTransport())
        self.assertIn("INVALID_REVIEW_PIN", {item.code for item in result.validation.errors})
        result = self.writer.run([approved_operation(trusted=False)], transport=SyntheticRecommendationTransport())
        self.assertIn("BLOCKED_TRUSTED_IDENTITY", {item.code for item in result.validation.errors})

    def test_superseded_review_and_bridge_hash_mismatch_block(self):
        operation = approved_operation()
        operation["review_superseded"] = True
        result = self.writer.run([operation], transport=SyntheticRecommendationTransport())
        self.assertIn("SUPERSEDED_REVIEW", {item.code for item in result.validation.errors})
        operation = approved_operation()
        operation["bridge"]["content_hash"] = "f" * 64
        result = self.writer.run([operation], transport=SyntheticRecommendationTransport())
        self.assertIn("INVALID_BRIDGE_PIN", {item.code for item in result.validation.errors})

    def test_target_and_principal_binding_are_runtime_refs(self):
        bad_target = RecommendationCanaryWriter(binding=binding(tab_name="Other"), audit_store=self.audit, idempotency_store=self.idempotency)
        result = bad_target.run([approved_operation()], transport=SyntheticRecommendationTransport())
        self.assertIn("TARGET_TAB_NOT_ALLOWED", {item.code for item in result.validation.errors})
        unknown_target = RecommendationCanaryWriter(binding=binding(binding_id="unknown", workbook_id_ref="workbook-id"), audit_store=self.audit, idempotency_store=self.idempotency)
        result = unknown_target.run([approved_operation()], transport=SyntheticRecommendationTransport())
        self.assertIn("TARGET_BINDING_UNKNOWN", {item.code for item in result.validation.errors})
        bad_principal = RecommendationCanaryWriter(binding=binding(writer_principal_ref=""), audit_store=self.audit, idempotency_store=self.idempotency)
        result = bad_principal.run([approved_operation()], transport=SyntheticRecommendationTransport())
        self.assertIn("INVALID_REFERENCE", {item.code for item in result.validation.errors})
        unknown_principal = RecommendationCanaryWriter(binding=binding(writer_principal_ref="principal://service-account/unknown"), audit_store=self.audit, idempotency_store=self.idempotency)
        result = unknown_principal.run([approved_operation()], transport=SyntheticRecommendationTransport())
        self.assertIn("WRITER_UNAUTHORIZED", {item.code for item in result.validation.errors})

    def test_protected_mutation_and_kill_switch_block_before_transport(self):
        transport = SyntheticRecommendationTransport()
        operation = approved_operation()
        operation["protected_field_mutation"] = {"human_notes": "do not write"}
        result = self.writer.run([operation], transport=transport)
        self.assertIn("PROTECTED_FIELD_MUTATION", {item.code for item in result.validation.errors})
        result = self.writer.run([approved_operation()], transport=transport, kill_switch=True)
        self.assertIn("KILL_SWITCH_ENABLED", {item.code for item in result.validation.errors})
        self.assertEqual(transport.write_calls, 0)

    def test_success_readback_mismatch_is_not_complete(self):
        result = self.writer.run([approved_operation()], transport=SyntheticRecommendationTransport("MISMATCH"))
        self.assertEqual(result.state, "READBACK_MISMATCH")
        self.assertFalse(result.is_valid)
        self.assertEqual(result.audit_receipt["readback_state"], "READBACK_MISMATCH")

    def test_timeout_exact_match_reconciles_without_retry(self):
        transport = SyntheticRecommendationTransport("TIMEOUT_WRITES")
        result = self.writer.run([approved_operation()], transport=transport)
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.reconciliation_state, "RECONCILED_SUCCESS")
        self.assertEqual(transport.write_calls, 1)

    def test_timeout_absent_requires_human_authorization_and_no_retry(self):
        transport = SyntheticRecommendationTransport("TIMEOUT_ABSENT")
        result = self.writer.run([approved_operation()], transport=transport)
        self.assertEqual(result.state, "BLOCKED")
        self.assertEqual(result.reconciliation_state, "SAFE_TO_RETRY_REQUIRES_HUMAN_AUTHORIZATION")
        self.assertEqual(transport.write_calls, 1)

    def test_timeout_conflicting_record_blocks(self):
        result = self.writer.run([approved_operation()], transport=SyntheticRecommendationTransport("TIMEOUT_CONFLICT"))
        self.assertEqual(result.state, "BLOCKED")
        self.assertEqual(result.reconciliation_state, "RECONCILIATION_CONFLICT")

    def test_rejected_transport_and_audit_failure_block(self):
        result = self.writer.run([approved_operation()], transport=SyntheticRecommendationTransport("REJECTED"))
        self.assertEqual(result.state, "BLOCKED")
        no_audit = RecommendationCanaryWriter(binding=binding(), audit_store=None, idempotency_store=self.idempotency)
        result = no_audit.run([approved_operation(operation_id="OP_CANARY_002")], transport=SyntheticRecommendationTransport())
        self.assertIn("AUDIT_UNAVAILABLE", {item.code for item in result.validation.errors})

    def test_replay_and_idempotency_conflict_do_not_duplicate(self):
        operation = approved_operation()
        first = self.writer.run([operation], transport=SyntheticRecommendationTransport())
        second = self.writer.run([copy.deepcopy(operation)], transport=SyntheticRecommendationTransport())
        self.assertTrue(first.is_valid)
        self.assertTrue(second.is_valid)
        self.assertEqual(second.reconciliation_state, "ALREADY_APPLIED")
        self.assertEqual(len(list(Path(self.audit.root).glob("operation_*.json"))), 1)
        conflict_key = first.write_intent.idempotency_key
        conflict_store = CanaryIdempotencyStore(Path(self.temp.name) / "conflict-idempotency.jsonl")
        conflict_store.record(conflict_key, "b" * 64)
        conflict_writer = RecommendationCanaryWriter(binding=binding(), audit_store=self.audit, idempotency_store=conflict_store)
        result = conflict_writer.run([copy.deepcopy(operation)], transport=SyntheticRecommendationTransport())
        self.assertIn("IDEMPOTENCY_CONFLICT", {item.code for item in result.validation.errors})

    def test_nested_secret_and_pii_are_rejected_without_leakage(self):
        operation = approved_operation()
        operation["metadata"] = {"nested": [{"api_key": "synthetic-secret"}, {"email": "person@example.invalid"}]}
        result = self.writer.run([operation], transport=SyntheticRecommendationTransport())
        codes = {item.code for item in result.validation.errors}
        self.assertIn("SECRET_REJECTED", codes)
        self.assertIn("PII_REJECTED", codes)
        self.assertNotIn("synthetic-secret", json.dumps(result.as_dict()))
        self.assertNotIn("person@example.invalid", json.dumps(result.as_dict()))

    def test_semantic_hash_is_deterministic_and_canary_does_not_expand(self):
        first = self.writer.run([approved_operation()], transport=SyntheticRecommendationTransport())
        second_writer = RecommendationCanaryWriter(binding=binding(), audit_store=self.audit, idempotency_store=None)
        second = second_writer.run([approved_operation()], transport=SyntheticRecommendationTransport())
        self.assertEqual(first.write_intent.idempotency_key, second.write_intent.idempotency_key)
        self.assertEqual(first.payload["semantic_hash"], second.payload["semantic_hash"])
        expanded = self.writer.run([approved_operation(operation_id="OP_CANARY_002"), approved_operation(operation_id="OP_CANARY_003")], transport=SyntheticRecommendationTransport())
        self.assertIn("BLOCKED_OPERATION_LIMIT", {item.code for item in expanded.validation.errors})

    def test_production_environment_is_hard_blocked(self):
        production = RecommendationCanaryWriter(binding=binding(environment="PRODUCTION"), audit_store=self.audit, idempotency_store=self.idempotency)
        result = production.run([approved_operation()], transport=SyntheticRecommendationTransport())
        self.assertIn("TARGET_ENVIRONMENT_BLOCKED", {item.code for item in result.validation.errors})

    def test_no_mutation_and_observation_config_are_explicit(self):
        self.assertEqual(self.writer.observation_period, "1 business day")
        result = self.writer.run([approved_operation()], transport=SyntheticRecommendationTransport())
        self.assertEqual(result.production_mutation_count, 0)
        self.assertFalse(result.payload.get("next_steps_written", False))


if __name__ == "__main__":
    unittest.main()
