from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


class BundleSetError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value)


def freeze_bundle_set(
    root: Path,
    *,
    task_id: str,
    spec_sha256: str,
    pool_sha256: str,
    candidates: list[dict[str, Any]],
) -> Path:
    if not task_id or not _is_hash(spec_sha256) or not _is_hash(pool_sha256):
        raise BundleSetError("invalid bundle-set identity")
    if len(candidates) < 2:
        raise BundleSetError("a base bundle set requires at least two candidates")
    ids = [c.get("candidate_id") for c in candidates]
    hashes = [c.get("bundle_hash") for c in candidates]
    if any(not x for x in ids) or len(set(ids)) != len(ids):
        raise BundleSetError("candidate IDs must be present and unique")
    if any(not _is_hash(x) for x in hashes):
        raise BundleSetError("candidate bundle hashes are invalid")
    session_hashes = [((c.get("identity") or {}).get("session_id_hash") or c.get("session_id_hash")) for c in candidates]
    producer_ids = [((c.get("identity") or {}).get("producer_id") or c.get("producer_id")) for c in candidates]
    if any(not _is_hash(x) for x in session_hashes):
        raise BundleSetError("candidate session hashes are required")
    if len(set(session_hashes)) != len(session_hashes):
        raise BundleSetError("candidate sessions must be independent")
    if any(not isinstance(x, str) or not x for x in producer_ids) or len(set(producer_ids)) != len(producer_ids):
        raise BundleSetError("candidate producer identities must be unique")

    material = {
        "schema_version": 1,
        "task_id": task_id,
        "spec_sha256": spec_sha256,
        "pool_sha256": pool_sha256,
        "candidate_order": ids,
        "candidates": candidates,
    }
    bundle_set_hash = _sha(material)
    target = root / bundle_set_hash
    if target.exists():
        load_bundle_set(target, bundle_root=root.parent / "bundles")
        return target
    root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{bundle_set_hash}.", dir=root))
    try:
        manifest = {**material, "bundle_set_hash": bundle_set_hash}
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        try:
            os.replace(temporary, target)
        except FileExistsError:
            load_bundle_set(target, bundle_root=root.parent / "bundles")
        return target
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def load_bundle_set(path: Path, *, bundle_root: Path | None = None) -> dict[str, Any]:
    manifest_path = path / "manifest.json"
    if not manifest_path.is_file():
        raise BundleSetError("bundle-set manifest is missing")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    expected = manifest.get("bundle_set_hash")
    material = {k: v for k, v in manifest.items() if k != "bundle_set_hash"}
    actual = _sha(material)
    if expected != actual or path.name != actual:
        raise BundleSetError("bundle-set content address mismatch")
    if bundle_root is not None:
        from .bundle import load_bundle
        for candidate in manifest.get("candidates", []):
            bundle_hash = candidate.get("bundle_hash")
            if not isinstance(bundle_hash, str):
                raise BundleSetError("candidate bundle hash is missing")
            bundle = load_bundle(bundle_root / bundle_hash)
            identity = bundle.get("identity") or {}
            if identity.get("task_id") != manifest.get("task_id"):
                raise BundleSetError("candidate task identity differs from bundle-set")
            if identity.get("spec_sha256") != manifest.get("spec_sha256"):
                raise BundleSetError("candidate spec provenance differs from bundle-set")
            if identity.get("pool_sha256") != manifest.get("pool_sha256"):
                raise BundleSetError("candidate pool provenance differs from bundle-set")
            if identity.get("producer_id") and identity["producer_id"] != candidate.get("producer_id"):
                raise BundleSetError("candidate producer identity does not match candidate metadata")
            if identity.get("session_id_hash") != ((candidate.get("identity") or {}).get("session_id_hash") or candidate.get("session_id_hash")):
                raise BundleSetError("candidate session identity does not match bundle metadata")
            if identity.get("model") and candidate.get("model") and identity["model"] != candidate["model"]:
                raise BundleSetError("candidate model identity does not match bundle metadata")
    return manifest
