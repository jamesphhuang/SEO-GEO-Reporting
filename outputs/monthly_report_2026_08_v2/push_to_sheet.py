"""Publish the Aug-2026 report model into the reporting workbook.

Each tab is a flat header row plus data rows so the bound Apps Script can read it
without knowing anything about how the numbers were produced. Rerunning this replaces
the managed tabs in place; tabs the workbook already had are left alone.
"""

import json
import sys
from pathlib import Path

import sheets_api

OUT = Path(__file__).resolve().parent
MODEL = json.loads((OUT / "report_data.json").read_text())
SPREADSHEET_ID = sys.argv[1] if len(sys.argv) > 1 else "14lyC4zotKGBGg90CExf3q-hPk7awRAvUgIoEYAn1QtI"
TITLE = "SHOPLINE 台灣 SEO／GEO 月報｜2026 年 8 月"

COUNT, PERCENT, DECIMAL, POINT = "#,##0", "0.00%", "0.00", "+0.00;-0.00"

# Tabs people edit by hand. This script registers their column order in _Schema so the
# bound Apps Script can see them, creates them with a header row when they are missing,
# and otherwise never touches their contents — no wipe, no value write, no reformatting.
RECOMMENDATIONS = [("編號", "id"), ("期別", "period"), ("段落", "section"), ("排序", "order"),
                   ("優先度", "priority"), ("建議內容", "text"), ("狀態", "status"),
                   ("證據來源", "evidenceRef"), ("負責人", "owner"), ("預計完成", "due"), ("錨點", "anchor")]
NEXT_STEPS = [("期別", "period"), ("區塊", "section"), ("排序", "order"), ("Next Step", "text"),
              ("來源建議編號", "sourceRef"), ("狀態", "status"), ("負責人", "owner"), ("預計完成", "due")]
PROTECTED = {
    "Recommendations": {"headers": RECOMMENDATIONS, "widths": {5: 460, 7: 320},
                        "required": {"id", "period", "section", "order", "priority", "text",
                                     "status", "evidenceRef"}},
    "Next_Steps": {"headers": NEXT_STEPS, "widths": {3: 460, 4: 180},
                   "required": {"period", "section", "order", "text", "sourceRef", "status"}},
}


def tab(name, headers, rows, formats=None, widths=None, protected=False):
    return {"name": name, "headers": [h[0] for h in headers], "fields": [h[1] for h in headers],
            "rows": rows, "formats": formats or {}, "widths": widths or {}, "protected": protected}


def build_tabs():
    business, period = MODEL["business"], MODEL["period"]
    meta_rows = [
        ["reportTitle", TITLE],
        ["periodCurrent", period["current"]],
        ["periodPrevious", period["previous"]],
        ["generatedAt", MODEL["generatedAt"]],
        ["geoSnapshotAt", MODEL["geoSnapshotAt"]],
        ["technicalStatus", MODEL.get("technicalStatus", "PENDING")],
        ["cwvStatus", MODEL.get("cwvStatus", "PENDING")],
        ["cwvPeriod", MODEL.get("cwvPeriod", "")],
        ["cwvRetrievedAt", MODEL.get("cwvRetrievedAt") or ""],
        ["businessSpreadsheetId", business["spreadsheetId"]],
        ["businessSourceTab", business["sourceTab"]],
        ["businessSourceRow", business["sourceRow"]],
        # Actuals in the source workbook get restated after the fact, so the report says
        # which reading it is showing rather than implying a single settled number.
        ["businessAsOf", business.get("asOf") or ""],
    ]

    tabs = [
        tab("_Meta", [("key", "key"), ("value", "value")], meta_rows),
        tab("Business",
            [("項目", "label"), ("7 月目標", "julTarget"), ("7 月實績", "julActual"), ("7 月達成率", "julReach"),
             ("8 月目標", "augTarget"), ("8 月實績", "augActual"), ("8 月達成率", "augReach"),
             ("較 7 月", "momChange"), ("與目標差距", "gap"), ("9 月目標", "sepTarget"),
             # SQL 達成率與月變化在成熟日之前一律為空，這是 data_contract 的規定，不是資料缺漏。
             ("SQL 狀態", "sqlStatus"), ("SQL 項目", "sqlLabel"), ("SQL 8 月目標", "sqlTarget"), ("SQL 8 月累計", "sqlActual"),
             ("SQL 成熟日", "sqlMatureOn"), ("SQL 已成熟", "sqlIsMature"), ("SQL 達成率", "sqlReach"),
             ("SQL 較 7 月", "sqlMomChange"), ("SQL 來源狀態", "sqlSourceStatus"), ("SQL 來源列", "sqlSourceRow")],
            [business], {3: PERCENT, 6: PERCENT, 7: PERCENT, 1: COUNT, 2: COUNT, 4: COUNT, 5: COUNT, 8: COUNT,
                         9: COUNT, 12: COUNT, 13: COUNT, 16: PERCENT, 17: PERCENT}),
        tab("GSC_Monthly",
            [("站點", "siteLabel"), ("年月", "month"), ("月份", "monthLabel"), ("天數", "days"), ("點擊", "clicks"),
             ("曝光", "impressions"), ("CTR", "ctr"), ("平均排名", "position")],
            MODEL["gscMonthly"], {4: COUNT, 5: COUNT, 6: PERCENT, 7: DECIMAL}),
        tab("GSC_Delta",
            [("站點", "siteLabel"), ("7 月點擊", "clicksJul"), ("8 月點擊", "clicksAug"), ("點擊變化", "clicksChange"),
             ("7 月曝光", "imprJul"), ("8 月曝光", "imprAug"), ("曝光變化", "imprChange"),
             ("7 月 CTR", "ctrJul"), ("8 月 CTR", "ctrAug"), ("CTR 變化 (pt)", "ctrChangePt"),
             ("7 月排名", "posJul"), ("8 月排名", "posAug"), ("排名變化", "posChange")],
            MODEL["gscDeltas"],
            {1: COUNT, 2: COUNT, 3: PERCENT, 4: COUNT, 5: COUNT, 6: PERCENT, 7: PERCENT, 8: PERCENT,
             9: POINT, 10: DECIMAL, 11: DECIMAL, 12: POINT}),
        tab("GSC_Pages",
            [("站點", "siteLabel"), ("網址", "page"), ("點擊", "clicks"), ("曝光", "impressions"),
             ("CTR", "ctr"), ("平均排名", "position")],
            MODEL["gscPages"], {2: COUNT, 3: COUNT, 4: PERCENT, 5: DECIMAL}, {1: 420}),
        tab("GSC_Queries",
            [("站點", "siteLabel"), ("查詢", "query"), ("點擊", "clicks"), ("曝光", "impressions"),
             ("CTR", "ctr"), ("平均排名", "position")],
            MODEL["gscQueries"], {2: COUNT, 3: COUNT, 4: PERCENT, 5: DECIMAL}, {1: 260}),
        tab("GA4_Channels",
            [("Property", "propertyId"), ("站點", "siteLabel"), ("Hostname", "hostname"), ("渠道", "channel"),
             ("7 月工作階段", "sessionsJul"), ("8 月工作階段", "sessionsAug"), ("變化", "sessionsChange"),
             ("8 月使用者", "usersAug"), ("7 月互動率", "engagementJul"), ("8 月互動率", "engagementAug")],
            MODEL["ga4Channels"], {4: COUNT, 5: COUNT, 6: PERCENT, 7: COUNT, 8: PERCENT, 9: PERCENT}),
        tab("GEO_Workduo",
            [("品牌", "entity"), ("7 月可見度", "visibilityJul"), ("8 月可見度", "visibilityAug"),
             ("可見度變化 (pt)", "visibilityChangePt"), ("7 月 SOV", "sovJul"), ("8 月 SOV", "sovAug"),
             ("8 月提及數", "mentionsAug"), ("8 月天數", "daysAug")],
            MODEL["geo"], {1: PERCENT, 2: PERCENT, 3: POINT, 4: PERCENT, 5: PERCENT, 6: COUNT}),
        tab("Sitemaps",
            [("站點", "siteLabel"), ("Sitemap", "path"), ("狀態", "status"), ("警告", "warnings"), ("錯誤", "errors"),
             ("最後提交", "lastSubmitted"), ("最後抓取", "lastDownloaded"), ("停滯天數", "staleDays"),
             ("提交筆數", "submittedCount"), ("說明", "note")],
            MODEL["sitemaps"], {3: COUNT, 4: COUNT, 7: COUNT, 8: COUNT}, {1: 320, 9: 380}),
        tab("CWV",
            [("類別", "group"), ("站點", "siteLabel"), ("裝置", "formLabel"), ("指標", "metricLabel"),
             ("代號", "metricShort"), ("單位", "unit"), ("p75", "p75"), ("評級", "rating"),
             ("良好占比", "goodShare"), ("需改善占比", "needsShare"), ("不佳占比", "poorShare"),
             ("良好門檻", "goodThreshold"), ("不佳門檻", "poorThreshold"),
             ("前一期 p75", "prevP75"), ("前一期結束", "prevEnd"), ("變化", "change"),
             ("期間起", "periodFirst"), ("期間迄", "periodLast")],
            MODEL.get("cwv", []), {8: PERCENT, 9: PERCENT, 10: PERCENT, 15: PERCENT}, {3: 200}),
        tab("CWV_Trend",
            [("站點", "siteLabel"), ("裝置", "formLabel"), ("指標", "metricShort"), ("單位", "unit"),
             ("期間結束", "periodEnd"), ("p75", "p75")],
            MODEL.get("cwvTrend", [])),
        tab("CWV_Missing",
            [("站點", "siteLabel"), ("裝置", "formLabel"), ("原因", "reason")],
            MODEL.get("cwvMissing", []), {}, {2: 460}),
        tab("Technical_SF",
            [("優先度", "severity"), ("站點", "siteLabel"), ("項目", "issue"), ("數量", "count"),
             ("佔比", "share"), ("分母", "scope"), ("說明", "note")],
            MODEL.get("technical", []), {3: COUNT, 4: PERCENT}, {5: 260, 6: 420}),
        tab("SF_Crawls",
            [("站點", "siteLabel"), ("爬取起點", "siteCrawled"), ("爬取完成時間", "crawlDate"), ("耗時", "elapsed"),
             ("發現網址", "urlsEncountered"), ("實際爬取", "urlsCrawled"), ("站內網址", "internalUrls"),
             ("站內可索引", "internalIndexable"), ("站內不可索引", "internalNonIndexable")],
            MODEL.get("technicalCrawls", []), {4: COUNT, 5: COUNT, 6: COUNT, 7: COUNT, 8: COUNT}, {1: 240}),
        tab("SF_Excluded",
            [("未列入項目", "item"), ("原因", "reason")],
            MODEL.get("technicalExcluded", []), {}, {0: 340, 1: 460}),
        tab("GA4_Monthly",
            [("站點", "siteLabel"), ("年月", "month"), ("月份", "monthLabel"), ("渠道", "channel"),
             ("工作階段", "sessions"), ("相對 Organic", "shareOfOrganic")],
            MODEL.get("ga4Monthly", []), {4: COUNT, 5: PERCENT}, {0: 200}),
        tab("AI_Channel",
            [("年月", "month"), ("月份", "monthLabel"), ("名單", "leads"), ("SQL", "sql"), ("CVR", "cvr"),
             ("SQL 已成熟", "sqlIsMature"), ("SQL 成熟日", "sqlMatureOn"), ("來源", "sourceLabel")],
            MODEL.get("aiChannel", []), {2: COUNT, 3: COUNT, 4: PERCENT}, {7: 200}),
        tab("Sources",
            [("來源", "id"), ("說明", "label"), ("方法", "method"), ("篩選與限制", "filters")],
            sources(), {}, {2: 460, 3: 460}),
    ]
    tabs += [tab(name, spec["headers"], [], {}, spec["widths"], protected=True)
             for name, spec in PROTECTED.items()]
    return tabs


def schema_tab(tabs):
    """_Schema tells the bound Apps Script each tab's column order, so the renderer never
    depends on this file's literal column positions. Protected tabs contribute the order
    actually present in the workbook, resolved by resolve_protected()."""
    schema = [{"tab": t["name"], "fieldsCsv": ",".join(str(f) for f in t["fields"])} for t in tabs]
    return tab("_Schema", [("tab", "tab"), ("fieldsCsv", "fieldsCsv")], schema, {}, {1: 520})


def resolve_protected(spreadsheet_id, tabs, existing):
    """Rewrite each existing protected tab's field order to match its real header row.

    People own these tabs, so they may reorder or add columns. Reading the live header row
    keeps _Schema truthful instead of asserting the order this file happens to declare.
    A missing required column is a hard error: publishing a half-readable human tab would
    silently drop whatever the renderer expected to find there.
    """
    live = [t for t in tabs if t["protected"] and t["name"] in existing]
    blank = set()
    if not live:
        return blank
    read = sheets_api.read_values(spreadsheet_id, [f"'{t['name']}'!1:1" for t in live])
    for spec, value_range in zip(live, read.get("valueRanges", [])):
        header_row = ((value_range.get("values") or [[]]) or [[]])[0]
        known = dict(PROTECTED[spec["name"]]["headers"])
        headers = [str(h).strip() for h in header_row if str(h).strip()]
        if not headers:
            blank.add(spec["name"])  # tab exists but has no header row yet; write ours
            continue
        # An unrecognised column keeps its own label as the field name: extra human columns
        # reach the renderer as-is rather than shifting every later column out of position.
        fields = [known.get(h, h) for h in headers]
        missing = PROTECTED[spec["name"]]["required"] - set(fields)
        if missing:
            raise SystemExit(
                f"分頁「{spec['name']}」缺少必要欄位：{'、'.join(sorted(missing))}\n"
                f"目前標頭：{'｜'.join(headers)}\n"
                f"請補上欄位後再發佈；本次未寫入任何資料。")
        spec["headers"], spec["fields"] = headers, fields
    return blank


def sources():
    business = MODEL["business"]
    return [
        {"id": "business", "label": "正式業務來源｜2026 lead gen distribution",
         "method": (f"Google Sheets API values.batchGet；工作表「{business['sourceTab']}」第 {business['sourceRow']} 列。"
                    "7 月實績 C、8 月實績 G；目標 B、F。達成率 = 實績 / 目標，月增率 = 8 月 / 7 月 − 1。"),
         "filters": "TW；all_non_paid；原始數字儲存格，非公式結果；非 SEO 單一渠道。來源時區 Asia/Shanghai。"},
        {"id": "gsc", "label": "Google Search Console MCP｜兩站台灣搜尋",
         "method": ("get_advanced_search_analytics；dimensions=date，逐日加總 clicks 與 impressions。"
                    "CTR = 總點擊 / 總曝光；平均排名以曝光加權，來源每日排名已四捨五入，僅為近似。"),
         "filters": ("2026-07-01–07-31 與 2026-08-01–08-31，各 31 天；search_type=web；country=twn；"
                     "data_state=final；row_limit=100，has_more=false。GSC 日界以來源太平洋時間為準。")},
        {"id": "ga4", "label": "GA4 MCP｜主站 257016301／部落格 399614424",
         "method": ("run_report；dimensions=hostName,sessionDefaultChannelGroup；"
                    "metrics=sessions,engagedSessions,totalUsers。hostname 精確比對、不分大小寫；"
                    "僅取 Organic Search 與 AI Assistant。互動率 = engagedSessions / sessions。"),
         "filters": ("2026 年 7、8 月；Asia/Taipei；未加國別篩選，包含所有國家。兩個 property 分開報告，"
                     "依 ga4_scope.v1.json 禁止跨 property 加總。hostName 是事件主機診斷切分，不等同 landing-session 口徑。")},
        {"id": "ga4Monthly", "label": "GA4 MCP｜主站與部落格逐月渠道工作階段",
         "method": ("run_report；dimensions=yearMonth,hostName,sessionDefaultChannelGroup；metrics=sessions；"
                    "以 dimension_filter 在 API 端限定 hostName 精確相符。"
                    "「相對 Organic」= 該渠道工作階段 / 同站同月 Organic Search 工作階段。"),
         "filters": ("2026 年 6～8 月；僅取 Organic Search 與 AI Assistant 兩個渠道群組。"
                     "Google 自 2026-05 起才開始套用 AI Assistant 渠道群組，此前的 AI 來源流量被分類為 "
                     "Referral 或 Unassigned 且未回溯重新分類，因此本序列不往前延伸，也不能與 2026-04 以前比較。"
                     "2026-09-08 以 sessionSource 另行核對：2025-09～2026-04 平均約 102 次／月，"
                     "2026-05 起跳升至數百次；該核對僅供判讀脈絡，非本報表採用的口徑。"
                     "分母 Organic Search 本身正在下滑，佔比上升不必然代表 AI 流量成長，須與絕對值並看。")},
        {"id": "aiChannel", "label": "業務活頁簿｜AI Channel leads 頁籤（chatgpt.com）",
         "method": ("Google Sheets API values.batchGet 讀取「AI Channel leads」頁籤；"
                    "首欄為該月一日的序列日期，其餘為名單數、SQL 與 CVR，數值原樣取用未重算。"),
         "filters": ("該頁籤 B 欄標頭自述 source=chatgpt.com，僅涵蓋 chatgpt.com 單一來源，"
                     "不等於 GA4 的 AI Assistant 渠道群組，也不等於整體 AI 搜尋，兩者不可互相對帳。"
                     "資料自 2026-06 起；進行中的當月為部分月，已排除不列。"
                     "SQL 沿用 data_contract 的成熟規則（名單月結束後 60 天），未成熟月份僅供累計參考。")},
        {"id": "geo", "label": "Workduo MCP｜SHOPLINE 台灣專案（2026-09-06 快照）",
         "method": ("get_metrics；projectId=cmp2adkpz000gw209tj6025jc；metric=all；dimension=entity；interval=daily。"
                    "每日 visibility 與 sov 取等權算術平均，mentions 逐日加總。"
                    "這是每日平均監測指標，不是整月去重或按回覆量加權的比率。"),
         "filters": (f"region=TW；onlyTrackedEntity=true；2026 年 7、8 月各 310 列（10 entities × 31 日）；"
                     f"nextPageToken=null。本次執行環境未連線 Workduo MCP，沿用 {MODEL['geoSnapshotAt']} 的快照。"
                     "提示題目與平台組成尚未做固定樣本對齊，僅描述監測樣本，不能推論全市場。")},
        {"id": "pages", "label": "Google Search Console MCP｜8 月頁面與查詢",
         "method": ("get_advanced_search_analytics；dimensions=page 與 query；依 clicks 降序取前 25。"
                    "作為機會清單使用，不能用來推算全站總量或月降幅來源。"),
         "filters": "2026-08-01–08-31；search_type=web；country=twn；data_state=final；未取得 7 月逐頁對照。"},
        {"id": "sitemaps", "label": "Google Search Console MCP｜Sitemap 狀態",
         "method": ("get_sitemaps 列出各站已提交的 sitemap；get_sitemap_details 逐一查詢取得 last_submitted、"
                    "last_downloaded 與 content_breakdown 的 submitted／indexed 筆數。停滯天數 = 資料擷取時間 − "
                    "last_downloaded，用來判斷警告／錯誤是否為近期問題。"),
         "filters": ("content_breakdown 的 indexed 筆數在三筆 sitemap 中有兩筆回傳 0（含近期正常運作的 sitemap.xml），"
                     "判斷該欄位不可靠，故報表不採用『已索引筆數』做比較，只用狀態與最後抓取時間。")},
        {"id": "cwv", "label": "Chrome UX Report API｜Core Web Vitals 實際使用者資料",
         "method": ("records:queryRecord 取每個來源網域 × 裝置的當期紀錄，records:queryHistoryRecord 取前 25 期。"
                    "p75、良好／需改善／不佳占比全部直接取自 CrUX，未自行由分布重算。"
                    "評級用 Google 公布門檻：LCP ≤ 2500ms、INP ≤ 200ms、CLS ≤ 0.1 為良好，"
                    "> 4000ms／> 500ms／> 0.25 為不佳。整體通過需三項核心指標同時良好。"
                    "『前一期』是結束日早於當期起始日的最近一期，也就是緊鄰當期之前、與當期不重疊的 28 天窗口；"
                    "queryHistoryRecord 的序列可能落後當期一週，因此以日期挑選而非固定往前數幾期。"),
         "filters": (f"來源網域層級（非單頁），PHONE 與 DESKTOP 分開，未加國別篩選，包含所有國家的 Chrome 使用者。"
                     f"CrUX 為滾動 28 天窗口，本次為 {MODEL.get('cwvPeriod') or '尚未取得'}，"
                     "與報表月份不一致，不能當成 8 月單月數值，也不能與 GSC／GA4 的月度口徑對帳。"
                     "樣本僅含已啟用回報的 Chrome 使用者，不含 Safari 等其他瀏覽器。"
                     "Search Console 的 Core Web Vitals 報表同樣以 CrUX 為基礎，但其網址分組方式不同，數字不會完全一致。")},
        {"id": "technical", "label": "Screaming Frog SEO Spider MCP｜技術稽核",
         "method": ("export_crawl；save_report=Crawl Overview，讀取兩站已完成爬取的 crawl_overview.csv。"
                    "數量與佔比直接取自 Screaming Frog 的統計，分母沿用其原始定義（見 Technical_SF 的「分母」欄），"
                    "未自行重算。優先度為人工判定，非 Screaming Frog 原生欄位。"),
         "filters": ("主站 db f2215f0d（2026-09-06 20:24 完成，749 網址）；部落格 db 1af9795a"
                     "（2026-09-06 21:17 完成，21,133 網址）。Crawl Overview 追蹤的所有篩選中，"
                     "僅列入 sf_technical.py 的 CATALOGUE 允許清單；刻意排除的項目與原因見 SF_Excluded 分頁。"
                     "爬取為單一時點快照，無 7 月對照，不能據此判斷月變化。")},
    ]


def main():
    meta = sheets_api.metadata(SPREADSHEET_ID)
    existing = {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta["sheets"]}
    tabs = build_tabs()
    # Protected tabs are registered in _Schema using the column order the workbook really
    # has, so _Schema must be built after that order is resolved.
    blank = resolve_protected(SPREADSHEET_ID, tabs, existing)
    tabs.append(schema_tab(tabs))
    # A protected tab gets its header row written only when it is new or still empty.
    bootstrap = {t["name"] for t in tabs
                 if t["protected"] and (t["name"] not in existing or t["name"] in blank)}

    setup = []
    if meta["properties"]["title"] != TITLE:
        setup.append({"updateSpreadsheetProperties": {"properties": {"title": TITLE}, "fields": "title"}})
    # Reuse the workbook's first sheet as _Meta so no stray default tab is left behind.
    first_id = meta["sheets"][0]["properties"]["sheetId"]
    first_title = meta["sheets"][0]["properties"]["title"]
    if first_title not in [t["name"] for t in tabs]:
        setup.append({"updateSheetProperties": {"properties": {"sheetId": first_id, "title": tabs[0]["name"]},
                                                "fields": "title"}})
        existing[tabs[0]["name"]] = first_id
        existing.pop(first_title, None)
    for index, spec in enumerate(tabs):
        if spec["name"] in existing:
            if spec["protected"]:
                continue  # never wipe a tab people write in
            setup.append({"updateCells": {"range": {"sheetId": existing[spec["name"]]}, "fields": "*"}})
        else:
            setup.append({"addSheet": {"properties": {"title": spec["name"], "index": index}}})
    added = sheets_api.batch_update(SPREADSHEET_ID, setup)
    for reply in added.get("replies", []):
        if "addSheet" in reply:
            existing[reply["addSheet"]["properties"]["title"]] = reply["addSheet"]["properties"]["sheetId"]

    data, formatting = [], []
    for spec in tabs:
        if spec["protected"] and spec["name"] not in bootstrap:
            continue  # contents and formatting belong to whoever edits the tab
        sheet_id = existing[spec["name"]]
        values = [spec["headers"]]
        for row in spec["rows"]:
            values.append([row[f] if isinstance(row, dict) else row[f] for f in spec["fields"]]
                          if isinstance(row, dict) else list(row))
        values = [[("" if v is None else v) for v in line] for line in values]
        data.append({"range": f"'{spec['name']}'!A1", "values": values})
        formatting.append({"repeatCell": {
            "range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
            "cell": {"userEnteredFormat": {"textFormat": {"bold": True},
                                           "backgroundColor": {"red": 0.937, "green": 0.945, "blue": 0.957}}},
            "fields": "userEnteredFormat(textFormat,backgroundColor)"}})
        formatting.append({"updateSheetProperties": {
            "properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}},
            "fields": "gridProperties.frozenRowCount"}})
        for column, pattern in spec["formats"].items():
            formatting.append({"repeatCell": {
                "range": {"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": column, "endColumnIndex": column + 1},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": pattern}}},
                "fields": "userEnteredFormat.numberFormat"}})
        for column, width in spec["widths"].items():
            formatting.append({"updateDimensionProperties": {
                "range": {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": column, "endIndex": column + 1},
                "properties": {"pixelSize": width}, "fields": "pixelSize"}})

    sheets_api.write_values(SPREADSHEET_ID, data)
    sheets_api.batch_update(SPREADSHEET_ID, formatting)
    for spec in tabs:
        if not spec["protected"]:
            note = f"{len(spec['rows']):4} rows"
        elif spec["name"] in bootstrap:
            note = "   - 已建立表頭"
        else:
            note = "   - 保護中，內容未動"
        print(f"  {spec['name']:16} {note}")
    print("workbook:", f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit")


main()
