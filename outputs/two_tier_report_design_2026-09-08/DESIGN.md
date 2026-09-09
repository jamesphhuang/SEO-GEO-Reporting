# 雙層 SEO／GEO 月報架構設計

**產出日期**：2026-09-08
**方法**：`/grill-me` 逐題收斂，15 題
**狀態**：`READY_FOR_IMPLEMENTATION=YES`，等待實作核准
**基準**：`outputs/monthly_report_2026_08_v2`（2026-09-07 最後一次資料抓取）

---

## 目錄

1. [Ground Truth](#ground-truth)
2. [User Goal](#user-goal)
3. [Final Decisions](#final-decisions)
4. [Event / Data Model](#event--data-model)
5. [Recommended Schema](#recommended-schema)
6. [Data That Must Not Be Logged / Exposed](#data-that-must-not-be-logged--exposed)
7. [Architecture Options](#architecture-options)
8. [Recommended Architecture](#recommended-architecture)
9. [Lifecycle](#lifecycle)
10. [Failure Semantics](#failure-semantics)
11. [Idempotency Strategy](#idempotency-strategy)
12. [Privacy / Governance](#privacy--governance)
13. [Environment Isolation Strategy](#environment-isolation-strategy)
14. [Integration Strategy](#integration-strategy)
15. [Configuration Design](#configuration-design)
16. [Test Plan](#test-plan)
17. [Rollout Plan](#rollout-plan)
18. [Non-Goals](#non-goals)
19. [Future Opportunities](#future-opportunities)
20. [Work Packages](#work-packages)
21. [收斂狀態](#收斂狀態)

---

## Ground Truth

以下全部由讀取程式碼與活頁簿取得，非使用者描述的轉述。

### 現有報告

| 項目 | 事實 |
|---|---|
| 詳細版載體 | `outputs/monthly_report_2026_08_v2`，9 段 Apps Script 網頁 |
| 資料活頁簿 | `14lyC4zotKGBGg90CExf3q-hPk7awRAvUgIoEYAn1QtI`，`_Schema` 分頁驅動欄序 |
| 現有 9 段 | 摘要／業務成果／搜尋表現／導流結構 GA4／GEO／技術稽核+CWV+Sitemap／重點頁面與查詢／來源與方法／資料限制 |
| 摘要生成方式 | 100% 程式推導。`Report.html:349` 註解明載 `every bullet is derived, not written by hand`。**無任何人工文字欄位** |
| 報告立場 | 刻意不做因果歸因、不給建議（README：「只描述變化，不宣稱原因」）。「優化工作建議」在現有 pipeline 中無載體 |
| `push_to_sheet.py:199-200` | 對每個管理的分頁下 `updateCells` + `fields:"*"`，**整頁清空重寫** |
| `Code.gs` `readWorkbook()` | 只讀 `_Schema` 登記過的分頁；未登記者完全不可見 |
| `doGet()` | 目前無參數簽章，需改為 `doGet(e)` |
| Apps Script 設定 | `access: MYSELF`、`executeAs: USER_DEPLOYING` |
| Sheets 憑證 | 僅 `spreadsheets` scope，不含 `script.projects`，**無法用 API 部署 Apps Script**，須手動貼入 |

### 業務資料

| 項目 | 事實 |
|---|---|
| Non-Paid Leads | `2026 lead gen distribution` 第 23／71／119／163 列（四個季區塊），欄 C/G/K = Actual |
| Non-Paid Leads SQL | **存在**，位於母列下一列：第 24／72／120／164 列，同欄位配置 |
| 2026 逐月（Target/Actual） | 01: 90/71、02: 73/50、03: 114/96、04: 101/98、05: 108/100、06: 117/118、07: 102/108、08: 106/72、09: 97/3、10–12: 97/106/117，Actual 空白 |
| **跨年度標籤不一致** | 2024／2025 分頁該列標籤是 `*Qualified`，2026 才是 `*SQL`。跨年度序列等於接兩個名稱不同的列 |
| 同名手足列 | `*SQL` 也出現在 Inbound Total、Paid Leads、Trial Leads、Consultation、Feature Leads 之下，Non-Paid Leads 那列只是其中之一 |
| SQL 治理狀態 | `business_actual_mapping.v1.json` 列為 `SOURCE_NOT_CONFIRMED`；`data_contract.v1.json` 的 `sql_maturity` 規定 lead month + 60 天成熟，未成熟時禁止 `target_attainment`／`formal_trend`／`rag` |
| 成熟度現況（2026-09-08） | 最近的成熟月是 2026-06；2026-07 成熟於 09-29，2026-08 成熟於 10-30 |
| **回溯修訂是常態** | 4–8 月標頭皆已改為「9/7更新」；8 月 Non-paid 由 450 → 448（達成率 72.58%→72.26%，MoM −5.66%→−6.08%）。現有 `report_data.json` 仍是舊的 450 |
| 空白陷阱 | 10–12 月 Actual 空白但 Reach Rate 欄以公式渲染 0，不可讀成實績為零 |

### 搜尋與流量

| 項目 | 事實 |
|---|---|
| GSC 抓取範圍 | 僅 2026-07、2026-08。近半年需擴抽 |
| GSC 主站 8 月 | 曝光 105,840→90,703（−14.30%）、點擊 9,146→8,283（−9.44%）、CTR 8.64%→9.13%、平均排名 4.53→4.38 |
| GSC 部落格 8 月 | 曝光 1,119,300→1,007,621（−9.98%）、點擊 11,453→10,989（−4.05%）、CTR 1.02%→1.09%、排名 6.85→6.79 |
| GSC 必要參數 | `data_state=final`、`country=twn`，兩者都會改變 WoW／MoM 結論 |
| GA4 抓取範圍 | 僅 7、8 月；raw 含全部 15 渠道 × 19 hostname |
| GA4 API 限制 | 單一 report 最多 4 個 `date_ranges`，六個月需改用 `yearMonth` 維度單次呼叫 |
| 主站 8 月渠道結構 | 總計 57,508 次。Paid Social 22.53%、Organic Search 21.64%、Paid Search 17.57%、Direct 16.23%、Referral 11.31%、**AI Assistant 413 次（0.72%）**。付費類合計 44.75% |
| 分母敏感度 | AI Assistant 佔比＝全渠道 0.72%／非付費 1.30%／Organic Search 3.32%／property 全 host 0.31% |
| `ga4_scope.v1.json` | hostname 精確比對、預設拒絕未列出主機；`consultation.shopline.tw` 明文排除於主站流量總計；禁止跨 property 合計 |

### AI 與 GEO

| 項目 | 事實 |
|---|---|
| `AI Channel leads` 頁籤 | sheetId 250356833，**僅 4 列資料**：2026-06/07/08/09 |
| 欄位 | `leads`、`SQL`、`CVR`；B1 標頭寫死 **`source=chatgpt.com`** |
| 數值 | 06: 52/11/21.15%、07: 14/5/35.71%、08: 18/6/33.33%、09: 4/0/0%（**部分月，僅至 9/7**） |
| 口徑落差 | 這是 chatgpt.com 單一來源，**不等於** GA4 的 `AI Assistant` 渠道（涵蓋多個 AI 來源），更不等於「AI 搜尋」 |
| 缺欄位 | 該頁籤**沒有**工作階段、沒有佔主站流量%，兩者必須從 GA4 取得 |
| 6 月高峰 | 6 月 52 筆是後兩月的三倍多。**Phase 0 已證實這不是髒資料**——GA4 的 AI 工作階段同月同樣是後兩月的兩倍（見下節） |
| GEO 來源 | 2026-09-06 10:03 UTC Workduo 快照沿用。Workduo MCP 在 Claude Code 無法連線，磁碟上無 endpoint／API key |
| GEO 資料 | 10 entity × 7/8 月。SHOPLINE 70.8%（−6.6pt）／SOV 23.7%；CYBERBIZ 47.6%（−7.6pt）；Shopify 44.2%（−6.0pt）；91APP 39.5%（+0.4pt）；**WACA 36.4%（+5.0pt）**；EasyStore 31.1%；BV SHOP 15.7%；Meepshop 13.7%；Shopify TW 與 Pinzap 為零值雜訊列 |
| 結構訊號 | 前三名同步下滑、WACA 一家在漲 |

### 技術稽核（詳細版既有）

| 項目 | 事實 |
|---|---|
| Core Web Vitals | 來源 CrUX API（金鑰 `98_環境設定/crux/api_key.txt`）。四組站點×裝置中三組通過 |
| 未通過項 | 部落格行動裝置 LCP **3.61 秒**（+40.57%），8 月中跨過 2,500ms 門檻；同站 FCP +35.76%、TTFB +48%（1,775ms） |
| CrUX 口徑 | 滾動 28 天窗口，與報表月份不重合，**不能與 GSC／GA4 對帳**；來源網域層級、未分國別 |
| Screaming Frog | 2026-09-06 爬取，單一時點快照，**無 7 月對照**。高優先度：部落格圖片 >100kB 4,373 張（51.48%）、內部連結指向轉址 1,298 個、缺 H1 889 頁；主站圖片 >100kB 147 張（63.36%） |
| Sitemap | `get_sitemaps` 的 `indexed_urls` 實為 submitted 數；`indexed` 常為 0 亦非問題證據。應以 `status` 與 staleness 判讀 |

---

## Phase 0 驗證結果（2026-09-08）

執行了兩次 GA4 唯讀探測（`scratchpad/ga4_probe*.json`），驗證設計裡唯一未經證實的假設。

### 技術可行性

| 檢查項 | 結果 |
|---|---|
| `yearMonth` 維度 | ✅ 可用，可一次取回多月，避開 4 個 `date_ranges` 上限 |
| `dimension_filter`（含 `and_group` + `FULL_REGEXP`） | ✅ 可用，可在 API 端過濾 hostname 與 source |

### 原假設不成立

**`AI Assistant` 渠道在 shopline.tw 的資料起點是 2026-05，不是 2026-03。** 決策 6 原本規劃的「六個月折線」無法成立。

| 月份 | AI Assistant（渠道） | AI 來源（sessionSource） | Organic Search | AI/Organic |
|---|---|---|---|---|
| 2025-09 | — | 90 | 14,332 | 0.63% |
| 2025-10 | — | 108 | 15,565 | 0.69% |
| 2025-11 | — | 114 | 14,805 | 0.77% |
| 2025-12 | — | 170 | 14,827 | 1.15% |
| 2026-01 | — | 84 | 15,257 | 0.55% |
| 2026-02 | — | 58 | 10,832 | 0.54% |
| 2026-03 | — | 105 | 14,627 | 0.72% |
| 2026-04 | — | 91 | 13,106 | 0.69% |
| 2026-05 | 60 | 708 | 11,710 | 6.05% |
| 2026-06 | 697 | 721 | 14,381 | 5.01% |
| 2026-07 | 323 | 342 | 13,957 | 2.45% |
| 2026-08 | 413 | 423 | 12,446 | 3.40% |

### 三項延伸發現

1. **2026-05 的跳躍是真的，不是量測假象。** `chatgpt.com` 這個 source 字串在 12 個月內被穩定捕捉（75 → 96 → 102 → 141 → 68 → 37 → 56 → 55 → 679），各月 source 字串種類數穩定在 4–7 種，無標記方式改變的跡象。2025-09～2026-04 平均 102 次／月，2026-06～08 平均 495 次／月，**約 4.8 倍**。
2. **兩種定義實質等價。** 2026-06 起 sessionSource 判定與官方渠道群組差距僅 2.4%～5.9%（721/697、342/323、423/413）。
3. **2026-05 是分類過渡月。** 該月 60 筆進 `AI Assistant`、434 筆落在 `Unassigned`、214 筆落在 `Referral`。此前所有 AI 來源流量都被分類為 `Referral` 或 `Unassigned`，Google 未回溯重新分類。

### 由此產生的決策

**第 16 題**：維持 `AI Assistant` 渠道定義，圖只畫 **2026-06～08 三個月，改用柱狀**。

- **理由**：不偏離 `ga4_scope.v1.json` 的 `channels` 定義；三個月用柱狀而非折線，不假裝有趨勢
- **已知代價**：主管在圖上只會看到 697 → 323 → 413，容易讀成「AI 流量在跌」，而真相是它前一季才跳了近五倍
- **緩解**（不改變圖的定義）：把 12 個月的脈絡寫進附註區塊（決策 9 已建立該位置），內容為「`AI Assistant` 渠道分類自 2026-05 起才有；以 sessionSource 判定的長期觀察顯示 2026-05 出現階梯式跳躍，此前八個月平穩於約 102 次／月」。被追問時資料就在同一頁上

---

## 實作進度（2026-09-08）

**WP0–WP9 全部完成 ✅。** 剩下的只有兩件不屬於工程的事：Phase 2（人工填寫 `Recommendations` 與 `Next_Steps`），以及手動貼入 Apps Script 重新部署（憑證無 `script.projects` scope）。

| 驗證 | 結果 |
|---|---|
| WP1 離線測試（5 情境 25 項） | 25/25 |
| 保護分頁寫入測試列後重跑 → 內容存活 | ✅ |
| GSC 六個月 × 兩站，7／8 月數字與先前完全一致 | ✅ 無回歸 |
| 業務 8 月實績 450 → **448** 已流通到報表 | ✅ |
| `ga4Monthly` 與 Phase 0 探測完全吻合（697／323／413、8 月 3.32%） | ✅ |
| `sqlIsMature=false` 時 `sqlReach`／`sqlMomChange` 為 null | ✅ 未成熟欄位不存在於資料層 |
| `aiChannel` 三個完整月，進行中的部分月已排除 | ✅ |

### 過程中修掉的兩個既有缺陷（非原規劃範圍）

1. **`collect_evidence.py` 原本 fail-closed。** 它假設每筆 MCP 回應都是 JSON，一筆不是就整個中止。而這個 GSC MCP 回報失敗的方式是 `isError=False` 加一串人話，只有 JSON 解析會攔到。已改為 fail-open：跳過該筆、記入 `evidence["problems"]`、於輸出明白告知。
2. **`get_sitemap_details` 會覆蓋 `get_sitemaps`。** 兩者都沒有 `dimensions` 參數，而原本的分流只看這個，導致每站的 sitemap 清單被最後一筆詳情蓋掉。已改為以 `sitemap_url` 分流。

### 上游變動

主站的 `sitemap.xml.gz` 已不再是 Google 認得的已提交 sitemap（404 `is not a submitted or a known sitemap`）。程式刻意**不**以 2026-09-07 的舊快照回填——那會拿一天前的資料謊報現況。Sitemap 由 3 列變 2 列，主站 `sitemap.xml` 現為 `Valid`。

### 六個月資料揭露的三件事（供 Phase 2 判讀）

| | 3月 | 4月 | 5月 | 6月 | 7月 | 8月 |
|---|---|---|---|---|---|---|
| 主站曝光 | 106,625 | 88,467 | 90,334 | 103,131 | 105,840 | 90,703 |
| 主站 CTR | 9.26% | 9.87% | 8.39% | 9.92% | 8.64% | 9.13% |
| 主站平均排名 | 6.61 | 5.45 | 5.28 | 4.40 | 4.53 | **4.38** |
| 部落格點擊 | 18,688 | 15,740 | 14,710 | 12,666 | 11,453 | **10,989** |
| 部落格 CTR | 1.82% | 1.62% | 1.53% | 1.18% | 1.02% | **1.09%** |

1. **「量跌質升」要收斂講法。** 8 月 CTR 9.13% 在六個月裡只是中段，4 月 9.87%、6 月 9.92% 都更高。單月比是進步，六個月看是回到區間中間。
2. **真正的正面訊號是排名：6.61 → 4.38，六個月持續改善**，且只有拉開時間軸才看得到。這比 CTR 那 +0.49pt 有說服力得多。
3. **部落格才是該擔心的。** 曝光六個月大致持平在 100 萬上下，點擊卻從 18,688 掉到 10,989，CTR 從 1.82% 腰斬到 1.09%。MoM 只顯示 −4.05%，完全看不出這個坡度。

---

## 部署後的修正（2026-09-09）

v2 已部署至活頁簿綁定的 Apps Script（`AKfycbz23PYA…`），同一網址加 `?view=exec` 即為總覽版；不會另生新網址。上線後在正式畫面上發現三個渲染缺陷，皆已修正並在正式環境確認。

### 線上只保留一個網址

同日另有一個獨立 Apps Script 專案（`1YXlcxfUv1Gi…`，網址 `AKfycbys0wH…`）部署了舊的 MCP 快照版報表，資料凍結在 2026-09-06，因此仍顯示回溯修訂前的 Non-Paid Leads **450**，而正式版是 **448**。

同一個月份、兩個線上網址、兩個數字，是主管會議上最容易毀掉信任的那種落差——而決策 4 的 `businessAsOf` 只保護得到活頁簿驅動的那一份，凍結快照沒有取數標記，也不會再更新。該部署已於 2026-09-09 封存，線上只剩活頁簿綁定的那一個網址。

| # | 缺陷 | 成因 | 修法 |
|---|---|---|---|
| 1 | 圖表類別標籤被裁掉，且裁掉的是**開頭**（`CYBERBIZ Corp.` 只剩 `:RBIZ Corp.`、`SHOPLINE（−6.60 pt）` 只剩括號） | `groupedBars` 的標籤右對齊在固定 64px 邊界，更寬者被 viewBox 靜靜切掉 | 依最寬標籤自動配置邊界（CJK 估 12px、拉丁 6.6px，上限 320px） |
| 2 | 柱值與折線值標籤重疊 | 兩者都畫在各自資料點的上方 | 柱值錨定**柱底**——折線可能穿過柱身，錨柱頂不夠 |
| 3 | 375px 下版面被撐寬 53px | 來源說明含 `dimensions=yearMonth,hostName,...` 無斷行機會 | 對 `#sources .panel` 與 `details.notes` 加 `overflow-wrap` |

**驗證方式也一併升級。** 原本只檢查頁面層級的水平溢出，漏掉了 SVG 內部：現在逐一比對每張圖裡所有文字節點的邊界框，同時檢查是否落在 viewBox 外，並在展開附註區塊後才量測手機版（收合的內容不參與版面計算）。

### 詳細版 03 段的圖表重整

原本「點擊」與「曝光」各一張、兩站並列。改為**每站一張，曝光走柱狀（左軸）、點擊走折線（右軸）**，並使用活頁簿裡全部的月份。

兩個量級問題疊在一起使得原本的做法不可行：主站曝光是其點擊的約 13 倍、部落格約 92 倍（指標之間）；部落格曝光又是主站的約 10 倍（站與站之間）。因此指標用雙軸、站與站分圖。

副作用是部落格的問題第一次在圖上可見——曝光大致持平而點擊逐月下滑，六個月由 18,688 降至 10,989，正是 `2026-08-G01` 那條建議的內容。

**兩個檢視的第二條線刻意不同**：總覽版是 CTR（決策 5，回答「量跌質有沒有跌」），詳細版是點擊（CTR 在同段的卡片與對照表中已有）。

---

## User Goal

建立**兩層報告**：

- **詳細版**：供實務人員判讀技術項目、檢視證據，並產出優化工作建議。
- **總覽版**：供主管會議，四個區塊，Next Step 由人工與 AI 討論後產製。

兩層有明確的先後與從屬關係：**先產詳細版 → 人員判讀 → 產出優化工作建議 → 討論收斂 → 挑選改寫成總覽版的 Next Step**。

### 立場宣告

詳細版加入建議段落後，「只描述變化，不宣稱原因」的原則**仍然保留**。做法是：程式推導的數據敘述維持中立不歸因，人工建議明確標示為人工判斷並與數據敘述在版面上分離。報告本身不宣稱因果，宣稱因果的是署名的人。

---

## Final Decisions

### 總覽版（第 1–12 題）

| # | 決策 | 理由 |
|---|---|---|
| 1 | 同活頁簿、同 web app，`?view=exec` 切換 | 一份資料、一次發佈，兩版數字永遠一致 |
| 2 | 新增 `Next_Steps` 人工分頁；pipeline 登記進 `_Schema` 但**不覆寫內容** | 人工在熟悉的試算表介面編輯，改完重整網頁即生效 |
| 3 | SQL 卡遵守合約：只呼累計筆數與目標，達成率與 MoM 標「待成熟」 | 8 月 cohort 才 38 天、7 月 68 天，−33% 有多少是真衰退無法分辨 |
| 4 | `_Meta.businessAsOf` 顯示取數日；發佈後該月凍結 | 回溯修訂是常態，主管需知道這是哪天的數字 |
| 5 | 03 趨勢圖：主站 2026-03～08，曝光柱狀 + CTR 折線（雙軸） | 本月故事是「量跌質升」，單畫曝光會藏掉唯一正面訊號 |
| 6 | GEO 拆兩塊：GA4 圖與 chatgpt 小表分開 | 兩者母體不同，同圖會造成因果暗示（**「軸長不同」與「6 月是髒資料」這兩項原始理由已被 Phase 0 推翻，但主要理由成立，決策維持**） |
| 7 | 佔比分母 = shopline.tw Organic Search（8 月 3.32%） | 回答 GEO 真正的問題：AI 搜尋相對傳統搜尋的規模 |
| 8 | GEO 品牌明細 = Top 5 橫條圖，SHOPLINE 標色，列旁標變化 pt，不並列 SOV | 讓 WACA +5.0pt 這類結構訊號浮出 |
| 9 | 附註為可摺疊區塊，預設收起 | 版面乾淨但資訊完整；列印樣式強制展開以補其缺點 |
| 10 | `Next_Steps.section` ∈ {business, gsc, geo, technical}；technical 只匯總進 01 摘要 | 技術建議有處可放，但不新增草圖沒有的區塊 |
| 11 | 加 `period`；本期區塊只呼本期，摘要下方列「上期項目追蹤」 | 直接回答「上個月講的做了沒」 |
| 12 | 存取權限維持 `MYSELF`，會議螢幕分享 | `?view=exec` 是網址參數不是權限邊界；放寬即等於開放業務目標、SQL、競品分析給全網域 |

### 詳細版（第 13–15 題）

| # | 決策 | 理由 |
|---|---|---|
| 13 | 兩個分頁：`Recommendations`（詳細版）+ `Next_Steps`（總覽版），以 `sourceRef` 相連 | 兩種讀者的欄位需求不同；總覽版措辭可自由重寫不受技術描述綁架 |
| 14 | `Recommendations.status` 為唯一權威；`Next_Steps` 有 `sourceRef` 就帶入，無 `sourceRef` 才用自己的 | 每月只維護一張表的進度，根除兩邊矛盾；純管理類建議仍可獨立存在 |
| 15 | 各段末尾顯示該段建議 **且** 最後有一個彙總清單 | 同一陣列渲染兩次，重複只在畫面上不在維護上；證據相鄰與可執行待辦兩種需求都滿足 |

### Phase 0 之後（第 16 題）

| # | 決策 | 理由 |
|---|---|---|
| 16 | GA4 AI 流量圖：維持 `AI Assistant` 渠道定義，只畫 2026-06～08 三個月，**改用柱狀** | 不偏離 `ga4_scope.v1.json`；三個月用柱狀不假裝有趨勢。12 個月脈絡改寫入附註區塊 |

### 決策之間的修訂關係

- **第 14 題修訂第 11 題**：`Next_Steps.status` 由「必填」改為「條件性」——僅在 `sourceRef` 為空時使用。
- **第 16 題修訂第 6 題**：GA4 圖由「六個月折線」改為「三個月柱狀」。拆兩塊的決策本身維持，但原始理由中的「兩邊都能用自己最長的時間軸」與「6 月是髒資料」皆已被 Phase 0 推翻——兩邊現在都是三個月，且 6 月高峰是真的。維持拆分的理由只剩「母體不同、不製造因果暗示」，這一項仍然成立。

---

## Event / Data Model

### 「一次發佈」的定義

一次完整跑完步驟 1–6（抓取 → evidence → build → push → preview 驗證），並確認 `_Meta.businessAsOf` 為當次取數時間。

**以下不算新的一次發佈**，不得更動已凍結月份的數字：

- 重新整理網頁（Apps Script 即時讀分頁，但分頁內容未變）
- 人工編輯 `Recommendations` 或 `Next_Steps` 分頁（僅影響建議文字與進度，不影響指標）
- 為修正錯字重跑 `preview_local.py`

**已凍結月份需要更正時**，視為一次帶 `revision_note` 的重新發佈，並更新 `businessAsOf`。

### 建議的生命週期

```
詳細版數據段落（程式推導，中立不歸因）
        ↓  人員判讀
Recommendations 一列（人工，帶 evidenceRef 與 status）
        ↓  人工 + AI 討論收斂、挑選、改寫成主管語言
Next_Steps 一列（人工，帶 sourceRef 指回上游）
        ↓  Apps Script join
總覽版 01 摘要 ← 匯總本期 Next Step ＋ 上期項目追蹤
```

---

## Recommended Schema

### `Recommendations` 分頁（人工擁有，pipeline 不覆寫）

| 欄位 | 分級 | 說明 |
|---|---|---|
| `id` | **MVP 必須** | 穩定鍵，格式 `{period}-{section首字}{序號}`，例如 `2026-08-T01`、`2026-08-G03`。`Next_Steps.sourceRef` 指向它 |
| `period` | **MVP 必須** | `2026-08` |
| `section` | **MVP 必須** | `business` / `gsc` / `ga4` / `geo` / `technical`（詳細版五個可掛建議的段） |
| `order` | **MVP 必須** | 段內排序 |
| `priority` | **MVP 必須** | `高` / `中` / `低`（人工判定，非工具原生欄位） |
| `text` | **MVP 必須** | 建議內容，技術語言 |
| `status` | **MVP 必須** | `未開始` / `進行中` / `完成` / `取消`。**全系統唯一權威** |
| `evidenceRef` | **MVP 必須（值可留空）** | 自由文字指向證據列，例如 `Technical_SF · 部落格 · 圖片超過 100 kB`。**刻意不做結構化 id**——`Technical_SF` 目前沒有穩定主鍵，強制結構化只會製造另一種斷鏈 |
| `owner` | Future optional | 負責人 |
| `due` | Future optional | 預計完成日 |
| `anchor` | Future optional | 詳細版段落錨點，例如 `#technical` |

### `Next_Steps` 分頁（人工擁有，pipeline 不覆寫）

| 欄位 | 分級 | 說明 |
|---|---|---|
| `period` | **MVP 必須** | 只渲染與 `_Meta.period` 相符者 |
| `section` | **MVP 必須** | `business` / `gsc` / `geo` / `technical`。值域外的列略過並記入附註 |
| `order` | **MVP 必須** | 同 section 內排序 |
| `text` | **MVP 必須** | 主管語言的措辭，**可與 `Recommendations.text` 不同** |
| `sourceRef` | **MVP 必須（值可留空）** | 指向 `Recommendations.id` |
| `status` | **MVP 條件性** | `sourceRef` 非空時**忽略此欄**，改帶入 `Recommendations.status`；`sourceRef` 為空時才使用 |
| `owner` / `due` | Future optional | |

### Join 規則與斷鏈處理

| 情況 | 行為 |
|---|---|
| `sourceRef` 為空 | 使用 `Next_Steps.status` |
| `sourceRef` 命中 | 使用 `Recommendations.status`，並在該列標示上游 id |
| `sourceRef` 非空但找不到相符 id | **該列仍渲染**，status 顯示「來源遺失」，並在附註區塊列出斷鏈清單。fail-open，不擋渲染 |
| `Recommendations` 分頁不存在 | 所有 `sourceRef` 視為斷鏈；詳細版建議段落顯示 PENDING |

> Join 只比對 `id`，不比對 `period`——`id` 已含 period 前綴故天然唯一，且「上期項目追蹤」必須能跨期 join 回上一期的 Recommendations。

### `report_data.json` 新增／修改

| 欄位 | 動作 | 說明 |
|---|---|---|
| `business.sqlTarget` / `sqlActual` / `sqlMatureOn` / `sqlIsMature` | 新增 | 第 120 列。`sqlIsMature=false` 時前端自動隱藏達成率與 MoM；成熟日到了自動補上，**不需改程式** |
| `business.asOf` | 新增 | 寫入 `_Meta.businessAsOf` |
| `gscMonthly` | 擴充 | 由 4 列（2 站 × 2 月）擴為 12+ 列（2 站 × 6 月）。**欄位結構不變** |
| `ga4Monthly` | 新增分頁 | `yearMonth` × hostname × channel，供折線圖用 |
| `aiChannel` | 新增分頁 | chatgpt.com 的 `month` / `leads` / `sql` / `cvr` / `isMature` |
| `geo` | 不變 | 前端取 Top 5、濾掉可見度為 0 者 |

---

## Data That Must Not Be Logged / Exposed

- **絕不寫入業務來源活頁簿** `1lfbDAu…`（`remote_write_enabled: false`）
- **不放寬 web app access**；`?view=exec` 不得被當成權限機制描述
- **不把 GSC 查詢字詞原文帶進總覽版**（詳細版才有 Top 25 queries）
- **不把未成熟 SQL 的達成率寫進任何欄位**，包含隱藏欄位——資料層就不算
- `Recommendations` 與 `Next_Steps` 的自由文字不得含：客戶名稱、Salesforce 個案編號、憑證或內部 URL、對特定員工的績效評價
- CrUX 金鑰、`98_環境設定/` 下任何檔案路徑不得出現在報告或 `Sources` 分頁
- 合成／測試資料不得寫入活頁簿或 `evidence.json`

---

## Architecture Options

| 方案 | 可靠性 | 複雜度 | 失敗模式 |
|---|---|---|---|
| **A. 單 HTML + view 分支**（採用） | 高：一份資料一次發佈 | 中：`Report.html` 由 50KB 增至約 75KB，需拆共用 helper | 改壞會兩版一起壞 |
| B. 兩個 HTML 檔共用 `Helpers.html` | 中高 | 中高：Apps Script 的 `include()` 樣板拼接 | 兩檔漂移 |
| C. 兩個獨立部署 | 中 | 高：格式化 helper 複製兩份 | 授權、版本各自維護；改數字格式要改兩處 |

---

## Recommended Architecture

**方案 A。** `doGet(e)` 讀 `e.parameter.view`，預設 `full`；`exec` 走精簡組裝函式。兩版共用同一組 `sections[]` 機制與同一批格式化 helper（`pct` / `delta` / `int` / `dec` / `signCls`），只是組裝清單不同。`showSidebar()`／`showDialog()` 預設帶 `full`。

建議與 Next Step 的 join 抽成單一函式 `resolveActions(recommendations, nextSteps)`，兩個 view 都呼叫它，確保斷鏈判定邏輯只有一份。

### 詳細版段落結構（9 段 → 10 段）

| # | 段落 | 變更 |
|---|---|---|
| 1 | 摘要 | 不變（程式推導） |
| 2 | 業務成果 | 段末加建議小區塊（`section=business`） |
| 3 | 搜尋表現 | 段末加建議小區塊（`section=gsc`） |
| 4 | 導流結構 GA4 | 段末加建議小區塊（`section=ga4`） |
| 5 | GEO 品牌可見度 | 段末加建議小區塊（`section=geo`） |
| 6 | 技術稽核與 Sitemap | 段末加建議小區塊（`section=technical`） |
| 7 | 重點頁面與查詢 | 不變 |
| **8** | **優化工作建議彙總** | **新增**。全部建議依 priority → section → order 排序，含 `evidenceRef` 與 `status` |
| 9 | 來源與方法 | 原第 8 段 |
| 10 | 資料限制 | 原第 9 段 |

段末小區塊與彙總段渲染同一份陣列，只是篩選條件不同。兩處都顯示 `id`，並在段末小區塊加「本段建議」標題、彙總段用完整表格，避免被讀成兩件事。

### 總覽版區塊結構

| # | 區塊 | 內容 |
|---|---|---|
| 1 | 摘要 | 本期四類 Next Step 匯總（含 `technical`）＋ 下方「上期項目追蹤」 |
| 2 | 業務成果 | Non-paid Leads 五格卡 ＋ Non-paid Leads SQL 卡（累計筆數／目標／待成熟標示） |
| 3 | 搜尋表現 GSC | 主站卡、部落格卡（曝光／點擊／CTR／排名）＋ 主站近半年曝光柱狀 + CTR 折線雙軸圖 ＋ 本區 Next Step |
| 4 | GEO 品牌可見度 | Top 5 橫條圖 ＋ GA4 AI Assistant 三個月柱狀（2026-06～08，工作階段絕對值 + 相對 Organic 佔比）＋ chatgpt.com 小表 ＋ 本區 Next Step |
| — | 附註 | 可摺疊，預設收起，列印強制展開 |

---

## Lifecycle

```
GSC MCP（單次呼叫 2026-03-01～08-31, dimensions=date, row_limit=200）
GA4 MCP（單次呼叫, dimensions=yearMonth × hostName × channel）  ← 避開 GA4 的 4 個 date_range 上限
CrUX API
Screaming Frog（GUI 匯出，複製到 raw/screaming_frog/）
Sheets 讀（業務列 119/120 + AI Channel leads）
          ↓
      raw/*.json ──► evidence.json ──► report_data.json
                                          ↓
                    push_to_sheet.py（跳過 Recommendations 與 Next_Steps）
                                          ↓
        活頁簿資料分頁  ＋  人工編輯的 Recommendations  ＋  人工編輯的 Next_Steps
                                          ↓
                          doGet(e) 讀 _Schema → model → resolveActions()
                                          ↓
        view=full（10 段，段末建議 + 彙總）   │   view=exec（4 區塊 + 摺疊附註）
```

---

## Failure Semantics

**全部 fail-open**，沿用現有 `cwvStatus` 的 PENDING 慣例。新機制失敗絕不擋住主報告渲染。

| 情況 | 行為 |
|---|---|
| `Recommendations` 分頁不存在或本期無列 | 彙總段顯示「本期建議尚未產製」；**各段末尾的建議區塊在無內容時整塊不出現**（原設計寫的是五段各顯示一次待補提示，實作時改掉——同一句話重複五遍是雜訊，講一次就夠）。數據段落一律正常 |
| `Next_Steps` 分頁不存在或本期無列 | 總覽版 01 摘要顯示「本期 Next Step 尚未產製」，其餘區塊正常 |
| `sourceRef` 斷鏈 | 該列仍渲染，status 顯示「來源遺失」，附註區塊列出斷鏈清單 |
| `section` 值域外 | 該列不渲染，附註區塊列出被略過的列數與其 `id` |
| GSC 某月抓取失敗 | 該月**留空，不補 0**；趨勢圖斷點，附註標明缺月 |
| `AI Channel leads` 讀取失敗 | 小表顯示 PENDING，折線圖不受影響 |
| GEO 快照缺席 | GEO 區塊顯示 PENDING |
| 業務第 120 列缺值 | SQL 卡整張顯示「來源未提供」，**不顯示 0** |
| CrUX 無金鑰 | 沿用既有行為：`cwvStatus=PENDING`，資料限制自動改寫 |

---

## Idempotency Strategy

- `push_to_sheet.py` 本身是覆寫式（`updateCells` + 全量寫回），重跑天然冪等
- **新增 `PROTECTED = {"Recommendations", "Next_Steps"}`**：該分頁若不存在則建立並寫入表頭；若已存在，**只登記 `_Schema` 列，跳過 `updateCells` 與 values 寫入**
- `Recommendations.id` 是去重鍵；`Next_Steps` 以 `period` + `order` 去重
- 六個月 GSC／GA4 改為單次呼叫，避免多次呼叫部分成功導致月份參差
- 同一 period 重跑不會產生重複建議列

---

## Privacy / Governance

### 已完成的治理動作（2026-09-08）

`contracts/business_actual_mapping.v1.json` 已增補 `unresolved_metrics.sql.located_candidate`：

- `approval_state: RECORDED_NOT_APPROVED`
- `status` 維持 `SOURCE_NOT_CONFIRMED`，`mapping_version` 維持 `1.0.0`（未改任何 mapping）
- 記錄 2024／2025／2026 三個分頁的候選列位置與標籤差異（`*Qualified` vs `*SQL`）
- 記錄 2026 逐月觀測值、部分月與空白陷阱、以及 2026-09-07 的回溯修訂事實
- 記錄三項待業務負責人回答的 open questions
- 新增頂層 `revision_log` 說明這是純增補
- **驗證**：JSON 有效，`tests/test_business_actual_importer.py` 11 個測試全過

### 持續約束

- SQL 仍不得匯入為正式指標。定位到列 ≠ 解決口徑
- 存取權限維持 `MYSELF`、`executeAs: USER_DEPLOYING` 不變
- 報告不對 GEO 快照做「本次抓取」的宣稱
- 人工建議必須在版面上與程式推導的數據敘述分離，並標示為人工判斷

---

## Environment Isolation Strategy

此專案**無 UAT／正式之分**，只有一個報表活頁簿 `14lyC4z…`。

唯一的非正式渲染路徑是 `preview_local.py` 產生的本機 `preview.html`。合成／測試資料**不得**寫入活頁簿或 `evidence.json`——沿用 CWV 開發期的既有做法：合成樣本只存在暫存目錄。

人工分頁的測試列請用 `period` 標為不存在的期別（例如 `9999-01`）而非留在本期，這樣既能測試 join 又不會誤入報告。

---

## Integration Strategy

沿用既有機制，**不新增任何憑證**。

| 整合 | 機制 | 位置 |
|---|---|---|
| Google Sheets | OAuth authorized_user，僅 `spreadsheets` scope | `98_環境設定/google-sheets/authorized_user.json` |
| GSC MCP | stdio，`97_Runtime/gsc-mcp` venv 直譯器 | 需 `GSC_CONFIG_DIR`、`GSC_OAUTH_CLIENT_SECRETS_FILE` |
| GA4 MCP | stdio，`97_Runtime/ga4-mcp` venv 直譯器 | 需 `GOOGLE_APPLICATION_CREDENTIALS` |
| CrUX | API key（OAuth 會被回 `INVALID_ARGUMENT`） | `98_環境設定/crux/api_key.txt` |
| Screaming Frog | GUI 執行中時 MCP 匯出會被擋，**不可 kill** | 匯出檔 60 分鐘後自動刪除，須先複製 |
| Workduo | 無本地憑證，維持快照沿用並標示 | — |
| Apps Script 部署 | **手動貼入**（憑證無 `script.projects` scope） | — |

---

## Configuration Design

- `_Meta` 新增 `businessAsOf`、`execViewEnabled`
- `Recommendations.section` 與 `Next_Steps.section` 的值域寫在 `build_report_data.py` 的常數，並輸出到 `_Schema` 供人工參照
- 六個月的起訖由 report period 往回推 5 個完整月計算，**不寫死日期**
- `PROTECTED` 分頁清單為 `push_to_sheet.py` 的模組層常數
- SQL 成熟度門檻讀自 `data_contract.v1.json` 的 `sql_maturity`，不在報告端硬編碼

---

## Test Plan

### 正常路徑

1. `?view=exec` 渲染 4 區塊；`?view=full` 與現況逐項一致（回歸），並多出段末建議與彙總段
2. 六個月 GSC 曝光柱 + CTR 折線雙軸，左右刻度正確；1280px 與 375px 皆無水平溢出
3. GEO Top 5 橫條，SHOPLINE 標色，零值列已濾除
4. GA4 折線六個月，工作階段絕對值與相對 Organic 佔比兩條線並存
5. 摘要依 `order` 匯總四類 Next Step，含 `technical`
6. 詳細版：同一 `id` 同時出現在所屬段末與彙總段，且視覺上可辨識為同一件事

### 邊界事件

7. `Next_Steps` 只有上期列 → 本期區塊顯示 PENDING，「上期項目追蹤」正常列出且 status 由上期 `Recommendations` 帶入
8. `sqlIsMature` 由 false 改 true → 達成率與 MoM 自動出現，**未改任何程式碼**
9. `section` 打錯字 → 該列不渲染，附註列出略過的 `id`
10. `sourceRef` 指向不存在的 id → 該列仍渲染、status 顯示「來源遺失」、附註列出斷鏈
11. `sourceRef` 為空 → 使用 `Next_Steps.status`
12. 同一 `Recommendations` 列被兩條 Next Step 引用 → 兩條都正確帶入同一 status

### 失敗路徑

13. 刪除 `raw/gsc_data.json` 某月 → 趨勢圖斷點，不出現 0
14. 業務第 120 列清空 → SQL 卡顯示「來源未提供」，不顯示 0
15. `Recommendations` 分頁整個刪除 → 詳細版建議段落 PENDING、總覽版全部 Next Step 顯示「來源遺失」，兩版數據段落皆正常

### 冪等與保護

16. 連跑兩次 `push_to_sheet.py`，`Recommendations` 與 `Next_Steps` 內容完全不變、`_Schema` 仍含兩列
17. 兩個人工分頁皆不存在時跑 `push_to_sheet.py` → 自動建立並寫入表頭，不寫入資料列

### 輸出

18. 列印預覽：摺疊附註區塊在 PDF 中已展開
19. `contracts/` 三份合約檔皆為有效 JSON，既有測試全過

---

## Rollout Plan

### 關鍵路徑

到主管會議的關鍵路徑是：**WP1 → 資料層 → 人工產內容 → WP6 → WP7 → WP9**。

**WP8（詳細版的建議渲染）不在關鍵路徑上。** 人員判讀所需的數據，現有詳細版已經全部具備；建議是他們自己寫進試算表的，不需要先渲染出來才能寫。WP8 的價值在於讓下個月的讀者、以及非作者本人看得到建議與證據的對應關係，因此排在 WP9 之後補上，而不是省略。

### Phase 0 — 先驗證假設 ✅ 已完成 2026-09-08

結果見上方〈Phase 0 驗證結果〉。原假設不成立：`AI Assistant` 渠道起點是 2026-05 而非 2026-03，已據此產生第 16 題決策並修訂第 6 題。`yearMonth` 與 `dimension_filter` 皆已實測可用，WP3 風險由「中」降為「低」。

GSC 六個月無此風險（保留期 16 個月），未探測。

### Phase 1 — 資料層（工程）✅ 已完成 2026-09-08

1. **WP1**：`push_to_sheet.py` 加 `PROTECTED`。先做，因為它是永久性的地雷防護——一旦把人工分頁加進 `build_tabs()` 而沒有它，下一次發佈就會把人寫的內容清空
2. **WP2 / WP3 / WP4 / WP5 可並行**（主要落在不同函式，衝突面小）
3. 重跑步驟 3–6，用 `preview_local.py` 檢視**仍是既有 9 段**的詳細版

**Gate ✅ 全數通過**：448 已取代 450；`GSC_Monthly` 12 列（兩站 × 六個月）；`GA4_Monthly` 12 列、`AI_Channel` 3 列；既有 9 段無回歸。

### Phase 2 — 內容（人工，與 Phase 3 並行）⬅ 現在可以開始

Phase 1 的 Gate 已通過。**順序不可顛倒**：必須對著刷新後的數字判讀，否則建議會建立在 450、以及只有兩個月的 GSC 之上。

判讀 → 填 `Recommendations` → 人工＋AI 討論收斂 → 挑選改寫成 `Next_Steps`（帶 `sourceRef`）。

這條線不阻塞工程，但它是整件事的長桿。

### Phase 3 — 渲染（工程）✅ 已完成 2026-09-08

4. **WP6**：雙軸與橫條圖渲染器
5. **WP7**：`resolveActions()` join 與斷鏈處理
6. **WP9**：`doGet(e)` view 分支與 exec 四區塊
7. **部署**：貼回 Apps Script 重新部署，`?view=exec` 與 `?view=full` 實測

**Gate ✅ 全數通過**：總覽版四區塊可用；`?view=full` 九段回歸通過；1280px 與 375px 皆無水平溢出。

**渲染器的實際缺口比預期小。** `groupedBars` 本來就是橫向長條圖，GEO Top 5 直接沿用（只加了一個 `cfg.colors` 讓 SHOPLINE 標色，向後相容）。新寫的只有 `comboChart` 一個——垂直柱＋右軸折線——而它同時承載了 03 的「曝光×CTR」與 GEO 的「AI 工作階段×相對 Organic」。

**join 的五種情況已逐一實測**：帶入上游狀態、無 `sourceRef` 用自己的狀態、斷鏈仍渲染並標記、`section` 值域外略過並記錄、上期項目追蹤跨期帶入狀態。測試列驗證後已清除。

**部署尚未進行**（憑證無 `script.projects` scope，須手動貼入 Apps Script）。

### Phase 4 — 收尾（非關鍵路徑）✅ 已完成 2026-09-08

8. **WP8 ✅**：詳細版段末建議區塊與第 8 段彙總。詳細版現為 10 段（彙總插在第 8 段，來源與方法順延為 9、資料限制為 10）。
9. **凍結**：主管會議前一天凍結，記錄 `businessAsOf`

**WP8 的實作方式**：不去修改五個既有的段落建構器，而是在全部段落建好後依 `sections[].id` 對應貼上——段落 id 本來就等於 `Recommendations.section` 的值，所以整個對應關係集中在一處，日後新增段落不必再接線。段末區塊與彙總表渲染同一份陣列，重複只發生在畫面上，不在維護上。

**已實測**：五個段落（business／gsc／ga4／geo／technical）各自掛上對應建議；彙總表依優先度 → 段落 → 排序排列；`ga4` 類建議只出現在詳細版、不洩漏進總覽版；1280px 與 375px 皆無溢出。

### 時程壓縮時的取捨

若會議時間不足以走完 Phase 3，可退到 **WP1 + WP4 + WP7 + WP9**，總覽版沿用現有單軸折線渲染器只畫曝光。

但這**牴觸決策 5**——「量跌質升」的故事會消失，主管只會看到一條往下的線。若採此路徑，必須在會議上口頭補充 CTR 與排名的改善，並在附註區塊寫明圖表為簡化版本。這是明知的取捨，不是預設路徑。

---

## Non-Goals

- 不修訂 `data_contract.v1.json`；`business_actual_mapping.v1.json` 只做已完成的**純增補記錄**，不改 mapping、不改 status、不改版本號
- 不放寬 web app 存取權限
- 不把技術稽核／CWV／Sitemap／Top 頁面查詢的**數據區塊**帶進總覽版（技術**建議**可經由摘要進入）
- 不新增 Slides／PDF 輸出管線
- 不解決 Workduo MCP 的連線問題
- 不由 AI 自動生成建議寫入報告——建議一律經人工確認後才進分頁
- 不重建詳細版的任何既有數據段落

---

## Future Opportunities

**明確不納入本期 MVP。**

- SQL 成熟後（2026-10-30）補完整的 SQL 達成率與趨勢，並推動業務負責人回答合約裡記錄的三項 open questions
- `owner` / `due` / `anchor` 欄位與詳細版錨點連動
- 彙總段顯示「上期未完成建議」的延續清單
- GEO 逐月可見度趨勢（需先解決 Workduo 歷史資料取得）
- 釐清 `AI Channel leads` 6 月 52 筆的異常值，並把 chatgpt 以外的 AI 來源納入
- 業務數字的完整修訂追蹤（append-only 歷史分頁，`data_contract` 已規劃 `revision` / `supersedes` 語意）
- Screaming Frog 建立月度對照，讓技術項目能判斷月變化而非只描述現況

---

## Work Packages

| # | Goal | Likely files | Deps | Tests | Risk | Done definition |
|---|---|---|---|---|---|---|
| **WP0** | 合約增補記錄 | `contracts/business_actual_mapping.v1.json` | — | T19 | 低 | ✅ **已完成 2026-09-08**。JSON 有效、11 測試全過、status 未變 |
| **WP1** ✅ | `push_to_sheet.py` 支援保護分頁 | `push_to_sheet.py` | — | T16, T17 | 低 | 連跑兩次兩個人工分頁不變且在 `_Schema` |
| **WP2** ✅ | 擴 GSC 到六個月（單次呼叫）＋逐月彙總 | `raw/gsc_pull.json`, `build_report_data.py` | — | T2, T13 | 低 | `GSC_Monthly` 出現 12+ 列，7/8 月數字與現況一致 |
| **WP3** ✅ | GA4 改 `yearMonth` 維度、新增 `ga4Monthly` | `raw/ga4_pull.json`, `collect_evidence.py`, `build_report_data.py`, `push_to_sheet.py` | — | T4 | **低**（Phase 0 已實測 `yearMonth` 與 `dimension_filter` 皆可用，風險已消除） | `ga4Monthly` 含 2026-06～08 的 AI Assistant 與 Organic Search；查詢形狀沿用 Phase 0 已驗證的探測 |
| **WP4** ✅ | 業務 SQL 第 120 列 + `businessAsOf` + 成熟度旗標 | `collect_evidence.py`, `build_report_data.py` | — | T8, T14 | 中（治理） | `sqlIsMature` 正確，達成率未進資料層；448 取代 450 |
| **WP5** ✅ | `aiChannel` 分頁（chatgpt.com） | `collect_evidence.py`, `build_report_data.py`, `push_to_sheet.py` | — | T4 | 低 | 3 個完整月，9 月部分月已排除 |
| **WP6** ✅ | 雙軸 SVG 渲染器 + 橫條圖渲染器 | `apps_script/Report.html` | — | T2, T3 | 中（現有圖表皆自寫單軸 SVG） | 兩種新圖在 1280/375px 皆無溢出 |
| **WP7** ✅ | `resolveActions()` join 與斷鏈處理 | `apps_script/Report.html` | WP1 | T7, T10, T11, T12, T15 | 中 | 四種 join 情況行為正確，斷鏈進附註不靜默 |
| **WP8** ✅ | 詳細版：各段末尾建議區塊 + 新增第 8 段彙總 | `apps_script/Report.html` | WP7 | T1, T6, T9 | 中 | 10 段結構成立，同一 id 兩處呈現可辨識 |
| **WP9** ✅ | `doGet(e)` view 分支 + exec 四區塊 + 摺疊附註 + 列印樣式 | `apps_script/Code.gs`, `Report.html` | WP1–WP8 | T1, T5, T18 | 中 | 兩版並存，full 版回歸通過 |

---

## 收斂狀態

```
GRILL_ME_COMPLETE=YES
CURRENT_STATE_UNDERSTOOD=YES
CARRIER_AND_VIEW_SWITCH_DECIDED=YES
NEXT_STEP_STORAGE_DECIDED=YES
SQL_MATURITY_HANDLING_DECIDED=YES
BUSINESS_RESTATEMENT_HANDLING_DECIDED=YES
GSC_TREND_SPEC_DECIDED=YES
AI_CHANNEL_SCOPE_DECIDED=YES
TRAFFIC_SHARE_DENOMINATOR_DECIDED=YES
GEO_BRAND_PRESENTATION_DECIDED=YES
CAVEAT_PLACEMENT_DECIDED=YES
NEXT_STEP_SECTION_DOMAIN_DECIDED=YES
PERIOD_ROLLOVER_DECIDED=YES
ACCESS_CONTROL_DECIDED=YES
RECOMMENDATIONS_DATA_MODEL_DECIDED=YES
STATUS_AUTHORITY_DECIDED=YES
DETAIL_VIEW_PLACEMENT_DECIDED=YES
PHASE0_PROBE_COMPLETE=YES
AI_TRAFFIC_DEFINITION_DECIDED=YES
GA4_QUERY_SHAPE_VALIDATED=YES
CONTRACT_EVIDENCE_RECORDED=YES
CONTRACT_AMENDMENT_REQUIRED=NO
MVP_SCOPE_DEFINED=YES
SECURITY_GOVERNANCE_BLOCKER=NONE
READY_FOR_IMPLEMENTATION=YES
```
