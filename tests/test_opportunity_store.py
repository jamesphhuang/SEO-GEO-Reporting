import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from reporting.opportunity.candidate_store import CandidateStore
from reporting.opportunity.evidence import EvidenceStore
from reporting.opportunity.store.errors import ImmutableStoreError
from reporting.opportunity.store.manifest import RunManifestStore
from reporting.opportunity.store.serialization import content_hash


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = json.loads((ROOT / "tests/fixtures/opportunity_registry/synthetic_registry.json").read_text(encoding="utf-8"))
E1 = json.loads((ROOT / "tests/fixtures/opportunity_store/evidence_revision_1.json").read_text(encoding="utf-8"))
E2 = json.loads((ROOT / "tests/fixtures/opportunity_store/evidence_revision_2.json").read_text(encoding="utf-8"))


class OpportunityStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.evidence = EvidenceStore(self.temp.name, registry=REGISTRY)
        self.e1 = self.evidence.append_evidence(E1)

    def tearDown(self):
        self.temp.cleanup()

    def candidate(self, **overrides):
        value = {
            "record_type": "CANDIDATE",
            "candidate_id": "CANDIDATE_SYNTHETIC_CONTENT_GAP",
            "revision": 1,
            "topic_ref": {"entity_type": "TOPIC", "entity_id": "TOPIC_ECOMMERCE_PLATFORM_COMPARISON"},
            "evidence_refs": [{"evidence_id": self.e1["evidence_id"], "revision": 1, "content_hash": self.e1["content_hash"]}],
            "status": "CANDIDATE",
            "review_state": "UNREVIEWED",
            "opportunity_type": "PENDING_EVIDENCE_ONLY",
            "score": None,
            "confidence": None,
            "created_at": "2026-09-01T04:00:00+00:00",
        }
        value.update(overrides)
        return value

    def evidence_variant(self, base, **overrides):
        value = dict(base)
        value.pop("content_hash", None)
        value.update(overrides)
        return value

    def test_evidence_round_trip_history_and_latest(self):
        self.assertEqual(self.evidence.get_evidence(self.e1["evidence_id"], 1)["value"], 1200)
        e2 = self.evidence.append_evidence(E2)
        self.assertEqual(self.evidence.get_evidence(self.e1["evidence_id"])["revision"], 2)
        self.assertEqual([r["revision"] for r in self.evidence.history(self.e1["evidence_id"])], [1, 2])
        self.assertEqual(e2["value"], 1300)

    def test_candidate_pins_old_evidence_after_new_evidence_revision(self):
        candidates = CandidateStore(self.temp.name, evidence_store=self.evidence, registry=REGISTRY)
        c1 = candidates.append_candidate(self.candidate())
        self.evidence.append_evidence(E2)
        self.assertEqual(candidates.resolve_candidate_evidence(c1["candidate_id"])[0]["revision"], 1)
        self.assertEqual(candidates.resolve_candidate_evidence(c1["candidate_id"])[0]["value"], 1200)

    def test_duplicate_same_hash_is_idempotent_without_new_line(self):
        before = self.evidence.path.read_text(encoding="utf-8").count("\n")
        result = self.evidence.append_evidence(E1)
        self.assertTrue(result["idempotent"])
        self.assertEqual(self.evidence.path.read_text(encoding="utf-8").count("\n"), before)

    def test_same_revision_different_hash_fails_closed(self):
        altered = self.evidence_variant(E1, value=9999)
        with self.assertRaises(ImmutableStoreError) as ctx:
            self.evidence.append_evidence(altered)
        self.assertEqual(ctx.exception.code, "REVISION_CONFLICT")

    def test_revision_gap_and_invalid_supersedes(self):
        gap = self.evidence_variant(E2, revision=3, supersedes_revision=2)
        with self.assertRaises(ImmutableStoreError) as ctx:
            self.evidence.append_evidence(gap)
        self.assertEqual(ctx.exception.code, "REVISION_GAP")
        bad = self.evidence_variant(E2, supersedes_revision=7)
        with self.assertRaises(ImmutableStoreError) as ctx:
            self.evidence.append_evidence(bad)
        self.assertEqual(ctx.exception.code, "INVALID_SUPERSEDES")

    def test_invalid_record_does_not_write(self):
        before = self.evidence.path.read_text(encoding="utf-8")
        bad = self.evidence_variant(E1, evidence_id="EVIDENCE_BAD", revision=2, source_class="FIRST_PARTY_SEARCH_ACTUAL")
        with self.assertRaises(ImmutableStoreError) as ctx:
            self.evidence.append_evidence(bad)
        self.assertEqual(ctx.exception.code, "INVALID_SOURCE_SEMANTICS")
        self.assertEqual(self.evidence.path.read_text(encoding="utf-8"), before)

    def test_source_semantics_are_preserved(self):
        self.assertEqual(self.e1["source_class"], "THIRD_PARTY_ESTIMATE")
        with self.assertRaises(ImmutableStoreError) as ctx:
            self.evidence.append_evidence(self.evidence_variant(E2, source_class="FIRST_PARTY_SEARCH_ACTUAL"))
        self.assertEqual(ctx.exception.code, "INVALID_SOURCE_SEMANTICS")

    def test_missing_is_not_zero_and_states_are_preserved(self):
        missing = self.evidence_variant(E2, evidence_id="EVIDENCE_MISSING", revision=1, value=None, freshness_state="NOT_AVAILABLE", supersedes_evidence_id=None, supersedes_revision=None)
        stored = self.evidence.append_evidence(missing)
        self.assertIsNone(stored["value"])
        self.assertEqual(stored["freshness_state"], "NOT_AVAILABLE")
        stale = self.evidence_variant(E2, evidence_id="EVIDENCE_STALE", revision=1, value=1200, freshness_state="STALE", supersedes_evidence_id=None, supersedes_revision=None)
        self.assertEqual(self.evidence.append_evidence(stale)["freshness_state"], "STALE")

    def test_failed_and_unavailable_cannot_be_zero_or_value(self):
        bad = self.evidence_variant(E2, evidence_id="EVIDENCE_FAILED", revision=1, freshness_state="FAILED", value=0, supersedes_evidence_id=None, supersedes_revision=None)
        with self.assertRaises(ImmutableStoreError) as ctx:
            self.evidence.append_evidence(bad)
        self.assertEqual(ctx.exception.code, "INVALID_VALUE")

    def test_dangling_entity_ref_is_rejected(self):
        bad = self.evidence_variant(E2, evidence_id="EVIDENCE_DANGLING", revision=1, supersedes_evidence_id=None, supersedes_revision=None, entity_refs=[{"entity_type": "KEYWORD", "entity_id": "KW_DOES_NOT_EXIST"}])
        with self.assertRaises(ImmutableStoreError) as ctx:
            self.evidence.append_evidence(bad)
        self.assertEqual(ctx.exception.code, "UNRESOLVED_ENTITY")

    def test_candidate_requires_exact_revision_and_hash(self):
        candidates = CandidateStore(self.temp.name, evidence_store=self.evidence, registry=REGISTRY)
        missing = self.candidate(evidence_refs=[{"evidence_id": self.e1["evidence_id"], "revision": 2, "content_hash": "0" * 64}])
        with self.assertRaises(ImmutableStoreError) as ctx:
            candidates.append_candidate(missing)
        self.assertEqual(ctx.exception.code, "MISSING_EVIDENCE_REVISION")
        drift = self.candidate(evidence_refs=[{"evidence_id": self.e1["evidence_id"], "revision": 1, "content_hash": "0" * 64}])
        with self.assertRaises(ImmutableStoreError) as ctx:
            candidates.append_candidate(drift)
        self.assertEqual(ctx.exception.code, "CANDIDATE_EVIDENCE_DRIFT")

    def test_candidate_revision_lineage_and_duplicate(self):
        candidates = CandidateStore(self.temp.name, evidence_store=self.evidence, registry=REGISTRY)
        c1 = candidates.append_candidate(self.candidate())
        c2 = self.candidate(revision=2, supersedes_candidate_id=c1["candidate_id"], supersedes_revision=1, status="VALIDATED")
        c2["created_at"] = "2026-09-02T04:00:00+00:00"
        c2 = candidates.append_candidate(c2)
        self.assertEqual([r["revision"] for r in candidates.history(c1["candidate_id"])], [1, 2])
        self.assertTrue(candidates.append_candidate(c2)["idempotent"])

    def test_candidate_dangling_topic_is_rejected(self):
        candidates = CandidateStore(self.temp.name, evidence_store=self.evidence, registry=REGISTRY)
        with self.assertRaises(ImmutableStoreError) as ctx:
            candidates.append_candidate(self.candidate(topic_ref={"entity_type": "TOPIC", "entity_id": "TOPIC_NONE"}))
        self.assertEqual(ctx.exception.code, "UNRESOLVED_ENTITY")

    def test_nonfinite_values_fail_closed(self):
        bad = self.evidence_variant(E2, evidence_id="EVIDENCE_NAN", revision=1, value=float("nan"), supersedes_evidence_id=None, supersedes_revision=None)
        with self.assertRaises(ImmutableStoreError) as ctx:
            self.evidence.append_evidence(bad)
        self.assertEqual(ctx.exception.code, "NONFINITE_NUMBER")

    def test_explicit_date_and_datetime_validation(self):
        bad_date = self.evidence_variant(E2, evidence_id="EVIDENCE_BAD_DATE", revision=1, period_start="not-a-date", supersedes_evidence_id=None, supersedes_revision=None)
        with self.assertRaises(ImmutableStoreError) as ctx:
            self.evidence.append_evidence(bad_date)
        self.assertEqual(ctx.exception.code, "INVALID_DATE")
        bad_time = self.evidence_variant(E2, evidence_id="EVIDENCE_BAD_TIME", revision=1, retrieved_at="2026-09-02T03:00:00", supersedes_evidence_id=None, supersedes_revision=None)
        with self.assertRaises(ImmutableStoreError) as ctx:
            self.evidence.append_evidence(bad_time)
        self.assertEqual(ctx.exception.code, "NAIVE_DATETIME")

    def test_content_hash_is_deterministic_and_excludes_runtime_fields(self):
        a = dict(E1, created_at="2026-09-01T00:00:00+00:00", status="A")
        b = dict(E1, created_at="2026-09-02T00:00:00+00:00", status="B")
        self.assertEqual(content_hash(a), content_hash(b))

    def test_store_reloads_without_rewriting_history(self):
        EvidenceStore(self.temp.name, registry=REGISTRY)
        reloaded = EvidenceStore(self.temp.name, registry=REGISTRY)
        self.assertEqual(reloaded.get_evidence(self.e1["evidence_id"], 1)["content_hash"], self.e1["content_hash"])

    def test_persisted_tamper_fails_closed_on_reload(self):
        tampered = dict(self.e1, value=9999)
        with self.evidence.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(tampered, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
        with self.assertRaises(ImmutableStoreError) as ctx:
            EvidenceStore(self.temp.name, registry=REGISTRY)
        self.assertEqual(ctx.exception.code, "HASH_MISMATCH")

    def test_candidate_has_no_update_api(self):
        candidates = CandidateStore(self.temp.name, evidence_store=self.evidence, registry=REGISTRY)
        self.assertFalse(hasattr(candidates, "update_candidate"))

    def test_run_manifest_is_append_only_and_idempotent(self):
        manifests = RunManifestStore(self.temp.name)
        manifest = {"run_id": "fixture-run-001", "source_status": {"AHREFS": "SUCCESS"}, "evidence_ids": [self.e1["evidence_id"]], "candidate_ids": []}
        first = manifests.append(manifest)
        second = manifests.append(manifest)
        self.assertTrue(second["idempotent"])
        self.assertEqual(manifests.get("fixture-run-001")["content_hash"], first["content_hash"])
        with self.assertRaises(ImmutableStoreError) as ctx:
            manifests.append({**manifest, "source_status": {"AHREFS": "FAILED"}})
        self.assertEqual(ctx.exception.code, "REVISION_CONFLICT")

    def test_proposal_schema_accepts_canonical_records(self):
        schema = json.loads((ROOT / "contracts/opportunity_store.v1.proposal.json").read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(self.e1)), [])
        candidate = self.candidate()
        candidate["content_hash"] = content_hash(candidate)
        self.assertEqual(list(validator.iter_errors(candidate)), [])

    def test_negative_fixture_catalog_is_json_and_named(self):
        negative = json.loads((ROOT / "tests/fixtures/opportunity_store/negative_records.json").read_text(encoding="utf-8"))
        self.assertEqual(set(negative), {"invalid_source_class", "revision_gap", "dangling_entity", "missing_evidence_revision", "non_finite"})


if __name__ == "__main__":
    unittest.main()
