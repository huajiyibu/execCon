from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PublicValidationError(ValueError):
    pass


VALIDATOR_VERSION = "execcon-public-validator-v1"
REQUIRED_OUTPUTS = ("results.json", "exercise_boundary_tier2.npy")


def validate_outputs(root: Path, *, required_outputs: tuple[str, ...] = REQUIRED_OUTPUTS) -> dict[str, Any]:
    root = root.resolve()
    records: dict[str, dict[str, int]] = {}
    for rel in required_outputs:
        path = root / rel
        if not path.is_file() or path.is_symlink():
            raise PublicValidationError(f"missing required output: {rel}")
        raw = path.read_bytes()
        if not raw:
            raise PublicValidationError(f"empty required output: {rel}")
        records[rel] = {"size": len(raw)}
    try:
        parsed = json.loads((root / "results.json").read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PublicValidationError("results.json is not valid UTF-8 JSON") from exc
    if not isinstance(parsed, dict) or not parsed:
        raise PublicValidationError("results.json must be a non-empty object")
    if (root / "exercise_boundary_tier2.npy").read_bytes()[:6] != b"\x93NUMPY":
        raise PublicValidationError("exercise_boundary_tier2.npy has invalid NumPy magic")
    return {"validator_version": VALIDATOR_VERSION, "required_outputs": list(required_outputs), "files": records}
