"""Offline recommendation bridge gated by an exact human review revision."""

from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional

from .proposal_validation import ValidationError, ValidationResult
from .review import DECISIONS, ReviewInputError, _candidate, _diagnostic_pin, _hash, _pins, _semantic_hash, validate_human_review
from .store.errors import ImmutableStoreError
from .store.serialization import canonical_line


CONTRACT_VERSION = "recommendation_bridge.v1.proposal"
RULE_VERSION = "recommendation-bridge-proposal-1"
RECORD_TYPE = "RECOMMENDATION_BRIDGE"
TARGET_ENVIRONMENTS = frozenset({"UAT", "PREVIEW"})
# Keep the WP5 enum and the legacy labels still present in WP9 synthetic
# projections.  The bridge never invents a new action; it only carries one of
# these already-persisted Candidate values forward.
CANDIDATE_ACTIONS = frozenset({
    "UPDATE_EXISTING", "OPTIMIZE_EXISTING", "REFRESH_CONTENT",
    "SERP_SNIPPET_OPTIMIZE", "TECHNICAL_FIX", "FIX_TECHNICAL",
    "INTERNAL_LINK", "GEO_ENHANCE", "AUTHORITY_BUILD", "CREATE_NEW",
    "CONSOLIDATE", "MONITOR", "DO_NOTHING",
})
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_HASH = re.compile(r"^[a-f0-9]{64}$")


class RecommendationBridgeError(ValueError):
    """Raised by callers that ask for a bridge from an unauthorized transition."""

    def __init__(self, code: str, message: str, field: str = "record") -> None:
        super().__init__(message)
        self.code = code
        self.field = field


@dataclass
class RecommendationBridgeResult:
    bridge: Optional[dict[str, Any]]
    validation: ValidationResult
    persisted: bool = False
    persistence_error: Optional[str] = None

    @property
    def is_valid(self) -> bool:
        return self.validation.is_valid and self.bridge is not None

    def as_dict(self) -> dict[str, Any]:
        return {"bridge": copy.deepcopy(self.bridge), "validation": self.validation.as_dict(), "persisted": self.persisted, "persistence_error": self.persistence_error}


def _review_payload(value: Any) -> dict[str, Any]:
    if hasattr(value, "as_dict"):
        value = value.as_dict()
    if isinstance(value, Mapping) and isinstance(value.get("review"), Mapping):
        value = value["review"]
    if not isinstance(value, Mapping):
        raise RecommendationBridgeError("INVALID_REVIEW", "review must be a mapping", "review")
    result = copy.deepcopy(dict(value))
    validation = validate_human_review(result)
    if not validation.is_valid:
        raise RecommendationBridgeError("INVALID_REVIEW", validation.errors[0].message, validation.errors[0].field)
    return result


def _bridge_id(candidate_id: str) -> str:
    return "BRIDGE_" + _hash({"candidate_id": candidate_id, "stream": "recommendation-bridge"})[:24]


def _review_hash(review: Mapping[str, Any]) -> str:
    value = {key: item for key, item in review.items() if key not in {"content_hash", "created_at", "updated_at"}}
    return _hash(value)


def _error(code: str, field: str, message: str) -> RecommendationBridgeResult:
    return RecommendationBridgeResult(None, ValidationResult(errors=[ValidationError(code, field, message)]))


def _candidate_action(candidate: Mapping[str, Any]) -> str:
    action = candidate.get("recommended_action", candidate.get("action"))
    if not isinstance(action, str) or action not in CANDIDATE_ACTIONS:
        raise RecommendationBridgeError("INVALID_CANDIDATE_ACTION", "bridge must use the existing Candidate Action enum", "candidate.recommended_action")
    return action


def _candidate_score(candidate: Mapping[str, Any]) -> Any:
    score = candidate.get("opportunity_score", candidate.get("score"))
    if isinstance(score, Mapping):
        score = score.get("value", score.get("total"))
    return score


def _conflicts(candidate: Mapping[str, Any]) -> list[str]:
    values = []
    for field in ("conflicts", "conflicting_evidence_refs", "policy_gaps", "capability_gaps"):
        raw = candidate.get(field) or []
        if isinstance(raw, (list, tuple)):
            values.extend(str(item) for item in raw)
    return sorted(set(values))


def build_recommendation_bridge(candidate: Any, review: Any, *, target_env: str = "UAT", destination_id: str = "UAT_RECOMMENDATIONS", human_text: Optional[str] = None, text_provenance: Optional[str] = None, bridge_id: Optional[str] = None, revision: Optional[int] = None, review_store: Any = None, bridge_store: Optional["RecommendationBridgeStore"] = None, persist: bool = False, policy_version: str = RULE_VERSION) -> RecommendationBridgeResult:
    """Create a proposal-only bridge when an exact human APPROVE is valid."""

    try:
        candidate_value = _candidate(candidate)
        review_value = _review_payload(review)
        if review_value["decision"] != "APPROVE":
            return _error("HUMAN_APPROVAL_REQUIRED", "review.decision", "only an explicit human APPROVE can create a recommendation bridge")
        if review_value["candidate_id"] != candidate_value["candidate_id"] or review_value["candidate_revision"] != candidate_value["revision"] or review_value["candidate_hash"] != candidate_value["content_hash"]:
            return _error("CANDIDATE_REVISION_MISMATCH", "candidate", "review must bind the exact Candidate revision and hash")
        if review_store is not None:
            current = review_store.get_review(review_value["review_id"])
            if current is None or current["revision"] != review_value["revision"] or current["content_hash"] != review_value["content_hash"]:
                return _error("SUPERSEDED_REVIEW", "review.revision", "superseded review cannot be used as current approval")
        target_env = str(target_env).upper()
        if target_env not in TARGET_ENVIRONMENTS:
            return _error("PRODUCTION_DESTINATION_FORBIDDEN", "target_env", "WP10 bridge is UAT/preview only")
        if not isinstance(destination_id, str) or not _SAFE_REF.fullmatch(destination_id) or not destination_id.upper().startswith(("UAT_", "PREVIEW_")):
            return _error("DESTINATION_NOT_ALLOWLISTED", "destination_id", "bridge destination must be an offline UAT/preview destination")
        action = _candidate_action(candidate_value)
        score = _candidate_score(candidate_value)
        if score is None:
            return _error("MISSING_SCORE", "candidate.score", "approved bridge requires the existing WP5 score; it is never recomputed")
        confidence = str(candidate_value.get("confidence", "NOT_ASSESSABLE"))
        if confidence not in {"MEDIUM", "HIGH"}:
            return _error("INSUFFICIENT_CONFIDENCE", "candidate.confidence", "approved bridge requires MEDIUM or HIGH evidence confidence")
        validation_state = str(candidate_value.get("validation_state", ""))
        if validation_state != "PASS":
            return _error("VALIDATION_GATE_BLOCKED", "candidate.validation_state", "approved bridge requires validation_state=PASS")
        missing = list(candidate_value.get("missing_evidence_roles", []) or [])
        if missing:
            return _error("MISSING_REQUIRED_EVIDENCE", "candidate.missing_evidence_roles", "missing evidence blocks recommendation bridge creation")
        policy_gaps = list(candidate_value.get("policy_gaps", []) or [])
        if policy_gaps:
            return _error("POLICY_GAP_BLOCKED", "candidate.policy_gaps", "policy gaps require a separately approved policy before a bridge can be created")
        capability_gaps = list(candidate_value.get("capability_gaps", []) or [])
        if capability_gaps:
            return _error("CAPABILITY_GAP_BLOCKED", "candidate.capability_gaps", "capability gaps block recommendation bridge creation")
        stale_roles = list(candidate_value.get("stale_evidence_roles", []) or [])
        if candidate_value.get("stale") is True or str(candidate_value.get("freshness_state", "")).upper() in {"STALE", "FAILED", "NOT_AVAILABLE"} or stale_roles:
            return _error("STALE_EVIDENCE_BLOCKED", "candidate.stale_evidence_roles", "stale or unavailable critical evidence cannot be promoted")
        if str(candidate_value.get("serp_status", "")).upper() == "SERP_NOT_CHECKED":
            return _error("SERP_VALIDATION_REQUIRED", "candidate.serp_status", "SERP_NOT_CHECKED cannot enter a recommendation bridge")
        conflicts = _conflicts(candidate_value)
        if conflicts and not review_value.get("conflict_adjudication_ref"):
            return _error("CONFLICT_ADJUDICATION_REQUIRED", "review.conflict_adjudication_ref", "candidate conflicts require an explicit adjudication reference; approval cannot erase them")
        if review_value.get("candidate_evidence_refs") != candidate_value.get("evidence_refs", []):
            return _error("EVIDENCE_PIN_MISMATCH", "review.candidate_evidence_refs", "review must preserve the exact Candidate evidence pins")
        bridge_revision = revision if revision is not None else review_value["revision"]
        if not isinstance(bridge_revision, int) or isinstance(bridge_revision, bool) or bridge_revision < 1:
            return _error("INVALID_BRIDGE_REVISION", "revision", "bridge revision must be positive")
        bid = bridge_id or _bridge_id(candidate_value["candidate_id"])
        if not isinstance(bid, str) or not _SAFE_REF.fullmatch(bid):
            return _error("INVALID_BRIDGE_ID", "bridge_id", "bridge_id must be opaque")
        if human_text is not None and (not isinstance(human_text, str) or len(human_text) > 4000):
            return _error("INVALID_RECOMMENDATION_TEXT", "human_text", "recommendation text must be short text")
        provenance = text_provenance or ("HUMAN_AUTHORED" if human_text else "DRAFT_ONLY")
        if provenance not in {"HUMAN_AUTHORED", "DRAFT_ONLY", "NOT_PROVIDED"}:
            return _error("INVALID_TEXT_PROVENANCE", "text_provenance", "text must be human-authored or draft-only")
        if provenance == "HUMAN_AUTHORED" and not human_text:
            return _error("MISSING_HUMAN_TEXT", "human_text", "human-authored text is required when declared")
        evidence_refs = copy.deepcopy(review_value.get("candidate_evidence_refs", []))
        bundle_seed = {"candidate_id": candidate_value["candidate_id"], "candidate_revision": candidate_value["revision"], "candidate_hash": candidate_value["content_hash"], "evidence_refs": evidence_refs, "ga4": review_value.get("ga4_diagnostic_ref"), "serp": review_value.get("serp_validation_ref"), "geo": review_value.get("geo_diagnostic_ref")}
        record: dict[str, Any] = {
            "record_type": RECORD_TYPE,
            "contract_version": CONTRACT_VERSION,
            "bridge_id": bid,
            "revision": bridge_revision,
            "supersedes_bridge_revision": bridge_revision - 1 if bridge_revision > 1 else None,
            "candidate_id": candidate_value["candidate_id"],
            "candidate_revision": candidate_value["revision"],
            "candidate_hash": candidate_value["content_hash"],
            "review_id": review_value["review_id"],
            "review_revision": review_value["revision"],
            "review_hash": review_value["content_hash"],
            "reviewer_id": review_value["reviewer_id"],
            "review_decision": review_value["decision"],
            "approval_meaning": "RECOMMENDATION_WORKFLOW_ENTRY_ONLY",
            "target_env": target_env,
            "destination_id": destination_id,
            "recommendation_id": "REC_" + _hash({"candidate_id": candidate_value["candidate_id"], "candidate_revision": candidate_value["revision"], "review_id": review_value["review_id"], "review_revision": review_value["revision"]})[:24],
            "candidate_action": action,
            "candidate_score": copy.deepcopy(score),
            "candidate_confidence": confidence,
            "validation_state": validation_state,
            "target_url": candidate_value.get("target_url"),
            "section": candidate_value.get("section", "gsc"),
            "text": human_text,
            "text_provenance": provenance,
            "status": "BRIDGE_READY",
            "action_status": "NOT_STARTED",
            "evidence_bundle_ref": "EB_" + _hash(bundle_seed)[:24],
            "candidate_evidence_refs": evidence_refs,
            "ga4_diagnostic_ref": copy.deepcopy(review_value.get("ga4_diagnostic_ref")),
            "serp_validation_ref": copy.deepcopy(review_value.get("serp_validation_ref")),
            "geo_diagnostic_ref": copy.deepcopy(review_value.get("geo_diagnostic_ref")),
            "conflicts": conflicts,
            "policy_version": policy_version,
            "next_steps_written": False,
            "production_mutation": False,
            "created_at": review_value["decision_at"],
        }
        record["content_hash"] = _semantic_hash(record)
        validation = validate_recommendation_bridge(record)
        if validation.is_valid and persist and bridge_store is not None:
            try:
                stored = bridge_store.append_bridge(record)
                return RecommendationBridgeResult(stored, validation, persisted=True)
            except Exception as exc:
                return RecommendationBridgeResult(record, validation, persistence_error=str(exc))
        return RecommendationBridgeResult(record if validation.is_valid else None, validation)
    except (ReviewInputError, RecommendationBridgeError) as exc:
        return _error(getattr(exc, "code", "INVALID_BRIDGE_INPUT"), getattr(exc, "field", "record"), str(exc))
    except Exception as exc:
        return _error("INVALID_BRIDGE_INPUT", "record", str(exc))


def validate_recommendation_bridge(payload: Any) -> ValidationResult:
    errors: list[ValidationError] = []
    if not isinstance(payload, Mapping):
        return ValidationResult(errors=[ValidationError("SCHEMA_VIOLATION", "$", "bridge must be an object")])
    try:
        from jsonschema import Draft202012Validator, FormatChecker
        schema_path = Path(__file__).resolve().parents[2] / "contracts/recommendation_bridge.v1.proposal.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        errors.extend(ValidationError("SCHEMA_VIOLATION", ".".join(map(str, item.absolute_path)) or "$", "bridge violates proposal schema", rule=str(item.validator)) for item in Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload))
    except Exception as exc:
        errors.append(ValidationError("SCHEMA_VALIDATION_ERROR", "$", str(exc)))
    if payload.get("target_env") not in TARGET_ENVIRONMENTS:
        errors.append(ValidationError("PRODUCTION_DESTINATION_FORBIDDEN", "target_env", "bridge must remain in UAT/preview"))
    if payload.get("review_decision") != "APPROVE":
        errors.append(ValidationError("HUMAN_APPROVAL_REQUIRED", "review_decision", "bridge requires APPROVE"))
    if payload.get("approval_meaning") != "RECOMMENDATION_WORKFLOW_ENTRY_ONLY":
        errors.append(ValidationError("APPROVAL_MEANING_INVALID", "approval_meaning", "approval is not truth or guarantee"))
    if payload.get("production_mutation") is not False or payload.get("next_steps_written") is not False:
        errors.append(ValidationError("PRODUCTION_BOUNDARY", "production_mutation", "bridge cannot write production Recommendations or Next Steps"))
    if payload.get("candidate_action") not in CANDIDATE_ACTIONS:
        errors.append(ValidationError("INVALID_CANDIDATE_ACTION", "candidate_action", "bridge action must be an existing Candidate Action"))
    if payload.get("candidate_confidence") not in {"MEDIUM", "HIGH"}:
        errors.append(ValidationError("INSUFFICIENT_CONFIDENCE", "candidate_confidence", "bridge must preserve MEDIUM or HIGH confidence"))
    if payload.get("validation_state") != "PASS":
        errors.append(ValidationError("VALIDATION_GATE_BLOCKED", "validation_state", "bridge must preserve validation_state=PASS"))
    try:
        if payload.get("content_hash") != _semantic_hash(payload):
            errors.append(ValidationError("CONTENT_HASH_MISMATCH", "content_hash", "bridge content hash mismatch"))
    except Exception as exc:
        errors.append(ValidationError("CONTENT_HASH_ERROR", "content_hash", str(exc)))
    for field_name in ("candidate_evidence_refs",):
        try:
            _pins(payload.get(field_name), field_name)
        except Exception as exc:
            errors.append(ValidationError(getattr(exc, "code", "EVIDENCE_PIN_INVALID"), field_name, str(exc)))
    if any("next" in str(key).lower() for key in payload if key != "next_steps_written"):
        errors.append(ValidationError("NEXT_STEPS_BOUNDARY", "record", "bridge cannot carry a Next Steps artifact"))
    return ValidationResult(errors=errors)


def project_review_status(candidate: Any, review: Any = None, bridge: Any = None) -> dict[str, Any]:
    """Return a read-only UAT review status projection for a WP9 row."""

    candidate_value = _candidate(candidate)
    review_value = None
    if review is not None:
        try:
            review_value = _review_payload(review)
        except RecommendationBridgeError:
            review_value = None
    bridge_value = None
    if bridge is not None:
        bridge_value = bridge.get("bridge") if isinstance(bridge, Mapping) and isinstance(bridge.get("bridge"), Mapping) else bridge
        if not isinstance(bridge_value, Mapping):
            bridge_value = None
    status = "NOT_REVIEWED" if review_value is None else {
        "APPROVE": "APPROVED",
        "REJECT": "REJECTED",
        "NEEDS_MORE_EVIDENCE": "NEEDS_MORE_EVIDENCE",
        "DEFER": "DEFERRED",
        "RETURN_FOR_REVIEW": "RETURNED_FOR_REVIEW",
    }.get(review_value.get("decision"), "INVALID")
    return {
        "candidate_id": candidate_value["candidate_id"],
        "candidate_revision": candidate_value["revision"],
        "review_status": status,
        "review_id": review_value.get("review_id") if review_value else None,
        "review_revision": review_value.get("revision") if review_value else None,
        "reviewer_id": review_value.get("reviewer_id") if review_value else None,
        "review_decision": review_value.get("decision") if review_value else None,
        "recommendation_bridge_status": "BRIDGE_READY" if bridge_value and bridge_value.get("status") == "BRIDGE_READY" else ("BLOCKED" if review_value else "NOT_REVIEWED"),
        "recommendation_id": bridge_value.get("recommendation_id") if bridge_value else None,
        "next_steps_written": False,
        "read_only_projection": True,
    }


class RecommendationBridgeStore:
    """Append-only local proposal bridge store; never a production writer."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "recommendation_bridges.jsonl"
        self._records: dict[tuple[str, int], dict[str, Any]] = {}
        self._load()

    def _prepare(self, record: Mapping[str, Any]) -> dict[str, Any]:
        value = copy.deepcopy(dict(record))
        calculated = _semantic_hash(value)
        if value.get("content_hash") is not None and value["content_hash"] != calculated:
            raise ImmutableStoreError("HASH_MISMATCH", "bridge content hash mismatch")
        value["content_hash"] = calculated
        return value

    def _validate(self, record: Mapping[str, Any]) -> None:
        result = validate_recommendation_bridge(record)
        if not result.is_valid:
            raise ImmutableStoreError("INVALID_BRIDGE", result.errors[0].message)

    def _load(self) -> None:
        if not self.path.exists():
            return
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line:
                continue
            row = self._prepare(json.loads(line))
            self._validate(row)
            key = (row["bridge_id"], row["revision"])
            if key in self._records:
                raise ImmutableStoreError("STORE_CORRUPTION", "duplicate bridge revision")
            self._records[key] = row
        for bridge_id in {key[0] for key in self._records}:
            revisions = sorted(revision for current_id, revision in self._records if current_id == bridge_id)
            if revisions != list(range(1, len(revisions) + 1)):
                raise ImmutableStoreError("STORE_CORRUPTION", "bridge revisions must be contiguous")
            for revision in revisions[1:]:
                row = self._records[(bridge_id, revision)]
                if row.get("supersedes_bridge_revision") != revision - 1:
                    raise ImmutableStoreError("STORE_CORRUPTION", "bridge supersedes chain is invalid")

    def append_bridge(self, record: Mapping[str, Any]) -> dict[str, Any]:
        prepared = self._prepare(record)
        self._validate(prepared)
        key = (prepared["bridge_id"], prepared["revision"])
        existing = self._records.get(key)
        if existing is not None:
            if existing["content_hash"] == prepared["content_hash"]:
                return {**copy.deepcopy(existing), "idempotent": True}
            raise ImmutableStoreError("REVISION_CONFLICT", "same bridge revision has a different hash")
        revisions = sorted(revision for bridge_id, revision in self._records if bridge_id == prepared["bridge_id"])
        expected = revisions[-1] + 1 if revisions else 1
        if prepared["revision"] != expected:
            raise ImmutableStoreError("REVISION_GAP", "bridge revisions must append contiguously")
        if prepared["revision"] == 1 and prepared.get("supersedes_bridge_revision") is not None:
            raise ImmutableStoreError("INVALID_SUPERSEDES", "bridge revision 1 cannot supersede")
        if prepared["revision"] > 1 and prepared.get("supersedes_bridge_revision") != prepared["revision"] - 1:
            raise ImmutableStoreError("INVALID_SUPERSEDES", "bridge revision must supersede the previous revision")
        with self.path.open("a", encoding="utf-8", newline="") as handle:
            handle.write(canonical_line(prepared))
            handle.flush()
            os.fsync(handle.fileno())
        self._records[key] = copy.deepcopy(prepared)
        return copy.deepcopy(prepared)

    def get_bridge(self, bridge_id: str, revision: Optional[int] = None) -> Optional[dict[str, Any]]:
        rows = self.history(bridge_id)
        if revision is None:
            return rows[-1] if rows else None
        return next((row for row in rows if row["revision"] == revision), None)

    def history(self, bridge_id: str) -> list[dict[str, Any]]:
        return [copy.deepcopy(self._records[key]) for key in sorted(self._records) if key[0] == bridge_id]


__all__ = [
    "CONTRACT_VERSION", "RULE_VERSION", "RECORD_TYPE", "TARGET_ENVIRONMENTS", "CANDIDATE_ACTIONS",
    "RecommendationBridgeError", "RecommendationBridgeResult", "build_recommendation_bridge",
    "validate_recommendation_bridge", "project_review_status", "RecommendationBridgeStore",
]
