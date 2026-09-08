"""Turn the Aug-2026 evidence snapshot into the tabular model the report renders from.

Every figure here is derived from evidence.json only. GA4 stays inside the hostname and
channel allow-list in contracts/ga4_scope.v1.json and is never summed across properties.
"""

import calendar
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import cwv
import sf_technical

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
E = json.loads((OUT / "evidence.json").read_text())
SCOPE = json.loads((ROOT / "contracts" / "ga4_scope.v1.json").read_text())
DATA_CONTRACT = json.loads((ROOT / "contracts" / "data_contract.v1.json").read_text())
PERIOD = {"current": "2026-08", "previous": "2026-07"}
AS_OF = E["retrievedAt"][:10]

SITES = [("https://shopline.tw/", "主站 shopline.tw"), ("sc-domain:blog.shopline.tw", "部落格 blog.shopline.tw")]
PROPERTIES = [(SCOPE["sites"]["tw_main"], "主站 shopline.tw"), (SCOPE["sites"]["tw_blog"], "部落格 blog.shopline.tw")]
CHANNELS = SCOPE["channels"]
def month_label(month):
    return f"{int(month)} 月"


def sql_mature_on(period):
    """The date a lead month's SQL becomes comparable, per data_contract's sql_maturity."""
    year, month = (int(part) for part in period.split("-"))
    last = date(year, month, calendar.monthrange(year, month)[1])
    days = DATA_CONTRACT["business"]["sql_maturity"]["days_after_calendar_month_end"]
    return (last + timedelta(days=days)).isoformat()


def change(new, old):
    """Relative change, or None when the base is missing or zero."""
    if old in (None, 0) or new is None:
        return None
    return new / old - 1


def gsc_monthly():
    """Every month the evidence holds for each site, oldest first.

    Whatever months raw/gsc_pull.json fetched land here; a month that failed to pull is
    simply absent rather than a zero row, so the trend chart breaks instead of lying.
    """
    rows = []
    for site, label in SITES:
        for month in sorted(E["gsc"].get(site, {})):
            days = E["gsc"][site][month]["rows"]
            clicks = sum(d["clicks"] for d in days)
            impressions = sum(d["impressions"] for d in days)
            weighted = sum(d["position"] * d["impressions"] for d in days)
            rows.append({"site": site, "siteLabel": label, "month": month, "monthLabel": month_label(month),
                         "days": len(days), "clicks": clicks, "impressions": impressions,
                         "ctr": clicks / impressions if impressions else None,
                         "position": weighted / impressions if impressions else None})
    return rows


def gsc_deltas(rows):
    """Month-over-month for each site's two most recent months.

    The Jul/Aug suffixes are the workbook's existing column keys and mean previous/current;
    they are not pinned to those calendar months. A site with fewer than two months is
    skipped rather than compared against nothing.
    """
    out = []
    for site, label in SITES:
        series = sorted((r for r in rows if r["site"] == site), key=lambda r: r["month"])
        if len(series) < 2:
            continue
        jul, aug = series[-2], series[-1]
        out.append({"site": site, "siteLabel": label,
                    "clicksJul": jul["clicks"], "clicksAug": aug["clicks"], "clicksChange": change(aug["clicks"], jul["clicks"]),
                    "imprJul": jul["impressions"], "imprAug": aug["impressions"], "imprChange": change(aug["impressions"], jul["impressions"]),
                    "ctrJul": jul["ctr"], "ctrAug": aug["ctr"], "ctrChangePt": (aug["ctr"] - jul["ctr"]) * 100,
                    "posJul": jul["position"], "posAug": aug["position"], "posChange": aug["position"] - jul["position"]})
    return out


def gsc_detail(bucket, field):
    rows = []
    for site, label in SITES:
        for row in E[bucket][site]["rows"]:
            rows.append({"siteLabel": label, field: row[field], "clicks": row["clicks"],
                         "impressions": row["impressions"], "ctr": row["ctr"], "position": row["position"]})
    rows.sort(key=lambda r: r["clicks"], reverse=True)
    return rows


def ga4_channels():
    rows = []
    for site, label in PROPERTIES:
        report = E["ga4"][site["property_id"]]
        buckets = {}
        for row in report["rows"]:
            host, channel, period = (v["value"] for v in row["dimension_values"])
            if host.lower() != site["hostname"].lower() or channel not in CHANNELS:
                continue
            sessions, engaged, users = (int(m["value"]) for m in row["metric_values"])
            buckets.setdefault(channel, {})[period] = {"sessions": sessions, "engaged": engaged, "users": users}
        for channel in CHANNELS:
            jul, aug = buckets.get(channel, {}).get("jul"), buckets.get(channel, {}).get("aug")
            if not jul and not aug:
                continue
            rows.append({
                "propertyId": site["property_id"], "siteLabel": label, "hostname": site["hostname"], "channel": channel,
                "sessionsJul": jul and jul["sessions"], "sessionsAug": aug and aug["sessions"],
                "sessionsChange": change(aug and aug["sessions"], jul and jul["sessions"]),
                "usersAug": aug and aug["users"],
                "engagementJul": jul and jul["engaged"] / jul["sessions"] if jul and jul["sessions"] else None,
                "engagementAug": aug and aug["engaged"] / aug["sessions"] if aug and aug["sessions"] else None})
    return rows


def geo_entities():
    snapshot, rows = E["geo"]["snapshot"], {}
    for month in ("07", "08"):
        for day in snapshot[month]["data"]:
            bucket = rows.setdefault(day["dimensionValue"], {}).setdefault(month, {"visibility": [], "sov": [], "mentions": 0, "days": set()})
            # Workduo returns null for a metric on days with no observation; skip rather than coerce to zero.
            if day["visibility"] is not None:
                bucket["visibility"].append(day["visibility"])
            if day["sov"] is not None:
                bucket["sov"].append(day["sov"])
            bucket["mentions"] += day["mentions"] or 0
            bucket["days"].add(day["date"])
    out = []
    for entity, months in rows.items():
        jul, aug = months.get("07"), months.get("08")
        mean = lambda values: sum(values) / len(values) if values else None
        out.append({"entity": entity,
                    "visibilityJul": mean(jul["visibility"]) if jul else None,
                    "visibilityAug": mean(aug["visibility"]) if aug else None,
                    "visibilityChangePt": (mean(aug["visibility"]) - mean(jul["visibility"])) * 100 if jul and aug else None,
                    "sovJul": mean(jul["sov"]) if jul else None, "sovAug": mean(aug["sov"]) if aug else None,
                    "mentionsAug": aug["mentions"] if aug else None,
                    "daysAug": len(aug["days"]) if aug else None})
    out.sort(key=lambda r: r["visibilityAug"] or 0, reverse=True)
    return out


def business():
    row, columns = E["business"]["row_values"], E["business"]["month_columns"]
    at = lambda letter: row[ord(letter) - ord("A")]
    jul_actual, aug_actual = at(columns["07"]), at(columns["08"])
    jul_target, aug_target = at(chr(ord(columns["07"]) - 1)), at(chr(ord(columns["08"]) - 1))
    sep_target = at(chr(ord(columns["09"]) - 1))
    model = {"label": row[0], "julTarget": jul_target, "julActual": jul_actual, "julReach": jul_actual / jul_target,
             "augTarget": aug_target, "augActual": aug_actual, "augReach": aug_actual / aug_target,
             "momChange": change(aug_actual, jul_actual), "gap": aug_target - aug_actual, "sepTarget": sep_target,
             "asOf": E["business"].get("readAt"),
             "sourceTab": E["business"]["tab"], "sourceRow": E["business"]["data_row"],
             "spreadsheetId": E["business"]["spreadsheet_id"]}
    model.update(business_sql(columns))
    return model


def business_sql(columns):
    """The Non-Paid Leads SQL row, held to both contracts at once.

    data_contract's sql_maturity allows only an accumulated count until a lead month is
    60 days past its end; attainment, month-over-month and RAG are excluded before then.
    Those fields are therefore left null rather than computed and hidden — an immature
    attainment figure must not exist in the data at all, or something downstream will
    eventually render it. The mapping contract separately still marks this source
    unconfirmed, so that label travels with the numbers.
    """
    sql = (E.get("business") or {}).get("sql")
    if not sql or not sql.get("row_values"):
        return {"sqlStatus": "MISSING"}
    at = lambda letter: sql["row_values"][ord(letter) - ord("A")]
    target, actual = at(chr(ord(columns["08"]) - 1)), at(columns["08"])
    mature_on = sql_mature_on(PERIOD["current"])
    is_mature = AS_OF >= mature_on
    previous = at(columns["07"])
    return {"sqlStatus": "OK", "sqlLabel": sql["row_label"].strip(),
            "sqlTarget": target, "sqlActual": actual,
            "sqlMatureOn": mature_on, "sqlIsMature": is_mature,
            "sqlReach": (actual / target) if is_mature and target else None,
            "sqlPrevActual": previous if is_mature else None,
            "sqlMomChange": change(actual, previous) if is_mature else None,
            "sqlSourceStatus": sql["status"], "sqlApprovalState": sql["approvalState"],
            "sqlSourceRow": sql["data_row"]}


def ga4_monthly():
    """Monthly sessions per allow-listed channel, from the yearMonth report.

    A month where a channel has no rows is absent rather than zero: GA4 only began
    classifying the AI Assistant channel group in 2026-05, and a zero would read as a
    real collapse instead of a metric that did not yet exist.
    """
    rows = []
    for site, label in PROPERTIES:
        report = (E.get("ga4Monthly") or {}).get(site["property_id"])
        if not report:
            continue
        buckets = {}
        for row in report.get("rows", []):
            month, host, channel = (v["value"] for v in row["dimension_values"])
            if host.lower() != site["hostname"].lower() or channel not in CHANNELS:
                continue
            buckets.setdefault(f"{month[:4]}-{month[4:]}", {})[channel] = int(row["metric_values"][0]["value"])
        for month in sorted(buckets):
            organic = buckets[month].get("Organic Search")
            for channel in CHANNELS:
                sessions = buckets[month].get(channel)
                if sessions is None:
                    continue
                rows.append({"propertyId": site["property_id"], "siteLabel": label,
                             "hostname": site["hostname"], "month": month,
                             "monthLabel": month_label(month[5:]), "channel": channel,
                             "sessions": sessions,
                             "shareOfOrganic": (sessions / organic) if organic and channel != "Organic Search" else None})
    return rows


def ai_channel():
    """chatgpt.com leads and SQL — one AI source, not GA4's AI Assistant channel.

    The source label is carried from the sheet's own column header rather than asserted
    here. The in-flight month is dropped: it was seven days old when read and would sit
    beside full months as an apparent collapse. SQL obeys the same maturity rule as the
    business SQL row.
    """
    block = E.get("aiChannel") or {}
    rows = []
    for entry in block.get("months", []):
        if entry["month"] > PERIOD["current"]:
            continue
        mature_on = sql_mature_on(entry["month"])
        rows.append({"month": entry["month"], "monthLabel": month_label(entry["month"][5:]),
                     "leads": entry["leads"], "sql": entry["sql"], "cvr": entry["cvr"],
                     "sqlMatureOn": mature_on, "sqlIsMature": AS_OF >= mature_on,
                     "sourceLabel": (block.get("sourceLabel") or "source=chatgpt.com").strip()})
    return rows


def sitemaps():
    """Join get_sitemaps (for site grouping) with get_sitemap_details (for real dates/counts).

    get_sitemaps' own "indexed_urls" field is actually the submitted count, not an indexed
    count — get_sitemap_details' content_breakdown carries the real submitted/indexed split,
    so that is the source of truth here.
    """
    site_labels = dict(SITES)
    details = {(d["site_url"], d["sitemap_url"]): d for d in E["sitemapDetails"]}
    now = datetime.fromisoformat(E["retrievedAt"].replace("Z", "+00:00"))
    rows = []
    for site, label in SITES:
        for entry in E["sitemaps"][site].get("sitemaps", []):
            detail = details.get((site, entry["path"]))
            row = {"siteLabel": label, "path": entry["path"], "status": entry.get("status"),
                  "errors": entry.get("errors"), "warnings": entry.get("warnings"),
                  "lastSubmitted": None, "lastDownloaded": None, "submittedCount": None,
                  "indexedCount": None, "staleDays": None, "note": None}
            if detail:
                breakdown = detail.get("content_breakdown", [])
                row["lastSubmitted"] = detail.get("last_submitted")
                row["lastDownloaded"] = detail.get("last_downloaded")
                row["submittedCount"] = sum(int(b["submitted"]) for b in breakdown) if breakdown else None
                row["indexedCount"] = sum(int(b["indexed"]) for b in breakdown) if breakdown else None
                if row["lastDownloaded"]:
                    downloaded = datetime.strptime(row["lastDownloaded"], "%Y-%m-%d %H:%M").replace(tzinfo=now.tzinfo)
                    row["staleDays"] = (now - downloaded).days
                if (entry.get("errors") or entry.get("warnings")) and row["staleDays"] and row["staleDays"] > 180:
                    row["note"] = f"Google 已 {row['staleDays']} 天未重新抓取此 sitemap；錯誤與警告是歷史紀錄，非本月新增。"
                elif entry.get("errors") or entry.get("warnings"):
                    row["note"] = "本月仍有錯誤或警告，Google 近期仍在抓取。"
            rows.append(row)
    return rows


SF_EXPORTS = [("主站 shopline.tw", "shopline_tw_crawl_overview.csv"),
              ("部落格 blog.shopline.tw", "blog_shopline_tw_crawl_overview.csv")]


def technical():
    """Curated Screaming Frog findings plus the crawl metadata behind them."""
    directory = OUT / "raw" / "screaming_frog"
    rows, crawls = [], []
    for label, filename in SF_EXPORTS:
        path = directory / filename
        if not path.exists():
            continue
        parsed = sf_technical.parse_overview(path)
        rows.extend(sf_technical.audit_rows(label, parsed))
        crawls.append(sf_technical.crawl_meta(label, parsed))
    rows.sort(key=lambda r: (sf_technical.SEVERITY_ORDER[r["severity"]], -r["count"]))
    return rows, crawls


def crux_date(date):
    """CrUX returns {year, month, day} objects, not ISO strings."""
    if not date:
        return None
    return f"{date['year']:04d}-{date['month']:02d}-{date['day']:02d}"


def previous_window(metric_history, periods, current_first):
    """The p75 from the most recent window that ends before the current one begins.

    CrUX history windows are 28 days wide and step one week at a time, and the series can
    lag the current record by a week — in the 2026-09-07 pull the history ended 2026-08-29
    while the current window ran 2026-08-09 to 09-05. Counting a fixed number of entries
    back from the end therefore skips a window; selecting by date keeps the comparison
    adjacent to the current window and non-overlapping whatever the lag.
    """
    series = ((metric_history or {}).get("percentilesTimeseries") or {}).get("p75s") or []
    for index in range(min(len(series), len(periods)) - 1, -1, -1):
        last = crux_date(periods[index].get("lastDate"))
        if last and current_first and last < current_first:
            return cwv.value(series[index]), last
    return None, None


def core_web_vitals():
    """Flatten the CrUX snapshot into one row per origin x form factor x metric.

    Densities are CrUX's own histogram bins and the ratings use Google's published
    thresholds from cwv.py; nothing is recomputed from a distribution here. The window is
    CrUX's rolling 28 days and does not line up with the report month, so every row keeps
    the collection period it came from.
    """
    snapshot = E.get("cwv") or {}
    rows, trend, periods_seen, missing = [], [], [], []
    for result in snapshot.get("results", []):
        record = result.get("record")
        if not record:
            missing.append({"siteLabel": result["originLabel"], "formLabel": result["formLabel"],
                            "reason": result.get("error") or f"CrUX 回傳 {result.get('status')}，此組合無足夠樣本。"})
            continue
        period = record.get("collectionPeriod") or {}
        first, last = crux_date(period.get("firstDate")), crux_date(period.get("lastDate"))
        periods_seen.append((first, last))
        history = result.get("history") or {}
        history_periods = history.get("collectionPeriods") or []
        history_metrics = history.get("metrics") or {}
        for metric_id, label, short, unit, good, poor, is_core in cwv.METRICS:
            metric = (record.get("metrics") or {}).get(metric_id)
            if not metric:
                continue
            p75 = cwv.value((metric.get("percentiles") or {}).get("p75"))
            good_share, needs_share, poor_share = cwv.histogram(metric)
            previous, previous_end = previous_window(history_metrics.get(metric_id), history_periods, first)
            rows.append({
                "siteLabel": result["originLabel"], "formLabel": result["formLabel"],
                "group": "Core Web Vitals" if is_core else "輔助診斷",
                "metricLabel": label, "metricShort": short, "unit": unit,
                "p75": p75, "rating": cwv.rate(metric_id, p75),
                "goodShare": good_share, "needsShare": needs_share, "poorShare": poor_share,
                "goodThreshold": good, "poorThreshold": poor,
                "prevP75": previous, "prevEnd": previous_end,
                "change": change(p75, previous), "periodFirst": first, "periodLast": last})
            if not is_core:
                continue
            series = ((history_metrics.get(metric_id) or {}).get("percentilesTimeseries") or {}).get("p75s") or []
            points = []
            for index in range(min(len(series), len(history_periods))):
                value = cwv.value(series[index])
                if value is None:
                    continue
                points.append((crux_date(history_periods[index].get("lastDate")), value))
            if last and p75 is not None and last not in [day for day, _ in points]:
                points.append((last, p75))
            for day, value in points:
                trend.append({"siteLabel": result["originLabel"], "formLabel": result["formLabel"],
                              "metricShort": short, "unit": unit, "periodEnd": day, "p75": value})
    period = periods_seen[0] if periods_seen else (None, None)
    return rows, trend, missing, period


def main():
    monthly = gsc_monthly()
    technical_rows, technical_crawls = technical()
    cwv_rows, cwv_trend, cwv_missing, cwv_period = core_web_vitals()
    model = {"generatedAt": E["retrievedAt"], "period": dict(PERIOD),
             "business": business(), "gscMonthly": monthly, "gscDeltas": gsc_deltas(monthly),
             "gscPages": gsc_detail("gscPages", "page"), "gscQueries": gsc_detail("gscQueries", "query"),
             "ga4Channels": ga4_channels(), "ga4Monthly": ga4_monthly(), "aiChannel": ai_channel(),
             "geo": geo_entities(), "sitemaps": sitemaps(),
             "geoSnapshotAt": E["geo"]["snapshotRetrievedAt"],
             "technical": technical_rows, "technicalCrawls": technical_crawls,
             "technicalStatus": "OK" if technical_rows else "PENDING",
             "technicalExcluded": [{"item": item, "reason": reason} for item, reason in sf_technical.EXCLUDED],
             "cwv": cwv_rows, "cwvTrend": cwv_trend, "cwvMissing": cwv_missing,
             "cwvStatus": "OK" if cwv_rows else "PENDING",
             "cwvPeriod": " – ".join(p for p in cwv_period if p),
             "cwvRetrievedAt": (E.get("cwv") or {}).get("retrievedAt")}
    (OUT / "report_data.json").write_text(json.dumps(model, ensure_ascii=False, indent=1))
    print("business:", json.dumps(model["business"], ensure_ascii=False))
    for r in model["gscDeltas"]:
        print(f"GSC {r['siteLabel']}: clicks {r['clicksJul']}->{r['clicksAug']} ({r['clicksChange']:+.2%}), "
              f"impr {r['imprJul']}->{r['imprAug']} ({r['imprChange']:+.2%}), ctr {r['ctrAug']:.2%}, pos {r['posAug']:.2f}")
    for r in model["ga4Channels"]:
        print(f"GA4 {r['siteLabel']} {r['channel']}: {r['sessionsJul']}->{r['sessionsAug']} "
              f"({r['sessionsChange']:+.2%})" if r["sessionsChange"] is not None else f"GA4 {r['siteLabel']} {r['channel']}: {r['sessionsAug']}")
    for r in model["geo"][:4]:
        print(f"GEO {r['entity']}: vis {r['visibilityJul']:.4f}->{r['visibilityAug']:.4f} ({r['visibilityChangePt']:+.2f}pt)")
    print("sitemaps rows:", len(model["sitemaps"]), "| pages:", len(model["gscPages"]), "| queries:", len(model["gscQueries"]))
    for crawl in model["technicalCrawls"]:
        print(f"SF {crawl['siteLabel']}: {crawl['urlsCrawled']:,}/{crawl['urlsEncountered']:,} crawled, "
              f"internal {crawl['internalUrls']:,}, crawled at {crawl['crawlDate']}")
    print("technical findings:", len(model["technical"]),
          "| high:", sum(1 for r in model["technical"] if r["severity"] == "高"))
    for row in model["cwv"]:
        if row["group"] == "Core Web Vitals":
            print(f"CWV {row['siteLabel']} {row['formLabel']} {row['metricShort']}: "
                  f"p75 {row['p75']} {row['rating']} (良好 {row['goodShare']})")
    print("cwv rows:", len(model["cwv"]), "| trend points:", len(model["cwvTrend"]),
          "| window:", model["cwvPeriod"] or "PENDING",
          "| 無資料組合:", len(model["cwvMissing"]))


main()
