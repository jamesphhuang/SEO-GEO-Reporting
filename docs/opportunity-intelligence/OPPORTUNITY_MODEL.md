# OPPORTUNITY_MODEL

所有門檻是 `rules_version=proposal-1` 的待校準預設，不是已驗證效益模型。本文件定義規則與不確定性，不能據此直接產正式建議。

## Canonical entity layer

| Entity | Stable identity / fields | 關聯規則 |
| --- | --- | --- |
| Topic Cluster | opaque `topic_cluster_id`；topic_name、primary_keyword、supporting_keywords、search_intent、funnel_stage、business_theme、asset_type、existing_urls、target_url、related_prompts、competitors、mapping_version | ID 不隨名稱改變；merge/split 保存 supersedes、valid_from/to；批准後才當 authoritative mapping |
| Keyword | keyword_id = hash(normalized_text, language, country, normalization_version) | 保留 original_text；Ahrefs keyword 是一個 source observation，不覆蓋 GSC query |
| Query | query_id，text + language + country；observation 還需 property/device/search_type/period | query→keyword exact lexical mapping 可自動；語義近似需 explicit mapping confidence |
| Prompt | project_id + provider_query_id + prompt_version + region + language | 每次修改 prompt 文字／region 建新 version；platform/run 屬 observation，不能遺失 |
| URL | url_id + sanitized observed URL；canonical assertion 另有來源/時間 | URL aliases many-to-one 需 redirect/canonical evidence；有衝突不自動合併 |
| Competitor | competitor_id、entity_aliases、domain/prefix scope、region、approval | brand entity 與 ranking domain 不一對一；子產品不得與母品牌重複計算 |
| Business Theme | theme_id + approved relevance overlay | 保留人工 override revision；無 owner evidence 時 UNMAPPED 或 unknown value |

Text normalization：Unicode NFC、trim、collapse whitespace、Latin casefold；不自動繁簡轉換、不刪中文標點、不把「平台推薦」與「平台費用」當同一意圖。保存 versioned dictionary；品牌／非品牌由批准字典匹配，歧義回 REVIEW_REQUIRED。

URL normalization：host lowercase、標準 port、去 fragment；只移除 versioned allowlist 的 tracking params。保留 path case、語義 query params；HTTP/HTTPS、www/non-www、trailing slash 不在無證據時合併。GA4 僅取 host + landingPage path；禁止抓含個資 query string。URL 輸入先去除 credential/userinfo 及 PII-like params，不能安全清理者 quarantine，不保存 raw URL。

TopicMembership 是 edge：`entity_type, entity_id, topic_cluster_id, mapping_method, mapping_confidence, evidence_refs, reviewed_by_id, valid_from/to, mapping_version`。一個 entity 可多主題，但同一排序 cohort 只指定一個 primary membership，避免相同 evidence 被加總；支援 derived secondary memberships，不刪原始 grain。

示意 topic（**synthetic，非實際商機**）：`ECOMMERCE_PLATFORM_COMPARISON`，電商平台比較；keywords：電商平台、電商平台推薦、網路開店平台、電商系統比較；prompts：台灣有哪些電商平台、新手適合什麼電商平台、SHOPLINE 跟 WACA 怎麼選。意圖 commercial investigation，funnel MOFU，theme ONLINE_STORE 候選；existing_urls/target_url 仍須 inventory 核對，不捏造 SHOPLINE 已有比較頁。

## Common evidence gates

每條 detection 產 `rule_id/version, matched_conditions, missing_conditions, conflicting_evidence, disqualifiers, evidence_refs, action, validation_state`。evidence refs 必须可解析到 immutable record，且 scope/period/coverage 可比。

- `INSUFFICIENT_EVIDENCE`：缺 required evidence 或 completeness；不等於 DO_NOTHING，不批准執行。
- `CONFLICTING_EVIDENCE`：intent、canonical、商業 scope、日期互相矛盾；交人工裁決，不平均消掉。
- `DO_NOTHING`：足夠證據確認近期沒有合理可執行收益，附理由與重看日期。低 confidence 不是 DO_NOTHING 的理由。
- 真實 zero：request 成功且 exact bucket 完整、沒有 suppression/truncation 才能記數值 0；「未回傳 query」是 not observed，不能等同不存在。

初始 thresholds：meaningful impressions=最近完整 28 日 ≥100；CTR investigation ≥500 impressions；用同 property/country/device/search_type/brand cohort 校準，樣本稀少時不硬套數字。內容改版／algorithm/seasonality/confounding 記成 alternative explanations。

## Opportunity taxonomy / entry criteria

| Type | Entry criteria + required evidence | Optional evidence | Disqualifier / unresolved gate | Recommended action |
| --- | --- | --- | --- | --- |
| QUICK_WIN | GSC query×URL position 4–15、≥100 impressions；Ahrefs 同市場 demand>0；inventory relevant URL；SERP intent fit；SF indexability check | GA4 quality、internal links、Workduo | critical blocker→TECHNICAL_UNLOCK；錯 intent→CONFLICT；Top-N-only 無 pair→INSUFFICIENT | UPDATE_EXISTING |
| CTR_OPPORTUNITY | GSC 同 cohort 兩個非重疊 28-day windows，position change ≤1、current impressions≥500；CTR 低於 cohort expectation 至少20% relative 或下滑；SF title/meta issue；SERP snippet mismatch | Ahrefs SERP features、query segments | SERP feature/layout 改變可解釋 decline；device mix 漂移；無足夠同 cohort baseline 不算 expected CTR | SERP_SNIPPET_OPTIMIZE |
| CONTENT_GAP | ≥2 個批准 competitor 在同市場 Top10；demand evidence；GSC no meaningful observation且coverage有註記；完整 URL inventory 無 matching asset；SERP page type fit | GA4 類似頁、business brief | inventory 缺漏不能 CREATE_NEW；有相同 intent URL 優先 UPDATE；競品僅品牌導航 query 排除 | CREATE_NEW，asset 可為比較頁/工具/FAQ/產品頁，不限文章 |
| CONTENT_DECAY | GSC query×page 至少6完整月、最近兩月 clicks/impressions 趨勢惡化（初始≥20% vs 前兩月）；SF blocker排查；內容變更log | Ahrefs keyword loss / competitor replacement、YoY | seasonality/追蹤scope改變/搬站未解；site monthly totals 不能推出單頁 decay | UPDATE_EXISTING；CONSOLIDATE 需另過 consolidation gate |
| TECHNICAL_UNLOCK | GSC page demand或有競爭可行性；SF URL-specific indexability/canonical/status issue 或 URL-level CrUX risk；issue可重現 | Ahrefs demand、模板影響範圍 | origin CrUX 不能當單頁 cause；刻意 noindex/非目標頁不修；抓取設定造成 false positive先排除 | TECHNICAL_FIX；其他 action 記 dependency |
| GEO_GAP | 固定 prompt/version×platform×region matched runs，SHOPLINE低於同組競品；content answer/entity/evidence coverage gap；topic mapping已審；live SERP topic relevance | Ahrefs competitor content/authority、citation evidence | sample不固定、entity alias有污染、denominator未知→INSUFFICIENT；未取citation不能聲稱citation gap | GEO_ENHANCE；若根本無asset需另審CREATE_NEW |
| AUTHORITY_GAP | relevant URL、intent/technical合格；Ahrefs linking domains與同意圖競爭頁比較，manual relevance/quality抽查；有demand | Workduo citation sources、品牌提及 | DR低單一理由不足；spam/付費操縱不能做解法；無可用asset先更新 | AUTHORITY_BUILD（原創研究、引用資產、合作推廣） |
| INTERNAL_LINK_OPPORTUNITY | SF source→target inlink graph；有 indexable relevant source page；target需求與intent確定 | GSC source/target traction、Ahrefs target rank | navigation/template重複不能算額外頁數；noindex/source不相關；不存在URL不能推薦連結 | INTERNAL_LINK |
| CONSOLIDATION | 同query/intent多URL，GSC多期ranking URL交替或訊號分散；SERP/人工確認重複；SF canonical/redirect可執行；內容差異檢視 | Ahrefs URL backlinks、GA4 quality | 多URL本身不是cannibalization；不同intent/語言/產品頁不合併；migration/owner未決不批准 | CONSOLIDATE（指定survivor、redirect、links、監測） |
| DO_NOTHING | scopes/evidence充分；無material gap、近期實驗觀察中或預期效益低於已核准成本門檻 | 已完成action log、穩定outcome | evidence不足不能用此類掩蓋；critical incident不可忽略 | DO_NOTHING 或 MONITOR，有review_at |

## Cross-source decision procedure

1. Validate source envelope、去重與 coverage；建立 query↔URL 明細，禁止把兩個各自 Top25 join。
2. 以 topic/intent/inventory 產候選假說，先辨別有沒有既有相符 asset。
3. SF critical blocker precedence：先 TECHNICAL_FIX，內容更新留 dependency，不能同 URL 重複扣月度資源。
4. 第一輪 provisional scores 僅用於 shortlist；缺 required evidence 的 candidate 可排「待查證」queue，不進正式執行排名。
5. shortlist 才 live SERP，intent conflict 優先於高分；過期則 SERP_NOT_CHECKED 重新驗證。
6. 決策優先：CONFLICT/INSUFFICIENT → MONITOR；critical blocker → TECHNICAL_FIX；overlap證實 → CONSOLIDATE；existing intent fit → UPDATE/SNIPPET/LINK；inventory確認空缺 → CREATE_NEW；GEO 特有缺口 → GEO_ENHANCE。
7. 一個 primary opportunity_type/action；次要發現放 related_opportunity_ids / dependency_ids，不額外製造重複資源承諾。合併/新增由人批准。

例 A–F 分別由 QUICK_WIN、CONTENT_GAP、CTR_OPPORTUNITY、CONTENT_DECAY、GEO_GAP、TECHNICAL_UNLOCK 規則處理，不是一個 source_count IF。GEO enrichment 不只 schema：可讀回答結構、比較證據、來源日期、品牌實體清楚性、可被引用的原創資料、第三方 citation quality，需指出實際缺什麼。

## Action taxonomy

CREATE_NEW、UPDATE_EXISTING、CONSOLIDATE、TECHNICAL_FIX、INTERNAL_LINK、SERP_SNIPPET_OPTIMIZE、GEO_ENHANCE、AUTHORITY_BUILD、MONITOR、DO_NOTHING。

每個可執行 action 要有 target asset、owner_id、effort_band、dependencies、acceptance checks、measurement_plan_id；CREATE_NEW 可在候選階段 target_url=null，但批准前必須有 target asset/path proposal；CONSOLIDATE 必須列 from_urls 與 survivor，不能自動刪頁/redirect。
