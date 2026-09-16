# Production Phase 1 — Recommendation Canary Writer

This document describes the Phase 1 Recommendation canary writer prepared from
baseline `9f984b26e177cec109e8b3b5ac2053d6b0e62b43`. It is an offline/UAT
implementation. `PHASE1_CANARY_WRITER_READINESS = READY` does not authorize
production activation.

## Scope

The canary accepts exactly one Recommendation Bridge that is bound to one
authenticated human review, one Candidate revision, one Review revision, and
one Bridge revision. The only target binding supported by this proposal is a
synthetic UAT Google Sheets binding whose tab is
`Opportunity_Recommendations`. The workbook ID and OAuth principal are
runtime references; no real value is stored in code or fixtures.

The Phase 1 field allowlist is:

`recommendation_id`, `candidate_id`, `candidate_revision`, `candidate_hash`,
`review_id`, `review_revision`, `review_hash`, `bridge_id`, `bridge_revision`,
`bridge_hash`, `recommendation_text`, `action_type`, `topic_refs`,
`target_url_refs`, `score`, `confidence`, `evidence_refs`, `conflict_status`,
`governance_status`, `release_id`, `operation_id`, `semantic_hash`, and
`created_at`.

Human notes, Next Steps, existing report data, human decision fields, review
content, unapproved fields, and other workbook data are protected. Score and
Confidence are carried as read-only projections; the writer never recomputes
them.

## Execution boundary

The flow is:

`Human Review → Recommendation Bridge → eligibility → target binding → one
WriteIntent → idempotency → injected synthetic transport → mandatory readback →
append-only audit receipt`.

The production environment is rejected. The current transport is a synthetic
fake used by tests and UAT planning; it never calls Google Sheets. Authorized
user OAuth remains an external runtime dependency. A caller's
`authenticated=true` flag is insufficient: a trusted review context must carry
an independently verified provider and subject reference.

The writer fails closed for invalid pins, stale evidence, superseded review,
unresolved conflicts, unknown target or principal, protected-field mutation,
more than one operation, kill switch, idempotency conflict, invalid hashes or
revisions, missing audit persistence, missing readback, and readback mismatch.

`CanaryIdempotencyStore` and `RecommendationAuditStore` are offline,
persistent-style abstractions. They are not distributed locks and do not
replace a production transaction or audit service. Audit receipts are written
under the configured temporary/UAT path as `operation_<operation_id>.json` and
cannot be overwritten by a different semantic hash.

## Unknown results

An uncertain transport result is never retried automatically. The writer reads
back the exact operation:

- exact record found → `RECONCILED_SUCCESS` and canary completion;
- no record → `SAFE_TO_RETRY_REQUIRES_HUMAN_AUTHORIZATION`;
- conflicting record → `RECONCILIATION_CONFLICT`.

An HTTP success without a matching readback is `READBACK_MISMATCH`, not
success.

## Explicit exclusions

Phase 1 does not automate Next Steps, outcome scheduling, 30/60/90 dispatch,
live GSC/GA4/Ahrefs/Workduo/SERP/Screaming Frog/CrUX collection, bulk or
multi-target publishing, automatic action execution, automatic score or
confidence recalculation, automatic Candidate approval, existing production
workbook integration, Apps Script deployment, or retry without reconciliation.

## Promotion prerequisites

The Phase 1 logical decisions are fixed: an independent Google workbook with the
`Opportunity_Recommendations` tab, authorized-user OAuth, project owner/user as
operational, rollback, and kill-switch authority, one operation, mandatory
readback, no automatic retry on unknown results, the logical audit location
`95_Production Canary/Opportunity Intelligence/audit/operation_<operation_id>.json`,
and a one-business-day observation window. Before any environment binding or
production promotion, the exact workbook/Drive binding, OAuth principal, ACL,
trusted identity provider/role mapping, persistent audit binding/retention and
production contracts must be created or verified. A production implementation
must add durable execution receipts, target ACL verification, staging/readback
and rollback controls. The current proposal contracts remain
`DRAFT_NOT_APPROVED` with `x-production-activation=false`.

```ini
PHASE1_CANARY_WRITER_READINESS = READY
PRODUCTION_ACTIVATION = NOT_AUTHORIZED
PRODUCTION_MUTATION = 0
```
