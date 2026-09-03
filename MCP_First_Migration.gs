function migrateToMcpFirst() {
  const ss = SpreadsheetApp.getActive();
  ss.setSpreadsheetTimeZone("Asia/Taipei");

  buildMcpDashboard_(ss);
  buildMcpConfig_(ss);
  buildMcpRunLog_(ss);
  buildInsightEvidence_(ss);
  annotateWeeklyReport_(ss);
  annotateSeoActions_(ss);
  if (typeof applySeoReportFormatV2 === "function") {
    applySeoReportFormatV2();
  }
  markLegacyRawTabs_(ss);
}

function buildMcpDashboard_(ss) {
  const sheet = ensureSheet_("Dashboard", 0, 200, 12, "#1f4e78");
  sheet.clear();
  sheet.setHiddenGridlines(true);
  sheet.getRange("A1:H1").merge().setValue("SEO MCP 資料中心");
  sheet.getRange("A2:H2").merge().setValue(
    "MCP 即時查詢 + Sheets 策略紀錄；raw tabs 保留為 Legacy，不再作為主要分析來源。"
  );

  sheet.getRange("A4:C4").setValues([["區塊", "指標", "公式 / 說明"]]);
  sheet.getRange("A5:C8").setValues([
    ["最新週報", "最新標題", '=IFERROR(INDEX(Weekly_Report!N1:N1000,MAX(FILTER(ROW(Weekly_Report!A1:A1000),Weekly_Report!A1:A1000<>""))),"尚無週報")'],
    ["最新週報", "最新狀態", '=IFERROR(INDEX(Weekly_Report!W1:W1000,MAX(FILTER(ROW(Weekly_Report!A1:A1000),Weekly_Report!A1:A1000<>""))),"待建立")'],
    ["執行追蹤", "待追蹤 Actions", '=COUNTIF(SEO_Actions!J:J,"To do")+COUNTIF(SEO_Actions!J:J,"In progress")+COUNTIF(SEO_Actions!J:J,"待追蹤")'],
    ["執行追蹤", "近 30 天 MCP runs", '=COUNTIF(MCP_Run_Log!B:B,">="&TODAY()-30)']
  ]);

  sheet.getRange("A10:C10").setValues([["推薦工作流", "資料展示方式", "使用說明"]]);
  sheet.getRange("A11:C14").setValues([
    ["1", "Weekly_Report", "一週一列，保存管理摘要、機會、風險、策略建議。"],
    ["2", "SEO_Actions", "只放可執行任務，追蹤 priority、owner、status、due date。"],
    ["3", "Insight_Evidence", "保存摘要證據，不保存大量 raw rows。"],
    ["4", "MCP_Run_Log", "記錄每次 MCP 查詢來源、範圍、limit、狀態。"]
  ]);

  styleTitle_(sheet.getRange("A1:H1"));
  styleNote_(sheet.getRange("A2:H2"));
  styleHeader_(sheet.getRange("A4:C4"));
  styleHeader_(sheet.getRange("A10:C10"));
  sheet.getRange("A5:C8").setBackground("#eaf2f8");
  sheet.getRange("A11:C14").setWrap(true);
  sheet.setFrozenRows(2);
  autoSize_(sheet, 1, 8);
}

function buildMcpConfig_(ss) {
  const headers = ["category", "config_key", "value", "required", "example", "purpose", "status", "notes"];
  const rows = [
    ["basic", "site_url", "", "yes", "https://example.com/", "主站 URL，所有資料源對齊用", "待填", ""],
    ["basic", "brand_name", "", "yes", "Your Brand", "品牌名稱與報告標題", "待填", ""],
    ["basic", "competitors", "", "recommended", "competitor1.com, competitor2.com", "競品 gap / GEO 對照", "待填", "逗號分隔"],
    ["basic", "target_country", "", "yes", "TW", "GSC / Ahrefs / Workduo 國家篩選", "待填", "依工具格式調整"],
    ["basic", "timezone", "Asia/Taipei", "yes", "Asia/Taipei", "週期計算", "已填", ""],
    ["gsc", "gsc_property_url", "", "yes", "https://example.com/ 或 sc-domain:example.com", "Search Console property", "待填", ""],
    ["gsc", "gsc_project_id_or_portfolio_id", "", "tool-dependent", "123456", "MCP 專案識別", "待填", "Ahrefs GSC 需要 project_id"],
    ["ga4", "ga4_property_id", "", "yes", "123456789", "GA4 property", "待填", "只填 ID，不填 secret"],
    ["ga4", "key_events", "", "recommended", "generate_lead,purchase", "轉換成效判讀", "待填", "逗號分隔"],
    ["ga4", "organic_channel_name", "Organic Search", "recommended", "Organic Search", "自然搜尋流量篩選", "已填", ""],
    ["ahrefs", "ahrefs_project_id", "", "yes", "123456", "Ahrefs project", "待填", ""],
    ["ahrefs", "ahrefs_target", "", "yes", "example.com", "Site Explorer target", "待填", "domain 建議 mode=subdomains"],
    ["ahrefs", "ahrefs_country", "", "yes", "tw", "Ahrefs 關鍵字 / 流量國家", "待填", ""],
    ["screaming_frog", "crawl_project_id_or_crawl_id", "", "yes", "sf-project-001", "最新 crawl / issue 查詢", "待填", "若無獨立 MCP，可先用 Ahrefs Site Audit"],
    ["workduo", "workspaceId", "", "tool-dependent", "workspace_xxx", "Workduo workspace", "待填", ""],
    ["workduo", "projectId", "", "yes", "project_xxx", "AI 搜尋監測專案", "待填", ""],
    ["workduo", "platforms", "", "recommended", "chatgpt,perplexity,gemini", "AI 平台篩選", "待填", "逗號分隔"],
    ["workduo", "queryCountries", "", "recommended", "TW,US", "AI 查詢國家", "待填", "ISO 2 碼，逗號分隔"]
  ];

  const sheet = ensureSheet_("MCP_Config", 1, 200, 10, "#1f4e78");
  const existingByKey = readExistingMcpConfig_(sheet);
  const mergedRows = rows.map(row => mergeMcpConfigRow_(row, existingByKey[row[1]]));
  sheet.clear();
  sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  sheet.getRange(2, 1, mergedRows.length, headers.length).setValues(mergedRows);
  styleHeader_(sheet.getRange(1, 1, 1, headers.length));
  const existingFilter = sheet.getFilter();
  if (existingFilter) existingFilter.remove();
  sheet.getRange(1, 1, rows.length + 1, headers.length).createFilter();
  sheet.getRange("G2:G200").setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(["待填", "已填", "待測試", "已串接", "暫不用"])
      .build()
  );
  sheet.setFrozenRows(1);
  autoSize_(sheet, 1, headers.length);
}

function readExistingMcpConfig_(sheet) {
  const existingByKey = {};
  if (!sheet || sheet.getLastRow() < 2 || sheet.getLastColumn() < 2) return existingByKey;

  const headers = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  const keyIndex = headers.indexOf("config_key");
  if (keyIndex === -1) return existingByKey;

  const fieldIndexes = {
    value: headers.indexOf("value"),
    status: headers.indexOf("status"),
    notes: headers.indexOf("notes")
  };
  const values = sheet.getRange(2, 1, sheet.getLastRow() - 1, sheet.getLastColumn()).getValues();
  values.forEach(row => {
    const key = row[keyIndex];
    if (!key) return;
    existingByKey[key] = {};
    Object.keys(fieldIndexes).forEach(field => {
      const index = fieldIndexes[field];
      if (index !== -1 && row[index] !== "") existingByKey[key][field] = row[index];
    });
  });
  return existingByKey;
}

function mergeMcpConfigRow_(templateRow, existing) {
  if (!existing) return templateRow;
  const row = templateRow.slice();
  [
    [2, "value"],
    [6, "status"],
    [7, "notes"]
  ].forEach(([index, field]) => {
    if (Object.prototype.hasOwnProperty.call(existing, field)) {
      row[index] = existing[field];
    }
  });
  return row;
}

function buildMcpRunLog_(ss) {
  const headers = [
    "run_id", "run_datetime", "period_start", "period_end", "source_tool",
    "query_type", "query_summary", "limit", "status", "rows_returned", "error_or_note"
  ];
  const sheet = ensureSheet_("MCP_Run_Log", 2, 1000, 12, "#1f4e78");
  if (sheet.getLastRow() === 0 || !sheet.getRange("A1").getValue()) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  }
  styleHeader_(sheet.getRange(1, 1, 1, headers.length));
  sheet.getRange("B:B").setNumberFormat("yyyy-mm-dd hh:mm");
  sheet.getRange("C:D").setNumberFormat("yyyy-mm-dd");
  sheet.setFrozenRows(1);
  autoSize_(sheet, 1, headers.length);
}

function buildInsightEvidence_(ss) {
  const headers = [
    "run_id", "evidence_id", "source_tool", "insight_type", "page_url",
    "keyword_or_topic", "metric_summary", "comparison", "source_query",
    "confidence", "action_ref", "created_at"
  ];
  const sheet = ensureSheet_("Insight_Evidence", 3, 1000, 14, "#1f4e78");
  if (sheet.getLastRow() === 0 || !sheet.getRange("A1").getValue()) {
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
  }
  styleHeader_(sheet.getRange(1, 1, 1, headers.length));
  sheet.getRange("L:L").setNumberFormat("yyyy-mm-dd hh:mm");
  sheet.setFrozenRows(1);
  autoSize_(sheet, 1, headers.length);
}

function annotateWeeklyReport_(ss) {
  const sheet = ss.getSheetByName("Weekly_Report");
  if (!sheet) return;
  sheet.setTabColor("#2f75b5");
  sheet.getRange("A1").setNote(
    "MCP-first output: 每週只新增策略摘要，不匯入 raw data。若欄位不足，可新增摘要、機會、風險、策略建議、資料來源欄。"
  );
}

function annotateSeoActions_(ss) {
  const sheet = ss.getSheetByName("SEO_Actions");
  if (!sheet) return;
  sheet.setTabColor("#70ad47");
  sheet.getRange("A1").setNote(
    "MCP-first action layer: 只放可執行任務與追蹤狀態，避免塞入大批資料列。"
  );
}

function markLegacyRawTabs_(ss) {
  ["GSC_raw", "GA4_raw", "Ahrefs_raw", "ScreamingFrog_raw", "Ahrefs_domain_rating", "Ahrefs_top_pages"].forEach(name => {
    const sheet = ss.getSheetByName(name);
    if (!sheet) return;
    sheet.setTabColor("#a6a6a6");
    sheet.getRange("A1").setNote(
      "Legacy raw-data tab: 已保留歷史資料，但 MCP-first automation 不應大量讀取此分頁。"
    );
  });
}

function ensureSheet_(name, index, rows, cols, tabColor) {
  const ss = SpreadsheetApp.getActive();
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name, index);
  }
  sheet.setTabColor(tabColor);
  if (sheet.getMaxRows() < rows) sheet.insertRowsAfter(sheet.getMaxRows(), rows - sheet.getMaxRows());
  if (sheet.getMaxColumns() < cols) sheet.insertColumnsAfter(sheet.getMaxColumns(), cols - sheet.getMaxColumns());
  return sheet;
}

function styleTitle_(range) {
  range
    .setBackground("#1f4e78")
    .setFontColor("#ffffff")
    .setFontWeight("bold")
    .setFontSize(16)
    .setVerticalAlignment("middle");
}

function styleHeader_(range) {
  range
    .setBackground("#244062")
    .setFontColor("#ffffff")
    .setFontWeight("bold")
    .setWrap(true)
    .setVerticalAlignment("middle");
}

function styleNote_(range) {
  range
    .setBackground("#f8fafc")
    .setFontColor("#334155")
    .setWrap(true);
}

function autoSize_(sheet, startColumn, numColumns) {
  for (let col = startColumn; col < startColumn + numColumns; col++) {
    sheet.autoResizeColumn(col);
    const width = Math.min(Math.max(sheet.getColumnWidth(col), 120), 420);
    sheet.setColumnWidth(col, width);
  }
}
