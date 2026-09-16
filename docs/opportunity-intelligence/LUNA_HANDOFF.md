# Luna handoff prompt

將以下提示詞完整貼給 **GPT-5.6 Luna，極高 reasoning**：

WP2 已完成本包實作：branch `feat/ahrefs-readonly-ingestion`；以 `WP2_BASELINE_SHA=8491d7c0914791498811b868f3aafb5af3deaa84` 為基線。新增 `reporting/opportunity/sources/ahrefs.py` 與 17 個 offline tests；Organic Keywords/Competitors live smoke 各 1 row、50 units；Content Gap dedicated endpoint unavailable，故 `WP2_AHREFS_INGESTION_READINESS=PARTIAL`。完整 regression 為 107 tests PASS。adapter 沒有 provider write、Sheets、Apps Script、scheduler 或 Opportunity Engine。

下一個唯一任務是 **WP3：建立版本化 canonical entity registry**；不要開始 scoring、GSC/GA4/SF joins、SERP/Workduo、UI 或 production write。

你要接手 SHOPLINE SEO / GEO Reporting 的 Content & Search Opportunity Intelligence Layer。WP1 已完成；本次只完成下一個唯一任務 WP2：Ahrefs scope-approved 的 read-only ingestion adapter，完成即停止，不自動展開 WP3。用繁體中文說明，先講假設與完成標準，讀callers/contracts/tests，再做最小改動。

Project path：`/Users/pohsunhuang/Library/CloudStorage/GoogleDrive-james.ph.huang@shopline.com/我的雲端硬碟/SEO／GEO Reporting/99_專案程式`。交接盤點日2026-09-10；WP1 branch `feat/opportunity-contract-validator`；`WP1_BASELINE_SHA=0b63c66f0c14331fabb0dd2d72e820147e8cd758`；`ARCHITECTURE_FOUNDATION_SHA=9376711`；`HANDOFF_BASELINE_SHA=692f475`；`CURRENT_HANDOFF_HEAD` 與最新 `origin/main` 均先以 Git 實測，不在自身 commit 內硬編 SHA。原 dirty worktree 不在這個 branch；你必須先核對現在HEAD/dirty，不盲信這些舊值。

先依序讀 `docs/opportunity-intelligence/CURRENT_STATE.md`、`NEXT_TASK.md`、`ARCHITECTURE.md`、`CONTRACT_DESIGN.md`、`SCORING_MODEL.md`、`CONFIDENCE_MODEL.md`、`TEST_STRATEGY.md`、`VALIDATION_RESULTS.md`。source語義查 `DATA_SOURCE_ROLES.md`，entity/rules查`OPPORTUNITY_MODEL.md`，failure/freshness查`EVIDENCE_FRESHNESS_POLICY.md`。完整roadmap在`ROADMAP.md`；不要把roadmap全部執行。

Architecture採C-lite immutable evidence + pure engine + human review + report projection，沒有production activation。Ahrefs多endpoint小量probe成功但scope/競品/budget未批准；Workduo在前一session可讀，舊collector仍沿用snapshot；Google live SERP結構化capture未驗。score採三個固定profile、ordinal0–4、missing不補零不reweight、score與confidence分開。Business Actual只有approved source可用，GA4 CTA不是formal成功，Ahrefs流量是THIRD_PARTY_ESTIMATE，source不同不能當分母。既有報表SQL顯示有歷史owner例外，但不可延伸為新層正式商業value/outcome。

WP1 result：`reporting/opportunity/proposal_validation.py`、`tests/test_opportunity_proposals.py` 與 synthetic context/negative inventory 已完成；20 new tests、90 total tests PASS。validator 僅 offline，proposal 仍是 DRAFT；不要重做 WP1，也不要把 schema proposal 改名成 active contract。

WP2 allowed direction：新增 `reporting/sources/ahrefs.py`、local evidence adapter、sanitized request manifest 與 fixtures，僅能使用已批准 scope/country/mode/select/limit；維持 `THIRD_PARTY_ESTIMATE`，不可寫正式 rows。WP2 不得修改既有 reporting modules、formal contracts、production Sheets、Recommendations、Next_Steps、credentials、UI 或 scheduler。

Forbidden files/scope：`outputs/**`、原有`reporting/*.py`、舊Apps Script模板、三份formal contracts、另一個HTML report app、credentials/config/runtime、所有production Sheets/Recommendations/Next_Steps、live ingestion、UI、scheduler。原有dirty的v1 README、v2 report_data.json、business_metric_source_resolution目錄、weekly_report_2026_09_01_07目錄是範圍外先前工作，保持原樣；有新UNKNOWN dirty時停止mutation。

實作schema validation與semantic checks兩層：refs與source解析、unique counts、profile/bands/score/bounds、missing business與scope、required freshness、review identity mock/exact revision hash、時間順序。JSON Schema的`x-semantic-invariants`只是文字，必須真的寫check；不要把approval_state字串當human authentication。本輪用本地mock reviewer，日後WP10才串真實身份。所有tests deterministic、無live API，positive synthetic records與negative fixtures都要有；不要把真實keyword/business payload放tests。

Runtime：系統python3是3.9且不足，bundled Python缺jsonschema；`../97_Runtime/gsc-mcp/bin/python3.12`已確認有jsonschema。從repo root執行：

```sh
PATH='/Users/pohsunhuang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:'"$PATH" PYTHONDONTWRITEBYTECODE=1 '../97_Runtime/gsc-mcp/bin/python3.12' -m unittest discover -s tests -p 'test_opportunity_proposals.py'
PATH='/Users/pohsunhuang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:'"$PATH" PYTHONDONTWRITEBYTECODE=1 '../97_Runtime/gsc-mcp/bin/python3.12' -m unittest discover -s tests
git diff --check
```

缺依賴要明確報錯，不能skip成pass或自行改runtime。前輪baseline在bundled Python+Node下70 tests通過；本輪需自己驗證。完成標準與停止條件以NEXT_TASK為準：遇UNKNOWN dirty、必改forbidden files、需business裁決、需live/production、缺依賴且不能安全解決時停止受影響工作並說明。不能讀/輸出API key、token、credential，不能收集customer name/email/phone/raw lead rows；只用aggregate或synthetic，sanitize錯誤，不log原始敏感input。

Git開始先fetch/status/HEAD/origin/main/lineage；不reset/stash/清理原有檔，不刪未知worktree。没有明確授權不commit/push；若獲授權，只explicit stage WP1 allowlist，獨立commit `test(opportunity): validate contract proposals offline`，禁止git add .、force push、amend unrelated commit。最終繁中回報Summary、Files changed、Verification、Not verified、Risks or follow-ups；列實際test結果，更新durable交接後停止。
## Previous handoff — WP3 complete

WP3 baseline：da9f1d6aa6384eba9eb9c463605c8d1aa3875ede。
branch：feat/opportunity-canonical-registry。

本包已完成 offline canonical entity registry：TOPIC、KEYWORD、QUERY、PROMPT、
URL、COMPETITOR、BUSINESS_THEME；typed deterministic IDs、Unicode/width/text
normalization、保守 URL policy、typed relations、provenance、candidate/approved/
rejected review states、referential integrity、duplicate/conflict detection、
deterministic serialization/hash 與 proposal schema 均已測試。Keyword、Query、
Prompt 保留不同 observation grain；metrics 不進 identity；沒有 live API、LLM、
fuzzy clustering、production write 或正式 Brand Dictionary mutation。

Registry proposal schema：contracts/canonical_registry.v1.proposal.json。
Synthetic fixture：tests/fixtures/opportunity_registry/synthetic_registry.json。
已知 HTTP/HTTPS、www、trailing slash、redirect/canonical equivalence 以 policy gap
保留，不自動合併。RULE_BASED relation 不得自行 APPROVED；approved mapping 需要
opaque reviewer ID。

WP3_CANONICAL_REGISTRY_READINESS = READY。下一個唯一工作是 WP4 evidence /
candidate immutable store；不要開始 WP5 scoring、cross-source joins、derived
Content Gap、live integrations、UI 或 production activation。

## Current handoff — WP4 complete

WP4 baseline：`28374fd2302685ce5bf060dc9292df3a679cf1e0`。
branch：`feat/opportunity-immutable-store`。

本包新增 offline local append-only Evidence Store、Candidate Store 與 run manifest。
Evidence/Candidate 分離；revision 只能 append，supersedes chain 連續，candidate
refs 固定 evidence revision + content hash。相同 revision + hash idempotent；
collision、gap、tamper、date/time、non-finite、source semantics 與 WP3 dangling
entity refs fail closed。READY/PARTIAL/STALE/FAILED/NOT_AVAILABLE 與 null missing
原樣保存，Ahrefs 維持 `THIRD_PARTY_ESTIMATE`。

proposal：`contracts/opportunity_store.v1.proposal.json`，仍未 activation。
22 個 WP4 tests 加上既有測試共 **149 tests PASS**；security scan、AST、JSON/schema、
`git diff --check` 通過；production mutation=0。

`WP4_IMMUTABLE_STORE_READINESS = READY`。下一個唯一工作是 **WP5：SEO engine v1
(Ahrefs + GSC + SF)**；不要在本輪開始 scoring、cross-source joins、GA4/SERP/
Workduo、UI、review bridge 或 production activation。

## Current handoff — WP5 complete

WP5 baseline：`202c41e88a54e0805158f41523acbb430934078b`。
branch：`feat/seo-opportunity-engine-v1`。

本包完成 offline `OpportunityEvaluationInput`、SEO rule engine、fixed scoring、
independent confidence、deterministic preview、WP1 proposal validation bridge 與
WP4 Candidate Store append bridge。只接受 normalized synthetic AHREFS/GSC/SF；每個
persisted candidate pin exact evidence revision/hash，沒有 auto approval。`CONTENT_GAP`
仍回傳 `POLICY_GAP`，不自行推導 negative existence。

17 個 WP5 tests 加上既有套件共 **166 tests PASS**；2 schemas、AST、explicit
date/date-time、`git diff --check` 與 scoped security/production-boundary scan 均
PASS；production mutation=0，沒有 live query。

`WP5_SEO_ENGINE_READINESS = READY`。下一個唯一工作是 **WP6 — GA4 quality diagnostics**；
本輪完成後停止，不開始 WP6。未 push remote。

## WP6 implementation handoff（2026-09-10）

基線 `cb01dc032e9c89313e6997b3d65327c7f777e9f1`，branch
`feat/opportunity-ga4-quality-diagnostics`。新增 `reporting/sources/ga4_quality.py`、
`reporting/opportunity/ga4_diagnostics.py`、`ga4_preview.py` 與
`contracts/ga4_quality_diagnostics.v1.proposal.json`，並保留 A–L synthetic fixture。

輸入是 offline normalized GA4 evidence；PAGE_LEVEL 僅接受 WP3 exact URL registry join，
SITE_WIDE_CONTEXT 只作 contextual conflict。Evidence 與 diagnostic 都 append-only，
固定 pin evidence id/revision/hash；GA4 不改 WP5 score、confidence 或 candidate
review state。CTA、AI Assistant attribution、GSC-vs-GA4 conflict 與
missing/stale 狀態均保持 diagnostic/policy gap。

15 個 WP6 tests 加上既有套件共 **181 tests PASS**；schema、fixtures、AST、explicit
date/date-time、`git diff --check` 與 scoped security/production-boundary scan 均 PASS。
沒有 live GA4 或其他 source query，沒有 production mutation。`WP6_GA4_QUALITY_READINESS = READY`。
下一個唯一工作是 **WP7 — SERP validation**；本輪停止，未開始 WP7、未 push。

## Current handoff — WP7 complete（2026-09-10）

WP7 clean baseline：`16c6c74248a0d96f8357b21d9eca45e3668d16eb`；branch `feat/opportunity-serp-validation`，worktree `/private/tmp/seo-geo-wp7-serp`。本輪只實作 offline shortlist SERP validation：normalizer、bounded injected collection、deterministic composition rules、proposal schemas、preview、synthetic A–N fixtures 與 append-only validation history。exact canonical query、scope、owned URL、approved competitor mapping 與 provider provenance 是必要 identity；NOT_AVAILABLE、STALE、FAILED、PARTIAL、unknown domain 與 mixed intent 均保留，不補零、不把缺失轉 false、不把 cached Ahrefs 當 live。

Candidate 與 SERP validation 各自 pin `evidence_id + revision + content_hash`；validation status 不會改 WP5 score/confidence 或 review state，`approval_transition_allowed=false`。WP7 targeted **9 tests**、full regression **190 tests**、schema/AST/JSON/date-time、diff、security 與 production boundary 全部 PASS。未 push、未建立 PR、未 merge main，也未開始 WP8。下一個唯一工作是 **WP8 — GEO fixed sample layer**。

## Current handoff — WP8 complete

WP8 baseline：`da1f5e53a446bbe903d49291de9c27d8eb0d44ca`；branch `feat/opportunity-geo-fixed-sample`，worktree `/private/tmp/seo-geo-wp8-geo`。

本輪完成 offline fixed Workduo sample registry、normalizer、GEO diagnostic rules、preview、proposal schemas、synthetic A–P fixtures 與 append-only diagnostic store。固定 sample 保留 sample/version/revision、prompt population、scope、有效日期與 hash；所有 Prompt/Topic/URL/Competitor join 都走 canonical registry。Mention/citation 分離，missing/STALE/FAILED/NOT_AVAILABLE 不轉零；sample drift 形成 comparability gap；unknown domain 不建立 entity。GEO 只 enrich existing candidate，保留 WP5 score/confidence/review state，不自動 APPROVED，SERP/GA4 cross-channel conflict 原樣保留。21 WP8 tests 與 full regression 211 tests PASS；schema/fixture/AST/date-time/diff/security/production-boundary checks PASS，沒有 live query 或 production mutation。

`WP8_GEO_FIXED_SAMPLE_READINESS = READY`。下一個唯一工作是 **WP9 — Opportunity preview / UAT report**；不要在本輪開始 WP9、建立 WP9 branch、push 或 merge。

## Current handoff — WP9 complete（2026-09-11）

`WP9_BASELINE_SHA=4188fe631c1f6368fe64cf964a97d518c1a5382d`；branch
`feat/opportunity-preview-uat`，worktree `/private/tmp/seo-geo-wp9-preview`。WP9 只在離線
synthetic data 上建立 read-only report projection；沒有 live source、production report、
Google Sheets、Apps Script、Recommendations、Next Steps 或 scheduler mutation。

`reporting/opportunity/report_projection.py` 保留 WP4–WP8 candidate/evidence/diagnostic
revision、content hash、日期、estimate/missing/stale/conflict、Score/Confidence separation、
SERP_NOT_CHECKED、GA4 `DIAGNOSTIC_ONLY`、GEO comparability 與 cross-channel conflict。
首屏 max 20、四組分區與 UAT-only IDs 均 deterministic；HTML 只有 local escaped output，
不支援 production activation。

WP9 targeted **23 tests PASS**、full regression **234 tests PASS**；proposal schema、A–P
fixture、AST、explicit date/date-time、`git diff --check`、security/PII/live-call 與
production-boundary scans 全部 PASS，production mutation=0。`WP9_OPPORTUNITY_PREVIEW_READINESS = READY`。
本輪只建立 local commit，未 push、未建 PR、未 merge。下一個唯一工作是 **WP10 — Human review /
recommendation bridge**；不要開始 WP10。

## Current handoff — WP10 complete（2026-09-11）

Baseline `356285f80a1a4bd4a98425a0bc561e7b65141455`；branch
`feat/opportunity-human-review-bridge`；clean worktree `/private/tmp/seo-geo-wp10-review`。
新增 `review.py`、`review_bridge.py`、兩份 proposal schema、A–P synthetic fixture 與
26 個 targeted tests。Review 是 authenticated HUMAN actor 的 first-class decision record，
以 candidate revision/hash、evidence refs、optional GA4/SERP/GEO refs、policy、notes
provenance 與 semantic hash 保存。Bridge 只能從 exact human APPROVE 建立，且只到 UAT /
PREVIEW；Score/Confidence、GA4、SERP、GEO、conflicts 與 Candidate history 均不被改寫。

Review 與 bridge stores 都是 append-only JSONL，支援 contiguous revisions、supersedes、
idempotency、tamper detection 與 stale/superseded rejection。Missing/STALE、SERP_NOT_CHECKED、
policy/capability gap、revision/hash mismatch、未 adjudicate conflict 與任何非 human actor
均 fail closed。`next_steps_written=false`、`production_mutation=false`；沒有正式
Recommendations、Next Steps、Sheets、Apps Script、scheduler、live query、PR、push 或 merge。

WP10 targeted **26 tests PASS**，full regression **260 tests PASS**；schema、fixtures、AST、
date/date-time、`git diff --check`、security/PII/live-call/production-boundary checks PASS，
production mutation=0。`WP10_HUMAN_REVIEW_BRIDGE_READINESS = READY`。只建立 local commit，
不要 push/merge，也不要開始或建立 WP11。下一個唯一任務是 **WP11 — Outcome tracking**。

## Current handoff — WP11 complete（2026-09-14）

Baseline `83745d36ff59b9dfa45313c43c125f3a014f8b94`；branch
`feat/opportunity-outcome-tracking`；clean worktree `/private/tmp/seo-geo-wp11-outcomes`。

WP11 新增 implementation event anchor、outcome evaluator、30/60/90D checkpoint projection、
append-only OutcomeStore、兩份 Draft proposal schema、A–P synthetic fixture 與 targeted tests。
正式 outcome 前必須有 exact authenticated human APPROVE、Bridge revision 與明確
IMPLEMENTED deployment/change anchor；MONITOR/DO_NOTHING 只保留 observation-only 狀態。

所有 observations 都 pin `evidence_id + revision + content_hash`，baseline/follow-up 依
Asia/Taipei 28 complete days 比較，同 scope/population/methodology 與 GEO sample revision
必須一致。GSC、GA4、SERP、GEO、SF/CrUX、Business 的 source semantics 分離；GA4 CTA 不作
conversion，Business 無 attribution contract 不形成正式 outcome，SERP timestamp 不併成
period rank。WON 需要 primary、independent support 與 guardrails；missing、FAILED、STALE、
NOT_AVAILABLE、NOT_COMPARABLE 均保留，沒有 causal 或 ROI 文字。

WP11 targeted **21/21 PASS**；fresh full regression **281/281 PASS**。Schema、fixtures、AST、
explicit date/date-time、`git diff --check`、security/PII/live-call/production-boundary
checks PASS，production mutation=0。`WP11_OUTCOME_TRACKING_READINESS = READY`。

本輪只允許建立 local commit；不 push、不建 PR、不 merge、不開始或建立 WP12。下一個唯一
任務依 ROADMAP 是 **WP12 — Production hardening（最後gate）**。

## Current handoff — WP12 initial production hardening implementation before consistency probe（2026-09-14）

Baseline `6415c9e086f6afe419076461fa486d2c457f89a6`；branch
`feat/opportunity-production-hardening`；clean isolated worktree，原 dirty worktree 未觸碰。
新增 offline hardening planner、activation/release manifest proposal contracts、A–T synthetic
fixture 與 30 個 targeted tests。

Hardening layer 計算 deterministic release manifest、planned/blocked operations、idempotency
keys、structured observability events 與 rollback/kill-switch plan。未知 environment、draft
contract、缺 explicit authorization、writer/target 不在 allowlist、stale/hash/revision/
conflict/schema/audit/source failure、secret/PII 與 scheduler attempt 都 fail closed；partial
write 永不宣稱 complete。Actual writes、production mutation 與 scheduler activity 全為 0。

Fresh regression **311/311 PASS**，WP12 targeted **30/30 PASS**；schema、fixture/JSON、AST、
date-time、`git diff --check`、security/PII/live-call/production-boundary checks PASS。
`WP12_PRODUCTION_HARDENING_READINESS = READY`，但 `PRODUCTION_ACTIVATION = NOT_AUTHORIZED`；
不得把 hardening PASS 視為 production activation。

本輪只建立 local commit；不 push、建 PR、merge、啟用 scheduler/writer、寫 Recommendations、
Next Steps、Sheets、Apps Script 或執行 live source。ROADMAP 沒有自動 WP13；production activation
需另行取得明確 owner authorization。

## WP12 repair record（2026-09-15）

Handoff consistency probe 初次結果為 `BLOCKED_HANDOFF_INCONSISTENCY`，因為部分安全語意仍只存在 fixture/docs。follow-up repair 將 required readiness gates、activation state/kill switch、revision/hash、audit、append-only cross-run idempotency、recursive secret/PII redaction、manifest lineage/test summary、partial receipt 與 structured rollback 實作為 runtime checks。修補沒有改寫 `884559049b0bb34751b2c46cb9b2b9b54041eacb`，沒有 push/PR/merge，亦沒有 production mutation；proposal contracts 仍為 `DRAFT_NOT_APPROVED` 且 activation false。
Repair 後 WP12 targeted **40/40 PASS**、fresh full regression **321/321 PASS**；schema、AST、JSON、date/date-time、`git diff --check`、security/PII/live-call/production-boundary checks 均通過，production mutation=0。

## Production Phase 1 Recommendation Canary Writer（2026-09-16）

以 `9f984b26e177cec109e8b3b5ac2053d6b0e62b43` 為 baseline 的 clean branch
`feat/opportunity-recommendation-canary-writer` 已完成 offline/UAT-only canary writer。
它以 exact human review → Recommendation Bridge lineage 為入口，只產生一筆 WriteIntent，將
allowlisted fields 送至注入的 synthetic target，強制 exact readback 與 append-only audit。
Untrusted identity、caller 自稱 authenticated、protected mutation、unknown target、timeout
without reconciliation、readback mismatch、audit failure 與 kill switch 都 fail closed。

WP Phase 1 **18/18**、WP12→WP1 **214/214**、fresh full regression **339/339 PASS**。
Contracts `recommendation_canary_writer.v1` 與 `google_sheets_target_binding.v1` 仍是
`DRAFT_NOT_APPROVED`、activation false。沒有 real workbook/tab、OAuth refresh/consent、
live source、production writer、scheduler、Apps Script 或 production mutation。

`PHASE1_CANARY_WRITER_READINESS = READY`；`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`。
Phase 1 logical design 已確認為 independent Google workbook、`Opportunity_Recommendations`、
authorized-user OAuth、project owner/user 的 operational/rollback/kill-switch authority、
最多一筆 operation、mandatory readback、unknown result no automatic retry，以及一個 business
day observation period；audit logical location 為
`95_Production Canary/Opportunity Intelligence/audit/operation_<operation_id>.json`。

下一個唯一任務是 **Phase 1 Canary Environment Binding**：建立專用 workbook、取得 exact
workbook/Drive binding、驗證 OAuth principal 與 ACL、建立 trusted human-review identity
binding，以及建立 persistent audit binding。這些 exact environment values 尚未建立或驗證；
本地 commit 完成後仍不得自行 push、PR、merge、Google write 或 production activation。


## Phase 1 Canary Environment Binding handoff（2026-09-16）

Fresh `origin/main` baseline 為 `17f2669de0e49f33fb51d3a545b2af1698df3e29`；在隔離
branch `feat/opportunity-canary-environment-binding` 完成 environment binding。精確
Drive root、`95_Production Canary/Opportunity Intelligence/` 資料夾鏈、獨立 workbook、
`Opportunity_Recommendations` tab 與 `audit/` folder 均已建立並 readback。真實 resource ID
只保存在 external non-secret binding metadata；不可搬回 repository source/docs。

`principal://authorized-user-oauth/runtime` 已由 profile 與 bounded Drive/Sheets 操作驗證，
current principal 對 workbook/audit path 具 owner/writer-capable access；未導入 service account、
未讀取或輸出 token/client secret、未修改 ACL。Canonical 23 欄 header 是唯一 structural
write，target data rows = `0`；沒有 Recommendation write、WriteIntent 或 production audit receipt。

`CANARY_ENVIRONMENT_BINDING = READY`，但 trusted human-review identity/provider 仍
`NOT_VERIFIED`，不可把 OAuth identity 當成 reviewer authentication。`PRODUCTION_ACTIVATION =
NOT_AUTHORIZED`。下一個唯一任務是 **Phase 1 Zero-Write Production-Config Dry Run**；完成前
不得進入 live Recommendation write、scheduler 或 production activation。


## Phase 1 Canary Environment Binding finalization handoff（2026-09-16）

Owner decision 允許並確認 `shopline.com` domain-wide `reader` policy；workbook 與 audit
path 已 read-only verify 符合，未修改 ACL。Durable non-secret binding 已移至
`98_環境設定/opportunity-canary/environment-binding.json`；實際 resource refs 留在 external
config，不進 Git docs/source。

Readback 已確認 principal ref、Drive/workbook/tab/audit refs、23-field schema hash、
allowlist hash、ACL policy、`recommendation_row_count=0` 與 binding semantic hash 全部一致。
因此 `DURABLE_BINDING = VERIFIED`、`ACL_POLICY = APPROVED`、
`ZERO_WRITE_DRY_RUN_READINESS = READY`。

`TRUSTED_REVIEW_IDENTITY = NOT_VERIFIED`；OAuth principal 不等同 human-review provider。
`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`。下一個唯一任務是 **Phase 1 Zero-Write
Production-Config Dry Run**，不得在本輪執行。


## Phase 1 Zero-Write Production-Config Dry Run handoff（2026-09-16）

Dry-run 只使用 durable external binding，不讀取 credential file，不執行 Google business
write。真實 workbook/tab/schema/ACL/audit metadata 以 read-only path 驗證；pre/post
Recommendation rows = `0`，audit folder 沒有新增 receipt。

`DryRunWritePlan` 僅保存 operation、exact Candidate/Review/Bridge refs、allowlisted planned
fields、payload hash、deterministic idempotency key、readback/audit plan 與 kill-switch state；
不建立正式 `WriteIntent`、production idempotency ledger 或 audit receipt。

`ZERO_WRITE_CONFIG_DRY_RUN = PASS`；`LIVE_WRITE_READINESS = BLOCKED`。三個預期 blocker
為 trusted human-review identity 未驗證、proposal contracts 未批准、production activation 未授權。
下一個唯一任務是 **Phase 1 Trusted Review Identity Binding**，本輪停止。
