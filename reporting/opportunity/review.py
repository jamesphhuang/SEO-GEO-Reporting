"""Offline, append-only human review decisions for WP10.

Review is a separate decision layer.  It never mutates a Candidate, Evidence,
GA4, SERP, or GEO record and it does not write a production destination.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from .proposal_validation import ValidationError, ValidationResult
from .store.errors import ImmutableStoreError
from .store.serialization import canonical_json, canonical_line, content_hash


CONTRACT_VERSION = "human_review.v1.proposal"
RULE_VERSION = "human-review-proposal-1"
RECORD_TYPE = "HUMAN_REVIEW"
DECISIONS = frozenset({"APPROVE", "REJECT", "NEEDS_MORE_EVIDENCE", "DEFER", "RETURN_FOR_REVIEW"})
HUMAN_ACTOR_TYPE = "HUMAN"
FORBIDDEN_ACTORS = frozenset({"SYSTEM", "AI", "LLM", "AUTO", "RULE_ENGINE", "ENGINE"})
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_HASH = re.compile(r"^[a-f0-9]{64}$")


class ReviewInputError(ValueError):
    """Raised when a human review cannot be safely recorded."""

    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


def _hash(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        raise ReviewInputError("INVALID_DATETIME", f"{field} must be ISO-8601 text", field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewInputError("INVALID_DATETIME", f"{field} must be ISO-8601 text", field) from exc
    if parsed.tzinfo is None:
        raise ReviewInputError("NAIVE_DATETIME", f"{field} must include a timezone", field)
    return parsed


def _pin(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewInputError("INVALID_EVIDENCE_PIN", f"{field} must be a mapping", field)
    evidence_id, revision, evidence_hash = value.get("evidence_id"), value.get("revision"), value.get("content_hash")
    if not isinstance(evidence_id, str) or not _SAFE_REF.fullmatch(evidence_id):
        raise ReviewInputError("INVALID_EVIDENCE_ID", f"{field}.evidence_id must be an opaque reference", field)
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ReviewInputError("INVALID_EVIDENCE_REVISION", f"{field}.revision must be positive", field)
    if not isinstance(evidence_hash, str) or not _HASH.fullmatch(evidence_hash):
        raise ReviewInputError("INVALID_EVIDENCE_HASH", f"{field}.content_hash must be SHA-256", field)
    return {"evidence_id": evidence_id, "revision": revision, "content_hash": evidence_hash}


def _pins(values: Any, field: str) -> list[dict[str, Any]]:
    if values is None:
        return []
    if not isinstance(values, (list, tuple)):
        raise ReviewInputError("INVALID_EVIDENCE_REFS", f"{field} must be a list", field)
    result = [_pin(value, f"{field}[{index}]") for index, value in enumerate(values)]
    keys = [(item["evidence_id"], item["revision"]) for item in result]
    if len(keys) != len(set(keys)):
        raise ReviewInputError("DUPLICATE_EVIDENCE_REFERENCE", f"{field} must contain unique revisions", field)
    return result


def _diagnostic_pin(value: Any, field: str) -> Optional[dict[str, Any]]:
    if value is None:
        return None
    return _pin(value, field)


def _actor(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ReviewInputError("MISSING_HUMAN_ACTOR", "reviewer must identify an explicit human actor", "reviewer")
    actor_type = str(value.get("actor_type", "")).upper()
    actor_ref = value.get("actor_ref", value.get("reviewer_id"))
    if actor_type != HUMAN_ACTOR_TYPE or not isinstance(actor_ref, str) or not _SAFE_REF.fullmatch(actor_ref):
        raise ReviewInputError("INVALID_HUMAN_ACTOR", "reviewer must use an opaque HUMAN actor reference", "reviewer")
    actor_upper = actor_ref.upper()
    forbidden_token = re.compile(r"(?:^|[_:/.\-])(SYSTEM|AI|LLM|AUTO|RULE_ENGINE)(?:$|[_:/.\-])")
    if actor_upper in FORBIDDEN_ACTORS or forbidden_token.search(actor_upper):
        raise ReviewInputError("FORBIDDEN_ACTOR", "system or AI identities cannot approve a candidate", "reviewer")
    if value.get("authenticated") is not True:
        raise ReviewInputError("HUMAN_AUTHENTICATION_REQUIRED", "human identity must be explicitly authenticated by the review surface", "reviewer.authenticated")
    identity_source = str(value.get("identity_source", "")).upper()
    if not identity_source or identity_source in FORBIDDEN_ACTORS:
        raise ReviewInputError("INVALID_IDENTITY_SOURCE", "identity_source must describe a review surface", "reviewer.identity_source")
    return {"actor_type": HUMAN_ACTOR_TYPE, "actor_ref": actor_ref, "authenticated": True, "identity_source": identity_source}


def _candidate(value: Any) -> dict[str, Any]:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if isinstance(value, Mapping) and isinstance(value.get("candidate"), Mapping):
        value = value["candidate"]
    if not isinstance(value, Mapping):
        raise ReviewInputError("INVALID_CANDIDATE", "candidate must be a mapping", "candidate")
    result = copy.deepcopy(dict(value))
    candidate_id = result.get("candidate_id", result.get("opportunity_id"))
    revision = result.get("revision", result.get("candidate_revision"))
    candidate_hash = result.get("content_hash", result.get("candidate_hash"))
    if not isinstance(candidate_id, str) or not _SAFE_REF.fullmatch(candidate_id):
        raise ReviewInputError("INVALID_CANDIDATE_ID", "candidate_id must be an opaque reference", "candidate.candidate_id")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
        raise ReviewInputError("INVALID_CANDIDATE_REVISION", "candidate revision must be positive", "candidate.revision")
    if not isinstance(candidate_hash, str) or not _HASH.fullmatch(candidate_hash):
        raise ReviewInputError("MISSING_CANDIDATE_HASH", "candidate content_hash is required", "candidate.content_hash")
    calculated = content_hash(result)
    if calculated != candidate_hash:
        raise ReviewInputError("CANDIDATE_HASH_MISMATCH", "candidate content_hash does not match the pinned revision", "candidate.content_hash")
    result["candidate_id"] = candidate_id
    result["revision"] = revision
    result["content_hash"] = candidate_hash
    return result


def _review_id(candidate_id: str, candidate_revision: int) -> str:
    return "REV_" + _hash({"candidate_id": candidate_id, "candidate_revision": candidate_revision, "stream": "human-review"})[:24]


def _semantic_hash(record: Mapping[str, Any]) -> str:
    value = {key: item for key, item in record.items() if key not in {"content_hash", "created_at", "updated_at"}}
    return _hash(value)


@dataclass(frozen=True)
class HumanReviewInput:
    candidate: Mapping[str, Any]
    reviewer: Mapping[str, Any]
    decision: str
    reason_code: str
    decision_at: str
    notes: Optional[str] = None
    review_id: Optional[str] = None
    revision: int = 1
    candidate_evidence_refs: Optional[Sequence[Mapping[str, Any]]] = None
    ga4_diagnostic_ref: Optional[Mapping[str, Any]] = None
    serp_validation_ref: Optional[Mapping[str, Any]] = None
    geo_diagnostic_ref: Optional[Mapping[str, Any]] = None
    preview_semantic_hash: Optional[str] = None
    conflict_adjudication_ref: Optional[str] = None
    policy_version: str = RULE_VERSION


@dataclass
class HumanReviewResult:
    review: Optional[dict[str, Any]]
    validation: ValidationResult
    persisted: bool = False
    persistence_error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.validation.is_valid and self.review is not None

    def as_dict(self) -> dict[str, Any]:
        return {"review": copy.deepcopy(self.review), "validation": self.validation.as_dict(), "persisted": self.persisted, "persistence_error": self.persistence_error}


def create_human_review(value: HumanReviewInput | Mapping[str, Any] | Any, *, reviewer: Optional[Mapping[str, Any]] = None, decision: Optional[str] = None, reason_code: Optional[str] = None, decision_at: Optional[str] = None, notes: Optional[str] = None, review_id: Optional[str] = None, revision: Optional[int] = None, candidate_evidence_refs: Optional[Sequence[Mapping[str, Any]]] = None, ga4_diagnostic_ref: Optional[Mapping[str, Any]] = None, serp_validation_ref: Optional[Mapping[str, Any]] = None, geo_diagnostic_ref: Optional[Mapping[str, Any]] = None, preview_semantic_hash: Optional[str] = None, conflict_adjudication_ref: Optional[str] = None, policy_version: Optional[str] = None, review_store: Optional["HumanReviewStore"] = None, persist: bool = False) -> HumanReviewResult:
    if isinstance(value, HumanReviewInput):
        raw = {"candidate": value.candidate, "reviewer": value.reviewer, "decision": value.decision, "reason_code": value.reason_code, "decision_at": value.decision_at, "notes": value.notes, "review_id": value.review_id, "revision": value.revision, "candidate_evidence_refs": value.candidate_evidence_refs, "ga4_diagnostic_ref": value.ga4_diagnostic_ref, "serp_validation_ref": value.serp_validation_ref, "geo_diagnostic_ref": value.geo_diagnostic_ref, "preview_semantic_hash": value.preview_semantic_hash, "conflict_adjudication_ref": value.conflict_adjudication_ref, "policy_version": value.policy_version}
    elif isinstance(value, Mapping):
        # A bare Candidate mapping is the common call shape. Treat it as the
        # candidate payload unless it already carries the review envelope.
        if "candidate" in value:
            raw = dict(value)
        elif "candidate_id" in value or "opportunity_id" in value:
            raw = {"candidate": value}
        else:
            raw = dict(value)
    else:
        raw = {"candidate": value}
    for key, supplied in (("reviewer", reviewer), ("decision", decision), ("reason_code", reason_code), ("decision_at", decision_at), ("notes", notes), ("review_id", review_id), ("revision", revision), ("candidate_evidence_refs", candidate_evidence_refs), ("ga4_diagnostic_ref", ga4_diagnostic_ref), ("serp_validation_ref", serp_validation_ref), ("geo_diagnostic_ref", geo_diagnostic_ref), ("preview_semantic_hash", preview_semantic_hash), ("conflict_adjudication_ref", conflict_adjudication_ref), ("policy_version", policy_version)):
        if supplied is not None:
            raw[key] = supplied
    try:
        candidate = _candidate(raw.get("candidate"))
        actor = _actor(raw.get("reviewer"))
        decision_value = str(raw.get("decision", "")).upper()
        if decision_value not in DECISIONS:
            raise ReviewInputError("INVALID_DECISION", "unsupported human review decision", "decision")
        reason = raw.get("reason_code")
        if not isinstance(reason, str) or not _SAFE_REF.fullmatch(reason):
            raise ReviewInputError("INVALID_REASON_CODE", "reason_code must be an opaque reference", "reason_code")
        decision_value_at = raw.get("decision_at")
        _parse_datetime(decision_value_at, "decision_at")
        created_at = raw.get("created_at", decision_value_at)
        created = _parse_datetime(created_at, "created_at")
        decided = _parse_datetime(decision_value_at, "decision_at")
        if created > decided:
            raise ReviewInputError("INVALID_DATE_ORDER", "created_at must not be after decision_at")
        revision = raw.get("revision", 1)
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 1:
            raise ReviewInputError("INVALID_REVIEW_REVISION", "review revision must be positive", "revision")
        rid = raw.get("review_id") or _review_id(candidate["candidate_id"], candidate["revision"])
        if not isinstance(rid, str) or not _SAFE_REF.fullmatch(rid):
            raise ReviewInputError("INVALID_REVIEW_ID", "review_id must be an opaque reference", "review_id")
        note = raw.get("notes")
        if note is not None and (not isinstance(note, str) or len(note) > 4000):
            raise ReviewInputError("INVALID_REVIEW_NOTES", "notes must be short human-authored text", "notes")
        preview_hash = raw.get("preview_semantic_hash")
        if preview_hash is not None and (not isinstance(preview_hash, str) or not _HASH.fullmatch(preview_hash)):
            raise ReviewInputError("INVALID_PREVIEW_HASH", "preview_semantic_hash must be SHA-256", "preview_semantic_hash")
        conflict_ref = raw.get("conflict_adjudication_ref")
        if conflict_ref is not None and (not isinstance(conflict_ref, str) or not _SAFE_REF.fullmatch(conflict_ref)):
            raise ReviewInputError("INVALID_ADJUDICATION_REF", "conflict_adjudication_ref must be opaque", "conflict_adjudication_ref")
        record: dict[str, Any] = {
            "record_type": RECORD_TYPE,
            "contract_version": CONTRACT_VERSION,
            "review_id": rid,
            "revision": revision,
            "supersedes_review_revision": revision - 1 if revision > 1 else None,
            "candidate_id": candidate["candidate_id"],
            "candidate_revision": candidate["revision"],
            "candidate_hash": candidate["content_hash"],
            "reviewer_id": actor["actor_ref"],
            "reviewer": actor,
            "authenticated_human": True,
            "decision": decision_value,
            "reason_code": reason,
            "notes": note,
            "notes_provenance": "HUMAN_AUTHORED" if note else "NOT_PROVIDED",
            "candidate_evidence_refs": _pins(raw.get("candidate_evidence_refs", candidate.get("evidence_refs", [])), "candidate_evidence_refs"),
            "ga4_diagnostic_ref": _diagnostic_pin(raw.get("ga4_diagnostic_ref"), "ga4_diagnostic_ref"),
            "serp_validation_ref": _diagnostic_pin(raw.get("serp_validation_ref"), "serp_validation_ref"),
            "geo_diagnostic_ref": _diagnostic_pin(raw.get("geo_diagnostic_ref"), "geo_diagnostic_ref"),
            "preview_semantic_hash": preview_hash,
            "conflict_adjudication_ref": conflict_ref,
            "policy_version": str(raw.get("policy_version", RULE_VERSION)),
            "created_at": created_at,
            "decision_at": decision_value_at,
        }
        record["content_hash"] = _semantic_hash(record)
        validation = validate_human_review(record)
        if validation.is_valid and persist and review_store is not None:
            try:
                stored = review_store.append_review(record)
                record = stored
                return HumanReviewResult(record, validation, persisted=True)
            except Exception as exc:
                return HumanReviewResult(record, validation, persisted=False, persistence_error=str(exc))
        return HumanReviewResult(record if validation.is_valid else None, validation)
    except ReviewInputError as exc:
        return HumanReviewResult(None, ValidationResult(errors=[ValidationError(exc.code, exc.field, str(exc))]))
    except Exception as exc:
        return HumanReviewResult(None, ValidationResult(errors=[ValidationError("INVALID_REVIEW_INPUT", "record", str(exc))]))


def validate_human_review(payload: Any, *, candidate_store: Any = None, evidence_store: Any = None) -> ValidationResult:
    errors: list[ValidationError] = []
    if not isinstance(payload, Mapping):
        return ValidationResult(errors=[ValidationError("SCHEMA_VIOLATION", "$", "human review must be an object")])
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        schema_path = Path(__file__).resolve().parents[2] / "contracts/human_review.v1.proposal.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors.extend(ValidationError("SCHEMA_VIOLATION", ".".join(map(str, item.absolute_path)) or "$", "human review violates proposal schema", rule=str(item.validator)) for item in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload))
    except Exception as exc:
        errors.append(ValidationError("SCHEMA_VALIDATION_ERROR", "$", str(exc)))
    if payload.get("record_type") != RECORD_TYPE:
        errors.append(ValidationError("INVALID_RECORD_TYPE", "record_type", "record must be HUMAN_REVIEW"))
    try:
        actor = _actor(payload.get("reviewer"))
        if payload.get("reviewer_id") != actor["actor_ref"]:
            errors.append(ValidationError("ACTOR_REFERENCE_MISMATCH", "reviewer_id", "reviewer_id must match the human actor"))
    except ReviewInputError as exc:
        errors.append(ValidationError(exc.code, exc.field, str(exc)))
    if payload.get("decision") not in DECISIONS:
        errors.append(ValidationError("INVALID_DECISION", "decision", "unknown review decision"))
    try:
        if payload.get("content_hash") != _semantic_hash(payload):
            errors.append(ValidationError("CONTENT_HASH_MISMATCH", "content_hash", "review content hash mismatch"))
    except Exception as exc:
        errors.append(ValidationError("CONTENT_HASH_ERROR", "content_hash", str(exc)))
    for field_name in ("created_at", "decision_at"):
        try:
            _parse_datetime(payload.get(field_name), field_name)
        except ReviewInputError as exc:
            errors.append(ValidationError(exc.code, exc.field, str(exc)))
    for field_name in ("candidate_evidence_refs",):
        try:
            pins = _pins(payload.get(field_name), field_name)
            if evidence_store is not None:
                for pin in pins:
                    evidence_store.resolve_reference(pin["evidence_id"], pin["revision"], pin["content_hash"])
        except (ReviewInputError, Exception) as exc:
            code = getattr(exc, "code", "EVIDENCE_PIN_INVALID")
            errors.append(ValidationError(code, field_name, str(exc)))
    if candidate_store is not None:
        try:
            candidate = candidate_store.get_candidate(payload.get("candidate_id"), payload.get("candidate_revision"))
            if candidate is None or candidate.get("content_hash") != payload.get("candidate_hash"):
                errors.append(ValidationError("CANDIDATE_PIN_INVALID", "candidate_hash", "review does not resolve the exact candidate revision"))
        except Exception as exc:
            errors.append(ValidationError("CANDIDATE_PIN_INVALID", "candidate_hash", str(exc)))
    return ValidationResult(errors=errors)


class HumanReviewStore:
    """Append-only local JSONL store for human review decision revisions."""

    def __init__(self, root: str | os.PathLike[str], *, candidate_store: Any = None, evidence_store: Any = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "human_reviews.jsonl"
        self.candidate_store = candidate_store
        self.evidence_store = evidence_store
        self._records: dict[tuple[str, int], dict[str, Any]] = {}
        self._load()

    def _prepare(self, record: Mapping[str, Any]) -> dict[str, Any]:
        value = copy.deepcopy(dict(record))
        calculated = _semantic_hash(value)
        if value.get("content_hash") is not None and value["content_hash"] != calculated:
            raise ImmutableStoreError("HASH_MISMATCH", "human review content hash mismatch")
        value["content_hash"] = calculated
        return value

    def _validate(self, record: Mapping[str, Any]) -> None:
        result = validate_human_review(record, candidate_store=self.candidate_store, evidence_store=self.evidence_store)
        if not result.is_valid:
            raise ImmutableStoreError("INVALID_REVIEW", result.errors[0].message)

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = self._prepare(json.loads(line))
            self._validate(row)
            key = (row["review_id"], row["revision"])
            if key in self._records:
                raise ImmutableStoreError("STORE_CORRUPTION", "duplicate human review revision")
            self._records[key] = row
        for review_id in {key[0] for key in self._records}:
            revisions = sorted(revision for current_id, revision in self._records if current_id == review_id)
            if revisions != list(range(1, len(revisions) + 1)):
                raise ImmutableStoreError("STORE_CORRUPTION", "human review revisions must be contiguous")
            for revision in revisions[1:]:
                row = self._records[(review_id, revision)]
                if row.get("supersedes_review_revision") != revision - 1:
                    raise ImmutableStoreError("STORE_CORRUPTION", "human review supersedes chain is invalid")

    def append_review(self, record: Mapping[str, Any]) -> dict[str, Any]:
        prepared = self._prepare(record)
        self._validate(prepared)
        key = (prepared["review_id"], prepared["revision"])
        existing = self._records.get(key)
        if existing is not None:
            if existing["content_hash"] == prepared["content_hash"]:
                return {**copy.deepcopy(existing), "idempotent": True}
            raise ImmutableStoreError("REVISION_CONFLICT", "same review revision has a different hash")
        revisions = sorted(revision for review_id, revision in self._records if review_id == prepared["review_id"])
        expected = revisions[-1] + 1 if revisions else 1
        if prepared["revision"] != expected:
            raise ImmutableStoreError("REVISION_GAP", "review revisions must append contiguously")
        if prepared["revision"] == 1 and prepared.get("supersedes_review_revision") is not None:
            raise ImmutableStoreError("INVALID_SUPERSEDES", "review revision 1 cannot supersede")
        if prepared["revision"] > 1 and prepared.get("supersedes_review_revision") != prepared["revision"] - 1:
            raise ImmutableStoreError("INVALID_SUPERSEDES", "review revision must supersede the previous revision")
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(canonical_line(prepared))
            handle.flush()
            os.fsync(handle.fileno())
        self._records[key] = copy.deepcopy(prepared)
        return copy.deepcopy(prepared)

    def get_review(self, review_id: str, revision: Optional[int] = None) -> Optional[dict[str, Any]]:
        rows = self.history(review_id)
        if revision is None:
            return rows[-1] if rows else None
        return next((row for row in rows if row["revision"] == revision), None)

    def history(self, review_id: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._records[key]) for key in sorted(self._records) if key[0] == review_id]


__all__ = [
    "CONTRACT_VERSION", "RULE_VERSION", "RECORD_TYPE", "DECISIONS", "ReviewInputError",
    "HumanReviewInput", "HumanReviewResult", "create_human_review", "validate_human_review", "HumanReviewStore",
]
