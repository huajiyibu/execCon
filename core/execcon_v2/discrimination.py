from __future__ import annotations

from typing import Any


def _artifact_signature(candidate: dict[str, Any]) -> tuple[tuple[str, int, str], ...]:
    return tuple(
        sorted(
            (str(item.get("path")), int(item.get("size", -1)), str(item.get("sha256")))
            for item in candidate.get("files", [])
        )
    )


def _evidence_signature(candidate: dict[str, Any]) -> tuple[Any, ...]:
    evidence = candidate.get("evidence") or {}
    checks = evidence.get("runtime_checks") or {}
    artifacts = evidence.get("artifacts") or []
    return (
        checks.get("public_self_check"),
        checks.get("required_outputs_present"),
        tuple(sorted(str(item.get("path")) for item in artifacts if isinstance(item, dict))),
        evidence.get("snapshot_id"),
    )


def assess_candidate_discrimination(candidates: list[dict[str, Any]], *, required_outputs: list[str]) -> dict[str, Any]:
    if len(candidates) < 2:
        return {"eligible": False, "status": "insufficient_candidates", "reason": "at least two candidates are required"}
    complete = [set(item.get("path") for item in c.get("files", [])) >= set(required_outputs) for c in candidates]
    validator = [(c.get("evidence") or {}).get("runtime_checks", {}).get("public_self_check") for c in candidates]
    artifact_signatures = [_artifact_signature(c) for c in candidates]
    evidence_signatures = [_evidence_signature(c) for c in candidates]
    reasons = []
    if len(set(validator)) > 1:
        reasons.append("public_validator_status_differs")
    if len(set(artifact_signatures)) > 1:
        reasons.append("artifact_content_or_shape_differs")
    if len(set(evidence_signatures)) > 1:
        reasons.append("execution_evidence_structure_differs")
    eligible = bool(all(complete) and reasons)
    return {
        "eligible": eligible,
        "status": "eligible" if eligible else "diagnostic_only_no_discrimination",
        "reasons": reasons,
        "complete": complete,
        "validator_statuses": validator,
        "artifact_signatures_distinct": len(set(artifact_signatures)) > 1,
        "evidence_signatures_distinct": len(set(evidence_signatures)) > 1,
    }
