import hashlib
import json
import unittest
from dataclasses import replace
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from reporting.opportunity.store.serialization import canonical_json
from reporting.opportunity.trusted_review_identity import (
    TrustedIdentityError,
    TrustedIdentityEvidence,
    TrustedReviewBinding,
    TrustedReviewVerifier,
    VerifiedProviderIdentity,
    reviewer_subject_ref,
    verify_trusted_review_context,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/opportunity_trusted_review_identity/scenarios.json").read_text())
WRITER = "principal://authorized-user-oauth/runtime"
TIMESTAMP = "2026-09-17T09:00:00+08:00"


def digest(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def binding_value(**overrides):
    value = {
        "binding_version": "trusted-review-identity-binding.v1",
        "provider": "GOOGLE_WORKSPACE",
        "reviewer_subject_ref": reviewer_subject_ref("synthetic-google-subject-a"),
        "workspace_domain": "shopline.com",
        "role": "RECOMMENDATION_APPROVER",
        "scope": "PHASE1_CANARY",
        "status": "ACTIVE",
        "binding_revision": 1,
        "provider_verification_method": "GOOGLE_OIDC_ID_TOKEN_V1",
        "same_person_writer_reviewer": True,
        "separation_of_duties_waiver": "APPROVED_PHASE1_CANARY_ONLY",
        "production_inheritance": False,
        "automatic_scope_expansion": False,
        "verified_at": TIMESTAMP,
    }
    value.update(overrides)
    value["semantic_hash"] = digest(value)
    return value


def binding(**overrides):
    return TrustedReviewBinding.from_mapping(binding_value(**overrides))


def evidence(value=None):
    current = value or binding()
    identity = VerifiedProviderIdentity.from_verified_google_claims(
        {"sub": "synthetic-google-subject-a", "hd": "shopline.com"},
        verified_at=TIMESTAMP,
    )
    return TrustedIdentityEvidence.from_verified_provider_output(identity, current)


def changed_evidence(current, **overrides):
    payload = {
        key: value for key, value in current.__dict__.items()
        if key not in {"evidence_hash", "_attestation"}
    }
    payload.update(overrides)
    return TrustedIdentityEvidence(
        **payload,
        evidence_hash=digest(payload),
        _attestation=current._attestation,
    )


class TrustedReviewIdentityTests(unittest.TestCase):
    def test_contract_is_draft_and_schema_is_valid(self):
        schema = json.loads((ROOT / "contracts/trusted_review_identity_binding.v1.proposal.json").read_text())
        Draft202012Validator.check_schema(schema)
        self.assertEqual(schema["x-proposal-status"], "DRAFT_NOT_APPROVED")
        self.assertFalse(schema["x-production-activation"])
        self.assertTrue(Draft202012Validator(schema, format_checker=FormatChecker()).is_valid(binding_value()))

    def test_fixture_is_synthetic_and_covers_a_to_s(self):
        self.assertTrue(FIXTURE["metadata"]["synthetic"])
        self.assertEqual(FIXTURE["metadata"]["production_mutation"], 0)
        self.assertEqual([item["id"] for item in FIXTURE["scenarios"]], list("ABCDEFGHIJKLMNOPQRS"))

    def test_subject_ref_is_deterministic_and_distinct(self):
        first = reviewer_subject_ref("synthetic-google-subject-a")
        self.assertEqual(first, reviewer_subject_ref("synthetic-google-subject-a"))
        self.assertNotEqual(first, reviewer_subject_ref("synthetic-google-subject-b"))
        self.assertRegex(first, r"^[a-f0-9]{64}$")

    def test_valid_provider_evidence_and_binding_pass(self):
        current = binding()
        result = TrustedReviewVerifier(current).verify(
            evidence(current), writer_principal_ref=WRITER, operation_count=1, environment="PHASE1_CANARY"
        )
        self.assertTrue(result.trusted, result)
        self.assertEqual(result.state, "PASS")

    def test_authenticated_or_caller_claims_alone_are_blocked(self):
        for context in (
            {"authenticated": True},
            {"email": "synthetic@shopline.example"},
            {"role": "RECOMMENDATION_APPROVER"},
            {"subject_ref": "a" * 64, "workspace_domain": "shopline.com"},
        ):
            result = verify_trusted_review_context(context, writer_principal_ref=WRITER, operation_count=1)
            self.assertFalse(result.trusted)

    def test_provider_evidence_absent_is_blocked(self):
        result = verify_trusted_review_context({"binding": binding()}, writer_principal_ref=WRITER, operation_count=1)
        self.assertFalse(result.trusted)
        self.assertIn("PROVIDER_EVIDENCE_REQUIRED", result.errors)

    def test_wrong_provider_subject_domain_role_and_scope_are_blocked(self):
        current = binding()
        valid = evidence(current)
        for changes in (
            {"provider": "OTHER"},
            {"reviewer_subject_ref": "b" * 64},
            {"workspace_domain": "invalid.example"},
            {"role": "OTHER_ROLE"},
            {"scope": "OTHER_SCOPE"},
        ):
            result = TrustedReviewVerifier(current).verify(
                changed_evidence(valid, **changes), writer_principal_ref=WRITER, operation_count=1, environment="PHASE1_CANARY"
            )
            self.assertFalse(result.trusted)

    def test_disabled_binding_and_bad_hash_fail_closed(self):
        with self.assertRaises(TrustedIdentityError):
            binding(status="DISABLED")
        value = binding_value()
        value["semantic_hash"] = "0" * 64
        with self.assertRaises(TrustedIdentityError) as error:
            TrustedReviewBinding.from_mapping(value)
        self.assertEqual(error.exception.code, "BINDING_HASH_MISMATCH")
        value = binding_value()
        value["unexpected"] = "synthetic"
        with self.assertRaises(TrustedIdentityError) as error:
            TrustedReviewBinding.from_mapping(value)
        self.assertEqual(error.exception.code, "BINDING_UNEXPECTED_FIELD")

    def test_revision_and_semantic_hash_mismatch_are_blocked(self):
        current = binding()
        valid = evidence(current)
        for changes in ({"binding_revision": 2}, {"binding_semantic_hash": "0" * 64}):
            result = TrustedReviewVerifier(current).verify(
                changed_evidence(valid, **changes), writer_principal_ref=WRITER, operation_count=1, environment="PHASE1_CANARY"
            )
            self.assertFalse(result.trusted)

    def test_same_person_waiver_is_phase1_only(self):
        current = binding()
        valid = evidence(current)
        self.assertTrue(TrustedReviewVerifier(current).verify(valid, writer_principal_ref=WRITER, operation_count=1, environment="PHASE1_CANARY").trusted)
        no_waiver = replace(current, separation_of_duties_waiver=None)
        self.assertFalse(TrustedReviewVerifier(no_waiver).verify(valid, writer_principal_ref=WRITER, operation_count=1, environment="PHASE1_CANARY").trusted)
        self.assertFalse(TrustedReviewVerifier(current).verify(valid, writer_principal_ref=WRITER, operation_count=2, environment="PHASE1_CANARY").trusted)
        self.assertFalse(TrustedReviewVerifier(current).verify(valid, writer_principal_ref=WRITER, operation_count=1, environment="PRODUCTION").trusted)
        self.assertFalse(TrustedReviewVerifier(current).verify(valid, writer_principal_ref=WRITER, operation_count=1, environment="OTHER").trusted)

    def test_writer_and_reviewer_references_remain_distinct(self):
        current = binding()
        result = TrustedReviewVerifier(current).verify(
            evidence(current),
            writer_principal_ref=current.reviewer_subject_ref,
            operation_count=1,
            environment="PHASE1_CANARY",
        )
        self.assertFalse(result.trusted)
        self.assertIn("WRITER_REVIEWER_REFERENCE_COLLISION", result.errors)

    def test_evidence_requires_internal_verified_provider_attestation(self):
        current = binding()
        valid = evidence(current)
        fake = replace(valid, _attestation=object())
        result = TrustedReviewVerifier(current).verify(fake, writer_principal_ref=WRITER, operation_count=1, environment="PHASE1_CANARY")
        self.assertFalse(result.trusted)
        self.assertIn("PROVIDER_EVIDENCE_REQUIRED", result.errors)

    def test_binding_contains_no_secret_or_raw_identity_fields(self):
        value = binding_value()
        value["raw_subject"] = "synthetic-only"
        value["semantic_hash"] = digest({key: item for key, item in value.items() if key != "semantic_hash"})
        with self.assertRaises(TrustedIdentityError) as error:
            TrustedReviewBinding.from_mapping(value)
        self.assertEqual(error.exception.code, "BINDING_SENSITIVE_FIELD")


if __name__ == "__main__":
    unittest.main()
