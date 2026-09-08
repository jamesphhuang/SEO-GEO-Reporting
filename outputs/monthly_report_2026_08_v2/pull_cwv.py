"""Pull Chrome UX Report field data for both origins into raw/crux_data.json.

One queryRecord call per origin x form factor gives the current 28-day window that
Search Console's Core Web Vitals report is based on; one queryHistoryRecord call gives
the 25 preceding windows, which is the only real month-over-month trend available for
anything in the technical section.

The CrUX API accepts a Google API key only — an OAuth access token is rejected with
INVALID_ARGUMENT even when the token is valid, so the project's Sheets/GSC/GA4
credentials cannot be reused here. Put the key in CRUX_API_KEY or on the first line of
98_環境設定/crux/api_key.txt. The key needs the Chrome UX Report API enabled.

Origins with too little Chrome traffic return 404; that is recorded, not fatal, so one
missing site never blocks the other.
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import cwv

OUT = Path(__file__).resolve().parent
DRIVE = OUT.parents[2]
KEY_FILE = DRIVE / "98_環境設定" / "crux" / "api_key.txt"
API = "https://chromeuxreport.googleapis.com/v1"


def api_key():
    key = (os.environ.get("CRUX_API_KEY") or "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text().strip().splitlines()[0].strip()
    if not key:
        raise SystemExit(
            "缺少 CrUX API key。設定環境變數 CRUX_API_KEY，或把金鑰寫入\n"
            f"  {KEY_FILE}\n"
            "金鑰需在 Google Cloud 專案啟用 Chrome UX Report API。")
    return key


def query(endpoint, key, payload):
    """POST one CrUX request. Returns (status, body); 404 means the origin has no data."""
    request = urllib.request.Request(
        f"{API}/records:{endpoint}?key={urllib.parse.quote(key)}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return 200, json.loads(response.read())
        except urllib.error.HTTPError as error:
            body = error.read().decode()
            if error.code == 404:
                return 404, json.loads(body)
            if error.code < 500 or attempt == 3:
                return error.code, json.loads(body)
            time.sleep(1.5 * (attempt + 1))


def main():
    key = api_key()
    results = []
    for origin, origin_label in cwv.ORIGINS:
        for form_factor, form_label in cwv.FORM_FACTORS:
            payload = {"origin": origin, "formFactor": form_factor}
            status, record = query("queryRecord", key, payload)
            history_status, history = query("queryHistoryRecord", key, payload)
            results.append({
                "origin": origin, "originLabel": origin_label,
                "formFactor": form_factor, "formLabel": form_label,
                "status": status, "record": record.get("record") if status == 200 else None,
                "historyStatus": history_status,
                "history": history.get("record") if history_status == 200 else None,
                "error": None if status == 200 else record.get("error", {}).get("message")})
            note = "ok" if status == 200 else f"{status} {results[-1]['error']}"
            print(f"{origin} {form_factor}: {note}; history {history_status}")

    payload = {"retrievedAt": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
               "api": "chromeuxreport.googleapis.com/v1", "results": results}
    target = OUT / "raw" / "crux_data.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=1))
    print("wrote", target)


main()
