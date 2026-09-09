# 2026 年 8 月 SEO／GEO 月報（試算表驅動版）

報表資料存在活頁簿分頁，網頁由綁定的 Apps Script 即時讀取後產生。換月只要重跑發佈流程更新分頁，網頁自動跟著變，不需要改程式。

- 活頁簿：<https://docs.google.com/spreadsheets/d/14lyC4zotKGBGg90CExf3q-hPk7awRAvUgIoEYAn1QtI/edit>
- 本機預覽：`preview.html`（詳細版）與 `preview_exec.html`（總覽版），用真實活頁簿資料渲染，與 Apps Script 走同一份模板。
  兩者**不進版控**——每次執行都會重寫，且整份 payload 在同一行，diff 沒有審閱價值。需要時用步驟 6 重建。

## 資料流

```
MCP（stdio）＋ CrUX API ──► raw/*.json ──► evidence.json ──► report_data.json ──► 活頁簿分頁 ──► Apps Script doGet() ──► HTML
```

| 步驟 | 指令 | 說明 |
| --- | --- | --- |
| 1 | `python3 mcp_client.py raw/gsc_pull.json raw/gsc_data.json` | 以 GSC MCP 的 venv 直譯器執行 |
| 2 | `python3 mcp_client.py raw/ga4_pull.json raw/ga4_data.json` | 以 GA4 MCP 的 venv 直譯器執行 |
| 2b | `python3 pull_cwv.py` | 取 CrUX Core Web Vitals（當期 + 前 25 期）；需 `CRUX_API_KEY` |
| 3 | `python3 collect_evidence.py raw` | 合併 MCP 回應與 CrUX，並依合約讀取業務實績 |
| 4 | `python3 build_report_data.py` | 換算月對月指標，輸出 `report_data.json` |
| 4b | Screaming Frog：`export_crawl` 帶 `save_report=Crawl Overview`，把產生的 `crawl_overview.csv` 複製到 `raw/screaming_frog/` | 匯出檔存在 `~/.cache/sf-mcp/exports/`，**60 分鐘後自動刪除**，要先複製留存 |
| 5 | `python3 push_to_sheet.py [spreadsheetId]` | 寫入活頁簿分頁與 `_Schema` |
| 6 | `python3 preview_local.py [spreadsheetId]` | 本機渲染 `preview.html`（詳細版）驗證 |
| 6b | `python3 preview_local.py --exec [spreadsheetId]` | 本機渲染 `preview_exec.html`（總覽版），對應 `?view=exec` |

步驟 1、2 要用對應 venv 的直譯器，例如：

```bash
"$RUNTIME/gsc-mcp/bin/python3.12" mcp_client.py raw/gsc_pull.json raw/gsc_data.json
```

其中 `RUNTIME` 為 `97_Runtime`。GSC 需要 `GSC_CONFIG_DIR`、`GSC_OAUTH_CLIENT_SECRETS_FILE`；GA4 需要 `GOOGLE_APPLICATION_CREDENTIALS`。這些已寫在 `raw/*_pull.json` 的 `env` 內。

## 活頁簿分頁

`_Schema` 記錄每個分頁的欄位順序，Apps Script 只讀它來決定怎麼解析，因此加欄或調整欄序都不必改程式。以底線開頭的分頁是控制用分頁，不會被當成報表段落。

| 分頁 | 內容 |
| --- | --- |
| `_Meta` | 標題、期間、資料擷取時間、技術稽核狀態 |
| `_Schema` | 分頁 → 欄位順序 |
| `Business` | Non-Paid Leads 目標與實績 |
| `GSC_Monthly` / `GSC_Delta` | 兩站逐月彙總與月對月變化 |
| `GSC_Pages` / `GSC_Queries` | 8 月各站 Top 25 |
| `GA4_Channels` | property × hostname × 渠道 |
| `GEO_Workduo` | 品牌每日平均可見度與 SOV |
| `Sitemaps` | GSC sitemap 警告與錯誤 |
| `CWV` | Core Web Vitals 與輔助診斷指標的 p75、分布、評級、前一期對照 |
| `CWV_Trend` | 三項核心指標的 p75 逐期序列（前 25 期） |
| `CWV_Missing` | CrUX 無資料的站點 × 裝置組合與原因 |
| `Technical_SF` | Screaming Frog 技術稽核，依優先度排序 |
| `SF_Crawls` | 兩站爬取範圍與完成時間 |
| `SF_Excluded` | 刻意未列為缺陷的項目與原因 |
| `Sources` | 各來源的方法與篩選限制 |

## Apps Script

`apps_script/` 內有 `Code.gs`、`Report.html`、`appsscript.json`，這三個是唯一的來源。
部署包不進版控（git 無法 diff，且曾經默默與原始碼漂移），需要時重新打包：

```bash
cd apps_script && zip -X ../SHOPLINE_2026_08_v2_AppsScript.zip Code.gs Report.html appsscript.json
```

這個指令碼要**綁定在上述活頁簿**（擴充功能 → Apps Script），因為它用 `SpreadsheetApp.getActive()` 讀資料。

1. 開啟活頁簿 → 擴充功能 → Apps Script。
2. 把 `Code.gs` 全文貼入預設的 `Code.gs`。
3. 新增 HTML 檔，命名為 `Report`（不含副檔名），貼入 `Report.html` 全文。
4. 專案設定勾選「在編輯器中顯示 appsscript.json」，套用套件內的設定。
5. 部署 → 新增部署作業 → 網頁應用程式。存取權限預設為 `MYSELF`；月報含內部業務數據，要放寬前先確認分享範圍。
6. 首次執行會要求授權讀取此活頁簿。

`onOpen()` 會在活頁簿加上「SEO／GEO 月報」選單，可直接在側邊欄或全頁對話框預覽，不必先部署。

`appsscript.json` 的 `webapp.access` 是 `MYSELF`、`executeAs` 是 `USER_DEPLOYING`：以部署者身分讀活頁簿，只有部署者能開網頁。

## 驗證結果

- `Code.gs` 與 `Report.html` 的 JS 通過語法解析。
- `preview.html` 以真實活頁簿資料在瀏覽器實際載入：9 個段落、5 張圖表、6 張表格、4 張指標卡、2 組站點篩選都正常；站點篩選由 50 列縮到 25 列後可還原。
- Core Web Vitals 段落已以**真實 CrUX 資料**在瀏覽器實測：4 張評級卡、100% 堆疊分布圖（12 列 × 3 段）、
  LCP p75 趨勢折線圖（2 條線各 26 點，含良好門檻虛線）、20 列指標明細皆正常，第 1 段摘要與第 8 段來源、
  第 9 段資料限制都自動加上對應項目，無 console 錯誤。開發期間另以合成樣本與無金鑰的 `PENDING` 版本
  各驗證過一次（合成樣本只存在暫存目錄，未寫入活頁簿或 `evidence.json`）。
- 1280px 與 375px 皆無水平溢出（`scrollWidth` 等於 `clientWidth`）。加入 Screaming Frog 後來源標籤變長，曾在 375px 造成 31px 溢出，已移除 `.chip` 的 `white-space: nowrap` 修正。
- 本次重抓的 GSC／GA4 與業務實績，與 2026-09-06 早上那版月報的關鍵數字一致：Non-paid 8 月 450 筆、目標 620、達成率 72.58%、較 7 月 −5.66%；GA4 主站 Organic −10.83%、AI Assistant +27.86%；部落格 Organic −9.37%。

## Core Web Vitals

在報表第 6 段「技術稽核與 Sitemap」的最前面，分成三個小節：**Core Web Vitals**（實際使用者資料）、
**Screaming Frog 稽核**（爬取端）、**Sitemap**。兩種資料口徑不同，分開判讀，不做因果歸因。

資料來自 **Chrome UX Report（CrUX）API**，不是 Search Console API：GSC API 沒有開放 Core Web Vitals
報表，而 Search Console 那份報表本身就是以 CrUX 為基礎。Screaming Frog 的 PageSpeed 區塊在這兩次爬取
中全為 0（未設定 PSI 金鑰），GA4 也沒有 `web-vitals` 事件，因此 CrUX 是唯一可用的來源。

- **金鑰**：CrUX API 只接受 Google API key，帶 OAuth token 會被回 `INVALID_ARGUMENT`，所以本專案的
  Sheets／GSC／GA4 憑證都不能用。把金鑰放進環境變數 `CRUX_API_KEY`，或
  `98_環境設定/crux/api_key.txt` 第一行。金鑰所屬的 Cloud 專案要啟用 Chrome UX Report API。
- **範圍**：`https://shopline.tw` 與 `https://blog.shopline.tw` 兩個來源網域，`PHONE` 與 `DESKTOP`
  分開。Google 各裝置分別評級，Search Console 也是這樣分的，因此報表不合併。
- **評級**：`cwv.py` 的 `METRICS` 記錄 Google 公布門檻（LCP ≤ 2500ms、INP ≤ 200ms、CLS ≤ 0.1 為良好；
  > 4000ms／> 500ms／> 0.25 為不佳），良好／需改善／不佳占比直接取自 CrUX 的 histogram，未由 p75 反推。
  三項核心指標全部良好才算「通過」；核心指標不齊則標為「資料不足」。
- **趨勢**：`queryHistoryRecord` 提供 25 期，每期都是 28 天窗口、每週前進一週，因此相鄰期會重疊。
  這個序列可能**落後當期一週**（2026-09-07 那次：歷史到 08-29，當期是 08-09～09-05），所以
  「前一期」是以**日期**挑選——結束日早於當期起始日的最近一期，緊鄰當期且不重疊——而不是固定往前數幾期；
  趨勢序列也會補上當期，讓折線的最後一點與卡片、表格的數字一致。這是技術段落唯一有真實時間序列的資料。
- **限制**：窗口是 CrUX 的**滾動 28 天**，與報表月份不一致，不能當成 8 月單月，也不能與 GSC／GA4 的
  月度口徑對帳。樣本是來源網域層級（非單頁）、未分國別，且僅含已啟用回報的 Chrome 使用者。
  流量不足的組合會回 404，寫入 `CWV_Missing` 而不是當成 0。

沒有 `raw/crux_data.json` 時，`cwvStatus` 為 `PENDING`，該小節會顯示待補說明，第 9 段資料限制也會改寫成
「未納入 Core Web Vitals」。補上資料後重跑步驟 3～6 即可，不需修改程式。

### 2026-09-07 結果（窗口 2026-08-09～09-05，對照窗口至 08-08）

四組（站點 × 裝置）中三組通過，四組都有足夠樣本，沒有無資料組合。

| 站點 × 裝置 | 判定 | LCP | INP | CLS |
| --- | --- | --- | --- | --- |
| 主站 · 行動裝置 | 通過 | 1.49 秒（−7.13%） | 155 ms（−7.19%） | 0.000 |
| 主站 · 電腦 | 通過 | 1.15 秒（+0.35%） | 66 ms（+8.20%） | 0.000 |
| 部落格 · 行動裝置 | **未通過** | **3.61 秒 需改善（+40.57%）** | 195 ms（+16.07%） | 0.000 |
| 部落格 · 電腦 | 通過 | 2.22 秒（+27.56%） | 77 ms（+11.59%） | 0.020 |

部落格行動裝置 LCP 從 8 月中開始上升：逐期 p75 為 2,571（至 08-08）→ 2,816 → 3,467 → 3,654 → 3,614 ms，
在 08-15 那期之後跨過 2,500ms 門檻。同站行動裝置 FCP（+35.76%）與 TTFB（+48%，1,775ms）同步惡化，
方向與伺服器回應時間一致。部落格電腦 LCP 也上升 27.56%，但仍在良好範圍內。

CrUX 是來源網域層級的欄位資料，無法歸因到特定頁面或特定變更；報表因此只描述變化，不宣稱原因，
也不與 Screaming Frog 的爬取端發現（例如部落格 51.48% 圖片超過 100 kB）做因果連結。

## Screaming Frog 技術稽核

已於 2026-09-07 匯出並寫入報表。來源爬取：

| 站點 | Database Id | 完成時間 | 發現網址 |
| --- | --- | --- | --- |
| shopline.tw | `f2215f0d-6f30-42c0-8ec0-9b0a067a71c0` | 2026-09-06 20:24 | 749 |
| blog.shopline.tw | `1af9795a-6a20-44d4-a724-67bd0c9165d3` | 2026-09-06 21:17 | 21,133 |

`sf_technical.py` 的 `CATALOGUE` 是允許清單：Crawl Overview 追蹤的所有篩選中，只有列在裡面且數量大於 0 的才會進報表。`EXCLUDED` 記錄刻意排除的項目與原因（例如 meta keywords 缺失、自我參照 canonical、非循序標題），寫入 `SF_Excluded` 分頁，讓省略的判斷可被檢視。

優先度（高／中／低）是人工判定，不是 Screaming Frog 原生欄位。佔比的分母沿用 Screaming Frog 原始定義並保留在「分母」欄，未自行重算。

高優先度結果：部落格圖片超過 100 kB 4,373 張（51.48%）、部落格內部連結指向轉址 1,298 個（6.14%）、部落格缺少 H1 889 頁（35.56%）、主站圖片超過 100 kB 147 張（63.36%）、主站內部連結指向轉址 2 個。

## 尚未完成

- **Apps Script 尚未建立或部署，沒有正式網址。** 目前執行環境沒有連上 Claude in Chrome 擴充功能，Sheets 憑證也只有 `spreadsheets` scope，不含 `script.projects`。
- **GEO 為沿用快照。** Workduo MCP 在此執行環境無法連線，磁碟上找不到 endpoint／API key，沿用 2026-09-06 10:03 UTC 透過 Workduo MCP 取得的 7、8 月每日資料。
- Screaming Frog 為單一時點快照，**無 7 月對照**，只能描述現況、不能判斷月變化。
- Core Web Vitals 的窗口是 CrUX 的**滾動 28 天**，與報表月份不重合，不能與 GSC／GA4 的月度數字對帳；
  為來源網域層級、未分國別，且僅含已啟用回報的 Chrome 使用者。
- SQL 與成功轉換口徑仍未確認，報表不作轉換成果宣稱。未納入 Ahrefs。
