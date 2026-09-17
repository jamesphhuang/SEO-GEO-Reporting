"""Offline contract-approval evidence primitives for the Phase 1 canary.

This module models approval evidence without acquiring credentials or writing to
any production system.  Every verifier is fail-closed and keeps contract
semantics approval separate from production activation authorization.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .store.serialization import canonical_json, canonical_line
from .trusted_review_identity import TrustedIdentityEvidence


CONTRACT_APPROVAL_RECEIPT_VERSION = "contract_approval_receipt.v1"
CONTRACT_APPROVAL_WAIVER_VERSION = "contract_approval_waiver.v1"
CONTRACT_REVOCATION_RECEIPT_VERSION = "contract_revocation_receipt.v1"
ROLLBACK_ACKNOWLEDGEMENT_VERSION = "rollback_acknowledgement_receipt.v1"
CONTRACT_SEMANTICS_APPROVER_ROLE = "CONTRACT_SEMANTICS_APPROVER"
PHASE1_CANARY_ENVIRONMENT = "PHASE1_CANARY_ONLY"
PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER = "PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER"
RETENTION_POLICY = "SUBJECT_TO_COMPANY_RETENTION_POLICY"
DEFAULT_UNUSED_APPROVAL_DAYS = 7
PRODUCTION_ACTIVATION = "NOT_AUTHORIZED"
PRODUCTION_CONTRACTS_APPROVED = False
LIVE_WRITE_READINESS = "BLOCKED"
PHASE1_CONTRACT_DEPENDENCIES = (
    "trusted_review_identity.v1",
    "human_review.v1",
    "recommendation_bridge.v1",
    "google_sheets_target_binding.v1",
    "recommendation_canary_writer.v1",
    "production_release_manifest.v1",
    "production_activation.v1",
)

_HEX64 = re.compile(r"^[a-f0-9]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_SENSITIVE = re.compile(r"(?:token|secret|credential|password|authorization|cookie|raw[_-]?(?:sub|subject)|email)", re.I)


class ContractApprovalError(ValueError):
    """Fail-closed input or policy error."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _hash(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(dict(payload)).encode("utf-8")).hexdigest()


def _check_ref(value: Any, code: str) -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise ContractApprovalError(code)
    return value


def _check_hash(value: Any, code: str) -> str:
    if not isinstance(value, str) or _HEX64.fullmatch(value) is None:
        raise ContractApprovalError(code)
    return value


def _check_time(value: Any, code: str) -> str:
    if not isinstance(value, str) or _ISO.fullmatch(value) is None:
        raise ContractApprovalError(code)
    try:
        if datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None:
            raise ValueError
    except ValueError as exc:
        raise ContractApprovalError(code) from exc
    return value


def _utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _reject_sensitive(value: Mapping[str, Any]) -> None:
    if any(_SENSITIVE.search(str(key)) for key in value):
        raise ContractApprovalError("SENSITIVE_FIELD_FORBIDDEN")


@dataclass(frozen=True)
class ContractInstance:
    """The exact contract revision to which a receipt applies."""

    contract_id: str
    contract_version: str
    revision: int
    semantic_fields: Mapping[str, Any]
    semantic_hash: str

    @classmethod
    def create(cls, contract_id: str, contract_version: str, revision: int,
               semantic_fields: Mapping[str, Any]) -> "ContractInstance":
        _check_ref(contract_id, "CONTRACT_ID_INVALID")
        _check_ref(contract_version, "CONTRACT_VERSION_INVALID")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ContractApprovalError("CONTRACT_REVISION_INVALID")
        if not isinstance(semantic_fields, Mapping):
            raise ContractApprovalError("CONTRACT_FIELDS_INVALID")
        _reject_sensitive(semantic_fields)
        fields = dict(semantic_fields)
        return cls(contract_id, contract_version, revision, fields, _hash(fields))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ContractInstance":
        if not isinstance(value, Mapping):
            raise ContractApprovalError("CONTRACT_INVALID")
        allowed = {"contract_id", "contract_version", "revision", "semantic_fields", "semantic_hash"}
        if set(value) - allowed:
            raise ContractApprovalError("CONTRACT_UNEXPECTED_FIELD")
        result = cls.create(value.get("contract_id"), value.get("contract_version"), value.get("revision"), value.get("semantic_fields"))
        if value.get("semantic_hash") != result.semantic_hash:
            raise ContractApprovalError("CONTRACT_HASH_MISMATCH")
        return result

    def as_dict(self) -> dict[str, Any]:
        return {"contract_id": self.contract_id, "contract_version": self.contract_version,
                "revision": self.revision, "semantic_fields": dict(self.semantic_fields),
                "semantic_hash": self.semantic_hash}


@dataclass(frozen=True)
class ContractApproverIdentityEvidence:
    """Provider-verified pseudonymous identity with an explicit contract role."""

    identity_ref: str
    provider: str
    role: str
    environment: str
    evidence_hash: str
    source_evidence_hash: str | None = None

    @classmethod
    def from_trusted_identity(cls, evidence: TrustedIdentityEvidence, *,
                              environment: str = PHASE1_CANARY_ENVIRONMENT) -> "ContractApproverIdentityEvidence":
        if not isinstance(evidence, TrustedIdentityEvidence) or not evidence.is_verified_provider_evidence():
            raise ContractApprovalError("APPROVER_EVIDENCE_NOT_VERIFIED")
        if environment != PHASE1_CANARY_ENVIRONMENT:
            raise ContractApprovalError("APPROVER_ENVIRONMENT_INVALID")
        payload = {"identity_ref": evidence.reviewer_subject_ref, "provider": evidence.provider,
                   "role": CONTRACT_SEMANTICS_APPROVER_ROLE, "environment": environment,
                   "source_evidence_hash": evidence.evidence_hash}
        return cls(payload["identity_ref"], payload["provider"], payload["role"], environment, _hash(payload), evidence.evidence_hash)

    def is_valid(self) -> bool:
        if not (bool(_HEX64.fullmatch(self.identity_ref)) and _HEX64.fullmatch(self.evidence_hash) is not None):
            return False
        if self.source_evidence_hash is None:
            return True
        if _HEX64.fullmatch(self.source_evidence_hash) is None:
            return False
        payload = {"identity_ref": self.identity_ref, "provider": self.provider,
                   "role": self.role, "environment": self.environment,
                   "source_evidence_hash": self.source_evidence_hash}
        return self.evidence_hash == _hash(payload)


@dataclass(frozen=True)
class ContractApprovalWaiver:
    waiver_id: str
    revision: int
    environment: str
    operation_limit: int
    production_inheritance: bool
    automatic_scope_expansion: bool
    broader_production_use: bool
    approver_identity_ref: str
    semantic_hash: str

    @classmethod
    def create(cls, waiver_id: str, revision: int, approver_identity_ref: str) -> "ContractApprovalWaiver":
        payload = {"waiver_id": _check_ref(waiver_id, "WAIVER_ID_INVALID"), "revision": revision,
                   "environment": PHASE1_CANARY_ENVIRONMENT, "operation_limit": 1,
                   "production_inheritance": False, "automatic_scope_expansion": False,
                   "broader_production_use": False, "approver_identity_ref": _check_hash(approver_identity_ref, "WAIVER_IDENTITY_INVALID")}
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ContractApprovalError("WAIVER_REVISION_INVALID")
        return cls(**payload, semantic_hash=_hash(payload))

    def as_dict(self) -> dict[str, Any]:
        payload = {k: getattr(self, k) for k in ("waiver_id", "revision", "environment", "operation_limit",
                   "production_inheritance", "automatic_scope_expansion", "broader_production_use", "approver_identity_ref")}
        return {**payload, "semantic_hash": self.semantic_hash}

    def is_valid(self) -> bool:
        payload = {k: getattr(self, k) for k in ("waiver_id", "revision", "environment", "operation_limit",
                   "production_inheritance", "automatic_scope_expansion", "broader_production_use", "approver_identity_ref")}
        return self.semantic_hash == _hash(payload)


@dataclass(frozen=True)
class ContractApprovalReceipt:
    receipt_id: str
    contract_id: str
    contract_version: str
    contract_revision: int
    contract_semantic_hash: str
    approved_scope: str
    environment: str
    target_binding_ref: str
    approver_identity_ref: str
    approver_role: str
    approved_at: str
    effective_at: str
    expires_at: str
    status: str
    revocation_state: str
    supersedes: str | None
    superseded_by: str | None
    operation_limit: int
    production_inheritance: bool
    automatic_scope_expansion: bool
    approval_waiver_ref: str | None
    readback_result: str
    receipt_semantic_hash: str

    @classmethod
    def create(cls, *, receipt_id: str, contract: ContractInstance, approver: ContractApproverIdentityEvidence,
               target_binding_ref: str, approved_at: str, effective_at: str, expires_at: str,
               approval_waiver_ref: str | None = None, status: str = "ACTIVE",
               readback_result: str = "NOT_PERFORMED", supersedes: str | None = None) -> "ContractApprovalReceipt":
        if not isinstance(approver, ContractApproverIdentityEvidence) or not approver.is_valid():
            raise ContractApprovalError("APPROVER_EVIDENCE_INVALID")
        base = dict(receipt_id=_check_ref(receipt_id, "RECEIPT_ID_INVALID"), contract_id=contract.contract_id,
                    contract_version=contract.contract_version, contract_revision=contract.revision,
                    contract_semantic_hash=contract.semantic_hash, approved_scope=PHASE1_CANARY_ENVIRONMENT,
                    environment=PHASE1_CANARY_ENVIRONMENT, target_binding_ref=_check_ref(target_binding_ref, "TARGET_INVALID"),
                    approver_identity_ref=approver.identity_ref, approver_role=approver.role,
                    approved_at=_check_time(approved_at, "APPROVED_AT_INVALID"), effective_at=_check_time(effective_at, "EFFECTIVE_AT_INVALID"),
                    expires_at=_check_time(expires_at, "EXPIRES_AT_INVALID"), status=status, revocation_state="ACTIVE",
                    supersedes=supersedes, superseded_by=None, operation_limit=1, production_inheritance=False,
                    automatic_scope_expansion=False, approval_waiver_ref=approval_waiver_ref, readback_result=readback_result)
        if base["status"] not in {"ACTIVE", "EXPIRED", "REVOKED", "SUPERSEDED"}:
            raise ContractApprovalError("RECEIPT_STATUS_INVALID")
        if _utc(base["expires_at"]) <= _utc(base["effective_at"]):
            raise ContractApprovalError("RECEIPT_EXPIRY_INVALID")
        if _utc(base["expires_at"]) - _utc(base["approved_at"]) > timedelta(days=DEFAULT_UNUSED_APPROVAL_DAYS):
            raise ContractApprovalError("RECEIPT_EXPIRY_TOO_LONG")
        if approval_waiver_ref is not None:
            _check_ref(approval_waiver_ref, "WAIVER_REF_INVALID")
        return cls(**base, receipt_semantic_hash=_hash(base))

    def as_dict(self) -> dict[str, Any]:
        payload = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "receipt_semantic_hash"}
        return {**payload, "receipt_semantic_hash": self.receipt_semantic_hash}

    def is_valid(self) -> bool:
        payload = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "receipt_semantic_hash"}
        return self.receipt_semantic_hash == _hash(payload)


@dataclass(frozen=True)
class ContractRevocationReceipt:
    revocation_id: str
    approval_receipt_id: str
    contract_revision: int
    contract_semantic_hash: str
    revoked_at: str
    reason: str
    revocation_semantic_hash: str

    @classmethod
    def create(cls, revocation_id: str, approval: ContractApprovalReceipt, revoked_at: str, reason: str) -> "ContractRevocationReceipt":
        payload = {"revocation_id": _check_ref(revocation_id, "REVOCATION_ID_INVALID"), "approval_receipt_id": approval.receipt_id,
                   "contract_revision": approval.contract_revision, "contract_semantic_hash": approval.contract_semantic_hash,
                   "revoked_at": _check_time(revoked_at, "REVOKED_AT_INVALID"), "reason": _check_ref(reason, "REVOCATION_REASON_INVALID")}
        return cls(**payload, revocation_semantic_hash=_hash(payload))

    def as_dict(self) -> dict[str, Any]:
        payload = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "revocation_semantic_hash"}
        return {**payload, "revocation_semantic_hash": self.revocation_semantic_hash}

    def is_valid(self) -> bool:
        payload = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "revocation_semantic_hash"}
        return self.revocation_semantic_hash == _hash(payload)


@dataclass(frozen=True)
class RollbackAcknowledgementReceipt:
    receipt_id: str
    release_id: str
    contract_id: str
    contract_revision: int
    contract_semantic_hash: str
    acknowledger_identity_ref: str
    acknowledged_at: str
    reason: str
    rollback_target: str
    semantic_hash: str

    @classmethod
    def create(cls, *, receipt_id: str, release_id: str, contract: ContractInstance,
               acknowledger_identity_ref: str, acknowledged_at: str, reason: str,
               rollback_target: str) -> "RollbackAcknowledgementReceipt":
        payload = {"receipt_id": _check_ref(receipt_id, "ROLLBACK_RECEIPT_ID_INVALID"), "release_id": _check_ref(release_id, "RELEASE_ID_INVALID"),
                   "contract_id": contract.contract_id, "contract_revision": contract.revision, "contract_semantic_hash": contract.semantic_hash,
                   "acknowledger_identity_ref": _check_hash(acknowledger_identity_ref, "ACK_IDENTITY_INVALID"),
                   "acknowledged_at": _check_time(acknowledged_at, "ACK_TIME_INVALID"), "reason": _check_ref(reason, "ACK_REASON_INVALID"),
                   "rollback_target": _check_ref(rollback_target, "ROLLBACK_TARGET_INVALID")}
        return cls(**payload, semantic_hash=_hash(payload))

    def as_dict(self) -> dict[str, Any]:
        payload = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "semantic_hash"}
        return {**payload, "semantic_hash": self.semantic_hash}

    def is_valid(self) -> bool:
        payload = {k: getattr(self, k) for k in self.__dataclass_fields__ if k != "semantic_hash"}
        return self.semantic_hash == _hash(payload)


@dataclass(frozen=True)
class ContractApprovalVerification:
    gate: str
    errors: tuple[str, ...]
    production_activation: str = PRODUCTION_ACTIVATION


class ContractApprovalVerifier:
    """Exact-match approval gate; it never grants activation authority."""

    def verify(self, contract: ContractInstance, approval: ContractApprovalReceipt,
               approver: ContractApproverIdentityEvidence, *, waiver: ContractApprovalWaiver | None,
               environment: str, target_binding_ref: str, operation_count: int,
               now: str, revocations: Iterable[ContractRevocationReceipt] = ()) -> ContractApprovalVerification:
        errors: list[str] = []
        if not isinstance(contract, ContractInstance): errors.append("CONTRACT_INVALID")
        if not isinstance(approval, ContractApprovalReceipt) or not approval.is_valid(): errors.append("APPROVAL_INVALID")
        if not isinstance(approver, ContractApproverIdentityEvidence) or not approver.is_valid(): errors.append("APPROVER_EVIDENCE_INVALID")
        if not errors:
            if (approval.contract_id, approval.contract_version, approval.contract_revision, approval.contract_semantic_hash) != (contract.contract_id, contract.contract_version, contract.revision, contract.semantic_hash): errors.append("CONTRACT_PIN_MISMATCH")
            if approver.identity_ref != approval.approver_identity_ref: errors.append("IDENTITY_MISMATCH")
            if approver.role != CONTRACT_SEMANTICS_APPROVER_ROLE or approval.approver_role != CONTRACT_SEMANTICS_APPROVER_ROLE: errors.append("ROLE_INVALID")
            if environment != PHASE1_CANARY_ENVIRONMENT or approval.environment != environment or approval.approved_scope != environment: errors.append("ENVIRONMENT_MISMATCH")
            if target_binding_ref != approval.target_binding_ref: errors.append("TARGET_MISMATCH")
            if operation_count < 1 or operation_count > approval.operation_limit or approval.operation_limit != 1: errors.append("OPERATION_LIMIT_EXCEEDED")
            try: current = _utc(now)
            except (TypeError, ValueError): errors.append("NOW_INVALID"); current = None
            if current is not None and not (_utc(approval.effective_at) <= current < _utc(approval.expires_at)): errors.append("APPROVAL_EXPIRED_OR_NOT_EFFECTIVE")
            if approval.status != "ACTIVE" or approval.revocation_state != "ACTIVE": errors.append("APPROVAL_NOT_ACTIVE")
            if approval.superseded_by is not None: errors.append("APPROVAL_SUPERSEDED")
            if any(r.is_valid() and r.approval_receipt_id == approval.receipt_id for r in revocations): errors.append("APPROVAL_REVOKED")
            if approval.approval_waiver_ref is None or waiver is None: errors.append("WAIVER_REQUIRED")
            elif not waiver.is_valid() or waiver.waiver_id != PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER or approval.approval_waiver_ref != PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER or waiver.approver_identity_ref != approver.identity_ref or waiver.environment != environment or waiver.operation_limit != 1 or waiver.production_inheritance or waiver.automatic_scope_expansion or waiver.broader_production_use: errors.append("WAIVER_INVALID")
        return ContractApprovalVerification("PASS" if not errors else "BLOCKED", tuple(errors))


class ContractApprovalReceiptStore:
    """Append-only JSONL evidence store for synthetic/UAT use."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, receipt: ContractApprovalReceipt) -> None:
        existing = list(self.records())
        if any(r.get("receipt_id") == receipt.receipt_id for r in existing):
            raise ContractApprovalError("DUPLICATE_RECEIPT_FORBIDDEN")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_line(receipt.as_dict()))

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists(): return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]


class ContractRevocationReceiptStore:
    """Append-only revocation log; the original approval is never overwritten."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, receipt: ContractRevocationReceipt) -> None:
        records = self.records()
        if any(item.get("revocation_id") == receipt.revocation_id for item in records):
            raise ContractApprovalError("DUPLICATE_REVOCATION_FORBIDDEN")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_line(receipt.as_dict()))

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists(): return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]


class RollbackAcknowledgementStore:
    """Append-only rollback acknowledgement log for UAT evidence."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, receipt: RollbackAcknowledgementReceipt) -> None:
        records = self.records()
        if any(item.get("receipt_id") == receipt.receipt_id for item in records):
            raise ContractApprovalError("DUPLICATE_ROLLBACK_ACK_FORBIDDEN")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_line(receipt.as_dict()))

    def records(self) -> list[dict[str, Any]]:
        if not self.path.exists(): return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]


def contract_semantic_hash(contract: ContractInstance) -> str:
    return contract.semantic_hash


__all__ = [
    "CONTRACT_APPROVAL_RECEIPT_VERSION", "CONTRACT_APPROVAL_WAIVER_VERSION", "CONTRACT_REVOCATION_RECEIPT_VERSION",
    "ROLLBACK_ACKNOWLEDGEMENT_VERSION", "CONTRACT_SEMANTICS_APPROVER_ROLE", "PHASE1_CANARY_ENVIRONMENT",
    "PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER", "RETENTION_POLICY", "DEFAULT_UNUSED_APPROVAL_DAYS", "PRODUCTION_ACTIVATION",
    "PRODUCTION_CONTRACTS_APPROVED", "LIVE_WRITE_READINESS", "PHASE1_CONTRACT_DEPENDENCIES",
    "ContractApprovalError", "ContractInstance", "ContractApproverIdentityEvidence", "ContractApprovalWaiver",
    "ContractApprovalReceipt", "ContractRevocationReceipt", "RollbackAcknowledgementReceipt", "ContractApprovalVerification",
    "ContractApprovalVerifier", "ContractApprovalReceiptStore", "ContractRevocationReceiptStore",
    "RollbackAcknowledgementStore", "contract_semantic_hash",
]
