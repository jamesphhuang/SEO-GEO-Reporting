# OUTCOME TRACKING / MONTHLY LIFECYCLE

## Action與checkpoint contract

批准前凍結measurement_plan：`action_id, opportunity_revision, approved_action, target_url_ids, baseline_evidence_refs, primary_metric, target_delta, guardrails, minimum_sample, attribution_limitations, comparison_method, owner_id, planned_effort`。完工記actual completed_at、deployment/change reference、affected_urls、actual_effort與其他同時變更。

30/60/90 calendar days從completed_at算，Asia/Taipei。checkpoint day只是due date，來源若尚未final則WAITING_FOR_FINAL，不用未完整period補出勝利。提案baseline=完工前28個完整日；30/60/90 checkpoint各取截止日往前28日，排除執行日。確保比較window不重疊、相同country/device/channel/prompt cohort；若採月/季不同window，需在plan中明訂，不能事後挑有利日。

| Source | 追蹤內容 | 約束 |
| --- | --- | --- |
| GSC | query×URL clicks/impressions/CTR/position | 同scope，weighted position，CTR用sum clicks/sum impressions；不得平均daily CTR |
| GA4 | landing sessions/engagement/CTA diagnostic | 不稱formal conversion，不跨property加總；guardrails與sampling明示 |
| Workduo | matched prompt/platform visibility、mentions、owned citations | 固定query/平台/region/版本；新prompt另列，不混入baseline |
| SF / CrUX | issue resolved、indexability、URL/ origin UX | technical checks代表交付驗收，不單獨等於商業WON；CrUX可能只能用滾動窗口與context |
| Business | approved aggregate outcome/attributed theme | 沒有topic/URL attribution contract就「不可歸因」；SQL需正式source approval和maturity |

## Outcome classification（人工確認）

先检查minimum sample、coverage、scope與干擾。資料不足/窗口未到/未final/關鍵來源失敗 → INSUFFICIENT_DATA。季節、活動、SERP改版、同時網站變更皆保留alternative explanation；可用matched non-treated URLs作對照，不宣稱隨機因果。

- WON：預先指定primary goal達標、至少一個独立supporting signal同向、所有material guardrails未破、實作驗收通過、無未解重大confound；人工確認。不能只有clicks上升。
- PARTIAL_WIN：primary或預定secondary部分達標且無material guardrail損害，但尚不滿WON的完整條件。
- NO_CHANGE：資料充分，主要指標在預定tolerance內，沒有material improvement/decline。
- LOST：資料充分，primary下降超過預定tolerance或guardrail material breach；需註記是否可歸因，不能把相關性直接稱action造成。
- INSUFFICIENT_DATA：樣本/母體/attribution不足，不補NO_CHANGE。

target_delta、tolerance、minimum_sample依action與baseline在批准前填，不預設所有頁面「+10%就成功」。若primary是正式business outcome但目前無attribution，不能拿GA4 CTA完成WON；可以先把primary定成SEO/GEO可觀測目標並明示商業效果未證實。

Outcome record append-only：baseline、after refs、comparison、result、confidence、reviewer_id、evaluated_at、revision/supersedes。Action未完成則不跑30d效果評估；取消保留原因。追蹤只設計，不建立排程。

## 月度作業

Collect → Normalize → Validate → Discover → Cluster → Score provisional → SERP Validate → Produce Candidates → Human Review → Recommendations → Executive Next Steps → Track Outcomes。

| 節奏 | 作業 | Gate / output |
| --- | --- | --- |
| 每月第1階段，等source final | GSC/GA4完整月、business latest revision、Workduo固定cohort、SF最近crawl、CrUX最新window | collection manifest；每sourceREADY/PARTIAL等；不能强求所有來源同日期 |
| 每月discovery | Ahrefs範圍內keyword/competitor更新，topic去重與mapping review | scope approval、budget、coverage；完整discovery是否每月由成本與變動率決定 |
| 每月候選 | 類型rules、score intervals、conflicts queue | 不足資料留待查證，不自動CREATE_NEW |
| 只有shortlist | Top30 live SERP、SF URL check、content answer/citation QA、effort estimate | 每筆SERP_VALIDATED / SERP_CONFLICT / SERP_NOT_CHECKED；平台/地區/時間/feature欄逐一標observed/not observed/not captured |
| 每月review | 按已核准各profile capacity挑工作；合併dependencies；人工批准 | approved manifest，Next Steps人工selection |
| 每月outcome sweep | 到期30/60/90d checkpoints | final資料到齊才評估，未到維持pending |
| 每季 | competitor/domain registry、business strategy overlay、品牌詞字典、GEO Core prompt version、score backtest | 新version，不改寫舊snapshot；新題先experimental cohort |
| 特定事件 | 改版、canonical變更、source schema/entitlement、tracking change | invalidation manifest、要求revalidation，不等下月盲用舊資料 |

SERP capture每candidate至少記intent/page type、features、PAA、AIO presence、forums、videos、comparison pages、freshness、dominant domains。沒有完整擷取能力的欄位填NOT_CAPTURED，不能變false。Ahrefs cached SERP提供context，不能標成本次Google live SERP。
