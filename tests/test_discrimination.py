import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.discrimination import assess_candidate_discrimination


class DiscriminationTests(unittest.TestCase):
    def candidate(self, cid, digest, check="pass"):
        return {
            "candidate_id": cid,
            "files": [
                {"path": "results.json", "size": 10, "sha256": digest},
                {"path": "exercise_boundary_tier2.npy", "size": 20, "sha256": digest},
            ],
            "evidence": {
                "artifacts": [{"path": "results.json"}],
                "snapshot_id": "snap",
                "runtime_checks": {
                    "public_self_check": check,
                    "required_outputs_present": True,
                },
            },
        }

    def test_identical_valid_candidates_are_diagnostic_only(self):
        result = assess_candidate_discrimination(
            [self.candidate("a", "a" * 64), self.candidate("b", "a" * 64)],
            required_outputs=["results.json", "exercise_boundary_tier2.npy"],
        )
        self.assertFalse(result["eligible"])
        self.assertEqual(result["status"], "diagnostic_only_no_discrimination")

    def test_distinct_artifacts_are_eligible(self):
        result = assess_candidate_discrimination(
            [self.candidate("a", "a" * 64), self.candidate("b", "b" * 64)],
            required_outputs=["results.json", "exercise_boundary_tier2.npy"],
        )
        self.assertTrue(result["eligible"])
        self.assertIn("artifact_content_or_shape_differs", result["reasons"])

    def test_validator_difference_is_eligible(self):
        result = assess_candidate_discrimination(
            [self.candidate("a", "a" * 64), self.candidate("b", "a" * 64, check="fail")],
            required_outputs=["results.json", "exercise_boundary_tier2.npy"],
        )
        self.assertTrue(result["eligible"])


if __name__ == "__main__":
    unittest.main()
