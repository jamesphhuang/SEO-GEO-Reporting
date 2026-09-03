function buildTechnicalSEOAgentSheet() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheets = {
    Config: [
      "site_url", "brand_name", "competitors", "target_country", "report_frequency", "timezone", "ga4_property_id", "gsc_property_url", "notes"
    ],
    GSC_raw: [
      "date", "page", "query", "clicks", "impressions", "ctr", "position", "country", "device"
    ],
    GA4_raw: [
      "date", "landing_page", "sessions", "engaged_sessions", "engagement_rate", "conversions", "revenue", "source_medium"
    ],
    Ahrefs_raw: [
      "date", "url", "keyword", "country", "volume", "kd", "position", "traffic", "backlinks", "ref_domains", "competitor_url", "content_gap_note"
    ],
    ScreamingFrog_raw: [
      "crawl_date", "url", "status_code", "indexability", "title", "meta_description", "h1", "canonical", "inlinks", "outlinks", "word_count", "depth", "issue_type"
    ],
    SEO_Actions: [
      "created_date", "priority", "category", "url", "query_or_keyword", "issue", "evidence", "recommendation", "expected_impact", "status", "owner", "due_date", "done_date", "result_note",
      "problem", "impact", "expected_outcome_range", "how_to", "priority_score", "business_impact", "traffic_opportunity", "conversion_relevance", "technical_risk", "effort", "confidence"
    ],
    Weekly_Report: [
      "week_start", "week_end", "summary", "top_opportunity", "top_risk", "organic_clicks_change", "organic_sessions_change", "conversions_change", "recommended_actions", "next_review_date",
      "競爭對手比較", "競品內容缺口", "競品AI搜尋觀察", "title", "executed_at", "data_quality", "gsc_summary", "ga4_summary", "ahrefs_summary", "screaming_frog_summary", "workduo_summary", "competitor_comparison", "status",
      "executive_summary", "keyword_cluster_summary", "search_performance_summary", "technical_seo_summary", "internal_linking_summary", "content_recommendation_summary", "competitor_ai_summary", "action_count", "p1_action_count", "validation_status"
    ],
    Data_Dictionary: [
      "sheet", "field", "description", "example"
    ]
  };

  Object.entries(sheets).forEach(([name, headers]) => {
    let sheet = ss.getSheetByName(name);
    if (!sheet) sheet = ss.insertSheet(name);
    sheet.clear();
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]);
    sheet.setFrozenRows(1);
    sheet.getRange(1, 1, 1, headers.length)
      .setFontWeight("bold")
      .setFontColor("#ffffff")
      .setBackground("#1f4e78")
      .setHorizontalAlignment("center");
    sheet.getRange(1, 1, Math.max(sheet.getMaxRows(), 50), headers.length).createFilter();
    headers.forEach((header, index) => {
      const width = ["summary", "top_opportunity", "top_risk", "recommended_actions", "recommendation", "evidence", "issue", "meta_description", "content_gap_note", "notes", "result_note", "problem", "impact", "expected_outcome_range", "how_to", "executive_summary", "keyword_cluster_summary", "search_performance_summary", "technical_seo_summary", "internal_linking_summary", "content_recommendation_summary", "competitor_ai_summary"].includes(header)
        ? 320
        : ["url", "page", "landing_page", "canonical", "competitor_url", "site_url", "gsc_property_url"].includes(header)
          ? 280
          : 140;
      sheet.setColumnWidth(index + 1, width);
    });
  });

  ss.getSheetByName("Config").getRange(2, 1, 1, 9).setValues([[
    "https://example.com", "Your Brand", "competitor1.com, competitor2.com, competitor3.com", "Taiwan", "weekly", "Asia/Taipei", "", "https://example.com/", "Fill this row first."
  ]]);

  const today = new Date();
  const lastWeek = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
  ss.getSheetByName("GSC_raw").getRange(2, 1, 1, 9).setValues([[
    lastWeek, "/pricing", "best crm software", 42, 4200, 0.01, 8.4, "TWN", "desktop"
  ]]);
  ss.getSheetByName("GA4_raw").getRange(2, 1, 1, 8).setValues([[
    lastWeek, "/pricing", 310, 198, 0.638, 7, 12000, "google / organic"
  ]]);
  ss.getSheetByName("Ahrefs_raw").getRange(2, 1, 1, 12).setValues([[
    lastWeek, "/pricing", "best crm software", "TW", 1200, 37, 8, 95, 42, 18, "competitor1.com/pricing", "Competitor has comparison FAQ and clearer pricing intent."
  ]]);
  ss.getSheetByName("ScreamingFrog_raw").getRange(2, 1, 1, 13).setValues([[
    lastWeek, "/pricing", 200, "Indexable", "Pricing | Your Brand", "Compare plans and pricing", "", "https://example.com/pricing", 34, 12, 980, 2, "Missing H1"
  ]]);
  ss.getSheetByName("SEO_Actions").getRange(2, 1, 1, 25).setValues([[
    today, "P1", "Content", "/pricing", "best crm software", "High impressions but low CTR and position outside top 5", "GSC: 4,200 impressions, 1.0% CTR, avg position 8.4", "Rewrite title/meta, add comparison FAQ, add 5 internal links from high-authority pages", "CTR +0.3-0.8pp", "open", "", new Date(today.getTime() + 14 * 24 * 60 * 60 * 1000), "", "",
    "High impressions but low CTR and rank outside top 5", "Commercial page is not capturing available demand", "CTR +0.3-0.8pp", "Rewrite title/meta, add comparison FAQ, and add 5 internal links from high-authority pages", 13, 4, 4, 4, 3, 2, "high"
  ]]);
  ss.getSheetByName("Weekly_Report").getRange(2, 1, 1, 33).setValues([[
    lastWeek, today, "Organic visibility has a clear opportunity on high-intent commercial pages.", "/pricing: high impressions and ranking 4-15 range.", "Technical issue: Missing H1 found on commercial page.", "=SUM(GSC_raw!D:D)", "=SUM(GA4_raw!C:C)", "=SUM(GA4_raw!F:F)", "Prioritize P1 actions in SEO_Actions.", new Date(today.getTime() + 7 * 24 * 60 * 60 * 1000),
    "Competitors have stronger pricing comparison content.", "Missing comparison FAQ and internal links.", "AI citation data pending.", "High-intent commercial pages need CTR and content depth improvements", today, "Template data only; MCP-first run required.", "GSC sample: pricing page has high impressions and low CTR.", "GA4 sample: organic sessions and conversions should be checked.", "Ahrefs sample: competitor has comparison FAQ.", "Screaming Frog sample: Missing H1.", "Workduo pending.", "Competitor comparison should be populated by Ahrefs and Workduo.", "manual_template",
    "Largest issue: high-intent pages are visible but under-clicked; largest opportunity: commercial CTR; largest risk: technical quality on money pages; actions: 1 P1.", "Top organic/non-brand/rising/declining/long-tail queries should be clustered by intent.", "Use GSC for CTR/ranking gaps and GA4 for sessions/users/keyEvents.", "Separate speed, indexability, canonical/noindex, duplicates, broken links, schema/hreflang/sitemap.", "Add outbound and inbound links for commercial ranking opportunities.", "Classify recommendations as refresh, expand, consolidate, split, prune/noindex.", "Compare Ahrefs competitor gaps and Workduo AI citation share.", 1, 1, "warning"
  ]]);

  const actionSheet = ss.getSheetByName("SEO_Actions");
  actionSheet.getRange("B2:B500").setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(["P1", "P2", "P3"]).build());
  actionSheet.getRange("C2:C500").setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(["Technical SEO", "Content", "Internal Linking", "Keyword Research", "Topic Cluster", "Competitor", "AI Search / GEO", "Reporting"]).build());
  actionSheet.getRange("J2:J500").setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(["open", "in_progress", "blocked", "done", "parked"]).build());
  actionSheet.getRange("Y2:Y500").setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(["high", "medium", "low"]).build());

  ss.setActiveSheet(ss.getSheetByName("Config"));
}
