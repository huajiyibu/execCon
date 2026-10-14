import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.summary import summarize_cells


class SummaryTests(unittest.TestCase):
    def test_summary_keeps_infrastructure_failures_out_of_score_denominator(self):
        cells = [
            {"condition": "base", "treatment": "E0", "status": "graded", "pass": False, "score": 0.0},
            {"condition": "base", "treatment": "E1", "status": "graded", "pass": True, "score": 1.0},
            {"condition": "irrelevant", "treatment": "E0", "status": "infrastructure_error"},
        ]
        report = summarize_cells(cells)
        self.assertEqual(report["n_graded"], 2)
        self.assertEqual(report["n_infrastructure"], 1)
        self.assertEqual(report["mean_score"], 0.5)
        self.assertEqual(report["paired"]["base"]["pass_delta_e1_minus_e0"], 1)
        self.assertEqual(report["paired"]["base"]["score_delta_e1_minus_e0"], 1.0)


if __name__ == "__main__":
    unittest.main()
