# Phase 1 Trusted Review Identity

Phase 1 reviewer trust uses verified Google Workspace OIDC output. The provider adapter must verify
the ID token signature, issuer, audience and expiry before constructing runtime evidence. The stable
Google subject is converted in memory with the fixed namespace
`google-workspace-reviewer-v1:` and SHA-256; raw subject and full email are never stored in Git,
fixtures, logs or documentation.

The external binding is `98_環境設定/opportunity-canary/trusted-review-identity.json`. It is not a
production contract and contains only provider, pseudonymous subject reference, `shopline.com`,
role `RECOMMENDATION_APPROVER`, scope `PHASE1_CANARY`, ACTIVE status, revision, verification method,
same-person waiver, inheritance/expansion flags, timestamp and semantic hash. It must reject hash or
revision drift on readback.

The runtime verifier accepts typed provider evidence only. It requires exact provider, subject ref,
Workspace domain, role, scope, binding revision and semantic hash. `authenticated=true`, caller
email, caller domain, caller role, caller subject ref and an unverified claim map all fail closed.

Phase 1 permits the writer owner and reviewer to be the same natural person only through
`APPROVED_PHASE1_CANARY_ONLY`: one operation, `PHASE1_CANARY`, no production inheritance and no
automatic scope expansion. Writer principal and reviewer subject ref remain different identity models.

This binding does not create a HumanReview event, Recommendation, WriteIntent, audit receipt or
production authorization. `LIVE_WRITE_READINESS` remains blocked until production contracts are
approved and production activation is separately authorized.
