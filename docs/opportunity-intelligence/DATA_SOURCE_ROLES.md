# DATA_SOURCE_ROLES

下列是新層責任契約提案；source_class 和 unit 必須與 evidence 同行。JOIN_KEYS 代表在核對 scope 後可以連結，不表示可互當分母。

| Source | ROLE / SOURCE_CLASS | BEST_FOR | NOT_VALID_FOR | GRAIN | FRESHNESS | LIMITATION | JOIN_KEYS |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Ahrefs | 市場探索、競品 / THIRD_PARTY_ESTIMATE | keyword demand、competitor ranks、backlink gap | actual traffic、formal business conversion、GSC missing=0 | keyword×country×target×snapshot；link×crawl history | snapshot as_of + keyword last_update；月更 | 估計、非完整市場、各 endpoint country 語義不同 | keyword_id、url_id、competitor_id、scope_id |
| GSC | 自有 Google Search 表現 / FIRST_PARTY_SEARCH_ACTUAL | traction、CTR、decay、page-query map | 全市場需求、非 Google 流量、逐使用者 conversion | property×query×page×country×device×search_type×period | final 完整月份；shortlist 最近完整 28 天 | anonymization、Top N、dimensions 改變母體、延遲 | query_id、url_id、search_scope_id |
| GA4 | 行為診斷 / FIRST_PARTY_BEHAVIOR_DIAGNOSTIC | landing engagement、CTA、quality guardrail | keyword discovery、正式 leads、跨 property 未去重總量 | property×hostname×landingPage×channel×period；event grain 另列 | 完整期間並核對 timezone/thresholding | consent、attribution、event scope 與 sessions 不同 | url_id（由 host+path）、ga4_scope_id；不以 query join |
| Google Search | live intent / LIVE_SERP_SNAPSHOT | page types、PAA、AIO、forums/videos、dominant domains | 月搜尋量、未觀測 feature=無 feature、unbiased 全市場排名 | query×locale×location×device×time×provider | shortlist 七日內，批准前重新驗 | 個人化、位置、動態 feature、擷取不完整 | query_id、observed_url_id、serp_snapshot_id |
| SF | 技術執行條件 / TECHNICAL_CRAWL_EVIDENCE | indexability、canonical、snippet、inlinks | demand、business impact、counts=全部要修 | crawl_id×requested_url×final_url×issue/config | 月 crawl；shortlist 14 日內；重大變更重抓 | crawl scope/exclusions、robots/settings、assets vs pages | url_id、crawl_id、crawl_config_hash |
| Workduo | monitored GEO sample / MONITORED_GEO_SAMPLE | prompt/entity/citation/topic gaps | 全球 AI market share、實際 visits、未追蹤 prompt=0 | project×prompt_version×platform×region×run×entity | monthly fixed cohort；shortlist 最近完整 28 天 | 題庫、run denominator、模型與 entity aliases 改變 | prompt_id、topic mapping、competitor_id、citation_url_id |
| CrUX | field UX / FIELD_UX_EVIDENCE | performance risk、UX guardrail | URL diagnosis from origin、排名因果、7-day MoM | origin OR URL×form_factor×28-day window | 最新可用完整 window；不可改稱報表月 | Chrome eligible sample、低流量無資料、窗口重疊 | origin_id 或 url_id（保留 fallback_type） |
| Business Actual | 正式商業成果 / FORMAL_BUSINESS_ACTUAL | aggregate leads、已批准 outcome | 按 query/URL 分配 revenue、unresolved SQL、GA4 CTA | approved metric×segment×lead cohort×as_of revision | monthly restatement；SQL 遵守 month-end+60 | topic attribution 未批准、部分 metrics unresolved | business_theme 僅人工關聯；有 attribution contract 才可 outcome join |

## Cross-source 比較規則

允許「GSC 實際 traction + Ahrefs 市場估計 + SERP intent」支持同一假說，禁止 Ahrefs traffic / GA4 sessions、GSC clicks / GA4 sessions 被命名為 conversion rate。GA4 engagementRate 只以相同 request population 的 engagedSessions / sessions 計算；CTA 保留 event count 或已確認 session-scoped diagnostic rate，不能把 event counts 當成功人數。

每個 denominator 明確記在 evidence。估計量不跨來源相加。GSC impressions 在同一 query 多 URL 也不等於獨立市場需求；cluster demand 對近義詞使用代表詞或 max，預設不直接 sum volume。CrUX origin warning 可以提示整站風險，但沒有 URL causal link 時不能聲稱該頁是 technical blocker。

## Business Theme / Funnel

可用分類：ONLINE_STORE、POS、OMO、CRM、PAYMENTS、LOGISTICS、SOCIAL_COMMERCE、GROUP_BUYING、AI_AUTOMATION、MERCHANT_GROWTH、ENTERPRISE_RETAIL、UNMAPPED。前述是 taxonomy，不是已批准的商業優先序。Workduo metadata 的 payments、smart-omo、social-commerce、SHOP Builder 只能支持產品相關性候選。

intent：INFORMATIONAL、COMMERCIAL_INVESTIGATION、TRANSACTIONAL、NAVIGATIONAL、MIXED、UNKNOWN。funnel：TOFU、MOFU、BOFU、UNKNOWN。Commercial intent 不直接等於高 business_score。

Business relevance overlay 由人工指定 `theme_id, relevance_band, strategic_priority, evidence_ref, reviewer_id, rationale, valid_from, valid_to, override_revision`。保存原始建議值及 override；過期或沒有批准則 business_score=null，不能以 CPC 代替。reviewer_id 是內部 opaque ID，不存姓名／email。跨主題 commercial outcome attribution 必須另有 approved mapping，現有 Non-paid aggregate 不足以分配到各 URL。

## WP7 SERP validation boundary（2026-09-10）

Google Search 的 WP7 角色固定為 `LIVE / OBSERVED SERP VALIDATION EVIDENCE`，source
class 為 `LIVE_SERP_SNAPSHOT`。它只驗證 WP5 shortlist 的 exact canonical query 與
locale/country/device/search scope；不做全 keyword discovery，不把 cached Ahrefs snapshot
冒充本次 live evidence。每筆 snapshot 保留 observed/retrieved timestamp、provider
provenance、organic result rows、page type、owned/approved competitor mapping、feature
state 與 deterministic `snapshot_hash`。AIO/PAA 未捕獲是 `NOT_AVAILABLE`，不是不存在。

WP7 validation 只輸出 `SERP_VALIDATED`、`SERP_CONFLICT` 或 `SERP_NOT_CHECKED`，並 pin
SERP evidence 與原 candidate evidence 的 `evidence_id + revision + content_hash`。它不
改寫 WP5 score/confidence、GSC/Ahrefs metrics 或 candidate review state，也不會自行建立
unmapped competitor entity。
