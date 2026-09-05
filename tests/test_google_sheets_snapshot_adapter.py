import copy
import unittest

from reporting.google_sheets_snapshot_adapter import GoogleSheetsSnapshotAdapter, SheetSchemaError
from reporting.snapshot_mvp import COLUMNS, CONTRACT


def candidate(**updates):
    row = {
        "loaded_at": "2026-09-05T10:00:00+08:00", "source": "Excel Actual",
        "metric_granularity": "Monthly", "period_start": "2026-06-01", "period_end": "2026-06-30",
        "as_of_date": "2026-09-05", "data_status": "Ready", "metric_group": "Business", "metric": "sql",
        "segment": "UNIT_TEST_ONLY", "platform/property": "TW", "value": 12,
        "denominator": None, "target": 20,
        "source_reference": "https://docs.google.com/spreadsheets/d/" + CONTRACT["business"]["source_of_truth"]["spreadsheet_id"] + "/edit#test-fixture-not-actual",
        "revision_note": "UNIT TEST fixture; not business data", "contract_version": CONTRACT["contract_version"],
        "unit": "count", "source_timezone": "Asia/Taipei", "supersedes_snapshot_id": None,
    }
    row.update(updates)
    return row


class FakeGateway:
    def __init__(self, headers=None):
        self.values = [list(headers or COLUMNS)]
        self.batch_calls = 0
        self.raise_on_write = False
        self.drop_write = False

    def read_values(self, spreadsheet_id, sheet_title, cell_range):
        return copy.deepcopy(self.values)

    def batch_update(self, spreadsheet_id, requests):
        self.batch_calls += 1
        if self.raise_on_write:
            raise RuntimeError("synthetic remote write failure")
        if self.drop_write:
            return
        for request in requests:
            for row in request["appendCells"]["rows"]:
                values = []
                for cell in row["values"]:
                    entered = cell.get("userEnteredValue", {})
                    values.append(entered.get("stringValue", entered.get("numberValue", "")))
                self.values.append(values)


def adapter(gateway, **updates):
    return GoogleSheetsSnapshotAdapter(gateway, "test-spreadsheet", "__TEST__", 123, **updates)


class GoogleSheetsSnapshotAdapterTests(unittest.TestCase):
    def test_append_readback_retry_and_latest_revision(self):
        gateway = FakeGateway()
        storage = adapter(gateway)
        first = storage.append_if_new([candidate()])
        self.assertEqual((first.storage_status, first.appended_count), ("Ready", 1))
        self.assertEqual(len(storage.read_snapshots()), 1)
        self.assertEqual(storage.append_if_new([candidate()]).appended_count, 0)
        previous = storage.resolve_latest_revision(candidate())
        corrected = candidate(value=13, source_reference=candidate()["source_reference"] + "&corrected=true",
                              revision_note="Approved source correction: unit test",
                              supersedes_snapshot_id=previous["snapshot_id"])
        revised = storage.append_snapshots([corrected])
        self.assertEqual((revised.storage_status, revised.appended_count), ("Ready", 1))
        self.assertEqual(storage.find_existing_business_key(corrected)["revision"], 2)
        self.assertEqual(gateway.batch_calls, 2)

    def test_missing_value_stays_blank_and_invalid_ready_value_is_rejected(self):
        gateway = FakeGateway()
        storage = adapter(gateway)
        partial = storage.append_if_new([candidate(data_status="Partial", value=None)])
        self.assertEqual(partial.appended_count, 1)
        self.assertEqual(gateway.values[1][COLUMNS.index("value")], "")
        invalid = storage.append_if_new([candidate(value=None)])
        self.assertEqual((invalid.storage_status, invalid.appended_count), ("Failed", 0))
        self.assertEqual(gateway.batch_calls, 1)

    def test_explicit_header_mapping_serializes_and_deserializes(self):
        headers = ["remote_" + field for field in reversed(COLUMNS)]
        mapping = {field: "remote_" + field for field in COLUMNS}
        gateway = FakeGateway(headers)
        storage = adapter(gateway, header_mapping=mapping)
        result = storage.append_if_new([candidate()])
        self.assertEqual(result.appended_count, 1)
        self.assertEqual(storage.read_snapshots()[0]["value"], 12)

    def test_duplicate_or_unexpected_header_fails_closed(self):
        duplicate = FakeGateway(COLUMNS[:-1] + [COLUMNS[-2]])
        self.assertEqual(adapter(duplicate).append_if_new([candidate()]).storage_status, "Failed")
        unexpected = FakeGateway(COLUMNS[:-1] + ["unexpected"])
        self.assertEqual(adapter(unexpected).append_if_new([candidate()]).appended_count, 0)
        with self.assertRaises(SheetSchemaError):
            adapter(FakeGateway(), header_mapping={"value": "duplicate", "target": "duplicate"})

    def test_remote_failure_or_missing_readback_never_replays(self):
        failed = FakeGateway()
        failed.raise_on_write = True
        result = adapter(failed).append_if_new([candidate()])
        self.assertEqual((result.storage_status, result.appended_count), ("Failed", None))
        dropped = FakeGateway()
        dropped.drop_write = True
        result = adapter(dropped).append_if_new([candidate()])
        self.assertEqual((result.storage_status, result.appended_count), ("Failed", None))
