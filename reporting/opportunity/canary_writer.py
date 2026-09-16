"""Offline Recommendation Phase 1 canary writer.

This module is a proposal-only boundary.  It plans one Recommendation write,
uses an injected synthetic transport, performs mandatory readback, and stores
an append-only audit receipt.  It never refreshes OAuth, calls Google Sheets,
starts a scheduler, or writes a production destination.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence

from .proposal_validation import ValidationError, ValidationResult
from .review_bridge import validate_recommendation_bridge
from .review import validate_human_review
from .store.serialization import canonical_json, canonical_line


CONTRACT_VERSION = "recommendation_canary_writer.v1.proposal"
TARGET_BINDING_CONTRACT_VERSION = "google_sheets_target_binding.v1.proposal"
WRITER_ID = "recommendation-canary-writer"
TARGET_TAB = "Opportunity_Recommendations"
PROPOSAL_STATUS = "DRAFT_NOT_APPROVED"
ALLOWED_FIELDS = (
    "recommendation_id", "candidate_id", "candidate_revision", "candidate_hash",
    "review_id", "review_revision", "review_hash", "bridge_id", "bridge_revision",
    "bridge_hash", "recommendation_text", "action_type", "topic_refs",
    "target_url_refs", "score", "confidence", "evidence_refs", "conflict_status",
    "governance_status", "release_id", "operation_id", "semantic_hash", "created_at",
)
PROTECTED_FIELDS = (
    "human_notes", "next_steps", "existing_report_data", "human_decision",
    "review_content", "unapproved_fields", "other_workbook_data",
)
RESULT_STATES = frozenset({
    "PLANNED", "BLOCKED", "WRITE_INTENT_READY", "TRANSPORT_SUCCEEDED",
    "TRANSPORT_UNKNOWN", "READBACK_MATCHED", "READBACK_MISMATCH",
    "RECONCILED_SUCCESS", "RECONCILIATION_CONFLICT", "AUDIT_PERSISTED",
    "CANARY_COMPLETE", "SAFE_TO_RETRY_REQUIRES_HUMAN_AUTHORIZATION",
})
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_SECRET_KEY = re.compile(r"(?:api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|password|authorization|cookie|private[_-]?key)", re.I)
_PII_KEY = re.compile(r"(?:^|[_-])(email|e-mail|phone|telephone|mobile|customer[_-]?id|lead[_-]?id|full[_-]?name)(?:$|[_-])", re.I)
_SECRET_VALUE = re.compile(r"(?:bearer\s+|sk-[A-Za-z0-9]|gh[pousr]_[A-Za-z0-9]|AIza[0-9A-Za-z_-]{20,})", re.I)
_EMAIL_VALUE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE_VALUE = re.compile(r"(?<!\d)\+?\d[\d\s().-]{7,}\d(?!\d)")


def _error(code: str, field: str, message: str) -> ValidationError:
    return ValidationError(code, field, message)


def _hash(value: Mapping[str, Any], *, exclude: Sequence[str] = ()) -> str:
    excluded = set(exclude)
    payload = {key: item for key, item in value.items() if key not in excluded}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _positive_revision(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _valid_hash(value: Any) -> bool:
    return isinstance(value, str) and _SHA256.fullmatch(value) is not None


def _text_ref(value: Any, field: str) -> Optional[ValidationError]:
    if not isinstance(value, str) or not _REF.fullmatch(value):
        return _error("INVALID_REFERENCE", field, "reference must be a bounded opaque value")
    return None


def _safe_datetime(value: Any, field: str = "created_at") -> Optional[ValidationError]:
    if not isinstance(value, str) or not _DATETIME.fullmatch(value):
        return _error("INVALID_DATETIME", field, "timestamp must be timezone-aware ISO-8601")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return _error("INVALID_DATETIME", field, "timestamp is not parseable")
    return None


def _canary_sensitive_errors(value: Any, path: str = "record") -> list[ValidationError]:
    errors: list[ValidationError] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if _SECRET_KEY.search(key_text):
                errors.append(_error("SECRET_REJECTED", path, "secret-like fields cannot enter canary artifacts"))
            if _PII_KEY.search(key_text):
                errors.append(_error("PII_REJECTED", path, "raw PII fields cannot enter canary artifacts"))
            errors.extend(_canary_sensitive_errors(item, f"{path}.*"))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            errors.extend(_canary_sensitive_errors(item, f"{path}[{index}]"))
    elif isinstance(value, str):
        if _SECRET_VALUE.search(value):
            errors.append(_error("SECRET_REJECTED", path, "secret-like values cannot enter canary artifacts"))
        if not _DATETIME.fullmatch(value) and not _SHA256.fullmatch(value):
            if _EMAIL_VALUE.search(value) or _PHONE_VALUE.fullmatch(value.strip()):
                errors.append(_error("PII_REJECTED", path, "raw PII values cannot enter canary artifacts"))
    return errors


@dataclass(frozen=True)
class GoogleSheetsTargetBinding:
    """Runtime target binding; workbook ID and principal are references only."""

    binding_id: str
    environment: str
    workbook_id_ref: str
    tab_name: str
    allowed_fields: tuple[str, ...]
    protected_fields: tuple[str, ...]
    writer_principal_ref: str
    readback_required: bool
    max_operations: int
    created_at: str
    semantic_hash: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "GoogleSheetsTargetBinding":
        data = dict(value)
        allowed = tuple(data.get("allowed_fields", ALLOWED_FIELDS))
        protected = tuple(data.get("protected_fields", PROTECTED_FIELDS))
        raw = {key: data.get(key) for key in (
            "binding_id", "environment", "workbook_id_ref", "tab_name", "writer_principal_ref",
            "readback_required", "max_operations", "created_at",
        )}
        raw["allowed_fields"] = list(allowed)
        raw["protected_fields"] = list(protected)
        raw["semantic_hash"] = None
        calculated = _hash(raw, exclude=("semantic_hash",))
        provided = data.get("semantic_hash")
        if provided is not None and provided != calculated:
            raise ValueError("TARGET_BINDING_HASH_MISMATCH")
        return cls(
            binding_id=str(data.get("binding_id", "")),
            environment=str(data.get("environment", "")).upper(),
            workbook_id_ref=str(data.get("workbook_id_ref", "")),
            tab_name=str(data.get("tab_name", "")),
            allowed_fields=allowed,
            protected_fields=protected,
            writer_principal_ref=str(data.get("writer_principal_ref", "")),
            readback_required=data.get("readback_required") is True,
            max_operations=data.get("max_operations", 0),
            created_at=str(data.get("created_at", "")),
            semantic_hash=calculated,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "binding_id": self.binding_id, "environment": self.environment,
            "workbook_id_ref": self.workbook_id_ref, "tab_name": self.tab_name,
            "allowed_fields": list(self.allowed_fields), "protected_fields": list(self.protected_fields),
            "writer_principal_ref": self.writer_principal_ref, "readback_required": self.readback_required,
            "max_operations": self.max_operations, "created_at": self.created_at,
            "semantic_hash": self.semantic_hash,
        }


@dataclass(frozen=True)
class WriteIntent:
    operation_id: str
    idempotency_key: str
    writer_id: str
    principal_ref: str
    target_binding_ref: str
    recommendation_id: str
    candidate_revision: int
    review_revision: int
    bridge_revision: int
    planned_fields: tuple[str, ...]
    payload_hash: str
    created_at: str
    state: str = "WRITE_INTENT_READY"

    def as_dict(self) -> dict[str, Any]:
        return {key: value for key, value in self.__dict__.items()}


@dataclass(frozen=True)
class TransportResult:
    state: str
    record: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None


class RecommendationTransport(Protocol):
    def write(self, binding: GoogleSheetsTargetBinding, intent: WriteIntent, payload: Mapping[str, Any]) -> TransportResult:
        ...

    def readback(self, binding: GoogleSheetsTargetBinding, operation_id: str) -> Optional[dict[str, Any]]:
        ...


class SyntheticRecommendationTransport:
    """Fake transport for offline/UAT tests; it never performs network I/O."""

    def __init__(self, mode: str = "SUCCESS") -> None:
        self.mode = mode.upper()
        self.records: dict[str, dict[str, Any]] = {}
        self.write_calls = 0

    def write(self, binding: GoogleSheetsTargetBinding, intent: WriteIntent, payload: Mapping[str, Any]) -> TransportResult:
        self.write_calls += 1
        if self.mode == "REJECTED":
            return TransportResult("REJECTED", error_code="TRANSPORT_REJECTED")
        if self.mode == "PARTIAL":
            return TransportResult("PARTIAL", error_code="TRANSPORT_PARTIAL")
        if self.mode in {"TIMEOUT_WRITES", "UNKNOWN_WRITES"}:
            self.records[intent.operation_id] = copy.deepcopy(dict(payload))
            return TransportResult("UNKNOWN", error_code="TRANSPORT_UNKNOWN")
        if self.mode in {"TIMEOUT_ABSENT", "UNKNOWN_ABSENT"}:
            return TransportResult("UNKNOWN", error_code="TRANSPORT_UNKNOWN")
        if self.mode in {"TIMEOUT_CONFLICT", "UNKNOWN_CONFLICT"}:
            conflict = copy.deepcopy(dict(payload))
            conflict["semantic_hash"] = "f" * 64
            self.records[intent.operation_id] = conflict
            return TransportResult("UNKNOWN", error_code="TRANSPORT_UNKNOWN")
        if self.mode == "MISMATCH":
            self.records[intent.operation_id] = {**copy.deepcopy(dict(payload)), "candidate_hash": "e" * 64}
            return TransportResult("SUCCEEDED")
        self.records[intent.operation_id] = copy.deepcopy(dict(payload))
        return TransportResult("SUCCEEDED", record=copy.deepcopy(dict(payload)))

    def readback(self, binding: GoogleSheetsTargetBinding, operation_id: str) -> Optional[dict[str, Any]]:
        return copy.deepcopy(self.records.get(operation_id))


class CanaryIdempotencyStore:
    """Persistent-style append-only key store for offline reconciliation."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._records: dict[str, str] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    item = json.loads(line)
                    self._records[str(item["idempotency_key"])] = str(item["payload_hash"])

    def reconcile(self, key: str, payload_hash: str) -> str:
        previous = self._records.get(key)
        if previous is None:
            return "NEW"
        return "ALREADY_APPLIED" if previous == payload_hash else "IDEMPOTENCY_CONFLICT"

    def record(self, key: str, payload_hash: str) -> None:
        if key in self._records:
            return
        line = canonical_line({"idempotency_key": key, "payload_hash": payload_hash})
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
            handle.flush()
        self._records[key] = payload_hash


class RecommendationAuditStore:
    """Append-only JSON receipt store; existing receipts are never overwritten."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def append(self, receipt: Mapping[str, Any]) -> dict[str, Any]:
        operation_id = str(receipt.get("operation_id", ""))
        if not _REF.fullmatch(operation_id):
            raise ValueError("AUDIT_OPERATION_ID_INVALID")
        path = self.root / f"operation_{operation_id}.json"
        value = copy.deepcopy(dict(receipt))
        value["semantic_hash"] = _hash(value, exclude=("semantic_hash",))
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("semantic_hash") != value["semantic_hash"]:
                raise ValueError("AUDIT_IMMUTABLE_CONFLICT")
            return existing
        encoded = canonical_json(value) + "\n"
        path.write_text(encoded, encoding="utf-8")
        return value


@dataclass(frozen=True)
class CanaryResult:
    state: str
    validation: ValidationResult
    payload: Optional[dict[str, Any]]
    write_intent: Optional[WriteIntent]
    audit_receipt: Optional[dict[str, Any]]
    reconciliation_state: Optional[str]
    transport_state: Optional[str]
    readback_state: Optional[str]
    production_mutation_count: int = 0

    @property
    def is_valid(self) -> bool:
        return self.state == "CANARY_COMPLETE" and self.validation.is_valid

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state, "validation": self.validation.as_dict(),
            "payload": copy.deepcopy(self.payload),
            "write_intent": self.write_intent.as_dict() if self.write_intent else None,
            "audit_receipt": copy.deepcopy(self.audit_receipt),
            "reconciliation_state": self.reconciliation_state,
            "transport_state": self.transport_state, "readback_state": self.readback_state,
            "production_mutation_count": self.production_mutation_count,
        }


def idempotency_key(*, writer_id: str, target_binding_ref: str, recommendation_id: str, candidate_revision: int, review_revision: int, bridge_revision: int, semantic_hash: str, operation_type: str = "PUBLISH_RECOMMENDATION") -> str:
    seed = {
        "writer_id": writer_id, "target_binding_ref": target_binding_ref,
        "recommendation_id": recommendation_id, "candidate_revision": candidate_revision,
        "review_revision": review_revision, "bridge_revision": bridge_revision,
        "semantic_hash": semantic_hash, "operation_type": operation_type,
    }
    return "IDEM_" + _hash(seed)[:48]


def _result(state: str, errors: list[ValidationError], *, payload: Optional[dict[str, Any]] = None, intent: Optional[WriteIntent] = None, receipt: Optional[dict[str, Any]] = None, reconciliation: Optional[str] = None, transport: Optional[str] = None, readback: Optional[str] = None) -> CanaryResult:
    return CanaryResult(state, ValidationResult(errors=errors), payload, intent, receipt, reconciliation, transport, readback)


def _pin(value: Any, prefix: str, errors: list[ValidationError]) -> None:
    if not isinstance(value, Mapping):
        errors.append(_error("INVALID_PIN", prefix, "revision pin is required"))
        return
    if not isinstance(value.get("evidence_id"), str) or not value["evidence_id"] or not _positive_revision(value.get("revision")) or not _valid_hash(value.get("content_hash")):
        errors.append(_error("INVALID_PIN", prefix, "pin requires evidence_id, positive revision and SHA-256 content_hash"))


def _validate_binding(binding: GoogleSheetsTargetBinding) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for field in ("binding_id", "workbook_id_ref", "writer_principal_ref"):
        err = _text_ref(getattr(binding, field), field)
        if err:
            errors.append(err)
    if binding.environment != "UAT":
        errors.append(_error("TARGET_ENVIRONMENT_BLOCKED", "environment", "canary writer only accepts UAT synthetic bindings"))
    if not binding.binding_id.startswith("binding://canary/") or not binding.workbook_id_ref.startswith("runtime://"):
        errors.append(_error("TARGET_BINDING_UNKNOWN", "binding_id", "target binding must be an approved runtime UAT reference"))
    if not binding.writer_principal_ref.startswith("principal://authorized-user-oauth/"):
        errors.append(_error("WRITER_UNAUTHORIZED", "writer_principal_ref", "only the authorized-user OAuth runtime reference is allowed"))
    if binding.tab_name != TARGET_TAB:
        errors.append(_error("TARGET_TAB_NOT_ALLOWED", "tab_name", f"target tab must be {TARGET_TAB}"))
    if tuple(binding.allowed_fields) != ALLOWED_FIELDS:
        errors.append(_error("ALLOWLIST_MISMATCH", "allowed_fields", "target binding must use the fixed Phase 1 allowlist"))
    if not set(PROTECTED_FIELDS).issubset(set(binding.protected_fields)):
        errors.append(_error("PROTECTED_FIELDS_MISSING", "protected_fields", "all protected fields must remain protected"))
    if binding.readback_required is not True:
        errors.append(_error("READBACK_REQUIRED", "readback_required", "readback is mandatory"))
    if binding.max_operations != 1:
        errors.append(_error("OPERATION_LIMIT_INVALID", "max_operations", "Phase 1 max_operations must be 1"))
    if _safe_datetime(binding.created_at, "created_at"):
        errors.append(_safe_datetime(binding.created_at, "created_at"))
    return [error for error in errors if error is not None]


def _trusted_review_errors(review: Mapping[str, Any], context: Any) -> list[ValidationError]:
    errors: list[ValidationError] = []
    if not isinstance(context, Mapping) or context.get("verified") is not True or not context.get("provider_ref") or not context.get("subject_ref"):
        errors.append(_error("BLOCKED_TRUSTED_IDENTITY", "trusted_review_context", "production identity provider verification is required; caller authentication booleans are insufficient"))
    if review.get("reviewer", {}).get("authenticated") is not True or review.get("authenticated_human") is not True:
        errors.append(_error("BLOCKED_TRUSTED_IDENTITY", "reviewer", "reviewer must be authenticated"))
    if review.get("superseded") is True or str(review.get("review_status", "")).upper() == "SUPERSEDED":
        errors.append(_error("SUPERSEDED_REVIEW", "review", "superseded review cannot publish"))
    return errors


def _eligibility(operation: Mapping[str, Any], trusted_review_context: Any) -> tuple[list[ValidationError], Optional[dict[str, Any]], Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    errors: list[ValidationError] = []
    candidate = operation.get("candidate") if isinstance(operation.get("candidate"), Mapping) else {}
    review = operation.get("review") if isinstance(operation.get("review"), Mapping) else {}
    bridge = operation.get("bridge") if isinstance(operation.get("bridge"), Mapping) else {}
    if not candidate or not review or not bridge:
        errors.append(_error("ELIGIBILITY_INPUT_MISSING", "operation", "candidate, review and bridge are required"))
        return errors, None, None, None
    bridge_result = validate_recommendation_bridge(bridge)
    if not bridge_result.is_valid:
        errors.extend(_error("INVALID_BRIDGE_PIN", "bridge", error.message) for error in bridge_result.errors)
    review_result = validate_human_review(review)
    if not review_result.is_valid:
        errors.extend(_error("INVALID_REVIEW_PIN", "review", error.message) for error in review_result.errors)
    if candidate.get("revision") != bridge.get("candidate_revision") or candidate.get("content_hash") != bridge.get("candidate_hash"):
        errors.append(_error("CANDIDATE_PIN_MISMATCH", "candidate", "bridge must pin the exact Candidate revision/hash"))
    if review.get("revision") != bridge.get("review_revision") or review.get("content_hash") != bridge.get("review_hash"):
        errors.append(_error("REVIEW_PIN_MISMATCH", "review", "bridge must pin the exact Review revision/hash"))
    errors.extend(_trusted_review_errors(review, trusted_review_context))
    if operation.get("review_superseded") is True:
        errors.append(_error("SUPERSEDED_REVIEW", "review", "superseded review cannot publish"))
    if bridge.get("review_decision") != "APPROVE":
        errors.append(_error("HUMAN_APPROVAL_REQUIRED", "bridge.review_decision", "only an approved bridge can publish"))
    if bridge.get("conflicts") and not review.get("conflict_adjudication_ref"):
        errors.append(_error("UNRESOLVED_BLOCKING_CONFLICT", "bridge.conflicts", "blocking conflicts require explicit adjudication"))
    if candidate.get("freshness_state") in {"STALE", "FAILED", "NOT_AVAILABLE", "MISSING"} or candidate.get("stale") is True:
        errors.append(_error("FRESHNESS_BLOCKED", "candidate.freshness_state", "stale or unavailable evidence cannot publish"))
    if str(candidate.get("serp_status", "")).upper() == "SERP_NOT_CHECKED":
        errors.append(_error("SERP_VALIDATION_REQUIRED", "candidate.serp_status", "SERP_NOT_CHECKED cannot publish"))
    for field in ("candidate_hash", "review_hash", "content_hash"):
        if not _valid_hash(bridge.get(field)):
            errors.append(_error("INVALID_HASH", f"bridge.{field}", "pinned hashes must be SHA-256"))
    for field in ("candidate_revision", "review_revision", "revision"):
        if not _positive_revision(bridge.get(field)):
            errors.append(_error("INVALID_REVISION", f"bridge.{field}", "revision must be positive"))
    if bridge.get("candidate_score") is None or bridge.get("candidate_confidence") is None:
        errors.append(_error("SCORE_CONFIDENCE_REQUIRED", "bridge", "Score and Confidence are required read-only projections"))
    if bridge.get("text_provenance") != "HUMAN_AUTHORED" or not isinstance(bridge.get("text"), str) or not bridge.get("text", "").strip():
        errors.append(_error("RECOMMENDATION_TEXT_REQUIRED", "bridge.text", "canary requires human-authored approved recommendation text"))
    return errors, candidate, review, bridge


class RecommendationCanaryWriter:
    """Plan and execute one synthetic Recommendation canary operation."""

    def __init__(self, *, binding: Mapping[str, Any] | GoogleSheetsTargetBinding, audit_store: Optional[RecommendationAuditStore], idempotency_store: Optional[CanaryIdempotencyStore], operational_owner_ref: str = "owner://project", rollback_owner_ref: str = "owner://project", kill_switch_authority_ref: str = "owner://project", observation_period: str = "1 business day") -> None:
        self.binding = binding if isinstance(binding, GoogleSheetsTargetBinding) else GoogleSheetsTargetBinding.from_mapping(binding)
        self.audit_store = audit_store
        self.idempotency_store = idempotency_store
        self.operational_owner_ref = operational_owner_ref
        self.rollback_owner_ref = rollback_owner_ref
        self.kill_switch_authority_ref = kill_switch_authority_ref
        self.observation_period = observation_period

    def run(self, operations: Sequence[Mapping[str, Any]], *, transport: RecommendationTransport, kill_switch: bool = False, release_id: str = "REL_CANARY_UAT", operation_timestamp: str = "2026-09-16T09:00:00+08:00") -> CanaryResult:
        errors = _validate_binding(self.binding)
        if kill_switch:
            errors.append(_error("KILL_SWITCH_ENABLED", "kill_switch", "kill switch blocks the operation before transport"))
        if not isinstance(operations, Sequence) or isinstance(operations, (str, bytes)):
            errors.append(_error("OPERATIONS_INVALID", "operations", "operations must be a sequence"))
            return _result("BLOCKED", errors)
        if len(operations) == 0:
            return _result("BLOCKED", [_error("NO_OPERATION", "operations", "no Recommendation operation is eligible")])
        if len(operations) > 1:
            return _result("BLOCKED", [_error("BLOCKED_OPERATION_LIMIT", "operations", "Phase 1 allows exactly one operation")])
        operation = operations[0]
        if not isinstance(operation, Mapping):
            return _result("BLOCKED", [_error("OPERATIONS_INVALID", "operations[0]", "operation must be an object")])
        if errors:
            return _result("BLOCKED", errors)
        sensitive_errors = _canary_sensitive_errors(operation)
        if sensitive_errors:
            return _result("BLOCKED", sensitive_errors)
        trusted = operation.get("trusted_review_context")
        eligibility_errors, candidate, review, bridge = _eligibility(operation, trusted)
        errors.extend(eligibility_errors)
        if errors:
            return _result("BLOCKED", errors)
        operation_id = operation.get("operation_id")
        if _text_ref(operation_id, "operation_id"):
            return _result("BLOCKED", [_text_ref(operation_id, "operation_id")])
        if _text_ref(release_id, "release_id"):
            return _result("BLOCKED", [_text_ref(release_id, "release_id")])
        now_error = _safe_datetime(operation_timestamp)
        if now_error:
            return _result("BLOCKED", [now_error])
        recommendation_id = str(bridge["recommendation_id"])
        payload = {
            "recommendation_id": recommendation_id,
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
            "created_at": operation_timestamp,
        }
        unexpected = set(operation.get("payload_overrides", {})) - set(ALLOWED_FIELDS)
        if unexpected or operation.get("protected_field_mutation"):
            return _result("BLOCKED", [_error("PROTECTED_FIELD_MUTATION", "payload_overrides", "protected or non-allowlisted fields cannot be changed")], payload=payload)
        payload_hash = _hash(payload, exclude=("semantic_hash", "created_at"))
        payload["semantic_hash"] = payload_hash
        key = idempotency_key(writer_id=WRITER_ID, target_binding_ref=self.binding.binding_id, recommendation_id=recommendation_id, candidate_revision=bridge["candidate_revision"], review_revision=bridge["review_revision"], bridge_revision=bridge["revision"], semantic_hash=payload_hash)
        if self.idempotency_store is not None:
            idempotency_state = self.idempotency_store.reconcile(key, payload_hash)
            if idempotency_state == "ALREADY_APPLIED":
                return _result("CANARY_COMPLETE", [], payload=payload, reconciliation="ALREADY_APPLIED")
            if idempotency_state == "IDEMPOTENCY_CONFLICT":
                return _result("BLOCKED", [_error("IDEMPOTENCY_CONFLICT", "idempotency_key", "same key has a different payload hash")], payload=payload, reconciliation=idempotency_state)
        intent = WriteIntent(operation_id=str(operation_id), idempotency_key=key, writer_id=WRITER_ID, principal_ref=self.binding.writer_principal_ref, target_binding_ref=self.binding.binding_id, recommendation_id=recommendation_id, candidate_revision=bridge["candidate_revision"], review_revision=bridge["review_revision"], bridge_revision=bridge["revision"], planned_fields=tuple(ALLOWED_FIELDS), payload_hash=payload_hash, created_at=operation_timestamp)
        transport_result = transport.write(self.binding, intent, payload)
        if transport_result.state == "SUCCEEDED":
            readback = transport.readback(self.binding, str(operation_id))
            readback_state = "READBACK_MATCHED" if readback == payload else "READBACK_MISMATCH"
            reconciliation = None
            final_state = "CANARY_COMPLETE" if readback_state == "READBACK_MATCHED" else "READBACK_MISMATCH"
        elif transport_result.state == "UNKNOWN":
            readback = transport.readback(self.binding, str(operation_id))
            if readback == payload:
                readback_state, reconciliation, final_state = "READBACK_MATCHED", "RECONCILED_SUCCESS", "CANARY_COMPLETE"
            elif readback is None:
                readback_state, reconciliation, final_state = "READBACK_ABSENT", "SAFE_TO_RETRY_REQUIRES_HUMAN_AUTHORIZATION", "BLOCKED"
            else:
                readback_state, reconciliation, final_state = "READBACK_MISMATCH", "RECONCILIATION_CONFLICT", "BLOCKED"
        else:
            readback_state, reconciliation, final_state = "NOT_ATTEMPTED", None, "BLOCKED"
        receipt = None
        receipt_data = {
            "operation_id": operation_id, "release_id": release_id, "writer_id": WRITER_ID,
            "principal_ref": self.binding.writer_principal_ref, "target_binding_ref": self.binding.binding_id,
            "recommendation_id": recommendation_id, "candidate_id": candidate["candidate_id"],
            "candidate_revision": bridge["candidate_revision"], "candidate_hash": bridge["candidate_hash"],
            "review_id": bridge["review_id"], "review_revision": bridge["review_revision"], "review_hash": bridge["review_hash"],
            "bridge_id": bridge["bridge_id"], "bridge_revision": bridge["revision"], "bridge_hash": bridge["content_hash"],
            "idempotency_key": key, "write_intent_hash": _hash(intent.as_dict()),
            "transport_state": transport_result.state, "readback_state": readback_state,
            "reconciliation_state": reconciliation, "final_state": final_state,
            "production_mutation_count": 0, "started_at": operation_timestamp, "completed_at": operation_timestamp,
            "target_tab": self.binding.tab_name, "semantic_hash": payload_hash,
        }
        if self.audit_store is None:
            return _result("BLOCKED", [_error("AUDIT_UNAVAILABLE", "audit_store", "persistent audit receipt is required")], payload=payload, intent=intent, reconciliation=reconciliation, transport=transport_result.state, readback=readback_state)
        try:
            receipt = self.audit_store.append(receipt_data)
        except Exception:
            return _result("BLOCKED", [_error("AUDIT_PERSISTENCE_FAILED", "audit_store", "audit receipt could not be persisted")], payload=payload, intent=intent, reconciliation=reconciliation, transport=transport_result.state, readback=readback_state)
        if self.idempotency_store is not None and final_state == "CANARY_COMPLETE":
            self.idempotency_store.record(key, payload_hash)
        return _result(final_state, [], payload=payload, intent=intent, receipt=receipt, reconciliation=reconciliation, transport=transport_result.state, readback=readback_state)


def validate_canary_contract(value: Mapping[str, Any]) -> ValidationResult:
    """Validate the proposal contract without approving or activating it."""

    errors: list[ValidationError] = []
    if not isinstance(value, Mapping):
        return ValidationResult(errors=[_error("SCHEMA_INVALID", "$", "canary contract must be an object")])
    if value.get("x-proposal-status") != PROPOSAL_STATUS:
        errors.append(_error("CONTRACT_NOT_APPROVED", "x-proposal-status", "canary contract remains a proposal"))
    if value.get("x-production-activation") is not False:
        errors.append(_error("PRODUCTION_DISABLED", "x-production-activation", "canary writer cannot activate production"))
    errors.extend(_canary_sensitive_errors(value))
    return ValidationResult(errors=errors)


__all__ = [
    "ALLOWED_FIELDS", "PROTECTED_FIELDS", "TARGET_TAB", "WRITER_ID",
    "CanaryIdempotencyStore", "CanaryResult", "GoogleSheetsTargetBinding", "RecommendationAuditStore",
    "RecommendationCanaryWriter", "RecommendationTransport", "SyntheticRecommendationTransport",
    "TransportResult", "WriteIntent", "idempotency_key", "validate_canary_contract",
]
