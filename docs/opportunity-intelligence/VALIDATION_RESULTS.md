# VALIDATION_RESULTS

執行日2026-09-10。只報本輪實际檢查，不將測試計畫寫成已完成實作。

| Check | Result | Scope / limit |
| --- | --- | --- |
| git fetch origin | PASS | 最新main 4e30cec；clean integration branch ancestor已確認；原 dirty worktree未切換 |
| existing unittest suite，system Python 3.9 | FAIL | 47 runner-counted tests，5 errors；不支援type union + framework Node依賴未滿足 |
| existing unittest suite，bundled Python + Node | PASS | **70 tests，1.296s，OK**；fake transport單元測試，非live integration |
| Proposal Draft202012Validator.check_schema | PASS | 兩份schema符合draft 2020-12 meta-schema |
| Synthetic schema fixtures | PASS | 兩份positive shape records；不是business/source完整性驗證 |
| Negative shape fixtures | PASS | 12種變更均被拒絕，見下表 |
| Score weights | PASS | 三profile各總和100；synthetic missing-business例60–90；未實作engine scorer |
| Semantic validation gaps | CONFIRMED | 將evidence_count改999、lower_bound改99，純schema仍接受；WP1要補，不能宣称contract已強制執行 |
| Date-time checker | FIXED IN VALIDATION HARNESS | 首次負例`not-a-date`未被拒，因runtime缺format checker支援；改用datetime/date標準庫explicit callbacks後通過。正式validator仍待WP1 |
| NEXT_TASK headings | PASS | 嚴格只有指定9個heading，ONE NEXT TASK=WP1 |
| Existing dirty artifacts preservation | PASS | 本輪建檔前26個既有檔案SHA-256對照全相同；包括兩個tracked dirty files与兩個untracked目錄 |
| Bounded secret pattern scan | PASS | 僅新docs/examples/proposals；未發現Google API-key、OAuth token、GitHub token或private-key樣式；不是全repo安全稽核 |
| git diff --check | PASS | 已追蹤diff無whitespace error；新未追蹤檔另做JSON解析與文字檢查 |
| Final artifact audit | PASS | 23個新檔：19 Markdown、2 proposals、2 synthetic JSON；relative links全可解析、無trailing whitespace；4 JSON皆可解析 |
| Branch lineage audit | PASS | 7個本機branch tips皆為fetch後origin/main ancestor；未刪除或移動branch |

## Negative shape cases

Ahrefs scope：錯source_class、estimation_flag=false、environment=production、APPROVED但approval_ref=null。

Opportunity：environment=production、duplicate evidence_refs、band=5、額外raw_payload、未滿條件卻status=APPROVED、review_state=APPROVED但status不符、evidence不足卻status=VALIDATED、非法created_at。共12 cases。

schema positive/negative harness執行於`../97_Runtime/gsc-mcp/bin/python3.12`（有jsonschema）；bundled Python無該library。自訂date callback用`date.fromisoformat`與長度10；date-time callback要求`T`與timezone-aware `datetime.fromisoformat`。未安裝或修改任何runtime dependency。

## 可重現基本檢查

從repo root（下列只檢schema meta-schema與shape；完整semantic tests是WP1）：

```sh
PYTHONDONTWRITEBYTECODE=1 '../97_Runtime/gsc-mcp/bin/python3.12' - <<'PY'
import json
from pathlib import Path
from jsonschema import Draft202012Validator
for schema_name, example_name in [
    ('ahrefs_scope.v1.proposal.json', 'ahrefs_scope.synthetic.json'),
    ('opportunity_contract.v1.proposal.json', 'opportunity.synthetic.json'),
]:
    schema = json.loads((Path('contracts') / schema_name).read_text())
    example = json.loads((Path('docs/opportunity-intelligence/examples') / example_name).read_text())
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(example)
    print(schema_name, 'schema and shape OK; formats/semantics require explicit checks')
PY
```

既有70-test suite的確切命令見TEST_STRATEGY。WP1正式保留可重跑的positive/negative/semantic suite；本輪臨時harness未加入production code。

## Not verified

沒有opportunity engine、ingestion pipeline、review身份/bridge、UI、outcome implementation，所以未跑這些實作測試；沒有production activation。Ahrefs probes不是全歷史、全國別、全mode、全export上限測試；Google live AIO/PAA capture尚未驗。Workduo只小量sample，不代表Core全覆蓋。CrUX本輪未live query；Apps Script遠端runtime/ACL未重驗。

## Git result / preservation

本輪新增只在`docs/opportunity-intelligence/`、`contracts/ahrefs_scope.v1.proposal.json`、`contracts/opportunity_contract.v1.proposal.json`；`9376711` 是 architecture foundation，`692f475` 是 handoff baseline，後續僅有 handoff clarification docs commits。既有tracked兩個modified path與兩個untracked output目錄保持。沒有scheduler、正式Sheets寫入或Apps Script部署；remote architecture branch已推送，原工作樹仍由最終回報核對。

## WP1 implementation validation

| Check | Result | Scope / limit |
| --- | --- | --- |
| WP1 tests | PASS | 20 deterministic unittest cases；synthetic context only |
| Full regression | PASS | 90 tests，包含既有70 tests |
| Structural + explicit format | PASS | 兩份 proposal schemas、date、timezone-aware date-time、URL、period、identifier |
| Semantic + cross-field | PASS | evidence refs/count/families/source classes、score profiles/bounds、confidence、freshness、action、revision/content hash、mock human approval |
| Positive fixtures | PASS | Ahrefs scope、DISCOVERED/CANDIDATE、SEO_NEW、GEO、VALIDATED、mock human APPROVED |
| Negative semantic fixtures | PASS | 16 named cases；含 missing != zero、stale/conflict、approval/hash、CREATE_NEW conflict |
| Offline boundary | PASS | validator 只接受 payload/context；未呼叫 live APIs、Drive、Sheets 或 Apps Script |
| Security | PASS | synthetic fixtures；scoped secret/PII pattern scan為0 |
| Production mutation | PASS | 0；兩份 contracts仍為 proposal，沒有正式 writer 或 scheduler |
| WP1 readiness | READY | 下一個唯一任務依 ROADMAP 為 WP2 Ahrefs read-only ingestion |
