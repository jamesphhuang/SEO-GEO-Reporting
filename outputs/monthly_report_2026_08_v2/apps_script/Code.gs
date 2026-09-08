/**
 * Bound web app that renders the SEO／GEO monthly report from this workbook's own tabs.
 *
 * Column order is read from the _Schema tab rather than hard-coded here, so the
 * publishing pipeline can add or reorder columns without a code change. Tabs whose
 * names start with an underscore are control tabs and are never rendered as sections.
 */

var TEMPLATE = 'Report';
var SCHEMA_TAB = '_Schema';
var META_TAB = '_Meta';

/**
 * ?view=exec renders the four-block overview for the management meeting; anything else
 * renders the full report. Both read the same tabs in the same publish, so the two views
 * can never show different numbers for the same month.
 */
function doGet(e) {
  var template = HtmlService.createTemplateFromFile(TEMPLATE);
  var model = readWorkbook();
  model.view = (e && e.parameter && e.parameter.view === 'exec') ? 'exec' : 'full';
  model.scriptUrl = ScriptApp.getService().getUrl();
  template.payload = JSON.stringify(model).replace(/</g, '\\u003c');
  return template.evaluate()
    .setTitle(model.meta.reportTitle || 'SEO／GEO 月報')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** Adds a menu entry so the report can be opened from the spreadsheet itself. */
function onOpen() {
  SpreadsheetApp.getUi().createMenu('SEO／GEO 月報')
    .addItem('在側邊欄開啟', 'showSidebar')
    .addItem('全頁預覽', 'showDialog')
    .addToUi();
}

function showSidebar() {
  var template = HtmlService.createTemplateFromFile(TEMPLATE);
  template.payload = JSON.stringify(readWorkbook()).replace(/</g, '\\u003c');
  SpreadsheetApp.getUi().showSidebar(template.evaluate().setTitle('SEO／GEO 月報'));
}

function showDialog() {
  var template = HtmlService.createTemplateFromFile(TEMPLATE);
  template.payload = JSON.stringify(readWorkbook()).replace(/</g, '\\u003c');
  var output = template.evaluate().setWidth(1400).setHeight(900);
  SpreadsheetApp.getUi().showModalDialog(output, '月報預覽');
}

/** Reads every data tab named in _Schema into plain objects. */
function readWorkbook() {
  var book = SpreadsheetApp.getActive();
  var schema = readSchema(book);
  var model = {meta: {}, tables: {}, rowCounts: {}};

  Object.keys(schema).forEach(function (name) {
    if (name === SCHEMA_TAB) {
      return;
    }
    var records = readRecords(book, name, schema[name]);
    model.rowCounts[name] = records.length;
    if (name === META_TAB) {
      records.forEach(function (record) {
        model.meta[record.key] = record.value;
      });
    } else {
      model.tables[name] = records;
    }
  });

  model.workbookUrl = book.getUrl();
  model.renderedAt = Utilities.formatDate(new Date(), book.getSpreadsheetTimeZone(), "yyyy-MM-dd HH:mm");
  model.timeZone = book.getSpreadsheetTimeZone();
  return model;
}

function readSchema(book) {
  var sheet = book.getSheetByName(SCHEMA_TAB);
  if (!sheet) {
    throw new Error('找不到 ' + SCHEMA_TAB + ' 工作表；請先執行發佈流程寫入資料。');
  }
  var values = sheet.getDataRange().getValues();
  var schema = {};
  for (var row = 1; row < values.length; row++) {
    var name = String(values[row][0] || '').trim();
    var fields = String(values[row][1] || '').trim();
    if (name && fields) {
      schema[name] = fields.split(',').map(function (field) { return field.trim(); });
    }
  }
  return schema;
}

function readRecords(book, name, fields) {
  var sheet = book.getSheetByName(name);
  if (!sheet || sheet.getLastRow() < 2) {
    return [];
  }
  var values = sheet.getRange(2, 1, sheet.getLastRow() - 1, fields.length).getValues();
  return values.filter(function (row) {
    return row.some(function (cell) { return cell !== '' && cell !== null; });
  }).map(function (row) {
    var record = {};
    fields.forEach(function (field, index) {
      var cell = row[index];
      record[field] = cell === '' ? null : cell;
    });
    return record;
  });
}
