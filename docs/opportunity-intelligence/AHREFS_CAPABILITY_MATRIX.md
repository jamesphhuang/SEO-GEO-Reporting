# AHREFS_CAPABILITY_MATRIX

探測日 2026-09-10。只保留 capability metadata，沒有關鍵字／流量原始資料、API key、token 或 credential。AVAILABLE 僅指下表實測 request scope；工具名稱存在不等於 entitlement 全開。

## 帳戶與接入

本 session 有原生 `mcp__ahrefs_mcp__*` tools，透過 Ahrefs API v3。先用 `doc` 讀 input/output schema，再做 bounded probes。`subscription-info-limits-and-usage` 成功（0 units）：Standard 2022, billed yearly；workspace monthly units limit 400000、probe 前已用 12773、reset 2026-09-21。key-level units limit 為 null；不將 null 解釋成 workspace 無限。

八個 data probes 每個回報 50 units，共 400 units；單次時點資料，其他使用者可能同時消耗額度，不能據此算目前剩餘額度。MCP connector 處理認證；本機 credential 儲存機制、MCP 是否經 OAuth proxy、CLI 無人值守權限仍 UNKNOWN。REST API 使用 API key 的方式有官方文件，不因 connector 已登入就把它轉存進 repo。

| 能力 | 狀態 | evidence / 限制 |
| --- | --- | --- |
| Subscription / usage metadata | AVAILABLE | live subscription call 成功；方案名稱不保證每個 endpoint |
| Keyword metrics | AVAILABLE | `keywords-explorer-overview`，TW、一個 seed、四個欄位、limit 1 成功；未測所有 metric |
| Organic keywords | AVAILABLE | `site-explorer-organic-keywords`；shopline.tw、domain、tw、2026-09-09、limit 1 成功 |
| Organic competitors | AVAILABLE | `site-explorer-organic-competitors` 同範圍、limit 1 成功；沒有自動批准 competitor registry |
| Top pages | AVAILABLE | `site-explorer-top-pages` 同範圍、limit 1 成功 |
| Referring domains | AVAILABLE | `site-explorer-referring-domains`，domain、limit 1 成功；不宣稱該資料有 TW geographic segmentation |
| Backlinks | AVAILABLE | `site-explorer-all-backlinks`，domain、limit 1 成功；link metrics 是競爭估計／crawl observation |
| Volume history | LIMITED | `keywords-explorer-volume-history`，TW、一個 seed、2026-08-01～08-31 成功一筆；更深歷史 entitlement 尚未測 |
| Organic historical comparisons | UNKNOWN | doc 有 date/date_compared、歷史工具；未實測跨期 query loss／replacement |
| SERP snapshot | LIMITED | `serp-overview`，TW、一個 seed，top_positions 1 實際回六列；限制的是 organic positions，不是總 feature rows；不是保證 live Google |
| SERP features / AIO enum | LIMITED | doc 列 ai_overview、ai_overview_sitelink、ai_overview_found、question、discussion、video 等；欄位存在不代表指定 query 有 AIO |
| AIO 完整回答／citation evidence | UNKNOWN | Brand Radar AI responses/citations 工具有暴露，但本輪未 probe 權限與覆蓋；不能替代 Workduo 固定樣本 |
| Dedicated Content Gap endpoint | UNAVAILABLE | 本輪 tool inventory 未提供同名 endpoint；允許從 competitor keyword sets 衍生，但必須做 coverage / scope audit，不偽造 endpoint |
| Derived Content Gap | LIMITED | 基礎 keyword / competitor endpoints 成功；完整 key sets 尚未取齊、邏輯未實作 |
| Country/database | LIMITED | TW 實測成功；doc country ISO alpha-2，其他 database 及語言覆蓋未測 |
| Domain / prefix / exact / subdomains | LIMITED | 四 modes 在 doc；僅 domain 實測；default subdomains 不可沿用到正式 scope |
| Export / pagination | LIMITED | doc limit 預設 1000；各 endpoint output options 不相同；未測上限與完整翻頁。不得將 limit rows 當全母體 |
| Local integration / CLI | UNKNOWN | 月報 code/contracts/tests 搜尋無 Ahrefs ingestion；有三份 5 月 Site Audit 摘要 CSV；無正式 API adapter |

## 官方限制與本機政策分開

[Ahrefs API 官方說明](https://docs.ahrefs.com/en/api/docs/introduction)（2026-09-10 讀取）：一般預設 60 requests/min，429 也可能是動態 throttling；非免費 request 最低 50 units，成本依 row/field；免費 endpoint 例外。這是 provider 預設，非此帳戶 SLA，不能保證最大 export rows 或所有歷史權限。

提案：單 worker、每 endpoint 明確 select、limit、timeout；429 honor Retry-After，最多三次 bounded exponential backoff；401/403 不盲重試。每輪 budget 在 request 前檢查，cache key 包 scope/date/modes/fields/schema；回傳 metadata 另記 actual units。scope 未核准時只做這種小量 probe，不啟動 full discovery。SERP 的 row cap 另設 output truncation flag，不能假設 top_positions 就是 hard row cap。

## CURRENT MCP CAPABILITY

| Source | 本輪已驗證 | 未驗證 |
| --- | --- | --- |
| GSC | get_capabilities 顯示 authenticated；list_properties 可見 `https://shopline.tw/`、`sc-domain:blog.shopline.tw` | 本輪未重抓 search rows；完整 query×page 分頁與匿名 query coverage 待 smoke |
| GA4 | get_account_summaries 可見 contract 的 257016301 / 399614424 | landingPage×channel、thresholding、data loss 與 event scope 未重驗 |
| SF | sf_check 24.3 / licensed；list_crawls 最新兩站 09-06，皆 100%；另有歷史 crawl | URL issue / inlink exports 未重新匯出；歷史設定等價未驗 |
| Workduo | projects 成功，SHOPLINE TW；queries pageSize 1 成功；同一 query 09-01～09-07 visibility metrics 成功一列 | 全 prompt set、各平台、citation 實際資料與 run denominators 未取齊；接入舊 collector 未完成 |
| Google Search | `web.run` 可一般搜尋與讀官方文件；browser 能力存在 | 無已驗證可回 TW/device/location/PAA/AIO 完整結構的 Google live SERP adapter；SERP_NOT_CHECKED 為預設 |
| CrUX | repo 有 queryRecord / queryHistoryRecord code；live workbook 有 window / retrievedAt | 本輪未使用金鑰重新 query；目前 API entitlement / 無人值守 access 未 smoke |
| Sheets / Drive | root metadata、两 workbook metadata、bounded schemas/registries 可讀 | remote Apps Script deployment / ACL 未重驗 |
| Business Actual | 已讀正式 mapping；僅 non_paid_leads 確認，SQL / successful_conversions unresolved | 本輪不重新盤查 Salesforce、不讀 lead rows；topic attribution contract 缺席 |

Workduo project metadata 中可見 WACA aliases 混有 Ecuador 字樣、Shopify 與 Shopify TW 並存：這是 **ENTITY_MAPPING_REVIEW_REQUIRED** 的線索，不能直接把它們當同一母體加總，也不能僅依名字自動合併。標為 registry QA 待辦。

## WP2 re-probe and implementation boundary（2026-09-10）

本輪重新以 runtime tool discovery + `doc` schema 做 bounded smoke，未保存 raw rows：

| 能力 | 本輪狀態 | 實測範圍 / 成本觀察 |
| --- | --- | --- |
| Organic Keywords | AVAILABLE | `site-explorer-organic-keywords`、`shopline.tw`、TW、domain、2026-09-09、`limit=1`；returned 1 row、50 observed units |
| Organic Competitors | AVAILABLE | `site-explorer-organic-competitors`、同 target/country/date、domain、`limit=1`；returned 1 row、50 observed units；subdomains 組合被 runtime 判為 invalid params，不能當成 entitlement failure |
| Dedicated Content Gap | UNAVAILABLE | runtime inventory 沒有 dedicated Content Gap endpoint；本輪不以其他大量 endpoint 冒充 |

WP2 adapter 只處理前兩項；Content Gap 由 manifest 明確標為 `NOT_AVAILABLE/CAPABILITY_GAP`。client hard caps 為每 run 4 requests、500 observed units、每 endpoint 5 rows、2 pages、30 秒 timeout、每次最多 1 retry；provider `limit` 或 `top_positions` 不等同 trusted output limit。units 未由 provider 暴露時保持 `UNKNOWN`，不估算精確成本。
