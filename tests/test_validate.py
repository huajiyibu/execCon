import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.validate import ValidationError, validate_canary_report


class ValidateTests(unittest.TestCase):
    def row(self, index=0):
        return {
            "status": "ok", "task_id": "task", "stage": "h1", "raw_bytes_equal": True,
            "api_sha256": "a", "remote_sha256": "a", "input_listing": ["problem_spec.md"], "closed": True,
            "session_id_hash": f"{index + 1:064x}", "root_basename": f"sandbox-{index}",
        }

    def test_canary_requires_all_fresh_successful_runs(self):
        report = {"run_type": "canary", "runs": [self.row(), self.row()], "all_passed": True}
        with self.assertRaises(ValidationError):
            validate_canary_report(report, required_runs=3, expected_task_id="task")

    def test_canary_rejects_failed_row(self):
        row = self.row(); row["raw_bytes_equal"] = False
        report = {"run_type": "canary", "runs": [self.row(), self.row(), row], "all_passed": False}
        with self.assertRaises(ValidationError):
            validate_canary_report(report, required_runs=3, expected_task_id="task")

    def test_canary_accepts_complete_report(self):
        report = {"run_type": "canary", "runs": [self.row(0), self.row(1), self.row(2)], "all_passed": True}
        gate = validate_canary_report(report, required_runs=3, expected_task_id="task")
        self.assertTrue(gate["eligible_for_inference"])


if __name__ == "__main__":
    unittest.main()
