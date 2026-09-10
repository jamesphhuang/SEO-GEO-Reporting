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
