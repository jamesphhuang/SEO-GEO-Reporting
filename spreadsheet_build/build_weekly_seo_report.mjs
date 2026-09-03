import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputPath = "/Volumes/T7/Codex AI Agent/0528週報.xlsx";

const workbook = Workbook.create();

const dashboard = workbook.worksheets.add("Dashboard");
const report = workbook.worksheets.add("週報紀錄");
const spec = workbook.worksheets.add("MCP查詢規格");
const format = workbook.worksheets.add("整理格式");

for (const sheet of [dashboard, report, spec, format]) {
  sheet.showGridLines = false;
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getCell(0, index).format.columnWidthPx = width;
  });
}

function styleTitle(range) {
  range.format.font = { bold: true, size: 20, color: "#111827" };
}

function styleSection(range) {
  range.format.font = { bold: true, size: 12, color: "#FFFFFF" };
  range.format.fill = "#1F4E78";
}

function styleHeader(range) {
  range.format.font = { bold: true, color: "#FFFFFF" };
  range.format.fill = "#244062";
  range.format.wrapText = true;
}

function styleNote(range) {
  range.format.font = { color: "#334155" };
  range.format.fill = "#F8FAFC";
  range.format.wrapText = true;
}

// Dashboard
dashboard.getRange("A1:H1").merge();
dashboard.getRange("A1").values = [["SEO MCP 資料中心"]];
styleTitle(dashboard.getRange("A1"));
dashboard.getRange("A2:H2").merge();
dashboard.getRange("A2").values = [["MCP-first 架構：各工具只查詢必要摘要與 Top N，Excel 僅保存策略週報與行動紀錄，避免 raw data 長期堆積。"]];
styleNote(dashboard.getRange("A2"));

dashboard.getRange("A4:B4").values = [["最新週報", ""]];
dashboard.getRange("A5:B5").values = [["最新標題", ""]];
dashboard.getRange("A6:B6").values = [["最新狀態", ""]];
dashboard.getRange("A7:B7").values = [["待追蹤週報數", ""]];
dashboard.getRange("A8:B8").values = [["高優先行動週報數", ""]];
dashboard.getRange("A4:B4").format.font = { bold: true, color: "#FFFFFF" };
dashboard.getRange("A4:B4").format.fill = "#1F4E78";
dashboard.getRange("B5").formulas = [["=IFERROR(LOOKUP(2,1/('週報紀錄'!$A$2:$A$201<>\"\"),'週報紀錄'!$C$2:$C$201),\"尚無週報\")"]];
dashboard.getRange("B6").formulas = [["=IFERROR(LOOKUP(2,1/('週報紀錄'!$A$2:$A$201<>\"\"),'週報紀錄'!$P$2:$P$201),\"待建立\")"]];
dashboard.getRange("B7").formulas = [["=COUNTIF('週報紀錄'!$P$2:$P$201,\"待追蹤\")"]];
dashboard.getRange("B8").formulas = [["=COUNTIF('週報紀錄'!$M$2:$M$201,\"*P1*\")"]];
dashboard.getRange("A5:A8").format.font = { bold: true, color: "#0F172A" };
dashboard.getRange("A5:B8").format.fill = "#EAF2F8";

dashboard.getRange("D4:H4").merge();
dashboard.getRange("D4").values = [["推薦展示方式"]];
styleSection(dashboard.getRange("D4:H4"));
dashboard.getRange("D5:H10").values = [
  ["1", "Executive Dashboard", "看趨勢、風險、機會與本週 P1 行動。", "適合老闆/決策者", "每週更新"],
  ["2", "Opportunity Matrix", "用 impressions、排名、轉換價值、難度排優先。", "適合 SEO 策略", "每週更新"],
  ["3", "Technical Health", "彙整 Screaming Frog / Site Audit 問題。", "適合技術修復", "每次 crawl 更新"],
  ["4", "AI Search Visibility", "彙整 Workduo / Brand Radar 的 AI 搜尋能見度。", "適合 GEO", "每週更新"],
  ["5", "Action Backlog", "只留下可執行建議、owner、狀態、下週追蹤。", "適合執行管理", "持續更新"],
  ["6", "Evidence Layer", "保留 MCP 查詢摘要與來源，不保存大批 raw rows。", "適合稽核", "隨報告更新"],
];
dashboard.getRange("D5:H10").format.wrapText = true;

dashboard.getRange("A12:H12").merge();
dashboard.getRange("A12").values = [["資料中心建議結論"]];
styleSection(dashboard.getRange("A12:H12"));
dashboard.getRange("A13:H16").values = [
  ["建議不要再以 Google Sheet 作為 raw data lake。", "保留 Google Sheet / Excel 作為報告與行動追蹤層即可。", "", "", "", "", "", ""],
  ["最佳做法是 MCP 即時查詢 + 小量快取 + 每週策略摘要。", "這會降低 token、降低同步錯誤，也避免多工具 schema 維護成本。", "", "", "", "", "", ""],
  ["若需要互動 Dashboard，建議另建 Looker Studio / Metabase / Retool。", "Excel 保存週報、Looker Studio 顯示 KPI，MCP 負責按需查詢。", "", "", "", "", "", ""],
  ["此工作簿作為每週報告儲存與追蹤中心。", "Automation 每週追加一列，不匯入大量 raw data。", "", "", "", "", "", ""],
];
dashboard.getRange("A13:H16").format.wrapText = true;

setWidths(dashboard, [150, 360, 80, 80, 180, 260, 160, 130]);
dashboard.freezePanes.freezeRows(2);

// Weekly report log
const reportHeaders = [
  "執行日期",
  "週期",
  "標題",
  "整體判讀",
  "GSC重點",
  "GA4重點",
  "Ahrefs重點",
  "ScreamingFrog重點",
  "WorkduoAI重點",
  "機會",
  "風險",
  "SEO策略建議",
  "本週優先行動",
  "成效假設",
  "資料來源與查詢範圍",
  "狀態",
  "完成回報"
];
report.getRange("A1:Q1").values = [reportHeaders];
styleHeader(report.getRange("A1:Q1"));
report.getRange("A2:A201").setNumberFormat("yyyy-mm-dd hh:mm");
report.getRange("A1:Q201").format.wrapText = true;
report.getRange("A1:Q201").format.verticalAlignment = "top";
report.freezePanes.freezeRows(1);
report.tables.add("A1:Q201", true, "WeeklySEOReports");
report.getRange("P2:P201").dataValidation = { rule: { type: "list", values: ["待追蹤", "已完成", "需要確認", "封存"] } };
report.getRange("P2:P201").conditionalFormats.add("containsText", {
  text: "待追蹤",
  format: { fill: "#FEF3C7", font: { color: "#92400E", bold: true } },
});
report.getRange("P2:P201").conditionalFormats.add("containsText", {
  text: "已完成",
  format: { fill: "#DCFCE7", font: { color: "#166534", bold: true } },
});
setWidths(report, [130, 160, 260, 360, 320, 320, 320, 320, 320, 300, 300, 420, 420, 300, 380, 110, 300]);

// MCP query spec
spec.getRange("A1:H1").merge();
spec.getRange("A1").values = [["MCP 查詢規格：只取決策需要的摘要，不匯入 raw data"]];
styleTitle(spec.getRange("A1"));
spec.getRange("A3:H3").values = [["工具", "目的", "建議查詢", "限制", "排序/篩選", "週報輸出", "Token策略", "備註"]];
styleHeader(spec.getRange("A3:H3"));
spec.getRange("A4:H8").values = [
  ["Google Search Console MCP", "搜尋需求與排名機會", "近 7 天 vs 前 7 天；pages、queries、position buckets", "Top 50-100", "impressions 高、position 4-20、CTR 低、clicks 下滑", "GSC重點、機會、風險", "只取聚合與 Top N", "可由 Ahrefs GSC 工具或獨立 GSC MCP 執行"],
  ["Google Analytics 4 MCP", "SEO 流量與商業結果", "Organic Search landing pages、sessions、engagement、key events、revenue", "Top 50", "conversion value 高、engagement 低、流量下滑", "GA4重點、成效假設", "只取必要 metrics", "若 GA4 MCP 不可用，可用 GA4 Data API MCP"],
  ["Ahrefs MCP", "排名、競品、連結與內容缺口", "organic keywords、content gap、backlinks、site audit summary", "Top 50-100", "traffic/value 高、keyword difficulty 可承受、排名接近首頁", "Ahrefs重點、策略建議", "select 必填欄位，避免全欄位", "金額欄位若回傳 cents，要除以 100"],
  ["Screaming Frog MCP", "技術 SEO 健康度", "latest crawl issues、status code、indexability、canonical、titles、h1", "Top 100 issues", "P1/P2、模板型問題、影響頁數", "ScreamingFrog重點、風險", "只取 issue summary 和 affected URLs sample", "若未接 MCP，先由 crawl export 接入"],
  ["Workduo AI MCP", "AI 搜尋/GEO 能見度", "sentiment themes、citations、platform visibility、negative themes", "Top 20-50", "負面情緒、競品提及、引用來源缺口", "WorkduoAI重點、GEO建議", "只取 theme/citation summary", "可補充 Ahrefs Brand Radar"],
];
spec.getRange("A4:H8").format.wrapText = true;
spec.freezePanes.freezeRows(3);
spec.tables.add("A3:H8", true, "MCPQuerySpec");
setWidths(spec, [210, 210, 330, 120, 300, 240, 220, 280]);

// Format discussion sheet
format.getRange("A1:G1").merge();
format.getRange("A1").values = [["每週 SEO 策略建議報告：整理格式"]];
styleTitle(format.getRange("A1"));
format.getRange("A3:G3").values = [["區塊", "欄位", "內容規則", "建議長度", "是否必填", "適合展示位置", "備註"]];
styleHeader(format.getRange("A3:G3"));
format.getRange("A4:G16").values = [
  ["基本資訊", "執行日期", "Automation 實際完成時間", "日期時間", "是", "週報紀錄", ""],
  ["基本資訊", "週期", "上一個完整週一至週日", "YYYY-MM-DD ~ YYYY-MM-DD", "是", "週報紀錄", ""],
  ["基本資訊", "標題", "用一句話說明本週最大 SEO 主題", "20-40 字", "是", "Dashboard / 回報訊息", ""],
  ["管理摘要", "整體判讀", "說明自然搜尋、技術、競品、AI 搜尋的整體方向", "3-5 句", "是", "Dashboard", ""],
  ["資料重點", "GSC/GA4/Ahrefs/SF/Workduo", "每個工具保留 3-5 個 bullet，不貼 raw rows", "每格 3-5 點", "是", "週報紀錄", ""],
  ["策略", "機會", "用 page/query/theme 描述可放大的機會", "3-5 點", "是", "週報紀錄", ""],
  ["策略", "風險", "包含流量下滑、技術錯誤、排名流失、AI 負面情緒", "3-5 點", "是", "週報紀錄", ""],
  ["策略", "SEO策略建議", "每點包含原因、建議、預期影響", "5-8 點", "是", "週報紀錄", ""],
  ["執行", "本週優先行動", "P1/P2/P3，附 owner 可留空", "3-7 點", "是", "Action Backlog", ""],
  ["執行", "成效假設", "用可驗證指標描述，例如 CTR +0.5pp 或 sessions +10%", "2-4 點", "是", "週報紀錄", ""],
  ["稽核", "資料來源與查詢範圍", "列出日期區間、工具、limit、主要 filter", "簡短", "是", "週報紀錄", ""],
  ["追蹤", "狀態", "待追蹤 / 已完成 / 需要確認 / 封存", "固定選項", "是", "週報紀錄", ""],
  ["追蹤", "完成回報", "固定格式：SEO 週報已完成，最新一筆為：[標題]", "一句話", "是", "週報紀錄", ""],
];
format.getRange("A4:G16").format.wrapText = true;
format.freezePanes.freezeRows(3);
format.tables.add("A3:G16", true, "ReportFormat");
setWidths(format, [120, 180, 430, 170, 100, 180, 220]);

const dashboardCheck = await workbook.inspect({
  kind: "table",
  range: "Dashboard!A1:H16",
  include: "values,formulas",
  tableMaxRows: 20,
  tableMaxCols: 8,
});
console.log(dashboardCheck.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan",
});
console.log(errors.ndjson);

await workbook.render({ sheetName: "Dashboard", range: "A1:H16", scale: 1 });
await workbook.render({ sheetName: "週報紀錄", range: "A1:Q12", scale: 1 });
await workbook.render({ sheetName: "MCP查詢規格", range: "A1:H9", scale: 1 });
await workbook.render({ sheetName: "整理格式", range: "A1:G17", scale: 1 });

const xlsx = await SpreadsheetFile.exportXlsx(workbook);
await xlsx.save(outputPath);
console.log(outputPath);
