from __future__ import annotations

import hashlib
import json
from typing import Any


class ValidationError(ValueError):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def validate_canary_report(
    report: dict[str, Any], *, required_runs: int, expected_task_id: str, expected_stage: str = "h1"
) -> dict[str, Any]:
    if report.get("run_type", "canary") != "canary":
        raise ValidationError("report is not a canary report")
    runs = report.get("runs")
    if not isinstance(runs, list) or len(runs) != required_runs:
        raise ValidationError(f"canary requires exactly {required_runs} runs")
    session_hashes = []
    roots = []
    for row in runs:
        if not isinstance(row, dict):
            raise ValidationError("canary row must be an object")
        if row.get("status") != "ok" or row.get("task_id") != expected_task_id or row.get("stage") != expected_stage:
            raise ValidationError("canary row is not a successful expected task")
        if row.get("raw_bytes_equal") is not True:
            raise ValidationError("canary raw-byte equality failed")
        if not row.get("api_sha256") or row.get("api_sha256") != row.get("remote_sha256"):
            raise ValidationError("canary hashes are missing or differ")
        if not isinstance(row.get("input_listing"), list) or not row["input_listing"]:
            raise ValidationError("canary input listing is incomplete")
        if row.get("closed") is not True:
            raise ValidationError("canary session close marker is missing")
        if not row.get("session_id_hash") or not row.get("root_basename"):
            raise ValidationError("canary session identity is required")
        session_hashes.append(row["session_id_hash"])
        roots.append(row["root_basename"])
    if session_hashes and len(set(session_hashes)) != len(session_hashes):
        raise ValidationError("canary sessions are not independent")
    if roots and len(set(roots)) != len(roots):
        raise ValidationError("canary sandbox roots are not independent")
    if report.get("all_passed") is not True:
        raise ValidationError("canary report is not all_passed")
    return {"gate_status": "PASS", "eligible_for_inference": True, "report_hash": _sha(report)}


def validate_experiment_identity(
    masked: dict[str, Any], visible: dict[str, Any], *, expected_bundle_set_hash: str
) -> None:
    if masked.get("bundle_set_hash") != expected_bundle_set_hash or visible.get("bundle_set_hash") != expected_bundle_set_hash:
        raise ValidationError("convergence input bundle-set identity mismatch")
    if masked.get("experiment_identity") != visible.get("experiment_identity"):
        raise ValidationError("E0/E1 experiment identity differs")
    if masked.get("candidates") != _mask_evidence_candidates(visible.get("candidates", [])):
        raise ValidationError("E0/E1 candidate projections differ outside evidence")


def _mask_evidence_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = json.loads(json.dumps(candidates, ensure_ascii=False))
    fields = {"calls", "artifacts", "snapshot_id", "runtime_checks"}
    for candidate in result:
        evidence = candidate.get("evidence") or {}
        for field in fields:
            if field in evidence:
                evidence[field] = "MASKED"
    return result
