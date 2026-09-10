## Current baseline

Repo：`/Users/pohsunhuang/Library/CloudStorage/GoogleDrive-james.ph.huang@shopline.com/我的雲端硬碟/SEO／GEO Reporting/99_專案程式`。
WP1 branch `feat/opportunity-contract-validator`；`WP1_BASELINE_SHA=0b63c66f0c14331fabb0dd2d72e820147e8cd758`；architecture foundation `9376711`；handoff baseline `692f475`；最新 fetch 後 `origin/main` 以實測為準。原有四組dirty paths列CURRENT_STATE，皆範圍外保留。bundled runtime baseline 70 tests通過，WP1 suite 20 tests通過。

## Current blocker

WP1 offline validator 已完成；正式scope、budget、business relevance、UAT destination與review身份仍需各自 owner/approval 流程，不能由本 validator 代替。這些限制阻塞 live ingestion 與 production activation，但不阻塞下一個 offline/read-only 分包。

## Next single task

**WP2：建立 Ahrefs scope-approved 的 read-only ingestion adapter。** 只處理已批准 scope、明確 country/mode/select/limit、typed third-party estimate evidence 與 immutable manifest；不得開始 topic clustering、scoring、Opportunity Engine、UI 或 production write。scope、competitor、budget 或 capability 未批准時只保留 fixture path，不能 live ingest。

## Files allowed

- 新增 `reporting/opportunity/proposal_validation.py`（必要時空 `__init__.py`）。
- 新增 `tests/test_opportunity_proposals.py`、`tests/fixtures/opportunity/*.json`。
- 若測試證明proposal矛盾，可最小修改 `contracts/ahrefs_scope.v1.proposal.json`、`contracts/opportunity_contract.v1.proposal.json`，必須仍為DRAFT且記錄理由；不得改weight/商業決策。
- 更新 `docs/opportunity-intelligence/CONTRACT_DESIGN.md`、`TEST_STRATEGY.md`、`VALIDATION_RESULTS.md`、`NEXT_TASK.md`、`LUNA_HANDOFF.md` 的本包驗證與交接；不擴工作範圍。

## Files forbidden

`outputs/**`、原有`reporting/*.py`、`apps_script/**`、現有monthly apps_script、三份正式contracts、`seo_geo_html_report_2026-08-31/**`、credential/config/runtime檔、正式Google Sheets、Recommendations、Next_Steps。不能整理原有dirty產物。

## Acceptance criteria

schema與語義驗證分開，錯誤code穩定、不輸出敏感input。驗證ref解析/來源、evidence_count、score/profile/bounds、inactive band、missing business、scope approval、approved revision/hash與時間順序；用mock immutable evidence/review fixtures。有效DISCOVERED/VALIDATED/APPROVED(mock human)可驗，無人工事件或production environment必拒。近義字分群和API adapters不在此包。

## Tests

從repo root，使用已確認有jsonschema的runtime：

```sh
PATH='/Users/pohsunhuang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:'"$PATH" PYTHONDONTWRITEBYTECODE=1 '../97_Runtime/gsc-mcp/bin/python3.12' -m unittest discover -s tests -p 'test_opportunity_proposals.py'
PATH='/Users/pohsunhuang/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin:'"$PATH" PYTHONDONTWRITEBYTECODE=1 '../97_Runtime/gsc-mcp/bin/python3.12' -m unittest discover -s tests
git diff --check
```

至少fixtures：missing ref、wrong source、duplicate ref/count、invalid enum、production env、null score批准、wrong score、profile switching、stale required evidence、human event缺失、hash mismatch、future timestamps與valid records。無網路；runtime缺jsonschema就明確報依賴問題，禁止skip成綠燈。

## Stop conditions

新UNKNOWN dirty、原有dirty變動、必須改forbidden files、schema矛盾需要商業決定、runtime依賴不可用、validation需live access、用戶要求擴到production或scheduler，都先停止相應mutation並回報。依賴不可用可提出最小修復，不自行改整個runtime。

## Git instructions

開始 `git fetch origin`、`git status --short`、branch/HEAD/main/merge-base核對，分類dirty。不切分支、不stash/reset原有工作。文件未commit時先確認檔案存在；若別人已更新baseline，重讀diff再評估。若需要獨立分支，取得明確baseline後使用`codex/`前綴且不搬移未知dirty。沒有明確授權不commit/push；若授權，explicit stage本包allowlist，commit `test(opportunity): validate contract proposals offline`。禁止`git add .`、force push、amend他人commit。
