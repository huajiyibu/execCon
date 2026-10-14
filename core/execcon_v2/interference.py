from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_duplicate(candidate: dict[str, Any], *, instance_id: str) -> dict[str, Any]:
    duplicate = copy.deepcopy(candidate)
    duplicate["candidate_id"] = instance_id
    duplicate["duplicate_of"] = candidate["candidate_id"]
    duplicate["construction"] = "exact_duplicate_reference"
    duplicate["construction_hash"] = _hash({"source": candidate["bundle_hash"], "instance": instance_id})
    return duplicate


def build_irrelevant(required_outputs: list[str]) -> dict[str, Any]:
    candidate = {
        "candidate_id": "d-irrelevant",
        "specialist": "irrelevant_control",
        "claim": "This execution concerns an unrelated formatting preference and makes no task claim.",
        "bundle_hash": _hash({"kind": "irrelevant", "required": sorted(required_outputs)}),
        "files": [{"path": "unrelated_note.txt", "sha256": _hash("irrelevant"), "size": 10}],
        "evidence": {
            "calls": [],
            "artifacts": [{"path": "unrelated_note.txt", "sha256": _hash("irrelevant")}],
            "snapshot_id": "synthetic-control",
            "runtime_checks": {"relation": "irrelevant"},
        },
        "construction": "deterministic_irrelevant_control",
    }
    if {f["path"] for f in candidate["files"]} & set(required_outputs):
        raise ValueError("irrelevant control overlaps required outputs")
    return candidate


def build_unsupported_conflict(field: str, value: Any) -> dict[str, Any]:
    return {
        "candidate_id": "d-unsupported-conflict",
        "specialist": "unsupported_control",
        "claim": f"The value of {field} is {value}, asserted without execution support.",
        "bundle_hash": _hash({"kind": "unsupported_conflict", "field": field, "value": value}),
        "files": [],
        "evidence": {
            "calls": [],
            "artifacts": [],
            "snapshot_id": "synthetic-control",
            "runtime_checks": {"support": "unsupported", "field": field},
        },
        "construction": "deterministic_unsupported_conflict",
    }


def misbind_evidence(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(candidates) < 2:
        raise ValueError("misbinding requires at least two candidates")
    result = copy.deepcopy(candidates)
    evidence = [copy.deepcopy(c["evidence"]) for c in candidates]
    rotated = evidence[1:] + evidence[:1]
    for candidate, replacement in zip(result, rotated):
        candidate["evidence"] = replacement
        candidate["evidence_binding"] = "misbound"
    return result
