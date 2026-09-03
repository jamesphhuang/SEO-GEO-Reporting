const SEO_REPORT_SPREADSHEET_ID_V2 = "1YdB3R1JmLjIH1fRhFg1r0fei887sbtVopkBnWbFWCi0";

function applySeoReportFormatV2() {
  const ss = getSeoReportSpreadsheetV2_();
  ss.setSpreadsheetTimeZone("Asia/Taipei");

  const weeklyHeaders = [
    "executive_summary",
    "keyword_cluster_summary",
    "search_performance_summary",
    "technical_seo_summary",
    "internal_linking_summary",
    "content_recommendation_summary",
    "competitor_ai_summary",
    "action_count",
    "p1_action_count",
    "validation_status"
  ];

  const actionHeaders = [
    "problem",
    "impact",
    "expected_outcome_range",
    "how_to",
    "priority_score",
    "business_impact",
    "traffic_opportunity",
    "conversion_relevance",
    "technical_risk",
    "effort",
    "confidence"
  ];

  const evidenceHeaders = [
    "expected_outcome_range",
    "module",
    "priority_score"
  ];

  appendMissingHeaders_("Weekly_Report", weeklyHeaders);
  appendMissingHeaders_("SEO_Actions", actionHeaders);
  appendMissingHeaders_("Insight_Evidence", evidenceHeaders);
  buildReportFormatGuide_();
  applySeoReportValidations_();
  refreshDashboardV2_();
}

function appendMissingHeaders_(sheetName, requiredHeaders) {
  const ss = getSeoReportSpreadsheetV2_();
  let sheet = ss.getSheetByName(sheetName);
  if (!sheet) sheet = ss.insertSheet(sheetName);

  if (sheet.getMaxRows() < 1000) {
    sheet.insertRowsAfter(sheet.getMaxRows(), 1000 - sheet.getMaxRows());
  }

  const lastColumn = Math.max(sheet.getLastColumn(), 1);
  const currentHeaders = sheet.getRange(1, 1, 1, lastColumn).getValues()[0].filter(String);
  const missingHeaders = requiredHeaders.filter(header => currentHeaders.indexOf(header) === -1);
  if (!missingHeaders.length) return;

  const startColumn = currentHeaders.length + 1;
  if (sheet.getMaxColumns() < startColumn + missingHeaders.length - 1) {
    sheet.insertColumnsAfter(sheet.getMaxColumns(), startColumn + missingHeaders.length - 1 - sheet.getMaxColumns());
  }
  sheet.getRange(1, startColumn, 1, missingHeaders.length).setValues([missingHeaders]);
  styleHeaderV2_(sheet.getRange(1, startColumn, 1, missingHeaders.length));
  sheet.setFrozenRows(1);
  autoSizeV2_(sheet, startColumn, missingHeaders.length);
}

function buildReportFormatGuide_() {
  const ss = getSeoReportSpreadsheetV2_();
  const sheet = ensureSheetV2_("Report_Format_Guide", 7, 200, 12, "#7030a0");
  sheet.clear();
  sheet.setHiddenGridlines(true);
  sheet.getRange("A1:L1").merge().setValue("SEO 週報 V2 格式與品質規則");
  styleTitleV2_(sheet.getRange("A1:L1"));
  sheet.getRange("A2:L2").merge().setValue(
    "每週輸出 1 筆 Weekly_Report、5-10 筆 Insight_Evidence、10-15 筆 SEO_Actions；不匯入大量 raw data。每個 action 必須回答：問題、影響、預計成果、怎麼做。"
  );
  styleNoteV2_(sheet.getRange("A2:L2"));

  sheet.getRange("A4:F4").setValues([["module_order", "module", "required_output", "primary_tools", "quality_rule", "sheet_field"]]);
  styleHeaderV2_(sheet.getRange("A4:F4"));
  sheet.getRange("A5:F12").setValues([
    [1, "Executive Summary", "最大問題、最大機會、最大風險、P1/P2/P3 數量", "All MCPs", "2 分鐘內可讀完", "executive_summary"],
    [2, "Keyword Research & Topic Clusters", "Top organic、non-brand、rising、declining、long-tail、intent、topic cluster", "GSC, Ahrefs", "避免品牌詞淹沒非品牌機會", "keyword_cluster_summary"],
    [3, "Search Performance", "低 CTR、高曝光、position 4-20、下滑頁、GA4 organic sessions/users/keyEvents", "GSC, GA4", "必須含 Organic Search keyEvents", "search_performance_summary"],
    [4, "Technical SEO Audit", "Core Web Vitals、indexability、robots/noindex/canonical、duplicates、404、schema/hreflang/sitemap", "Screaming Frog, Ahrefs", "每個 issue 要有 affected count 與 sample URLs", "technical_seo_summary"],
    [5, "Internal Linking Recommendations", "新頁 outbound、舊頁 inbound、hub page、orphan/weak pages", "GSC, Ahrefs, Screaming Frog", "優先商業價值高且排名 4-20 的頁面", "internal_linking_summary"],
    [6, "Content Refresh / Page Recommendations", "refresh、expand、consolidate、split、prune/noindex", "GSC, GA4, Ahrefs", "每項綁定目標 query cluster", "content_recommendation_summary"],
    [7, "Competitor & AI Search Visibility", "競品 top pages/keywords/content gap/backlinks、AI citation share/visibility", "Ahrefs, Workduo", "每週至少 3 個競品可借鏡內容角度", "competitor_ai_summary"],
    [8, "Prioritized Action Plan", "10-15 個 action；P1 不超過 5 個", "All MCPs", "每項必須有問題、影響、預計成果、怎麼做", "recommended_actions"]
  ]);

  sheet.getRange("H4:L4").setValues([["priority", "score_rule", "meaning", "expected_count", "notes"]]);
  styleHeaderV2_(sheet.getRange("H4:L4"));
  sheet.getRange("H5:L7").setValues([
    ["P1", "score >= 12 且影響 conversion/indexing/核心商業頁/大量 URL", "本週必做", "0-5", "P1 不超過 5 項"],
    ["P2", "score 8-11", "有明確 SEO 成長空間", "5-10", "排入近期 backlog"],
    ["P3", "score <= 7", "低優先或待觀察", "0-5", "通常不進主週報"]
  ]);

  sheet.getRange("A15:G15").setValues([["field", "business_impact", "traffic_opportunity", "conversion_relevance", "technical_risk", "effort", "priority_score"]]);
  styleHeaderV2_(sheet.getRange("A15:G15"));
  sheet.getRange("A16:G16").setValues([["scoring_formula", "1-5", "1-5", "1-5", "1-5", "1-5", "business_impact + traffic_opportunity + conversion_relevance + technical_risk - effort"]]);

  sheet.getRange("A18:E18").setValues([["required_action_fields", "problem", "impact", "expected_outcome_range", "how_to"]]);
  styleHeaderV2_(sheet.getRange("A18:E18"));
  sheet.getRange("A19:D23").setValues([
    ["CTR opportunity", "高曝光低 CTR", "現有排名沒有轉成 clicks", "CTR +0.3-0.8pp"],
    ["Organic growth", "排名 4-20 或內容缺口", "可提升 sessions 與商業流量", "Organic sessions +5-10%"],
    ["Conversion", "Organic landing page keyEvents 偏低", "SEO 流量未轉成 lead/purchase", "Key events +3-8%"],
    ["Indexability", "noindex/canonical/sitemap/robots 問題", "重要頁可能無法收錄或訊號分散", "Indexable pages +10-20"],
    ["Broken links", "404 或內外部失效連結", "降低使用者體驗與 crawl 效率", "Broken links -80-100%"]
  ]);

  sheet.getRange("A5:L23").setWrap(true);
  sheet.setFrozenRows(4);
  autoSizeV2_(sheet, 1, 12);
}

function applySeoReportValidations_() {
  const ss = getSeoReportSpreadsheetV2_();
  const actions = ss.getSheetByName("SEO_Actions");
  if (actions) {
    const headers = getHeaders_(actions);
    setValidationByHeader_(actions, headers, "priority", ["P1", "P2", "P3"]);
    setValidationByHeader_(actions, headers, "category", ["Technical SEO", "Content", "Internal Linking", "Keyword Research", "Topic Cluster", "Competitor", "AI Search / GEO", "Reporting"]);
    setValidationByHeader_(actions, headers, "status", ["open", "in_progress", "blocked", "done", "parked"]);
    setValidationByHeader_(actions, headers, "confidence", ["high", "medium", "low"]);
    ["business_impact", "traffic_opportunity", "conversion_relevance", "technical_risk", "effort", "priority_score"].forEach(header => {
      const index = headers.indexOf(header);
      if (index !== -1) actions.getRange(2, index + 1, 999, 1).setNumberFormat("0");
    });
  }

  const evidence = ss.getSheetByName("Insight_Evidence");
  if (evidence) {
    const headers = getHeaders_(evidence);
    setValidationByHeader_(evidence, headers, "confidence", ["high", "medium", "low"]);
    setValidationByHeader_(evidence, headers, "module", [
      "Executive Summary",
      "Keyword Research & Topic Clusters",
      "Search Performance",
      "Technical SEO Audit",
      "Internal Linking Recommendations",
      "Content Refresh / Page Recommendations",
      "Competitor & AI Search Visibility",
      "Prioritized Action Plan"
    ]);
  }

  const weekly = ss.getSheetByName("Weekly_Report");
  if (weekly) {
    const headers = getHeaders_(weekly);
    setValidationByHeader_(weekly, headers, "validation_status", ["pass", "warning", "fail"]);
    setValidationByHeader_(weekly, headers, "status", ["manual_test_completed", "completed", "needs_review", "blocked"]);
  }
}

function refreshDashboardV2_() {
  const ss = getSeoReportSpreadsheetV2_();
  const sheet = ss.getSheetByName("Dashboard");
  if (!sheet) return;
  sheet.getRange("A16:C16").setValues([["報告格式", "V2 action completeness", '=COUNTIFS(SEO_Actions!O:O,"<>",SEO_Actions!P:P,"<>",SEO_Actions!Q:Q,"<>",SEO_Actions!R:R,"<>")']]);
  sheet.getRange("A17:C17").setValues([["報告格式", "本週 P1 上限檢查", '=IF(COUNTIF(SEO_Actions!B:B,"P1")<=5,"OK","P1 超過 5 項")']]);
  sheet.getRange("A18:C18").setValues([["報告格式", "格式說明", "請看 Report_Format_Guide 分頁"]]);
  sheet.getRange("A16:C18").setWrap(true).setBackground("#f3e8ff");
  autoSizeV2_(sheet, 1, 3);
}

function getHeaders_(sheet) {
  return sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
}

function setValidationByHeader_(sheet, headers, header, values) {
  const index = headers.indexOf(header);
  if (index === -1) return;
  sheet.getRange(2, index + 1, Math.max(sheet.getMaxRows() - 1, 1), 1).setDataValidation(
    SpreadsheetApp.newDataValidation()
      .requireValueInList(values)
      .setAllowInvalid(true)
      .build()
  );
}

function ensureSheetV2_(name, index, rows, cols, tabColor) {
  const ss = getSeoReportSpreadsheetV2_();
  let sheet = ss.getSheetByName(name);
  if (!sheet) {
    sheet = ss.insertSheet(name, Math.min(index, ss.getNumSheets()));
  }
  sheet.setTabColor(tabColor);
  if (sheet.getMaxRows() < rows) sheet.insertRowsAfter(sheet.getMaxRows(), rows - sheet.getMaxRows());
  if (sheet.getMaxColumns() < cols) sheet.insertColumnsAfter(sheet.getMaxColumns(), cols - sheet.getMaxColumns());
  return sheet;
}

function getSeoReportSpreadsheetV2_() {
  return SpreadsheetApp.openById(SEO_REPORT_SPREADSHEET_ID_V2);
}

function styleTitleV2_(range) {
  range
    .setBackground("#1f4e78")
    .setFontColor("#ffffff")
    .setFontWeight("bold")
    .setFontSize(16)
    .setVerticalAlignment("middle");
}

function styleHeaderV2_(range) {
  range
    .setBackground("#244062")
    .setFontColor("#ffffff")
    .setFontWeight("bold")
    .setWrap(true)
    .setVerticalAlignment("middle");
}

function styleNoteV2_(range) {
  range
    .setBackground("#f8fafc")
    .setFontColor("#334155")
    .setWrap(true);
}

function autoSizeV2_(sheet, startColumn, numColumns) {
  for (let col = startColumn; col < startColumn + numColumns; col++) {
    sheet.autoResizeColumn(col);
    const width = Math.min(Math.max(sheet.getColumnWidth(col), 120), 440);
    sheet.setColumnWidth(col, width);
  }
}
