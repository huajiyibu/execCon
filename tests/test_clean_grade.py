import base64
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.clean_grade import GradeIntegrityError, stage_and_grade


class CleanGradeTests(unittest.TestCase):
    def test_requires_empty_output_and_verifies_written_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            sandbox = Path(tmp)
            payload = b"ok"
            decision = {"artifacts": [{"path": "results.json", "content_b64": base64.b64encode(payload).decode(), "sha256": "bad"}]}
            with self.assertRaises(GradeIntegrityError):
                stage_and_grade(decision, sandbox=sandbox, grader=lambda _: {"pass_rate": 1, "overall_success": True})

    def test_grader_output_is_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            import hashlib
            payload = b"ok"
            decision = {"artifacts": [{"path": "results.json", "content_b64": base64.b64encode(payload).decode(), "sha256": hashlib.sha256(payload).hexdigest()}]}
            result = stage_and_grade(decision, sandbox=Path(tmp), grader=lambda _: {"pass_rate": 1.0, "overall_success": True})
            self.assertEqual(result["status"], "graded")
            self.assertNotIn("grade", decision)
            self.assertTrue(result["grade"]["overall_success"])


if __name__ == "__main__":
    unittest.main()
