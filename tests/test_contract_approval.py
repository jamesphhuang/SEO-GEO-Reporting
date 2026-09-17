"""Synthetic contract-approval evidence foundation tests."""

from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from reporting.opportunity.contract_approval import (
    CONTRACT_SEMANTICS_APPROVER_ROLE,
    PHASE1_CANARY_ENVIRONMENT,
    ContractApprovalError,
    ContractApprovalReceipt,
    ContractApprovalReceiptStore,
    ContractApprovalVerifier,
    ContractApproverIdentityEvidence,
    ContractInstance,
    ContractRevocationReceipt,
    ContractApprovalWaiver,
    RollbackAcknowledgementReceipt,
    ContractRevocationReceiptStore,
    RollbackAcknowledgementStore,
    PHASE1_CONTRACT_DEPENDENCIES,
    PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER,
    approval_semantic_fingerprint,
)
from reporting.opportunity.store.serialization import canonical_json
from reporting.opportunity.trusted_review_identity import (
    TrustedIdentityEvidence,
    TrustedReviewBinding,
    VerifiedProviderIdentity,
    reviewer_subject_ref,
)


NOW = "2026-09-10T10:00:00Z"
IDENTITY = "a" * 64
EVIDENCE = "b" * 64
WRITER = "principal://synthetic-writer"


def make_binding_and_evidence():
    subject_ref = reviewer_subject_ref("synthetic-contract-approver")
    payload = {
        "binding_version": "trusted-review-identity-binding.v1", "provider": "GOOGLE_WORKSPACE",
        "reviewer_subject_ref": subject_ref, "workspace_domain": "shopline.com",
        "role": "RECOMMENDATION_APPROVER", "scope": "PHASE1_CANARY", "status": "ACTIVE",
        "binding_revision": 1, "provider_verification_method": "GOOGLE_OIDC_ID_TOKEN_V1",
        "same_person_writer_reviewer": False, "separation_of_duties_waiver": None,
        "production_inheritance": False, "automatic_scope_expansion": False,
        "verified_at": "2026-09-10T08:00:00Z",
    }
    binding_payload = {**payload, "semantic_hash": hashlib.sha256(canonical_json(payload).encode()).hexdigest()}
    binding = TrustedReviewBinding.from_mapping(binding_payload)
    provider = VerifiedProviderIdentity.from_verified_google_claims(
        {"sub": "synthetic-contract-approver", "hd": "shopline.com"}, verified_at="2026-09-10T08:00:00Z"
    )
    evidence = TrustedIdentityEvidence.from_verified_provider_output(provider, binding)
    return binding, evidence


def make_contract(**fields):
    return ContractInstance.create("human_review.v1", "proposal", 1, {"environment": "PHASE1_CANARY", "target": "uat", **fields})


def make_approver(**kwargs):
    binding, evidence = make_binding_and_evidence()
    return ContractApproverIdentityEvidence.from_trusted_identity(evidence, binding)


def make_receipt(contract=None, approver=None, **kwargs):
    return ContractApprovalReceipt.create(
        receipt_id=kwargs.get("receipt_id", "approval-1"), contract=contract or make_contract(), approver=approver or make_approver(),
        target_binding_ref=kwargs.get("target_binding_ref", "target/uat"), approved_at="2026-09-10T09:00:00Z",
        effective_at="2026-09-10T09:00:00Z", expires_at=kwargs.get("expires_at", "2026-09-16T09:00:00Z"),
        approval_waiver_ref=kwargs.get("approval_waiver_ref", PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER), supersedes=kwargs.get("supersedes"),
    )


def make_waiver(approver=None, waiver_id=PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER):
    return ContractApprovalWaiver.create(waiver_id, 1, approver or make_approver().identity_ref)


def verify(contract=None, approval=None, approver=None, waiver=None, **kwargs):
    c = contract or make_contract()
    receipt_approver = make_approver()
    a = approval or make_receipt(c, receipt_approver, **kwargs)
    verifier_approver = approver or receipt_approver
    return ContractApprovalVerifier().verify(c, a, verifier_approver, waiver=waiver if waiver is not None else make_waiver(),
        environment=kwargs.get("environment", PHASE1_CANARY_ENVIRONMENT), target_binding_ref=kwargs.get("target_binding_ref", "target/uat"),
        operation_count=kwargs.get("operation_count", 1), now=kwargs.get("now", NOW),
        trusted_binding=make_binding_and_evidence()[0], writer_principal_ref=WRITER)


class ContractApprovalTests(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tempdir.name)

    def tearDown(self):
        self._tempdir.cleanup()

    def test_valid_exact_approval_passes_and_does_not_authorize_activation(self):
        result = verify()
        assert result.gate == "PASS"
        assert result.production_activation == "NOT_AUTHORIZED"


    def test_phase1_dependency_set_is_exact(self):
        assert PHASE1_CONTRACT_DEPENDENCIES == (
            "trusted_review_identity.v1", "human_review.v1", "recommendation_bridge.v1",
            "google_sheets_target_binding.v1", "recommendation_canary_writer.v1",
            "production_release_manifest.v1", "production_activation.v1",
        )


    def _assert_contract_pin_change(self, change):
        original = make_contract()
        changed = ContractInstance.create("human_review.v1", "changed" if change == "contract_version" else original.contract_version,
                                   2 if change == "contract_revision" else original.revision,
                                   {**original.semantic_fields, "changed": True} if change == "semantic_fields" else original.semantic_fields)
        self.assertIn("CONTRACT_PIN_MISMATCH", verify(contract=changed, approval=make_receipt(original)).errors)

    def test_contract_version_pin_changes_require_new_approval(self):
        self._assert_contract_pin_change("contract_version")

    def test_contract_revision_pin_changes_require_new_approval(self):
        self._assert_contract_pin_change("contract_revision")

    def test_contract_semantic_fields_changes_require_new_approval(self):
        self._assert_contract_pin_change("semantic_fields")


    def test_wrong_identity_is_blocked(self):
        forged = ContractApproverIdentityEvidence("c" * 64, "GOOGLE_WORKSPACE", CONTRACT_SEMANTICS_APPROVER_ROLE, PHASE1_CANARY_ENVIRONMENT, EVIDENCE)
        result = verify(approver=forged)
        assert "APPROVER_EVIDENCE_INVALID" in result.errors


    def test_wrong_role_is_blocked(self):
        forged = ContractApproverIdentityEvidence(IDENTITY, "GOOGLE_WORKSPACE", "RECOMMENDATION_APPROVER", PHASE1_CANARY_ENVIRONMENT, EVIDENCE)
        result = verify(approver=forged)
        assert "APPROVER_EVIDENCE_INVALID" in result.errors


    def test_wrong_environment_is_blocked(self):
        assert "ENVIRONMENT_MISMATCH" in verify(environment="PRODUCTION").errors


    def test_wrong_target_is_blocked(self):
        assert "TARGET_MISMATCH" in verify(approval=make_receipt(target_binding_ref="target/uat"), target_binding_ref="target/other").errors


    def test_missing_waiver_is_blocked(self):
        contract = make_contract()
        approval = make_receipt(contract)
        result = ContractApprovalVerifier().verify(contract, approval, make_approver(), waiver=None,
            environment=PHASE1_CANARY_ENVIRONMENT, target_binding_ref="target/uat", operation_count=1, now=NOW)
        assert "WAIVER_REQUIRED" in result.errors


    def test_wrong_waiver_is_blocked(self):
        assert "WAIVER_INVALID" in verify(waiver=make_waiver(waiver_id="other")).errors


    def test_operation_limit_is_one(self):
        assert "OPERATION_LIMIT_EXCEEDED" in verify(operation_count=2).errors


    def test_expired_approval_is_blocked(self):
        assert "APPROVAL_EXPIRED_OR_NOT_EFFECTIVE" in verify(now="2026-09-17T10:00:00Z").errors


    def test_revoked_approval_is_blocked(self):
        contract = make_contract()
        approval = make_receipt(contract)
        revocation = ContractRevocationReceipt.create("revoke-1", approval, "2026-09-11T10:00:00Z", "operator-request")
        result = ContractApprovalVerifier().verify(contract, approval, make_approver(), waiver=make_waiver(), environment=PHASE1_CANARY_ENVIRONMENT, target_binding_ref="target/uat", operation_count=1, now=NOW, revocations=[revocation])
        assert "APPROVAL_REVOKED" in result.errors


    def test_superseded_approval_is_blocked(self):
        contract = make_contract()
        changed = ContractApprovalReceipt.create(receipt_id="approval-1", contract=contract, approver=make_approver(),
            target_binding_ref="target/uat", approved_at="2026-09-10T09:00:00Z", effective_at="2026-09-10T09:00:00Z",
            expires_at="2026-09-16T09:00:00Z", approval_waiver_ref=PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER, status="SUPERSEDED")
        assert "APPROVAL_NOT_ACTIVE" in verify(approval=changed).errors


    def test_superseded_by_pin_is_blocked(self):
        approval = make_receipt()
        changed = ContractApprovalReceipt(**{**approval.__dict__, "superseded_by": "approval-2",
            "receipt_semantic_hash": approval.receipt_semantic_hash})
        assert "APPROVAL_INVALID" in verify(approval=changed).errors


    def test_modified_contract_hash_cannot_be_reused(self):
        contract = make_contract()
        tampered = ContractInstance(contract.contract_id, contract.contract_version, contract.revision, contract.semantic_fields, "c" * 64)
        with self.assertRaisesRegex(ContractApprovalError, expected_regex="CONTRACT_HASH_MISMATCH"):
            ContractInstance.from_mapping(tampered.as_dict())


    def test_duplicate_receipt_is_blocked(self):
        store = ContractApprovalReceiptStore(self.tmp_path / "approvals.jsonl")
        receipt = make_receipt()
        store.append(receipt)
        with self.assertRaisesRegex(ContractApprovalError, expected_regex="DUPLICATE_RECEIPT_FORBIDDEN"):
            store.append(receipt)


    def test_receipt_store_is_append_only(self):
        store = ContractApprovalReceiptStore(self.tmp_path / "approvals.jsonl")
        store.append(make_receipt())
        assert len(store.records()) == 1
        assert json.loads((self.tmp_path / "approvals.jsonl").read_text())["receipt_id"] == "approval-1"


    def test_different_receipt_ids_same_semantics_are_blocked(self):
        store = ContractApprovalReceiptStore(self.tmp_path / "approvals.jsonl")
        store.append(make_receipt(receipt_id="approval-1"))
        with self.assertRaisesRegex(ContractApprovalError, expected_regex="SEMANTIC_COLLISION_FORBIDDEN"):
            store.append(make_receipt(receipt_id="approval-2"))


    def test_different_semantics_are_not_a_collision(self):
        store = ContractApprovalReceiptStore(self.tmp_path / "approvals.jsonl")
        store.append(make_receipt(receipt_id="approval-1", target_binding_ref="target/uat"))
        store.append(make_receipt(receipt_id="approval-2", target_binding_ref="target/uat-2"))
        assert len(store.records()) == 2


    def test_fingerprint_ignores_storage_identity_and_lifecycle_metadata(self):
        receipt = make_receipt()
        first = approval_semantic_fingerprint(receipt.as_dict())
        changed = {**receipt.as_dict(), "receipt_id": "other", "status": "SUPERSEDED", "revocation_state": "REVOKED"}
        assert first == approval_semantic_fingerprint(changed)


    def test_revocation_and_rollback_logs_are_append_only(self):
        approval = make_receipt()
        revocation = ContractRevocationReceipt.create("revoke-1", approval, "2026-09-11T10:00:00Z", "operator-request")
        revocations = ContractRevocationReceiptStore(self.tmp_path / "revocations.jsonl")
        revocations.append(revocation)
        with self.assertRaisesRegex(ContractApprovalError, expected_regex="DUPLICATE_REVOCATION_FORBIDDEN"):
            revocations.append(revocation)
        rollback = RollbackAcknowledgementReceipt.create(receipt_id="rollback-1", release_id="release-1", contract=make_contract(), acknowledger_identity_ref=IDENTITY, acknowledged_at=NOW, reason="rollback", rollback_target="release-0")
        rollbacks = RollbackAcknowledgementStore(self.tmp_path / "rollback.jsonl")
        rollbacks.append(rollback)
        with self.assertRaisesRegex(ContractApprovalError, expected_regex="DUPLICATE_ROLLBACK_ACK_FORBIDDEN"):
            rollbacks.append(rollback)


    def test_revocation_and_rollback_semantic_collisions_are_blocked(self):
        approval = make_receipt()
        revocations = ContractRevocationReceiptStore(self.tmp_path / "revocations.jsonl")
        revocations.append(ContractRevocationReceipt.create("revoke-1", approval, "2026-09-11T10:00:00Z", "operator-request"))
        with self.assertRaisesRegex(ContractApprovalError, expected_regex="REVOCATION_SEMANTIC_COLLISION_FORBIDDEN"):
            revocations.append(ContractRevocationReceipt.create("revoke-2", approval, "2026-09-11T10:00:00Z", "operator-request"))
        rollbacks = RollbackAcknowledgementStore(self.tmp_path / "rollback.jsonl")
        first = RollbackAcknowledgementReceipt.create(receipt_id="rollback-1", release_id="release-1", contract=make_contract(), acknowledger_identity_ref=IDENTITY, acknowledged_at=NOW, reason="rollback", rollback_target="release-0")
        rollbacks.append(first)
        second = RollbackAcknowledgementReceipt.create(receipt_id="rollback-2", release_id="release-1", contract=make_contract(), acknowledger_identity_ref=IDENTITY, acknowledged_at=NOW, reason="rollback", rollback_target="release-0")
        with self.assertRaisesRegex(ContractApprovalError, expected_regex="ROLLBACK_SEMANTIC_COLLISION_FORBIDDEN"):
            rollbacks.append(second)


    def test_semantic_hash_is_deterministic(self):
        assert make_contract().semantic_hash == make_contract().semantic_hash
        assert make_contract(note="a").semantic_hash != make_contract(note="b").semantic_hash


    def test_activation_contract_approval_stays_not_authorized(self):
        result = verify(contract=ContractInstance.create("production_activation.v1", "proposal", 1, {"state": "NOT_AUTHORIZED"}))
        assert result.production_activation == "NOT_AUTHORIZED"


    def test_receipt_rejects_more_than_seven_days(self):
        with self.assertRaisesRegex(ContractApprovalError, expected_regex="RECEIPT_EXPIRY_TOO_LONG"):
            make_receipt(expires_at="2026-09-18T09:00:00Z")


    def test_rollback_acknowledgement_pins_release_and_contract(self):
        receipt = RollbackAcknowledgementReceipt.create(receipt_id="rollback-1", release_id="release-1", contract=make_contract(), acknowledger_identity_ref=IDENTITY, acknowledged_at=NOW, reason="rollback", rollback_target="release-0")
        assert receipt.contract_semantic_hash == make_contract().semantic_hash
        assert len(receipt.semantic_hash) == 64


    def test_waiver_forbids_production_inheritance(self):
        waiver = make_waiver()
        assert waiver.production_inheritance is False
        assert waiver.automatic_scope_expansion is False
        assert waiver.broader_production_use is False


    def test_no_raw_identity_values_are_stored(self):
        assert "@" not in json.dumps(make_receipt().as_dict())


    def test_status_is_not_an_activation_signal(self):
        result = verify()
        assert result.gate == "PASS"
        assert result.production_activation != "AUTHORIZED"


    def test_tampered_receipt_hash_is_blocked(self):
        receipt = make_receipt()
        tampered = ContractApprovalReceipt(**{**receipt.__dict__, "target_binding_ref": "target/other"})
        assert "APPROVAL_INVALID" in verify(approval=tampered).errors


    def test_directly_constructed_correct_looking_identity_is_blocked(self):
        forged = ContractApproverIdentityEvidence(
            make_approver().identity_ref, "GOOGLE_WORKSPACE", CONTRACT_SEMANTICS_APPROVER_ROLE,
            PHASE1_CANARY_ENVIRONMENT, EVIDENCE,
        )
        result = verify(approver=forged)
        assert "APPROVER_EVIDENCE_INVALID" in result.errors
