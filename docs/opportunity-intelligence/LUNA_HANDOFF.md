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
