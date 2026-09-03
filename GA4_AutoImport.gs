const GA4_SHEET_NAME = "GA4_raw";
const GA4_CONFIG_SHEET_NAME = "Config";

const GA4_HEADERS = [
  "date",
  "site_key",
  "site_url",
  "ga4_property_id",
  "host_name",
  "landing_page",
  "sessions",
  "engaged_sessions",
  "engagement_rate",
  "key_events",
  "total_revenue",
  "session_default_channel_group"
];

function checkGA4ImporterVersion() {
  Logger.log("GA4 importer version: multi-property-clean-v1");
  SpreadsheetApp.getActive().toast("GA4 importer version: multi-property-clean-v1", "Technical SEO Agent", 8);
}

function importGA4Recent() {
  const configs = getGA4ConfigRows_();
  const timezone = configs[0].timezone || Session.getScriptTimeZone() || "Asia/Taipei";
  const today = new Date();
  const startDate = formatGA4Date_(addGA4Days_(today, -10), timezone);
  const endDate = formatGA4Date_(addGA4Days_(today, -2), timezone);
  importGA4DateRange(startDate, endDate);
}

function importGA4DateRange(startDate, endDate) {
  const configs = getGA4ConfigRows_();
  ensureGA4Sheet_();

  const rows = [];
  configs.forEach(config => {
    const propertyId = String(config.ga4_property_id || "").trim();
    const fetchedRows = fetchGA4Rows_(propertyId, startDate, endDate, config);
    rows.push(...fetchedRows);
  });

  replaceGA4RowsByDateRange_(startDate, endDate, rows);

  SpreadsheetApp.getActive().toast(
    `GA4 import completed: ${configs.length} properties, ${rows.length} rows`,
    "Technical SEO Agent",
    8
  );
}

function testGA4Connection() {
  const configs = getGA4ConfigRows_();
  testOneGA4Connection_(configs[0]);
  SpreadsheetApp.getActive().toast("GA4 connection OK", "Technical SEO Agent", 8);
}

function testAllGA4Connections() {
  const configs = getGA4ConfigRows_();
  configs.forEach(config => testOneGA4Connection_(config));
  SpreadsheetApp.getActive().toast(`GA4 connection OK for ${configs.length} properties`, "Technical SEO Agent", 8);
}

function upgradeGA4RawSchema() {
  ensureGA4Sheet_();
  SpreadsheetApp.getActive().toast("GA4_raw schema upgraded", "Technical SEO Agent", 8);
}

function installDailyGA4ImportTrigger() {
  removeGA4ImportTriggers();
  ScriptApp.newTrigger("importGA4Recent")
    .timeBased()
    .everyDays(1)
    .atHour(8)
    .create();

  SpreadsheetApp.getActive().toast("Daily GA4 import trigger installed", "Technical SEO Agent", 8);
}

function removeGA4ImportTriggers() {
  ScriptApp.getProjectTriggers()
    .filter(trigger => trigger.getHandlerFunction() === "importGA4Recent")
    .forEach(trigger => ScriptApp.deleteTrigger(trigger));
}

function testOneGA4Connection_(config) {
  const propertyId = String(config.ga4_property_id || "").trim();
  const timezone = config.timezone || Session.getScriptTimeZone() || "Asia/Taipei";
  const today = new Date();
  const startDate = formatGA4Date_(addGA4Days_(today, -10), timezone);
  const endDate = formatGA4Date_(addGA4Days_(today, -2), timezone);
  const url = `https://analyticsdata.googleapis.com/v1beta/properties/${propertyId}:runReport`;
  const payload = {
    dateRanges: [{ startDate, endDate }],
    dimensions: [{ name: "date" }],
    metrics: [{ name: "sessions" }],
    limit: 1
  };

  const json = callGA4Api_(url, payload, `GA4 API test failed for property ${propertyId}`);
  Logger.log(`${propertyId}: ${JSON.stringify(json)}`);
}

function fetchGA4Rows_(propertyId, startDate, endDate, config) {
  const url = `https://analyticsdata.googleapis.com/v1beta/properties/${propertyId}:runReport`;
  const limit = 100000;
  let offset = 0;
  let hasMoreRows = true;
  const output = [];

  while (hasMoreRows) {
    const payload = {
      dateRanges: [{ startDate, endDate }],
      dimensions: [
        { name: "date" },
        { name: "hostName" },
        { name: "landingPagePlusQueryString" },
        { name: "sessionDefaultChannelGroup" }
      ],
      metrics: [
        { name: "sessions" },
        { name: "engagedSessions" },
        { name: "engagementRate" },
        { name: "keyEvents" },
        { name: "totalRevenue" }
      ],
      dimensionFilter: {
        filter: {
          fieldName: "sessionDefaultChannelGroup",
          stringFilter: {
            matchType: "EXACT",
            value: "Organic Search"
          }
        }
      },
      limit,
      offset
    };

    const json = callGA4Api_(url, payload, `GA4 API request failed for property ${propertyId}`);
    const rows = json.rows || [];

    rows.forEach(row => {
      const dimensions = row.dimensionValues || [];
      const metrics = row.metricValues || [];
      output.push([
        normalizeGA4ApiDate_(dimensions[0] && dimensions[0].value),
        config.site_key || "",
        config.site_url || "",
        propertyId,
        dimensions[1] ? dimensions[1].value : "",
        dimensions[2] ? dimensions[2].value : "",
        toGA4Number_(metrics[0] && metrics[0].value),
        toGA4Number_(metrics[1] && metrics[1].value),
        toGA4Number_(metrics[2] && metrics[2].value),
        toGA4Number_(metrics[3] && metrics[3].value),
        toGA4Number_(metrics[4] && metrics[4].value),
        dimensions[3] ? dimensions[3].value : ""
      ]);
    });

    hasMoreRows = rows.length === limit;
    offset += limit;
  }

  return output;
}

function callGA4Api_(url, payload, errorPrefix) {
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

function replaceGA4RowsByDateRange_(startDate, endDate, newRows) {
  const sheet = SpreadsheetApp.getActive().getSheetByName(GA4_SHEET_NAME);
  const lastRow = sheet.getLastRow();
  const lastColumn = GA4_HEADERS.length;
  const keptRows = [];

  if (lastRow > 1) {
    const existingRows = sheet.getRange(2, 1, lastRow - 1, lastColumn).getValues();
    existingRows.forEach(row => {
      const rowDate = normalizeGA4SheetDate_(row[0]);
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
    const bySite = String(a[1]).localeCompare(String(b[1]));
    if (bySite !== 0) return bySite;
    return String(a[5]).localeCompare(String(b[5]));
  });

  if (allRows.length) {
    sheet.getRange(2, 1, allRows.length, lastColumn).setValues(allRows);
  }

  sheet.getRange("A:A").setNumberFormat("yyyy-mm-dd");
  sheet.getRange("I:I").setNumberFormat("0.00%");
  sheet.getRange("K:K").setNumberFormat("#,##0.00");
  sheet.autoResizeColumns(1, lastColumn);
}

function ensureGA4Sheet_() {
  const ss = SpreadsheetApp.getActive();
  let sheet = ss.getSheetByName(GA4_SHEET_NAME);
  if (!sheet) sheet = ss.insertSheet(GA4_SHEET_NAME);

  sheet.getRange(1, 1, 1, GA4_HEADERS.length).setValues([GA4_HEADERS]);
  sheet.setFrozenRows(1);
  sheet.getRange(1, 1, 1, GA4_HEADERS.length)
    .setFontWeight("bold")
    .setFontColor("#ffffff")
    .setBackground("#1f4e78")
    .setHorizontalAlignment("center");
}

function getGA4ConfigRows_() {
  const sheet = SpreadsheetApp.getActive().getSheetByName(GA4_CONFIG_SHEET_NAME);
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
    .filter(config => config.site_url && config.ga4_property_id);

  if (!configs.length) {
    throw new Error("Please fill Config!site_url and Config!ga4_property_id first.");
  }

  return configs;
}

function normalizeGA4ApiDate_(value) {
  const text = String(value || "");
  if (/^\d{8}$/.test(text)) {
    return `${text.slice(0, 4)}-${text.slice(4, 6)}-${text.slice(6, 8)}`;
  }
  return text;
}

function normalizeGA4SheetDate_(value) {
  if (!value) return "";
  if (Object.prototype.toString.call(value) === "[object Date]") {
    return Utilities.formatDate(value, Session.getScriptTimeZone(), "yyyy-MM-dd");
  }
  return String(value).slice(0, 10);
}

function formatGA4Date_(date, timezone) {
  return Utilities.formatDate(date, timezone, "yyyy-MM-dd");
}

function addGA4Days_(date, days) {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function toGA4Number_(value) {
  const number = Number(value || 0);
  return Number.isFinite(number) ? number : 0;
}
