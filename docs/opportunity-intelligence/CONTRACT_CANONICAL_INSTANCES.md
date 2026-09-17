# Contract Canonical Instances

## Phase 1 foundation（2026-09-17）

This document describes the repository's canonical rules instances. It is not an
approval record, an approval receipt, or an external target binding.

Every instance keeps these dimensions separate:

| Dimension | Phase 1 value |
| --- | --- |
| `approval_scope` | `PHASE1_CANARY` |
| `execution_context` | `UAT` |
| `transport_mode` | `ZERO_WRITE` (synthetic materialization is allowed in tests) |
| `target_environment` | `PRODUCTION_CANARY` |
| `production_activation` | `NOT_AUTHORIZED` |
| `production_inheritance` | `false` |
| `automatic_scope_expansion` | `false` |

`PHASE1_CANARY_ONLY` is a legacy composite value. New instances reject it. The
only supported migration is the explicit `migrate_legacy_environment()` path,
which records the legacy value and the independent canonical dimensions.

## Authoritative registry

The registry contains exactly seven logical contracts:

1. `trusted_review_identity.v1` → `trusted_review_identity_binding.v1.proposal.json`
2. `human_review.v1` → `human_review.v1.proposal.json`
3. `recommendation_bridge.v1` → `recommendation_bridge.v1.proposal.json`
4. `google_sheets_target_binding.v1` → `google_sheets_target_binding.v1.proposal.json`
5. `recommendation_canary_writer.v1` → `recommendation_canary_writer.v1.proposal.json`
6. `production_release_manifest.v1` → `production_release_manifest.v1.proposal.json`
7. `production_activation.v1` → `production_activation.v1.proposal.json`

Each entry also pins a ruleset reference, runtime consumer, materializer key,
canonical contract version, and semantic field allowlist. Unknown, duplicate,
or ambiguous mappings fail closed. The trusted identity logical id is mapped to
the existing `trusted_review_identity_binding` proposal without renaming that
proposal or treating an external identity binding as an approval receipt.

## Instance and hash rules

`CanonicalContractInstance` contains the contract id, canonical version,
contract semantics revision, independent dimensions, semantic fields, semantic
hash, ruleset reference, and materializer version. The semantic hash includes
the contract revision and only canonical JSON fields. It excludes timestamps,
Git SHAs, filesystem paths, test metadata, receipt ids, credentials, identity
values, and real workbook or folder ids. Reordering mapping inputs does not
change a hash; changing the contract revision does.

The checked-in `contracts/canonical_contract_instances.v1.json` fixture contains
the seven deterministic definitions. It is a rules fixture, not an approval
decision and not a persistent approval store.

## Readiness and boundaries

```ini
CONTRACT_CANONICAL_INSTANCE_FOUNDATION = READY
SEMANTIC_READINESS = READY
CANONICAL_INSTANCE_READINESS = READY
APPROVAL_EXECUTION_READINESS = BLOCKED_PERSISTENT_STORE
PRIOR_APPROVAL_DECISION_STATUS = RECONFIRMATION_REQUIRED
FORMAL_APPROVAL_RECEIPTS = 0
CONTRACTS_APPROVED = 0
PRODUCTION_ACTIVATION = NOT_AUTHORIZED
LIVE_WRITE_READINESS = BLOCKED
NEXT_TASK = Phase 1 Persistent Approval Store
```

No `approvals/` directory, approval receipt, Google Sheets write, audit write,
scheduler, live source call, or production mutation is created by this
foundation.
