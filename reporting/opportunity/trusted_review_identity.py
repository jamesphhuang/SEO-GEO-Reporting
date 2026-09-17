"""Trusted reviewer identity binding for the Phase 1 canary.

The module handles only non-secret, provider-verified identity evidence.  It
does not acquire credentials, verify a raw token, create a HumanReview, or
perform a write.  A provider adapter must supply a typed
``VerifiedProviderIdentity`` after cryptographic token verification.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .store.serialization import canonical_json


BINDING_VERSION = "trusted-review-identity-binding.v1"
PROVIDER = "GOOGLE_WORKSPACE"
ROLE = "RECOMMENDATION_APPROVER"
SCOPE = "PHASE1_CANARY"
WAIVER = "APPROVED_PHASE1_CANARY_ONLY"
ACTIVE_STATUS = "ACTIVE"
PRODUCTION_INHERITANCE = False
AUTOMATIC_SCOPE_EXPANSION = False
VERIFICATION_METHOD = "GOOGLE_OIDC_ID_TOKEN_V1"
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$")
_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9.-]{0,252}[a-z0-9]$")
_SAFE_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}$")
_SENSITIVE_KEY = re.compile(r"(?:token|secret|credential|password|authorization|cookie|email|raw[_-]?(?:sub|subject))", re.I)


class TrustedIdentityError(ValueError):
    """Fail-closed trusted identity input error."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _semantic_hash(value: Mapping[str, Any], *, excluded: set[str]) -> str:
    payload = {key: item for key, item in value.items() if key not in excluded}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _valid_datetime(value: Any) -> bool:
    if not isinstance(value, str) or not _DATETIME.fullmatch(value):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is not None
    except ValueError:
        return False


def reviewer_subject_ref(stable_google_sub: str) -> str:
    """Return the fixed Phase 1 pseudonymous reference for a Google subject."""

    if not isinstance(stable_google_sub, str) or not stable_google_sub or len(stable_google_sub) > 255:
        raise TrustedIdentityError("INVALID_PROVIDER_SUBJECT")
    return hashlib.sha256(
        b"google-workspace-reviewer-v1:" + stable_google_sub.encode("utf-8")
    ).hexdigest()


def _binding_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value[key] for key in (
        "binding_version", "provider", "reviewer_subject_ref", "workspace_domain",
        "role", "scope", "status", "binding_revision", "provider_verification_method",
        "same_person_writer_reviewer", "separation_of_duties_waiver",
        "production_inheritance", "automatic_scope_expansion", "verified_at",
    )}


@dataclass(frozen=True)
class TrustedReviewBinding:
    binding_version: str
    provider: str
    reviewer_subject_ref: str
    workspace_domain: str
    role: str
    scope: str
    status: str
    binding_revision: int
    provider_verification_method: str
    same_person_writer_reviewer: bool
    separation_of_duties_waiver: str | None
    production_inheritance: bool
    automatic_scope_expansion: bool
    verified_at: str
    semantic_hash: str

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "TrustedReviewBinding":
        if not isinstance(value, Mapping):
            raise TrustedIdentityError("BINDING_INVALID")
        if any(_SENSITIVE_KEY.search(str(key)) for key in value):
            raise TrustedIdentityError("BINDING_SENSITIVE_FIELD")
        allowed_fields = {
            "binding_version", "provider", "reviewer_subject_ref", "workspace_domain",
            "role", "scope", "status", "binding_revision", "provider_verification_method",
            "same_person_writer_reviewer", "separation_of_duties_waiver",
            "production_inheritance", "automatic_scope_expansion", "verified_at", "semantic_hash",
        }
        if set(value) - allowed_fields:
            raise TrustedIdentityError("BINDING_UNEXPECTED_FIELD")
        try:
            payload = _binding_payload(value)
        except KeyError as exc:
            raise TrustedIdentityError("BINDING_REQUIRED_FIELD_MISSING") from exc
        if payload["binding_version"] != BINDING_VERSION:
            raise TrustedIdentityError("BINDING_VERSION_MISMATCH")
        if payload["provider"] != PROVIDER:
            raise TrustedIdentityError("BINDING_PROVIDER_INVALID")
        if not isinstance(payload["reviewer_subject_ref"], str) or _SHA256.fullmatch(payload["reviewer_subject_ref"]) is None:
            raise TrustedIdentityError("BINDING_SUBJECT_REF_INVALID")
        if not isinstance(payload["workspace_domain"], str) or _DOMAIN.fullmatch(payload["workspace_domain"]) is None:
            raise TrustedIdentityError("BINDING_DOMAIN_INVALID")
        if payload["role"] != ROLE or payload["scope"] != SCOPE:
            raise TrustedIdentityError("BINDING_ROLE_OR_SCOPE_INVALID")
        if payload["status"] != ACTIVE_STATUS:
            raise TrustedIdentityError("BINDING_NOT_ACTIVE")
        if not isinstance(payload["binding_revision"], int) or isinstance(payload["binding_revision"], bool) or payload["binding_revision"] < 1:
            raise TrustedIdentityError("BINDING_REVISION_INVALID")
        if payload["provider_verification_method"] != VERIFICATION_METHOD:
            raise TrustedIdentityError("BINDING_VERIFICATION_METHOD_INVALID")
        if not isinstance(payload["same_person_writer_reviewer"], bool):
            raise TrustedIdentityError("BINDING_WAIVER_STATE_INVALID")
        if payload["same_person_writer_reviewer"]:
            if payload["separation_of_duties_waiver"] != WAIVER:
                raise TrustedIdentityError("BINDING_WAIVER_INVALID")
        elif payload["separation_of_duties_waiver"] is not None:
            raise TrustedIdentityError("BINDING_WAIVER_UNEXPECTED")
        if payload["production_inheritance"] is not False or payload["automatic_scope_expansion"] is not False:
            raise TrustedIdentityError("BINDING_PRODUCTION_EXPANSION_FORBIDDEN")
        if not _valid_datetime(payload["verified_at"]):
            raise TrustedIdentityError("BINDING_VERIFIED_AT_INVALID")
        supplied_hash = value.get("semantic_hash")
        calculated_hash = _semantic_hash(payload, excluded=set())
        if not isinstance(supplied_hash, str) or supplied_hash != calculated_hash:
            raise TrustedIdentityError("BINDING_HASH_MISMATCH")
        return cls(**payload, semantic_hash=calculated_hash)

    def as_dict(self) -> dict[str, Any]:
        payload = _binding_payload(self.__dict__)
        return {**payload, "semantic_hash": self.semantic_hash}


_ATTESTATION = object()


@dataclass(frozen=True)
class VerifiedProviderIdentity:
    """Non-secret result supplied only after provider token verification."""

    provider: str
    reviewer_subject_ref: str
    workspace_domain: str
    verified_at: str
    verification_method: str
    _attestation: object

    def __deepcopy__(self, memo: dict[int, Any]) -> "VerifiedProviderIdentity":
        return self

    @classmethod
    def from_verified_google_claims(
        cls,
        claims: Mapping[str, Any],
        *,
        verified_at: str,
    ) -> "VerifiedProviderIdentity":
        """Convert claims only after an official Google verifier has accepted them."""

        stable_subject = claims.get("sub") if isinstance(claims, Mapping) else None
        hosted_domain = claims.get("hd") if isinstance(claims, Mapping) else None
        if not isinstance(stable_subject, str) or not isinstance(hosted_domain, str):
            raise TrustedIdentityError("VERIFIED_PROVIDER_CLAIMS_INCOMPLETE")
        if hosted_domain != "shopline.com" or not _valid_datetime(verified_at):
            raise TrustedIdentityError("VERIFIED_PROVIDER_CLAIMS_INVALID")
        return cls(
            provider=PROVIDER,
            reviewer_subject_ref=reviewer_subject_ref(stable_subject),
            workspace_domain=hosted_domain,
            verified_at=verified_at,
            verification_method=VERIFICATION_METHOD,
            _attestation=_ATTESTATION,
        )


@dataclass(frozen=True)
class TrustedIdentityEvidence:
    provider: str
    reviewer_subject_ref: str
    workspace_domain: str
    verified_at: str
    verification_method: str
    binding_revision: int
    binding_semantic_hash: str
    role: str
    scope: str
    evidence_hash: str
    _attestation: object

    def __deepcopy__(self, memo: dict[int, Any]) -> "TrustedIdentityEvidence":
        return self

    @classmethod
    def from_verified_provider_output(
        cls,
        provider_identity: VerifiedProviderIdentity,
        binding: TrustedReviewBinding,
    ) -> "TrustedIdentityEvidence":
        if not isinstance(provider_identity, VerifiedProviderIdentity) or provider_identity._attestation is not _ATTESTATION:
            raise TrustedIdentityError("UNVERIFIED_PROVIDER_OUTPUT")
        payload = {
            "provider": provider_identity.provider,
            "reviewer_subject_ref": provider_identity.reviewer_subject_ref,
            "workspace_domain": provider_identity.workspace_domain,
            "verified_at": provider_identity.verified_at,
            "verification_method": provider_identity.verification_method,
            "binding_revision": binding.binding_revision,
            "binding_semantic_hash": binding.semantic_hash,
            "role": binding.role,
            "scope": binding.scope,
        }
        return cls(**payload, evidence_hash=_semantic_hash(payload, excluded=set()), _attestation=_ATTESTATION)

    def is_verified_provider_evidence(self) -> bool:
        payload = {key: value for key, value in self.__dict__.items() if key not in {"evidence_hash", "_attestation"}}
        return self._attestation is _ATTESTATION and self.evidence_hash == _semantic_hash(payload, excluded=set())


@dataclass(frozen=True)
class TrustedIdentityVerification:
    trusted: bool
    state: str
    errors: tuple[str, ...]


class TrustedReviewVerifier:
    """Fail-closed runtime check for a loaded binding and verified evidence."""

    def __init__(self, binding: TrustedReviewBinding) -> None:
        self.binding = binding

    def verify(
        self,
        evidence: Any,
        *,
        writer_principal_ref: str,
        operation_count: int,
        environment: str,
    ) -> TrustedIdentityVerification:
        errors: list[str] = []
        if not isinstance(evidence, TrustedIdentityEvidence) or not evidence.is_verified_provider_evidence():
            errors.append("PROVIDER_EVIDENCE_REQUIRED")
        else:
            for field in ("provider", "reviewer_subject_ref", "workspace_domain", "role", "scope", "binding_revision", "binding_semantic_hash"):
                if getattr(evidence, field) != getattr(self.binding, field if field != "binding_semantic_hash" else "semantic_hash"):
                    errors.append("BINDING_" + field.upper() + "_MISMATCH")
        if not isinstance(writer_principal_ref, str) or _SAFE_REF.fullmatch(writer_principal_ref) is None or not writer_principal_ref.startswith("principal://"):
            errors.append("WRITER_PRINCIPAL_INVALID")
        if isinstance(evidence, TrustedIdentityEvidence) and writer_principal_ref == evidence.reviewer_subject_ref:
            errors.append("WRITER_REVIEWER_REFERENCE_COLLISION")
        if not isinstance(operation_count, int) or isinstance(operation_count, bool) or operation_count != 1:
            errors.append("OPERATION_LIMIT_INVALID")
        if str(environment).upper() != SCOPE:
            errors.append("SCOPE_ENVIRONMENT_INVALID")
        if self.binding.same_person_writer_reviewer:
            if self.binding.separation_of_duties_waiver != WAIVER:
                errors.append("SAME_PERSON_WAIVER_REQUIRED")
            if self.binding.scope != SCOPE or self.binding.production_inheritance or self.binding.automatic_scope_expansion:
                errors.append("SAME_PERSON_WAIVER_SCOPE_INVALID")
        return TrustedIdentityVerification(not errors, "PASS" if not errors else "BLOCKED", tuple(sorted(set(errors))))


def verify_trusted_review_context(
    context: Any,
    *,
    writer_principal_ref: str,
    operation_count: int,
    environment: str = SCOPE,
) -> TrustedIdentityVerification:
    """Reject caller-provided claim maps; only typed verified evidence is accepted."""

    if not isinstance(context, Mapping):
        return TrustedIdentityVerification(False, "BLOCKED", ("TRUSTED_CONTEXT_REQUIRED",))
    raw_binding = context.get("binding")
    evidence = context.get("evidence")
    try:
        binding = raw_binding if isinstance(raw_binding, TrustedReviewBinding) else TrustedReviewBinding.from_mapping(raw_binding)
    except TrustedIdentityError as error:
        return TrustedIdentityVerification(False, "BLOCKED", (error.code,))
    return TrustedReviewVerifier(binding).verify(
        evidence,
        writer_principal_ref=writer_principal_ref,
        operation_count=operation_count,
        environment=environment,
    )


def load_trusted_review_binding(path: str | Path) -> TrustedReviewBinding:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TrustedIdentityError("BINDING_UNREADABLE") from exc
    return TrustedReviewBinding.from_mapping(value)


__all__ = [
    "ACTIVE_STATUS", "AUTOMATIC_SCOPE_EXPANSION", "BINDING_VERSION", "PRODUCTION_INHERITANCE",
    "PROVIDER", "ROLE", "SCOPE", "VERIFICATION_METHOD", "WAIVER", "TrustedIdentityError",
    "TrustedIdentityEvidence", "TrustedIdentityVerification", "TrustedReviewBinding",
    "TrustedReviewVerifier", "VerifiedProviderIdentity", "load_trusted_review_binding",
    "reviewer_subject_ref", "verify_trusted_review_context",
]
