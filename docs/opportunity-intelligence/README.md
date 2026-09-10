# Content & Search Opportunity Intelligence Layer

設計交付：2026-09-10。目的是回答「下個月有限的SEO/GEO資源應投入哪些主題、頁面與工作，以及如何驗證」，不是多加一個Ahrefs報表區塊。

**Architecture READY；Ahrefs integration PARTIAL；production 未啟用。** 本輪只建立架構文件、兩份schema proposals與兩份合成shape範例。既有程式／資料／正式Google Sheets沒有修改，沒有commit或push。

## 閱讀順序

1. [目前實際狀態與documentation drift](CURRENT_STATE.md)
2. [Ahrefs與其他MCP capability](AHREFS_CAPABILITY_MATRIX.md)
3. [推薦架構與漸進遷移](ARCHITECTURE.md)
4. [唯一下一個任務](NEXT_TASK.md)
5. [可直接貼給Luna的完整交接提示](LUNA_HANDOFF.md)

## 需求覆蓋與文件索引

| Phase / 要求 | Durable artifact |
| --- | --- |
| 0 Repo/Drive/production ground truth | [CURRENT_STATE](CURRENT_STATE.md) |
| 1 Ahrefs capability metadata | [AHREFS_CAPABILITY_MATRIX](AHREFS_CAPABILITY_MATRIX.md) |
| 2 Source responsibilities、9 Business、10 GA4 | [DATA_SOURCE_ROLES](DATA_SOURCE_ROLES.md) |
| 3 Entity、4 taxonomy、5 actions、6 rules、11 SF、13 GEO | [OPPORTUNITY_MODEL](OPPORTUNITY_MODEL.md)、[WORKBOOK_ARCHITECTURE](WORKBOOK_ARCHITECTURE.md) |
| 7 Option A/B/explainable score | [SCORING_MODEL](SCORING_MODEL.md) |
| 8 Confidence / approval | [CONFIDENCE_MODEL](CONFIDENCE_MODEL.md) |
| 12 Live SERP、18 Outcome、19 Monthly lifecycle | [OUTCOME_TRACKING](OUTCOME_TRACKING.md) |
| 14 Ahrefs contract、15 Opportunity contract | [CONTRACT_DESIGN](CONTRACT_DESIGN.md)、[Ahrefs proposal](../../contracts/ahrefs_scope.v1.proposal.json)、[Opportunity proposal](../../contracts/opportunity_contract.v1.proposal.json) |
| 16 Workbook / report、17 Recommendations | [WORKBOOK_ARCHITECTURE](WORKBOOK_ARCHITECTURE.md) |
| 20 Failure、21 freshness | [EVIDENCE_FRESHNESS_POLICY](EVIDENCE_FRESHNESS_POLICY.md) |
| 22 Canonical refactor、23 UAT、26 architecture review | [ARCHITECTURE](ARCHITECTURE.md) |
| 24 Security / decisions | [DECISIONS](DECISIONS.md) |
| 25 deterministic test plan | [TEST_STRATEGY](TEST_STRATEGY.md)、[actual validation](VALIDATION_RESULTS.md) |
| 27 WP0–WP12 | [ROADMAP](ROADMAP.md) |
| 28 durable handoff、29 one next task、30 Luna prompt | 本索引、[NEXT_TASK](NEXT_TASK.md)、[LUNA_HANDOFF](LUNA_HANDOFF.md) |
| Scope / budget / owner unknowns | [OPEN_QUESTIONS](OPEN_QUESTIONS.md) |

[Ahrefs synthetic record](examples/ahrefs_scope.synthetic.json) 與 [Opportunity synthetic record](examples/opportunity.synthetic.json) 只驗record形狀；其references不是live evidence，不得作為production候選。shape通過不表示具商業價值、證據充分或已批准。
