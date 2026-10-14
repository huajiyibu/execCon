from __future__ import annotations

import argparse
import base64
import hashlib
import json
import tempfile
from pathlib import Path

from src.execcon_v2.bundle_set import freeze_bundle_set
from src.execcon_v2.clean_grade import stage_and_grade
from src.execcon_v2.convergence import converge, property_comparison
from src.execcon_v2.inputs import assert_treatment_purity, build_convergence_input
from src.execcon_v2.interference import build_duplicate, build_irrelevant, build_unsupported_conflict, misbind_evidence
from src.execcon_v2.qualify import qualify_candidates
from src.execcon_v2.safe_json import write_public_json
from src.execcon_v2.summary import summarize_cells

REQUIRED = ["results.json", "exercise_boundary_tier2.npy"]
SPECIALISTS = ["numerics_stats", "runtime_base"]


def candidate(cid: str, specialist: str, bundle: str, value: bytes) -> dict:
    digest = hashlib.sha256(value).hexdigest()
    return {
        "candidate_id": cid,
        "specialist": specialist,
        "bundle_hash": bundle,
        "session_id_hash": hashlib.sha256(cid.encode()).hexdigest(),
        "producer_id": cid + ":producer",
        "provenance": {"task_id": "business_finance/american_option_pricing_ls", "spec_sha256": "1" * 64, "pool_sha256": "2" * 64, "validator_version": "execcon-public-validator-v1"},
        "files": [{"path": name, "sha256": digest, "size": len(value), "content_b64": base64.b64encode(value).decode()} for name in REQUIRED],
        "evidence": {
            "calls": [{"name": "public_check", "exit_code": 0}],
            "artifacts": [{"path": name} for name in REQUIRED],
            "snapshot_id": "fixture-snapshot",
            "runtime_checks": {"public_self_check": "pass"},
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    c0 = candidate("cand-0", SPECIALISTS[0], "a" * 64, b"candidate-0")
    c1 = candidate("cand-1", SPECIALISTS[1], "b" * 64, b"candidate-1")
    candidates = [c0, c1]
    qualification = qualify_candidates(candidates, required_outputs=REQUIRED, required_specialists=SPECIALISTS)
    base_set = {"schema_version": 1, "candidates": candidates, "set_hash": "fixture"}
    conditions = {
        "base": candidates,
        "irrelevant": candidates + [build_irrelevant(REQUIRED)],
        "duplicate": candidates + [build_duplicate(c0, instance_id="dup-0")],
        "unsupported_conflict": candidates + [build_unsupported_conflict("value", "conflict")],
    }
    cells = []
    decisions = {}
    for condition, pool in conditions.items():
        masked = build_convergence_input("fixture public spec", pool, evidence_visible=False)
        visible = build_convergence_input("fixture public spec", pool, evidence_visible=True)
        assert_treatment_purity(masked, visible)
        decisions[(condition, "E0")] = converge(masked, required_outputs=REQUIRED)
        decisions[(condition, "E1")] = converge(visible, required_outputs=REQUIRED)
        if condition in {"base", "unsupported_conflict"}:
            misbound = build_convergence_input("fixture public spec", misbind_evidence(pool), evidence_visible=True)
            decisions[(condition, "E2")] = converge(misbound, required_outputs=REQUIRED)
        for treatment in ["E0", "E1", "E2"]:
            if (condition, treatment) not in decisions:
                continue
            decision = decisions[(condition, treatment)]
            with tempfile.TemporaryDirectory(dir=args.output) as tmp:
                result = stage_and_grade(decision, sandbox=Path(tmp), grader=lambda _: {"pass_rate": 1.0 if decision["status"] == "selected" else 0.0, "overall_success": decision["status"] == "selected"})
            cells.append({"condition": condition, "treatment": treatment, "status": "graded", "pass": result["grade"]["overall_success"], "score": result["grade"]["pass_rate"], "decision_hash": decision["decision_hash"], "artifact_hash": decision["artifact_set_hash"]})
    report = {"schema_version": 1, "qualification": qualification, "summary": summarize_cells(cells), "cells": cells, "properties": {"duplicate": property_comparison(decisions[("base", "E1")], decisions[("duplicate", "E1")]), "irrelevant": property_comparison(decisions[("base", "E1")], decisions[("irrelevant", "E1")])}, "bundle_set": base_set}
    write_public_json(args.output / "offline_protocol_report.json", report)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
