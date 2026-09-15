"""Offline production-hardening gates for the Opportunity Intelligence layer.

WP12 is deliberately a proposal-only boundary. This module validates inputs
and produces a deterministic dry-run manifest; it never opens a production
writer, starts a scheduler, calls a live source, or persists a production
record.
"""

from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from .proposal_validation import ValidationError, ValidationResult
from .store.serialization import canonical_json


ACTIVATION_CONTRACT_VERSION = "production_activation.v1.proposal"
RELEASE_MANIFEST_CONTRACT_VERSION = "production_release_manifest.v1.proposal"
RULE_VERSION = "production-hardening-1"
PROPOSAL_STATUS = "DRAFT_NOT_APPROVED"
ENVIRONMENTS = frozenset({"LOCAL", "TEST", "UAT", "PRODUCTION"})
DRY_RUN_STATES = frozenset({"DRY_RUN", "NOT_AUTHORIZED", "BLOCKED", "REVOKED", "DISABLED"})
PRODUCTION_MUTATION = 0

ERROR_CODES = frozenset(
    {
        "AUTHORIZATION_REQUIRED", "CONTRACT_NOT_APPROVED", "REVISION_MISMATCH",
        "HASH_MISMATCH", "STALE_EVIDENCE", "NOT_COMPARABLE", "WRITER_NOT_ALLOWED",
        "TARGET_NOT_ALLOWED", "IDEMPOTENCY_CONFLICT", "IDEMPOTENCY_KEY_MISMATCH",
        "AUDIT_REQUIRED", "AUDIT_WRITE_FAILED", "SOURCE_UNAVAILABLE", "SCHEMA_INVALID",
        "PRODUCTION_DISABLED", "UNKNOWN_ENVIRONMENT", "MISSING_IDEMPOTENCY_KEY",
        "SECRET_REJECTED", "PII_REJECTED", "KILL_SWITCH_ACTIVE", "SCHEDULER_DISABLED",
        "CONFLICT_UNRESOLVED", "REQUIRED_GATE_FAILED", "REQUIRED_GATE_UNKNOWN",
    }
)

_HASH = re.compile(r"^[a-f0-9]{64}$")
_SHA40 = re.compile(r"^[a-f0-9]{40}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_SECRET_KEYS = re.compile(r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization|cookie|private[_-]?key|oauth|(?:^|[_-])token(?:$|[_-])|(?:^|[_-])secret(?:$|[_-]))", re.I)
_PII_KEYS = re.compile(r"(?:email|e-mail|phone|telephone|mobile|customer[_-]?id|lead[_-]?id|full[_-]?name|raw[_-]?lead|(?:^|[_-])name$)", re.I)
_SECRET_VALUE = re.compile(r"(?:bearer\s+|sk-[A-Za-z0-9]|gh[pousr]_[A-Za-z0-9]|AIza[0-9A-Za-z_-]{20,})", re.I)
_EMAIL_VALUE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_VALUE = re.compile(r"(?<!\d)(?:\+?\d[\d\s().-]{7,}\d)(?!\d)")


class ProductionHardeningError(ValueError):
    """Raised only for malformed local hardening inputs."""

    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


@dataclass(frozen=True)
class HardeningResult:
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


class IdempotencyLedger:
    """Append-only offline ledger for repeated dry-run plans.

    It stores deterministic fingerprints only and cannot be used as a
    production write or distributed lock service.
    """

    def __init__(self, records: Optional[Mapping[str, str]] = None) -> None:
        self._records: dict[str, str] = dict(records or {})

    def reconcile(self, operation: Mapping[str, Any]) -> str:
        key = str(operation["idempotency_key"])
        fingerprint = str(operation["semantic_hash"])
        previous = self._records.get(key)
        if previous is None:
            return "NEW"
        if previous == fingerprint:
            return "ALREADY_APPLIED"
        return "IDEMPOTENCY_CONFLICT"

    def record_plan(self, operation: Mapping[str, Any]) -> None:
        self._records.setdefault(str(operation["idempotency_key"]), str(operation["semantic_hash"]))

    def snapshot(self) -> dict[str, str]:
        return dict(self._records)


def _error(code: str, field: str, message: str, *, severity: str = "ERROR") -> ValidationError:
    return ValidationError(code, field, message, severity=severity)


def _hash_payload(value: Mapping[str, Any], *, excluded: Iterable[str] = ()) -> str:
    excluded_set = set(excluded)
    semantic = {key: item for key, item in value.items() if key not in excluded_set}
    return hashlib.sha256(canonical_json(semantic).encode("utf-8")).hexdigest()


def semantic_hash(value: Mapping[str, Any]) -> str:
    """Hash a release or operation while excluding runtime hash fields."""

    return _hash_payload(value, excluded=("semantic_hash", "content_hash"))


def _valid_revision(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and _HASH.fullmatch(value) is not None


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
    elif isinstance(value, str):
        if _SECRET_VALUE.search(value):
            errors.append(_error("SECRET_REJECTED", path, "secret-like values cannot enter hardening artifacts"))
        if not _DATETIME.fullmatch(value) and not _SHA40.fullmatch(value) and not _HASH.fullmatch(value) and (_EMAIL_VALUE.search(value) or _PHONE_VALUE.search(value)):
            errors.append(_error("PII_REJECTED", path, "raw PII values cannot enter hardening artifacts"))
    return errors


def _schema_errors(contract_name: str, payload: Mapping[str, Any]) -> list[ValidationError]:
    try:
        from jsonschema import Draft202012Validator, FormatChecker

        root = Path(__file__).resolve().parents[2]
        schema = __import__("json").loads((root / "contracts" / contract_name).read_text(encoding="utf-8"))
        errors: list[ValidationError] = []
        for item in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload):
            parts = []
            for part in item.absolute_path:
                text = str(part)
                parts.append("[redacted]" if _SECRET_KEYS.search(text) or _PII_KEYS.search(text) else text)
            errors.append(_error("SCHEMA_INVALID", ".".join(parts) or "$", "proposal violates its JSON schema"))
        return errors
    except Exception as exc:  # pragma: no cover
        return [_error("SCHEMA_INVALID", "$", str(exc))]


def _gate_errors(required: Any, actual: Any, *, field: str = "readiness_gates") -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(required, Mapping) or not required:
        errors.append(_error("REQUIRED_GATE_FAILED", field, "required readiness gates must be a non-empty object"))
        return errors
    if any(not isinstance(key, str) or not key.strip() or not isinstance(passed, bool) for key, passed in required.items()):
        errors.append(_error("REQUIRED_GATE_FAILED", field, "required readiness gates must map names to booleans"))
    for key, passed in required.items():
        if passed is not True:
            errors.append(_error("REQUIRED_GATE_FAILED", f"{field}.{key}", "required gate is not satisfied"))
    if actual is not None:
        if not isinstance(actual, Mapping) or not actual:
            errors.append(_error("REQUIRED_GATE_FAILED", field, "runtime readiness gates must be a non-empty object"))
        else:
            unknown = sorted(str(key) for key in actual if key not in required)
            missing = sorted(str(key) for key in required if key not in actual)
            if unknown:
                errors.append(_error("REQUIRED_GATE_UNKNOWN", field, "runtime readiness contains an unknown gate"))
            if missing:
                errors.append(_error("REQUIRED_GATE_FAILED", field, "runtime readiness is missing a required gate"))
            for key in required:
                if key in actual and actual[key] is not True:
                    errors.append(_error("REQUIRED_GATE_FAILED", f"{field}.{key}", "runtime gate is not satisfied"))
                if key in actual and not isinstance(actual[key], bool):
                    errors.append(_error("REQUIRED_GATE_FAILED", f"{field}.{key}", "runtime gate must be boolean"))
    return errors


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
    if state != "DRY_RUN":
        errors.append(_error("PRODUCTION_DISABLED", "activation_state", "only DRY_RUN can pass the offline gate"))
    if value.get("kill_switch") is True:
        errors.append(_error("KILL_SWITCH_ACTIVE", "kill_switch", "kill switch blocks all new writes"))
    if value.get("production_mutation") != 0:
        errors.append(_error("PRODUCTION_DISABLED", "production_mutation", "production mutation must be zero"))
    created_at = value.get("created_at")
    if not isinstance(created_at, str) or not _DATETIME.fullmatch(created_at):
        errors.append(_error("SCHEMA_INVALID", "created_at", "created_at must be timezone-aware ISO-8601"))
    supplied_hash = value.get("semantic_hash")
    if not _valid_hash(supplied_hash):
        errors.append(_error("HASH_MISMATCH", "semantic_hash", "semantic_hash must be SHA-256"))
    elif supplied_hash != semantic_hash(value):
        errors.append(_error("HASH_MISMATCH", "semantic_hash", "activation semantic hash does not match"))
    errors.extend(_gate_errors(value.get("required_readiness_gates"), None, field="required_readiness_gates"))
    return errors


def validate_activation_proposal(value: Any) -> ValidationResult:
    return ValidationResult(errors=_base_contract_errors(value))


def idempotency_key(operation: Mapping[str, Any]) -> str:
    """Return the stable key bound to the full immutable operation identity."""

    required = ("artifact_type", "entity_id", "revision", "target", "operation", "writer", "semantic_hash")
    if any(operation.get(field) in (None, "") for field in required):
        raise ProductionHardeningError("MISSING_IDEMPOTENCY_KEY", "operation lacks an idempotency input", "operation")
    if not _valid_revision(operation.get("revision")) or not _valid_hash(operation.get("semantic_hash")):
        raise ProductionHardeningError("MISSING_IDEMPOTENCY_KEY", "operation identity is malformed", "operation")
    seed = {field: operation[field] for field in required}
    return "IDEM_" + _hash_payload(seed)[:32]


def _normalise_operation(value: Any, index: int) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ProductionHardeningError("SCHEMA_INVALID", "operation must be an object", f"operations[{index}]")
    operation = copy.deepcopy(dict(value))
    operation.setdefault("operation_id", f"OP_{index + 1:03d}")
    operation.setdefault("failure_mode", "SUCCESS")
    if not _valid_revision(operation.get("revision")):
        raise ProductionHardeningError("REVISION_MISMATCH", "operation revision must be a positive integer", f"operations[{index}].revision")
    if not _valid_hash(operation.get("semantic_hash")):
        raise ProductionHardeningError("HASH_MISMATCH", "operation semantic_hash must be lowercase SHA-256", f"operations[{index}].semantic_hash")
    if not _valid_revision(operation.get("expected_revision")):
        raise ProductionHardeningError("REVISION_MISMATCH", "expected_revision must be a positive integer", f"operations[{index}].expected_revision")
    if not _valid_hash(operation.get("expected_hash")):
        raise ProductionHardeningError("HASH_MISMATCH", "expected_hash must be lowercase SHA-256", f"operations[{index}].expected_hash")
    if operation.get("idempotency_key") in (None, ""):
        operation["idempotency_key"] = idempotency_key(operation)
    elif not isinstance(operation.get("idempotency_key"), str):
        raise ProductionHardeningError("MISSING_IDEMPOTENCY_KEY", "idempotency_key must be opaque text", f"operations[{index}].idempotency_key")
    elif operation["idempotency_key"] != idempotency_key(operation):
        # Keep the supplied opaque key for reconciliation, but mark it so the
        # operation is blocked while a shared ledger can still report a real
        # same-key/different-hash conflict.
        operation["_key_mismatch"] = True
    if operation.get("audit_required") is not True:
        raise ProductionHardeningError("AUDIT_REQUIRED", "every operation requires an audit plan", f"operations[{index}].audit_required")
    audit = operation.get("audit_config")
    if not isinstance(audit, Mapping) or not audit.get("audit_type") or not audit.get("writer"):
        raise ProductionHardeningError("AUDIT_REQUIRED", "audit_config must contain audit_type and writer", f"operations[{index}].audit_config")
    return operation


def _event(event_type: str, *, run_id: str, release_id: str, timestamp: str, status: str, operation: Optional[Mapping[str, Any]] = None, error_code: Optional[str] = None) -> dict[str, Any]:
    safe_run_id = _safe_identifier(run_id)
    safe_release_id = _safe_identifier(release_id)
    record: dict[str, Any] = {
        "event_type": event_type, "run_id": safe_run_id, "release_id": safe_release_id,
        "status": status, "timestamp": timestamp, "production_mutation": 0,
    }
    if operation is not None:
        record.update({
            "operation_id": operation.get("operation_id"), "artifact_type": operation.get("artifact_type"),
            "target": operation.get("target"), "semantic_hash": operation.get("semantic_hash"),
            "idempotency_key": operation.get("idempotency_key"),
        })
    if error_code:
        record["error_code"] = error_code
    return record


def _safe_identifier(value: Any) -> str:
    text = str(value)
    if _SECRET_VALUE.search(text) or _EMAIL_VALUE.search(text) or (_PHONE_VALUE.search(text) and not _DATETIME.fullmatch(text)):
        return "REDACTED"
    return text


def _rollback_plan(release_id: str) -> dict[str, Any]:
    rollback_id = "RB_" + hashlib.sha256(release_id.encode("utf-8")).hexdigest()[:16]
    return {
        "rollback_id": rollback_id, "release_id": release_id, "disable_new_writes": True,
        "disable_future_writes": True, "kill_switch": "set activation_state=REVOKED and disable writer/scheduler",
        "scheduler_disable_required": True, "history_policy": "append superseding or corrective revision; never delete immutable history",
        "supersede_strategy": "append corrective revision with a new semantic hash", "reason": "stop future writes after a failed or revoked promotion",
        "readback_required": True,
        "status": "PLANNED",
    }


def _safe_test_summary(value: Any, *, blocked: bool = False) -> dict[str, Any]:
    if not blocked and isinstance(value, Mapping) and value:
        suites = value.get("suites")
        safe_suites: dict[str, Any] = {}
        if isinstance(suites, Mapping):
            for name, suite in suites.items():
                if isinstance(suite, Mapping):
                    safe_suites[str(name)] = {key: copy.deepcopy(suite[key]) for key in ("suite", "passed", "failed", "skipped", "status", "run_identifier", "source_ref") if key in suite}
        return {"status": value.get("status"), "suites": safe_suites}
    return {"status": "BLOCKED", "suites": {"hardening": {"suite": "hardening", "passed": 0, "failed": 1, "skipped": 0, "status": "FAIL", "run_identifier": "MISSING_OR_REJECTED"}}}


def _test_summary_errors(value: Any) -> list[ValidationError]:
    if not isinstance(value, Mapping) or not value:
        return [_error("SCHEMA_INVALID", "test_result_summary", "structured test result summary is required")]
    suites = value.get("suites")
    if not isinstance(suites, Mapping) or not suites:
        return [_error("SCHEMA_INVALID", "test_result_summary.suites", "test summary suites are required")]
    errors: list[ValidationError] = []
    for suite_name, suite in suites.items():
        required = ("suite", "passed", "failed", "skipped", "status", "run_identifier")
        if not isinstance(suite, Mapping) or any(key not in suite for key in required) or suite.get("status") not in {"PASS", "FAIL"}:
            errors.append(_error("SCHEMA_INVALID", f"test_result_summary.suites.{suite_name}", "suite status must be PASS or FAIL"))
        if isinstance(suite, Mapping) and (not isinstance(suite.get("run_identifier"), str) or not suite.get("run_identifier")):
            errors.append(_error("SCHEMA_INVALID", f"test_result_summary.suites.{suite_name}", "suite run_identifier is required"))
        if isinstance(suite, Mapping) and (not isinstance(suite.get("passed"), int) or not isinstance(suite.get("failed"), int) or not isinstance(suite.get("skipped"), int) or suite.get("failed", 0) < 0 or suite.get("passed", 0) < 0 or suite.get("skipped", 0) < 0):
            errors.append(_error("SCHEMA_INVALID", f"test_result_summary.suites.{suite_name}", "suite counts must be non-negative integers"))
        if isinstance(suite, Mapping) and suite.get("failed", 0) > 0:
            errors.append(_error("PRODUCTION_DISABLED", f"test_result_summary.suites.{suite_name}", "failed test suite blocks production readiness"))
    return errors


def _manifest_input_errors(value: Mapping[str, Any]) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(value.get("release_id"), str) or not value.get("release_id"):
        errors.append(_error("SCHEMA_INVALID", "release_id", "release_id is required"))
    if not isinstance(value.get("main_sha"), str) or _SHA40.fullmatch(value.get("main_sha", "")) is None:
        errors.append(_error("SCHEMA_INVALID", "main_sha", "main_sha must be a 40-character lowercase SHA"))
    for field in ("wp_versions", "contract_versions"):
        if not isinstance(value.get(field), Mapping) or not value.get(field):
            errors.append(_error("SCHEMA_INVALID", field, f"{field} must be non-empty"))
    if "revision" in value and not _valid_revision(value.get("revision")):
        errors.append(_error("REVISION_MISMATCH", "revision", "release revision must be a positive integer"))
    return errors


def _operation_summary(operation: Mapping[str, Any], *, status: Optional[str] = None, errors: Optional[list[ValidationError]] = None) -> dict[str, Any]:
    summary = {key: operation.get(key) for key in ("operation_id", "artifact_type", "revision", "expected_revision", "target", "operation", "writer", "semantic_hash", "expected_hash", "idempotency_key", "status") if operation.get(key) is not None}
    if status is not None:
        summary["status"] = status
    if errors:
        summary["errors"] = [error.as_dict() for error in errors]
    return summary


def build_release_manifest(value: Mapping[str, Any], *, status: str, planned_operations: list[dict[str, Any]], blocked_operations: list[dict[str, Any]], events: list[dict[str, Any]], required_gates: Optional[Mapping[str, Any]] = None, gate_results: Optional[Mapping[str, Any]] = None, sensitive_rejected: bool = False) -> dict[str, Any]:
    """Build a deterministic manifest with mandatory lineage and gate fields."""

    activation = value.get("activation") if isinstance(value.get("activation"), Mapping) else {}
    required = required_gates if required_gates is not None else activation.get("required_readiness_gates")
    results = gate_results if gate_results is not None else value.get("readiness_gates")
    release_id = _safe_identifier(value.get("release_id", "REL_WP12_DRY_RUN"))
    manifest: dict[str, Any] = {
        "record_type": "PRODUCTION_RELEASE_MANIFEST", "contract_version": RELEASE_MANIFEST_CONTRACT_VERSION,
        "release_id": release_id, "revision": value.get("revision", 1) if _valid_revision(value.get("revision", 1)) else 1,
        "main_sha": value.get("main_sha") if _SHA40.fullmatch(str(value.get("main_sha", ""))) else "0" * 40,
        "wp_versions": copy.deepcopy(value.get("wp_versions")) if isinstance(value.get("wp_versions"), Mapping) and value.get("wp_versions") else {"WP12": "UNKNOWN"},
        "contract_versions": copy.deepcopy(value.get("contract_versions")) if isinstance(value.get("contract_versions"), Mapping) and value.get("contract_versions") else {"activation": ACTIVATION_CONTRACT_VERSION},
        "test_result_summary": _safe_test_summary(value.get("test_result_summary"), blocked=sensitive_rejected),
        "required_gates": copy.deepcopy(dict(required)) if isinstance(required, Mapping) and required else {"_missing": False},
        "gate_results": copy.deepcopy(dict(results)) if isinstance(results, Mapping) and results else {"_missing": False},
        "activation_status": status, "activation_state": activation.get("activation_state", "BLOCKED"),
        "approved_writers": copy.deepcopy(activation.get("allowed_writers", [])), "scheduler_state": "DISABLED",
        "production_write_ready": False, "production_activation_readiness": "NOT_AUTHORIZED",
        "known_policy_gaps": [] if sensitive_rejected else (copy.deepcopy(value.get("known_policy_gaps", [])) if isinstance(value.get("known_policy_gaps", []), list) else []),
        "known_source_gaps": [] if sensitive_rejected else (copy.deepcopy(value.get("known_source_gaps", [])) if isinstance(value.get("known_source_gaps", []), list) else []),
        "rollback_instructions": _rollback_plan(str(release_id)), "planned_operations": copy.deepcopy(planned_operations),
        "blocked_operations": copy.deepcopy(blocked_operations), "observability_events": copy.deepcopy(events),
        "production_mutation": 0, "actual_write_count": 0, "created_at": value.get("created_at", activation.get("created_at")),
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
    if value.get("production_mutation") != 0 or value.get("actual_write_count") != 0 or value.get("production_write_ready") is not False:
        errors.append(_error("PRODUCTION_DISABLED", "production_mutation", "release manifest cannot perform writes"))
    if value.get("production_activation_readiness") != "NOT_AUTHORIZED":
        errors.append(_error("PRODUCTION_DISABLED", "production_activation_readiness", "production activation remains unauthorized"))
    if value.get("semantic_hash") != semantic_hash(value):
        errors.append(_error("HASH_MISMATCH", "semantic_hash", "release manifest semantic hash does not match"))
    errors.extend(_gate_errors(value.get("required_gates"), value.get("gate_results"), field="gate_results"))
    errors.extend(_test_summary_errors(value.get("test_result_summary")))
    errors.extend(_manifest_input_errors(value))
    return ValidationResult(errors=errors)


def _receipt_errors(operation: Mapping[str, Any]) -> tuple[list[ValidationError], Optional[str]]:
    receipt = operation.get("execution_receipt")
    if receipt is None:
        mode = operation.get("failure_mode")
        if mode == "WRITE_THEN_AUDIT_FAIL":
            return [_error("AUDIT_WRITE_FAILED", "execution_receipt", "audit receipt failed after the simulated write")], "PARTIAL"
        if mode == "WRITE_FAIL":
            return [_error("PRODUCTION_DISABLED", "execution_receipt", "simulated write failed")], "FAILED"
        return [], None
    if not isinstance(receipt, Mapping) or receipt.get("status") not in {"PLANNED", "SUCCEEDED", "FAILED"}:
        return [_error("SCHEMA_INVALID", "execution_receipt", "execution receipt status is required")], "FAILED"
    if receipt.get("status") == "FAILED":
        return [_error(str(receipt.get("error_code", "PRODUCTION_DISABLED")), "execution_receipt", "execution receipt records a failure")], "PARTIAL"
    return [], None


def dry_run_promotion(value: Mapping[str, Any], *, ledger: Optional[IdempotencyLedger] = None) -> HardeningResult:
    """Evaluate a production-style promotion without performing a write."""

    errors: list[ValidationError] = []
    events: list[dict[str, Any]] = []
    value = copy.deepcopy(dict(value)) if isinstance(value, Mapping) else {}
    activation = value.get("activation") if isinstance(value.get("activation"), Mapping) else {}
    run_id = str(value.get("run_id", "RUN_WP12_DRY_RUN"))
    release_id = str(value.get("release_id", "REL_WP12_DRY_RUN"))
    timestamp = str(value.get("created_at", activation.get("created_at", "2026-09-14T12:00:00+08:00")))
    events.append(_event("run_started", run_id=run_id, release_id=release_id, timestamp=timestamp, status="STARTED"))
    errors.extend(_base_contract_errors(activation))
    sensitive_errors = _walk_sensitive(value)
    errors.extend(sensitive_errors)
    environment = str(activation.get("environment", "")).upper()
    if bool(value.get("scheduler_enabled")) or value.get("scheduler_state", "DISABLED") != "DISABLED" or activation.get("allowed_schedulers"):
        errors.append(_error("SCHEDULER_DISABLED", "scheduler", "scheduler is disabled in WP12"))
    if bool(value.get("kill_switch")) or activation.get("kill_switch") is True:
        errors.append(_error("KILL_SWITCH_ACTIVE", "kill_switch", "kill switch blocks all new writes"))
    required = activation.get("required_readiness_gates")
    readiness = value.get("readiness_gates")
    errors.extend(_gate_errors(required, readiness))
    approval = value.get("production_authorization")
    explicit_authorization = isinstance(approval, Mapping) and approval.get("authorized") is True
    if environment == "PRODUCTION" and not explicit_authorization:
        errors.append(_error("AUTHORIZATION_REQUIRED", "production_authorization", "production activation requires separate explicit authorization"))
    if environment == "PRODUCTION" and activation.get("x-proposal-status") == PROPOSAL_STATUS:
        errors.append(_error("CONTRACT_NOT_APPROVED", "x-proposal-status", "draft activation contract blocks production"))
    errors.extend(_test_summary_errors(value.get("test_result_summary")))
    errors.extend(_manifest_input_errors(value))
    if errors:
        events.append(_event("validation_failed", run_id=run_id, release_id=release_id, timestamp=timestamp, status="FAILED", error_code=errors[0].code))
    else:
        events.append(_event("validation_passed", run_id=run_id, release_id=release_id, timestamp=timestamp, status="PASS"))

    allowed_writers = set(str(item) for item in activation.get("allowed_writers", []) if isinstance(item, str))
    allowed_targets = set(str(item) for item in activation.get("allowed_targets", []) if isinstance(item, str))
    allowed_sources = set(str(item) for item in activation.get("allowed_sources", []) if isinstance(item, str))
    planned: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    partial = False
    failed = False
    for index, raw_operation in enumerate(value.get("operations", []) or []):
        operation_sensitive = _walk_sensitive(raw_operation, f"operations[{index}]")
        if operation_sensitive:
            summary = {"operation_id": f"OP_{index + 1:03d}", "status": "BLOCKED", "errors": [error.as_dict() for error in operation_sensitive]}
            blocked.append(summary)
            errors.extend(operation_sensitive)
            events.append(_event("write_blocked", run_id=run_id, release_id=release_id, timestamp=timestamp, status="BLOCKED", error_code=operation_sensitive[0].code))
            continue
        try:
            operation = _normalise_operation(raw_operation, index)
        except ProductionHardeningError as exc:
            blocked.append({"operation_id": f"OP_{index + 1:03d}", "status": "BLOCKED", "error_code": exc.code})
            errors.append(_error(exc.code, exc.field, str(exc)))
            if exc.code == "IDEMPOTENCY_KEY_MISMATCH":
                errors.append(_error("IDEMPOTENCY_CONFLICT", exc.field, "supplied idempotency key conflicts with operation identity"))
            continue
        operation_errors: list[ValidationError] = []
        if operation.get("revision") != operation.get("expected_revision"):
            operation_errors.append(_error("REVISION_MISMATCH", "revision", "artifact revision does not match the pinned expected revision"))
        if operation.get("semantic_hash") != operation.get("expected_hash"):
            operation_errors.append(_error("HASH_MISMATCH", "semantic_hash", "artifact hash does not match the pinned expected hash"))
        if operation.get("writer") not in allowed_writers:
            operation_errors.append(_error("WRITER_NOT_ALLOWED", "writer", "writer is not on the activation allowlist"))
        if operation.get("target") not in allowed_targets:
            operation_errors.append(_error("TARGET_NOT_ALLOWED", "target", "target is not on the activation allowlist"))
        if str(operation.get("target", "")).upper().startswith("PRODUCTION"):
            operation_errors.append(_error("PRODUCTION_DISABLED", "target", "production targets are disabled in WP12"))
        if operation.get("source") is not None and operation.get("source") not in allowed_sources:
            operation_errors.append(_error("SOURCE_UNAVAILABLE", "source", "source is not on the activation allowlist"))
        freshness = operation.get("freshness_state")
        if freshness in {"STALE", "FAILED"}:
            operation_errors.append(_error("STALE_EVIDENCE", "freshness_state", "stale or failed evidence blocks a write"))
        elif freshness in {"NOT_AVAILABLE", "MISSING"}:
            operation_errors.append(_error("SOURCE_UNAVAILABLE", "freshness_state", "missing evidence cannot be treated as zero"))
        elif freshness != "READY":
            operation_errors.append(_error("STALE_EVIDENCE", "freshness_state", "freshness_state must be READY"))
        if operation.get("status") not in {"READY", "VALIDATED", "APPROVED_UAT"}:
            operation_errors.append(_error("PRODUCTION_DISABLED", "status", "operation status is not eligible for dry-run planning"))
        if operation.get("contract_state") != PROPOSAL_STATUS:
            operation_errors.append(_error("CONTRACT_NOT_APPROVED", "contract_state", "operation contract must remain proposal-only"))
        if operation.get("approval_state") not in {"APPROVED_UAT", "NOT_REQUIRED_FOR_DRY_RUN"}:
            operation_errors.append(_error("AUTHORIZATION_REQUIRED", "approval_state", "human/UAT approval state is required"))
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
        receipt_errors, receipt_status = _receipt_errors(operation)
        operation_errors.extend(receipt_errors)
        if operation.get("_key_mismatch"):
            operation_errors.append(_error("IDEMPOTENCY_KEY_MISMATCH", "idempotency_key", "idempotency key is not bound to operation identity"))
        if receipt_status == "PARTIAL":
            partial = True
        if receipt_status == "FAILED":
            failed = True
        key = operation["idempotency_key"]
        previous_hash = seen.get(key)
        if previous_hash is not None:
            if previous_hash != operation["semantic_hash"]:
                operation_errors.append(_error("IDEMPOTENCY_CONFLICT", "idempotency_key", "same key has a different semantic hash"))
            else:
                operation["status"] = "IDEMPOTENT_NO_OP"
        else:
            seen[key] = operation["semantic_hash"]
        if ledger is not None:
            ledger_state = ledger.reconcile(operation)
            if ledger_state == "IDEMPOTENCY_CONFLICT":
                operation_errors.append(_error("IDEMPOTENCY_CONFLICT", "idempotency_key", "cross-run key has a different semantic hash"))
            elif ledger_state == "ALREADY_APPLIED":
                operation["status"] = "ALREADY_APPLIED"
        if operation_errors:
            operation["status"] = "BLOCKED"
            blocked.append(_operation_summary(operation, status="BLOCKED", errors=operation_errors))
            errors.extend(operation_errors)
            events.append(_event("write_blocked", run_id=run_id, release_id=release_id, timestamp=timestamp, status="BLOCKED", operation=operation, error_code=operation_errors[0].code))
            if receipt_status in {"PARTIAL", "FAILED"}:
                events.append(_event("write_failed", run_id=run_id, release_id=release_id, timestamp=timestamp, status="FAILED", operation=operation, error_code=receipt_errors[0].code if receipt_errors else "PRODUCTION_DISABLED"))
        else:
            if operation.get("status") in {"READY", "VALIDATED", "APPROVED_UAT", None}:
                operation["status"] = "PLANNED"
            planned.append(_operation_summary(operation, status=operation["status"]))
            if ledger is not None and operation["status"] == "PLANNED":
                ledger.record_plan(operation)
            events.append(_event("write_planned", run_id=run_id, release_id=release_id, timestamp=timestamp, status=operation["status"], operation=operation))
            if operation.get("failure_mode") == "WRITE_THEN_AUDIT_FAIL":
                partial = True
                events.append(_event("write_succeeded", run_id=run_id, release_id=release_id, timestamp=timestamp, status="SIMULATED", operation=operation))
                events.append(_event("write_failed", run_id=run_id, release_id=release_id, timestamp=timestamp, status="FAILED", operation=operation, error_code="AUDIT_WRITE_FAILED"))
            elif operation.get("failure_mode") == "WRITE_FAIL":
                failed = True
                events.append(_event("write_failed", run_id=run_id, release_id=release_id, timestamp=timestamp, status="FAILED", operation=operation, error_code="PRODUCTION_DISABLED"))
    if partial and not any(error.code == "AUDIT_WRITE_FAILED" for error in errors):
        errors.append(_error("AUDIT_WRITE_FAILED", "operations", "audit failure leaves the run partial"))
    if failed and not any(error.code == "PRODUCTION_DISABLED" for error in errors):
        errors.append(_error("PRODUCTION_DISABLED", "operations", "write failure is retryable and not complete"))
    if partial:
        status = "PARTIAL"
    elif failed:
        status = "FAILED"
    elif errors and not planned:
        status = "BLOCKED"
    elif errors:
        status = "DRY_RUN_VALIDATION_BLOCKED"
    else:
        status = "DRY_RUN_VALIDATION_READY"
    events.append(_event("run_partial" if status == "PARTIAL" else "run_completed", run_id=run_id, release_id=release_id, timestamp=timestamp, status=status))
    manifest = build_release_manifest(value, status=status, planned_operations=planned, blocked_operations=blocked, events=events, required_gates=required, gate_results=readiness, sensitive_rejected=bool(sensitive_errors))
    manifest["x-proposal-status"] = PROPOSAL_STATUS
    manifest["x-production-activation"] = False
    manifest["semantic_hash"] = semantic_hash(manifest)
    result = ValidationResult(errors=errors)
    manifest_validation = validate_release_manifest(manifest)
    if not manifest_validation.is_valid:
        result = ValidationResult(errors=[*errors, *manifest_validation.errors])
    return HardeningResult(manifest=manifest, validation=result, events=tuple(events))


def validate_hardening_result(result: HardeningResult) -> ValidationResult:
    errors = list(result.validation.errors)
    errors.extend(_walk_sensitive(result.manifest))
    if result.write_count != 0 or result.manifest.get("production_mutation") != 0:
        errors.append(_error("PRODUCTION_DISABLED", "actual_write_count", "hardening result must have zero writes"))
    if result.manifest.get("scheduler_state") != "DISABLED":
        errors.append(_error("SCHEDULER_DISABLED", "scheduler_state", "scheduler must remain disabled"))
    if result.manifest.get("production_write_ready") is not False:
        errors.append(_error("PRODUCTION_DISABLED", "production_write_ready", "production writer must remain disabled"))
    return ValidationResult(errors=errors)


__all__ = [
    "ACTIVATION_CONTRACT_VERSION", "RELEASE_MANIFEST_CONTRACT_VERSION", "ERROR_CODES",
    "HardeningResult", "IdempotencyLedger", "ProductionHardeningError",
    "build_release_manifest", "dry_run_promotion", "idempotency_key", "semantic_hash",
    "validate_activation_proposal", "validate_hardening_result", "validate_release_manifest",
]
