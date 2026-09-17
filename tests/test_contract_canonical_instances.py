"""Offline tests for the seven Phase 1 canonical contract instances."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from reporting.opportunity.contract_canonical import (
    APPROVAL_SCOPE,
    EXECUTION_CONTEXT,
    LEGACY_PHASE1_CANARY_ONLY,
    PRODUCTION_ACTIVATION,
    TARGET_ENVIRONMENT,
    TRANSPORT_MODE,
    CanonicalContractSpec,
    CanonicalEnvironment,
    CanonicalInstanceError,
    CANONICAL_CONTRACT_REGISTRY,
    PHASE1_CANONICAL_CONTRACT_IDS,
    _validate_registry,
    get_contract_spec,
    materialize_all_contract_instances,
    materialize_contract_instance,
    migrate_legacy_environment,
    parse_environment,
)


FIXTURE = Path(__file__).parent / "../contracts/canonical_contract_instances.v1.json"


def test_registry_has_exactly_seven_authoritative_logical_ids():
    assert len(CANONICAL_CONTRACT_REGISTRY) == 7
    assert PHASE1_CANONICAL_CONTRACT_IDS == (
        "trusted_review_identity.v1",
        "human_review.v1",
        "recommendation_bridge.v1",
        "google_sheets_target_binding.v1",
        "recommendation_canary_writer.v1",
        "production_release_manifest.v1",
        "production_activation.v1",
    )


def test_registry_maps_logical_ids_to_proposal_files_and_consumers():
    assert get_contract_spec("trusted_review_identity.v1").proposal_path.endswith(
        "trusted_review_identity_binding.v1.proposal.json"
    )
    for spec in CANONICAL_CONTRACT_REGISTRY.values():
        assert spec.schema_id.endswith(spec.proposal_path)
        assert spec.ruleset_ref
        assert spec.runtime_consumer
        assert spec.materializer_key


def test_unknown_logical_id_fails_closed():
    with pytest.raises(CanonicalInstanceError, match="unknown logical contract id"):
        get_contract_spec("unknown.v1")


def test_registry_rejects_duplicate_or_ambiguous_mappings():
    spec = next(iter(CANONICAL_CONTRACT_REGISTRY.values()))
    duplicate = CanonicalContractSpec(
        logical_contract_id=spec.logical_contract_id,
        proposal_path="contracts/other.json",
        schema_id="https://example.invalid/contracts/other.json",
        ruleset_ref="other",
        runtime_consumer="other",
        materializer_key="other",
        contract_version="other",
        semantic_field_allowlist=spec.semantic_field_allowlist,
        default_semantic_fields=spec.default_semantic_fields,
    )
    with pytest.raises(CanonicalInstanceError, match="duplicate logical contract id"):
        _validate_registry((spec, duplicate))


def test_environment_dimensions_are_independent_and_fail_closed():
    environment = CanonicalEnvironment()
    assert environment.approval_scope == APPROVAL_SCOPE
    assert environment.execution_context == EXECUTION_CONTEXT
    assert environment.transport_mode == TRANSPORT_MODE
    assert environment.target_environment == TARGET_ENVIRONMENT
    assert environment.production_activation == PRODUCTION_ACTIVATION
    assert environment.production_inheritance is False
    assert environment.automatic_scope_expansion is False


def test_legacy_environment_requires_explicit_migration():
    with pytest.raises(CanonicalInstanceError, match="requires explicit"):
        parse_environment(LEGACY_PHASE1_CANARY_ONLY)
    migration = migrate_legacy_environment(LEGACY_PHASE1_CANARY_ONLY)
    assert migration.legacy_value == LEGACY_PHASE1_CANARY_ONLY
    assert migration.canonical.approval_scope == APPROVAL_SCOPE
    assert migration.canonical.production_inheritance is False
    assert parse_environment(LEGACY_PHASE1_CANARY_ONLY, migrate_legacy=True) == migration


def test_all_seven_instances_are_materialized():
    instances = materialize_all_contract_instances()
    assert tuple(instance.contract_id for instance in instances) == PHASE1_CANONICAL_CONTRACT_IDS
    assert all(instance.validate() is instance for instance in instances)


def test_fixture_contains_the_same_seven_instances():
    payload = json.loads(FIXTURE.read_text())
    actual = {instance.contract_id: instance.as_dict() for instance in materialize_all_contract_instances()}
    assert len(payload["instances"]) == 7
    expected = {instance["contract_id"]: instance for instance in payload["instances"]}
    assert expected == actual


def test_materialization_is_deterministic_across_repeated_runs():
    first = materialize_all_contract_instances()
    second = materialize_all_contract_instances()
    assert [item.as_dict() for item in first] == [item.as_dict() for item in second]


def test_semantic_field_order_does_not_change_hash():
    spec = get_contract_spec("human_review.v1")
    overrides = dict(reversed(tuple(spec.defaults().items())))
    assert materialize_contract_instance("human_review.v1", semantic_overrides=overrides).contract_semantic_hash == materialize_contract_instance(
        "human_review.v1"
    ).contract_semantic_hash


def test_contract_revision_is_semantic_and_changes_hash():
    first = materialize_contract_instance("human_review.v1", contract_revision=1)
    second = materialize_contract_instance("human_review.v1", contract_revision=2)
    assert first.contract_semantic_hash != second.contract_semantic_hash
    assert first.contract_revision == 1
    assert second.contract_revision == 2


def test_runtime_trace_metadata_does_not_change_semantic_hash():
    instance = materialize_contract_instance("human_review.v1")
    traced = replace(instance, created_from_ruleset_ref="trace-only-ruleset-ref")
    assert traced.contract_semantic_hash == instance.contract_semantic_hash
    assert "created_from_ruleset_ref" not in instance.semantic_payload()


def test_runtime_event_revision_cannot_replace_contract_revision():
    with pytest.raises(CanonicalInstanceError, match="unknown semantic field"):
        materialize_contract_instance("human_review.v1", semantic_overrides={"revision": 9})


def test_unknown_semantic_override_fails_closed():
    with pytest.raises(CanonicalInstanceError, match="unknown semantic field"):
        materialize_contract_instance("human_review.v1", semantic_overrides={"created_at": "now"})


def test_runtime_and_external_metadata_cannot_become_semantic_fields():
    with pytest.raises(CanonicalInstanceError, match="unknown semantic field"):
        materialize_contract_instance(
            "human_review.v1",
            semantic_overrides={"allowed_decisions": ["APPROVE"], "reviewer_actor_type": "HUMAN", "exact_candidate_pin": True, "requires_trusted_identity": True, "approval_does_not_authorize_activation": True, "receipt_id": "r1"},
        )


def test_identity_binding_and_workbook_ids_are_external_to_contract_instances():
    instance = materialize_contract_instance("trusted_review_identity.v1")
    target = materialize_contract_instance("google_sheets_target_binding.v1")
    assert "reviewer_subject_ref" not in instance.semantic_fields
    assert "workbook_id_ref" not in target.semantic_fields
    with pytest.raises(CanonicalInstanceError, match="unknown semantic field"):
        materialize_contract_instance(
            "google_sheets_target_binding.v1",
            semantic_overrides={"workbook_id_ref": "external-only"},
        )


def test_canonical_instances_never_authorize_production():
    for instance in materialize_all_contract_instances():
        assert instance.production_activation == "NOT_AUTHORIZED"
        assert instance.production_inheritance is False
        assert instance.automatic_scope_expansion is False


def test_production_activation_instance_is_governance_only():
    instance = materialize_contract_instance("production_activation.v1")
    assert instance.semantic_fields["activation_kind"] == "GOVERNANCE_GATE_ONLY"
    assert instance.semantic_fields["production_mutation"] == 0
    assert instance.semantic_fields["automatic_activation"] is False


def test_instances_contain_no_external_identity_or_target_values():
    rendered = json.dumps([item.as_dict() for item in materialize_all_contract_instances()])
    for forbidden in ("workbook_id", "folder_id", "client_secret", "access_token", "@shopline.com"):
        assert forbidden not in rendered
