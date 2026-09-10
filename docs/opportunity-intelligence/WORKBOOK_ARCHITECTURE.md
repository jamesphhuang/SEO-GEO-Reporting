# WORKBOOK / REPORT INTEGRATION

## 已回讀 schema（2026-09-10）

正式 workbook `14lyC4zotKGBGg90CExf3q-hPk7awRAvUgIoEYAn1QtI` 的 `_Schema!A1:B30`：

| Tab | fieldsCsv |
| --- | --- |
| _Meta | key,value |
| Business | label,julTarget,julActual,julReach,augTarget,augActual,augReach,momChange,gap,sepTarget,sqlStatus,sqlLabel,sqlTarget,sqlActual,sqlPrevActual,sqlMatureOn,sqlIsMature,sqlReach,sqlMomChange,sqlSourceStatus,sqlSourceRow |
| GSC_Monthly | siteLabel,month,monthLabel,days,clicks,impressions,ctr,position |
| GSC_Delta | siteLabel,clicksJul,clicksAug,clicksChange,imprJul,imprAug,imprChange,ctrJul,ctrAug,ctrChangePt,posJul,posAug,posChange |
| GSC_Pages | siteLabel,page,clicks,impressions,ctr,position |
| GSC_Queries | siteLabel,query,clicks,impressions,ctr,position |
| GA4_Channels | propertyId,siteLabel,hostname,channel,sessionsJul,sessionsAug,sessionsChange,usersAug,engagementJul,engagementAug |
| GEO_Workduo | entity,visibilityJul,visibilityAug,visibilityChangePt,sovJul,sovAug,mentionsAug,daysAug |
| Sitemaps | siteLabel,path,status,warnings,errors,lastSubmitted,lastDownloaded,staleDays,submittedCount,note |
| CWV | group,siteLabel,formLabel,metricLabel,metricShort,unit,p75,rating,goodShare,needsShare,poorShare,goodThreshold,poorThreshold,prevP75,prevEnd,change,periodFirst,periodLast |
| CWV_Trend | siteLabel,formLabel,metricShort,unit,periodEnd,p75 |
| CWV_Missing | siteLabel,formLabel,reason |
| Technical_SF | severity,siteLabel,issue,count,share,scope,note |
| SF_Crawls | siteLabel,siteCrawled,crawlDate,elapsed,urlsEncountered,urlsCrawled,internalUrls,internalIndexable,internalNonIndexable |
| SF_Excluded | item,reason |
| GA4_Monthly | siteLabel,month,monthLabel,channel,sessions,shareOfOrganic |
| AI_Channel | month,monthLabel,leads,sql,cvr,sqlIsMature,sqlMatureOn,sourceLabel |
| Sources | id,label,method,filters |
| Recommendations | id,period,section,order,priority,text,status,evidenceRef,owner,due,anchor |
| Next_Steps | period,section,order,text,sourceRef,status,owner,due |

`Recommendations.status` 是既有執行進度權威。`resolveActions()` 用 id 跨期 join；有 sourceRef 的 Next Step 帶入 Recommendations.status，斷鏈仍顯示並標來源遺失。這是status resolution，不是機器可驗的approval系統。不能將「表內有一列」自動當新engine有批准證據。

## 新資料載體（僅 preview/UAT 提案）

| Tab / artifact | Grain / key | 內容與權責 |
| --- | --- | --- |
| Ahrefs_Keywords | evidence_id × keyword × target × country × as_of | normalized evidence；estimate flag、volume mode、coverage；原始API response不進主報表 |
| Ahrefs_Competitors | evidence_id × competitor scope × snapshot | competitor observation、registry approval分開 |
| Ahrefs_Content_Gap | derived_set_id × keyword × competitor | 寫derived=true、input hashes與coverage；不是provider endpoint |
| Topic_Clusters | topic_cluster_id × mapping_version | Topic metadata、business overlay refs；多值關聯由membership artifact維護 |
| Opportunity_Evidence | opportunity_id × revision × evidence_id | 只列normalised摘要/claim、source_class、date、scope、status、可稽核reference；unique複合鍵 |
| Opportunity_Candidates | opportunity_id × revision | score/profile、confidence、validation、action、why、effort、missing/conflicting、target；只由engine產 |
| Opportunity_Reviews | review_event_id | append-only review decision，opaque reviewer_id、candidate hash、reviewed_at；只供human surface |
| Opportunity_Actions | action_id | approval_ref、target、completed_at、measurement_plan、dependencies |
| Opportunity_Outcomes | action_id × checkpoint × revision | baseline/window/evaluation、evidence_refs、outcome、limitations |

Sheets 是有行數限制的投影，不當原始payload database。完整 normalized evidence 保存在access-controlled artifacts；sheet僅shortlist必要列。不得把raw keyword / prompt 的任意文字當可執行formula或HTML。

## 詳細版「SEO／GEO 內容與關鍵字機會」

置於數據診斷後、建議彙總前。四組：Quick Wins、Content Gaps、GEO Gaps、Content Decay / Technical Unlock；其他類型用action/type filter補充。首屏最多20候選，SERP驗證shortlist起始cap30（是本系統預算提案，不是API限制），不顯示數千keywords。

每列：topic、existing/target asset、action、priority band、score/profile或unknown interval、confidence、estimate/actual標籤、required gaps、why now、effort/dependencies、review state。展開顯示可比日期與source evidence、alternative explanation、30/60/90d驗證計畫。不得把未批准候選混在正式Recommendations或executive Next Steps。缺資料時能看到「未評估／待驗證」，不造示例商機假装production結果。

## Recommendation governance bridge

1. engine產immutable candidate revision，human surface讀它；不直接寫兩個正式人工tabs。
2. 人工對exact revision/hash批准，必有scope-approved、PASS、medium+confidence、完整score、目標/effort/measurement plan。reviewer server驗identity，不接受engine自行填approved_by。
3. bridge產preview promotion manifest：`opportunity_id, revision, approved_hash, review_event_id, recommendation_id, target_env, destination_id, text, evidence_bundle_ref, section, action_status, content_hash`。
4. existing section allowlist維持business/gsc/ga4/geo/technical；SEO候選映射gsc、GEO映射geo、technical映射technical。新opportunity section不直接塞入舊allowlist；UI擴充另包。
5. idempotency key = destination + opportunity_id + approved_revision；timeout先readback再判斷是否重送。人工已改text/status/owner/due時不可覆寫，產conflict待review；永不跑一般publisher去覆蓋manual tabs。
6. `Recommendations.evidenceRef` 放short safe bundle reference，不是raw payload。將新candidate/evidence refs對應寫入sidecar manifest，既有field不硬塞一份JSON。
7. executive Next Steps由人從已approved recommendations選取改寫；sourceRef指向確切recommendation id；不能自動挑Top3並發布。

新層資料變更時舊批准不再適用；撤回用事件與取消狀態，不刪review history。bridge activation前需UAT雙人/身份驗證政策確定；本輪不創建UAT、不寫正式分頁。

## GA4 quality / SF prioritization

GA4 landing query沿用`ga4_scope.v1`；property與exact hostname、channel一併保留。sessions、engagedSessions、engagement rate須同request grain，CTA events另組；低engagement只能促成人工檢查intent/UX，不足以證明商業價值低。原始event query string、user identifiers不收集。

SF issue counts → URL-level allowlisted issue export → safe URL map → GSC exact page/query demand → Ahrefs context → technical / snippet / internal-link candidates。1395之類總count不直接映射effort。以unique actionable HTML URL×issue去重；image assets另掛其引用頁，不拿圖片數當頁數。critical indexability先行，其餘按opportunity×effort排序，不做「修全部」工單。
