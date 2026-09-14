# WP12 — Production hardening（最後gate）

WP12 以 `WP12_BASELINE_SHA=6415c9e086f6afe419076461fa486d2c457f89a6` 為基線，
建立離線、proposal-only 的 production promotion hardening layer。這個 layer 驗證
未來進入 production 前的 writer、target、authorization、idempotency、rollback、
audit 與 observability 邊界；它不啟用 production。

## Activation boundary

`contracts/production_activation.v1.proposal.json` 是 activation gate 的 proposal，
`x-proposal-status=DRAFT_NOT_APPROVED` 且 `x-production-activation=false`。允許的
activation state 只有 `DRY_RUN`、`NOT_AUTHORIZED`、`BLOCKED`、`REVOKED`；
`APPROVED`、`ACTIVE`、`PRODUCTION` 不屬於本輪狀態。WP10 的 Candidate / Review
approval、WP11 的 outcome readiness、WP12 測試 PASS 都不能替代一個獨立的 production
activation authorization。

`reporting/opportunity/production_hardening.py` 的 `dry_run_promotion()` 只讀取
immutable artifact metadata，計算 planned/blocked operations、idempotency key、
release manifest 與 structured events。它不呼叫 GSC、GA4、Workduo、Google Search、
Ahrefs、Screaming Frog 或 CrUX，也不打開 workbook、Sheets、Apps Script、
Recommendations、Next Steps、runtime production store 或 scheduler。

## Writer and target boundary

每筆 planned operation 必須攜帶 artifact type、entity ID、revision、target、operation、
writer 與 semantic hash。writer 和 target 都必須在 activation proposal 的 allowlist。
Recommendations、Next Steps、production workbook、Apps Script 與 production outcome
store 在本輪均不允許寫入；只可在 UAT dry-run 中列為 planned/blocked operation。

所有 production-style operation 都必須有讀回可用的 idempotency key。相同 key 與相同
semantic hash 是 `IDEMPOTENT_NO_OP`；相同 key 搭配不同 hash 是
`IDEMPOTENCY_CONFLICT`。相同 input 重跑不會產生第二筆正式紀錄。

## Failure and rollback semantics

硬化層採 fail-closed：draft contract、缺少 explicit production authorization、未知
environment、未授權 writer/target、missing idempotency key、stale critical evidence、
hash/revision mismatch、unresolved conflict、schema/audit failure、source unavailable
與 active kill switch 都會產生 blocked/failed 結果。`WRITE_THEN_AUDIT_FAIL` 保留
`PARTIAL`，不得宣稱 `COMPLETE`；source timeout 與 write failure 保留 retryable
語義，不補零或假裝成功。

rollback 只會 disable 後續 writes、停用 writer/scheduler 並要求 readback；immutable
history 不刪除，只能用 superseding 或 corrective revision。`rollback_state`、
`kill_switch` 與 `history_policy` 會落在 release manifest。

## Dry-run and release manifest

`contracts/production_release_manifest.v1.proposal.json` 描述 offline/UAT release
manifest，包含 main SHA、WP/contract versions、test summary、activation status、
approved writers、scheduler state、known policy/source gaps、planned/blocked operations、
rollback instructions、observability events 與 semantic hash。manifest 的
`production_mutation` 與 `actual_write_count` 永遠為 `0`，scheduler state 永遠是
`DISABLED`。

Structured events 使用 `run_started`、`validation_passed`、`validation_failed`、
`write_planned`、`write_blocked`、`write_succeeded`、`write_failed`、`run_partial`、
`run_completed` 的既有語義集合；事件只保留 run/release/artifact/target/status/time/error
與 hash，不保存 chain-of-thought、credential、token 或 PII。secret-like 和 PII-like
欄位在 manifest 前即被拒絕，且敏感欄位名稱與值不會進入 blocked summary。

## Verification fixtures

`tests/fixtures/opportunity_hardening/scenarios.json` 是 synthetic、offline-only 的
A–T fixture inventory，覆蓋 dry-run success、authorization/contract gate、writer/target
allowlist、idempotency、audit/partial failure、source/stale/hash/revision errors、
unknown environment、rollback/kill switch、determinism、secret/PII、scheduler default-off
與 zero mutation。

本輪 readiness 的正式狀態是：

```ini
WP12_PRODUCTION_HARDENING_READINESS = READY
PRODUCTION_ACTIVATION = NOT_AUTHORIZED
PRODUCTION_ACTIVATION_READINESS = NOT_AUTHORIZED
```

後續若要真的 promotion，必須另取得明確 production activation authorization，並重新
驗證 approved contracts、writer ACL、scheduler approval、rollback、audit、dry-run
readback 與 live-source collector contract。WP12 本身不會建立 scheduler、啟用 writer、
寫入 production 或公開發布。
