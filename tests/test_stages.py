import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.stages import get_stage


class StageTests(unittest.TestCase):
    def test_h1_h2_h3_pool_sizes(self):
        self.assertEqual(len(get_stage("h1").specialists), 2)
        self.assertEqual(len(get_stage("h2").specialists), 5)
        self.assertEqual(len(get_stage("h3").specialists), 8)

    def test_unknown_stage_rejected(self):
        with self.assertRaises(ValueError):
            get_stage("h4")


if __name__ == "__main__":
    unittest.main()
