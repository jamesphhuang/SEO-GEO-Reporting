# SCORING_MODEL

Score 表示同類工作內的相對優先，不是成功機率或預測營收。Score、Confidence、evidence completeness、human approval 分開。初始權重需 UAT backtest 與 owner 審核，未校準前畫面標「提案評分」。

## OPTION A / OPTION B

| Model | Demand | Traction | Business | Attainability | GEO | Ease | 評估 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A 統一分數 | 20 | 20 | 20 | 15 | 15 | 10 | 簡單但 demand/traction 相關、GEO 缺測懲罰所有 SEO、新內容無 traction 被系統性低估 |
| B SEO_EXISTING | 20 | 15 | 30 | 20 | 0 | 15 | 既有 URL 的更新/snippet/link/technical，商業優先 |
| B SEO_NEW | 25 | 0 | 30 | 25 | 0 | 20 | 有完整 inventory 證明無asset；不拿missing traction冒充零 |
| B GEO | 10 | 5 | 30 | 15 | 30 | 10 | 固定 prompt sample 的 GEO action；不拿Ahrefs AIO presence替代GEO gap |

**RECOMMENDED MODEL = B**，三個固定且版本化 profile。不可按某筆缺什麼欄位臨時換權重；由 primary action/type 決定。GEO profile 用於 GEO_ENHANCE；CREATE_NEW 用 SEO_NEW（GEO新asset也先做需求/資產審查）；其他執行action用 SEO_EXISTING。MONITOR/DO_NOTHING 不進 execution ranking，但保留原 profile 的診斷分。

跨 profile 不把 80 vs 75 當可直接比較。每月先由 owner 分配 SEO existing/new/GEO 的 effort budget，再各自排序；business_theme、依赖、deadline、effort 可作人工 portfolio 調整並記錄理由。尚未提供月度人日上限，不能宣稱已選出最佳月計畫。

## Dimension definition

每個 dimension 是 ordinal band `0,1,2,3,4`，對應 `0,25,50,75,100`。未取到是 null，不是 band 0。

| Dimension | Source / normalization（proposal） | cap/floor | Missing / explanation |
| --- | --- | --- | --- |
| Search Demand | Ahrefs TW 同volume_mode，代表詞volume；0=觀測0；1=1–99；2=100–499；3=500–1999；4≥2000；近義詞max，不sum | 0/4；極大量不再加分 | 未抓/估計null→null；GSC曝光可支持偵測但不能代填Ahrefs量；顯示估計日期/mode |
| Existing Traction | GSC matched query×URL；impressions<100且完整為0；≥100時position 4–15→4、>15–20→3、>20–40→2、>40→1；≤3只有CTR/decay等有效headroom時3，否則0 | 0/4 | pair缺漏/TopN無coverage→null；說明headroom不是「排名越高分越高」；SEO_NEW固定weight0 |
| Business Value | owner-approved relevance: 0=不相干；1=間接受眾；2=產品教育；3=已確認pipeline相關主題；4=本季優先且有可稽核strategy/aggregate evidence | 0/4；不以CPC、TOFU/BOFU自動給分 | 未批准/過期→null；必附override revision/reviewer evidence；不可推估URL revenue |
| Attainability | SERP同意圖可競爭性、asset quality、SF execution、Ahrefs竞争頁強度。0=已確認不可行；1=強勢壁壘且欠多項資產；2=至少一個重大可解gap；3=可比同業可達且gap有限；4=明確頁面級headroom且無重大障礙 | 0/4；KD只是auxiliary，不用100-KD作成功率 | 缺SERP/inventory→null；critical blocker先dependency，不拿高其他分抵消 |
| GEO Opportunity | Workduo同prompt/platform cohort；gap=competitor visibility−SHOPLINE visibility（percentage points）；0≤0、1=(0,5)、2=[5,15)、3=[15,30)、4≥30；需content gap review | 0/4；只用同母體gap，provider百分數先明確轉換 | cohort/denominator/coverage不明→null；不能因未追蹤給0；SEO profiles weight0 |
| Execution Ease | 執行owner估人日含QA/approval/dependencies；4≤1日、3≤3日、2≤5日、1≤10日、0>10日或已確認不可行 | 0/4；effort還需單獨顯示 | 未估工→null；AI估計僅suggested，不直接approved |

任一 band 必須有 `evidence_refs` 和 `rationale`。weight=0 欄位 null 表示 profile 不適用，不能借此跳過 rule required evidence。表中 thresholds 為 deterministic 初始值，季校準時建立新 profile version，不重寫歷史分數。

## Missing-data behavior / formula

`observed_points = Σ(weight_i × band_i / 4)`（僅非null維度）。`score_lower_bound=floor(observed_points)`；`score_upper_bound=ceil(observed_points + Σ active missing weights)`。active dimension 全齊才 `opportunity_score = floor(observed_points + 0.5)`，否則 null，顯示「待評估；範圍 L–U」，不以lower bound冒充正式分數、不以剩餘權重重正規化。

完整範例（synthetic）：SEO_EXISTING bands=Demand3、Traction4、Business3、Attainability3、GEO null、Ease4 → 15+15+22.5+15+15=82.5 → **83/100**。Business 缺值則 score=null、範圍 **60–90**；此處不是60分。Score有值仍可能因CONFIDENCE或rule gate不通而不能批准。

排名 tie-break：已核准strategic priority、較高confidence、较低effort、stable opportunity_id。分數接近（例如≤5）標同一priority band，避免pseudo precision。禁止浮點小數長尾、ROI承諾、score自動 APPROVED。

## Calibration

先用至少一個歷史月做blind review，再比較專家排序、漏失商機、錯誤CREATE_NEW、跨主題集中度；有30/60/90d後再看結果。不得只因高分action clicks增加就證明模型有效；控制季節、品牌活動、實作選擇偏誤，保留DO_NOTHING對照。每季審weight/threshold，先UAT再新版本，記錄變更理由。
