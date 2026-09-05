import copy
import json
import unittest
from datetime import date
from pathlib import Path

from reporting.local_snapshot_adapter import LocalSheetAdapter
from reporting.snapshot_mvp import (
    COLUMNS, CONTRACT, SCOPE, ga4_candidates, ga4_request, mature_on, parse_sheet_values,
    plan_append, plan_sheet_append, report_rows, sheet_values, validate_history,
    verify_readback,
)


def business(**updates):
    # Explicit synthetic unit-test fixture; never uploaded as an actual business result.
    row = dict(loaded_at="2026-09-05T10:00:00+08:00", source="Excel Actual",
               metric_granularity="Monthly", period_start="2026-06-01", period_end="2026-06-30",
               as_of_date="2026-09-05", data_status="Ready", metric_group="Business", metric="sql",
               segment="UNIT_TEST_ONLY", value=12, denominator=None, target=20,
               source_reference="https://docs.google.com/spreadsheets/d/" + CONTRACT["business"]["source_of_truth"]["spreadsheet_id"] + "/edit#test-fixture-not-actual",
               revision_note="UNIT TEST fixture; not business data", contract_version="1.0.0",
               unit="count", source_timezone="Asia/Taipei", supersedes_snapshot_id=None)
    row["platform/property"] = "TW"
    row.update(updates)
    return row


def api_fixture():
    return {"request": ga4_request("tw_main", "2026-09-02"), "response": {
        "dimension_headers": [{"name": name} for name in ("date", "hostName", "sessionDefaultChannelGroup")],
        "metric_headers": [{"name": name} for name in ("sessions", "engagedSessions")],
        "row_count": 2,
        "metadata": {"time_zone": "Asia/Taipei", "data_loss_from_other_row": False, "sampling_metadatas": []},
        "rows": [{"dimension_values": [{"value": "20260902"}, {"value": "shopline.tw"}, {"value": channel}],
                  "metric_values": [{"value": count}, {"value": "1"}]}
                 for channel, count in (("Organic Search", "2"), ("AI Assistant", "1"))]}}


def adapt(envelope):
    return ga4_candidates(envelope, "tw_main", "2026-09-05T10:00:00+08:00", "2026-09-05", "unit-test-only.json")


class ContractTests(unittest.TestCase):
    def test_required_columns(self):
        minimum = "snapshot_id loaded_at source metric_granularity period_start period_end as_of_date data_status metric_group metric segment platform/property value denominator target source_reference revision_note".split()
        self.assertTrue(set(minimum).issubset(COLUMNS))
        self.assertEqual(len(COLUMNS), len(set(COLUMNS)))
        self.assertFalse(CONTRACT["scheduler"]["enabled"])

    def test_ga4_event_mapping_remains_diagnostic(self):
        events = {event["intent"]: event for event in SCOPE["events"]}
        consultation = events["consultation_success"]
        self.assertEqual(consultation["candidate_events"], ["Free_Consultation", "signed_up_tw_consultation"])
        self.assertEqual(consultation["event_classification"], "CANDIDATE_SUCCESS_EVENT")
        self.assertEqual(consultation["mapping_status"], "BUSINESS_CONFIRMATION_REQUIRED")
        self.assertIsNone(consultation["successful_event"])
        self.assertEqual(events["trial_cta"]["event_classification"], "CTA_INTERACTION")
        self.assertIsNone(events["trial_cta"]["successful_event"])

    def test_sql_maturity_boundaries(self):
        self.assertEqual(mature_on("2026-06"), date(2026, 8, 29))
        self.assertEqual(mature_on("2026-07"), date(2026, 9, 29))
        self.assertEqual(mature_on("2024-02"), date(2024, 4, 29))
        for as_of, expected in (("2026-08-28", False), ("2026-08-29", True)):
            view = report_rows(plan_append([], [business(as_of_date=as_of)]), as_of)[0]
            self.assertEqual(view["formal_target_eligible"], expected)
            self.assertEqual(view["formal_trend_eligible"], expected)
            self.assertEqual(view["target_attainment"], 0.6 if expected else None)
            self.assertIsNone(view["rag"])

    def test_immature_sql_retains_display_value(self):
        rows = plan_append([], [business(period_start="2026-07-01", period_end="2026-07-31")])
        view = report_rows(rows, "2026-09-05")[0]
        self.assertEqual(view["value"], 12)
        self.assertFalse(view["mature_cohort"])
        self.assertIsNone(view["target_attainment"])

    def test_all_non_ready_states_block_formal_conclusions(self):
        for status in ("Partial", "Stale", "Failed"):
            value = None if status == "Failed" else 12
            view = report_rows(plan_append([], [business(data_status=status, value=value)]), "2026-09-05")[0]
            self.assertFalse(view["formal_target_eligible"])
            self.assertFalse(view["formal_trend_eligible"])
            self.assertIsNone(view["target_attainment"])
            self.assertIsNone(view["rag"])

    def test_ga4_cannot_replace_business_actuals(self):
        with self.assertRaises(ValueError):
            plan_append([], [business(source="GA4")])

    def test_wrong_business_source_reference(self):
        with self.assertRaises(ValueError):
            plan_append([], [business(source_reference="made-up-source")])

    def test_invalid_values_are_not_zero(self):
        for value in (None, "N/A", "", float("nan"), float("inf"), True, -1, 0.5):
            with self.subTest(value=value), self.assertRaises(ValueError):
                plan_append([], [business(value=value)])
        self.assertEqual(plan_append([], [business(value=0)])[0]["value"], 0)

    def test_unknown_contract_does_not_reinterpret_history(self):
        with self.assertRaises(ValueError):
            plan_append([], [business(contract_version="2.0.0")])

    def test_sql_cannot_use_event_month_or_daily_grain(self):
        for change in ({"metric_granularity": "Daily"}, {"period_start": "2026-06-02"}, {"period_end": "2026-06-29"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                plan_append([], [business(**change)])

    def test_future_or_invalid_dates_rejected(self):
        for change in ({"as_of_date": "2026-09-06"}, {"loaded_at": "2026-09-05T10:00:00"}, {"period_end": "2026-02-30"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                plan_append([], [business(**change)])

    def test_unknown_targets_and_zero_targets_are_not_rates(self):
        for target in (None, 0):
            view = report_rows(plan_append([], [business(target=target)]), "2026-09-05")[0]
            self.assertIsNone(view["target_attainment"])


class AppendTests(unittest.TestCase):
    def test_retry_is_noop_even_with_new_load_time(self):
        first = plan_append([], [business()])
        self.assertEqual(plan_append(first, [business(loaded_at="2026-09-05T11:00:00+08:00")]), [])
        self.assertEqual(len(plan_append([], [business(), business()])), 1)

    def test_revision_preserves_original(self):
        original = plan_append([], [business()])
        before = copy.deepcopy(original)
        corrected = business(value=13, supersedes_snapshot_id=original[0]["snapshot_id"], revision_note="Approved source correction: unit test")
        appended = plan_append(original, [corrected])
        self.assertEqual(original, before)
        self.assertEqual(appended[0]["revision"], 2)
        self.assertEqual(len(validate_history(original + appended)), 1)
        self.assertEqual(plan_append(original + appended, [corrected]), [])

    def test_source_reference_correction_creates_revision(self):
        original = plan_append([], [business()])
        corrected = business(source_reference=business()["source_reference"] + "&corrected=true",
                             supersedes_snapshot_id=original[0]["snapshot_id"],
                             revision_note="Approved source-reference correction: unit test")
        appended = plan_append(original, [corrected])
        self.assertEqual(appended[0]["revision"], 2)
        self.assertEqual(appended[0]["source_reference"], corrected["source_reference"])

    def test_unannounced_or_wrong_revision_rejected(self):
        first = plan_append([], [business()])
        for reference in (None, "unknown"):
            with self.assertRaises(ValueError):
                plan_append(first, [business(value=13, supersedes_snapshot_id=reference)])

    def test_reverting_value_is_a_new_explicit_revision(self):
        first = plan_append([], [business()])
        second = plan_append(first, [business(value=13, supersedes_snapshot_id=first[0]["snapshot_id"])])
        third = plan_append(first + second, [business(supersedes_snapshot_id=second[0]["snapshot_id"])])
        self.assertEqual(third[0]["revision"], 3)

    def test_latest_failed_does_not_fall_back_to_ready(self):
        first = plan_append([], [business()])
        second = plan_append(first, [business(value=None, data_status="Failed", supersedes_snapshot_id=first[0]["snapshot_id"])])
        view = report_rows(first + second, "2026-09-05")[0]
        self.assertIsNone(view["value"])
        self.assertFalse(view["formal_target_eligible"])

    def test_tamper_duplicates_and_missing_chain_fail_closed(self):
        first = plan_append([], [business()])
        tampered = copy.deepcopy(first)
        tampered[0]["value"] = 99
        for history in (tampered, first + first):
            with self.assertRaises(ValueError):
                validate_history(history)
        second = plan_append(first, [business(value=13, supersedes_snapshot_id=first[0]["snapshot_id"])])
        with self.assertRaises(ValueError):
            validate_history(second)
        with self.assertRaises(ValueError):
            report_rows(tampered, "2026-09-05")

    def test_staleness_and_time_travel_gates(self):
        first = plan_append([], [business()])
        view = report_rows(first, "2026-09-06")[0]
        self.assertEqual(view["effective_status"], "Stale")
        self.assertIsNone(view["target_attainment"])
        with self.assertRaises(ValueError):
            report_rows(first, "2026-09-04")

    def test_float_readback_is_numerically_equivalent(self):
        rows = plan_append([], [business()])
        values = sheet_values(rows)
        values[1][COLUMNS.index("value")] = 12.0
        values[1][COLUMNS.index("revision")] = 1.0
        self.assertEqual(parse_sheet_values(values), rows)


class Ga4Tests(unittest.TestCase):
    def test_real_shape_produces_four_behavior_snapshots(self):
        rows = plan_append([], adapt(api_fixture()))
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["data_status"] == "Ready" for row in rows))
        self.assertTrue(all(not row["formal_target_eligible"] for row in report_rows(rows, "2026-09-05")))

    def test_missing_channel_is_partial_not_zero(self):
        envelope = api_fixture()
        envelope["response"]["rows"].pop()
        envelope["response"]["row_count"] = 1
        rows = adapt(envelope)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["data_status"] == "Partial" for row in rows))

    def test_truncated_empty_duplicate_and_wrong_scope_rejected(self):
        changes = [lambda r: r.update(row_count=100), lambda r: r.update(rows=[], row_count=0),
                   lambda r: r["rows"].__setitem__(1, copy.deepcopy(r["rows"][0])),
                   lambda r: r["rows"][0]["dimension_values"][1].update(value="marketing.shopline.tw"),
                   lambda r: r["rows"][0]["metric_values"][0].update(value="N/A")]
        for change in changes:
            envelope = api_fixture()
            change(envelope["response"])
            with self.assertRaises(ValueError):
                adapt(envelope)

    def test_sampling_threshold_and_timezone_rejected(self):
        for update in ({"sampling_metadatas": [{}]}, {"subject_to_thresholding": True}, {"time_zone": "UTC"}, {"data_loss_from_other_row": True}):
            envelope = api_fixture()
            envelope["response"]["metadata"].update(update)
            with self.assertRaises(ValueError):
                adapt(envelope)

    def test_filter_removal_is_rejected(self):
        envelope = api_fixture()
        del envelope["request"]["dimension_filter"]
        with self.assertRaises(ValueError):
            adapt(envelope)


class SheetPlanTests(unittest.TestCase):
    def test_local_storage_adapter_exercises_read_append_readback_retry(self):
        adapter = LocalSheetAdapter(123)
        first = plan_sheet_append(123, adapter.read_values(), [business()])
        adapter.apply(first)
        self.assertEqual(verify_readback(first, adapter.read_values()), {"status": "PASS", "rows": 1, "appended": 1})
        retry = plan_sheet_append(123, adapter.read_values(), [business()])
        self.assertEqual(retry["requests"], [])

    def test_append_readback_retry_and_uncertain_delivery_recovery(self):
        plan = plan_sheet_append(123, [COLUMNS], [business()])
        self.assertEqual(list(plan["requests"][0]), ["appendCells"])
        self.assertEqual(verify_readback(plan, plan["expected_values"])["appended"], 1)
        retry = plan_sheet_append(123, plan["expected_values"], [business()])
        self.assertEqual(retry["requests"], [])
        with self.assertRaises(ValueError):
            verify_readback(plan, [COLUMNS])

    def test_blank_missing_values_roundtrip_as_null(self):
        rows = plan_append([], [business(value=None, data_status="Partial")])
        values = sheet_values(rows)
        self.assertEqual(values[1][COLUMNS.index("value")], "")
        self.assertIsNone(parse_sheet_values(values)[0]["value"])

    def test_bad_header_rejected_before_write(self):
        with self.assertRaises(ValueError):
            plan_sheet_append(123, [["wrong"]], [business()])

    def test_formula_like_text_is_literal_string_not_formula(self):
        plan = plan_sheet_append(123, [COLUMNS], [business(segment="=NOT_A_FORMULA")])
        cell = plan["requests"][0]["appendCells"]["rows"][0]["values"][COLUMNS.index("segment")]
        self.assertEqual(cell["userEnteredValue"], {"stringValue": "=NOT_A_FORMULA"})

    def test_template_no_longer_uses_instant_sql_maturity(self):
        template = Path("spreadsheet_build/build_seo_geo_reporting_framework_v1.mjs").read_text()
        self.assertNotIn("不使用 60 天成熟期", template)
        self.assertNotIn("已填入 SQL 視為成熟", template)


if __name__ == "__main__":
    unittest.main()
