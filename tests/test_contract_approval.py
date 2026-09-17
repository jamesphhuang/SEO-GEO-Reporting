"""Synthetic contract-approval evidence foundation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

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
)


NOW = "2026-09-10T10:00:00Z"
IDENTITY = "a" * 64
EVIDENCE = "b" * 64


def make_contract(**fields):
    return ContractInstance.create("human_review.v1", "proposal", 1, {"environment": "PHASE1_CANARY", "target": "uat", **fields})


def make_approver(**kwargs):
    return ContractApproverIdentityEvidence(
        kwargs.get("identity_ref", IDENTITY), kwargs.get("provider", "GOOGLE_WORKSPACE"),
        kwargs.get("role", CONTRACT_SEMANTICS_APPROVER_ROLE), kwargs.get("environment", PHASE1_CANARY_ENVIRONMENT), EVIDENCE,
    )


def make_receipt(contract=None, approver=None, **kwargs):
    return ContractApprovalReceipt.create(
        receipt_id=kwargs.get("receipt_id", "approval-1"), contract=contract or make_contract(), approver=approver or make_approver(),
        target_binding_ref=kwargs.get("target_binding_ref", "target/uat"), approved_at="2026-09-10T09:00:00Z",
        effective_at="2026-09-10T09:00:00Z", expires_at=kwargs.get("expires_at", "2026-09-16T09:00:00Z"),
        approval_waiver_ref=kwargs.get("approval_waiver_ref", PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER), supersedes=kwargs.get("supersedes"),
    )


def make_waiver(approver=IDENTITY, waiver_id=PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER):
    return ContractApprovalWaiver.create(waiver_id, 1, approver)


def verify(contract=None, approval=None, approver=None, waiver=None, **kwargs):
    c = contract or make_contract()
    receipt_approver = make_approver()
    a = approval or make_receipt(c, receipt_approver, **kwargs)
    verifier_approver = approver or receipt_approver
    return ContractApprovalVerifier().verify(c, a, verifier_approver, waiver=waiver if waiver is not None else make_waiver(),
        environment=kwargs.get("environment", PHASE1_CANARY_ENVIRONMENT), target_binding_ref=kwargs.get("target_binding_ref", "target/uat"),
        operation_count=kwargs.get("operation_count", 1), now=kwargs.get("now", NOW))


def test_valid_exact_approval_passes_and_does_not_authorize_activation():
    result = verify()
    assert result.gate == "PASS"
    assert result.production_activation == "NOT_AUTHORIZED"


def test_phase1_dependency_set_is_exact():
    assert PHASE1_CONTRACT_DEPENDENCIES == (
        "trusted_review_identity.v1", "human_review.v1", "recommendation_bridge.v1",
        "google_sheets_target_binding.v1", "recommendation_canary_writer.v1",
        "production_release_manifest.v1", "production_activation.v1",
    )


@pytest.mark.parametrize("change", ["contract_version", "contract_revision", "semantic_fields"])
def test_contract_pin_changes_require_new_approval(change):
    original = make_contract()
    changed = ContractInstance.create("human_review.v1", "changed" if change == "contract_version" else original.contract_version,
                               2 if change == "contract_revision" else original.revision,
                               {**original.semantic_fields, "changed": True} if change == "semantic_fields" else original.semantic_fields)
    assert "CONTRACT_PIN_MISMATCH" in verify(contract=changed, approval=make_receipt(original)).errors


def test_wrong_identity_is_blocked():
    assert "IDENTITY_MISMATCH" in verify(approver=make_approver(identity_ref="c" * 64)).errors


def test_wrong_role_is_blocked():
    assert "ROLE_INVALID" in verify(approver=make_approver(role="RECOMMENDATION_APPROVER")).errors


def test_wrong_environment_is_blocked():
    assert "ENVIRONMENT_MISMATCH" in verify(environment="PRODUCTION").errors


def test_wrong_target_is_blocked():
    assert "TARGET_MISMATCH" in verify(approval=make_receipt(target_binding_ref="target/uat"), target_binding_ref="target/other").errors


def test_missing_waiver_is_blocked():
    contract = make_contract()
    approval = make_receipt(contract)
    result = ContractApprovalVerifier().verify(contract, approval, make_approver(), waiver=None,
        environment=PHASE1_CANARY_ENVIRONMENT, target_binding_ref="target/uat", operation_count=1, now=NOW)
    assert "WAIVER_REQUIRED" in result.errors


def test_wrong_waiver_is_blocked():
    assert "WAIVER_INVALID" in verify(waiver=make_waiver(waiver_id="other")).errors


def test_operation_limit_is_one():
    assert "OPERATION_LIMIT_EXCEEDED" in verify(operation_count=2).errors


def test_expired_approval_is_blocked():
    assert "APPROVAL_EXPIRED_OR_NOT_EFFECTIVE" in verify(now="2026-09-17T10:00:00Z").errors


def test_revoked_approval_is_blocked():
    contract = make_contract()
    approval = make_receipt(contract)
    revocation = ContractRevocationReceipt.create("revoke-1", approval, "2026-09-11T10:00:00Z", "operator-request")
    result = ContractApprovalVerifier().verify(contract, approval, make_approver(), waiver=make_waiver(), environment=PHASE1_CANARY_ENVIRONMENT, target_binding_ref="target/uat", operation_count=1, now=NOW, revocations=[revocation])
    assert "APPROVAL_REVOKED" in result.errors


def test_superseded_approval_is_blocked():
    contract = make_contract()
    changed = ContractApprovalReceipt.create(receipt_id="approval-1", contract=contract, approver=make_approver(),
        target_binding_ref="target/uat", approved_at="2026-09-10T09:00:00Z", effective_at="2026-09-10T09:00:00Z",
        expires_at="2026-09-16T09:00:00Z", approval_waiver_ref=PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER, status="SUPERSEDED")
    assert "APPROVAL_NOT_ACTIVE" in verify(approval=changed).errors


def test_superseded_by_pin_is_blocked():
    approval = make_receipt()
    changed = ContractApprovalReceipt(**{**approval.__dict__, "superseded_by": "approval-2",
        "receipt_semantic_hash": approval.receipt_semantic_hash})
    assert "APPROVAL_INVALID" in verify(approval=changed).errors


def test_modified_contract_hash_cannot_be_reused():
    contract = make_contract()
    tampered = ContractInstance(contract.contract_id, contract.contract_version, contract.revision, contract.semantic_fields, "c" * 64)
    with pytest.raises(ContractApprovalError, match="CONTRACT_HASH_MISMATCH"):
        ContractInstance.from_mapping(tampered.as_dict())


def test_duplicate_receipt_is_blocked(tmp_path: Path):
    store = ContractApprovalReceiptStore(tmp_path / "approvals.jsonl")
    receipt = make_receipt()
    store.append(receipt)
    with pytest.raises(ContractApprovalError, match="DUPLICATE_RECEIPT_FORBIDDEN"):
        store.append(receipt)


def test_receipt_store_is_append_only(tmp_path: Path):
    store = ContractApprovalReceiptStore(tmp_path / "approvals.jsonl")
    store.append(make_receipt())
    assert len(store.records()) == 1
    assert json.loads((tmp_path / "approvals.jsonl").read_text())["receipt_id"] == "approval-1"


def test_revocation_and_rollback_logs_are_append_only(tmp_path: Path):
    approval = make_receipt()
    revocation = ContractRevocationReceipt.create("revoke-1", approval, "2026-09-11T10:00:00Z", "operator-request")
    revocations = ContractRevocationReceiptStore(tmp_path / "revocations.jsonl")
    revocations.append(revocation)
    with pytest.raises(ContractApprovalError, match="DUPLICATE_REVOCATION_FORBIDDEN"):
        revocations.append(revocation)
    rollback = RollbackAcknowledgementReceipt.create(receipt_id="rollback-1", release_id="release-1", contract=make_contract(), acknowledger_identity_ref=IDENTITY, acknowledged_at=NOW, reason="rollback", rollback_target="release-0")
    rollbacks = RollbackAcknowledgementStore(tmp_path / "rollback.jsonl")
    rollbacks.append(rollback)
    with pytest.raises(ContractApprovalError, match="DUPLICATE_ROLLBACK_ACK_FORBIDDEN"):
        rollbacks.append(rollback)


def test_semantic_hash_is_deterministic():
    assert make_contract().semantic_hash == make_contract().semantic_hash
    assert make_contract(note="a").semantic_hash != make_contract(note="b").semantic_hash


def test_activation_contract_approval_stays_not_authorized():
    result = verify(contract=ContractInstance.create("production_activation.v1", "proposal", 1, {"state": "NOT_AUTHORIZED"}))
    assert result.production_activation == "NOT_AUTHORIZED"


def test_receipt_rejects_more_than_seven_days():
    with pytest.raises(ContractApprovalError, match="RECEIPT_EXPIRY_TOO_LONG"):
        make_receipt(expires_at="2026-09-18T09:00:00Z")


def test_rollback_acknowledgement_pins_release_and_contract():
    receipt = RollbackAcknowledgementReceipt.create(receipt_id="rollback-1", release_id="release-1", contract=make_contract(), acknowledger_identity_ref=IDENTITY, acknowledged_at=NOW, reason="rollback", rollback_target="release-0")
    assert receipt.contract_semantic_hash == make_contract().semantic_hash
    assert len(receipt.semantic_hash) == 64


def test_waiver_forbids_production_inheritance():
    waiver = make_waiver()
    assert waiver.production_inheritance is False
    assert waiver.automatic_scope_expansion is False
    assert waiver.broader_production_use is False


def test_no_raw_identity_values_are_stored():
    assert "@" not in json.dumps(make_receipt().as_dict())


def test_status_is_not_an_activation_signal():
    result = verify()
    assert result.gate == "PASS"
    assert result.production_activation != "AUTHORIZED"


def test_tampered_receipt_hash_is_blocked():
    receipt = make_receipt()
    tampered = ContractApprovalReceipt(**{**receipt.__dict__, "target_binding_ref": "target/other"})
    assert "APPROVAL_INVALID" in verify(approval=tampered).errors
