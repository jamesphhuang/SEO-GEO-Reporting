## Current baseline

Repo：`/Users/pohsunhuang/Library/CloudStorage/GoogleDrive-james.ph.huang@shopline.com/我的雲端硬碟/SEO／GEO Reporting/99_專案程式`。
`WP2_BASELINE_SHA=8491d7c0914791498811b868f3aafb5af3deaa84`；WP2 branch `feat/ahrefs-readonly-ingestion`；WP1 main integration 已完成。原有 dirty paths 列 CURRENT_STATE，皆範圍外保留。

## WP2 result

WP2 已新增 scope-approved、read-only Ahrefs adapter：Organic Keywords 與 Organic Competitors 可透過 injected transport bounded ingest；Content Gap 因 runtime 沒有 dedicated endpoint 保持 `UNAVAILABLE/CAPABILITY_GAP`。adapter 只產 local/test/output artifacts，含 raw/normalized 分離、run manifest、client budget、row/page/request/unit caps、bounded retry、failure semantics、source-class enforcement 與 deterministic normalized hash。

`WP2_AHREFS_INGESTION_READINESS = PARTIAL`。Organic Keywords、Competitors、offline normalization 與 live smoke 通過；scope/competitor/budget owner approval、Content Gap capability、production activation 尚未完成。

## Next single task

**WP3：建立版本化 canonical entity registry。** 只處理 query/keyword/prompt/URL/topic mappings、deterministic dedup 與 mapping revision manifest；不得開始 topic scoring、Opportunity Engine、GSC/GA4/SF joins、SERP/Workduo enrichment、UI 或 production write。

## Files allowed

- 新增 `reporting/opportunity/entities.py` 與必要的 mapping utilities。
- 新增 `tests/test_opportunity_entities.py`、`tests/fixtures/entities/*.json`。
- 更新 `docs/opportunity-intelligence/CURRENT_STATE.md`、`VALIDATION_RESULTS.md`、`NEXT_TASK.md`、`LUNA_HANDOFF.md` 的 WP3 驗證與交接；不改正式 contracts 或 production paths。

## Files forbidden

`outputs/**`、原有 `reporting/*.py`、`apps_script/**`、正式 contracts、`seo_geo_html_report_2026-08-31/**`、credential/config/runtime 檔、正式 Google Sheets、Recommendations、Next_Steps、scheduler、Opportunity Engine。

## Acceptance criteria

WP2 acceptance 已達成的部分：bounded Organic Keywords/Competitors read-only ingestion、normalized `THIRD_PARTY_ESTIMATE` evidence、manifest、client caps、dedup/retry/failure/stale guards、synthetic fixtures 與 live smoke。Content Gap 依 capability gap 保持 unavailable；不把 WP2 宣稱為完整 Opportunity coverage。

## Tests

Fresh bundled runtime discovery：`107 tests` 通過（既有90 + WP2 17）；WP2 fake-transport tests 不呼叫 live Ahrefs。Proposal schema、date/date-time 與 `git diff --check` 保持既有驗證；live smoke 獨立記錄 rows/units，不把 probe 當 full ingestion。

## Stop conditions

新 UNKNOWN dirty、原有 dirty 變動、必須改 forbidden files、需要 business 裁決、需要 production/live bulk access、Content Gap capability 仍未明確、或 runtime 依賴不可用時，停止相應 mutation 並回報。不得把 capability gap 靜默轉成空 rows。

## Git instructions

WP2 branch 只 stage 本包 allowlist，commit `feat(opportunity): add bounded Ahrefs ingestion`；正常 push `feat/ahrefs-readonly-ingestion`，不直接 main、不 force push、不使用 `git add .`，原 dirty worktree 不搬移。
