from __future__ import annotations

from typing import Any
import re


class QualificationError(ValueError):
    pass


def qualify_candidates(
    candidates: list[dict[str, Any]],
    *,
    required_outputs: list[str],
    required_specialists: list[str],
    expected_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if len(candidates) < 2:
        raise QualificationError("at least two candidates are required")
    if len({c.get("candidate_id") for c in candidates}) != len(candidates):
        raise QualificationError("candidate IDs must be unique")
    specialists = {c.get("specialist") for c in candidates}
    required_set = set(required_specialists)
    if None in specialists or not specialists.issubset(required_set):
        raise QualificationError("candidate specialist is not in the required set")
    covered = required_set.issubset(specialists)
    required = set(required_outputs)
    complete = []
    recoverable = []
    for candidate in candidates:
        paths = {f.get("path") for f in candidate.get("files", [])}
        is_complete = required.issubset(paths)
        provenance = candidate.get("provenance") or {}
        manifest_ok = all(isinstance(f.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", f["sha256"]) and isinstance(f.get("size"), int) and f["size"] >= 0 for f in candidate.get("files", []))
        provenance_ok = all(provenance.get(field) for field in ("task_id", "spec_sha256", "pool_sha256", "validator_version"))
        if expected_provenance is not None:
            provenance_ok = provenance_ok and all(provenance.get(k) == v for k, v in expected_provenance.items())
        if is_complete and manifest_ok and candidate.get("bundle_hash") and re.fullmatch(r"[0-9a-f]{64}", candidate["bundle_hash"]) and candidate.get("session_id_hash") and re.fullmatch(r"[0-9a-f]{64}", candidate["session_id_hash"]) and candidate.get("producer_id") and provenance_ok:
            complete.append(candidate["candidate_id"])
        checks = (candidate.get("evidence") or {}).get("runtime_checks") or {}
        # Recoverability is an eligibility property, so it must use the same
        # provenance and artifact checks as the complete-candidate gate.
        if (
            is_complete
            and manifest_ok
            and isinstance(candidate.get("bundle_hash"), str)
            and re.fullmatch(r"[0-9a-f]{64}", candidate["bundle_hash"])
            and isinstance(candidate.get("session_id_hash"), str)
            and re.fullmatch(r"[0-9a-f]{64}", candidate["session_id_hash"])
            and isinstance(candidate.get("producer_id"), str)
            and bool(candidate["producer_id"])
            and provenance_ok
            and checks.get("public_self_check") == "pass"
        ):
            recoverable.append(candidate["candidate_id"])
    from .discrimination import assess_candidate_discrimination
    discrimination = assess_candidate_discrimination(candidates, required_outputs=sorted(required))
    result = {
        "schema_version": 1,
        "candidate_discrimination": discrimination,
        "covered": covered,
        "recoverable": bool(recoverable),
        "n_complete_candidates": len(complete),
        "complete_candidate_ids": complete,
        "recoverable_candidate_ids": recoverable,
        "required_outputs": sorted(required),
        "required_specialists": sorted(required_specialists),
    }
    if not covered:
        raise QualificationError("required specialist capabilities are not covered")
    if len(complete) < 2:
        raise QualificationError("fewer than two candidates produced complete outputs")
    if not recoverable:
        raise QualificationError("no recoverable candidate passed the public self-check")
    return result
