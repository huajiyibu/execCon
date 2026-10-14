import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.bundle_set import BundleSetError, freeze_bundle_set, load_bundle_set
from execcon_v2.interference import (
    build_duplicate,
    build_irrelevant,
    build_unsupported_conflict,
    misbind_evidence,
)
from execcon_v2.qualify import QualificationError, qualify_candidates


class ExperimentDomainTests(unittest.TestCase):
    def candidates(self):
        return [
            {
                "candidate_id": "cand-0",
                "specialist": "numerics_stats",
                "claim": "Produced the required option-pricing outputs.",
                "bundle_hash": "a" * 64,
                "session_id_hash": "1" * 64,
                "producer_id": "cand-0:producer",
                "provenance": {"task_id": "task-a", "spec_sha256": "c" * 64, "pool_sha256": "d" * 64, "validator_version": "v1"},
                "files": [
                    {"path": "results.json", "sha256": "1" * 64, "size": 100},
                    {"path": "exercise_boundary_tier2.npy", "sha256": "2" * 64, "size": 800},
                ],
                "evidence": {
                    "calls": [{"tool": "write_text", "ok": True}],
                    "artifacts": [{"path": "results.json", "sha256": "1" * 64}],
                    "snapshot_id": "snap-0",
                    "runtime_checks": {"public_self_check": "pass"},
                },
            },
            {
                "candidate_id": "cand-1",
                "specialist": "runtime_base",
                "claim": "Produced an independent implementation.",
                "bundle_hash": "b" * 64,
                "session_id_hash": "2" * 64,
                "producer_id": "cand-1:producer",
                "provenance": {"task_id": "task-a", "spec_sha256": "c" * 64, "pool_sha256": "d" * 64, "validator_version": "v1"},
                "files": [
                    {"path": "results.json", "sha256": "3" * 64, "size": 100},
                    {"path": "exercise_boundary_tier2.npy", "sha256": "4" * 64, "size": 800},
                ],
                "evidence": {
                    "calls": [{"tool": "write_bytes", "ok": True}],
                    "artifacts": [{"path": "results.json", "sha256": "3" * 64}],
                    "snapshot_id": "snap-1",
                    "runtime_checks": {"public_self_check": "pass"},
                },
            },
        ]

    def test_bundle_set_is_content_addressed_and_ordered(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            frozen = freeze_bundle_set(
                root,
                task_id="task-a",
                spec_sha256="c" * 64,
                pool_sha256="d" * 64,
                candidates=self.candidates(),
            )
            loaded = load_bundle_set(frozen)
            self.assertEqual(loaded["bundle_set_hash"], frozen.name)
            self.assertEqual([c["candidate_id"] for c in loaded["candidates"]], ["cand-0", "cand-1"])

    def test_qualification_is_frozen_before_treatment(self):
        result = qualify_candidates(
            self.candidates(),
            required_outputs=["results.json", "exercise_boundary_tier2.npy"],
            required_specialists=["numerics_stats", "runtime_base"],
        )
        self.assertTrue(result["covered"])
        self.assertTrue(result["recoverable"])
        self.assertEqual(result["n_complete_candidates"], 2)
        self.assertNotIn("pass_rate", json.dumps(result))

    def test_qualification_fails_without_two_complete_candidates(self):
        candidates = self.candidates()
        candidates[1]["files"] = [{"path": "results.json", "sha256": "3" * 64, "size": 100}]
        with self.assertRaises(QualificationError):
            qualify_candidates(
                candidates,
                required_outputs=["results.json", "exercise_boundary_tier2.npy"],
                required_specialists=["numerics_stats", "runtime_base"],
            )

    def test_recoverable_requires_complete_provenance(self):
        candidates = self.candidates()
        candidates[0]["provenance"].pop("pool_sha256")
        with self.assertRaises(QualificationError):
            qualify_candidates(
                candidates,
                required_outputs=["results.json", "exercise_boundary_tier2.npy"],
                required_specialists=["numerics_stats", "runtime_base"],
            )

    def test_duplicate_is_exact_and_marks_same_provenance(self):
        duplicate = build_duplicate(self.candidates()[0], instance_id="dup-1")
        self.assertEqual(duplicate["bundle_hash"], "a" * 64)
        self.assertEqual(duplicate["duplicate_of"], "cand-0")
        self.assertEqual(duplicate["evidence"], self.candidates()[0]["evidence"])

    def test_irrelevant_has_no_required_output_overlap(self):
        irrelevant = build_irrelevant(["results.json", "exercise_boundary_tier2.npy"])
        paths = {f["path"] for f in irrelevant["files"]}
        self.assertFalse(paths & {"results.json", "exercise_boundary_tier2.npy"})
        self.assertEqual(irrelevant["evidence"]["runtime_checks"]["relation"], "irrelevant")

    def test_unsupported_conflict_has_no_supporting_evidence(self):
        conflict = build_unsupported_conflict("tier2.american_put_price", 999.0)
        self.assertIn("999.0", conflict["claim"])
        self.assertEqual(conflict["files"], [])
        self.assertEqual(conflict["evidence"]["calls"], [])
        self.assertEqual(conflict["evidence"]["artifacts"], [])

    def test_misbound_evidence_preserves_candidates_but_rotates_evidence(self):
        candidates = self.candidates()
        misbound = misbind_evidence(candidates)
        self.assertEqual([c["claim"] for c in misbound], [c["claim"] for c in candidates])
        self.assertEqual(misbound[0]["evidence"], candidates[1]["evidence"])
        self.assertEqual(misbound[1]["evidence"], candidates[0]["evidence"])


if __name__ == "__main__":
    unittest.main()
