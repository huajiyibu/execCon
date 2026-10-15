from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


class OfficialGraderError(RuntimeError):
    pass


def grade_with_task(task: Any, output_root: Path, *, expected_task_id: str | None = None, provenance: dict[str, Any] | None = None) -> dict[str, Any]:
    """Submit staged ALE outputs and return an isolated official GradeResult record.

    The returned record is grade-store data and must never be passed to convergence.
    The caller owns task creation and must ensure it is a fresh grading session.
    """
    try:
        if not callable(getattr(task, "submit_dir", None)) or not callable(getattr(task, "grade", None)):
            raise OfficialGraderError("official task lacks submit_dir/grade lifecycle")
        if expected_task_id is not None and getattr(task, "task_id", None) != expected_task_id:
            raise OfficialGraderError("official task identity mismatch")
        written = task.submit_dir(output_root)
        result = task.grade(keep_alive=False)
        if expected_task_id is not None and getattr(result, "task_id", None) != expected_task_id:
            raise OfficialGraderError("official grade result task identity mismatch")
        raw = getattr(result, "raw", {}) or {}
        return {
            "grader_type": "official_sdk_task_grade",
            "task_id": result.task_id,
            "pass_rate": result.pass_rate,
            "overall_success": result.overall_success,
            "n_passed": result.n_passed,
            "n_total": result.n_total,
            "per_verifier": result.per_verifier,
            "execution_mode": result.execution_mode,
            "raw_sha256": hashlib.sha256(__import__("json").dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
            "submitted": written,
            "provenance": provenance or {},
            "closed": False,
        }
    except Exception as exc:
        raise OfficialGraderError(f"official grader invocation failed: {type(exc).__name__}: {exc}") from exc
