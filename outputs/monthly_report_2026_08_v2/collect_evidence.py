"""Consolidate raw MCP responses into a single Aug-2026 evidence snapshot.

Inputs are the raw stdio-MCP transcripts produced by mcp_client.py plus the
Workduo snapshot retained from the 2026-09-06 pull, since Workduo MCP is not
reachable from this runtime. Business actuals are read live from the workbook
named in contracts/business_actual_mapping.v1.json.
"""

import json
import sys
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRIVE = ROOT.parent
OUT = Path(__file__).resolve().parent
RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT / "raw"
SHEETS_CREDENTIAL = DRIVE / "98_環境設定" / "google-sheets" / "authorized_user.json"
MAPPING = json.loads((ROOT / "contracts" / "business_actual_mapping.v1.json").read_text())
GA4_SCOPE = json.loads((ROOT / "contracts" / "ga4_scope.v1.json").read_text())
PRIOR_EVIDENCE = ROOT / "outputs" / "monthly_report_2026_08" / "evidence.json"


def payloads(path, problems=None):
    """Yield (call_args, parsed_json) for each usable tool call in a transcript.

    With `problems` supplied, a call that errored or returned something that is not JSON is
    recorded there and skipped instead of aborting: an upstream object disappearing (a
    sitemap that is no longer submitted, say) should cost that one row, not the whole
    evidence file. Note that this server reports some failures as plain prose with
    isError=False, so the JSON parse — not the flag — is what actually catches them.
    Without `problems` the old strict behaviour stands.
    """
    transcript = json.loads(Path(path).read_text())
    for result in transcript["results"]:
        call = result["call"]
        text = "\n".join(result.get("text", []))
        note = result.get("error") or (text[:300] if result.get("isError") else None)
        body = None
        if not note:
            try:
                body = json.loads(text)
            except json.JSONDecodeError:
                note = text.strip()[:300] or "empty response"
        if note:
            if problems is None:
                raise SystemExit(f"MCP call failed: {call['name']} {note}")
            problems.append({"source": Path(path).name, "call": call["name"],
                             "args": call.get("args", {}), "note": note})
            continue
        yield call["args"], body


def access_token():
    credential = json.loads(SHEETS_CREDENTIAL.read_text())
    form = urllib.parse.urlencode({
        "client_id": credential["client_id"], "client_secret": credential["client_secret"],
        "refresh_token": credential["refresh_token"], "grant_type": "refresh_token"}).encode()
    request = urllib.request.Request(credential["token_uri"], data=form)
    return json.load(urllib.request.urlopen(request, timeout=20))["access_token"]


def read_source_ranges(ranges):
    query = urllib.parse.urlencode([("ranges", r) for r in ranges] + [("valueRenderOption", "UNFORMATTED_VALUE")])
    url = (f"https://sheets.googleapis.com/v4/spreadsheets/{MAPPING['workbook']['spreadsheet_id']}"
           f"/values:batchGet?{query}")
    request = urllib.request.Request(url, headers={"Authorization": "Bearer " + access_token()})
    return json.load(urllib.request.urlopen(request, timeout=30))


def business_actuals():
    """Read the Non-Paid Leads block for 2026 exactly where the mapping contract points.

    The row immediately below it holds that segment's SQL. That row is still
    SOURCE_NOT_CONFIRMED in the mapping contract, so it is carried here as a labelled
    candidate — never as an approved metric — and data_contract.v1.json allows only an
    accumulated count for lead months that have not matured.
    """
    mapping = MAPPING["mappings"][0]
    tab = next(t for t in mapping["source_tabs"] if t["title"].startswith("2026"))
    block = next(b for b in tab["blocks"] if "07" in b["month_columns"])
    row = block["data_row"]
    candidate = next(m for m in MAPPING["unresolved_metrics"] if m["metric"] == "sql")["located_candidate"]
    sql_tab = next(t for t in candidate["source_tabs"] if t["title"] == tab["title"])
    sql_block = next(b for b in sql_tab["blocks"] if b["parent_data_row"] == row)
    sql_row = sql_block["data_row"]

    ranges = [f"'{tab['title']}'!A{row}:L{row}", f"'{tab['title']}'!A{block['header_row']}:L{block['header_row']}",
              f"'{tab['title']}'!A{sql_row}:L{sql_row}"]
    response = read_source_ranges(ranges)
    values = [(r.get("values") or [[]])[0] for r in response["valueRanges"]]
    return {"spreadsheet_id": MAPPING["workbook"]["spreadsheet_id"], "tab": tab["title"],
            "data_row": row, "header_row": block["header_row"],
            "row_values": values[0], "header_values": values[1],
            "month_columns": block["month_columns"], "row_label": mapping["row_label"],
            "readAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "sql": {"data_row": sql_row, "row_values": values[2], "row_label": sql_tab["row_label"],
                    "month_columns": sql_block["month_columns"],
                    "status": next(m for m in MAPPING["unresolved_metrics"] if m["metric"] == "sql")["status"],
                    "approvalState": candidate["approval_state"]}}


def ai_channel_leads():
    """Read the chatgpt.com lead/SQL tab.

    Column B's own header says source=chatgpt.com, so this is one AI source, not GA4's
    AI Assistant channel and not "AI search" in general. Row 1 is the header; each data
    row starts with a Sheets serial date for the first of that month.
    """
    response = read_source_ranges(["'AI Channel leads'!A1:D40"])
    values = (response["valueRanges"][0].get("values") or [])
    header = values[0] if values else []
    months = []
    for row in values[1:]:
        if not row or not isinstance(row[0], (int, float)):
            continue
        at = lambda i: row[i] if len(row) > i and row[i] != "" else None
        months.append({"month": (date(1899, 12, 30) + timedelta(days=int(row[0]))).strftime("%Y-%m"),
                       "leads": at(1), "sql": at(2), "cvr": at(3)})
    return {"tab": "AI Channel leads", "sourceLabel": (header[1] if len(header) > 1 else "") or "source=chatgpt.com",
            "header": header, "months": months}


def column_index(letter):
    return ord(letter) - ord("A")


def main():
    problems = []
    evidence = {"retrievedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "gsc": {}, "gscPages": {}, "gscQueries": {}, "sitemaps": {}, "sitemapDetails": [],
                "ga4": {}, "ga4Monthly": {}, "geo": {}, "business": {}, "aiChannel": {},
                "cwv": {}, "problems": problems}
    details = {}

    for args, body in payloads(RAW / "gsc_data.json", problems):
        site = args["site_url"]
        # get_sitemaps and get_sitemap_details both arrive without a dimensions argument;
        # only the latter names a sitemap_url, and dispatching on that keeps the per-site
        # sitemap listing from being overwritten by the last detail call.
        if "sitemap_url" in args:
            details[(site, args["sitemap_url"])] = {"site_url": site, **body}
            continue
        if "dimensions" not in args:
            evidence["sitemaps"][site] = body
            continue
        if args["dimensions"] == "date":
            evidence["gsc"].setdefault(site, {})[args["start_date"][5:7]] = body
        elif args["dimensions"] == "page":
            evidence["gscPages"][site] = body
        elif args["dimensions"] == "query":
            evidence["gscQueries"][site] = body

    # get_sitemaps only returns a status label; get_sitemap_details carries the
    # last_submitted/last_downloaded dates and the submitted/indexed breakdown that
    # actually explain a warning or error count.
    # A detail call that just failed must not be back-filled from an older transcript:
    # "no longer a submitted sitemap" is the finding, and a stale copy would hide it.
    failed = {(p["args"].get("site_url"), p["args"].get("sitemap_url")) for p in problems
              if p["call"] == "get_sitemap_details"}
    sitemap_detail_path = RAW / "gsc_sitemap_data.json"
    if sitemap_detail_path.exists():
        for args, body in payloads(sitemap_detail_path, problems):
            key = (args["site_url"], args["sitemap_url"])
            if key in failed:
                continue
            # The same detail may also be in gsc_data.json; that copy is pulled in the same
            # run as everything else, so it wins over this standalone transcript.
            details.setdefault(key, {"site_url": args["site_url"], **body})
    evidence["sitemapDetails"] = [details[key] for key in sorted(details)]

    for args, body in payloads(RAW / "ga4_data.json"):
        # Two shapes share one property id: the hostname x channel report the existing
        # sections read, and the yearMonth series the trend chart needs. Keyed apart so
        # neither overwrites the other.
        slot = "ga4Monthly" if "yearMonth" in (args.get("dimensions") or []) else "ga4"
        evidence[slot][args["property_id"]] = body

    # Core Web Vitals come from the CrUX API, not from an MCP server, so the pull is a
    # plain JSON body rather than a tool transcript. Absent file means the section stays
    # PENDING and renders its own explanation.
    crux_path = RAW / "crux_data.json"
    if crux_path.exists():
        evidence["cwv"] = json.loads(crux_path.read_text())

    prior = json.loads(PRIOR_EVIDENCE.read_text())
    evidence["geo"] = {"snapshot": prior["geo"], "snapshotRetrievedAt": prior["retrievedAt"],
                       "reason": "Workduo MCP is not reachable from this runtime; the 2026-09-06 pull is reused verbatim."}
    evidence["business"] = business_actuals()
    evidence["aiChannel"] = ai_channel_leads()
    evidence["contracts"] = {"ga4_scope": GA4_SCOPE["scope_version"], "business_mapping": MAPPING["mapping_version"]}

    (OUT / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=1))
    row, columns = evidence["business"]["row_values"], evidence["business"]["month_columns"]
    print("business row label:", row[0])
    for month, letter in columns.items():
        print(f"  month {month}: column {letter} =", row[column_index(letter)])
    print("gsc sites:", {site: sorted(months) for site, months in evidence["gsc"].items()})
    print("sitemap details:", len(evidence["sitemapDetails"]))
    for problem in problems:
        target = problem["args"].get("sitemap_url") or problem["args"].get("site_url") or ""
        print(f"  略過 {problem['call']} {target}：{problem['note'].splitlines()[0][:150]}")
    print("ga4 properties:", list(evidence["ga4"]))
    crux = evidence["cwv"].get("results", [])
    print("crux records:", sum(1 for r in crux if r.get("record")), "of", len(crux), "requested")
    print("wrote", OUT / "evidence.json")


main()
