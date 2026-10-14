import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.convergence import converge, property_comparison
from execcon_v2.inputs import assert_treatment_purity, build_convergence_input
from execcon_v2.interference import build_duplicate, build_irrelevant


class ConvergenceTests(unittest.TestCase):
    def candidates(self):
        return [
            {
                "candidate_id": "cand-0",
                "specialist": "numerics_stats",
                "claim": "Completed all required outputs.",
                "bundle_hash": "a" * 64,
                "files": [{"path": "results.json"}, {"path": "exercise_boundary_tier2.npy"}],
                "evidence": {
                    "calls": [{"tool": "write_text", "ok": True}],
                    "artifacts": [{"path": "results.json"}, {"path": "exercise_boundary_tier2.npy"}],
                    "snapshot_id": "s0",
                    "runtime_checks": {"public_self_check": "pass"},
                },
            },
            {
                "candidate_id": "cand-1",
                "specialist": "runtime_base",
                "claim": "Completed all required outputs.",
                "bundle_hash": "b" * 64,
                "files": [{"path": "results.json"}, {"path": "exercise_boundary_tier2.npy"}],
                "evidence": {
                    "calls": [],
                    "artifacts": [],
                    "snapshot_id": "s1",
                    "runtime_checks": {"public_self_check": "fail"},
                },
            },
        ]

    def test_e0_e1_differ_only_in_evidence_and_use_same_algorithm(self):
        candidates = self.candidates()
        candidates[1]["evidence"]["runtime_checks"]["public_self_check"] = "pass"
        e0 = build_convergence_input("spec", candidates, evidence_visible=False)
        e1 = build_convergence_input("spec", candidates, evidence_visible=True)
        assert_treatment_purity(e0, e1)
        d0 = converge(e0, required_outputs=["results.json", "exercise_boundary_tier2.npy"])
        d1 = converge(e1, required_outputs=["results.json", "exercise_boundary_tier2.npy"])
        self.assertEqual(d0["algorithm"], d1["algorithm"])
        self.assertIn(d0["selected_candidate_id"], {"cand-0", "cand-1"})
        self.assertEqual(d1["selected_candidate_id"], "cand-0")

    def test_duplicate_does_not_change_evidence_visible_decision(self):
        base = self.candidates()
        decision = converge(build_convergence_input("spec", base, evidence_visible=True), required_outputs=["results.json", "exercise_boundary_tier2.npy"])
        duplicated = base + [build_duplicate(base[0], instance_id="dup-0")]
        decision_dup = converge(build_convergence_input("spec", duplicated, evidence_visible=True), required_outputs=["results.json", "exercise_boundary_tier2.npy"])
        comparison = property_comparison(decision, decision_dup)
        self.assertFalse(comparison["decision_flip"])
        self.assertFalse(comparison["artifact_flip"])

    def test_irrelevant_does_not_change_evidence_visible_decision(self):
        base = self.candidates()
        decision = converge(build_convergence_input("spec", base, evidence_visible=True), required_outputs=["results.json", "exercise_boundary_tier2.npy"])
        augmented = base + [build_irrelevant(["results.json", "exercise_boundary_tier2.npy"])]
        decision_aug = converge(build_convergence_input("spec", augmented, evidence_visible=True), required_outputs=["results.json", "exercise_boundary_tier2.npy"])
        self.assertFalse(property_comparison(decision, decision_aug)["decision_flip"])

    def test_order_does_not_change_evidence_visible_decision(self):
        base = self.candidates()
        a = converge(build_convergence_input("spec", base, evidence_visible=True), required_outputs=["results.json", "exercise_boundary_tier2.npy"])
        b = converge(build_convergence_input("spec", list(reversed(base)), evidence_visible=True), required_outputs=["results.json", "exercise_boundary_tier2.npy"])
        self.assertFalse(property_comparison(a, b)["decision_flip"])

    def test_non_hex_bundle_hash_is_not_eligible(self):
        candidates = self.candidates()
        candidates[0]["bundle_hash"] = "z" * 64
        decision = converge(
            build_convergence_input("spec", candidates, evidence_visible=True),
            required_outputs=["results.json", "exercise_boundary_tier2.npy"],
        )
        self.assertEqual(decision["status"], "unresolved")
        self.assertIsNone(decision["selected_candidate_id"])


if __name__ == "__main__":
    unittest.main()
