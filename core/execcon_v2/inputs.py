from __future__ import annotations

import copy
import json
from typing import Any


class ForbiddenEvaluationField(ValueError):
    pass


FORBIDDEN_FIELDS = frozenset(
    {
        "pass_rate",
        "overall_success",
        "per_verifier",
        "n_passed",
        "n_total",
        "grade",
        "grader",
        "oracle_tools",
    }
)
EVIDENCE_FIELDS = ("calls", "artifacts", "snapshot_id", "runtime_checks")
EVIDENCE_FIELD_SET = frozenset(EVIDENCE_FIELDS)


def _reject_forbidden(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if key.lower() in FORBIDDEN_FIELDS:
                raise ForbiddenEvaluationField(f"forbidden evaluation field at {path}.{key}")
            _reject_forbidden(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_forbidden(child, f"{path}[{index}]")


def build_convergence_input(
    spec: str,
    candidates: list[dict[str, Any]],
    *,
    evidence_visible: bool,
    bundle_set_hash: str | None = None,
    experiment_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    material = {"schema_version": 1, "spec": spec, "candidates": copy.deepcopy(candidates)}
    if bundle_set_hash is not None:
        material["bundle_set_hash"] = bundle_set_hash
    if experiment_identity is not None:
        material["experiment_identity"] = copy.deepcopy(experiment_identity)
    _reject_forbidden(material)
    for candidate in material["candidates"]:
        if not isinstance(candidate, dict):
            raise ValueError("each candidate must be an object")
        evidence = candidate.setdefault("evidence", {})
        if not isinstance(evidence, dict):
            raise ValueError("candidate evidence must be an object")
        unknown = sorted(set(evidence) - EVIDENCE_FIELD_SET)
        if unknown:
            raise ValueError(f"unknown evidence fields are forbidden: {', '.join(unknown)}")
        if not evidence_visible:
            candidate.pop("content_b64", None)
            candidate.pop("artifact_contents", None)
        for field in EVIDENCE_FIELDS:
            evidence.setdefault(field, None)
            if not evidence_visible:
                evidence[field] = "MASKED"
    material["treatment"] = {"evidence_visible": evidence_visible}
    return material


def _non_evidence_projection(value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(value)
    result.pop("treatment", None)
    for candidate in result.get("candidates", []):
        evidence = candidate.get("evidence") or {}
        for field in EVIDENCE_FIELDS:
            if field in evidence:
                evidence[field] = "EVIDENCE_SLOT"
    return result


def assert_treatment_purity(masked: dict[str, Any], visible: dict[str, Any]) -> None:
    left = json.dumps(_non_evidence_projection(masked), ensure_ascii=False, sort_keys=True)
    right = json.dumps(_non_evidence_projection(visible), ensure_ascii=False, sort_keys=True)
    if left != right:
        raise AssertionError("E0 and E1 differ outside admitted evidence fields")
