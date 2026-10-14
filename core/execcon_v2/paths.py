from __future__ import annotations

from pathlib import Path


class PathBoundaryError(ValueError):
    pass


def safe_candidate_path(private_root: Path, candidate_path: str) -> Path:
    root = private_root.resolve()
    raw = Path(candidate_path)
    resolved = raw.resolve() if raw.is_absolute() else (root / raw).resolve()
    if resolved != root and root not in resolved.parents:
        raise PathBoundaryError(f"candidate path escapes private root: {candidate_path}")
    return resolved
