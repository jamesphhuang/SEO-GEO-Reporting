# Contract Approval Evidence Foundation

本文件描述 Phase 1 的 offline/UAT approval evidence foundation。它不批准任何
production contract，也不建立 Google、Drive、Sheets、ACL、scheduler 或 audit 寫入。

Phase 1 dependency set 固定為：`trusted_review_identity.v1`、`human_review.v1`、
`recommendation_bridge.v1`、`google_sheets_target_binding.v1`、
`recommendation_canary_writer.v1`、`production_release_manifest.v1`、
`production_activation.v1`。本清單是 review scope，並不代表任何一份 contract 已獲批准。

## Exact instance

每一份 approval 都 pin `contract_id`、`contract_version`、`revision` 與由 canonical semantic
fields 計算的 SHA-256 `semantic_hash`。任何一項改變都使既有 approval 失效，必須建立新的
approval；`supersedes`／`superseded_by` 只保存不可變的 lineage。

## Identity and waiver

Approver 必須是 provider-verified 的 pseudonymous identity，並以獨立
`CONTRACT_SEMANTICS_APPROVER` role 綁定到 `PHASE1_CANARY_ONLY`。同一自然人同時擔任
operational owner 與 semantics approver 時，必須使用獨立
`PHASE1_CANARY_CONTRACT_APPROVAL_WAIVER`；不可重用 reviewer 的 approval waiver。每次最多
一個 operation，未使用 approval 七日後失效，禁止 production inheritance 與 automatic scope
expansion。

## Receipts and invalidation

Receipt 僅保存 opaque refs、pins、scope、expiry、status、readback result 與 deterministic hash，
不得保存 raw email、Google subject、token、credential 或 secret。Revocation 是 append-only
receipt；有效 approval 加上有效 revocation 一律視為 invalid。過期與 superseded approval
同樣 fail closed。Rollback acknowledgement 必須 pin release、contract revision/hash、verified
identity、timestamp、reason 與 rollback target，不接受 boolean、button 或 docs-only evidence。

## Runtime gate

Verifier 必須同時比對 exact contract、approval、approver evidence、waiver、environment、target
與 operation count，成功只表示 `CONTRACT_APPROVAL_GATE = PASS`。它永遠回傳
`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`；activation 仍需獨立的使用者授權與另外的 production
contract gate。Receipt retention 的預設 policy 是至少 Phase 1 結束後一年，並受
`SUBJECT_TO_COMPANY_RETENTION_POLICY` 約束。

## Status

本 foundation 的 proposal contracts 皆為 `DRAFT_NOT_APPROVED` 且
`x-production-activation=false`。本地 synthetic tests 可建立暫存 receipt 以驗證語義，但正式
approval receipts、Recommendation records、audit receipts 與 production mutation 皆為零。
