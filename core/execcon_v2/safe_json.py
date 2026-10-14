from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


class SensitiveDataError(ValueError):
    pass


SENSITIVE_KEYS = frozenset(
    {"authorization", "api_key", "apikey", "access_token", "refresh_token", "secret", "password", "cookie"}
)
CREDENTIAL_VALUE_PATTERNS = (
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{12,}", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"\bmas_[A-Za-z0-9_-]{32,}"),
)


def assert_public(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = key.lower().replace("-", "_")
            if normalized in SENSITIVE_KEYS and not isinstance(child, (bool, type(None))):
                raise SensitiveDataError(f"sensitive key cannot be serialized: {path}.{key}")
            assert_public(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            assert_public(child, f"{path}[{index}]")
    elif isinstance(value, str):
        if any(pattern.search(value) for pattern in CREDENTIAL_VALUE_PATTERNS):
            raise SensitiveDataError(f"credential-like value cannot be serialized: {path}")


def write_public_json(path: Path, value: Any) -> None:
    assert_public(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)
