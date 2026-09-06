import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const projectRoot = path.resolve(__dirname, "..");

process.on("uncaughtException", (error) => {
  console.error(`BUILD_ERROR: ${error.name}: ${error.message}`);
  console.error(error.stack);
  process.exit(1);
});

const dataContract = JSON.parse(
  await fs.readFile(path.join(projectRoot, "contracts", "data_contract.v1.json"), "utf8")
);
const snapshotSheetManifest = {
  legacy: {
    sheetName: "KPI Snapshots",
    title: "KPI Snapshots｜彙總、追加式、可追溯",
    description: "只寫入彙總指標，不存 GA4／Salesforce 個資或逐筆 raw data。新匯入一律追加；更正以新批次與 revision note 表示。",
    headerRow: 4,
    headers: [
      "Snapshot ID", "載入時間", "資料來源", "報表粒度", "期間起日", "期間迄日", "As-of 日期", "資料狀態", "Metric Group", "Metric", "Segment", "Platform / Property", "Value", "Denominator", "Target", "正式來源", "原始檔 / 查詢連結", "Revision / Note"
    ],
    initialDataRows: [],
  },
  v2: {
    sheetName: "KPI Snapshots v2",
    title: "KPI Snapshots v2｜Append-only Data Contract v1.0",
    description: "Production snapshot storage after activation. Activation pending until programmatic gateway verification. Legacy KPI Snapshots remains historical/read-only. No raw personal data.",
    headerRow: 4,
    headers: dataContract.snapshot.columns,
    initialDataRows: [],
  },
};

if (process.argv.includes("--snapshot-schema-manifest")) {
  console.log(JSON.stringify(snapshotSheetManifest));
  process.exit(0);
}

const { SpreadsheetFile, Workbook } = await import("@oai/artifact-tool");
const outputDir = process.env.SEO_GEO_FRAMEWORK_OUTPUT_DIR
  ? path.resolve(process.env.SEO_GEO_FRAMEWORK_OUTPUT_DIR)
  : path.join(projectRoot, "outputs", "seo_geo_reporting_framework_v1");
const outputPath = path.join(outputDir, "SEO_GEO_Reporting_Framework_v1.0.xlsx");

const COLORS = {
  navy: "#1F4E78",
  blue: "#244062",
  paleBlue: "#EAF2F8",
  paleGray: "#F8FAFC",
  gray: "#E5E7EB",
  text: "#0F172A",
  muted: "#475569",
  red: "#FEE2E2",
  amber: "#FEF3C7",
  green: "#DCFCE7",
  purple: "#F3E8FF",
};

const workbook = Workbook.create();

function addSheet(name) {
  const sheet = workbook.worksheets.add(name);
  sheet.showGridLines = false;
  return sheet;
}

function setWidths(sheet, widths) {
  widths.forEach((width, index) => {
    sheet.getCell(0, index).format.columnWidthPx = width;
  });
}

function title(sheet, range, text) {
  sheet.getRange(range).merge();
  const cell = sheet.getRange(range.split(":")[0]);
  cell.values = [[text]];
  cell.format = {
    fill: COLORS.navy,
    font: { bold: true, size: 18, color: "#FFFFFF" },
    verticalAlignment: "center",
  };
  cell.format.rowHeightPx = 30;
}

function subtitle(sheet, range, text) {
  sheet.getRange(range).merge();
  const cell = sheet.getRange(range.split(":")[0]);
  cell.values = [[text]];
  cell.format = {
    fill: COLORS.paleGray,
    font: { size: 10, color: COLORS.muted },
    wrapText: true,
    verticalAlignment: "center",
  };
  cell.format.rowHeightPx = 36;
}

function section(sheet, range, text) {
  sheet.getRange(range).merge();
  const cell = sheet.getRange(range.split(":")[0]);
  cell.values = [[text]];
  cell.format = {
    fill: COLORS.blue,
    font: { bold: true, size: 11, color: "#FFFFFF" },
    verticalAlignment: "center",
  };
  cell.format.rowHeightPx = 22;
}

function headers(sheet, range) {
  const cell = sheet.getRange(range);
  cell.format = {
    fill: COLORS.gray,
    font: { bold: true, color: COLORS.text },
    wrapText: true,
    verticalAlignment: "center",
  };
  cell.format.borders = { preset: "outside", style: "thin", color: "#CBD5E1" };
}

function note(sheet, range) {
  const cell = sheet.getRange(range);
  cell.format = {
    fill: COLORS.paleGray,
    font: { size: 10, color: COLORS.muted },
    wrapText: true,
    verticalAlignment: "top",
  };
}

function tableStyle(sheet, range) {
  const cell = sheet.getRange(range);
  cell.format.wrapText = true;
  cell.format.verticalAlignment = "top";
  cell.format.borders = { preset: "outside", style: "thin", color: "#CBD5E1" };
}

function applyListValidation(sheet, range, values) {
  sheet.getRange(range).dataValidation = { rule: { type: "list", values } };
}

const dashboard = addSheet("Dashboard");
const readme = addSheet("README & 口徑");
const reportRuns = addSheet("Report Runs");
const kpiSnapshots = addSheet(snapshotSheetManifest.legacy.sheetName);
const kpiSnapshotsV2 = addSheet(snapshotSheetManifest.v2.sheetName);
const actionQueue = addSheet("Action Queue");
const contentLog = addSheet("Content Change Log");
const urlRegistry = addSheet("URL Registry");
const brandDictionary = addSheet("Brand Dictionary");
const geoRegistry = addSheet("GEO Prompt Registry");
const crawlRuns = addSheet("Crawl Runs");
const targets = addSheet("Targets & Baselines");

// Dashboard
title(dashboard, "A1:J1", "SHOPLINE TW｜SEO / GEO Reporting Framework v1.0");
subtitle(
  dashboard,
  "A2:J2",
  "第一階段控制檔與 Dashboard 模板。正式數字須來自已通過資料健康檢查的追加式快照；尚無資料時不以 0 代替。"
);
section(dashboard, "A4:J4", "資料狀態與 P0：先看是否有需立即處理的問題");
dashboard.getRange("A5:B8").values = [
  ["最新 Report ID", ""],
  ["共同完整截止日", ""],
  ["P0 待驗證 / 處理", ""],
  ["正式資料狀態", "尚未匯入快照"],
];
dashboard.getRange("B5").formulas = [["=IFERROR(LOOKUP(2,1/('Report Runs'!$A$5:$A$501<>\"\"),'Report Runs'!$A$5:$A$501),\"尚無報告\")"]];
dashboard.getRange("B6").formulas = [["=IFERROR(LOOKUP(2,1/('Report Runs'!$A$5:$A$501<>\"\"),'Report Runs'!$E$5:$E$501),\"尚無共同完整截止日\")"]];
dashboard.getRange("B7").formulas = [["=COUNTIF('Action Queue'!$C$2:$C$501,\"P0\")-COUNTIFS('Action Queue'!$C$2:$C$501,\"P0\",'Action Queue'!$P$2:$P$501,\"Verified\")"]];
dashboard.getRange("A5:A8").format = { fill: COLORS.paleBlue, font: { bold: true, color: COLORS.text } };
dashboard.getRange("B5:B8").format = { fill: "#FFFFFF", font: { color: COLORS.text } };
dashboard.getRange("A5:B8").format.borders = { preset: "all", style: "thin", color: "#CBD5E1" };
dashboard.getRange("A5:B8").format.verticalAlignment = "center";

dashboard.getRange("D5:J8").values = [
  ["P0 顯示原則", "只顯示 New、In progress、Blocked 的 P0；Verified 才移出。", "", "", "", "", ""],
  ["P0 觸發邊界", "正式成功轉換異常中斷／歸零，或核心 SEO 範圍全站可存取／可索引性事故。", "", "", "", "", ""],
  ["不主動通知", "已取消 Slack／Email 發送；以此區塊與 Action Queue 為唯一紀錄與檢視入口。", "", "", "", "", ""],
  ["Crawl 快照", "週一 Lite Crawl 為 Preview／Final 共用快照；P0 或手動補跑才更新。", "", "", "", "", ""],
];
dashboard.getRange("D5:J8").format = { fill: COLORS.red, font: { color: COLORS.text }, wrapText: true, verticalAlignment: "center" };
dashboard.getRange("D5:J8").format.borders = { preset: "all", style: "thin", color: "#FCA5A5" };
for (const row of [5, 6, 7, 8]) dashboard.getRange(`E${row}:J${row}`).merge();
dashboard.getRange("A5:J5").format.rowHeightPx = 38;
dashboard.getRange("A6:J6").format.rowHeightPx = 58;
dashboard.getRange("A7:J8").format.rowHeightPx = 48;

section(dashboard, "A10:J10", "四個核心面向：分開看，不建立單一 SEO／GEO 總分");
dashboard.getRange("A11:J15").values = [
  ["面向", "正式指標", "來源", "比較方式", "判讀狀態", "", "", "", "", ""],
  ["SEO 能見度", "Google 曝光、點擊、CTR、排名；品牌詞／非品牌詞", "GSC", "共同完整截止日往回 7 天；等長比較", "待第一份快照", "", "", "", "", ""],
  ["網站健康度", "Google 體驗健康度 + 技術可搜尋性", "GSC / Screaming Frog", "週報看異常；月報看完整健康度", "待第一份快照", "", "", "", "", ""],
  ["GEO 能見度", "WorkDuo 平台別能見度、SOV、引用與情緒", "WorkDuo", "平台分開；總覽等權重；N/A 不視為 0", "待第一份快照", "", "", "", "", ""],
  ["商業成果", "Non-paid Leads、SQL（Sales-Qualified Lead）", "Salesforce / Excel Actual", "SQL 依名單月份 Cohort，月結滿 60 天才正式判讀；非 Ready 不作正式結論", "待第一份匯入", "", "", "", "", ""],
];
headers(dashboard, "A11:E11");
tableStyle(dashboard, "A11:E15");
dashboard.getRange("A12:A15").format.font = { bold: true, color: COLORS.text };

section(dashboard, "A17:J17", "閱讀與執行節奏");
dashboard.getRange("A18:J22").values = [
  ["週一 Preview", "前一週的早期觀察、Lite Crawl、Top 5 Action Queue；不得把未成熟來源當正式結論。", "", "", "", "", "", "", "", ""],
  ["週二 Final", "以共同完整截止日往回 7 天作正式比較；GA4 與 GSC 採相同截止日。", "", "", "", "", "", "", "", ""],
  ["月報", "完整 SEO／GEO 趨勢、Ahrefs 競品比較、Full Crawl、內容 T+ 成效與商業結果。", "", "", "", "", "", "", "", ""],
  ["季報", "策略、題庫版本、技術債、基準與資源分配調整。", "", "", "", "", "", "", "", ""],
  ["第一步", "匯入首批彙總快照，再完成試用／諮詢／講座成功事件與 Salesforce 對應的 P1 驗證。", "", "", "", "", "", "", "", ""],
];
note(dashboard, "A18:J22");

setWidths(dashboard, [150, 220, 150, 210, 160, 90, 90, 90, 90, 90]);
dashboard.freezePanes.freezeRows(2);

// README & definitions
title(readme, "A1:H1", "README｜資料口徑、來源職責與操作順序");
subtitle(readme, "A2:H2", "此控制檔不保存個人可識別資料或大量 raw data。原始 Excel、Screaming Frog crawl 檔與 CSV 保持於受限原始資料位置，並以連結／批次 ID 追溯。"
);
section(readme, "A4:H4", "兩種報告與三種決策視角");
readme.getRange("A5:B8").values = [
  ["SEO / GEO 總覽報告", "商業成果、SEO／GEO 趨勢、風險、機會與需要決策事項。"],
  ["SEO / GEO 執行與證據報告", "URL、query、prompt、資料來源、Action Queue 與驗證證據。"],
  ["週報", "異常與本週優先處理事項。"],
  ["月報／季報", "完整成果與策略資源調整。"],
];
note(readme, "A5:H8");

section(readme, "A10:H10", "資料來源職責");
readme.getRange("A11:E17").values = [
  ["來源", "正式職責", "不應做的事", "例行節奏", "資料狀態"],
  ["Google Search Console", "Google 曝光、點擊、CTR、排名、索引與 CWV。", "不以尚未完整日期下正式結論。", "週報／月報", "Ready / Partial / Stale / Failed"],
  ["GA4", "行為、跨網域、CTA 與可辨識 AI referral 診斷。", "不取代 Salesforce 正式商業結果。", "週報／月報", "Ready / Partial / Stale / Failed"],
  ["WorkDuo", "AI 能見度、SOV、引用、情緒與競品敘事。", "N/A 不可視為 0；不得直接宣稱因果。", "週報異常／月報完整", "Ready / Partial / Stale / Failed"],
  ["Screaming Frog", "每 URL 技術檢查與 crawl 證據。", "SSO 不做完整 crawl。", "週 Lite／月 Full／季比較", "Ready / Stale / Failed"],
  ["Ahrefs", "競品關鍵字、內容缺口、外鏈與網域。", "不作週度例行全量雜訊來源。", "月報；P0/P1 例外", "Ready / Partial / Stale / Failed"],
  ["Salesforce / Excel Actual", "Non-paid Leads、正式成功轉換、SQL。", "不以 GA4 補代正式結果。", "每次匯入／月報", "Ready / Stale / Failed"],
];
headers(readme, "A11:E11");
tableStyle(readme, "A11:E17");
readme.tables.add("A11:E17", true, "SourceRoles");

section(readme, "A19:H19", "資料與版本規則");
readme.getRange("A20:B25").values = [
  ["追加式快照", "每次 API／Excel 匯入新增一筆批次與期間，不覆寫原快照。若來源更正，Dashboard 顯示最新核定值並保留更正軌跡。"],
  ["資料健康檢查", "先檢查來源、日期、涵蓋率、欄位與可比較性，再產出報告。Partial／Stale／Failed 不驅動正式分數或紅黃綠結論。"],
  ["品牌詞字典", "季度例行版本化；新產品或重大活動可中途新版本。歧義查詢先列待判定，不自動歸為非品牌。"],
  ["內容 Cohort 群組", "本報告依同一內容版本或重大更新日期歸組追蹤；一般分析中 cohort 也可指具共同特徵或互動行為的使用者群體。"],
  ["SQL", "依 contracts/data_contract.v1.json：名單月份月結後滿 60 天才成熟。未成熟僅顯示累積 SQL，不納入 Target 達成率、正式趨勢或紅黃綠結論；定義變更須另建核准版本。"],
  ["最小權限", "Dashboard／彙總表可廣泛唯讀；Action 與內容列由指定 Owner 編輯；原始匯出與個資維持受限。"],
];
note(readme, "A20:H25");
setWidths(readme, [180, 390, 100, 100, 100, 100, 100, 100]);
readme.freezePanes.freezeRows(2);

// Report Runs
title(reportRuns, "A1:R1", "Report Runs｜Preview 與 Final 的可追溯紀錄");
subtitle(reportRuns, "A2:R2", "每一列代表一次已產出的報告；週二 Final 的正式比較期間為共同完整截止日往回 7 天。空白模板列不代表已完成報告。"
);
reportRuns.getRange("A4:R4").values = [[
  "Report ID", "產出日期", "版本", "報告類型", "共同完整截止日", "分析期起日", "分析期迄日", "比較期起日", "比較期迄日", "GSC 狀態", "GA4 狀態", "WorkDuo 狀態", "Crawl 狀態", "Excel / SF 狀態", "Final 狀態", "摘要連結", "資料批次 ID", "備註"
]];
headers(reportRuns, "A4:R4");
reportRuns.getRange("A5:R501").format = { wrapText: true, verticalAlignment: "top" };
reportRuns.getRange("B5:B501").setNumberFormat("yyyy-mm-dd hh:mm");
reportRuns.getRange("E5:I501").setNumberFormat("yyyy-mm-dd");
applyListValidation(reportRuns, "C5:C501", ["v1.0"]);
applyListValidation(reportRuns, "D5:D501", ["Weekly Preview", "Weekly Final", "Monthly", "Quarterly"]);
applyListValidation(reportRuns, "J5:O501", ["Ready", "Partial", "Stale", "Failed"]);
setWidths(reportRuns, [150, 145, 70, 120, 130, 120, 120, 120, 120, 95, 95, 110, 100, 115, 100, 220, 150, 260]);
reportRuns.freezePanes.freezeRows(4);

// KPI Snapshots
title(kpiSnapshots, "A1:R1", snapshotSheetManifest.legacy.title);
subtitle(kpiSnapshots, "A2:R2", snapshotSheetManifest.legacy.description);
kpiSnapshots.getRange("A4:R4").values = [snapshotSheetManifest.legacy.headers];
headers(kpiSnapshots, "A4:R4");
kpiSnapshots.getRange("A5:R2001").format = { wrapText: true, verticalAlignment: "top" };
kpiSnapshots.getRange("B5:B2001").setNumberFormat("yyyy-mm-dd hh:mm");
kpiSnapshots.getRange("E5:G2001").setNumberFormat("yyyy-mm-dd");
kpiSnapshots.getRange("M5:O2001").setNumberFormat("#,##0.0");
applyListValidation(kpiSnapshots, "C5:C2001", ["GSC", "GA4 Homepage-TW", "GA4 Blog-All", "WorkDuo", "Screaming Frog", "Ahrefs", "Salesforce / Excel Actual"]);
applyListValidation(kpiSnapshots, "D5:D2001", ["Daily", "Weekly", "Monthly", "Quarterly", "Crawl"]);
applyListValidation(kpiSnapshots, "H5:H2001", ["Ready", "Partial", "Stale", "Failed"]);
applyListValidation(kpiSnapshots, "I5:I2001", ["SEO Visibility", "Google Experience", "Technical Searchability", "GEO Visibility", "Business", "Content Outcome"]);
applyListValidation(kpiSnapshots, "P5:P2001", ["Yes", "No"]);
setWidths(kpiSnapshots, [155, 145, 150, 90, 110, 110, 105, 90, 160, 170, 160, 150, 100, 105, 100, 95, 250, 250]);
kpiSnapshots.freezePanes.freezeRows(4);

// KPI Snapshots v2
title(kpiSnapshotsV2, "A1:Y1", snapshotSheetManifest.v2.title);
subtitle(kpiSnapshotsV2, "A2:Y2", snapshotSheetManifest.v2.description);
kpiSnapshotsV2.getRange("A4:Y4").values = [snapshotSheetManifest.v2.headers];
headers(kpiSnapshotsV2, "A4:Y4");
kpiSnapshotsV2.getRange("A5:Y2001").format = { wrapText: true, verticalAlignment: "top" };
kpiSnapshotsV2.getRange("B5:B2001").setNumberFormat("yyyy-mm-dd hh:mm");
kpiSnapshotsV2.getRange("E5:G2001").setNumberFormat("yyyy-mm-dd");
kpiSnapshotsV2.getRange("M5:O2001").setNumberFormat("#,##0.0");
setWidths(kpiSnapshotsV2, [260, 165, 145, 110, 110, 110, 110, 95, 150, 170, 180, 170, 100, 110, 100, 280, 260, 120, 90, 130, 260, 80, 260, 260, 130]);
kpiSnapshotsV2.freezePanes.freezeRows(4);

// Action Queue
title(actionQueue, "A1:T1", "Action Queue｜P0 固定顯示、Top 5 動態排序");
subtitle(actionQueue, "A2:T2", "每筆 action 必須有一位 Owner、截止日、預期影響、驗證指標與後續回填結果。P0／P1 優先；其餘以影響 × 機會 × 信心 ÷ 成本排序。"
);
actionQueue.getRange("A4:T4").values = [[
  "Action ID", "建立日期", "Priority", "領域", "行動標題", "商業影響 (1-5)", "可回收機會 (1-5)", "證據信心 (1-5)", "投入成本 (1-5)", "排序分數", "診斷與證據", "預期影響", "驗證指標", "Owner", "截止日", "Status", "完成日期", "結果回填", "來源批次 / 連結", "備註"
]];
headers(actionQueue, "A4:T4");
actionQueue.getRange("A5:T501").format = { wrapText: true, verticalAlignment: "top" };
actionQueue.getRange("B5:B501").setNumberFormat("yyyy-mm-dd");
actionQueue.getRange("O5:O501").setNumberFormat("yyyy-mm-dd");
actionQueue.getRange("Q5:Q501").setNumberFormat("yyyy-mm-dd");
actionQueue.getRange("F5:I501").setNumberFormat("0");
actionQueue.getRange("J5:J501").formulasR1C1 = [["=IFERROR((RC[-4]*RC[-3]*RC[-2])/RC[-1],\"\")"]];
actionQueue.getRange("J5:J501").format.numberFormat = "0.0";
applyListValidation(actionQueue, "C5:C501", ["P0", "P1", "P2", "P3", "P4", "P5"]);
applyListValidation(actionQueue, "D5:D501", ["SEO Visibility", "Google Experience", "Technical Searchability", "GEO", "Conversion Measurement", "Content", "Competitor", "Reporting"]);
applyListValidation(actionQueue, "F5:I501", ["1", "2", "3", "4", "5"]);
applyListValidation(actionQueue, "P5:P501", ["New", "In progress", "Blocked", "Verified"]);
actionQueue.getRange("C5:C501").conditionalFormats.add("containsText", { text: "P0", format: { fill: COLORS.red, font: { bold: true, color: "#991B1B" } } });
actionQueue.getRange("C5:C501").conditionalFormats.add("containsText", { text: "P1", format: { fill: COLORS.amber, font: { bold: true, color: "#92400E" } } });
actionQueue.getRange("P5:P501").conditionalFormats.add("containsText", { text: "Verified", format: { fill: COLORS.green, font: { bold: true, color: "#166534" } } });
setWidths(actionQueue, [135, 105, 70, 145, 260, 105, 115, 105, 105, 95, 300, 210, 180, 160, 105, 110, 105, 250, 210, 220]);
actionQueue.freezePanes.freezeRows(4);

// Content Change Log
title(contentLog, "A1:R1", "Content Change Log｜版本化內容成效追蹤");
subtitle(contentLog, "A2:R2", "內容 Owner 應在發布或重大更新後 3 個工作天內登錄。重大變更建立新版本並重設觀察；輕微修改不重設。未登錄內容只呈現一般趨勢，不做 T+ 歸因。"
);
contentLog.getRange("A4:R4").values = [[
  "Change ID", "Canonical URL", "內容類型", "內容 Owner", "發布 / 更新日", "內容狀態", "新內容 / 既有更新", "變更程度", "版本", "假設與受眾", "SEO 目標詞", "GEO Core Topic", "CTA", "28 天前後基準", "對照方法", "T+14", "T+30 / 60 / 180", "結果與備註"
]];
headers(contentLog, "A4:R4");
contentLog.getRange("A5:R1001").format = { wrapText: true, verticalAlignment: "top" };
contentLog.getRange("E5:E1001").setNumberFormat("yyyy-mm-dd");
applyListValidation(contentLog, "F5:F1001", ["Planned", "Published", "Measured", "Overlapped"]);
applyListValidation(contentLog, "G5:G1001", ["New", "Existing update"]);
applyListValidation(contentLog, "H5:H1001", ["Minor", "Major"]);
applyListValidation(contentLog, "O5:O1001", ["YoY", "Control page", "MoM supplemental"]);
setWidths(contentLog, [130, 300, 125, 140, 115, 105, 125, 105, 95, 260, 180, 180, 130, 180, 135, 135, 170, 260]);
contentLog.freezePanes.freezeRows(4);

// URL Registry
title(urlRegistry, "A1:J1", "URL Registry｜轉換頁與獨立漏斗");
subtitle(urlRegistry, "A2:J2", "URL 使用 canonical 形式，不記錄 _gl 等追蹤參數。成功事件需在後端成功／thank-you 後觸發；按鈕點擊僅屬微轉換。"
);
urlRegistry.getRange("A4:J4").values = [["Canonical URL", "頁面 / 漏斗", "層級", "正式成功事件", "計入 North Star", "報告歸屬", "Crawl 範圍", "GA4 / SF 驗證", "微轉換", "備註"]];
urlRegistry.getRange("A5:J10").values = [
  ["https://consultation.shopline.tw/", "顧問諮詢", "Tier 1", "consultation_submit_success", "Yes", "商業 SEO / GEO", "Lite conversion-page check", "Pending validation", "form_start / CTA click", "成功送出商務諮詢"],
  ["https://sso.shoplineapp.com/users/sign_up?locale=zh-hant&ref=shopline.tw", "試用註冊", "Tier 1", "trial_signup_complete", "Yes", "商業 SEO / GEO", "No full crawl", "Pending validation", "trial CTA click", "完成註冊；SSO 排除 Full Crawl"],
  ["https://seminar.shopline.tw/", "開店講座", "Tier 2", "seminar_submit_success", "No", "次級商業名單", "Lite conversion-page check", "Pending validation", "form_start / CTA click", "明顯呈現但不合併 North Star"],
  ["https://shopline.tw/about/pricing", "Pricing", "Watchlist", "—", "No", "轉換協助", "Core SEO crawl", "Pending validation", "trial / consultation CTA", "高意圖協助頁"],
  ["https://shopline.tw/cooperate", "合作夥伴", "Independent", "partner_submit_success", "No", "合作夥伴漏斗", "Core SEO crawl", "Pending validation", "form_start / CTA click", "不可混入商業轉換總數"],
  ["https://marketing.shopline.tw/job", "HR 加入我們", "Independent", "job_application_submit_success", "No", "HR 漏斗", "Separate / non-commercial", "Pending validation", "application start", "不可混入商業轉換總數"],
];
headers(urlRegistry, "A4:J4");
tableStyle(urlRegistry, "A4:J10");
urlRegistry.tables.add("A4:J10", true, "URLRegistry");
setWidths(urlRegistry, [320, 145, 100, 210, 105, 160, 180, 140, 160, 220]);
urlRegistry.freezePanes.freezeRows(4);

// Brand dictionary
title(brandDictionary, "A1:J1", "Brand Dictionary｜人工確認後版本化啟用");
subtitle(brandDictionary, "A2:J2", "先由近 12 個完整月 GSC 查詢產生候選；Company brand、Product brand、Non-brand 與 Pending review 分開。Pending review 不得自動算入非品牌。"
);
brandDictionary.getRange("A4:J4").values = [["Dictionary Version", "詞彙", "分類", "匹配規則", "語言 / 地區", "生效日", "候選來源", "人工確認者", "狀態", "備註"]];
headers(brandDictionary, "A4:J4");
brandDictionary.getRange("A5:J1001").format = { wrapText: true, verticalAlignment: "top" };
brandDictionary.getRange("F5:F1001").setNumberFormat("yyyy-mm-dd");
applyListValidation(brandDictionary, "C5:C1001", ["Company brand", "Product brand", "Non-brand", "Pending review"]);
applyListValidation(brandDictionary, "D5:D1001", ["Exact", "Contains", "Regex"]);
applyListValidation(brandDictionary, "I5:I1001", ["Candidate", "Approved", "Retired"]);
setWidths(brandDictionary, [130, 220, 130, 110, 120, 105, 180, 140, 105, 260]);
brandDictionary.freezePanes.freezeRows(4);

// GEO prompt registry
title(geoRegistry, "A1:I1", "GEO Prompt Registry｜GEO-Core v1.0");
subtitle(geoRegistry, "A2:I2", "目前 41 題凍結為 GEO-Core v1.0。平台分開呈現（ChatGPT、Gemini、AI Overview）；總覽等權重。新題目先進實驗題庫，僅於季報調整核心版本。"
);
geoRegistry.getRange("A4:I4").values = [["版本", "題組", "題數", "地區", "主要判讀", "能見度 / SOV", "自有引用 / 情緒", "狀態", "備註"]];
geoRegistry.getRange("A5:I10").values = [
  ["GEO-Core v1.0", "競品比較（正負面）", 6, "TW", "競品與情緒", "N/A", "情緒", "Frozen", "N/A 不等於 0"],
  ["GEO-Core v1.0", "SHOPLINE 品牌問題追蹤", 3, "TW", "品牌能見度與情緒", "Track", "Track", "Frozen", ""],
  ["GEO-Core v1.0", "想創業開店", 4, "TW", "需求與方案能見度", "Track", "Track", "Frozen", ""],
  ["GEO-Core v1.0", "正在選擇零售系統", 12, "TW", "選擇階段能見度", "Track", "Track", "Frozen", ""],
  ["GEO-Core v1.0", "尋找解決方案", 12, "TW", "方案需求能見度", "Track", "Track", "Frozen", ""],
  ["GEO-Core v1.0", "SHOPLINE 風險問題追蹤", 4, "TW", "風險與情緒", "N/A", "情緒", "Frozen", "N/A 不等於 0"],
];
headers(geoRegistry, "A4:I4");
tableStyle(geoRegistry, "A4:I10");
geoRegistry.tables.add("A4:I10", true, "GEOPromptRegistry");
geoRegistry.getRange("C5:C10").format.numberFormat = "0";
setWidths(geoRegistry, [150, 220, 75, 80, 190, 120, 140, 90, 210]);
geoRegistry.freezePanes.freezeRows(4);

// Crawl Runs
title(crawlRuns, "A1:N1", "Crawl Runs｜手動 Screaming Frog 證據紀錄");
subtitle(crawlRuns, "A2:N2", "週一 Lite、月報 Full、季報比較技術債。crawler 資料過期時報告照常產出，但必須標示 Stale。原始 crawl 檔與 CSV 不放入此 Sheet。"
);
crawlRuns.getRange("A4:N4").values = [["Crawl ID", "執行時間", "Crawl 類型", "範圍", "起始 URL / 設定版本", "狀態", "Raw crawl 檔連結", "CSV 連結", "Indexability", "5xx", "Canonical / noindex", "CWV / UX 摘要", "與前次差異", "備註"]];
headers(crawlRuns, "A4:N4");
crawlRuns.getRange("A5:N501").format = { wrapText: true, verticalAlignment: "top" };
crawlRuns.getRange("B5:B501").setNumberFormat("yyyy-mm-dd hh:mm");
applyListValidation(crawlRuns, "C5:C501", ["Weekly Lite", "Monthly Full", "Quarterly Comparison", "Manual rerun"]);
applyListValidation(crawlRuns, "D5:D501", ["Core SEO scope", "Conversion Watchlist", "Top 5 / P0-P1", "Separate HR funnel"]);
applyListValidation(crawlRuns, "F5:F501", ["Ready", "Stale", "Failed"]);
setWidths(crawlRuns, [135, 145, 135, 165, 220, 90, 220, 220, 115, 80, 150, 170, 180, 260]);
crawlRuns.freezePanes.freezeRows(4);

// Targets and baselines
title(targets, "A1:L1", "Targets & Baselines｜先建基準，再設定 SEO／GEO 目標");
subtitle(targets, "A2:L2", "商業 KPI 使用既有 Target；SEO／GEO 先以完整歷史建立基準，再於季報審視。初始基準：GSC／GA4／Salesforce 12 個完整月、WorkDuo 90 天、Screaming Frog 前次成功 crawl。"
);
targets.getRange("A4:L4").values = [["Setting ID", "Metric Group", "Metric", "Scope", "Direction", "Target Type", "Target Value", "Baseline Start", "Baseline End", "Authority", "Status", "Note"]];
targets.getRange("A5:L9").values = [
  ["BUS-001", "Business", "Non-paid Leads", "TW", "Higher", "Existing target", "", "", "", "Salesforce / Excel Actual", "Pending import", "由既有 Target 匯入"],
  ["BUS-002", "Business", "SQL", "TW", "Higher", "Existing target", "", "", "", "Salesforce / Excel Actual", "Pending import", "名單月份月結滿 60 天且 Ready 才納入正式 Target；依 Data Contract v1.0.0"],
  ["SEO-001", "SEO Visibility", "Google impressions / clicks", "Brand & non-brand", "Higher", "Baseline first", "", "", "", "GSC", "Pending baseline", "近 12 個完整月"],
  ["GEO-001", "GEO Visibility", "Platform visibility / SOV", "GEO-Core v1.0", "Higher", "Baseline first", "", "", "", "WorkDuo", "Pending baseline", "近 90 天；平台分開"],
  ["TECH-001", "Technical Searchability", "Indexability / critical issues", "Core SEO scope", "Mixed", "Baseline first", "", "", "", "Screaming Frog", "Pending baseline", "前次成功 Full crawl"],
];
headers(targets, "A4:L4");
tableStyle(targets, "A4:L9");
targets.tables.add("A4:L9", true, "TargetsBaselines");
targets.getRange("G5:G501").format.numberFormat = "#,##0.0";
targets.getRange("H5:I501").setNumberFormat("yyyy-mm-dd");
applyListValidation(targets, "B5:B501", ["Business", "SEO Visibility", "Google Experience", "Technical Searchability", "GEO Visibility"]);
applyListValidation(targets, "E5:E501", ["Higher", "Lower", "Mixed"]);
applyListValidation(targets, "F5:F501", ["Existing target", "Baseline first"]);
applyListValidation(targets, "K5:K501", ["Pending import", "Pending baseline", "Active", "Retired"]);
setWidths(targets, [105, 170, 190, 170, 90, 120, 100, 110, 110, 170, 120, 230]);
targets.freezePanes.freezeRows(4);

const checks = [
  ["Dashboard", "A1:J22"],
  ["README & 口徑", "A1:H25"],
  ["KPI Snapshots", "A1:R5"],
  ["KPI Snapshots v2", "A1:Y5"],
  ["Action Queue", "A1:T10"],
  ["URL Registry", "A1:J10"],
  ["GEO Prompt Registry", "A1:I10"],
  ["Targets & Baselines", "A1:L9"],
];

for (const [sheetName, range] of checks) {
  const check = await workbook.inspect({
    kind: "table",
    range: `${sheetName}!${range}`,
    include: "values,formulas",
    tableMaxRows: 30,
    tableMaxCols: 30,
  });
  console.log(check.ndjson);
}

const formulaErrors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "formula error scan",
});
console.log(formulaErrors.ndjson);

await fs.mkdir(outputDir, { recursive: true });
for (const [sheetName, range] of checks) {
  const preview = await workbook.render({ sheetName, range, scale: 1.2, autoCrop: "all", format: "png" });
  const safeName = sheetName.replace(/[^a-zA-Z0-9]+/g, "_");
  await fs.writeFile(`${outputDir}/${safeName}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
console.log(outputPath);
