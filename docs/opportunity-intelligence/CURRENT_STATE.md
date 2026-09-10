# PROJECT GROUND TRUTH

盤點日：2026-09-10，Asia/Taipei。本輪是架構設計與唯讀 capability probe；文件中的提案不代表功能已上線。先讀本檔，再讀 ARCHITECTURE、ROADMAP、NEXT_TASK。

## Git baseline

| 項目 | 本輪實測 |
| --- | --- |
| 工作目錄 | `/Users/pohsunhuang/Library/CloudStorage/GoogleDrive-james.ph.huang@shopline.com/我的雲端硬碟/SEO／GEO Reporting/99_專案程式` |
| integration branch / architecture foundation | `docs/opportunity-intelligence-foundation` / `9376711` (`docs(opportunity): design opportunity intelligence layer`) |
| fetch 後 origin/main | `4e30cec2a7cb446c0defa06b315c0b295a01b9af`，PR #6 merge |
| merge-base | `4e30cec2a7cb446c0defa06b315c0b295a01b9af`；architecture branch 僅多一個 foundation commit |
| 本機 main | `dc4374e`，落後遠端；不可誤當最新 baseline |
| worktree | 原 dirty worktree 保留；乾淨 integration worktree 在 `/private/tmp/seo-geo-opportunity-foundation`；未刪除、stash 或 reset 原工作樹 |
| fetch / integration | fetch 初次受 sandbox 限制，取得執行權限後成功；foundation commit 已建立，remote branch 狀態由最後驗證回報 |

其他本機 feature branches：`feat/two-tier-seo-geo-report`、`chore/untrack-appsscript-bundles`、`chore/untrack-preview-artifacts`、`fix/chart-label-clipping`、`fix/impressions-chart-scale`。名稱不證明有人仍在開發；現有 tips 均位於 main 已合併的歷史，不刪分支。

開始時 dirty state 全數分類 **UNRELATED（本輪範圍外，保留）**：

| 路徑 | 分類依据 |
| --- | --- |
| `outputs/monthly_report_2026_08/README.md` | 既有 v1 部署補記；與較新封存紀錄矛盾，保留原檔 |
| `outputs/monthly_report_2026_08_v2/report_data.json` | SQL 三欄由 null 改為數值，與 HEAD `business_sql()` 明示的 09-09 顯示例外吻合 |
| `outputs/business_metric_source_resolution_2026-09-06/` | 先前 aggregate 業務來源對帳產物 |
| `outputs/weekly_report_2026_09_01_07/` | 先前 9 月第一週報表、取數與渲染產物 |

沒有 UNKNOWN 才開始建立新文件。未改以上檔案；本輪不 commit、不 push。後續若出現新的未知變更，停止 mutation。

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
