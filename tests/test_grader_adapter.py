import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.grader_adapter import OfficialGraderError, grade_with_task


class Result:
    task_id = "task"
    pass_rate = 0.5
    overall_success = False
    n_passed = 1
    n_total = 2
    per_verifier = [{"name": "v", "passed": False}]
    execution_mode = "remote"
    raw = {"pass_rate": 0.5}


class Task:
    def __init__(self):
        self.closed = False

    def submit_dir(self, root):
        return ["results.json"]

    def grade(self, keep_alive=False):
        assert keep_alive is False
        self.closed = True
        return Result()


class WrongResult:
    task_id = "other"
    pass_rate = 0.5
    overall_success = False
    n_passed = 1
    n_total = 2
    per_verifier = []
    execution_mode = "remote"
    raw = {}


class WrongResultTask(Task):
    def grade(self, keep_alive=False):
        return WrongResult()


class FailingTask:
    def submit_dir(self, root):
        raise RuntimeError("submit failed")


class GraderAdapterTests(unittest.TestCase):
    def test_maps_complete_official_result_without_convergence_shape(self):
        with TemporaryDirectory() as tmp:
            record = grade_with_task(Task(), Path(tmp))
        self.assertEqual(record["grader_type"], "official_sdk_task_grade")
        self.assertEqual(record["pass_rate"], 0.5)
        self.assertIn("raw_sha256", record)

    def test_wraps_failure(self):
        with self.assertRaises(OfficialGraderError):
            grade_with_task(FailingTask(), Path("."))

    def test_rejects_task_identity_mismatch(self):
        with self.assertRaises(OfficialGraderError):
            grade_with_task(Task(), Path("."), expected_task_id="other")

    def test_rejects_grade_result_identity_mismatch(self):
        with self.assertRaises(OfficialGraderError):
            grade_with_task(WrongResultTask(), Path("."), expected_task_id="task")


if __name__ == "__main__":
    unittest.main()
