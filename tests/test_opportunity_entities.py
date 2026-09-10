import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from reporting.opportunity.entities import (
    ENTITY_TYPES,
    MAPPING_VERSION,
    NORMALIZATION_VERSION,
    REGISTRY_VERSION,
    URL_POLICY_VERSION,
    RegistryInputError,
    build_registry,
    make_business_theme,
    make_competitor,
    make_keyword,
    make_prompt,
    make_query,
    make_relation,
    make_topic,
    make_url,
    normalize_domain,
    normalize_text,
    normalize_url,
    registry_semantic_hash,
    serialize_registry,
    validate_registry,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "opportunity_registry" / "synthetic_registry.json"
SCHEMA = ROOT / "contracts" / "canonical_registry.v1.proposal.json"


class OpportunityEntityNormalizationTests(unittest.TestCase):
    def test_unicode_width_whitespace_and_latin_case_are_deterministic(self):
        self.assertEqual(normalize_text("  ＥＣＯ　Platform  "), "eco platform")
        self.assertEqual(normalize_text("網路開店"), "網路開店")
        self.assertNotEqual(normalize_text("網路開店"), normalize_text("網店"))

    def test_keyword_ids_are_stable_and_metrics_are_not_identity(self):
        first = make_keyword(" 電商平台 ", locale="zh-TW", country_database="TW")
        second = make_keyword("電商平台", locale="zh-TW", country_database="TW")
        self.assertEqual(first["keyword_id"], second["keyword_id"])
        self.assertEqual(first["normalization_version"], NORMALIZATION_VERSION)
        self.assertNotIn("volume", first)
        self.assertNotIn("difficulty", first)
        self.assertNotIn("position", first)

    def test_query_and_keyword_keep_separate_source_grains(self):
        keyword = make_keyword("台灣電商平台")
        query = make_query("台灣電商平台")
        self.assertNotEqual(keyword["keyword_id"], query["query_id"])
        self.assertEqual(keyword["normalized_text"], query["normalized_text"])

    def test_prompt_is_independent_from_keyword(self):
        keyword = make_keyword("電商平台推薦")
        prompt = make_prompt(
            "台灣有哪些適合新手的電商平台？",
            project_id="synthetic-project",
            provider_query_id="prompt-001",
            prompt_version="v1",
            region="TW",
        )
        self.assertNotEqual(keyword["keyword_id"], prompt["prompt_id"])
        self.assertIn("prompt_text", prompt)
        self.assertIn("platform", prompt)

    def test_url_policy_preserves_semantic_variants_and_removes_allowlisted_tracking(self):
        clean = normalize_url("https://shopline.tw/foo/?q=Two&tag=One")
        tracked = normalize_url("https://SHOPLINE.tw/foo/?q=Two&utm_source=x&tag=One#fragment")
        self.assertEqual(clean, tracked)
        self.assertNotEqual(normalize_url("https://shopline.tw/foo"), normalize_url("https://shopline.tw/foo/"))
        self.assertNotEqual(normalize_url("https://shopline.tw/Foo"), normalize_url("https://shopline.tw/foo"))
        self.assertIn("q=Two", clean)
        self.assertIn("tag=One", clean)
        self.assertEqual(URL_POLICY_VERSION, "url-sanitization.v1")

    def test_url_rejects_credentials_and_pii_like_query(self):
        for value in ("https://user:pass@shopline.tw/foo", "https://shopline.tw/foo?customer_email=x"):
            with self.assertRaises(RegistryInputError) as ctx:
                normalize_url(value)
            self.assertEqual(ctx.exception.code, "INVALID_URL_IDENTITY")

    def test_domain_policy_does_not_merge_parent_child_or_www(self):
        self.assertEqual(normalize_domain("WACA.EXAMPLE."), "waca.example")
        self.assertNotEqual(normalize_domain("www.example.com"), normalize_domain("example.com"))
        parent = make_competitor("Brand", domain="brand.example", competitor_id="COMP_BRAND")
        child = make_competitor("Brand Plus", domain="plus.brand.example", competitor_id="COMP_BRAND_PLUS")
        self.assertNotEqual(parent["competitor_id"], child["competitor_id"])
        with self.assertRaises(RegistryInputError) as port_error:
            normalize_domain("brand.example:invalid")
        self.assertEqual(port_error.exception.code, "INVALID_DOMAIN")


class OpportunityEntityRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE.read_text())

    def test_fixture_has_all_entity_types_and_is_valid(self):
        self.assertEqual(set(self.fixture["entities"]), set(ENTITY_TYPES))
        result = validate_registry(self.fixture)
        self.assertTrue(result.is_valid, result.as_dict())
        self.assertEqual(self.fixture["registry_version"], REGISTRY_VERSION)
        self.assertEqual(self.fixture["mapping_version"], MAPPING_VERSION)
        self.assertTrue(self.fixture["metadata"]["synthetic"])
        self.assertEqual(
            self.fixture["metadata"]["revision_manifest"]["revision_id"],
            self.fixture["mapping_version"],
        )

    def test_registry_schema_is_valid_and_fixture_passes(self):
        schema = json.loads(SCHEMA.read_text())
        Draft202012Validator.check_schema(schema)
        errors = list(Draft202012Validator(schema).iter_errors(self.fixture))
        self.assertEqual(errors, [])
        self.assertEqual(schema["x-proposal-status"], "DRAFT_NOT_APPROVED")
        self.assertFalse(schema["x-production-activation"])

    def test_relations_have_provenance_and_review_state(self):
        relations = self.fixture["relations"]
        self.assertTrue(relations)
        self.assertTrue(all(item["mapping_method"] in {"MANUAL", "CURATED", "RULE_BASED", "IMPORTED"} for item in relations))
        self.assertTrue(all(item["review_state"] in {"CANDIDATE", "APPROVED", "REJECTED"} for item in relations))
        approved = [item for item in relations if item["review_state"] == "APPROVED"]
        self.assertTrue(approved)
        self.assertTrue(all(item["reviewed_by_id"] for item in approved))
        self.assertFalse(any(item["mapping_method"] == "LLM_INFERRED" for item in relations))

    def test_dangling_relation_is_rejected(self):
        invalid = copy.deepcopy(self.fixture)
        invalid["relations"][0]["target_entity_id"] = "KW_MISSING"
        result = validate_registry(invalid)
        self.assertIn("DANGLING_REFERENCE", {error.code for error in result.errors})

    def test_duplicate_and_conflicting_entity_ids_are_rejected(self):
        duplicate = copy.deepcopy(self.fixture)
        duplicate["entities"]["KEYWORD"].append(copy.deepcopy(duplicate["entities"]["KEYWORD"][0]))
        result = validate_registry(duplicate)
        self.assertIn("DUPLICATE_ENTITY_ID", {error.code for error in result.errors})

        conflict = copy.deepcopy(self.fixture)
        conflict["entities"]["KEYWORD"].append(copy.deepcopy(conflict["entities"]["KEYWORD"][0]))
        conflict["entities"]["KEYWORD"][-1]["text"] = "不同 canonical value"
        result = validate_registry(conflict)
        self.assertIn("CANONICAL_VALUE_CONFLICT", {error.code for error in result.errors})

    def test_approved_rule_based_relation_cannot_pass_review_gate(self):
        invalid = copy.deepcopy(self.fixture)
        relation = invalid["relations"][0]
        relation["review_state"] = "APPROVED"
        relation["mapping_method"] = "RULE_BASED"
        relation["reviewed_by_id"] = "reviewer:synthetic"
        result = validate_registry(invalid)
        self.assertIn("UNAPPROVED_RELATION", {error.code for error in result.errors})

    def test_invalid_relation_type_and_self_relation_are_rejected(self):
        invalid = copy.deepcopy(self.fixture)
        relation = invalid["relations"][0]
        relation["relation_type"] = "TOPIC_HAS_URL"
        result = validate_registry(invalid)
        self.assertIn("INVALID_RELATION_TYPE", {error.code for error in result.errors})

        url = make_url("https://shopline.tw/foo")
        self_relation = make_relation(
            "URL_CANONICALIZES_TO",
            source_entity_type="URL",
            source_entity_id=url["url_id"],
            target_entity_type="URL",
            target_entity_id="URL_OTHER",
        )
        registry = build_registry({"URL": [url]}, [self_relation])
        self_relation["target_entity_id"] = url["url_id"]
        result = validate_registry(registry | {"relations": [self_relation]})
        self.assertIn("INVALID_RELATION_TYPE", {error.code for error in result.errors})

    def test_semantic_hash_and_serialization_ignore_input_order_and_runtime_timestamps(self):
        reversed_registry = copy.deepcopy(self.fixture)
        reversed_registry["entities"]["KEYWORD"].reverse()
        reversed_registry["relations"].reverse()
        reversed_registry["metadata"]["policy_gaps"].reverse()
        reversed_registry["entities"]["TOPIC"][0]["business_theme_refs"].reverse()
        reversed_registry["metadata"]["created_at"] = "2026-01-01T00:00:00Z"
        original_hash = registry_semantic_hash(self.fixture)
        reversed_hash = registry_semantic_hash(reversed_registry)
        self.assertEqual(original_hash, reversed_hash)
        self.assertEqual(serialize_registry(self.fixture), serialize_registry(self.fixture))

    def test_identity_and_evidence_separation_is_explicit(self):
        for entities in self.fixture["entities"].values():
            for entity in entities:
                self.assertNotIn("volume", entity)
                self.assertNotIn("clicks", entity)
                self.assertNotIn("impressions", entity)
                self.assertNotIn("position", entity)

    def test_url_canonical_relation_requires_explicit_candidate_mapping(self):
        observed = make_url("https://shopline.tw/foo")
        canonical = make_url("https://shopline.tw/foo/")
        relation = make_relation(
            "URL_CANONICALIZES_TO",
            source_entity_type="URL",
            source_entity_id=observed["url_id"],
            target_entity_type="URL",
            target_entity_id=canonical["url_id"],
        )
        registry = build_registry({"URL": [observed, canonical]}, [relation])
        self.assertTrue(validate_registry(registry).is_valid)

    def test_metadata_policy_gaps_are_explicit(self):
        gaps = self.fixture["metadata"]["policy_gaps"]
        self.assertIn("HTTP_HTTPS_EQUIVALENCE_UNRESOLVED", gaps)
        self.assertIn("TRAILING_SLASH_EQUIVALENCE_UNRESOLVED", gaps)

    def test_missing_is_not_empty_or_zero(self):
        self.assertNotIn("volume", self.fixture["entities"]["KEYWORD"][0])
        self.assertNotIn("priority", self.fixture["entities"]["TOPIC"][0])
        self.assertNotIn("business_priority", self.fixture["entities"]["BUSINESS_THEME"][0])

    def test_error_code_inventory_is_stable(self):
        unknown = copy.deepcopy(self.fixture)
        unknown["entities"]["UNKNOWN"] = []
        self.assertIn("UNKNOWN_ENTITY_TYPE", {error.code for error in validate_registry(unknown).errors})

        invalid_value = copy.deepcopy(self.fixture)
        invalid_value["entities"]["KEYWORD"][0]["normalized_text"] = "wrong"
        self.assertIn("INVALID_NORMALIZED_VALUE", {error.code for error in validate_registry(invalid_value).errors})

        invalid_policy = copy.deepcopy(self.fixture)
        invalid_policy["metadata"]["policy_gaps"] = [""]
        self.assertIn("POLICY_GAP", {error.code for error in validate_registry(invalid_policy).errors})

        with self.assertRaises(RegistryInputError) as domain_error:
            normalize_domain("not-a-domain")
        self.assertEqual(domain_error.exception.code, "INVALID_DOMAIN")


if __name__ == "__main__":
    unittest.main()
