from __future__ import annotations

import hashlib
import json
from typing import Any

ALGORITHM = "execcon-v2-coherent-candidate-selector"


def _hash(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _candidate_score(candidate: dict[str, Any], required_outputs: set[str]) -> tuple[int, int, int, str]:
    files = {f.get("path") for f in candidate.get("files", [])}
    output_coverage = len(required_outputs & files)
    evidence = candidate.get("evidence") or {}
    visible = evidence.get("calls") != "MASKED"
    if visible:
        checks = evidence.get("runtime_checks") or {}
        self_check = 1 if checks.get("public_self_check") == "pass" else 0
        artifacts = evidence.get("artifacts") or []
        evidence_coverage = len({a.get("path") for a in artifacts} & required_outputs)
    else:
        self_check = 0
        evidence_coverage = 0
    duplicate_penalty = -1 if candidate.get("duplicate_of") else 0
    canonical = candidate.get("duplicate_of") or candidate.get("candidate_id") or ""
    return self_check, evidence_coverage, output_coverage + duplicate_penalty, canonical


def converge(
    convergence_input: dict[str, Any],
    *,
    required_outputs: list[str],
    expected_bundle_set_hash: str | None = None,
    required_specialists: list[str] | None = None,
    qualified_candidate_ids: set[str] | None = None,
) -> dict[str, Any]:
    candidates = convergence_input.get("candidates") or []
    required = set(required_outputs)
    specialists = set(required_specialists or [])
    if expected_bundle_set_hash is not None and convergence_input.get("bundle_set_hash") != expected_bundle_set_hash:
        raise ValueError("convergence input bundle-set hash does not match expected frozen set")
    eligible = [
        c for c in candidates
        if required.issubset({f.get("path") for f in c.get("files", [])})
        and (not specialists or c.get("specialist") in specialists)
        and (
                (
                    c.get("evidence") == "MASKED"
                    or (
                        isinstance(c.get("evidence"), dict)
                        and all(c["evidence"].get(field) == "MASKED" for field in ("calls", "artifacts", "snapshot_id", "runtime_checks"))
                    )
                )
                or (
                    isinstance(c.get("evidence"), dict)

                and isinstance((c.get("evidence") or {}).get("runtime_checks"), dict)
                and (c.get("evidence") or {}).get("runtime_checks", {}).get("public_self_check") == "pass"
            )
        )
        and isinstance(c.get("bundle_hash"), str)
        and len(c["bundle_hash"]) == 64
        and all(char in "0123456789abcdef" for char in c["bundle_hash"])
        and (qualified_candidate_ids is None or c.get("candidate_id") in qualified_candidate_ids)
    ]
    if not eligible:
        decision = {
            "algorithm": ALGORITHM,
            "status": "unresolved",
            "selected_candidate_id": None,
            "selected_bundle_hash": None,
            "artifacts": [],
            "reason": "no candidate covers all required outputs",
        }
    else:
        ranked = sorted(eligible, key=lambda c: _candidate_score(c, required), reverse=True)
        best = ranked[0]
        canonical_id = best.get("duplicate_of") or best["candidate_id"]
        canonical = next((c for c in eligible if c.get("candidate_id") == canonical_id), best)
        decision = {
            "algorithm": ALGORITHM,
            "status": "selected",
            "selected_candidate_id": canonical_id,
            "selected_bundle_hash": canonical.get("bundle_hash"),
            "artifacts": sorted(
                [f for f in canonical.get("files", []) if f.get("path") in required_outputs],
                key=lambda f: f.get("path") or "",
            ),
            "reason": "selected one coherent candidate using only visible input fields",
        }
    decision["decision_hash"] = _hash({k: v for k, v in decision.items() if k != "decision_hash"})
    decision["artifact_set_hash"] = _hash(decision["artifacts"])
    return decision


def property_comparison(left: dict[str, Any], right: dict[str, Any]) -> dict[str, bool]:
    return {
        "decision_flip": left.get("selected_bundle_hash") != right.get("selected_bundle_hash")
        or left.get("status") != right.get("status"),
        "artifact_flip": left.get("artifact_set_hash") != right.get("artifact_set_hash"),
    }
