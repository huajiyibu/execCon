from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Callable


class GradeIntegrityError(ValueError):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stage_and_grade(
    decision: dict[str, Any],
    *,
    sandbox: Path,
    grader: Callable[[Path], dict[str, Any]],
) -> dict[str, Any]:
    """Stage a convergence decision in an empty sandbox, then grade it.

    The grader is injected so the protocol can be tested offline; grader output is
    returned separately and must never be passed back to convergence.
    """
    base = sandbox / "base"
    output = base / "output"
    if output.exists() and any(output.iterdir()):
        raise GradeIntegrityError("grading output sandbox is not empty before staging")
    output.mkdir(parents=True, exist_ok=True)
    artifacts = decision.get("artifacts") or []
    staged = []
    seen_paths: set[str] = set()
    for artifact in artifacts:
        rel = artifact.get("path")
        if not isinstance(rel, str) or not rel or rel.startswith("/") or ".." in Path(rel).parts:
            raise GradeIntegrityError("invalid decision artifact path")
        if rel in seen_paths:
            raise GradeIntegrityError(f"duplicate decision artifact path: {rel}")
        seen_paths.add(rel)
        content = artifact.get("content_b64")
        if not isinstance(content, str):
            raise GradeIntegrityError("decision artifact lacks content_b64")
        import base64
        try:
            raw = base64.b64decode(content, validate=True)
        except Exception as exc:
            raise GradeIntegrityError("invalid artifact base64") from exc
        expected = artifact.get("sha256")
        if not isinstance(expected, str) or len(expected) != 64:
            raise GradeIntegrityError(f"artifact sha256 is required: {rel}")
        if expected != _sha256(raw):
            raise GradeIntegrityError(f"artifact hash mismatch: {rel}")
        target = output / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        reread = target.read_bytes()
        if _sha256(reread) != _sha256(raw):
            raise GradeIntegrityError(f"staged artifact changed after write: {rel}")
        staged.append({"path": rel, "sha256": _sha256(reread), "size": len(reread)})
    result = grader(base)
    if not isinstance(result, dict) or "pass_rate" not in result or "overall_success" not in result:
        raise GradeIntegrityError("grader returned an incomplete result")
    return {"status": "graded", "staged": staged, "grade": result}
