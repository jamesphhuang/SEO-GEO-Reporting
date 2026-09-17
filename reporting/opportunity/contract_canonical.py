"""Deterministic canonical instances for the Phase 1 contract set.

This module is deliberately separate from approval receipts and external target
bindings.  It describes the rules that an approval would pin; it never records
an approval and it never performs a production operation.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any, ClassVar, Mapping

from .store.serialization import canonical_json


CANONICAL_INSTANCE_VERSION = "canonical_contract_instance.v1"
MATERIALIZER_VERSION = "contract-canonical-materializer.v1"

APPROVAL_SCOPE = "PHASE1_CANARY"
EXECUTION_CONTEXT = "UAT"
TRANSPORT_MODE = "ZERO_WRITE"
TARGET_ENVIRONMENT = "PRODUCTION_CANARY"
PRODUCTION_ACTIVATION = "NOT_AUTHORIZED"
LEGACY_PHASE1_CANARY_ONLY = "PHASE1_CANARY_ONLY"


class CanonicalInstanceError(ValueError):
    """Raised when canonical contract data is unknown or ambiguous."""


@dataclass(frozen=True)
class CanonicalEnvironment:
    """The independent dimensions used by every canonical instance."""

    approval_scope: str = APPROVAL_SCOPE
    execution_context: str = EXECUTION_CONTEXT
    transport_mode: str = TRANSPORT_MODE
    target_environment: str = TARGET_ENVIRONMENT
    production_activation: str = PRODUCTION_ACTIVATION
    production_inheritance: bool = False
    automatic_scope_expansion: bool = False

    ALLOWED_SCOPES: ClassVar[frozenset[str]] = frozenset({APPROVAL_SCOPE})
    ALLOWED_CONTEXTS: ClassVar[frozenset[str]] = frozenset({EXECUTION_CONTEXT})
    ALLOWED_TRANSPORTS: ClassVar[frozenset[str]] = frozenset({TRANSPORT_MODE, "SYNTHETIC"})
    ALLOWED_TARGETS: ClassVar[frozenset[str]] = frozenset({TARGET_ENVIRONMENT})
    ALLOWED_ACTIVATION_STATES: ClassVar[frozenset[str]] = frozenset({PRODUCTION_ACTIVATION})

    def validate(self) -> "CanonicalEnvironment":
        if self.approval_scope == LEGACY_PHASE1_CANARY_ONLY:
            raise CanonicalInstanceError(
                "legacy PHASE1_CANARY_ONLY requires explicit migrate_legacy_environment()"
            )
        if self.approval_scope not in self.ALLOWED_SCOPES:
            raise CanonicalInstanceError(f"unknown approval_scope: {self.approval_scope}")
        if self.execution_context not in self.ALLOWED_CONTEXTS:
            raise CanonicalInstanceError(f"unknown execution_context: {self.execution_context}")
        if self.transport_mode not in self.ALLOWED_TRANSPORTS:
            raise CanonicalInstanceError(f"unknown transport_mode: {self.transport_mode}")
        if self.target_environment not in self.ALLOWED_TARGETS:
            raise CanonicalInstanceError(f"unknown target_environment: {self.target_environment}")
        if self.production_activation not in self.ALLOWED_ACTIVATION_STATES:
            raise CanonicalInstanceError(
                f"unknown production_activation: {self.production_activation}"
            )
        if self.production_inheritance or self.automatic_scope_expansion:
            raise CanonicalInstanceError(
                "Phase 1 canonical instances cannot inherit production scope or expand automatically"
            )
        return self

    def as_dict(self) -> dict[str, Any]:
        self.validate()
        return {
            "approval_scope": self.approval_scope,
            "execution_context": self.execution_context,
            "transport_mode": self.transport_mode,
            "target_environment": self.target_environment,
            "production_activation": self.production_activation,
            "production_inheritance": self.production_inheritance,
            "automatic_scope_expansion": self.automatic_scope_expansion,
        }


@dataclass(frozen=True)
class LegacyEnvironmentMigration:
    """An explicit, auditable interpretation of a legacy environment value."""

    legacy_value: str
    canonical: CanonicalEnvironment
    migration_rule: str = "phase1-canary-only-to-independent-dimensions.v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "legacy_value": self.legacy_value,
            "migration_rule": self.migration_rule,
            "canonical": self.canonical.as_dict(),
        }


def migrate_legacy_environment(value: str) -> LegacyEnvironmentMigration:
    """Migrate the one legacy value only when the caller asks explicitly."""

    if value != LEGACY_PHASE1_CANARY_ONLY:
        raise CanonicalInstanceError(f"unsupported legacy environment: {value}")
    return LegacyEnvironmentMigration(
        legacy_value=value,
        canonical=CanonicalEnvironment(),
    )


def parse_environment(value: str, *, migrate_legacy: bool = False) -> CanonicalEnvironment | LegacyEnvironmentMigration:
    """Reject legacy values by default; never silently reinterpret them."""

    if value == LEGACY_PHASE1_CANARY_ONLY:
        if not migrate_legacy:
            raise CanonicalInstanceError(
                "PHASE1_CANARY_ONLY is legacy and requires explicit migration; "
                "pass migrate_legacy=True"
            )
        return migrate_legacy_environment(value)
    if value != APPROVAL_SCOPE:
        raise CanonicalInstanceError(f"unknown environment/scope: {value}")
    return CanonicalEnvironment()


@dataclass(frozen=True)
class CanonicalContractSpec:
    """Authoritative logical-contract mapping and semantic allowlist."""

    logical_contract_id: str
    proposal_path: str
    schema_id: str
    ruleset_ref: str
    runtime_consumer: str
    materializer_key: str
    contract_version: str
    semantic_field_allowlist: tuple[str, ...]
    default_semantic_fields: tuple[tuple[str, Any], ...]

    def defaults(self) -> dict[str, Any]:
        return dict(self.default_semantic_fields)


def _spec(
    logical_id: str,
    proposal_path: str,
    ruleset: str,
    consumer: str,
    key: str,
    fields: Mapping[str, Any],
) -> CanonicalContractSpec:
    return CanonicalContractSpec(
        logical_contract_id=logical_id,
        proposal_path=proposal_path,
        schema_id=f"https://example.invalid/{proposal_path}",
        ruleset_ref=ruleset,
        runtime_consumer=consumer,
        materializer_key=key,
        contract_version=f"{logical_id}.canonical.v1",
        semantic_field_allowlist=tuple(fields),
        default_semantic_fields=tuple((key, fields[key]) for key in fields),
    )


CANONICAL_CONTRACT_SPECS: tuple[CanonicalContractSpec, ...] = (
    _spec(
        "trusted_review_identity.v1",
        "contracts/trusted_review_identity_binding.v1.proposal.json",
        "trusted-review-identity-rules.v1",
        "trusted_review_identity.TrustedReviewBinding/TrustedReviewVerifier",
        "trusted_review_identity",
        {
            "provider": "GOOGLE_WORKSPACE",
            "role": "RECOMMENDATION_APPROVER",
            "scope": APPROVAL_SCOPE,
            "provider_verification_method": "GOOGLE_OIDC_ID_TOKEN_V1",
            "requires_provider_evidence": True,
            "production_inheritance": False,
            "automatic_scope_expansion": False,
        },
    ),
    _spec(
        "human_review.v1",
        "contracts/human_review.v1.proposal.json",
        "human-review-rules.v1",
        "review.HumanReviewStore/validate_human_review",
        "human_review",
        {
            "reviewer_actor_type": "HUMAN",
            "requires_trusted_identity": True,
            "exact_candidate_pin": True,
            "allowed_decisions": ["APPROVE", "REJECT", "NEEDS_MORE_EVIDENCE", "DEFER", "RETURN_FOR_REVIEW"],
            "approval_does_not_authorize_activation": True,
        },
    ),
    _spec(
        "recommendation_bridge.v1",
        "contracts/recommendation_bridge.v1.proposal.json",
        "recommendation-bridge-rules.v1",
        "review_bridge.RecommendationBridgeStore/validate_recommendation_bridge",
        "recommendation_bridge",
        {
            "workflow_role": "RECOMMENDATION_WORKFLOW_ENTRY_ONLY",
            "allowed_review_decision": "APPROVE",
            "target_scope": APPROVAL_SCOPE,
            "production_mutation": False,
            "next_steps_written": False,
            "automatic_approval": False,
            "exact_review_pin": True,
        },
    ),
    _spec(
        "google_sheets_target_binding.v1",
        "contracts/google_sheets_target_binding.v1.proposal.json",
        "google-sheets-target-binding-rules.v1",
        "canary_writer.GoogleSheetsTargetBinding",
        "google_sheets_target_binding",
        {
            "target_type": "GOOGLE_SHEETS",
            "target_tab": "Opportunity_Recommendations",
            "external_binding_required": True,
            "external_target_id_excluded": True,
            "readback_required": True,
            "max_operations": 1,
            "protected_fields_required": True,
        },
    ),
    _spec(
        "recommendation_canary_writer.v1",
        "contracts/recommendation_canary_writer.v1.proposal.json",
        "recommendation-canary-writer-rules.v1",
        "canary_writer.RecommendationCanaryWriter",
        "recommendation_canary_writer",
        {
            "writer_mode": "AUTHORIZED_USER_OAUTH",
            "max_operations": 1,
            "bulk_write": False,
            "automatic_retry": False,
            "readback_required": True,
            "audit_receipt_required": True,
            "kill_switch_required": True,
            "production_inheritance": False,
            "transport_mode": TRANSPORT_MODE,
        },
    ),
    _spec(
        "production_release_manifest.v1",
        "contracts/production_release_manifest.v1.proposal.json",
        "production-release-manifest-rules.v1",
        "production_hardening.build_release_manifest",
        "production_release_manifest",
        {
            "release_kind": "PRODUCTION_CANARY_RULESET",
            "production_write_ready": False,
            "scheduler_state": "DISABLED",
            "activation_state": PRODUCTION_ACTIVATION,
            "rollback_required": True,
            "readback_required": True,
            "audit_required": True,
            "planned_operations_max": 1,
        },
    ),
    _spec(
        "production_activation.v1",
        "contracts/production_activation.v1.proposal.json",
        "production-activation-rules.v1",
        "production_hardening.validate_activation_proposal",
        "production_activation",
        {
            "activation_kind": "GOVERNANCE_GATE_ONLY",
            "activation_state": PRODUCTION_ACTIVATION,
            "explicit_authorization_required": True,
            "production_mutation": 0,
            "scheduler_enabled": False,
            "approval_receipt_required": True,
            "automatic_activation": False,
        },
    ),
)


def _validate_registry(specs: tuple[CanonicalContractSpec, ...]) -> dict[str, CanonicalContractSpec]:
    by_id: dict[str, CanonicalContractSpec] = {}
    seen_paths: set[str] = set()
    seen_keys: set[str] = set()
    for spec in specs:
        if spec.logical_contract_id in by_id:
            raise CanonicalInstanceError(f"duplicate logical contract id: {spec.logical_contract_id}")
        if spec.proposal_path in seen_paths:
            raise CanonicalInstanceError(f"ambiguous proposal mapping: {spec.proposal_path}")
        if spec.materializer_key in seen_keys:
            raise CanonicalInstanceError(f"duplicate materializer key: {spec.materializer_key}")
        if len(spec.semantic_field_allowlist) != len(set(spec.semantic_field_allowlist)):
            raise CanonicalInstanceError(f"duplicate semantic field in {spec.logical_contract_id}")
        if set(spec.semantic_field_allowlist) != set(spec.defaults()):
            raise CanonicalInstanceError(f"default fields exceed allowlist for {spec.logical_contract_id}")
        by_id[spec.logical_contract_id] = spec
        seen_paths.add(spec.proposal_path)
        seen_keys.add(spec.materializer_key)
    return by_id


CANONICAL_CONTRACT_REGISTRY = _validate_registry(CANONICAL_CONTRACT_SPECS)
PHASE1_CANONICAL_CONTRACT_IDS = tuple(spec.logical_contract_id for spec in CANONICAL_CONTRACT_SPECS)


def get_contract_spec(logical_contract_id: str) -> CanonicalContractSpec:
    try:
        return CANONICAL_CONTRACT_REGISTRY[logical_contract_id]
    except KeyError as exc:
        raise CanonicalInstanceError(f"unknown logical contract id: {logical_contract_id}") from exc


def _reject_runtime_metadata(value: Any, path: str = "semantic_fields") -> None:
    forbidden_fragments = (
        "timestamp", "created_at", "updated_at", "git_sha", "filesystem_path",
        "test_metadata", "receipt_id", "credential", "token", "email", "workbook_id",
        "folder_id", "principal_ref", "subject_ref",
    )
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in forbidden_fragments):
                raise CanonicalInstanceError(f"runtime or external metadata is not semantic: {path}.{key}")
            _reject_runtime_metadata(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_runtime_metadata(item, f"{path}[{index}]")


@dataclass(frozen=True)
class CanonicalContractInstance:
    """A canonical, non-approval instance of one contract's rules."""

    contract_id: str
    contract_version: str
    contract_revision: int
    approval_scope: str
    execution_context: str
    transport_mode: str
    target_environment: str
    production_activation: str
    production_inheritance: bool
    automatic_scope_expansion: bool
    semantic_fields: Mapping[str, Any]
    contract_semantic_hash: str
    created_from_ruleset_ref: str
    materializer_version: str

    @property
    def revision(self) -> int:
        """Compatibility alias that makes the semantic revision explicit."""

        return self.contract_revision

    @property
    def semantic_hash(self) -> str:
        return self.contract_semantic_hash

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "contract_version": self.contract_version,
            "contract_revision": self.contract_revision,
            "approval_scope": self.approval_scope,
            "execution_context": self.execution_context,
            "transport_mode": self.transport_mode,
            "target_environment": self.target_environment,
            "production_activation": self.production_activation,
            "production_inheritance": self.production_inheritance,
            "automatic_scope_expansion": self.automatic_scope_expansion,
            "semantic_fields": dict(self.semantic_fields),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            **self.semantic_payload(),
            "contract_semantic_hash": self.contract_semantic_hash,
            "created_from_ruleset_ref": self.created_from_ruleset_ref,
            "materializer_version": self.materializer_version,
        }

    def validate(self) -> "CanonicalContractInstance":
        if not self.contract_id or not self.contract_version or not self.created_from_ruleset_ref:
            raise CanonicalInstanceError("canonical instance identity is incomplete")
        if not isinstance(self.contract_revision, int) or self.contract_revision < 1:
            raise CanonicalInstanceError("contract_revision must be a positive integer")
        CanonicalEnvironment(
            approval_scope=self.approval_scope,
            execution_context=self.execution_context,
            transport_mode=self.transport_mode,
            target_environment=self.target_environment,
            production_activation=self.production_activation,
            production_inheritance=self.production_inheritance,
            automatic_scope_expansion=self.automatic_scope_expansion,
        ).validate()
        spec = get_contract_spec(self.contract_id)
        fields = dict(self.semantic_fields)
        if set(fields) != set(spec.semantic_field_allowlist):
            raise CanonicalInstanceError(f"semantic fields do not match allowlist for {self.contract_id}")
        _reject_runtime_metadata(fields)
        expected = _hash_semantics(self.semantic_payload())
        if expected != self.contract_semantic_hash:
            raise CanonicalInstanceError("contract_semantic_hash does not match semantic payload")
        if self.materializer_version != MATERIALIZER_VERSION:
            raise CanonicalInstanceError("unknown materializer_version")
        return self


def _hash_semantics(payload: Mapping[str, Any]) -> str:
    return sha256(canonical_json(dict(payload)).encode("utf-8")).hexdigest()


def materialize_contract_instance(
    logical_contract_id: str,
    *,
    contract_revision: int = 1,
    semantic_overrides: Mapping[str, Any] | None = None,
    environment: CanonicalEnvironment | None = None,
) -> CanonicalContractInstance:
    """Materialize one canonical instance without external or runtime metadata."""

    spec = get_contract_spec(logical_contract_id)
    if not isinstance(contract_revision, int) or contract_revision < 1:
        raise CanonicalInstanceError("contract_revision must be a positive integer")
    env = environment or CanonicalEnvironment()
    env.validate()
    fields = spec.defaults()
    if semantic_overrides:
        unknown = set(semantic_overrides) - set(spec.semantic_field_allowlist)
        if unknown:
            raise CanonicalInstanceError(
                f"unknown semantic field(s) for {logical_contract_id}: {sorted(unknown)}"
            )
        fields.update(dict(semantic_overrides))
    _reject_runtime_metadata(fields)
    payload = {
        "contract_id": logical_contract_id,
        "contract_version": spec.contract_version,
        "contract_revision": contract_revision,
        **env.as_dict(),
        "semantic_fields": fields,
    }
    instance = CanonicalContractInstance(
        contract_id=logical_contract_id,
        contract_version=spec.contract_version,
        contract_revision=contract_revision,
        approval_scope=env.approval_scope,
        execution_context=env.execution_context,
        transport_mode=env.transport_mode,
        target_environment=env.target_environment,
        production_activation=env.production_activation,
        production_inheritance=env.production_inheritance,
        automatic_scope_expansion=env.automatic_scope_expansion,
        semantic_fields=fields,
        contract_semantic_hash=_hash_semantics(payload),
        created_from_ruleset_ref=spec.ruleset_ref,
        materializer_version=MATERIALIZER_VERSION,
    )
    return instance.validate()


def materialize_all_contract_instances(
    *, contract_revision: int = 1, environment: CanonicalEnvironment | None = None
) -> tuple[CanonicalContractInstance, ...]:
    """Materialize all seven authoritative Phase 1 contract definitions."""

    return tuple(
        materialize_contract_instance(
            spec.logical_contract_id,
            contract_revision=contract_revision,
            environment=environment,
        )
        for spec in CANONICAL_CONTRACT_SPECS
    )


# Short aliases keep call sites readable while retaining the explicit API names.
materialize_contract = materialize_contract_instance
materialize_all_contracts = materialize_all_contract_instances
