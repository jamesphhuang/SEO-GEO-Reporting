import json
import unittest
from pathlib import Path

from reporting.business_actual_importer import import_sheet_rows, load_mapping
from reporting.snapshot_mvp import CONTRACT, plan_append


MAPPING = load_mapping()
SOURCE_ID = CONTRACT["business"]["source_of_truth"]["spreadsheet_id"]
REFERENCE = f"https://docs.google.com/spreadsheets/d/{SOURCE_ID}/edit#gid=1999633447&range=C23"


def row(**updates):
    value = {
        "metric": "non_paid_leads",
        "metric_label": "Non-Paid Leads",
        "source_tab": "2026 lead gen distribution",
        "source_row": 23,
        "source_column": "C",
        "period": "2026-01",
        "actual": 399,
        "target": 474,
        "segment": "all_non_paid",
        "source_reference": REFERENCE,
    }
    value.update(updates)
    return value


class BusinessActualImporterTests(unittest.TestCase):
    def test_mapping_is_pinned_and_only_non_paid_is_confirmed(self):
        self.assertEqual(MAPPING["base_data_contract_version"], "1.0.0")
        self.assertEqual([item["metric"] for item in MAPPING["mappings"]], ["non_paid_leads"])
        self.assertEqual({item["metric"] for item in MAPPING["unresolved_metrics"]}, {"sql", "successful_conversions"})

    def test_valid_monthly_row_normalizes_to_snapshot_candidate(self):
        result = import_sheet_rows([row()], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        self.assertEqual(result["errors"], [])
        candidate = result["snapshot_candidates"][0]
        self.assertEqual(candidate["period_start"], "2026-01-01")
        self.assertEqual(candidate["period_end"], "2026-01-31")
        self.assertEqual(candidate["value"], 399)
        self.assertEqual(candidate["source"], "Excel Actual")

    def test_missing_is_partial_null_and_zero_is_valid_zero(self):
        missing = import_sheet_rows([row(actual="N/A")], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        self.assertEqual(missing["errors"], [])
        self.assertIsNone(missing["snapshot_candidates"][0]["value"])
        self.assertEqual(missing["snapshot_candidates"][0]["data_status"], "Partial")
        zero = import_sheet_rows([row(actual=0)], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        self.assertEqual(zero["snapshot_candidates"][0]["value"], 0)
        self.assertEqual(zero["snapshot_candidates"][0]["data_status"], "Ready")

    def test_malformed_number_is_explicit_error(self):
        result = import_sheet_rows([row(actual="not-a-number")], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        self.assertEqual([error["code"] for error in result["errors"]], ["MALFORMED_NUMBER"])
        self.assertEqual(result["snapshot_candidates"], [])

    def test_duplicate_business_key_is_rejected(self):
        result = import_sheet_rows([row(), row()], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        self.assertEqual(len(result["snapshot_candidates"]), 1)
        self.assertEqual([error["code"] for error in result["errors"]], ["DUPLICATE_BUSINESS_KEY"])

    def test_unsupported_and_unconfirmed_metrics_fail_closed(self):
        unsupported = import_sheet_rows([row(metric="unsupported_metric")], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        self.assertEqual(unsupported["errors"][0]["code"], "UNSUPPORTED_METRIC")
        unresolved = import_sheet_rows([row(metric="sql", metric_label="*SQL")], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        self.assertEqual(unresolved["errors"][0]["code"], "SOURCE_NOT_CONFIRMED")

    def test_unknown_segment_source_reference_and_mapping_drift(self):
        for changes, expected in (({"segment": "paid"}, "UNKNOWN_SEGMENT"), ({"source_reference": "https://example.invalid"}, "SOURCE_REFERENCE_REQUIRED"), ({"source_column": "G"}, "MAPPING_DRIFT"), ({"metric_label": "Paid Leads"}, "MAPPING_DRIFT")):
            result = import_sheet_rows([row(**changes)], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
            self.assertEqual(result["errors"][0]["code"], expected)

    def test_sql_maturity_is_exposed_when_a_test_mapping_allows_sql(self):
        test_mapping = json.loads(json.dumps(MAPPING))
        test_mapping["mappings"].append({
            "metric": "sql", "metric_group": "Business", "source": "Excel Actual",
            "source_tabs": [{"title": "fixture", "blocks": [{"data_row": 2, "month_columns": {"06": "C"}}]}],
            "row_label": "SQL", "unit": "count", "segment": "all_sql", "allowed_segments": ["all_sql"],
            "platform_property": "TW", "source_timezone": "Asia/Taipei", "formula_policy": "raw_or_formula_result",
        })
        result = import_sheet_rows([row(metric="sql", metric_label="SQL", source_tab="fixture", source_row=2, source_column="C", period="2026-06", actual=12, target=20, segment="all_sql", source_reference=REFERENCE)], test_mapping, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        self.assertEqual(result["errors"], [])
        record = result["source_records"][0]
        self.assertEqual(record["maturity_date"], "2026-08-29")
        self.assertTrue(record["mature_cohort"])

    def test_formula_value_is_rejected_for_raw_actual_mapping(self):
        result = import_sheet_rows([row(formula="=C20+C24")], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        self.assertEqual(result["errors"][0]["code"], "FORMULA_VALUE_NOT_ALLOWED")

    def test_correction_reference_is_preserved_for_append_revision_planning(self):
        first = import_sheet_rows([row()], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        history = plan_append([], first["snapshot_candidates"])
        corrected = import_sheet_rows([row(actual=400, supersedes_snapshot_id=history[0]["snapshot_id"], revision_note="Approved source correction; preview only")], MAPPING, loaded_at="2026-09-06T10:00:00+08:00", as_of_date="2026-09-06")
        revision = plan_append(history, corrected["snapshot_candidates"])
        self.assertEqual(revision[0]["revision"], 2)
        self.assertEqual(revision[0]["supersedes_snapshot_id"], history[0]["snapshot_id"])

    def test_contract_file_is_json_and_no_sensitive_fixture(self):
        raw = Path("contracts/business_actual_mapping.v1.json").read_text()
        json.loads(raw)
        self.assertNotIn("access_token", raw)
        self.assertNotIn("refresh_token", raw)
        self.assertNotIn("client_secret", raw)


if __name__ == "__main__":
    unittest.main()
