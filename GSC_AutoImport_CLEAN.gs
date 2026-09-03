const GSC_SHEET_NAME = "GSC_raw";
const CONFIG_SHEET_NAME = "Config";

const GSC_HEADERS = [
  "date",
  "page",
  "query",
  "clicks",
  "impressions",
  "ctr",
  "position",
  "country",
  "device",
  "site_url",
  "gsc_property_url"
];

function checkGSCImporterVersion() {
  Logger.log("GSC importer version: multi-property-clean-v1");
  Logger.log(`Expected GSC_raw columns: ${GSC_HEADERS.join(", ")}`);
  SpreadsheetApp.getActive().toast("GSC importer version: multi-property-clean-v1", "Technical SEO Agent", 8);
}

function importGSCRecent() {
  const configs = getConfigRows_();
  const timezone = configs[0].timezone || Session.getScriptTimeZone() || "Asia/Taipei";
  const today = new Date();
  const startDate = formatDate_(addDays_(today, -10), timezone);
  const endDate = formatDate_(addDays_(today, -3), timezone);
  importGSCDateRange(startDate, endDate);
}

function importGSCDateRange(startDate, endDate) {
  const configs = getConfigRows_();
  ensureGscSheet_();

  const rows = [];
  configs.forEach(config => {
    const propertyUrl = normalizeGscPropertyUrl_(config.gsc_property_url, config.site_url);
    const siteRows = fetchGscRows_(propertyUrl, startDate, endDate, config.site_url);
    rows.push(...siteRows);
  });

  replaceGscRowsByDateRange_(startDate, endDate, rows);

  SpreadsheetApp.getActive().toast(
    `GSC import completed: ${configs.length} properties, ${rows.length} rows`,
    "Technical SEO Agent",
    8
  );
}

function testGSCConnection() {
  const configs = getConfigRows_();
  testOneGSCConnection_(configs[0]);
  SpreadsheetApp.getActive().toast("GSC connection OK", "Technical SEO Agent", 8);
}

function testAllGSCConnections() {
  const configs = getConfigRows_();
  configs.forEach(config => testOneGSCConnection_(config));
  SpreadsheetApp.getActive().toast(`GSC connection OK for ${configs.length} properties`, "Technical SEO Agent", 8);
}

function upgradeGscRawSchema() {
  ensureGscSheet_();
  backfillGscPropertyColumns_();
  SpreadsheetApp.getActive().toast("GSC_raw schema upgraded", "Technical SEO Agent", 8);
}

function installDailyGSCImportTrigger() {
  removeGSCImportTriggers();
  ScriptApp.newTrigger("importGSCRecent")
    .timeBased()
    .everyDays(1)
    .atHour(7)
    .create();
  SpreadsheetApp.getActive().toast("Daily GSC import trigger installed", "Technical SEO Agent", 8);
}

function removeGSCImportTriggers() {
  ScriptApp.getProjectTriggers()
    .filter(trigger => trigger.getHandlerFunction() === "importGSCRecent")
    .forEach(trigger => ScriptApp.deleteTrigger(trigger));
}

function testOneGSCConnection_(config) {
  const propertyUrl = normalizeGscPropertyUrl_(config.gsc_property_url, config.site_url);
  const timezone = config.timezone || Session.getScriptTimeZone() || "Asia/Taipei";
  const today = new Date();
  const startDate = formatDate_(addDays_(today, -10), timezone);
  const endDate = formatDate_(addDays_(today, -3), timezone);
  const url = `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(propertyUrl)}/searchAnalytics/query`;
  const payload = {
    startDate,
    endDate,
    dimensions: ["date"],
    rowLimit: 1
  };

  const json = callGscApi_(url, payload, `GSC API test failed for ${propertyUrl}`);
  Logger.log(`${propertyUrl}: ${JSON.stringify(json)}`);
}

function fetchGscRows_(propertyUrl, startDate, endDate, sourceSiteUrl) {
  const url = `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(propertyUrl)}/searchAnalytics/query`;
  const rowLimit = 25000;
  let startRow = 0;
  let hasMoreRows = true;
  const output = [];

  while (hasMoreRows) {
    const payload = {
      startDate,
      endDate,
      dimensions: ["date", "page", "query", "country", "device"],
      rowLimit,
      startRow
    };

    const json = callGscApi_(url, payload, `GSC API request failed for ${propertyUrl}`);
    const rows = json.rows || [];

    rows.forEach(row => {
      const keys = row.keys || [];
      output.push([
        keys[0] || "",
        keys[1] || "",
        keys[2] || "",
        row.clicks || 0,
        row.impressions || 0,
        row.ctr || 0,
        row.position || 0,
        keys[3] || "",
        keys[4] || "",
        sourceSiteUrl || "",
        propertyUrl
      ]);
    });

    hasMoreRows = rows.length === rowLimit;
    startRow += rowLimit;
  }

  return output;
}

function callGscApi_(url, payload, errorPrefix) {
  const response = UrlFetchApp.fetch(url, {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: `Bearer ${ScriptApp.getOAuthToken()}`
    },
    payload: JSON.stringify(payload),
    muteHttpExceptions: true
  });

  const status = response.getResponseCode();
  const body = response.getContentText();

  if (status < 200 || status >= 300) {
    throw new Error(`${errorPrefix} (${status}): ${body}`);
  }

  return JSON.parse(body);
}

function replaceGscRowsByDateRange_(startDate, endDate, newRows) {
  const sheet = SpreadsheetApp.getActive().getSheetByName(GSC_SHEET_NAME);
  const lastRow = sheet.getLastRow();
  const lastColumn = GSC_HEADERS.length;
  const keptRows = [];

  if (lastRow > 1) {
    const existingRows = sheet.getRange(2, 1, lastRow - 1, lastColumn).getValues();
    existingRows.forEach(row => {
      const rowDate = normalizeDateValue_(row[0]);
      if (!rowDate || rowDate < startDate || rowDate > endDate) {
        keptRows.push(row);
      }
    });
    sheet.getRange(2, 1, lastRow - 1, lastColumn).clearContent();
  }

  const allRows = keptRows.concat(newRows);
  allRows.sort((a, b) => {
    const byDate = String(a[0]).localeCompare(String(b[0]));
    if (byDate !== 0) return byDate;
    const bySite = String(a[9]).localeCompare(String(b[9]));
    if (bySite !== 0) return bySite;
    const byPage = String(a[1]).localeCompare(String(b[1]));
    if (byPage !== 0) return byPage;
    return String(a[2]).localeCompare(String(b[2]));
  });

  if (allRows.length) {
    sheet.getRange(2, 1, allRows.length, lastColumn).setValues(allRows);
  }

  sheet.getRange("A:A").setNumberFormat("yyyy-mm-dd");
  sheet.getRange("F:F").setNumberFormat("0.00%");
  sheet.autoResizeColumns(1, lastColumn);
}

function ensureGscSheet_() {
  const ss = SpreadsheetApp.getActive();
  let sheet = ss.getSheetByName(GSC_SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(GSC_SHEET_NAME);

  sheet.getRange(1, 1, 1, GSC_HEADERS.length).setValues([GSC_HEADERS]);
  sheet.setFrozenRows(1);
  sheet.getRange(1, 1, 1, GSC_HEADERS.length)
    .setFontWeight("bold")
    .setFontColor("#ffffff")
    .setBackground("#1f4e78")
    .setHorizontalAlignment("center");
}

function backfillGscPropertyColumns_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(GSC_SHEET_NAME);
  const configs = getConfigRows_();
  const lastRow = sheet.getLastRow();
  const siteUrlColumn = GSC_HEADERS.indexOf("site_url") + 1;
  const propertyColumn = GSC_HEADERS.indexOf("gsc_property_url") + 1;

  if (lastRow < 2) return;

  const pageValues = sheet.getRange(2, 2, lastRow - 1, 1).getValues();
  const output = pageValues.map(([page]) => {
    const pageUrl = String(page || "");
    const matchedConfig = configs.find(config => {
      const site = String(config.site_url || "").trim();
      return site && pageUrl.startsWith(site);
    }) || configs[0];
    const property = normalizeGscPropertyUrl_(matchedConfig.gsc_property_url, matchedConfig.site_url);
    return [matchedConfig.site_url || "", property];
  });

  sheet.getRange(2, siteUrlColumn, output.length, 2).setValues(output);
}

function getConfigRows_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(CONFIG_SHEET_NAME);
  if (!sheet) throw new Error("Config sheet not found.");

  const lastRow = sheet.getLastRow();
  const lastColumn = sheet.getLastColumn();
  if (lastRow < 2) throw new Error("Please fill at least one Config row.");

  const headers = sheet.getRange(1, 1, 1, lastColumn).getValues()[0].map(header => String(header).trim());
  const values = sheet.getRange(2, 1, lastRow - 1, lastColumn).getValues();
  const configs = values
    .map(row => {
      const config = {};
      headers.forEach((header, index) => {
        if (header) config[header] = row[index];
      });
      return config;
    })
    .filter(config => config.site_url || config.gsc_property_url);

  if (!configs.length) {
    throw new Error("Please fill Config!site_url or Config!gsc_property_url first.");
  }

  return configs;
}

function normalizeGscPropertyUrl_(gscPropertyUrl, siteUrl) {
  const property = String(gscPropertyUrl || "").trim();
  const site = String(siteUrl || "").trim();

  if (!property && !site) return "";
  if (property.startsWith("http://") || property.startsWith("https://") || property.startsWith("sc-domain:")) {
    return property;
  }
  if (!property) return site;

  if (site.startsWith("http://") || site.startsWith("https://")) {
    const propertyHost = property.replace(/^\/+|\/+$/g, "");
    const siteHost = site.replace(/^https?:\/\//, "").replace(/^\/+|\/+$/g, "");
    if (propertyHost === siteHost) return site;
  }

  return `sc-domain:${property.replace(/^\/+|\/+$/g, "")}`;
}

function normalizeDateValue_(value) {
  if (!value) return "";
  if (Object.prototype.toString.call(value) === "[object Date]") {
    return Utilities.formatDate(value, Session.getScriptTimeZone(), "yyyy-MM-dd");
  }
  return String(value).slice(0, 10);
}

function formatDate_(date, timezone) {
  return Utilities.formatDate(date, timezone, "yyyy-MM-dd");
}

function addDays_(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}
