import copy
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from reporting.opportunity.sources.ahrefs import (
    COMPETITORS_ENDPOINT,
    CONTENT_GAP_ENDPOINT,
    ORGANIC_KEYWORDS_ENDPOINT,
    AhrefsQuery,
    AhrefsQueryBudget,
    AhrefsTransportError,
    ingest_ahrefs,
    normalize_ahrefs_response,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "ahrefs"
RETRIEVED_AT = datetime(2026, 9, 10, tzinfo=timezone.utc)


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text())


def approved_scope():
    return {
        "approval_state": "APPROVED",
        "approval_ref": "SYNTHETIC_SCOPE_APPROVAL",
        "environment": "preview",
        "source_class": "THIRD_PARTY_ESTIMATE",
        "estimation_flag": True,
        "country_database": "TW",
        "scopes": [{"target": "shopline.tw", "mode": "domain"}],
    }


def query(endpoint=ORGANIC_KEYWORDS_ENDPOINT, limit=5, date="2026-09-09"):
    return AhrefsQuery(
        endpoint=endpoint,
        target="https://shopline.tw",
        country="TW",
        date=date,
        select=("keyword", "best_position", "best_position_url", "volume"),
        mode="domain",
        limit=limit,
        scope_id="synthetic-scope",
    )


class FakeTransport:
    def __init__(self, responses=None, errors=None):
        self.responses = list(responses or [])
        self.errors = list(errors or [])
        self.calls = []

    def request(self, endpoint, params):
        self.calls.append((endpoint, copy.deepcopy(dict(params))))
        if self.errors:
            error = self.errors.pop(0)
            if isinstance(error, Exception):
                raise error
            return error
        if not self.responses:
            raise AssertionError("unexpected transport call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class AhrefsNormalizationTests(unittest.TestCase):
    def test_organic_normalization_preserves_estimate_semantics(self):
        records, metadata, warnings = normalize_ahrefs_response(
            ORGANIC_KEYWORDS_ENDPOINT,
            query(),
            load_fixture("organic_keywords_normal.json"),
            retrieved_at=RETRIEVED_AT,
            max_rows=5,
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(metadata["accepted_rows"], 2)
        self.assertEqual(warnings, [])
        record = records[0]
        self.assertEqual(record["source_class"], "THIRD_PARTY_ESTIMATE")
        self.assertTrue(record["estimation_flag"])
        self.assertEqual(record["freshness_state"], "FRESH")
        self.assertEqual(record["metric"], "organic_keyword")
        self.assertNotIn("actual", json.dumps(record).lower())

    def test_competitor_normalization_uses_competitor_metric(self):
        records, metadata, _ = normalize_ahrefs_response(
            COMPETITORS_ENDPOINT,
            query(COMPETITORS_ENDPOINT),
            load_fixture("competitors_normal.json"),
            retrieved_at=RETRIEVED_AT,
        )
        self.assertEqual(len(records), 2)
        self.assertEqual(metadata["accepted_rows"], 2)
        self.assertEqual(records[0]["metric"], "organic_competitor")
        self.assertIsNone(records[0]["keyword"])
        self.assertEqual(records[0]["competitor"], "competitor-one.test")

    def test_missing_optional_metrics_remain_null(self):
        records, _, _ = normalize_ahrefs_response(
            ORGANIC_KEYWORDS_ENDPOINT,
            query(),
            load_fixture("missing_optional.json"),
            retrieved_at=RETRIEVED_AT,
        )
        self.assertEqual(len(records), 1)
        self.assertIsNone(records[0]["volume"])
        self.assertIsNone(records[0]["traffic_estimate"])
        self.assertIsNone(records[0]["difficulty"])
        self.assertNotEqual(records[0]["volume"], 0)

    def test_duplicate_rows_are_dropped_deterministically(self):
        records, metadata, warnings = normalize_ahrefs_response(
            ORGANIC_KEYWORDS_ENDPOINT,
            query(),
            load_fixture("duplicate_rows.json"),
            retrieved_at=RETRIEVED_AT,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(metadata["duplicate_rows"], 1)
        self.assertIn("DUPLICATE_ROWS_DROPPED", warnings)

    def test_malformed_rows_are_quarantined(self):
        records, metadata, warnings = normalize_ahrefs_response(
            ORGANIC_KEYWORDS_ENDPOINT,
            query(),
            load_fixture("malformed.json"),
            retrieved_at=RETRIEVED_AT,
        )
        self.assertEqual(records, [])
        self.assertEqual(metadata["malformed_rows"], 2)
        self.assertIn("MALFORMED_ROWS_DROPPED", warnings)

    def test_unsafe_url_rows_are_quarantined(self):
        payload = load_fixture("organic_keywords_normal.json")
        payload["keywords"][0]["best_position_url"] = "https://user:password@example.test/private"
        records, metadata, warnings = normalize_ahrefs_response(
            ORGANIC_KEYWORDS_ENDPOINT,
            query(),
            payload,
            retrieved_at=RETRIEVED_AT,
        )
        self.assertEqual(len(records), 1)
        self.assertEqual(metadata["malformed_rows"], 1)
        self.assertIn("MALFORMED_ROWS_DROPPED", warnings)

    def test_normalized_hash_excludes_retrieval_time(self):
        payload = load_fixture("organic_keywords_normal.json")
        first, _, _ = normalize_ahrefs_response(
            ORGANIC_KEYWORDS_ENDPOINT,
            query(),
            payload,
            retrieved_at=RETRIEVED_AT,
        )
        second, _, _ = normalize_ahrefs_response(
            ORGANIC_KEYWORDS_ENDPOINT,
            query(),
            payload,
            retrieved_at=RETRIEVED_AT.replace(hour=23),
        )
        self.assertEqual([item["content_hash"] for item in first], [item["content_hash"] for item in second])


class AhrefsIngestionTests(unittest.TestCase):
    def test_scope_must_be_approved_and_non_production(self):
        transport = FakeTransport([load_fixture("organic_keywords_normal.json")])
        scope = approved_scope()
        scope["approval_state"] = "PENDING"
        result = ingest_ahrefs([query()], scope=scope, transport=transport, run_id="scope-pending", git_sha="sha")
        self.assertEqual(result.status, "NOT_AVAILABLE")
        self.assertEqual(result.errors[0]["code"], "SCOPE_NOT_APPROVED")
        self.assertEqual(transport.calls, [])

        scope = approved_scope()
        scope["environment"] = "production"
        result = ingest_ahrefs([query()], scope=scope, transport=transport, run_id="scope-production", git_sha="sha")
        self.assertEqual(result.errors[0]["code"], "PRODUCTION_ENVIRONMENT_BLOCKED")

    def test_row_cap_is_independent_of_provider_limit(self):
        transport = FakeTransport([load_fixture("over_limit.json")])
        budget = AhrefsQueryBudget(max_rows_per_endpoint=3, max_units_per_run=500)
        result = ingest_ahrefs([query(limit=50)], scope=approved_scope(), transport=transport, budget=budget, run_id="row-cap", git_sha="sha")
        self.assertEqual(result.status, "PARTIAL")
        self.assertEqual(len(result.records), 3)
        self.assertEqual(result.manifest["truncated_rows"], 4)
        self.assertTrue(result.manifest["endpoints"][ORGANIC_KEYWORDS_ENDPOINT]["truncated"])
        self.assertEqual(transport.calls[0][1]["limit"], 3)

    def test_pagination_stops_at_page_cap(self):
        transport = FakeTransport([load_fixture("pagination_page_1.json"), load_fixture("pagination_page_2.json")])
        budget = AhrefsQueryBudget(max_pages=1, max_rows_per_endpoint=5)
        result = ingest_ahrefs([query(limit=5)], scope=approved_scope(), transport=transport, budget=budget, run_id="page-cap", git_sha="sha")
        self.assertEqual(result.status, "PARTIAL")
        self.assertEqual(len(result.records), 1)
        self.assertIn("MAX_PAGES_REACHED", result.manifest["warnings"])
        self.assertEqual(len(transport.calls), 1)

    def test_request_and_unit_caps_stop_before_next_call(self):
        transport = FakeTransport([load_fixture("organic_keywords_normal.json"), load_fixture("organic_keywords_normal.json")])
        budget = AhrefsQueryBudget(max_rows_per_endpoint=2, max_units_per_run=100, max_requests_per_run=4)
        result = ingest_ahrefs([query(limit=2), query(limit=2)], scope=approved_scope(), transport=transport, budget=budget, run_id="unit-cap", git_sha="sha")
        self.assertEqual(result.status, "PARTIAL")
        self.assertIn("BUDGET_EXCEEDED", result.manifest["warnings"])
        self.assertEqual(len(transport.calls), 1)

    def test_transient_retry_is_bounded_and_counted(self):
        transport = FakeTransport(
            responses=[load_fixture("organic_keywords_normal.json")],
            errors=[AhrefsTransportError("rate limited", status_code=429)],
        )
        result = ingest_ahrefs([query(limit=2)], scope=approved_scope(), transport=transport, run_id="retry", git_sha="sha", sleep_fn=lambda _: None)
        self.assertEqual(result.status, "READY")
        self.assertEqual(result.manifest["request_count"], 2)
        self.assertEqual(result.manifest["retry_count"], 1)

    def test_auth_failure_is_not_retried(self):
        transport = FakeTransport(errors=[AhrefsTransportError("forbidden", status_code=403)])
        result = ingest_ahrefs([query()], scope=approved_scope(), transport=transport, run_id="auth-failure", git_sha="sha", sleep_fn=lambda _: None)
        self.assertEqual(result.status, "NOT_AVAILABLE")
        self.assertEqual(result.manifest["request_count"], 1)
        self.assertEqual(result.errors[0]["code"], "AUTH_OR_PERMISSION")

    def test_schema_drift_is_failed_closed(self):
        transport = FakeTransport([{"unexpected": []}])
        result = ingest_ahrefs([query()], scope=approved_scope(), transport=transport, run_id="schema-drift", git_sha="sha")
        self.assertEqual(result.status, "FAILED")
        self.assertEqual(result.errors[0]["code"], "SCHEMA_DRIFT")
        self.assertEqual(result.records, [])

    def test_stale_evidence_is_explicit(self):
        transport = FakeTransport([load_fixture("organic_keywords_normal.json")])
        result = ingest_ahrefs(
            [query(date="2026-07-01")],
            scope=approved_scope(),
            transport=transport,
            run_id="stale",
            git_sha="sha",
            started_at=RETRIEVED_AT,
        )
        self.assertEqual(result.status, "STALE")
        self.assertEqual(result.records[0]["freshness_state"], "STALE")

    def test_content_gap_capability_gap_is_explicit(self):
        result = ingest_ahrefs(
            [query(CONTENT_GAP_ENDPOINT)],
            scope=approved_scope(),
            transport=FakeTransport(),
            run_id="content-gap",
            git_sha="sha",
        )
        self.assertEqual(result.status, "NOT_AVAILABLE")
        self.assertIn(CONTENT_GAP_ENDPOINT, result.manifest["endpoint"])
        self.assertIn(f"{CONTENT_GAP_ENDPOINT}:CAPABILITY_GAP", result.manifest["warnings"])

    def test_manifest_and_artifacts_are_bounded_and_redacted(self):
        payload = load_fixture("organic_keywords_normal.json")
        payload["authorization"] = "placeholder"
        transport = FakeTransport([payload])
        with tempfile.TemporaryDirectory() as temp_dir:
            result = ingest_ahrefs([query(limit=2)], scope=approved_scope(), transport=transport, run_id="artifact-run", git_sha="sha", output_dir=temp_dir)
            root = Path(temp_dir) / "artifact-run" / "ahrefs"
            self.assertTrue((root / "run_manifest.json").exists())
            self.assertTrue((root / "raw" / f"{ORGANIC_KEYWORDS_ENDPOINT}.json").exists())
            self.assertTrue((root / "normalized" / f"{ORGANIC_KEYWORDS_ENDPOINT}.json").exists())
            serialized = "\n".join(path.read_text() for path in root.rglob("*.json"))
            for forbidden in ("Authorization", "Bearer", "api_key", "access_token", "client_secret"):
                self.assertNotIn(forbidden, serialized)
            self.assertEqual(result.manifest["git_sha"], "sha")
            self.assertEqual(result.manifest["source_class"], "THIRD_PARTY_ESTIMATE")


if __name__ == "__main__":
    unittest.main()
