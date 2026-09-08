/** 2026 年 8 月固定快照；MCP 查詢與報表驗證在產出時完成。 */
function doGet() {
  return HtmlService.createHtmlOutputFromFile("Report")
    .setTitle("SHOPLINE SEO／GEO 月報｜2026 年 8 月")
    .addMetaTag("viewport", "width=device-width, initial-scale=1");
}
