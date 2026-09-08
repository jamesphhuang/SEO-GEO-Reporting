"""Thin Google Sheets v4 helper sharing one refreshed access token per run."""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CREDENTIAL = (Path(__file__).resolve().parents[3] / "98_環境設定" / "google-sheets" / "authorized_user.json")
API = "https://sheets.googleapis.com/v4/spreadsheets"
_token = None


def _open(request, timeout):
    """Retry the transient 5xx responses Google's endpoints occasionally return."""
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code < 500 or attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))


def token():
    global _token
    if _token is None:
        credential = json.loads(CREDENTIAL.read_text())
        form = urllib.parse.urlencode({
            "client_id": credential["client_id"], "client_secret": credential["client_secret"],
            "refresh_token": credential["refresh_token"], "grant_type": "refresh_token"}).encode()
        _token = json.loads(_open(urllib.request.Request(credential["token_uri"], data=form), 20))["access_token"]
    return _token


def call(method, path, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(API + path, data=body, method=method, headers={
        "Authorization": "Bearer " + token(), "Content-Type": "application/json"})
    try:
        return json.loads(_open(request, 60) or b"{}")
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Sheets {method} {path.split('?')[0]} -> {error.code}\n{error.read().decode()[:800]}")


def metadata(spreadsheet_id, fields="spreadsheetId,properties.title,sheets.properties"):
    return call("GET", f"/{spreadsheet_id}?fields={urllib.parse.quote(fields)}")


def batch_update(spreadsheet_id, requests):
    return call("POST", f"/{spreadsheet_id}:batchUpdate", {"requests": requests})


def write_values(spreadsheet_id, data):
    return call("POST", f"/{spreadsheet_id}/values:batchUpdate",
                {"valueInputOption": "RAW", "data": data})


def read_values(spreadsheet_id, ranges):
    query = urllib.parse.urlencode([("ranges", r) for r in ranges] + [("valueRenderOption", "UNFORMATTED_VALUE")])
    return call("GET", f"/{spreadsheet_id}/values:batchGet?{query}")
