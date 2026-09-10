# Luna handoff prompt

將以下提示詞完整貼給 **GPT-5.6 Luna，極高 reasoning**：

你要接手 SHOPLINE SEO / GEO Reporting 的 Content & Search Opportunity Intelligence Layer。本次只完成WP1：contract proposals的離線驗證器與synthetic fixtures，完成即停止，不自動展開下一包。用繁體中文說明，先講假設與完成標準，讀callers/contracts/tests，再做最小改動。

Project path：`/Users/pohsunhuang/Library/CloudStorage/GoogleDrive-james.ph.huang@shopline.com/我的雲端硬碟/SEO／GEO Reporting/99_專案程式`。交接盤點日2026-09-10；乾淨 integration branch `docs/opportunity-intelligence-foundation`；`ARCHITECTURE_FOUNDATION_SHA=9376711`（`docs(opportunity): design opportunity intelligence layer`）；`HANDOFF_BASELINE_SHA=692f475`（`docs(opportunity): record integration baseline`）；`CURRENT_HANDOFF_HEAD` 以 branch HEAD 與 remote ref 實測（不在自身 commit 內硬編 SHA）；fetch後origin/main `4e30cec2a7cb446c0defa06b315c0b295a01b9af`。原 dirty worktree 不在這個 branch；你必須先核對現在HEAD/dirty，不盲信這些舊值。

先依序讀 `docs/opportunity-intelligence/CURRENT_STATE.md`、`NEXT_TASK.md`、`ARCHITECTURE.md`、`CONTRACT_DESIGN.md`、`SCORING_MODEL.md`、`CONFIDENCE_MODEL.md`、`TEST_STRATEGY.md`、`VALIDATION_RESULTS.md`。source語義查 `DATA_SOURCE_ROLES.md`，entity/rules查`OPPORTUNITY_MODEL.md`，failure/freshness查`EVIDENCE_FRESHNESS_POLICY.md`。完整roadmap在`ROADMAP.md`；不要把roadmap全部執行。

Architecture採C-lite immutable evidence + pure engine + human review + report projection，沒有production activation。Ahrefs多endpoint小量probe成功但scope/競品/budget未批准；Workduo在前一session可讀，舊collector仍沿用snapshot；Google live SERP結構化capture未驗。score採三個固定profile、ordinal0–4、missing不補零不reweight、score與confidence分開。Business Actual只有approved source可用，GA4 CTA不是formal成功，Ahrefs流量是THIRD_PARTY_ESTIMATE，source不同不能當分母。既有報表SQL顯示有歷史owner例外，但不可延伸為新層正式商業value/outcome。

WP1 allowed files：新增`reporting/opportunity/proposal_validation.py`（必要空`__init__.py`）、`tests/test_opportunity_proposals.py`、`tests/fixtures/opportunity/*.json`；兩份`contracts/ahrefs_scope.v1.proposal.json`、`contracts/opportunity_contract.v1.proposal.json`僅能為已證明的schema矛盾做最小修正，保留DRAFT/禁止production；只更新CONTRACT_DESIGN、TEST_STRATEGY、VALIDATION_RESULTS、NEXT_TASK、LUNA_HANDOFF的本包結果。不得改權重與business決策。

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
