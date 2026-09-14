"""Offline production-hardening gates for the Opportunity Intelligence layer.

WP12 defines the boundary around a future production promotion.  It does not
activate a writer, scheduler, source collector, workbook, Recommendations or
Next Steps.  The planner consumes immutable artifact metadata and returns a
deterministic dry-run manifest; every attempted mutation is represented as a
plan or a blocked operation and the actual write count is always zero.
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from .proposal_validation import ValidationError, ValidationResult
from .store.serialization import canonical_json


ACTIVATION_CONTRACT_VERSION = "production_activation.v1.proposal"
RELEASE_MANIFEST_CONTRACT_VERSION = "production_release_manifest.v1.proposal"
RULE_VERSION = "production-hardening-1"
PROPOSAL_STATUS = "DRAFT_NOT_APPROVED"
ENVIRONMENTS = frozenset({"LOCAL", "TEST", "UAT", "PRODUCTION"})
DRY_RUN_STATES = frozenset({"DRY_RUN", "NOT_AUTHORIZED", "BLOCKED", "REVOKED"})
PRODUCTION_MUTATION = 0

ERROR_CODES = frozenset(
    {
        "AUTHORIZATION_REQUIRED",
        "CONTRACT_NOT_APPROVED",
        "REVISION_MISMATCH",
        "HASH_MISMATCH",
        "STALE_EVIDENCE",
        "NOT_COMPARABLE",
        "WRITER_NOT_ALLOWED",
        "TARGET_NOT_ALLOWED",
        "IDEMPOTENCY_CONFLICT",
        "AUDIT_WRITE_FAILED",
        "SOURCE_UNAVAILABLE",
        "SCHEMA_INVALID",
        "PRODUCTION_DISABLED",
        "UNKNOWN_ENVIRONMENT",
        "MISSING_IDEMPOTENCY_KEY",
        "SECRET_REJECTED",
        "PII_REJECTED",
        "KILL_SWITCH_ACTIVE",
        "SCHEDULER_DISABLED",
        "CONFLICT_UNRESOLVED",
    }
)

_HASH = re.compile(r"^[a-f0-9]{64}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_SECRET_KEYS = re.compile(r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization|cookie|private[_-]?key|oauth)", re.I)
_PII_KEYS = re.compile(r"(?:email|e-mail|phone|telephone|mobile|customer[_-]?id|lead[_-]?id|full[_-]?name|raw[_-]?lead)", re.I)
_SECRET_VALUE = re.compile(r"(?:bearer\s+|sk-[A-Za-z0-9]|gh[pousr]_[A-Za-z0-9]|AIza[0-9A-Za-z_-]{20,})", re.I)


class ProductionHardeningError(ValueError):
    """Raised only for malformed local hardening inputs."""

    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


@dataclass(frozen=True)
class HardeningResult:
    """Stable dry-run result returned by :func:`dry_run_promotion`."""

    manifest: dict[str, Any]
    validation: ValidationResult
    events: tuple[dict[str, Any], ...]

    @property
    def is_valid(self) -> bool:
        return self.validation.is_valid

    @property
    def write_count(self) -> int:
        return int(self.manifest.get("actual_write_count", 0))

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest": copy.deepcopy(self.manifest),
            "validation": self.validation.as_dict(),
            "events": copy.deepcopy(list(self.events)),
        }


def _error(code: str, field: str, message: str, *, severity: str = "ERROR") -> ValidationError:
    return ValidationError(code, field, message, severity=severity)


def _hash_payload(value: Mapping[str, Any], *, excluded: Iterable[str] = ()) -> str:
    excluded_set = set(excluded)
    semantic = {key: item for key, item in value.items() if key not in excluded_set}
    return hashlib.sha256(canonical_json(semantic).encode("utf-8")).hexdigest()


def semantic_hash(value: Mapping[str, Any]) -> str:
    """Hash a release or operation while excluding its runtime hash field."""

    return _hash_payload(value, excluded=("semantic_hash", "content_hash"))


def _walk_sensitive(value: Any, path: str = "record") -> list[ValidationError]:
    errors: list[ValidationError] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEYS.search(key_text):
                errors.append(_error("SECRET_REJECTED", path, "secret-like fields cannot enter hardening artifacts"))
            if _PII_KEYS.search(key_text):
                errors.append(_error("PII_REJECTED", path, "raw PII fields cannot enter hardening artifacts"))
            errors.extend(_walk_sensitive(item, f"{path}.*"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            errors.extend(_walk_sensitive(item, f"{path}[{index}]"))
    elif isinstance(value, str) and _SECRET_VALUE.search(value):
        errors.append(_error("SECRET_REJECTED", path, "secret-like values cannot enter hardening artifacts"))
    return errors


def _schema_errors(contract_name: str, payload: Mapping[str, Any]) -> list[ValidationError]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker

        root = Path(__file__).resolve().parents[2]
        schema = __import__("json").loads((root / "contracts" / contract_name).read_text(encoding="utf-8"))
        return [
            _error(
                "SCHEMA_INVALID",
                ".".join(map(str, item.absolute_path)) or "$",
                "proposal violates its JSON schema",
            )
            for item in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload)
        ]
    except Exception as exc:  # pragma: no cover - dependency/runtime failure is itself a gate
        return [_error("SCHEMA_INVALID", "$", str(exc))]


def _base_contract_errors(value: Any) -> list[ValidationError]:
    if not isinstance(value, Mapping):
        return [_error("SCHEMA_INVALID", "$", "activation proposal must be an object")]
    errors = _schema_errors("production_activation.v1.proposal.json", value)
    errors.extend(_walk_sensitive(value))
    if value.get("x-proposal-status") != PROPOSAL_STATUS:
        errors.append(_error("CONTRACT_NOT_APPROVED", "x-proposal-status", "production activation remains proposal-only"))
    if value.get("x-production-activation") is not False:
        errors.append(_error("PRODUCTION_DISABLED", "x-production-activation", "production activation must remain false"))
    environment = str(value.get("environment", "")).upper()
    if environment not in ENVIRONMENTS:
        errors.append(_error("UNKNOWN_ENVIRONMENT", "environment", "unknown environment fails closed"))
    state = str(value.get("activation_state", ""))
    if state not in DRY_RUN_STATES:
        errors.append(_error("PRODUCTION_DISABLED", "activation_state", "only offline dry-run states are allowed"))
    if value.get("production_mutation") != 0:
        errors.append(_error("PRODUCTION_DISABLED", "production_mutation", "production mutation must be zero"))
    created_at = value.get("created_at")
    if not isinstance(created_at, str) or not _DATETIME.fullmatch(created_at):
        errors.append(_error("SCHEMA_INVALID", "created_at", "created_at must be timezone-aware ISO-8601"))
    supplied_hash = value.get("semantic_hash")
    if not isinstance(supplied_hash, str) or not _HASH.fullmatch(supplied_hash):
        errors.append(_error("HASH_MISMATCH", "semantic_hash", "semantic_hash must be SHA-256"))
    elif supplied_hash != semantic_hash(value):
        errors.append(_error("HASH_MISMATCH", "semantic_hash", "activation semantic hash does not match"))
    return errors


def validate_activation_proposal(value: Any) -> ValidationResult:
    """Validate the proposal contract and its production-disabled semantics."""

    return ValidationResult(errors=_base_contract_errors(value))


def idempotency_key(operation: Mapping[str, Any]) -> str:
    """Return the stable key for one planned operation."""

    required = ("artifact_type", "entity_id", "revision", "target", "operation", "semantic_hash")
    if any(operation.get(field) in (None, "") for field in required):
        raise ProductionHardeningError("MISSING_IDEMPOTENCY_KEY", "operation lacks an idempotency input", "operation")
    seed = {field: operation[field] for field in required}
    return "IDEM_" + _hash_payload(seed)[:32]


def _normalise_operation(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionHardeningError("SCHEMA_INVALID", "operation must be an object", f"operations[{index}]")
    operation = copy.deepcopy(dict(value))
    operation.setdefault("operation_id", f"OP_{index + 1:03d}")
    operation.setdefault("failure_mode", "SUCCESS")
    operation.setdefault("audit_required", True)
    operation.setdefault("semantic_hash", semantic_hash(operation))
    # A caller may carry a previously persisted key for readback/reconcile.
    # Otherwise derive the key from the immutable operation identity.  Keeping
    # a supplied key lets the planner detect a same-key/different-hash conflict
    # instead of silently treating it as a new operation.
    if operation.get("idempotency_key") in (None, ""):
        operation["idempotency_key"] = idempotency_key(operation)
    elif not isinstance(operation.get("idempotency_key"), str):
        raise ProductionHardeningError("MISSING_IDEMPOTENCY_KEY", "idempotency_key must be opaque text", f"operations[{index}].idempotency_key")
    return operation


def _event(event_type: str, *, run_id: str, release_id: str, timestamp: str, status: str, operation: Optional[Mapping[str, Any]] = None, error_code: Optional[str] = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "event_type": event_type,
        "run_id": run_id,
        "release_id": release_id,
        "status": status,
        "timestamp": timestamp,
        "production_mutation": 0,
    }
    if operation is not None:
        record.update({
            "operation_id": operation.get("operation_id"),
            "artifact_type": operation.get("artifact_type"),
            "target": operation.get("target"),
            "semantic_hash": operation.get("semantic_hash"),
            "idempotency_key": operation.get("idempotency_key"),
        })
    if error_code:
        record["error_code"] = error_code
    return record


def _rollback_plan() -> dict[str, Any]:
    return {
        "disable_new_writes": True,
        "kill_switch": "set activation_state=REVOKED and disable writer/scheduler",
        "history_policy": "append superseding or corrective revision; never delete immutable history",
        "readback_required": True,
    }


def build_release_manifest(value: Mapping[str, Any], *, status: str, planned_operations: list[dict[str, Any]], blocked_operations: list[dict[str, Any]], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a deterministic, proposal-only release manifest."""

    activation = value["activation"]
    manifest: dict[str, Any] = {
        "record_type": "PRODUCTION_RELEASE_MANIFEST",
        "contract_version": RELEASE_MANIFEST_CONTRACT_VERSION,
        "release_id": value.get("release_id", "REL_WP12_DRY_RUN"),
        "revision": int(value.get("revision", 1)),
        "main_sha": value.get("main_sha"),
        "wp_versions": copy.deepcopy(value.get("wp_versions", {})),
        "contract_versions": copy.deepcopy(value.get("contract_versions", {})),
        "test_result_summary": copy.deepcopy(value.get("test_result_summary", {})),
        "activation_status": status,
        "activation_state": activation.get("activation_state"),
        "approved_writers": copy.deepcopy(activation.get("allowed_writers", [])),
        "scheduler_state": "DISABLED",
        "known_policy_gaps": copy.deepcopy(value.get("known_policy_gaps", [])),
        "known_source_gaps": copy.deepcopy(value.get("known_source_gaps", [])),
        "rollback_instructions": _rollback_plan(),
        "planned_operations": copy.deepcopy(planned_operations),
        "blocked_operations": copy.deepcopy(blocked_operations),
        "observability_events": copy.deepcopy(events),
        "production_mutation": 0,
        "actual_write_count": 0,
        "created_at": value.get("created_at", activation.get("created_at")),
    }
    manifest["semantic_hash"] = semantic_hash(manifest)
    return manifest


def validate_release_manifest(value: Any) -> ValidationResult:
    if not isinstance(value, Mapping):
        return ValidationResult(errors=[_error("SCHEMA_INVALID", "$", "release manifest must be an object")])
    errors = _schema_errors("production_release_manifest.v1.proposal.json", value)
    errors.extend(_walk_sensitive(value))
    if value.get("x-proposal-status") not in (None, PROPOSAL_STATUS):
        errors.append(_error("CONTRACT_NOT_APPROVED", "x-proposal-status", "release manifest remains proposal-only"))
    if value.get("production_mutation") != 0 or value.get("actual_write_count") != 0:
        errors.append(_error("PRODUCTION_DISABLED", "production_mutation", "release manifest cannot perform writes"))
    if value.get("semantic_hash") != semantic_hash(value):
        errors.append(_error("HASH_MISMATCH", "semantic_hash", "release manifest semantic hash does not match"))
    return ValidationResult(errors=errors)


def dry_run_promotion(value: Mapping[str, Any]) -> HardeningResult:
    """Evaluate a production-style promotion without performing a write.

    The input is intentionally a plain mapping so a future collector or CI
    pipeline can provide the same immutable artifact metadata.  This function
    never opens a workbook, calls a source, starts a scheduler, or persists a
    production record.
    """

    errors: list[ValidationError] = []
    events: list[dict[str, Any]] = []
    value = copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}
    activation = value.get("activation") if isinstance(value.get("activation"), Mapping) else {}
    run_id = str(value.get("run_id", "RUN_WP12_DRY_RUN"))
    release_id = str(value.get("release_id", "REL_WP12_DRY_RUN"))
    timestamp = str(value.get("created_at", activation.get("created_at", "2026-09-14T12:00:00+08:00")))
    events.append(_event("run_started", run_id=run_id, release_id=release_id, timestamp=timestamp, status="STARTED"))
    errors.extend(_base_contract_errors(activation))
    errors.extend(_walk_sensitive(value))
    environment = str(activation.get("environment", "")).upper()
    scheduler_enabled = bool(value.get("scheduler_enabled", False))
    kill_switch = bool(value.get("kill_switch", False))
    if scheduler_enabled:
        errors.append(_error("SCHEDULER_DISABLED", "scheduler_enabled", "scheduler is disabled by default"))
    if kill_switch:
        errors.append(_error("KILL_SWITCH_ACTIVE", "kill_switch", "kill switch blocks all new writes"))
    readiness = value.get("readiness_gates", {})
    if not isinstance(readiness, Mapping):
        errors.append(_error("SCHEMA_INVALID", "readiness_gates", "readiness_gates must be an object"))
        readiness = {}
    failed_gates = sorted(str(key) for key, passed in readiness.items() if passed is not True)
    if failed_gates:
        errors.append(_error("PRODUCTION_DISABLED", "readiness_gates", "required readiness gate failed: " + ", ".join(failed_gates)))
    approval = value.get("production_authorization")
    explicit_authorization = isinstance(approval, Mapping) and approval.get("authorized") is True
    if environment == "PRODUCTION" and not explicit_authorization:
        errors.append(_error("AUTHORIZATION_REQUIRED", "production_authorization", "production activation requires separate explicit authorization"))
    if environment == "PRODUCTION" and activation.get("x-proposal-status") == PROPOSAL_STATUS:
        errors.append(_error("CONTRACT_NOT_APPROVED", "x-proposal-status", "draft activation contract blocks production"))
    if errors:
        events.append(_event("validation_failed", run_id=run_id, release_id=release_id, timestamp=timestamp, status="FAILED", error_code=errors[0].code))
    else:
        events.append(_event("validation_passed", run_id=run_id, release_id=release_id, timestamp=timestamp, status="PASS"))
    allowed_writers = set(str(item) for item in activation.get("allowed_writers", []) if isinstance(item, str))
    allowed_targets = set(str(item) for item in activation.get("allowed_targets", []) if isinstance(item, str))
    planned: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for index, raw_operation in enumerate(value.get("operations", []) or []):
        sensitive_errors = _walk_sensitive(raw_operation, f"operations[{index}]")
        if sensitive_errors:
            summary = {
                "operation_id": f"OP_{index + 1:03d}",
                "status": "BLOCKED",
                "errors": [error.as_dict() for error in sensitive_errors],
            }
            blocked.append(summary)
            errors.extend(sensitive_errors)
            events.append(_event("write_blocked", run_id=run_id, release_id=release_id, timestamp=timestamp, status="BLOCKED", error_code=sensitive_errors[0].code))
            continue
        try:
            operation = _normalise_operation(raw_operation, index)
        except ProductionHardeningError as exc:
            blocked.append({"operation_id": f"OP_{index + 1:03d}", "status": "BLOCKED", "error_code": exc.code, "reason": str(exc)})
            errors.append(_error(exc.code, exc.field, str(exc)))
            continue
        operation_errors: list[ValidationError] = []
        if operation.get("writer") not in allowed_writers:
            operation_errors.append(_error("WRITER_NOT_ALLOWED", "writer", "writer is not on the activation allowlist"))
        if operation.get("target") not in allowed_targets:
            operation_errors.append(_error("TARGET_NOT_ALLOWED", "target", "target is not on the activation allowlist"))
        if operation.get("target", "").upper().startswith("PRODUCTION"):
            operation_errors.append(_error("PRODUCTION_DISABLED", "target", "production targets are disabled in WP12"))
        if operation.get("failure_mode") in {"SOURCE_TIMEOUT", "SOURCE_UNAVAILABLE"}:
            operation_errors.append(_error("SOURCE_UNAVAILABLE", "failure_mode", "source failure cannot be treated as success"))
        if operation.get("failure_mode") == "STALE_EVIDENCE":
            operation_errors.append(_error("STALE_EVIDENCE", "failure_mode", "stale critical evidence blocks a write"))
        if operation.get("failure_mode") == "HASH_MISMATCH":
            operation_errors.append(_error("HASH_MISMATCH", "failure_mode", "hash mismatch blocks a write"))
        if operation.get("failure_mode") == "REVISION_MISMATCH":
            operation_errors.append(_error("REVISION_MISMATCH", "failure_mode", "revision mismatch blocks a write"))
        if operation.get("failure_mode") == "UNRESOLVED_CONFLICT":
            operation_errors.append(_error("CONFLICT_UNRESOLVED", "failure_mode", "unresolved conflict blocks a write"))
        key = operation["idempotency_key"]
        previous_hash = seen.get(key)
        if previous_hash is not None and previous_hash != operation["semantic_hash"]:
            operation_errors.append(_error("IDEMPOTENCY_CONFLICT", "idempotency_key", "same key has a different semantic hash"))
        elif previous_hash is not None:
            operation["status"] = "IDEMPOTENT_NO_OP"
        else:
            seen[key] = operation["semantic_hash"]
        if operation_errors:
            operation["status"] = "BLOCKED"
            operation["errors"] = [error.as_dict() for error in operation_errors]
            blocked.append(operation)
            for error in operation_errors:
                errors.append(error)
            events.append(_event("write_blocked", run_id=run_id, release_id=release_id, timestamp=timestamp, status="BLOCKED", operation=operation, error_code=operation_errors[0].code))
        else:
            operation.setdefault("status", "PLANNED")
            planned.append(operation)
            events.append(_event("write_planned", run_id=run_id, release_id=release_id, timestamp=timestamp, status=operation["status"], operation=operation))
            if operation.get("failure_mode") == "WRITE_THEN_AUDIT_FAIL":
                events.append(_event("write_succeeded", run_id=run_id, release_id=release_id, timestamp=timestamp, status="SIMULATED", operation=operation))
                events.append(_event("write_failed", run_id=run_id, release_id=release_id, timestamp=timestamp, status="FAILED", operation=operation, error_code="AUDIT_WRITE_FAILED"))
            elif operation.get("failure_mode") == "WRITE_FAIL":
                events.append(_event("write_failed", run_id=run_id, release_id=release_id, timestamp=timestamp, status="FAILED", operation=operation, error_code="PRODUCTION_DISABLED"))
    failure_modes = {str(item.get("failure_mode")) for item in value.get("operations", []) if isinstance(item, Mapping)}
    if "WRITE_THEN_AUDIT_FAIL" in failure_modes:
        errors.append(_error("AUDIT_WRITE_FAILED", "operations", "audit failure leaves the run partial"))
    if "WRITE_FAIL" in failure_modes:
        errors.append(_error("PRODUCTION_DISABLED", "operations", "write failure is retryable and not complete"))
    if "WRITE_THEN_AUDIT_FAIL" in failure_modes:
        status = "PARTIAL"
    elif "WRITE_FAIL" in failure_modes:
        status = "FAILED"
    elif errors and not planned:
        status = "BLOCKED"
    elif errors:
        status = "DRY_RUN_BLOCKED"
    else:
        status = "DRY_RUN_READY"
    events.append(_event("run_partial" if status == "PARTIAL" else "run_completed", run_id=run_id, release_id=release_id, timestamp=timestamp, status=status))
    manifest = build_release_manifest(value, status=status, planned_operations=planned, blocked_operations=blocked, events=events)
    # Proposal metadata is kept outside the immutable manifest body so hashes
    # stay stable while the schema remains explicit about activation state.
    manifest["x-proposal-status"] = PROPOSAL_STATUS
    manifest["x-production-activation"] = False
    manifest["semantic_hash"] = semantic_hash(manifest)
    result = ValidationResult(errors=errors)
    manifest_validation = validate_release_manifest(manifest)
    if not manifest_validation.is_valid:
        result = ValidationResult(errors=[*errors, *manifest_validation.errors])
    return HardeningResult(manifest=manifest, validation=result, events=tuple(events))


def validate_hardening_result(result: HardeningResult) -> ValidationResult:
    """Validate a result without allowing it to become a production activation."""

    errors = list(result.validation.errors)
    errors.extend(_walk_sensitive(result.manifest))
    if result.write_count != 0 or result.manifest.get("production_mutation") != 0:
        errors.append(_error("PRODUCTION_DISABLED", "actual_write_count", "hardening result must have zero writes"))
    if result.manifest.get("scheduler_state") != "DISABLED":
        errors.append(_error("SCHEDULER_DISABLED", "scheduler_state", "scheduler must remain disabled"))
    return ValidationResult(errors=errors)


__all__ = [
    "ACTIVATION_CONTRACT_VERSION",
    "RELEASE_MANIFEST_CONTRACT_VERSION",
    "ERROR_CODES",
    "HardeningResult",
    "ProductionHardeningError",
    "build_release_manifest",
    "dry_run_promotion",
    "idempotency_key",
    "semantic_hash",
    "validate_activation_proposal",
    "validate_hardening_result",
    "validate_release_manifest",
]
