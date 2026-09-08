# 2026 年 8 月 SEO／GEO 月報

開啟 `apps_script/Report.html` 即可閱讀完整月報。HTML 內含資料、圖表與來源資訊，不需安裝套件。這是一份固定快照；開啟網頁不會重跑 MCP。

## 內容

- 正式 Non-paid Leads、7 月對照與目標達成率。
- 主站／部落格 GSC 台灣 WEB 搜尋表現。
- 主站／部落格 GA4 Organic Search 與 AI Assistant，依既有 hostname 合約、所有國家。
- Workduo 台灣專案的每日平均可見度、SOV 及品牌比較。
- 8 月重點頁面、9 月建議行動與資料限制。

## Apps Script

`apps_script` 目錄與 `SHOPLINE_2026_08_AppsScript.zip` 包含三個檔案：`Code.gs`、`Report.html`、`appsscript.json`。ZIP 是傳輸套件；Apps Script 編輯器不提供直接匯入 ZIP 的功能。

1. 在 Apps Script 建立獨立專案，或使用既有專案（先檢查是否已有 `doGet`，避免重複）。
2. 將 `Code.gs` 內容貼入指令碼；新增名稱為 `Report` 的 HTML 檔並貼入 `Report.html` 全文。
3. 專案設定可顯示 `appsscript.json`，使用套件中的設定。此程式僅回傳內嵌月報，不需要存取試算表或呼叫外部 API。
4. 使用「部署 → 測試部署 → 網頁應用程式」檢查。正式部署時選擇實際需要的存取範圍；月報包含內部業務數據，不應自行擴大分享範圍。
5. 開啟部署回傳的網址，確認標題、450 筆名單、7 張圖表、表格換頁與來源資訊均可用。

實作依據：[Google Apps Script HTML Service](https://developers.google.com/apps-script/guides/html)、[Web Apps](https://developers.google.com/apps-script/guides/web)。

截至本次交付，尚未建立／更新遠端 Apps Script，也沒有正式部署網址：可用 MCP 沒有 Apps Script 建立／部署能力、Drive 搜尋未找到可用指令碼專案，內建瀏覽器造訪 Apps Script 轉至未登入頁面。需要已登入的瀏覽器或可操作的專案，才能完成遠端部署及回讀。

## 證據與重製

`evidence.json` 保存本次 MCP 回應快照；`pages.json` 保存頁面查詢。`artifact.json` 是標準報表結構與已檢視資料。`build_report.py` 從快照產生內容，並實際執行 SQLite JSON1 查詢彙總。SQL 檔保存轉換邏輯；來源說明保留原始 MCP 工具、日期、篩選與分頁限制。

在專案根目錄執行 `python3 outputs/monthly_report_2026_08/build_report.py` 可重建 artifact；HTML 由已安裝 Data Analytics 插件的 `skills/build-report/scripts/deliver_portable_artifact.mjs` 產生。這只會重製已保存資料，不會更新來源。

## 驗證與限制

- 標準 artifact 驗證、HTML 封裝及 payload 結構一致性檢查通過。
- 內建瀏覽器實際載入報表與互動圖表；檢視桌面、390px 手機畫面，手機頁面無水平溢出。
- 自動 headless Chrome 驗證逾時，未宣稱自動視覺驗證通過；以實際瀏覽器檢查補充。
- 尚未在 Apps Script 伺服器執行 `doGet()`，未驗證 Apps Script iframe 內的互動及部署權限。
- SQL 與成功轉換尚未有確認口徑；報表保持 partial。GEO 為每日等權平均，提示題目與平台組合尚未固定樣本對齊。
- GSC 頁面明細各站僅 Top 20；未取得 7 月逐頁對照。不以此判斷下滑原因。未納入 Ahrefs 與當月 Screaming Frog 技術稽核。
- 未修改既有報表、業務來源、資料合約或歷史快照。
