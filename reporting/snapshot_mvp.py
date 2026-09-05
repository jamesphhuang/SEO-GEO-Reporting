"""Validated append-only snapshot planning. No scheduler, credentials or remote writes."""

import calendar
import copy
import hashlib
import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "contracts/data_contract.v1.json").read_text())
SCOPE = json.loads((ROOT / "contracts/ga4_scope.v1.json").read_text())
COLUMNS = CONTRACT["snapshot"]["columns"]
KEY_FIELDS = CONTRACT["snapshot"]["logical_key_fields"]
CONTENT_FIELDS = CONTRACT["snapshot"]["content_fields"]
GENERATED = {"snapshot_id", "logical_key", "revision", "content_hash", "validation_status"}


def validate_scope_contract():
    """Fail closed if the checked-in GA4 event labels are weakened or misused."""
    if SCOPE.get("ga4_admin_mutation") is not False:
        raise ValueError("GA4 admin mutation must remain disabled")
    events = {event["intent"]: event for event in SCOPE["events"]}
    consultation = events.get("consultation_success")
    if not consultation or consultation.get("candidate_events") != ["Free_Consultation", "signed_up_tw_consultation"]:
        raise ValueError("Consultation candidate event contract mismatch")
    if (consultation.get("successful_event") is not None
            or consultation.get("event_classification") != "CANDIDATE_SUCCESS_EVENT"
            or consultation.get("mapping_status") != "BUSINESS_CONFIRMATION_REQUIRED"):
        raise ValueError("Consultation candidates cannot be promoted to success")
    for intent in ("trial_cta", "consultation_cta"):
        event = events.get(intent)
        if not event or event.get("successful_event") is not None or event.get("event_classification") != "CTA_INTERACTION":
            raise ValueError("CTA interaction cannot be promoted to success")


validate_scope_contract()


def digest(value):
    def normalized(item):
        if isinstance(item, dict):
            return {key: normalized(val) for key, val in item.items()}
        if isinstance(item, (list, tuple)):
            return [normalized(val) for val in item]
        if type(item) is float and math.isfinite(item) and item.is_integer():
            return int(item)
        return item

    value = normalized(value)
    data = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def iso_date(value):
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("Expected YYYY-MM-DD")
    return date.fromisoformat(value)


def mature_on(cohort_month):
    first = iso_date(cohort_month + "-01")
    last = date(first.year, first.month, calendar.monthrange(first.year, first.month)[1])
    return last + timedelta(days=CONTRACT["business"]["sql_maturity"]["days_after_calendar_month_end"])


def validate_payload(row):
    missing = (set(COLUMNS) - GENERATED) - set(row)
    if missing:
        raise ValueError("Missing fields: " + ", ".join(sorted(missing)))
    if set(row) - set(COLUMNS):
        raise ValueError("Unexpected fields")
    if row["contract_version"] != CONTRACT["contract_version"]:
        raise ValueError("Unknown contract version; do not silently migrate history")
    for field in KEY_FIELDS + ["loaded_at", "source_reference", "revision_note", "unit", "source_timezone"]:
        if not isinstance(row[field], str) or not row[field].strip():
            raise ValueError("Empty/non-text field: " + field)
    loaded = datetime.fromisoformat(row["loaded_at"].replace("Z", "+00:00"))
    if loaded.tzinfo is None:
        raise ValueError("loaded_at requires timezone")
    start, end, as_of = [iso_date(row[f]) for f in ("period_start", "period_end", "as_of_date")]
    if as_of > loaded.astimezone(ZoneInfo(CONTRACT["timezone"])).date():
        raise ValueError("as_of_date cannot be after loaded_at in the contract timezone")
    if not start <= end <= as_of:
        raise ValueError("Invalid period/as-of order")
    if row["metric_granularity"] not in {"Daily", "Monthly"}:
        raise ValueError("MVP supports Daily or Monthly observations only")
    if row["metric_granularity"] == "Daily" and start != end:
        raise ValueError("Daily observations must describe exactly one date")
    if row["data_status"] not in CONTRACT["snapshot"]["states"]:
        raise ValueError("Invalid data_status")
    metric = CONTRACT["snapshot"]["supported_metrics"].get(row["metric"])
    if not metric or row["metric_group"] != metric["group"] or row["unit"] != metric["unit"]:
        raise ValueError("Unknown metric/group/unit contract")
    sources = CONTRACT["business"]["source_of_truth"]["allowed_sources"] if metric["source"] == "business" else [metric["source"]]
    if row["source"] not in sources:
        raise ValueError("Metric source is not authoritative")
    if metric["source"] == "business":
        source_id = CONTRACT["business"]["source_of_truth"]["spreadsheet_id"]
        if source_id not in row["source_reference"]:
            raise ValueError("Business rows must reference the approved actuals workbook")
    if row["metric"] == "sql":
        last = date(start.year, start.month, calendar.monthrange(start.year, start.month)[1])
        if row["metric_granularity"] != "Monthly" or start.day != 1 or end != last:
            raise ValueError("SQL must use a full lead-month cohort")
    if row["source"] == "GA4":
        segment = json.loads(row["segment"])
        if row["segment"] != json.dumps(segment, sort_keys=True, separators=(",", ":")):
            raise ValueError("GA4 segment must use canonical JSON")
        site = SCOPE["sites"].get(segment.get("site"))
        if not site or segment != {"site": segment["site"], "hostname": site["hostname"], "channel": segment.get("channel")}:
            raise ValueError("GA4 segment must exactly identify the allowed site/hostname/channel")
        if segment["channel"] not in SCOPE["channels"] or row["platform/property"] != "properties/" + site["property_id"]:
            raise ValueError("GA4 property/channel outside scope")
        if row["source_timezone"] != site["source_timezone"]:
            raise ValueError("Unexpected GA4 source timezone")
    for field in ("value", "denominator", "target"):
        value = row[field]
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError("Expected finite nonnegative number or null: " + field)
    if row["value"] is not None and not float(row["value"]).is_integer():
        raise ValueError("Count metric must be an integer")
    if row["data_status"] == "Ready" and row["value"] is None:
        raise ValueError("Ready cannot contain an unavailable value")
    if row["data_status"] == "Failed" and row["value"] is not None:
        raise ValueError("Failed must not expose a fabricated value")
    if row["supersedes_snapshot_id"] is not None and not isinstance(row["supersedes_snapshot_id"], str):
        raise ValueError("Invalid supersedes_snapshot_id")


def seal(row, revision):
    result = copy.deepcopy(row)
    result["logical_key"] = digest([row[f] for f in KEY_FIELDS])
    result["content_hash"] = digest([row[f] for f in CONTENT_FIELDS])
    result["revision"] = revision
    result["snapshot_id"] = "snap_" + digest([result["logical_key"], result["content_hash"], revision, row["supersedes_snapshot_id"]])
    result["validation_status"] = "Passed"
    return result


def validate_history(rows):
    latest, ids = {}, set()
    for row in rows:
        validate_payload(row)
        if set(row) != set(COLUMNS) or type(row["revision"]) is not int or row["revision"] < 1:
            raise ValueError("Invalid snapshot schema/revision")
        expected = seal(row, row["revision"])
        if any(row[f] != expected[f] for f in GENERATED):
            raise ValueError("Snapshot integrity/validation mismatch")
        if row["snapshot_id"] in ids:
            raise ValueError("Duplicate snapshot_id in storage")
        previous = latest.get(row["logical_key"])
        if row["revision"] != (previous["revision"] + 1 if previous else 1):
            raise ValueError("Missing or unordered revision history")
        if row["supersedes_snapshot_id"] != (previous["snapshot_id"] if previous else None):
            raise ValueError("Broken revision chain")
        if previous and row["as_of_date"] < previous["as_of_date"]:
            raise ValueError("Revision cannot move as-of backward")
        ids.add(row["snapshot_id"])
        latest[row["logical_key"]] = row
    return latest


def plan_append(existing, candidates):
    """Pure single-writer plan. Changed content needs an explicit latest-revision reference."""
    latest = validate_history(existing)
    append = []
    for candidate in candidates:
        validate_payload(candidate)
        key = digest([candidate[f] for f in KEY_FIELDS])
        previous = latest.get(key)
        content_hash = digest([candidate[f] for f in CONTENT_FIELDS])
        if previous and content_hash == previous["content_hash"]:
            continue
        if previous:
            if candidate["supersedes_snapshot_id"] != previous["snapshot_id"]:
                raise ValueError("Correction requires the latest supersedes_snapshot_id")
            if candidate["as_of_date"] < previous["as_of_date"]:
                raise ValueError("Stale source observation cannot revise newer data")
        elif candidate["supersedes_snapshot_id"] is not None:
            raise ValueError("Initial snapshot cannot supersede an unknown row")
        row = seal(candidate, previous["revision"] + 1 if previous else 1)
        append.append(row)
        latest[key] = row
    return append


def report_rows(history, required_as_of):
    """Latest revision first; never fall back to an older Ready row. No RAG thresholds invented."""
    cutoff = iso_date(required_as_of)
    output = []
    for row in validate_history(history).values():
        as_of = iso_date(row["as_of_date"])
        if as_of > cutoff:
            raise ValueError("Future snapshot cannot serve an earlier report cutoff")
        state = "Stale" if row["data_status"] == "Ready" and as_of < cutoff else row["data_status"]
        mature = row["metric"] != "sql" or as_of >= mature_on(row["period_start"][:7])
        eligible = state == "Ready" and mature and row["metric_group"] == "Business"
        target = row["target"]
        output.append({**row, "effective_status": state, "mature_cohort": mature,
                       "formal_trend_eligible": eligible,
                       "formal_target_eligible": eligible and target is not None and target > 0,
                       "target_attainment": row["value"] / target if eligible and target is not None and target > 0 else None,
                       "rag": None})
    return output


def ga4_request(site_key, day):
    iso_date(day)
    site = SCOPE["sites"][site_key]
    return {"property_id": site["property_id"], "date_ranges": [{"start_date": day, "end_date": day}],
            "dimensions": ["date", "hostName", "sessionDefaultChannelGroup"],
            "metrics": ["sessions", "engagedSessions"],
            "dimension_filter": {"and_group": {"expressions": [
                {"filter": {"field_name": "hostName", "string_filter": {"match_type": "EXACT", "value": site["hostname"], "case_sensitive": False}}},
                {"filter": {"field_name": "sessionDefaultChannelGroup", "in_list_filter": {"values": SCOPE["channels"], "case_sensitive": True}}}]}},
            "order_bys": [{"dimension": {"dimension_name": field}} for field in ("date", "hostName", "sessionDefaultChannelGroup")],
            "limit": 100}


def ga4_candidates(envelope, site_key, loaded_at, as_of_date, source_reference):
    """Fail closed on incomplete/empty/ambiguous API responses; never fill missing groups with zero."""
    request, response = envelope["request"], envelope["response"]
    day = request["date_ranges"][0]["start_date"]
    if request != ga4_request(site_key, day):
        raise ValueError("GA4 query differs from the scoped daily contract")
    if [d["name"] for d in response["dimension_headers"]] != request["dimensions"] or [m["name"] for m in response["metric_headers"]] != request["metrics"]:
        raise ValueError("Unexpected GA4 headers")
    rows = response.get("rows", [])
    if response.get("row_count") != len(rows) or not rows:
        raise ValueError("Incomplete or empty response; unavailable is not zero")
    site = SCOPE["sites"][site_key]
    metadata = response.get("metadata", {})
    if metadata.get("time_zone") != site["source_timezone"] or metadata.get("data_loss_from_other_row") is not False or metadata.get("sampling_metadatas") or metadata.get("subject_to_thresholding"):
        raise ValueError("Source metadata fails completeness check")
    result, seen, channels = [], set(), set()
    for api_row in rows:
        dimensions = [v["value"] for v in api_row["dimension_values"]]
        values = [v["value"] for v in api_row["metric_values"]]
        if len(dimensions) != 3 or len(values) != 2 or tuple(dimensions) in seen:
            raise ValueError("Invalid/duplicate GA4 row")
        raw_day, hostname, channel = dimensions
        if raw_day != day.replace("-", "") or hostname != site["hostname"] or channel not in SCOPE["channels"]:
            raise ValueError("GA4 row outside requested scope")
        if any(not isinstance(v, str) or not v.isdecimal() for v in values):
            raise ValueError("Invalid count; no coercion to zero")
        sessions, engaged = map(int, values)
        if engaged > sessions:
            raise ValueError("Engaged sessions exceed sessions")
        seen.add(tuple(dimensions))
        channels.add(channel)
        segment = json.dumps({"site": site_key, "hostname": hostname, "channel": channel}, sort_keys=True, separators=(",", ":"))
        for metric, value in (("sessions", sessions), ("engaged_sessions", engaged)):
            result.append({"loaded_at": loaded_at, "source": "GA4", "metric_granularity": "Daily",
                           "period_start": day, "period_end": day, "as_of_date": as_of_date,
                           "data_status": "Ready", "metric_group": "Behavior", "metric": metric,
                           "segment": segment, "platform/property": "properties/" + site["property_id"],
                           "value": value, "denominator": None, "target": None,
                           "source_reference": source_reference, "revision_note": "Initial observed API snapshot; diagnostic only",
                           "contract_version": CONTRACT["contract_version"], "unit": "count",
                           "source_timezone": site["source_timezone"], "supersedes_snapshot_id": None})
    if channels != set(SCOPE["channels"]):
        for row in result:
            row["data_status"] = "Partial"
            row["revision_note"] = "An expected channel is absent; no zero substituted"
    return result


def sheet_values(history):
    validate_history(history)
    return [COLUMNS] + [["" if row[field] is None else row[field] for field in COLUMNS] for row in history]


def parse_sheet_values(values):
    """Read UNFORMATTED_VALUE (or exact exported cell values). Blank numeric cells stay null."""
    if not values or values[0] != COLUMNS:
        raise ValueError("Sheet header/schema mismatch")
    result = []
    nullable = {"value", "denominator", "target", "supersedes_snapshot_id"}
    for cells in values[1:]:
        if not any(value not in (None, "") for value in cells):
            continue
        if len(cells) > len(COLUMNS):
            raise ValueError("Unexpected extra cells")
        padded = list(cells) + [""] * (len(COLUMNS) - len(cells))
        row = {field: None if field in nullable and value in (None, "") else value for field, value in zip(COLUMNS, padded)}
        # Sheets numeric cells are delivered as floats by some readers.
        if type(row["revision"]) is float and row["revision"].is_integer():
            row["revision"] = int(row["revision"])
        result.append(row)
    validate_history(result)
    return result


def plan_sheet_append(sheet_id, existing_values, candidates):
    """No network effects. Caller must exclusively serialize read -> write -> readback."""
    if type(sheet_id) is not int or sheet_id < 0:
        raise ValueError("Require a metadata-grounded sheetId")
    existing = parse_sheet_values(existing_values)
    appended = plan_append(existing, candidates)
    rows = []
    for row in appended:
        cells = []
        for field in COLUMNS:
            value = row[field]
            cell = {"userEnteredFormat": {"verticalAlignment": "TOP", "wrapStrategy": "CLIP"}}
            if value is not None:
                cell["userEnteredValue"] = {"numberValue" if type(value) in (int, float) else "stringValue": value}
            cells.append(cell)
        rows.append({"values": cells})
    requests = [{"appendCells": {"sheetId": sheet_id, "rows": rows, "fields": "userEnteredValue,userEnteredFormat"}}] if rows else []
    return {"precondition_hash": digest(existing_values), "append": appended, "requests": requests,
            "expected_values": sheet_values(existing + appended)}


def verify_readback(plan, actual_values):
    actual = parse_sheet_values(actual_values)
    expected = parse_sheet_values(plan["expected_values"])
    if actual != expected:
        raise ValueError("Readback mismatch; do not blindly replay the append")
    return {"status": "PASS", "rows": len(actual), "appended": len(plan["append"])}
