from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


class BundleIntegrityError(ValueError):
    pass


REQUIRED_IDENTITY_FIELDS = frozenset(
    {
        "task_id",
        "cohort",
        "harness",
        "resource_mode",
        "model",
        "model_settings_sha256",
        "spec_sha256",
        "pool_sha256",
        "prompt_sha256",
        "tool_schema_sha256",
        "code_sha256",
        "output_protocol_sha256",
        "producer_id",
        "session_id_hash",
    }
)
HASH_FIELDS = frozenset(field for field in REQUIRED_IDENTITY_FIELDS if field.endswith("_sha256") or field.endswith("_hash"))


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _file_records(files_root: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(files_root.rglob("*")):
        if path.is_symlink():
            raise BundleIntegrityError(f"symbolic links are forbidden in candidate bundles: {path}")
        if not path.is_file():
            continue
        data = path.read_bytes()
        records.append(
            {
                "path": path.relative_to(files_root).as_posix(),
                "size": len(data),
                "sha256": _sha256_bytes(data),
            }
        )
    return records


SENSITIVE_KEY_PARTS = ("authorization", "api_key", "apikey", "token", "secret", "password")


def _reject_credentials(value: Any, path: str = "identity") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if any(part in normalized for part in SENSITIVE_KEY_PARTS):
                raise BundleIntegrityError(f"credential-like field is forbidden in bundle metadata: {path}.{key}")
            _reject_credentials(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_credentials(child, f"{path}[{index}]")


def _validate_identity(metadata: dict[str, Any]) -> None:
    missing = sorted(REQUIRED_IDENTITY_FIELDS - metadata.keys())
    if missing:
        raise BundleIntegrityError(f"bundle identity is incomplete: {', '.join(missing)}")
    for field in REQUIRED_IDENTITY_FIELDS:
        value = metadata[field]
        if value is None or value == "":
            raise BundleIntegrityError(f"bundle identity field is empty: {field}")
    for field in HASH_FIELDS:
        value = metadata[field]
        if not isinstance(value, str) or len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise BundleIntegrityError(f"bundle identity field is not a lowercase SHA-256: {field}")
    if not isinstance(metadata["cohort"], int) or not isinstance(metadata["harness"], int):
        raise BundleIntegrityError("cohort and harness must be integers")
    _reject_credentials(metadata)


def freeze_bundle(bundle_root: Path, metadata: dict[str, Any], source_files: Path) -> Path:
    _validate_identity(metadata)
    if not source_files.is_dir():
        raise BundleIntegrityError(f"candidate file directory does not exist: {source_files}")

    records = _file_records(source_files)
    manifest_without_hash = {"schema_version": 1, "identity": metadata, "files": records}
    bundle_hash = _sha256_bytes(_canonical_bytes(manifest_without_hash))
    target = bundle_root / bundle_hash
    if target.exists():
        load_bundle(target)
        return target

    bundle_root.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=f".{bundle_hash}.", dir=bundle_root))
    try:
        shutil.copytree(source_files, temporary / "files")
        manifest = {**manifest_without_hash, "bundle_hash": bundle_hash}
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        if _file_records(temporary / "files") != records:
            raise BundleIntegrityError("candidate files changed while the bundle was being frozen")
        try:
            os.replace(temporary, target)
        except FileExistsError:
            load_bundle(target)
        return target
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)


def load_bundle(bundle_dir: Path) -> dict[str, Any]:
    manifest_path = bundle_dir / "manifest.json"
    files_root = bundle_dir / "files"
    if not manifest_path.is_file() or not files_root.is_dir():
        raise BundleIntegrityError(f"not a complete bundle: {bundle_dir}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _validate_identity(manifest.get("identity") or {})
    actual_records = _file_records(files_root)
    if actual_records != manifest.get("files"):
        raise BundleIntegrityError("bundle file bytes differ from the frozen manifest")

    material = {
        "schema_version": manifest.get("schema_version"),
        "identity": manifest["identity"],
        "files": actual_records,
    }
    actual_hash = _sha256_bytes(_canonical_bytes(material))
    if actual_hash != manifest.get("bundle_hash") or actual_hash != bundle_dir.name:
        raise BundleIntegrityError("bundle content address does not match its manifest")
    return manifest
