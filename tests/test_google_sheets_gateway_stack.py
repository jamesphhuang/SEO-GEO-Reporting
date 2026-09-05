import copy
import json
import socket
import unittest
from urllib.error import URLError

from reporting.google_sheets_gateway import GoogleSheetsGateway
from reporting.google_sheets_snapshot_adapter import GoogleSheetsSnapshotAdapter
from reporting.snapshot_mvp import COLUMNS, CONTRACT


def candidate(**updates):
    row = {
        "loaded_at": "2026-09-06T10:00:00+08:00", "source": "Excel Actual",
        "metric_granularity": "Monthly", "period_start": "2026-06-01", "period_end": "2026-06-30",
        "as_of_date": "2026-09-05", "data_status": "Ready", "metric_group": "Business", "metric": "sql",
        "segment": "UNIT_TEST_ONLY", "platform/property": "TW", "value": 12,
        "denominator": None, "target": 20,
        "source_reference": "https://docs.google.com/spreadsheets/d/" + CONTRACT["business"]["source_of_truth"]["spreadsheet_id"] + "/edit#gateway-stack-test",
        "revision_note": "UNIT TEST fixture; not business data", "contract_version": CONTRACT["contract_version"],
        "unit": "count", "source_timezone": "Asia/Taipei", "supersedes_snapshot_id": None,
    }
    row.update(updates)
    return row


class Response:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class InMemorySheetsApi:
    def __init__(self):
        self.values = [["KPI Snapshots v2"], ["description"], [], list(COLUMNS)]
        self.batch_calls = 0
        self.timeout_after_append = False

    def __call__(self, request, timeout):
        if request.method == "GET":
            if "?fields=" in request.full_url:
                return Response({"sheets": [{"properties": {"sheetId": 823104256, "title": "KPI Snapshots v2"}}]})
            return Response({"values": copy.deepcopy(self.values)})
        self.batch_calls += 1
        for request_body in json.loads(request.data.decode())["requests"]:
            for row in request_body["appendCells"]["rows"]:
                cells = []
                for cell in row["values"]:
                    value = cell.get("userEnteredValue", {})
                    cells.append(value.get("stringValue", value.get("numberValue", "")))
                self.values.append(cells)
        if self.timeout_after_append:
            raise URLError(socket.timeout("synthetic timeout after dispatch"))
        return Response({})


def storage(api):
    gateway = GoogleSheetsGateway(lambda: "injected-test-token", opener=api, api_root="https://example.test")
    return GoogleSheetsSnapshotAdapter(gateway, "test-spreadsheet", "KPI Snapshots v2", 823104256, header_row=4)


class GoogleSheetsGatewayStackTests(unittest.TestCase):
    def test_full_python_stack_inserts_retries_revises_and_rejects_invalid_payload(self):
        api = InMemorySheetsApi()
        snapshots = storage(api)
        self.assertEqual(snapshots.append_if_new([candidate()]).appended_count, 1)
        self.assertEqual(snapshots.append_if_new([candidate()]).appended_count, 0)
        previous = snapshots.resolve_latest_revision(candidate())
        corrected = candidate(value=13, source_reference=candidate()["source_reference"] + "&corrected=true",
                              revision_note="Approved source correction: stack test",
                              supersedes_snapshot_id=previous["snapshot_id"])
        self.assertEqual(snapshots.append_if_new([corrected]).appended_count, 1)
        invalid = snapshots.append_if_new([candidate(value=None)])
        self.assertEqual((invalid.storage_status, invalid.appended_count, api.batch_calls), ("Failed", 0, 2))
        self.assertEqual(snapshots.read_snapshots()[-1]["revision"], 2)

    def test_full_python_stack_reconciles_a_timeout_without_replay(self):
        api = InMemorySheetsApi()
        api.timeout_after_append = True
        result = storage(api).append_if_new([candidate()])
        self.assertEqual((result.storage_status, result.appended_count, api.batch_calls), ("Ready", 1, 1))
