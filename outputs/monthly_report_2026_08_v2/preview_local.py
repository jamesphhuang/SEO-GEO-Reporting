"""Render Report.html locally against the live workbook.

Mirrors Code.gs readWorkbook() so the template can be checked in a real browser
before it is pasted into Apps Script. Read-only.
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import sheets_api

OUT = Path(__file__).resolve().parent
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
SPREADSHEET_ID = ARGS[0] if ARGS else "14lyC4zotKGBGg90CExf3q-hPk7awRAvUgIoEYAn1QtI"
# Mirrors doGet's ?view=exec so both views can be checked in a browser before deploying.
VIEW = "exec" if "--exec" in sys.argv else "full"


def read_workbook():
    schema_rows = sheets_api.read_values(SPREADSHEET_ID, ["'_Schema'!A1:B50"])["valueRanges"][0]["values"][1:]
    schema = {row[0]: [f.strip() for f in row[1].split(",")] for row in schema_rows if len(row) > 1}
    names = [n for n in schema if n != "_Schema"]
    ranges = [f"'{n}'!A1:{chr(ord('A') + len(schema[n]) - 1)}1000" for n in names]
    fetched = sheets_api.read_values(SPREADSHEET_ID, ranges)["valueRanges"]

    model = {"meta": {}, "tables": {}, "rowCounts": {}}
    for name, block in zip(names, fetched):
        fields = schema[name]
        rows = block.get("values", [])[1:]
        records = []
        for row in rows:
            padded = list(row) + [None] * (len(fields) - len(row))
            if not any(c not in (None, "") for c in padded):
                continue
            records.append({f: (None if padded[i] == "" else padded[i]) for i, f in enumerate(fields)})
        model["rowCounts"][name] = len(records)
        if name == "_Meta":
            for record in records:
                model["meta"][record["key"]] = record["value"]
        else:
            model["tables"][name] = records

    model["workbookUrl"] = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
    model["renderedAt"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    model["timeZone"] = "Asia/Taipei"
    model["view"] = VIEW
    model["scriptUrl"] = ""
    return model


def main():
    model = read_workbook()
    payload = json.dumps(model, ensure_ascii=False).replace("<", "\\u003c")
    template = (OUT / "apps_script" / "Report.html").read_text()
    if "<?!= payload ?>" not in template:
        raise SystemExit("Report.html no longer contains the payload placeholder")
    body = template.replace("<?!= payload ?>", payload)
    html = ('<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<title>{model["meta"].get("reportTitle", "SEO／GEO 月報")}</title></head><body>'
            f'{body}</body></html>')
    target = OUT / ("preview_exec.html" if VIEW == "exec" else "preview.html")
    target.write_text(html)
    print("tabs:", {k: v for k, v in model["rowCounts"].items()})
    print("view:", VIEW, "| meta keys:", list(model["meta"]))
    print("wrote", target, f"({len(html) / 1024:.0f} KB)")


main()
