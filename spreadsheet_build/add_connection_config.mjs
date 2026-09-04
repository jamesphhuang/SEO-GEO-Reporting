import path from "node:path";
import { fileURLToPath } from "node:url";
import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");
const workbookPath = path.join(projectRoot, "0528週報.xlsx");
const input = await FileBlob.load(workbookPath);
const workbook = await SpreadsheetFile.importXlsx(input);

const sheet = workbook.worksheets.getOrAdd("串接設定");
sheet.showGridLines = false;
sheet.getRange("A1:H80").clear({ applyTo: "all" });

function section(range) {
  range.format.fill = "#1F4E78";
  range.format.font = { bold: true, color: "#FFFFFF" };
}

function header(range) {
  range.format.fill = "#244062";
  range.format.font = { bold: true, color: "#FFFFFF" };
  range.format.wrapText = true;
}

sheet.getRange("A1:H1").merge();
sheet.getRange("A1").values = [["SEO MCP 串接設定"]];
sheet.getRange("A1").format.font = { bold: true, size: 20, color: "#111827" };

sheet.getRange("A2:H2").merge();
sheet.getRange("A2").values = [["請填非機密識別資訊即可，例如 project_id、property_id、site_url、country。不要在此填 API token、密碼或 OAuth secret。"]];
sheet.getRange("A2").format.fill = "#F8FAFC";
sheet.getRange("A2").format.font = { color: "#334155" };
sheet.getRange("A2").format.wrapText = true;

sheet.getRange("A4:H4").values = [["類別", "欄位", "是否必填", "請填內容", "範例", "用途", "狀態", "備註"]];
header(sheet.getRange("A4:H4"));

const rows = [
  ["基本", "site_url", "是", "", "https://example.com/", "所有工具對齊主站", "待填", "需與 GSC / GA4 / Ahrefs 對應"],
  ["基本", "brand_name", "是", "", "Your Brand", "Workduo / Brand Radar / 報告標題", "待填", ""],
  ["基本", "competitors", "建議", "", "competitor1.com, competitor2.com", "競品差距與 GEO 比較", "待填", "用逗號分隔"],
  ["基本", "target_country", "是", "", "TW", "GSC / Ahrefs / Workduo 國家篩選", "待填", "ISO 2 碼或工具支援格式"],
  ["基本", "timezone", "是", "Asia/Taipei", "Asia/Taipei", "週期計算與報表時間", "已填", ""],
  ["GSC MCP", "gsc_property_url", "是", "", "https://example.com/ 或 sc-domain:example.com", "Search Console 查詢資產", "待填", "如果走 Ahrefs GSC，也請填 Ahrefs project_id"],
  ["GSC MCP", "gsc_project_id / portfolio_id", "依工具", "", "123456", "MCP 查詢專案識別", "待填", "若獨立 GSC MCP 不需要可留空"],
  ["GA4 MCP", "ga4_property_id", "是", "", "123456789", "GA4 Data API property", "待填", "只填數字 ID，不需填 secret"],
  ["GA4 MCP", "key_events", "建議", "", "generate_lead,purchase", "週報轉換成效", "待填", "用逗號分隔"],
  ["GA4 MCP", "organic_channel_name", "建議", "Organic Search", "Organic Search", "自然搜尋流量篩選", "已填", "若 GA4 頻道名稱不同請改"],
  ["Ahrefs MCP", "ahrefs_project_id", "是", "", "123456", "GSC、Site Audit、Web Analytics 專案", "待填", ""],
  ["Ahrefs MCP", "ahrefs_target", "是", "", "example.com", "Site Explorer 查詢目標", "待填", "domain 建議用 mode=subdomains"],
  ["Ahrefs MCP", "ahrefs_country", "是", "", "tw", "關鍵字/流量國家", "待填", "依 Ahrefs API 國家格式"],
  ["Screaming Frog MCP", "crawl_project_id / crawl_id", "是", "", "sf-project-001", "最新 crawl / issue 查詢", "待填", "若先用 Ahrefs Site Audit 替代，填 Ahrefs project_id"],
  ["Screaming Frog MCP", "crawl_source", "建議", "", "MCP latest crawl", "確認 crawl 來源", "待填", ""],
  ["Workduo AI MCP", "workspaceId", "依工具", "", "workspace_xxx", "Workduo workspace 篩選", "待填", "如果預設 workspace 可留空"],
  ["Workduo AI MCP", "projectId", "是", "", "project_xxx", "AI 搜尋監測專案", "待填", ""],
  ["Workduo AI MCP", "platforms", "建議", "", "chatgpt,perplexity,gemini", "AI 平台篩選", "待填", "依 Workduo 支援值"],
  ["Workduo AI MCP", "queryCountries", "建議", "", "TW,US", "AI 查詢國家", "待填", "ISO 2 碼，多國逗號分隔"],
  ["報告", "weekly_report_file", "是", "0528週報.xlsx", "0528週報.xlsx", "Automation 寫入目標", "已填", ""],
  ["報告", "weekly_report_sheet", "是", "週報紀錄", "週報紀錄", "Automation 寫入分頁", "已填", ""],
  ["報告", "lookback_period", "是", "上一個完整週一至週日", "上一個完整週一至週日", "週報時間範圍", "已填", ""],
];

sheet.getRange(`A5:H${rows.length + 4}`).values = rows;
sheet.getRange(`A5:H${rows.length + 4}`).format.wrapText = true;
sheet.getRange("A4:H80").format.verticalAlignment = "top";
sheet.getRange("C5:C80").dataValidation = { rule: { type: "list", values: ["是", "建議", "依工具"] } };
sheet.getRange("G5:G80").dataValidation = { rule: { type: "list", values: ["待填", "已填", "待測試", "已串接", "暫不用"] } };
sheet.getRange("G5:G80").conditionalFormats.add("containsText", {
  text: "待填",
  format: { fill: "#FEF3C7", font: { color: "#92400E", bold: true } },
});
sheet.getRange("G5:G80").conditionalFormats.add("containsText", {
  text: "已串接",
  format: { fill: "#DCFCE7", font: { color: "#166534", bold: true } },
});

sheet.getRange("A29:H29").merge();
sheet.getRange("A29").values = [["串接測試順序"]];
section(sheet.getRange("A29:H29"));
sheet.getRange("A30:H34").values = [
  ["1", "確認基本欄位", "site_url、brand_name、target_country、timezone", "", "", "", "", ""],
  ["2", "測試 Ahrefs / Workduo", "目前可用工具已在本環境出現，可先用 project_id 跑小查詢", "", "", "", "", ""],
  ["3", "測試 GSC / GA4", "需要確認獨立 MCP 名稱或改由 Ahrefs GSC / GA4 Data API MCP 執行", "", "", "", "", ""],
  ["4", "測試 Screaming Frog", "若獨立 MCP 未載入，先用 Ahrefs Site Audit 作技術 SEO 摘要", "", "", "", "", ""],
  ["5", "跑一次人工週報", "成功後再讓每週一 Automation 自動跑", "", "", "", "", ""],
];
sheet.getRange("A30:H34").format.wrapText = true;

const widths = [150, 220, 90, 260, 260, 260, 110, 300];
widths.forEach((width, index) => {
  sheet.getCell(0, index).format.columnWidthPx = width;
});
sheet.freezePanes.freezeRows(4);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 200 },
  summary: "formula error scan",
});
console.log(errors.ndjson);

await workbook.render({ sheetName: "串接設定", range: "A1:H34", scale: 1 });
const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(workbookPath);
console.log(workbookPath);
