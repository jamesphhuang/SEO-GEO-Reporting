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
