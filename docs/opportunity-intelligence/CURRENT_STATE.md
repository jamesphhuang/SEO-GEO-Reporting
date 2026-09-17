# PROJECT GROUND TRUTH

盤點日：2026-09-10，Asia/Taipei。本輪是架構設計與唯讀 capability probe；文件中的提案不代表功能已上線。先讀本檔，再讀 ARCHITECTURE、ROADMAP、NEXT_TASK。

## Git baseline

| 項目 | 本輪實測 |
| --- | --- |
| 工作目錄 | `/Users/pohsunhuang/Library/CloudStorage/GoogleDrive-james.ph.huang@shopline.com/我的雲端硬碟/SEO／GEO Reporting/99_專案程式` |
| integration branch | `docs/opportunity-intelligence-foundation` |
| `ARCHITECTURE_FOUNDATION_SHA` | `9376711` (`docs(opportunity): design opportunity intelligence layer`) |
| `HANDOFF_BASELINE_SHA` | `692f475` (`docs(opportunity): record integration baseline`) |
| `CURRENT_HANDOFF_HEAD` | branch HEAD（以 `git rev-parse HEAD` 與 remote ref 實測；不在自身 commit 內硬編 SHA） |
| fetch 後 origin/main | `4e30cec2a7cb446c0defa06b315c0b295a01b9af`，PR #6 merge |
| merge-base | `4e30cec2a7cb446c0defa06b315c0b295a01b9af`；branch-only lineage 僅含 foundation、handoff baseline 與 docs-only handoff clarification commits |
| 本機 main | `dc4374e`，落後遠端；不可誤當最新 baseline |
| worktree | 原 dirty worktree 保留；乾淨 integration worktree 在 `/private/tmp/seo-geo-opportunity-foundation`；未刪除、stash 或 reset 原工作樹 |
| fetch / integration | fetch 初次受 sandbox 限制，取得執行權限後成功；clean integration worktree 已驗證並推送 `docs/opportunity-intelligence-foundation`，remote branch 狀態由最後 fetch 回報 |

其他本機 feature branches：`feat/two-tier-seo-geo-report`、`chore/untrack-appsscript-bundles`、`chore/untrack-preview-artifacts`、`fix/chart-label-clipping`、`fix/impressions-chart-scale`。名稱不證明有人仍在開發；現有 tips 均位於 main 已合併的歷史，不刪分支。

開始時 dirty state 全數分類 **UNRELATED（本輪範圍外，保留）**：

| 路徑 | 分類依据 |
| --- | --- |
| `outputs/monthly_report_2026_08/README.md` | 既有 v1 部署補記；與較新封存紀錄矛盾，保留原檔 |
| `outputs/monthly_report_2026_08_v2/report_data.json` | SQL 三欄由 null 改為數值，與 HEAD `business_sql()` 明示的 09-09 顯示例外吻合 |
| `outputs/business_metric_source_resolution_2026-09-06/` | 先前 aggregate 業務來源對帳產物 |
| `outputs/weekly_report_2026_09_01_07/` | 先前 9 月第一週報表、取數與渲染產物 |

沒有 UNKNOWN 才開始建立新文件。未改以上原有 dirty 檔案；本輪只在 clean integration branch 提交 architecture 與 handoff docs，沒有 production mutation。後續若出現新的未知變更，停止 mutation。

## 本機程式與資料流

| 層 | 目前位置與限制 |
| --- | --- |
| 月報取數 | `outputs/monthly_report_2026_08_v2/mcp_client.py`、`collect_evidence.py`；stdio GSC/GA4，加 Sheets actual、舊 Workduo snapshot |
| 月報 model | 同目錄 `build_report_data.py`、`cwv.py`、`sf_technical.py`；期間與路徑仍有月份耦合 |
| 月報投影 | `push_to_sheet.py` 覆寫一般分頁；`PROTECTED` 保留 Recommendations / Next_Steps；不是 append-only snapshot writer |
| Apps Script | 同目錄 `apps_script/Code.gs`、`Report.html`、`appsscript.json`；`SpreadsheetApp.getActive()`，讀 `_Schema`；詳細版 10 段，另有 executive view |
| 預覽 | `preview_local.py` 唯讀 live workbook 再產本機 HTML；沒有真正 UAT 隔離，也不是純 fixture preview |
| snapshot foundation | `reporting/snapshot_mvp.py`、local / Sheets adapters、gateway、auth provider、business importer；有 revision、hash、readback、single writer 規則 |
| 既有 contracts | `contracts/data_contract.v1.json`、`ga4_scope.v1.json`、`business_actual_mapping.v1.json`；不可直接加入 Ahrefs metrics 到正式 actual contract |
| 測試 | `tests/` 七個 unittest 模組；本輪使用 bundled Python + Node 執行 70 tests 通過 |
| 其他前端 | `seo_geo_html_report_2026-08-31/app/` 是另一載體，含自己的 AGENTS；不是本輪修改範圍 |
| Ahrefs 舊檔 | `seo_report_v2_2026-05-18_2026-05-24/exports/ahrefs_*_summary_2026-05-26.csv` 三個技術摘要；不是 keyword opportunity ingestion |

GSC 現有明細是 query 與 page **分開的 Top 25**，不能推出 query×URL 關聯或完整 content gap。GA4 是 hostname×channel，缺 landing-page evidence。SF 月報是 issue counts，缺可直接 join 的 URL-level rows。GEO 月報是 entity aggregates，缺 prompt×platform×run 的固定樣本關聯。

## Drive / production workbook 實際回讀

[Drive workspace](https://drive.google.com/drive/folders/1iCY6abjzfVnefpc05sQQp2Mu1gYRQWP_) 可讀。確認 `99_專案程式`、`97_Runtime`、`98_環境設定`、`90_正式報告`、控制中心及兩站資料夾；未讀取憑證內容。

| 載體 | 唯讀核對 |
| --- | --- |
| [正式月報 workbook](https://docs.google.com/spreadsheets/d/14lyC4zotKGBGg90CExf3q-hPk7awRAvUgIoEYAn1QtI/edit) | 21 tabs；timezone Asia/Taipei；讀 `_Schema!A1:B30`、`_Meta!A1:B35`、兩個人工分頁 header |
| [Framework workbook](https://docs.google.com/spreadsheets/d/1My3hsSSBwNqSRCyPNL7z-S8WsVFns5lZ2c76UE1N9RA/edit) | 13 tabs；timezone America/Los_Angeles；有 URL Registry、Brand Dictionary、GEO Prompt Registry、KPI Snapshots v2，另有舊測試 tab |
| 正式 _Meta | period 2026-08；generatedAt/businessAsOf 2026-09-08T09:24:43Z；GEO 2026-09-06T10:03:33.270Z；CrUX retrieved 2026-09-07T07:20:28Z、window 08-09～09-05 |
| Framework bounded reads | registry 各 A1:N6；KPI Snapshots v2 A1:Y5：header 在第 4 列，首筆資料列空，標題仍說 activation pending。未掃全表，不能宣稱完全無資料或已正式啟用 |

21 tabs 的精確 schemas 見 WORKBOOK_ARCHITECTURE.md。本輪未讀人工建議正文／owner 欄值；只能證明欄位存在，不能證明所有人工列已批准。

## DOCUMENTATION_DRIFT

| ID | 矛盾 | evidence 優先與處理 |
| --- | --- | --- |
| D01 | v2 README 說未部署；DESIGN 09-09 修訂說綁定版已部署 | 較新 Git 紀錄支持已部署；本輪僅確認 workbook，遠端 Apps Script 版本、ACL、HTML **未重驗** |
| D02 | dirty v1 README 稱舊網址正式；DESIGN 說舊版已封存 | 09-09 封存紀錄優先於部署當刻敘述；不要把舊凍結版 450 與新 448 並列為同版 |
| D03 | README / collector 註解稱 Workduo 不通 | 本 session projects、queries、bounded metrics 成功優先；不代表舊 stdio ingestion 已修好或全樣本已取齊 |
| D04 | data_contract 禁止 immature SQL formal ratios；builder / renderer 依先前 owner 要求顯示 | code 決定現有行為，contract 決定新層可採用的正式商業證據；保留 display exception，不把它延伸為 business score / WON |
| D05 | 文檔聲稱換月無須改程式；builder 仍有固定 period、月份欄位 | 執行碼優先；先解耦，不複製下一個月程式 |
| D06 | snapshot infrastructure 容易被誤當月報已 append-only | 月報 publisher 是覆寫投影；framework header 仍 activation pending。模組存在不等於 production 接通 |
| D07 | 週報稱品牌字典不可機讀；Framework 描述 62 筆 Approved | live registry 說明優先於「不存在」；本輪未讀完整規則、未驗版本 hash，因此尚不能直接啟用 |
| D08 | URL Registry 列成功事件和 North Star Yes；GA4 contract 未批准事件 | 正式 contract 優先於 registry 的設計標籤；不得使用 CTA 或未驗證 success event 當 conversion |
| D09 | SF 月報無歷史對照；資料庫已有 08-17 blog 等舊 crawl | list_crawls 證明歷史檔存在；未驗設定可比性，不能直接生 MoM |
| D10 | DESIGN 內仍殘留未部署／舊流程段落 | 同文件的 dated revisions + 程式 + live reads 優先，舊段落只作歷史 |

原則：沒有單一 evidence 能同時證明部署、數字與語義。live workbook 證明目前 cell/schema；code 證明本機行為；owner-approved contract 證明正式指標資格；Git dated history 證明變更歷史。無遠端回讀就保持 UNKNOWN，不「投票」消除矛盾。

## Readiness

OPPORTUNITY_INTELLIGENCE_ARCHITECTURE = READY（設計與交接可供分包，未上線）。

AHREFS_INTEGRATION_READINESS = PARTIAL（多 endpoint probe 成功；正式 scope、競品、budget、歷史語義與 ingestion 未凍結）。目前沒有使用者正式核准的 scoring/business weights；所有預設均為 proposal。

## WP2 implementation handoff（2026-09-10）

本輪以 `WP2_BASELINE_SHA=8491d7c0914791498811b868f3aafb5af3deaa84` 建立乾淨 branch `feat/ahrefs-readonly-ingestion`。新增的 adapter 只接受 scope-approved preview/uat requests，透過注入 transport 取得 Organic Keywords 與 Organic Competitors；不寫 Ahrefs、Google Sheets、Recommendations、Next Steps、Apps Script 或 scheduler。

Ahrefs live smoke：Organic Keywords 與 Organic Competitors 各以 TW、domain、`limit=1` 成功，實際各觀測 50 units；runtime inventory 沒有 dedicated Content Gap endpoint，因此 Content Gap 保持 `UNAVAILABLE`，沒有用其他 endpoint 偽造 coverage。adapter 以 client-side 4 requests/run、500 units/run、每 endpoint 5 rows、2 pages、30 秒 timeout、每次最多 1 retry 作保守上限；這些不是 owner-approved production budget。

`WP2_AHREFS_INGESTION_READINESS = PARTIAL`：Organic Keywords、Competitors、bounded normalization、manifest、failure/retry/cap guards 與 offline tests 已完成；Content Gap capability gap、scope/competitor/budget approval 與 production activation 仍未完成。

## WP1 implementation handoff

`origin/main` 已包含 architecture merge commit `0b63c66f0c14331fabb0dd2d72e820147e8cd758`。WP1 在獨立 branch `feat/opportunity-contract-validator`、以該 SHA 為 baseline 完成；validator 僅接受 offline payload 與 synthetic immutable context，沒有 live source、production writer 或 scheduler。

`WP1_VALIDATOR_READINESS = READY`。WP2 已完成 bounded read-only adapter，但 Content Gap capability、scope/competitor/budget approval 與 production activation 仍未完成；下一個唯一工作依 ROADMAP 為 WP3 canonical entity registry。
## WP3 implementation handoff（2026-09-10）

WP3 以 WP3_BASELINE_SHA=da9f1d6aa6384eba9eb9c463605c8d1aa3875ede 建立
feat/opportunity-canonical-registry。新增離線 canonical entity registry，
只保存 identity、typed stable IDs、explicit relations、mapping version、review
state 與 deterministic semantic hash；不保存 Ahrefs/GSC/GA4/Workduo metrics。

目前支援 TOPIC、KEYWORD、QUERY、PROMPT、URL、COMPETITOR、BUSINESS_THEME。
Keyword、Query、Prompt 保留不同 source grain；URL 只做 deterministic
sanitization，不做 redirect/HTTP fetch；競品不依文字相似度自動合併。Relation
預設為 CANDIDATE，RULE_BASED 不得自行變成 APPROVED，approved mapping
需要 opaque reviewer ID。

Registry schema 為 contracts/canonical_registry.v1.proposal.json，維持
DRAFT_NOT_APPROVED 與 x-production-activation=false。synthetic fixture
位於 tests/fixtures/opportunity_registry/synthetic_registry.json。已知 URL
HTTP/HTTPS、www/非 www、trailing slash 等 equivalence policy gaps 會明確保留，
不以猜測合併。

WP3_CANONICAL_REGISTRY_READINESS = READY。本包沒有 live API、production
writer、Brand Dictionary mutation、scoring、cross-source join 或 WP4 implementation。

## WP4 implementation handoff（2026-09-10）

本輪以 `WP4_BASELINE_SHA=28374fd2302685ce5bf060dc9292df3a679cf1e0` 建立乾淨
branch `feat/opportunity-immutable-store`，原 dirty worktree 保留且未觸碰。新增
離線 append-only Evidence Store、Candidate Store 與 local run manifest；每個
JSONL line 是 canonical immutable artifact，沒有 update/overwrite API。

Evidence 與 Candidate 是分離 record。Evidence revision 必須連續並以
`supersedes_evidence_id`/`supersedes_revision` 綁定前一版；candidate revision
同樣 append，並以 `evidence_id + revision + content_hash` pin 精確 evidence。
因此 evidence rev2 不會讓已寫入的 candidate rev1 漂移到 latest。相同 logical
revision 與相同 hash 是 deterministic idempotency；hash collision、gap、錯誤
supersedes、tamper 與 unresolved entity 均 fail closed。

Store 只接受 offline local inputs，使用 WP3 canonical registry 驗證 entity/topic
refs；保留 `READY/PARTIAL/STALE/FAILED/NOT_AVAILABLE`、null missing 與 0 的差異，
並保留 Ahrefs `THIRD_PARTY_ESTIMATE` source semantics。proposal schema
`contracts/opportunity_store.v1.proposal.json` 仍是 `DRAFT_NOT_APPROVED`，沒有
production activation。

`WP4_IMMUTABLE_STORE_READINESS = READY`。下一個唯一工作是 WP5 SEO engine v1；
本輪沒有 scoring、recommendation、live ingestion、UI 或 production mutation。

## WP5 implementation handoff（2026-09-10）

本輪在 `feat/seo-opportunity-engine-v1`、基於
`WP5_BASELINE_SHA=202c41e88a54e0805158f41523acbb430934078b` 的 clean worktree
完成離線 SEO Opportunity Engine v1。輸入是 immutable、normalized synthetic
Ahrefs/GSC/SF evidence 與 WP3 canonical registry；engine 不呼叫 live source，也不
寫入 production。

支援 `QUICK_WIN`、`CTR_OPPORTUNITY`、`CONTENT_DECAY`、`TECHNICAL_UNLOCK` 與
`DO_NOTHING` 的 deterministic rule trace；`CONTENT_GAP` 保留為
`POLICY_GAP`，因 OI-014 尚未批准 derived competitive gap。Score 維持
`SEO_EXISTING`/`SEO_NEW` 的 fixed profile、missing 不轉零；Confidence 依獨立
source families、freshness、mapping 與 conflict 獨立計算。Engine 只產生
`DISCOVERED`/`CANDIDATE`，永不自動 `APPROVED`。

候選 proposal 先通過 WP1 validator，再可選擇 append 到 WP4 Candidate Store；
store record 固定 `evidence_id + revision + content_hash`，candidate revision
變更以 supersedes chain 追加。preview 只輸出 deterministic JSON/Markdown，沒有
UI、Recommendations、Next Steps、scheduler 或 production writer。

`WP5_SEO_ENGINE_READINESS = READY`。下一個唯一工作依 ROADMAP 是 WP6 GA4 quality
diagnostics；本輪已停止，未開始 WP6。

## WP6 implementation handoff（2026-09-10）

本輪以 `WP6_BASELINE_SHA=cb01dc032e9c89313e6997b3d65327c7f777e9f1` 建立 clean
worktree 與 branch `feat/opportunity-ga4-quality-diagnostics`。新增的 GA4 layer
只接受離線、已 scope 的 synthetic rows，source role 固定為
`FIRST_PARTY_BEHAVIOR_DIAGNOSTIC`；沒有 live GA4 query、credential、production
writer 或 scheduler。

GA4 evidence 以 property、exact hostname、channel、period、timezone、coverage、
sampling/thresholding、freshness 與 collection state 正規化後 append 到 WP4
EvidenceStore。PAGE_LEVEL rows 必須以 WP3 registry 的 exact normalized URL / `url_id`
join；沒有 fuzzy title、redirect、scheme 或 trailing-slash equivalence。SITE_WIDE_CONTEXT
只保留為 contextual conflict，不推論單一頁面品質。

診斷 projection 是獨立的 `GA4_DIAGNOSTIC` artifact，固定保存 candidate revision、
GA4 evidence refs、candidate evidence refs、revision、supersedes 與 content hash。
Score 與 Confidence 不合併；WP5 score 原值保留但不被 GA4 改寫。CTA 只輸出
`CTA_SIGNAL_PRESENT/WEAK`，conversion boundary 固定 `DIAGNOSTIC_ONLY`；不產 Lead、SQL、
Revenue、CVR 或 APPROVED。AI Assistant 與外部 business population 的 attribution
保留 `AI_ASSISTANT_ATTRIBUTION_UNRESOLVED`，不做相除。

`contracts/ga4_quality_diagnostics.v1.proposal.json` 仍是
`DRAFT_NOT_APPROVED` 且 `x-production-activation=false`。synthetic scenarios A–L
涵蓋 healthy、traffic/engagement trends、missing、stale、wrong channel、sitewide、
unresolved URL、CTA、GSC conflict、deterministic replay 與歷史 revision。WP6 完成後
下一個唯一工作依 ROADMAP 是 WP7 SERP validation；本輪未開始 WP7。

## WP7 implementation handoff（2026-09-10）

本輪以 `WP7_BASELINE_SHA=16c6c74248a0d96f8357b21d9eca45e3668d16eb` 建立 clean worktree `/private/tmp/seo-geo-wp7-serp` 與 branch `feat/opportunity-serp-validation`。原 dirty worktree 未觸碰；沒有修改 `main`，也沒有呼叫 live Google Search、Ahrefs、GSC、GA4、Screaming Frog、Workduo 或 CrUX。

新增 `reporting/sources/serp.py` 作為 offline-only、injected transport 的 bounded shortlist collection boundary（query/candidate/result cap 30、timeout 30 秒、最多一次 transient retry）。它要求 WP3 canonical QUERY/KEYWORD 的 exact text、locale、country、device、scope，保留 provider provenance、observed timestamp、organic rows、page-type result kind、owned/approved competitor mapping 與 feature state。`NOT_AVAILABLE` 與未 capture 不轉成 false；unknown domain 只保留 `UNMAPPED_DOMAIN`。

`reporting/opportunity/serp_validation.py` 只解讀 pinned `SERP` evidence，不做 discovery、bulk crawl 或 LLM query invention。它輸出 `SERP_VALIDATED`、`SERP_CONFLICT`、`SERP_NOT_CHECKED` 三態，保留 query/scope、intent、page-type distribution、SHOPLINE/competitor presence、AIO/PAA feature state、structured conflicts、freshness、rule trace、`evidence_id + revision + content_hash` 與 candidate refs。SERP status 與 WP5 score/confidence 分離；不會把 validated 候選自動改成 APPROVED，也不會刪除候選。兩份 SERP proposal schema 都是 `DRAFT_NOT_APPROVED`、`x-production-activation=false`。

Synthetic scenarios A–N 涵蓋 quick win、page-type mismatch、feature crowding、mixed intent、owned strong、competitor dominance、missing query、unmapped domain、NOT_AVAILABLE、stale、determinism、revision history、locale mismatch 與 insufficient results。下一個唯一工作依 ROADMAP 是 **WP8 — GEO fixed sample layer**；本輪不開始 WP8。

## WP8 implementation handoff（2026-09-10）

本輪以 `WP8_BASELINE_SHA=da1f5e53a446bbe903d49291de9c27d8eb0d44ca` 建立 clean
worktree `/private/tmp/seo-geo-wp8-geo` 與 branch `feat/opportunity-geo-fixed-sample`。
原 dirty worktree 未觸碰；沒有修改 main，也沒有呼叫 Workduo、Google Search、GA4、GSC、Ahrefs、Screaming Frog、CrUX 或任何 production writer。

WP8 新增 offline `reporting/sources/workduo.py`、`reporting/opportunity/rules_geo.py`、`geo_diagnostics.py`、`geo_preview.py` 與三份 proposal schemas。Workduo source role 固定為 `MONITORED_FIXED_SAMPLE`，Evidence source class 為 `MONITORED_GEO_SAMPLE`；固定 sample 保留 version/revision、prompt population、market/locale/platform/model scope、有效日期與 sample hash。Prompt、topic、URL、competitor 都只接受 WP3 exact canonical mapping；unknown domain 只保留在 `unknown_domains`，不建立 entity。

Mention 與 citation 分離；`NOT_AVAILABLE`、missing、STALE、FAILED 不補零。只有相同 sample version、population、scope、provider methodology 才可比較，revision drift 產生 `COMPARABILITY_GAP`。GEO 只 enrich existing candidate，固定保留 candidate/WP5 score、confidence、review state；不建立新 candidate、不自動 APPROVED、不改 WP5 score。SERP/GA4 只作分離 context，衝突保留 `CROSS_CHANNEL_CONFLICT`/`MIXED_SIGNAL`。

Synthetic fixture `tests/fixtures/opportunity_geo/scenarios.json` 覆蓋 A–P；WP8 targeted **21 tests PASS**，full regression **211 tests PASS**。proposal schema、fixture JSON、AST、explicit date/date-time、`git diff --check`、scoped security/PII、production boundary 均已驗證；沒有 production mutation。`WP8_GEO_FIXED_SAMPLE_READINESS = READY`。下一個唯一工作是 **WP9 — Opportunity preview / UAT report**；本輪未開始 WP9、未 push。

## WP9 implementation handoff（2026-09-11）

WP9 以 `WP9_BASELINE_SHA=4188fe631c1f6368fe64cf964a97d518c1a5382d` 建立 clean
worktree `/private/tmp/seo-geo-wp9-preview` 與 branch `feat/opportunity-preview-uat`。
新增純讀取 `reporting/opportunity/report_projection.py`、
`contracts/opportunity_preview.v1.proposal.json`、A–P synthetic UAT fixture 與
`tests/test_opportunity_preview.py`。Projection 只接收 WP4–WP8 已 pin 的 candidate
revision/evidence refs，不重新計算 score 或 confidence，不建立 recommendation、Next
Steps、approval 或 production row；UAT preview candidate IDs 與 source candidate IDs
分離。

Preview 提供 Quick Wins、Content Gaps、GEO Gaps、Content Decay / Technical Unlock 四組，
首屏最多 20 筆，保留 score、獨立 confidence、evidence dates、estimate flag、missing、
conflict、GA4/SERP/GEO diagnostics 與 immutable refs。SERP_NOT_CHECKED、NOT_AVAILABLE、
STALE、POLICY_GAP、CAPABILITY_GAP 仍是可見狀態；GA4 CTA 維持
`DIAGNOSTIC_ONLY`，GEO 不作 whole-market claim。JSON、Markdown、responsive local HTML
renderer 均不寫檔。

WP9 targeted **23 tests PASS**；full regression **234 tests PASS**。proposal schema、A–P
fixture、AST、explicit date/date-time、`git diff --check`、scoped security/PII/live-call
與 production-boundary checks PASS；production mutation=0。`WP9_OPPORTUNITY_PREVIEW_READINESS = READY`。
本輪只允許建立 local commit，未 push、未建立 PR、未 merge；下一個唯一工作是 WP10，不能在本輪開始。

## WP10 implementation handoff（2026-09-11）

`WP10_BASELINE_SHA=356285f80a1a4bd4a98425a0bc561e7b65141455`。本輪在 clean
worktree `/private/tmp/seo-geo-wp10-review`、branch
`feat/opportunity-human-review-bridge` 完成 offline human review / recommendation
bridge。原 dirty worktree 未觸碰；沒有 live source、Google Sheets、Apps Script、正式
Recommendations、Next Steps 或 scheduler mutation。

`reporting/opportunity/review.py` 建立 first-class、append-only HUMAN_REVIEW records：
authenticated HUMAN actor、decision taxonomy、candidate revision/hash、evidence and
diagnostic pins、preview hash、policy version、notes provenance、decision time 與
semantic content hash 都固定保存。SYSTEM/AI/LLM/AUTO/RULE_ENGINE actor、缺 reviewer、
錯誤 hash、naive datetime 與 invalid decision fail closed。

`review_bridge.py` 只允許 exact human `APPROVE` 形成 proposal-only UAT/PREVIEW bridge；
它保留 Candidate Action、Score、Confidence、GA4/SERP/GEO refs、conflicts、review
identity 與 approval meaning `RECOMMENDATION_WORKFLOW_ENTRY_ONLY`。STALE、missing、
SERP_NOT_CHECKED、POLICY_GAP、CAPABILITY_GAP、candidate/review revision drift、
superseded review 與未 adjudicate 的 conflict 都不會建立 bridge。Review/bridge 均
append-only，Next Steps 與 production mutation 固定為 false。

新增 `contracts/human_review.v1.proposal.json` 與
`contracts/recommendation_bridge.v1.proposal.json`，兩者均維持
`DRAFT_NOT_APPROVED`、`x-production-activation=false`。A–P fixture 與 26 個 WP10
tests 全部 synthetic；`WP10_HUMAN_REVIEW_BRIDGE_READINESS = READY`。下一個唯一任務依
ROADMAP 是 **WP11 — Outcome tracking**；本輪未開始或建立 WP11。

## WP11 implementation handoff（2026-09-14）

本輪以 `WP11_BASELINE_SHA=83745d36ff59b9dfa45313c43c125f3a014f8b94` 建立 clean
worktree `/private/tmp/seo-geo-wp11-outcomes` 與 branch
`feat/opportunity-outcome-tracking`。原 dirty worktree 未觸碰；本輪沒有 push、PR、merge、
WP12 branch、live source query 或 production writer。

新增 `reporting/opportunity/outcomes.py` 與 `outcome_preview.py`。WP11 只接受已批准的
exact Candidate / human Review / UAT Bridge revision，以及明確的 IMPLEMENTED
implementation event anchor。APPROVE 不代表 IMPLEMENTED；DO_NOTHING 與 MONITOR 只會
留在 `NOT_ELIGIBLE` / `OBSERVATION_ONLY`，不產生假執行結果。

Outcome record 以 Asia/Taipei 的完成日計算 baseline 與 30/60/90D 各 28 個完整日，保留
source、scope、population、methodology、sample version、missing/FAILED/STALE/
NOT_AVAILABLE、exact evidence pins 與中立限制文字。GSC、GA4、GEO、SERP、SF/CrUX 的
grain 分開比較；GA4 僅是 behavior diagnostic，CTA/Lead/SQL/Revenue 不會被當成正式
conversion，SERP snapshot、不同 GEO fixed sample、site-wide/page-level 或 business
attribution contract 缺漏會保留 `NOT_COMPARABLE` / policy gap。

`WON` 需要 primary target、至少一個獨立 support signal、guardrails 通過且資料可比；
混合訊號保留為 `PARTIAL_WIN`，資料不足為 `INSUFFICIENT_DATA`，不作 causal / ROI claim。
Outcome 與 implementation event 都以 local append-only JSONL store 保存，revision 必須
連續、supersedes 前一版、hash 可重算、歷史 observation 不被新 revision 覆寫。兩份 proposal
schema 維持 `DRAFT_NOT_APPROVED` 與 `x-production-activation=false`。

`WP11_OUTCOME_TRACKING_READINESS = READY`。下一個唯一工作依 ROADMAP 是 **WP12 — Production
hardening（最後gate）**；本輪未開始或建立 WP12。

## WP12 production hardening handoff（2026-09-14）

`WP12_BASELINE_SHA=6415c9e086f6afe419076461fa486d2c457f89a6`。在 clean branch
`feat/opportunity-production-hardening` 完成 offline production hardening gates；原
dirty worktree 未觸碰。新增 `reporting/opportunity/production_hardening.py`、
`contracts/production_activation.v1.proposal.json`、
`contracts/production_release_manifest.v1.proposal.json`、A–T synthetic hardening
fixture 與 `tests/test_production_hardening.py`。

Hardening layer 只產生 dry-run planned/blocked operations、deterministic idempotency
keys、release manifest、rollback plan 與 structured observability events；writer、target、
environment、contract、authorization、scheduler、source、secret、PII、hash、revision、
stale evidence、audit 與 partial-failure gates 全部 fail closed。Recommendations、
Next Steps、production workbook、Apps Script、runtime production store 與 scheduler 都
維持 untouched；production mutation 與 actual write count 都是 0。

兩份新增 proposal contract 維持 `DRAFT_NOT_APPROVED` 與
`x-production-activation=false`。WP12 targeted **30 tests PASS**，fresh full regression
**311 tests PASS**；schema、synthetic fixture、AST、JSON、explicit date/date-time、
`git diff --check`、security/PII/live-call/production-boundary checks 均 PASS。

`WP12_PRODUCTION_HARDENING_READINESS = READY`；`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`。
WP12 不啟用 production、不建立 scheduler、不寫 production targets，亦未建立 PR、push 或
merge。ROADMAP 已完成最後 hardening gate；後續 production activation 仍需獨立明確授權。
## WP12 repair handoff（2026-09-15）
原始 WP12 handoff 的 consistency probe 曾因 runtime enforcement 不足暫列
`BLOCKED_HANDOFF_INCONSISTENCY`。follow-up repair 保留原始 commit 不變，補上 required gate
完整性、activation kill switch/terminal state、artifact revision/hash pins、mandatory
audit、cross-run idempotency ledger、recursive secret/PII rejection 與 redaction、manifest
lineage/structured test summary、structured rollback、partial failure receipts，以及
production/dry-run state separation。repair 只在 clean worktree 進行，未觸碰原 dirty worktree。
本節的最終 targeted/full regression 數字以 repair 後 fresh discovery 記錄為準；在驗證完成前
不得把原始 30/311 PASS 記錄解讀為 repair 已通過。readiness key 維持
`WP12_PRODUCTION_HARDENING_READINESS`，且 `PRODUCTION_ACTIVATION=NOT_AUTHORIZED`。
Repair 後 WP12 targeted **40/40**、fresh full regression **321/321 PASS**；所有 production
mutation/write count 仍為 `0`，沒有 push、PR、merge 或 production activation。

## Production Phase 1 Recommendation Canary Writer（2026-09-16）

以 `9f984b26e177cec109e8b3b5ac2053d6b0e62b43` 為 baseline，在隔離 branch
`feat/opportunity-recommendation-canary-writer` 完成 offline/UAT-only Recommendation
Canary Writer。它只接受一筆 exact human-approved Recommendation Bridge，保留 Candidate、
Review、Bridge 的 revision/hash pins，產生一個 WriteIntent，寫入注入的 synthetic transport，
強制 readback，並保存 append-only audit receipt。UAT target binding 固定為
`Opportunity_Recommendations`；實際 workbook ID 與 OAuth principal 僅允許 runtime refs，
不寫入 repository。

Writer 的 allowlist 只包含 recommendation、candidate/review/bridge pins、approved text、
action/topic/URL refs、read-only Score/Confidence、evidence/conflict/governance refs、
release/operation/semantic hash 與 created_at。人工備註、Next Steps、既有 production report
data、未批准欄位與其他 target data 均受保護。多於一個 operation、kill switch、invalid/
stale/missing evidence、untrusted reviewer、superseded review、unresolved conflict、protected
mutation、readback mismatch、audit failure 與 unknown target 都 fail closed。

Uncertain transport 絕不自動 retry：exact readback 才能 `RECONCILED_SUCCESS`，空結果只回傳
`SAFE_TO_RETRY_REQUIRES_HUMAN_AUTHORIZATION`，衝突則為
`RECONCILIATION_CONFLICT`。兩份 canary proposal contract 維持
`DRAFT_NOT_APPROVED` 與 `x-production-activation=false`。WP Phase 1 targeted **18/18**、
WP12→WP1 targeted **214/214**、fresh full regression **339/339 PASS**；全部資料與 transport
均 synthetic/offline，production mutation=0，沒有 OAuth consent、Google write、live source、
Apps Script、scheduler、push、PR 或 merge。

`PHASE1_CANARY_WRITER_READINESS = READY` 僅代表離線/UAT implementation ready；
`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`。Phase 1 logical design 已確認為 independent
Google workbook、`Opportunity_Recommendations`、authorized-user OAuth、project
owner/user 作為 operational、rollback 與 kill-switch authority、最多一筆 operation、
mandatory readback、unknown result stop/readback/reconcile/no automatic retry、以及
one-business-day observation period。logical audit location 也已確認為
`95_Production Canary/Opportunity Intelligence/audit/operation_<operation_id>.json`。

仍待下一階段建立或驗證的是 exact OAuth principal、exact workbook ID、Drive folder/binding、
workbook ACL、trusted human-review identity provider/role mapping、actual persistent audit
binding/retention，以及正式 production contracts。下一個工作是 **Phase 1 Canary Environment
Binding**；本輪不建立 workbook、不執行 production activation。


## Phase 1 Canary Environment Binding（2026-09-16）

以 `17f2669de0e49f33fb51d3a545b2af1698df3e29` 為 fresh `origin/main` baseline，在隔離
branch `feat/opportunity-canary-environment-binding` 完成受控 environment binding。
Drive root `SEO／GEO Reporting` 已以 exact title 與可列 children capability 消歧；
`95_Production Canary/Opportunity Intelligence/`、獨立 workbook
`Opportunity Intelligence｜Production Canary`、`Opportunity_Recommendations` tab 與
`audit/` folder 均已建立並完成 metadata/readback 驗證。Environment-specific resource
IDs 僅存在 external binding metadata，不進 Git。

目前驗證結果：

- `principal://authorized-user-oauth/runtime`：authorized-user OAuth identity 與有效 Drive/Sheets write path verified；未導入 service account，未輸出 credential。
- Workbook 與 audit folder：current principal 具 owner/writer-capable access；ACL 僅讀取，未做 share/invite/role/ownership mutation。
- `Opportunity_Recommendations!A1:X1`：canonical 23 欄 header verified；data rows = `0`。
- Structural sheet writes = `1`（canonical header row）；Recommendation records = `0`。
- Audit binding = `VERIFIED`；真實 `operation_<operation_id>.json` receipt = `0`。
- Trusted human-review identity/provider 仍為 `NOT_VERIFIED`；OAuth identity 不等同 human-review identity。

`CANARY_ENVIRONMENT_BINDING = READY` 僅表示資源、ACL、schema、zero-row readback 與
external binding metadata 完成；`PRODUCTION_ACTIVATION = NOT_AUTHORIZED` 仍維持。
下一階段只能進行 **Phase 1 Zero-Write Production-Config Dry Run**，不得 live write、
scheduler、batch expansion 或 production activation。


## Phase 1 Canary Environment Binding finalization（2026-09-16）

Owner decision 已確認 Canary workbook 可保留 `shopline.com` domain-wide `reader` access；
目前 workbook 與 audit path 均符合，未做 ACL mutation。非機密 binding 已從 task-local
metadata 移至既有 external environment config pattern：`98_環境設定/opportunity-canary/`。

`DURABLE_BINDING = VERIFIED`、`ACL_POLICY = APPROVED`（`shopline.com / reader`）、
`ZERO_WRITE_DRY_RUN_READINESS = READY`。Durable binding readback 與 semantic hash、schema hash、
principal ref、audit ref、`recommendation_row_count=0` 全部一致；不含 token、client secret、
Authorization header、cookie、private key 或 raw credential JSON。

`TRUSTED_REVIEW_IDENTITY = NOT_VERIFIED` 仍阻止第一筆 live Recommendation；
`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`。下一步仍是 **Phase 1 Zero-Write
Production-Config Dry Run**，本輪不開始執行。


## Historical state before Trusted Review Identity completion — Phase 1 Zero-Write Production-Config Dry Run（2026-09-16）

本輪只從 durable external binding `98_環境設定/opportunity-canary/environment-binding.json`
載入設定；未使用 task-local `/private/tmp` 作為正式來源。Binding semantic/schema/allowlist
hashes、principal ref、workbook/tab、audit ref、ACL policy 與 `verified_at` 均通過。

真實 Canary workbook readback：canonical 23 欄 header exact、pre/post
`Opportunity_Recommendations` data rows 均為 `0`；audit folder items 仍為 `0`。Dry-run
只產生一筆不可執行的 `DryRunWritePlan`，`transport_mode=ZERO_WRITE`，未建立正式
`WriteIntent`、未寫入 idempotency ledger、未建立 audit receipt。

`ZERO_WRITE_CONFIG_DRY_RUN = PASS`。在 Trusted Review Identity Binding 完成前，
live write eligibility 明確為 `BLOCKED`，當時原因為
`TRUSTED_REVIEW_IDENTITY_NOT_VERIFIED`、`PRODUCTION_CONTRACTS_NOT_APPROVED`、
`PRODUCTION_ACTIVATION_NOT_AUTHORIZED`。其中
`TRUSTED_REVIEW_IDENTITY_NOT_VERIFIED` 已於後續完成的 Trusted Review Identity Binding
解決；**Phase 1 Trusted Review Identity Binding** 是當時的下一個任務，現已完成。本輪不開始
live write、scheduler 或 production activation。

## Phase 1 Trusted Review Identity Binding（2026-09-17）

Google Workspace provider readback 已經過官方 OIDC verifier 的 signature、issuer、audience、
expiry、stable subject、`hd=shopline.com` 與 `email_verified` 驗證。外部 non-secret binding
位於 `98_環境設定/opportunity-canary/trusted-review-identity.json`，只保存 pseudonymous
subject ref、role `RECOMMENDATION_APPROVER`、scope `PHASE1_CANARY`、revision、waiver 與
semantic hash；不保存 raw subject、email、token 或 credential material，且不進 Git。

Runtime gate 必須同時比對 typed provider evidence、exact subject/domain/role/scope、binding
revision/hash 與 Phase 1 same-person waiver。`authenticated=true`、caller email、role、domain
或 subject ref 字串均不能單獨通過。writer principal 與 reviewer subject ref 是不同概念；本輪
waiver 只容許 `PHASE1_CANARY`、一筆 operation，且禁止 production inheritance 與自動擴張。

`TRUSTED_REVIEW_IDENTITY_BINDING = READY`、`TRUSTED_REVIEW_EXTERNAL_BINDING = VERIFIED`、
`TRUSTED_IDENTITY_GATE = PASS`。Recommendation records、real review events、audit receipts 與
business-data mutation 都是 `0`。`LIVE_WRITE_READINESS = BLOCKED`，剩餘 blockers 為
`PRODUCTION_CONTRACTS_NOT_APPROVED` 與 `PRODUCTION_ACTIVATION_NOT_AUTHORIZED`；
`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`。

## Phase 1 Contract Approval Evidence Foundation（2026-09-17）

Foundation commit 的實際 changed paths 為 14 個；沒有新增 dummy path，scope 只包含本 foundation
code、synthetic tests、四份 proposal schemas 與必要 handoff docs。

本地 foundation 定義 exact contract instance pinning（contract id/version/revision/semantic hash）、
provider-verified pseudonymous approver evidence、獨立的 `CONTRACT_SEMANTICS_APPROVER` role、
Phase 1 canary waiver、七日未使用 approval expiry、append-only revocation/supersession、rollback
acknowledgement 與 deterministic receipt hashes。Approval verifier 只產生
`CONTRACT_APPROVAL_GATE = PASS/BLOCKED`，不會把 contract semantics approval 轉成 production
activation authorization。

七份 Phase 1 dependency contracts 與 foundation proposal contracts 都維持
`DRAFT_NOT_APPROVED`、`x-production-activation=false`；本地 synthetic cases 與既有 regression
供驗證使用，沒有建立正式 approval receipt、Recommendation、audit receipt 或任何 production
mutation。`CONTRACT_APPROVAL_EVIDENCE_FOUNDATION = READY`、
`PRODUCTION_CONTRACTS_APPROVED = FALSE`、`LIVE_WRITE_READINESS = BLOCKED`、
`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`。下一步只做 Contract Approval Package Review。

## Phase 1 Contract Canonical Instance Foundation（2026-09-17）

Canonical contract instances are now materialized offline from an authoritative
seven-contract registry. The registry keeps proposal mapping, ruleset reference,
runtime consumer and materializer key explicit; unknown or ambiguous mappings
fail closed. The trusted identity logical id intentionally maps to the existing
`trusted_review_identity_binding.v1` proposal.

Canonical dimensions are independent: `approval_scope=PHASE1_CANARY`,
`execution_context=UAT`, `transport_mode=ZERO_WRITE`,
`target_environment=PRODUCTION_CANARY`, `production_activation=NOT_AUTHORIZED`,
`production_inheritance=false` and `automatic_scope_expansion=false`.
`PHASE1_CANARY_ONLY` is historical and requires the explicit migration helper;
it is never silently reinterpreted.

`CONTRACT_CANONICAL_INSTANCE_FOUNDATION = READY`、`SEMANTIC_READINESS = READY`、
`CANONICAL_INSTANCE_READINESS = READY`。This foundation contains rules instances,
not approval receipts; all seven proposal contracts remain `DRAFT_NOT_APPROVED` and
`x-production-activation=false`.

`APPROVAL_EXECUTION_READINESS = BLOCKED_PERSISTENT_STORE`、
`PRIOR_APPROVAL_DECISION_STATUS = RECONFIRMATION_REQUIRED`、
`FORMAL_APPROVAL_RECEIPTS = 0`、`CONTRACTS_APPROVED = 0`、
`PRODUCTION_ACTIVATION = NOT_AUTHORIZED`、`LIVE_WRITE_READINESS = BLOCKED`。
The next single task is **Phase 1 Persistent Approval Store**. No approval store,
approval receipt, Google/Drive/Sheets write, scheduler or live source call was
created in this foundation.

## Contract Canonical Instance Test Runner Consistency（2026-09-17）

The two canonical-foundation test modules are now pure `unittest` tests. The
repository has one reproducible authoritative runner:
`97_Runtime/gsc-mcp/bin/python3.12 -m unittest discover -s tests`.
Fresh discovery completed **419/419 PASS** with zero failures and zero errors;
pytest is not a repository dependency. Contract Approval and Canonical targeted
suites completed **52/52 PASS**. The canonical fixture still matches fresh
materialization **7/7** exactly, and production mutation remains `0`.

`TEST_RUNNER_CONSISTENCY = PASS` and `AUTHORITATIVE_TEST_RUNNER = UNITTEST`.
Approval execution remains `BLOCKED_PERSISTENT_STORE`; the next single task is
still **Phase 1 Persistent Approval Store**.
