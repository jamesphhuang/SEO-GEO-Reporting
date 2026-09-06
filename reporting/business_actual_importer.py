"""Read-only importer from approved business-actual sheet rows to snapshot candidates.

The importer never calls a Sheets writer. It normalizes one monthly source row at a
time, preserves missing values as null, and reports validation issues instead of
guessing a metric, segment, value, or source location.
"""

import calendar
import json
import math
import re
from datetime import date, datetime
from pathlib import Path

from reporting.snapshot_mvp import CONTRACT, mature_on, validate_payload


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAPPING_PATH = ROOT / "contracts/business_actual_mapping.v1.json"
MISSING_MARKERS = {"", "n/a", "na", "null", "unavailable"}
MONTH_PATTERN = re.compile(r"^(?P<year>\d{4})-(?P<month>0[1-9]|1[0-2])(?:-\d{2})?$")


def load_mapping(path=DEFAULT_MAPPING_PATH):
    """Load and minimally validate the immutable mapping document."""
    document = json.loads(Path(path).read_text())
    if document.get("base_data_contract_version") != CONTRACT["contract_version"]:
        raise ValueError("Business mapping is not pinned to the active data contract")
    workbook = document.get("workbook", {})
    if workbook.get("spreadsheet_id") != CONTRACT["business"]["source_of_truth"]["spreadsheet_id"]:
        raise ValueError("Business mapping references an unapproved workbook")
    if document.get("mapping_policy", {}).get("remote_write_enabled") is not False:
        raise ValueError("Business importer mapping must remain read-only")
    return document


def _error(code, row_number, message, severity="high"):
    return {"code": code, "row": row_number, "severity": severity, "message": message}


def _month_bounds(period):
    if not isinstance(period, str):
        raise ValueError("period must be YYYY-MM")
    match = MONTH_PATTERN.fullmatch(period.strip())
    if not match:
        raise ValueError("period must be YYYY-MM or YYYY-MM-DD")
    year, month = int(match.group("year")), int(match.group("month"))
    if len(period.strip()) == 10:
        try:
            date.fromisoformat(period.strip())
        except ValueError as exc:
            raise ValueError("period contains an invalid calendar date") from exc
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    return start.isoformat(), end.isoformat(), f"{year:04d}-{month:02d}"


def _period_from_row(row):
    if row.get("period") is not None:
        return _month_bounds(row["period"])
    if row.get("year") is not None and row.get("month") is not None:
        return _month_bounds(f"{int(row['year']):04d}-{int(row['month']):02d}")
    raise ValueError("Missing monthly period")


def _number(value, field):
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a nonnegative count")
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        text = value.strip()
        if text.lower() in MISSING_MARKERS:
            return None
        try:
            number = float(text.replace(",", ""))
        except ValueError as exc:
            raise ValueError(f"{field} is not numeric") from exc
    else:
        raise ValueError(f"{field} is not numeric")
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        raise ValueError(f"{field} must be a finite nonnegative integer")
    return int(number)


def _mapping_for(document, metric, source_tab):
    supported = CONTRACT["snapshot"]["supported_metrics"]
    if metric not in supported:
        return None, "UNSUPPORTED_METRIC"
    matches = [
        mapping for mapping in document.get("mappings", [])
        if mapping.get("metric") == metric
        and any(tab.get("title") == source_tab for tab in mapping.get("source_tabs", []))
    ]
    if not matches:
        return None, "SOURCE_NOT_CONFIRMED"
    return matches[0], None


def _tab_mapping(mapping, source_tab):
    for tab in mapping.get("source_tabs", []):
        if tab.get("title") == source_tab:
            return tab
    return None


def _location_matches(tab_mapping, period_key, source_row, source_column):
    if source_row is None or source_column is None:
        return False
    try:
        source_row = int(source_row)
    except (TypeError, ValueError):
        return False
    source_column = str(source_column).upper()
    for block in tab_mapping.get("blocks", []):
        if block.get("data_row") != source_row:
            continue
        if block.get("month_columns", {}).get(period_key[-2:]) == source_column:
            return True
    return False


def _source_reference_ok(reference, mapping):
    return isinstance(reference, str) and CONTRACT["business"]["source_of_truth"]["spreadsheet_id"] in reference and mapping["source"] in {"Excel Actual", "Salesforce", "Salesforce / Excel Actual"}


def _candidate(mapping, row, loaded_at, as_of_date, period_start, period_end, period_key, value, target):
    status = row.get("data_status") or ("Partial" if value is None else "Ready")
    candidate = {
        "loaded_at": loaded_at,
        "source": mapping["source"],
        "metric_granularity": "Monthly",
        "period_start": period_start,
        "period_end": period_end,
        "as_of_date": as_of_date,
        "data_status": status,
        "metric_group": mapping["metric_group"],
        "metric": mapping["metric"],
        "segment": row.get("segment", mapping["segment"]),
        "platform/property": mapping.get("platform_property", "TW"),
        "value": value,
        "denominator": None,
        "target": target,
        "source_reference": row["source_reference"],
        "revision_note": row.get("revision_note") or f"Read-only source normalization: {row['source_tab']} row {row['source_row']}; no remote write",
        "contract_version": CONTRACT["contract_version"],
        "unit": mapping["unit"],
        "source_timezone": mapping["source_timezone"],
        "supersedes_snapshot_id": row.get("supersedes_snapshot_id"),
    }
    return candidate


def import_sheet_rows(rows, mapping_document=None, *, loaded_at, as_of_date):
    """Normalize source rows without persistence.

    Input rows are bounded, already-read sheet records with at least
    ``metric``, ``source_tab``, ``source_row``, ``source_column``, ``period``,
    ``actual``, ``segment``, and ``source_reference``. The return value has
    ``source_records``, ``snapshot_candidates``, ``errors``, and ``summary``.
    """
    document = mapping_document or load_mapping()
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    datetime.fromisoformat(loaded_at.replace("Z", "+00:00"))
    date.fromisoformat(as_of_date)
    source_records, candidates, errors = [], [], []
    seen_keys = set()

    for row_number, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append(_error("INVALID_ROW", row_number, "Source row must be an object"))
            continue
        source_tab = row.get("source_tab")
        metric = row.get("metric")
        mapping, mapping_error = _mapping_for(document, metric, source_tab)
        record = {
            "row": row_number,
            "source_tab": source_tab,
            "source_row": row.get("source_row"),
            "source_column": row.get("source_column"),
            "metric": metric,
            "period": row.get("period"),
            "segment": row.get("segment"),
            "source_reference": row.get("source_reference"),
            "formula": row.get("formula"),
            "value_origin": "raw",
            "maturity_date": None,
            "mature_cohort": None,
            "candidate_status": "REJECTED",
            "issue_codes": [],
        }
        source_records.append(record)

        def fail(code, message, severity="high"):
            record["issue_codes"].append(code)
            errors.append(_error(code, row_number, message, severity))

        if mapping_error:
            fail(mapping_error, f"No evidence-confirmed mapping for metric/tab: {metric}/{source_tab}")
            continue
        tab_mapping = _tab_mapping(mapping, source_tab)
        try:
            period_start, period_end, period_key = _period_from_row(row)
        except (TypeError, ValueError) as exc:
            fail("INVALID_PERIOD", str(exc))
            continue
        record["period"] = period_key
        if not _location_matches(tab_mapping, period_key, row.get("source_row"), row.get("source_column")):
            fail("MAPPING_DRIFT", "Source row/column does not match the checked-in mapping")
            continue
        label = row.get("metric_label", mapping["row_label"])
        if not isinstance(label, str) or label.strip() != mapping["row_label"]:
            fail("MAPPING_DRIFT", "Source metric label differs from the checked-in mapping")
            continue
        if not _source_reference_ok(row.get("source_reference"), mapping):
            fail("SOURCE_REFERENCE_REQUIRED", "Source reference must identify the approved actuals workbook")
            continue
        segment = row.get("segment", mapping["segment"])
        if segment not in mapping.get("allowed_segments", [mapping["segment"]]):
            fail("UNKNOWN_SEGMENT", "Segment is not allowed by the mapping")
            continue
        formula = row.get("formula")
        if formula and mapping.get("formula_policy") == "raw_only":
            fail("FORMULA_VALUE_NOT_ALLOWED", "Actual value cell must be raw under this mapping")
            continue
        if formula:
            record["value_origin"] = "formula_result"
        try:
            value = _number(row.get("actual"), "actual")
            target = _number(row.get("target"), "target")
        except ValueError as exc:
            fail("MALFORMED_NUMBER", str(exc))
            continue
        record["value"] = value
        record["target"] = target
        if mapping["metric"] == "sql":
            maturity = mature_on(period_key)
            record["maturity_date"] = maturity.isoformat()
            record["mature_cohort"] = date.fromisoformat(as_of_date) >= maturity
        key = (mapping["source"], mapping["metric"], period_start, period_end, segment, mapping.get("platform_property", "TW"))
        if key in seen_keys:
            fail("DUPLICATE_BUSINESS_KEY", "A second source row resolves to the same business key")
            continue
        seen_keys.add(key)
        try:
            candidate = _candidate(mapping, {**row, "segment": segment}, loaded_at, as_of_date, period_start, period_end, period_key, value, target)
            validate_payload(candidate)
        except (KeyError, ValueError) as exc:
            fail("SNAPSHOT_VALIDATION", str(exc))
            continue
        record["candidate_status"] = "PARTIAL" if candidate["data_status"] != "Ready" else "READY"
        candidates.append(candidate)

    status_counts = {status: sum(1 for row in source_records if row["candidate_status"] == status) for status in ("READY", "PARTIAL", "REJECTED")}
    return {
        "source_records": source_records,
        "snapshot_candidates": candidates,
        "errors": errors,
        "summary": {
            "input_rows": len(rows),
            "candidate_rows": len(candidates),
            "error_rows": len({error["row"] for error in errors}),
            "error_count": len(errors),
            "candidate_status_counts": status_counts,
            "remote_write": "DISABLED",
        },
    }


__all__ = ["DEFAULT_MAPPING_PATH", "import_sheet_rows", "load_mapping"]
