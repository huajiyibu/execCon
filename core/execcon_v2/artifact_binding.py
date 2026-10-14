from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Any


class ArtifactBindingError(ValueError):
    pass


def artifacts_from_bundle(bundle_dir: Path, decision: dict[str, Any]) -> list[dict[str, Any]]:
    manifest = __import__("json").loads((bundle_dir / "manifest.json").read_text(encoding="utf-8"))
    selected_hash = decision.get("selected_bundle_hash")
    if selected_hash and bundle_dir.name != selected_hash:
        raise ArtifactBindingError("selected bundle directory does not match decision hash")
    records = {record["path"]: record for record in manifest.get("files", [])}
    selected = []
    seen = set()
    for requested in decision.get("artifacts", []):
        rel = requested.get("path")
        if not isinstance(rel, str) or rel in seen or rel not in records:
            raise ArtifactBindingError(f"decision artifact is not in selected bundle: {rel!r}")
        seen.add(rel)
        raw = (bundle_dir / "files" / rel).read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        record = records[rel]
        if digest != record.get("sha256") or len(raw) != record.get("size"):
            raise ArtifactBindingError(f"selected bundle manifest mismatch: {rel}")
        if requested.get("sha256") != digest:
            raise ArtifactBindingError(f"decision hash differs from selected bundle: {rel}")
        selected.append({"path": rel, "content_b64": base64.b64encode(raw).decode("ascii"), "sha256": digest})
    return selected
