"""Zero-write production-config planning for the Phase 1 canary.

This module deliberately stops before ``WriteIntent`` creation.  It loads a
non-secret external binding, validates the real target readback supplied by a
caller, projects one synthetic operation, and returns a reviewable plan.  No
Google transport, audit receipt, idempotency ledger, or ACL mutation is
available through this boundary.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .canary_writer import (
    ALLOWED_FIELDS,
    PROTECTED_FIELDS,
    TARGET_TAB,
    WRITER_ID,
    _canary_sensitive_errors,
    _eligibility,
    _hash,
    idempotency_key,
)
from .proposal_validation import ValidationError, ValidationResult
ZERO_WRITE_MODE = "ZERO_WRITE"
ZERO_WRITE_CONFIG_DRY_RUN = "ZERO_WRITE_CONFIG_DRY_RUN"
PRODUCTION_ACTIVATION = "NOT_AUTHORIZED"
LIVE_WRITE_BLOCKERS = (
    "TRUSTED_REVIEW_IDENTITY_NOT_VERIFIED",
    "PRODUCTION_CONTRACTS_NOT_APPROVED",
    "PRODUCTION_ACTIVATION_NOT_AUTHORIZED",
)
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/?#-]{0,255}$")
_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|"
    r"password|authorization|cookie|private[_-]?key|credential)",
    re.IGNORECASE,
)


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _error(code: str, field: str, message: str) -> ValidationError:
    return ValidationError(code, field, message)


def _hash_matches(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _ref(value: Any) -> bool:
    return isinstance(value, str) and _REF.fullmatch(value) is not None


def _binding_hash_payload(binding: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in binding.items() if key != "binding_semantic_hash"}


def load_durable_binding(path: str | Path) -> dict[str, Any]:
    """Load a JSON binding without ever reading a credential source."""

    binding_path = Path(path)
    try:
        value = json.loads(binding_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("BINDING_UNREADABLE") from error
    if not isinstance(value, dict):
        raise ValueError("BINDING_INVALID")
    return value


def validate_durable_binding(
    binding: Mapping[str, Any],
    *,
    expected_schema_hash: Optional[str] = None,
    expected_allowed_fields_hash: Optional[str] = None,
    expected_workbook_ref: Optional[str] = None,
    expected_audit_folder_ref: Optional[str] = None,
) -> ValidationResult:
    """Validate durable config plus metadata readback prerequisites."""

    errors: list[ValidationError] = []
    if not isinstance(binding, Mapping):
        return ValidationResult(errors=[_error("BINDING_INVALID", "$", "binding must be an object")])
    if binding.get("environment") != "PRODUCTION_CANARY":
        errors.append(_error("BINDING_ENVIRONMENT_INVALID", "environment", "production canary environment is required"))
    for field in ("drive_root_ref", "canary_folder_ref", "opportunity_folder_ref", "workbook_ref", "audit_folder_ref", "principal_ref"):
        if not _ref(binding.get(field)):
            errors.append(_error("BINDING_REF_INVALID", field, "binding reference is required"))
    if expected_workbook_ref is not None and binding.get("workbook_ref") != expected_workbook_ref:
        errors.append(_error("WORKBOOK_REF_MISMATCH", "workbook_ref", "binding workbook ref does not match the grounded target"))
    if expected_audit_folder_ref is not None and binding.get("audit_folder_ref") != expected_audit_folder_ref:
        errors.append(_error("AUDIT_REF_MISMATCH", "audit_folder_ref", "binding audit ref does not match the grounded audit target"))
    if binding.get("tab_name") != TARGET_TAB:
        errors.append(_error("TARGET_TAB_MISMATCH", "tab_name", f"target tab must be {TARGET_TAB}"))
    if binding.get("principal_type") != "authorized-user OAuth":
        errors.append(_error("PRINCIPAL_TYPE_INVALID", "principal_type", "authorized-user OAuth is required"))
    if binding.get("acl_policy") != {"domain": "shopline.com", "role": "reader", "status": "APPROVED"}:
        errors.append(_error("ACL_POLICY_INVALID", "acl_policy", "approved shopline.com reader policy is required"))
    if binding.get("acl_verified") is not True:
        errors.append(_error("ACL_NOT_VERIFIED", "acl_verified", "ACL readback must be verified"))
    if binding.get("recommendation_row_count") != 0:
        errors.append(_error("NONZERO_TARGET_ROWS", "recommendation_row_count", "zero Recommendation rows are required"))
    if binding.get("audit_binding") != "VERIFIED":
        errors.append(_error("AUDIT_BINDING_INVALID", "audit_binding", "audit binding must be verified"))
    if binding.get("secrets_persisted") is not False:
        errors.append(_error("SECRET_PERSISTENCE", "secrets_persisted", "binding must not persist secrets"))
    if binding.get("production_activation") != PRODUCTION_ACTIVATION:
        errors.append(_error("PRODUCTION_ACTIVATION_BLOCKED", "production_activation", "activation must remain unauthorized"))
    if binding.get("trusted_review_identity") != "NOT_VERIFIED":
        errors.append(_error("TRUSTED_IDENTITY_DRIFT", "trusted_review_identity", "trusted review remains unverified for this dry run"))

    fields_hash = _digest(list(ALLOWED_FIELDS))
    schema_hash = _digest({"tab_name": TARGET_TAB, "fields": list(ALLOWED_FIELDS)})
    if binding.get("allowed_fields_hash") != fields_hash or (expected_allowed_fields_hash and binding.get("allowed_fields_hash") != expected_allowed_fields_hash):
        errors.append(_error("ALLOWLIST_HASH_MISMATCH", "allowed_fields_hash", "allowlist hash does not match the canonical writer fields"))
    if binding.get("schema_hash") != schema_hash or (expected_schema_hash and binding.get("schema_hash") != expected_schema_hash):
        errors.append(_error("SCHEMA_HASH_MISMATCH", "schema_hash", "schema hash does not match the canonical target schema"))
    supplied_hash = binding.get("binding_semantic_hash")
    if not _hash_matches(supplied_hash) or _digest(_binding_hash_payload(binding)) != supplied_hash:
        errors.append(_error("BINDING_HASH_MISMATCH", "binding_semantic_hash", "durable binding semantic hash does not match"))

    secret_fields = [str(key) for key in binding if _SECRET_KEY.search(str(key))]
    if secret_fields:
        errors.append(_error("SECRET_FIELD_PRESENT", "binding", "secret-like fields cannot enter durable binding metadata"))
    return ValidationResult(errors=errors)


@dataclass(frozen=True)
class DryRunWritePlan:
    operation_id: str
    writer_id: str
    principal_ref: str
    target_binding_ref: str
    recommendation_id: str
    candidate_revision: int
    review_revision: int
    bridge_revision: int
    planned_fields: tuple[str, ...]
    payload_hash: str
    idempotency_key: str
    readback_fields: tuple[str, ...]
    audit_destination_ref: str
    audit_name_template: str
    kill_switch_authority_ref: str
    kill_switch_state: bool
    production_activation: str
    transport_mode: str = ZERO_WRITE_MODE

    def as_dict(self) -> dict[str, Any]:
        return {key: copy.deepcopy(value) for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class DryRunResult:
    state: str
    validation: ValidationResult
    plan: Optional[DryRunWritePlan]
    payload: Optional[dict[str, Any]]
    live_write_eligibility: str
    blockers: tuple[str, ...]
    attempted_mutations: tuple[str, ...] = ()

    @property
    def is_valid(self) -> bool:
        return self.state == ZERO_WRITE_CONFIG_DRY_RUN and self.validation.is_valid

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "validation": self.validation.as_dict(),
            "plan": self.plan.as_dict() if self.plan else None,
            "payload": copy.deepcopy(self.payload),
            "live_write_eligibility": self.live_write_eligibility,
            "blockers": list(self.blockers),
            "attempted_mutations": list(self.attempted_mutations),
        }


class ZeroWriteBlocked(RuntimeError):
    """Raised whenever a dry-run path attempts a mutating operation."""

    def __init__(self, operation: str):
        super().__init__("ZERO_WRITE_BLOCKED: " + operation)
        self.operation = operation


class ZeroWriteTransportGuard:
    """Transport-shaped guard that exposes no successful mutation path."""

    mode = ZERO_WRITE_MODE

    def __init__(self) -> None:
        self.attempted_operations: list[str] = []

    def _block(self, operation: str) -> None:
        self.attempted_operations.append(operation)
        raise ZeroWriteBlocked(operation)

    def write(self, *args: Any, **kwargs: Any) -> None:
        self._block("transport.write")

    def append_cells(self, *args: Any, **kwargs: Any) -> None:
        self._block("sheets.appendCells")

    def update_cells(self, *args: Any, **kwargs: Any) -> None:
        self._block("sheets.updateCells")

    def values_append(self, *args: Any, **kwargs: Any) -> None:
        self._block("sheets.values.append")

    def values_update(self, *args: Any, **kwargs: Any) -> None:
        self._block("sheets.values.update")

    def batch_update(self, *args: Any, **kwargs: Any) -> None:
        self._block("sheets.batchUpdate")

    def write_audit_receipt(self, *args: Any, **kwargs: Any) -> None:
        self._block("audit.receipt")

    def mutate_acl(self, *args: Any, **kwargs: Any) -> None:
        self._block("drive.acl")

    def mutate_drive(self, *args: Any, **kwargs: Any) -> None:
        self._block("drive.mutation")


def _project_payload(candidate: Mapping[str, Any], bridge: Mapping[str, Any], release_id: str, operation_id: str, timestamp: str) -> dict[str, Any]:
    payload = {
        "recommendation_id": bridge["recommendation_id"],
        "candidate_id": candidate["candidate_id"],
        "candidate_revision": bridge["candidate_revision"],
        "candidate_hash": bridge["candidate_hash"],
        "review_id": bridge["review_id"],
        "review_revision": bridge["review_revision"],
        "review_hash": bridge["review_hash"],
        "bridge_id": bridge["bridge_id"],
        "bridge_revision": bridge["revision"],
        "bridge_hash": bridge["content_hash"],
        "recommendation_text": bridge.get("text"),
        "action_type": bridge["candidate_action"],
        "topic_refs": copy.deepcopy(candidate.get("topic_refs", candidate.get("topic_ids", [candidate.get("topic_ref")] if candidate.get("topic_ref") else []))),
        "target_url_refs": copy.deepcopy(candidate.get("target_url_refs", [bridge.get("target_url")] if bridge.get("target_url") else [])),
        "score": copy.deepcopy(bridge["candidate_score"]),
        "confidence": bridge["candidate_confidence"],
        "evidence_refs": copy.deepcopy(bridge.get("candidate_evidence_refs", [])),
        "conflict_status": "ADJUDICATED" if bridge.get("conflicts") else "NONE",
        "governance_status": "HUMAN_APPROVED_BRIDGE_READY",
        "release_id": release_id,
        "operation_id": operation_id,
        "created_at": timestamp,
    }
    payload["semantic_hash"] = _hash(payload, exclude=("semantic_hash", "created_at"))
    return payload


def plan_zero_write(
    operations: Sequence[Mapping[str, Any]],
    *,
    binding: Mapping[str, Any],
    kill_switch: bool = False,
    release_id: str = "REL_CANARY_DRY_RUN",
    operation_timestamp: str = "2026-09-16T09:00:00+08:00",
    trusted_review_identity_verified: bool = False,
    production_contracts_approved: bool = False,
    expected_workbook_ref: Optional[str] = None,
    expected_audit_folder_ref: Optional[str] = None,
) -> DryRunResult:
    """Create a non-executable plan while keeping live eligibility blocked."""

    errors = list(validate_durable_binding(binding, expected_workbook_ref=expected_workbook_ref, expected_audit_folder_ref=expected_audit_folder_ref).errors)
    if not isinstance(operations, Sequence) or isinstance(operations, (str, bytes)):
        errors.append(_error("OPERATIONS_INVALID", "operations", "operations must be a sequence"))
        return DryRunResult("BLOCKED", ValidationResult(errors=errors), None, None, "BLOCKED_CONFIG", tuple(LIVE_WRITE_BLOCKERS))
    if len(operations) == 0:
        errors.append(_error("NO_OPERATION", "operations", "one synthetic operation is required for planning"))
    if len(operations) > 1:
        errors.append(_error("BLOCKED_OPERATION_LIMIT", "operations", "Phase 1 allows exactly one planned operation"))
    if errors:
        return DryRunResult("BLOCKED", ValidationResult(errors=errors), None, None, "BLOCKED_CONFIG", tuple(LIVE_WRITE_BLOCKERS))
    operation = operations[0]
    if not isinstance(operation, Mapping):
        errors.append(_error("OPERATIONS_INVALID", "operations[0]", "operation must be an object"))
        return DryRunResult("BLOCKED", ValidationResult(errors=errors), None, None, "BLOCKED_CONFIG", tuple(LIVE_WRITE_BLOCKERS))
    sensitive_errors = _canary_sensitive_errors(operation)
    if sensitive_errors:
        return DryRunResult("BLOCKED", ValidationResult(errors=sensitive_errors), None, None, "BLOCKED_CONFIG", tuple(LIVE_WRITE_BLOCKERS))
    synthetic_context = operation.get("trusted_review_context")
    eligibility_errors, candidate, review, bridge = _eligibility(
        operation,
        synthetic_context,
        writer_principal_ref=str(binding["principal_ref"]),
        operation_count=len(operations),
    )
    eligibility_errors = [
        error for error in eligibility_errors
        if not (error.code == "BLOCKED_TRUSTED_IDENTITY" and error.field == "trusted_review_context")
    ]
    errors.extend(eligibility_errors)
    if kill_switch:
        errors.append(_error("KILL_SWITCH_ENABLED", "kill_switch", "kill switch blocks dry-run planning"))
    if errors:
        return DryRunResult("BLOCKED", ValidationResult(errors=errors), None, None, "BLOCKED_CONFIG", tuple(LIVE_WRITE_BLOCKERS))
    operation_id = operation.get("operation_id")
    if not _ref(operation_id) or not _ref(release_id):
        errors.append(_error("REFERENCE_INVALID", "operation_id", "operation and release references are required"))
    if not isinstance(operation_timestamp, str) or not operation_timestamp:
        errors.append(_error("DATETIME_INVALID", "operation_timestamp", "operation timestamp is required"))
    if set(operation.get("payload_overrides", {})) - set(ALLOWED_FIELDS) or operation.get("protected_field_mutation"):
        errors.append(_error("PROTECTED_FIELD_MUTATION", "payload_overrides", "protected or non-allowlisted fields cannot enter a plan"))
    if errors:
        return DryRunResult("BLOCKED", ValidationResult(errors=errors), None, None, "BLOCKED_CONFIG", tuple(LIVE_WRITE_BLOCKERS))

    assert candidate is not None and bridge is not None
    payload = _project_payload(candidate, bridge, str(release_id), str(operation_id), operation_timestamp)
    unexpected = set(payload) - set(ALLOWED_FIELDS)
    if unexpected or set(PROTECTED_FIELDS).intersection(payload):
        errors.append(_error("PROJECTION_NOT_ALLOWLISTED", "payload", "projection contains a protected or unknown field"))
        return DryRunResult("BLOCKED", ValidationResult(errors=errors), None, payload, "BLOCKED_CONFIG", tuple(LIVE_WRITE_BLOCKERS))
    target_binding_ref = f"{binding['workbook_ref']}#{binding['tab_name']}"
    key = idempotency_key(
        writer_id=WRITER_ID,
        target_binding_ref=target_binding_ref,
        recommendation_id=str(bridge["recommendation_id"]),
        candidate_revision=bridge["candidate_revision"],
        review_revision=bridge["review_revision"],
        bridge_revision=bridge["revision"],
        semantic_hash=payload["semantic_hash"],
        operation_type="DRY_RUN_PUBLISH_RECOMMENDATION",
    )
    plan = DryRunWritePlan(
        operation_id=str(operation_id),
        writer_id=WRITER_ID,
        principal_ref=str(binding["principal_ref"]),
        target_binding_ref=target_binding_ref,
        recommendation_id=str(bridge["recommendation_id"]),
        candidate_revision=bridge["candidate_revision"],
        review_revision=bridge["review_revision"],
        bridge_revision=bridge["revision"],
        planned_fields=tuple(ALLOWED_FIELDS),
        payload_hash=payload["semantic_hash"],
        idempotency_key=key,
        readback_fields=(
            "recommendation_id", "candidate_revision", "candidate_hash", "review_id",
            "review_revision", "review_hash", "bridge_id", "bridge_revision",
            "bridge_hash", "semantic_hash", "target_binding_ref", "allowed_fields",
        ),
        audit_destination_ref=str(binding["audit_folder_ref"]),
        audit_name_template="operation_<operation_id>.json",
        kill_switch_authority_ref="owner://project",
        kill_switch_state=kill_switch,
        production_activation=str(binding["production_activation"]),
    )
    blockers = list(LIVE_WRITE_BLOCKERS)
    if trusted_review_identity_verified:
        blockers.remove("TRUSTED_REVIEW_IDENTITY_NOT_VERIFIED")
    if production_contracts_approved:
        blockers.remove("PRODUCTION_CONTRACTS_NOT_APPROVED")
    if binding.get("production_activation") == "AUTHORIZED":
        blockers.remove("PRODUCTION_ACTIVATION_NOT_AUTHORIZED")
    live = "READY" if not blockers else "BLOCKED_" + "_AND_".join(blockers)
    return DryRunResult(ZERO_WRITE_CONFIG_DRY_RUN, ValidationResult(errors=[]), plan, payload, live, tuple(blockers))


__all__ = [
    "ZERO_WRITE_MODE", "ZERO_WRITE_CONFIG_DRY_RUN", "PRODUCTION_ACTIVATION", "LIVE_WRITE_BLOCKERS",
    "DryRunWritePlan", "DryRunResult", "ZeroWriteBlocked", "ZeroWriteTransportGuard",
    "load_durable_binding", "validate_durable_binding", "plan_zero_write",
]
