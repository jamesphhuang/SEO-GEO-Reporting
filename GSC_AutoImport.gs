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

/**
 * Daily import entry point.
 * Search Console data is usually delayed, so this refreshes a rolling window:
 * from 10 days ago through 3 days ago.
 */
function importGSCRecent() {
  const configs = getConfigRows_();
  const timezone = configs[0].timezone || Session.getScriptTimeZone() || "Asia/Taipei";
  const today = new Date();
  const startDate = formatDate_(addDays_(today, -10), timezone);
  const endDate = formatDate_(addDays_(today, -3), timezone);

  importGSCDateRange(startDate, endDate);
}

/**
 * Manual backfill helper.
 * Example:
 * importGSCDateRange("2026-04-01", "2026-04-30")
 */
function importGSCDateRange(startDate, endDate) {
  const configs = getConfigRows_();
  ensureGscSheet_();

  const rows = [];
  configs.forEach(config => {
    const siteUrl = normalizeGscPropertyUrl_(config.gsc_property_url, config.site_url);
    const fetchedRows = fetchGscRows_(siteUrl, startDate, endDate, config.site_url);
    rows.push(...fetchedRows);
  });

  replaceGscRowsByDateRange_(startDate, endDate, rows);

  SpreadsheetApp.getActive().toast(
    `GSC import completed: ${configs.length} properties, ${rows.length} rows from ${startDate} to ${endDate}`,
    "Technical SEO Agent",
    8
  );
}

/**
 * Quick permission/API check. Run this first after pasting the script.
 */
function testGSCConnection() {
  const configs = getConfigRows_();
  const config = configs[0];
  const siteUrl = normalizeGscPropertyUrl_(config.gsc_property_url, config.site_url);
  const timezone = config.timezone || Session.getScriptTimeZone() || "Asia/Taipei";

  if (!siteUrl) {
    throw new Error("Please fill Config!gsc_property_url first.");
  }

  const today = new Date();
  const startDate = formatDate_(addDays_(today, -10), timezone);
  const endDate = formatDate_(addDays_(today, -3), timezone);
  const url = `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(siteUrl)}/searchAnalytics/query`;
  const payload = {
    startDate,
    endDate,
    dimensions: ["date"],
    rowLimit: 1
  };

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
    throw new Error(`GSC API test failed (${status}): ${body}`);
  }

  Logger.log(body);
  SpreadsheetApp.getActive().toast("GSC connection OK", "Technical SEO Agent", 8);
}

/**
 * Tests every Config row that has a site_url or gsc_property_url.
 */
function testAllGSCConnections() {
  const configs = getConfigRows_();
  const timezone = configs[0].timezone || Session.getScriptTimeZone() || "Asia/Taipei";
  const today = new Date();
  const startDate = formatDate_(addDays_(today, -10), timezone);
  const endDate = formatDate_(addDays_(today, -3), timezone);

  configs.forEach(config => {
    const siteUrl = normalizeGscPropertyUrl_(config.gsc_property_url, config.site_url);
    const url = `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(siteUrl)}/searchAnalytics/query`;
    const payload = {
      startDate,
      endDate,
      dimensions: ["date"],
      rowLimit: 1
    };

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
      throw new Error(`GSC API test failed for ${siteUrl} (${status}): ${body}`);
    }

    Logger.log(`${siteUrl}: ${body}`);
  });

  SpreadsheetApp.getActive().toast(`GSC connection OK for ${configs.length} properties`, "Technical SEO Agent", 8);
}

/**
 * Creates a daily trigger at around 7 AM in the script timezone.
 */
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

/**
 * Run this if GSC_raw still has the old 9-column layout.
 * It adds site_url and gsc_property_url columns, then backfills them by matching page URLs.
 */
function upgradeGscRawSchema() {
  ensureGscSheet_();
  backfillGscPropertyColumns_();

  SpreadsheetApp.getActive().toast("GSC_raw schema upgraded", "Technical SEO Agent", 8);
}

/**
 * Prints the installed script version in Apps Script logs.
 */
function checkGSCImporterVersion() {
  Logger.log("GSC importer version: multi-property-v2");
  Logger.log(`Expected GSC_raw columns: ${GSC_HEADERS.join(", ")}`);
  SpreadsheetApp.getActive().toast("GSC importer version: multi-property-v2", "Technical SEO Agent", 8);
}

function fetchGscRows_(siteUrl, startDate, endDate, sourceSiteUrl) {
  const url = `https://www.googleapis.com/webmasters/v3/sites/${encodeURIComponent(siteUrl)}/searchAnalytics/query`;
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
      throw new Error(`GSC API request failed (${status}): ${body}`);
    }

    const json = JSON.parse(body);
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
        siteUrl
      ]);
    });

    hasMoreRows = rows.length === rowLimit;
    startRow += rowLimit;
  }

  return output;
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

  const currentHeaders = sheet.getRange(1, 1, 1, GSC_HEADERS.length).getValues()[0];
  const hasHeaders = GSC_HEADERS.every((header, index) => currentHeaders[index] === header);

  if (!hasHeaders) {
    sheet.getRange(1, 1, 1, GSC_HEADERS.length).setValues([GSC_HEADERS]);
  }

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

function getConfigMap_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(CONFIG_SHEET_NAME);
  if (!sheet) throw new Error("Config sheet not found.");

  const lastColumn = sheet.getLastColumn();
  const headers = sheet.getRange(1, 1, 1, lastColumn).getValues()[0];
  const values = sheet.getRange(2, 1, 1, lastColumn).getValues()[0];
  const config = {};

  headers.forEach((header, index) => {
    if (header) config[String(header).trim()] = values[index];
  });

  return config;
}

function getConfigRows_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(CONFIG_SHEET_NAME);
  if (!sheet) throw new Error("Config sheet not found.");

  const lastRow = sheet.getLastRow();
  const lastColumn = sheet.getLastColumn();
  if (lastRow < 2) {
    throw new Error("Please fill at least one Config row.");
  }

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
    const siteHost = site
      .replace(/^https?:\/\//, "")
      .replace(/^\/+|\/+$/g, "");
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
