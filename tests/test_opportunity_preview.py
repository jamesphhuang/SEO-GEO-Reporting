import copy
import json
import unittest
from pathlib import Path

from reporting.opportunity.report_projection import (
    PreviewProjectionError,
    project_opportunity_preview,
    render_opportunity_preview,
    sanitize_cell,
    validate_opportunity_preview,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads((ROOT / "tests/fixtures/opportunity_preview/scenarios.json").read_text(encoding="utf-8"))


class OpportunityPreviewTests(unittest.TestCase):
    def setUp(self):
        self.input = FIXTURE

    def project(self, value=None, **kwargs):
        return project_opportunity_preview(value or self.input, **kwargs)

    def test_fixture_is_synthetic_and_has_a_to_p(self):
        self.assertTrue(FIXTURE["metadata"]["synthetic"])
        self.assertEqual(len(FIXTURE["candidates"]), 16)
        self.assertEqual([item["candidate_id"][-1] for item in FIXTURE["candidates"]], list("ABCDEFGHIJKLMNOP"))

    def test_projection_schema_and_four_groups(self):
        payload = self.project()
        result = validate_opportunity_preview(payload)
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual([group["group_id"] for group in payload["groups"]], ["QUICK_WINS", "CONTENT_GAPS", "GEO_GAPS", "CONTENT_DECAY_TECHNICAL_UNLOCK"])

    def test_first_screen_cap_is_twenty_and_does_not_drop_details(self):
        many = copy.deepcopy(self.input)
        many["candidates"] = many["candidates"] + [copy.deepcopy(many["candidates"][0]) for _ in range(10)]
        for index, item in enumerate(many["candidates"][16:], 17):
            item["candidate_id"] = f"CAND_EXTRA_{index}"
        payload = self.project(many, max_candidates=20)
        self.assertEqual(payload["candidate_count"], 26)
        self.assertEqual(len(payload["first_screen"]["candidate_ids"]), 20)
        self.assertTrue(payload["first_screen"]["truncated"])
        self.assertEqual(len(payload["candidates"]), 26)

    def test_sort_uses_persisted_score_without_recomputing(self):
        payload = self.project()
        scores = [(row["source_candidate_id"], (row["score"] or {}).get("value")) for row in payload["candidates"]]
        self.assertEqual(scores[0], ("CAND_WP9_A", 92))
        self.assertFalse(payload["governance"]["score_recomputed"])

    def test_score_confidence_and_review_state_stay_independent(self):
        rows = {row["source_candidate_id"]: row for row in self.project()["candidates"]}
        self.assertEqual(rows["CAND_WP9_C"]["score"]["value"], 86)
        self.assertEqual(rows["CAND_WP9_C"]["confidence"], "LOW")
        self.assertEqual(rows["CAND_WP9_D"]["recommended_action"], "DO_NOTHING")
        self.assertFalse(rows["CAND_WP9_D"]["approval_transition_allowed"])

    def test_all_source_layers_show_dates_estimate_and_missing(self):
        row = next(row for row in self.project()["candidates"] if row["source_candidate_id"] == "CAND_WP9_A")
        self.assertIn("AHREFS", row["source_layers"])
        self.assertTrue(row["source_layers"]["AHREFS"]["missing"])
        self.assertIn("GSC", row["source_layers"])
        self.assertTrue(row["source_layers"]["GSC"]["evidence"][0]["freshness"]["as_of"])
        self.assertFalse(row["source_layers"]["GA4"]["missing"])
        missing_ga4 = next(item for item in self.project()["candidates"] if item["source_candidate_id"] == "CAND_WP9_E")
        self.assertTrue(missing_ga4["source_layers"]["GA4"]["missing"])

    def test_ahrefs_estimate_is_marked_without_becoming_actual(self):
        row = next(row for row in self.project()["candidates"] if row["source_candidate_id"] == "CAND_WP9_I")
        self.assertTrue(row["estimate"]["available"])
        self.assertEqual(row["estimate"]["source"], "AHREFS")
        self.assertTrue(row["source_layers"]["AHREFS"]["is_estimate"])

    def test_ga4_cta_is_diagnostic_only(self):
        row = next(row for row in self.project()["candidates"] if row["source_candidate_id"] == "CAND_WP9_N")
        self.assertEqual(row["diagnostics"]["GA4"]["conversion_boundary"], "DIAGNOSTIC_ONLY")
        self.assertFalse(row["diagnostics"]["GA4"]["cta_is_conversion"])
        self.assertNotIn("lead", json.dumps(row).lower())

    def test_serp_not_checked_is_not_do_nothing(self):
        row = next(row for row in self.project()["candidates"] if row["source_candidate_id"] == "CAND_WP9_F")
        self.assertEqual(row["diagnostics"]["SERP"]["status"], "SERP_NOT_CHECKED")
        self.assertNotEqual(row["diagnostics"]["SERP"]["status"], "DO_NOTHING")

    def test_serp_and_geo_conflict_is_visible(self):
        row = next(row for row in self.project()["candidates"] if row["source_candidate_id"] == "CAND_WP9_L")
        self.assertIn("CROSS_CHANNEL_CONFLICT", row["conflicts"])
        self.assertEqual(row["diagnostics"]["SERP"]["status"], "SERP_VALIDATED")
        self.assertEqual(row["diagnostics"]["GEO"]["status"], "GEO_WEAK")

    def test_geo_mention_citation_and_comparability_are_separate(self):
        row = next(row for row in self.project()["candidates"] if row["source_candidate_id"] == "CAND_WP9_G")
        geo = row["diagnostics"]["GEO"]
        self.assertEqual(geo["mention_state"], "OBSERVED")
        self.assertEqual(geo["citation_state"], "NOT_AVAILABLE")
        self.assertEqual(geo["comparability"]["status"], "COMPARABLE")
        self.assertFalse(row["geo_governance"]["market_wide_claim"])

    def test_missing_and_stale_states_are_not_zero_or_current(self):
        value = copy.deepcopy(self.input)
        value["candidates"][0]["evidence_refs"] = []
        with self.assertRaises(PreviewProjectionError):
            self.project(value)
        row = next(row for row in self.project()["candidates"] if row["source_candidate_id"] == "CAND_WP9_P")
        self.assertIn("fresh_current_evidence", row["gaps"]["missing"])
        self.assertNotEqual(row["source_layers"]["GSC"]["status"], "CURRENT")

    def test_policy_and_capability_gaps_remain_visible(self):
        rows = {row["source_candidate_id"]: row for row in self.project()["candidates"]}
        self.assertIn("CONTENT_GAP_POLICY_UNAPPROVED", rows["CAND_WP9_I"]["gaps"]["policy"])
        self.assertIn("citation", rows["CAND_WP9_G"]["gaps"]["capability"])

    def test_exact_pinned_evidence_refs_are_traceable(self):
        row = next(row for row in self.project()["candidates"] if row["source_candidate_id"] == "CAND_WP9_A")
        self.assertTrue(row["evidence_refs"])
        self.assertTrue(all(set(ref) == {"evidence_id", "revision", "content_hash"} for ref in row["evidence_refs"]))
        self.assertEqual(row["evidence_refs"][0]["content_hash"], "a" * 64)

    def test_preview_and_candidate_ids_are_distinct(self):
        payload = self.project()
        self.assertTrue(payload["preview_id"].startswith("UAT_PREVIEW_"))
        self.assertTrue(all(row["candidate_id"].startswith("UAT_") for row in payload["candidates"]))
        self.assertNotEqual(payload["candidates"][0]["candidate_id"], payload["candidates"][0]["source_candidate_id"])

    def test_deterministic_json_and_semantic_hash(self):
        first = self.project()
        second = self.project()
        self.assertEqual(first, second)
        self.assertEqual(render_opportunity_preview(first), render_opportunity_preview(second))
        self.assertEqual(first["semantic_hash"], second["semantic_hash"])

    def test_projection_does_not_mutate_input(self):
        before = copy.deepcopy(self.input)
        self.project()
        self.assertEqual(self.input, before)

    def test_html_escapes_and_formula_sanitizes(self):
        value = copy.deepcopy(self.input)
        value["candidates"][0]["rationale"] = "<script>alert('x')</script>"
        rendered = render_opportunity_preview(self.project(value), format="html")
        self.assertEqual(sanitize_cell("=SUM(A1)"), "'=SUM(A1)")
        self.assertIn("&lt;script&gt;alert", rendered)
        self.assertIn("<meta name=\"viewport\"", rendered)
        self.assertIn("@media(max-width:375px)", rendered)
        self.assertNotIn("<script>alert", rendered)

    def test_markdown_contains_review_fields(self):
        markdown = render_opportunity_preview(self.project(), format="markdown")
        self.assertIn("Opportunity preview / UAT report", markdown)
        self.assertIn("Confidence", markdown)
        self.assertIn("Missing / conflicts", markdown)

    def test_empty_projection_has_four_empty_groups(self):
        payload = self.project({"candidates": [], "uat_dataset_id": "WP9_EMPTY"})
        self.assertEqual(payload["candidate_count"], 0)
        self.assertTrue(all(group["rows"] == [] for group in payload["groups"]))
        self.assertTrue(validate_opportunity_preview(payload).is_valid)

    def test_corrupt_candidate_fails_closed(self):
        with self.assertRaises(PreviewProjectionError):
            self.project({"candidates": [{"candidate_id": "bad", "revision": 0, "evidence_refs": []}]})

    def test_no_production_destination_flags(self):
        payload = self.project()
        self.assertFalse(payload["governance"]["production_mutation"])
        self.assertFalse(payload["governance"]["recommendations_written"])
        self.assertFalse(payload["governance"]["next_steps_written"])
        self.assertNotIn("Recommendations", render_opportunity_preview(payload, format="html"))
        self.assertNotIn("Next Steps", render_opportunity_preview(payload, format="html"))

    def test_render_json_is_canonical(self):
        rendered = render_opportunity_preview(self.project(), format="json")
        self.assertEqual(json.loads(rendered), self.project())
        self.assertNotIn("\\n", rendered)


if __name__ == "__main__":
    unittest.main()
