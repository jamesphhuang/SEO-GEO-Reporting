import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from reporting.opportunity.production_hardening import (
    IdempotencyLedger,
    PROPOSAL_STATUS,
    dry_run_promotion,
    semantic_hash,
    validate_activation_proposal,
    validate_hardening_result,
    validate_release_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/opportunity_hardening/scenarios.json").read_text(encoding="utf-8"))
MAIN_SHA = "6415c9e086f6afe419076461fa486d2c457f89a6"
CREATED_AT = "2026-09-14T12:00:00+08:00"


def activation(**overrides):
    value = {
        "x-proposal-status": PROPOSAL_STATUS,
        "x-production-activation": False,
        "activation_id": "ACT_WP12_UAT",
        "revision": 1,
        "environment": "UAT",
        "release_version": "wp12.1",
        "required_wp_versions": {f"WP{i}": "READY" for i in range(1, 13)},
        "required_contract_versions": {"activation": "production_activation.v1.proposal"},
        "required_readiness_gates": {"wp1_to_wp11_integrated": True, "dry_run": True},
        "allowed_writers": ["UAT_DRY_RUN_WRITER"],
        "allowed_targets": ["UAT_RECOMMENDATIONS", "UAT_NEXT_STEPS", "UAT_WORKBOOK", "UAT_APPS_SCRIPT"],
        "allowed_schedulers": [],
        "allowed_sources": ["IMMUTABLE_EVIDENCE"],
        "approval_ref": None,
        "activation_state": "DRY_RUN",
        "rollback_state": "AVAILABLE",
        "kill_switch": False,
        "created_at": CREATED_AT,
        "production_mutation": 0,
    }
    value.update(overrides)
    value["semantic_hash"] = semantic_hash(value)
    return value


def operation(*, target="UAT_RECOMMENDATIONS", writer="UAT_DRY_RUN_WRITER", failure_mode="SUCCESS", key=None, semantic="a" * 64, artifact_type="RECOMMENDATION_BRIDGE", entity_id="CAND_WP12_A", revision=1, operation_name="WRITE_PREVIEW"):
    value = {
        "artifact_type": artifact_type,
        "entity_id": entity_id,
        "revision": revision,
        "target": target,
        "operation": operation_name,
        "writer": writer,
        "semantic_hash": semantic,
        "expected_revision": revision,
        "expected_hash": semantic,
        "freshness_state": "READY",
        "status": "READY",
        "approval_state": "APPROVED_UAT",
        "contract_state": PROPOSAL_STATUS,
        "failure_mode": failure_mode,
        "audit_required": True,
        "audit_config": {"audit_type": "OFFLINE_PLAN", "writer": "UAT_AUDIT_PLAN"},
    }
    if key is not None:
        value["idempotency_key"] = key
    return value


def run(*operations, activation_value=None, readiness=None, ledger=None, **extra):
    payload = {
        "activation": activation_value or activation(),
        "main_sha": MAIN_SHA,
        "release_id": "REL_WP12_DRY_RUN",
        "run_id": "RUN_WP12_DRY_RUN",
        "created_at": CREATED_AT,
        "readiness_gates": readiness if readiness is not None else {"wp1_to_wp11_integrated": True, "dry_run": True},
        "wp_versions": {f"WP{i}": "READY" for i in range(1, 13)},
        "contract_versions": {"activation": "production_activation.v1.proposal", "manifest": "production_release_manifest.v1.proposal"},
        "test_result_summary": {"status": "PASS", "suites": {"full_regression": {"suite": "full_regression", "passed": 311, "failed": 0, "skipped": 0, "status": "PASS", "run_identifier": "RUN_WP12_TESTS"}}},
        "operations": list(operations),
    }
    payload.update(extra)
    return dry_run_promotion(payload, ledger=ledger)


class ProductionHardeningTests(unittest.TestCase):
    def test_proposal_schemas_are_valid_and_not_activated(self):
        for name in ("production_activation.v1.proposal.json", "production_release_manifest.v1.proposal.json"):
            schema = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            self.assertEqual(schema["x-proposal-status"], PROPOSAL_STATUS)
            self.assertFalse(schema["x-production-activation"])

    def test_fixture_is_synthetic_and_covers_a_to_t(self):
        self.assertTrue(FIXTURE["metadata"]["synthetic"])
        self.assertEqual(FIXTURE["metadata"]["source"], "offline-only")
        self.assertEqual(FIXTURE["metadata"]["production_mutation"], 0)
        self.assertEqual([item["id"] for item in FIXTURE["scenarios"]], list("ABCDEFGHIJKLMNOPQRST"))

    def test_activation_proposal_is_valid_but_draft(self):
        result = validate_activation_proposal(activation())
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(activation()["x-proposal-status"], PROPOSAL_STATUS)
        self.assertFalse(activation()["x-production-activation"])

    def test_wp12_ready_does_not_activate_production(self):
        result = run(operation())
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(result.manifest["activation_status"], "DRY_RUN_VALIDATION_READY")
        self.assertFalse(result.manifest["x-production-activation"])

    def test_draft_contract_and_missing_authorization_block_production(self):
        result = run(operation(target="PRODUCTION_RECOMMENDATIONS"), activation_value=activation(environment="PRODUCTION", allowed_targets=["PRODUCTION_RECOMMENDATIONS"]))
        codes = {item.code for item in result.validation.errors}
        self.assertIn("AUTHORIZATION_REQUIRED", codes)
        self.assertIn("CONTRACT_NOT_APPROVED", codes)
        self.assertEqual(result.write_count, 0)

    def test_unknown_environment_fails_closed(self):
        result = run(operation(), activation_value=activation(environment="UNKNOWN"))
        self.assertIn("UNKNOWN_ENVIRONMENT", {item.code for item in result.validation.errors})
        self.assertEqual(result.write_count, 0)

    def test_unapproved_writer_blocks(self):
        result = run(operation(writer="UNTRUSTED_WRITER"))
        self.assertIn("WRITER_NOT_ALLOWED", {item.code for item in result.validation.errors})

    def test_unapproved_target_blocks(self):
        result = run(operation(target="UNKNOWN_TARGET"))
        self.assertIn("TARGET_NOT_ALLOWED", {item.code for item in result.validation.errors})

    def test_same_operation_retry_is_idempotent(self):
        first = operation()
        second = copy.deepcopy(first)
        result = run(first, second)
        self.assertTrue(result.manifest["planned_operations"][0]["status"] == "PLANNED")
        self.assertEqual(result.manifest["planned_operations"][1]["status"], "IDEMPOTENT_NO_OP")
        self.assertEqual(result.write_count, 0)

    def test_duplicate_key_different_hash_is_conflict(self):
        first = operation(key="IDEM_FIXED", semantic="a" * 64)
        second = operation(key="IDEM_FIXED", semantic="b" * 64)
        result = run(first, second)
        self.assertIn("IDEMPOTENCY_CONFLICT", {item.code for item in result.validation.errors})
        self.assertEqual(result.write_count, 0)

    def test_partial_failure_remains_visible(self):
        result = run(operation(failure_mode="WRITE_THEN_AUDIT_FAIL"))
        self.assertEqual(result.manifest["activation_status"], "PARTIAL")
        self.assertTrue(any(event["event_type"] == "run_partial" for event in result.events))

    def test_audit_failure_cannot_be_skipped(self):
        result = run(operation(failure_mode="WRITE_THEN_AUDIT_FAIL"))
        self.assertIn("AUDIT_WRITE_FAILED", {item.code for item in result.validation.errors})

    def test_rollback_preserves_immutable_history(self):
        result = run(operation())
        rollback = result.manifest["rollback_instructions"]
        self.assertTrue(rollback["disable_new_writes"])
        self.assertIn("never delete immutable history", rollback["history_policy"])

    def test_kill_switch_blocks_new_writes(self):
        result = run(operation(), kill_switch=True)
        self.assertIn("KILL_SWITCH_ACTIVE", {item.code for item in result.validation.errors})
        self.assertEqual(result.write_count, 0)

    def test_scheduler_is_disabled_by_default(self):
        result = run(operation())
        self.assertEqual(result.manifest["scheduler_state"], "DISABLED")
        self.assertEqual(result.manifest["activation_state"], "DRY_RUN")

    def test_scheduler_enable_attempt_is_blocked(self):
        result = run(operation(), scheduler_enabled=True)
        self.assertIn("SCHEDULER_DISABLED", {item.code for item in result.validation.errors})

    def test_source_unavailable_is_not_zero(self):
        result = run(operation(failure_mode="SOURCE_UNAVAILABLE"))
        self.assertIn("SOURCE_UNAVAILABLE", {item.code for item in result.validation.errors})
        self.assertEqual(result.write_count, 0)

    def test_stale_critical_evidence_blocks(self):
        result = run(operation(failure_mode="STALE_EVIDENCE"))
        self.assertIn("STALE_EVIDENCE", {item.code for item in result.validation.errors})

    def test_hash_mismatch_blocks(self):
        result = run(operation(failure_mode="HASH_MISMATCH"))
        self.assertIn("HASH_MISMATCH", {item.code for item in result.validation.errors})

    def test_revision_mismatch_blocks(self):
        result = run(operation(failure_mode="REVISION_MISMATCH"))
        self.assertIn("REVISION_MISMATCH", {item.code for item in result.validation.errors})

    def test_secret_like_payload_is_rejected_without_persisting_value(self):
        value = operation()
        value["api_key"] = "synthetic-secret-placeholder"
        result = run(value)
        self.assertIn("SECRET_REJECTED", {item.code for item in result.validation.errors})
        self.assertNotIn("api_key", json.dumps(result.manifest))

    def test_pii_like_payload_is_rejected_without_persisting_value(self):
        value = operation()
        value["customer_id"] = "synthetic-customer-placeholder"
        result = run(value)
        self.assertIn("PII_REJECTED", {item.code for item in result.validation.errors})
        self.assertNotIn("customer_id", json.dumps(result.manifest))

    def test_dry_run_plans_operations_but_writes_zero(self):
        result = run(operation(), operation(entity_id="CAND_WP12_B"), operation(entity_id="CAND_WP12_C"))
        self.assertEqual(len(result.manifest["planned_operations"]), 3)
        self.assertEqual(result.manifest["actual_write_count"], 0)

    def test_recommendations_are_not_written(self):
        result = run(operation(target="PRODUCTION_RECOMMENDATIONS"))
        self.assertEqual(result.write_count, 0)
        self.assertTrue(any(item.get("target") == "PRODUCTION_RECOMMENDATIONS" for item in result.manifest["blocked_operations"]))

    def test_next_steps_are_not_written(self):
        result = run(operation(target="PRODUCTION_NEXT_STEPS"))
        self.assertIn("TARGET_NOT_ALLOWED", {item.code for item in result.validation.errors})

    def test_workbook_is_not_written(self):
        result = run(operation(target="PRODUCTION_WORKBOOK"))
        self.assertEqual(result.write_count, 0)

    def test_apps_script_is_not_written(self):
        result = run(operation(target="PRODUCTION_APPS_SCRIPT"))
        self.assertEqual(result.write_count, 0)

    def test_release_manifest_hash_is_deterministic(self):
        first = run(operation()).manifest
        second = run(operation()).manifest
        self.assertEqual(first["semantic_hash"], second["semantic_hash"])
        self.assertEqual(first["planned_operations"], second["planned_operations"])

    def test_production_mutation_is_zero_and_result_is_hardened(self):
        result = run(operation())
        self.assertEqual(result.manifest["production_mutation"], 0)
        self.assertTrue(validate_release_manifest(result.manifest).is_valid, validate_release_manifest(result.manifest).as_dict())
        self.assertTrue(validate_hardening_result(result).is_valid, validate_hardening_result(result).as_dict())

    def test_observability_events_are_structured_and_non_sensitive(self):
        result = run(operation())
        self.assertTrue({"run_started", "write_planned", "run_completed"}.issubset({event["event_type"] for event in result.events}))
        encoded = json.dumps(result.events)
        self.assertNotRegex(encoded, r"(?i)bearer|api[_-]?key|customer[_-]?id|email|phone")

    def test_required_gate_false_missing_unknown_and_empty_fail_closed(self):
        for readiness in (
            {"wp1_to_wp11_integrated": False, "dry_run": True},
            {"wp1_to_wp11_integrated": True},
            {"wp1_to_wp11_integrated": True, "dry_run": True, "unexpected": True},
            {},
        ):
            result = run(operation(), readiness=readiness)
            self.assertTrue({"REQUIRED_GATE_FAILED", "REQUIRED_GATE_UNKNOWN"} & {item.code for item in result.validation.errors})
            self.assertEqual(result.write_count, 0)

    def test_activation_kill_switch_and_terminal_states_fail_closed(self):
        for overrides, code in (({"kill_switch": True}, "KILL_SWITCH_ACTIVE"), ({"activation_state": "REVOKED"}, "PRODUCTION_DISABLED"), ({"activation_state": "DISABLED"}, "PRODUCTION_DISABLED"), ({"activation_state": "NOT_AUTHORIZED"}, "PRODUCTION_DISABLED")):
            result = run(operation(), activation_value=activation(**overrides))
            self.assertIn(code, {item.code for item in result.validation.errors})

    def test_revision_and_hash_pins_are_real_fields(self):
        for revision in (0, -1, 1.0, "1", None):
            result = run(operation(revision=revision))
            self.assertIn("REVISION_MISMATCH", {item.code for item in result.validation.errors})
        value = operation()
        value["expected_hash"] = "b" * 64
        result = run(value)
        self.assertIn("HASH_MISMATCH", {item.code for item in result.validation.errors})

    def test_missing_identity_arbitrary_key_and_audit_are_blocked(self):
        value = operation()
        value.pop("entity_id")
        result = run(value)
        self.assertIn("MISSING_IDEMPOTENCY_KEY", {item.code for item in result.validation.errors})
        value = operation(key="ARBITRARY_KEY")
        result = run(value)
        self.assertIn("IDEMPOTENCY_KEY_MISMATCH", {item.code for item in result.validation.errors})
        value = operation()
        value["audit_required"] = False
        result = run(value)
        self.assertIn("AUDIT_REQUIRED", {item.code for item in result.validation.errors})

    def test_cross_run_ledger_is_idempotent_and_conflicts_on_new_hash(self):
        ledger = IdempotencyLedger()
        first = run(operation(), ledger=ledger)
        self.assertTrue(first.is_valid)
        second = run(operation(), ledger=ledger)
        self.assertTrue(second.is_valid)
        self.assertEqual(second.manifest["planned_operations"][0]["status"], "ALREADY_APPLIED")
        conflict = run(operation(semantic="b" * 64, key=first.manifest["planned_operations"][0]["idempotency_key"]), ledger=ledger)
        self.assertIn("IDEMPOTENCY_CONFLICT", {item.code for item in conflict.validation.errors})

    def test_nested_secret_and_pii_values_are_redacted_from_result(self):
        value = operation()
        value["metadata"] = {"nested": [{"api_key": "synthetic-secret-value"}, {"note": "synthetic-person@example.invalid"}, {"note": "+886 9123 4567"}]}
        result = run(value)
        encoded = json.dumps(result.as_dict())
        self.assertIn("SECRET_REJECTED", {item.code for item in result.validation.errors})
        self.assertIn("PII_REJECTED", {item.code for item in result.validation.errors})
        self.assertNotIn("synthetic-secret-value", encoded)
        self.assertNotIn("synthetic-person@example.invalid", encoded)
        self.assertNotIn("9123 4567", encoded)

    def test_manifest_contains_lineage_gates_summary_and_structured_rollback(self):
        result = run(operation())
        manifest = result.manifest
        for field in ("wp_versions", "contract_versions", "test_result_summary", "required_gates", "gate_results"):
            self.assertTrue(manifest[field])
        self.assertFalse(manifest["production_write_ready"])
        self.assertEqual(manifest["production_activation_readiness"], "NOT_AUTHORIZED")
        rollback = manifest["rollback_instructions"]
        self.assertTrue(rollback["disable_future_writes"])
        self.assertTrue(rollback["reason"])
        self.assertEqual(rollback["status"], "PLANNED")

    def test_partial_execution_receipts_are_visible(self):
        first = operation(entity_id="CAND_WP12_A")
        second = operation(entity_id="CAND_WP12_B")
        second["execution_receipt"] = {"status": "FAILED", "error_code": "SOURCE_UNAVAILABLE"}
        result = run(first, second)
        self.assertEqual(result.manifest["activation_status"], "PARTIAL")
        self.assertIn("SOURCE_UNAVAILABLE", {item.code for item in result.validation.errors})
        self.assertTrue(any(event["event_type"] == "write_failed" for event in result.events))

    def test_structured_test_summary_is_mandatory(self):
        result = run(operation(), test_result_summary={})
        self.assertIn("SCHEMA_INVALID", {item.code for item in result.validation.errors})
        self.assertTrue(result.manifest["test_result_summary"]["suites"])

    def test_failed_suite_missing_manifest_evidence_and_scheduler_state_block(self):
        failed_summary = {"status": "FAIL", "suites": {"full_regression": {"suite": "full_regression", "passed": 10, "failed": 1, "skipped": 0, "status": "FAIL", "run_identifier": "RUN_FAIL"}}}
        result = run(operation(), test_result_summary=failed_summary)
        self.assertIn("PRODUCTION_DISABLED", {item.code for item in result.validation.errors})
        result = run(operation(), scheduler_state="ENABLED")
        self.assertIn("SCHEDULER_DISABLED", {item.code for item in result.validation.errors})
        result = run(operation(), main_sha="", wp_versions={}, contract_versions={})
        self.assertIn("SCHEMA_INVALID", {item.code for item in result.validation.errors})


if __name__ == "__main__":
    unittest.main()
