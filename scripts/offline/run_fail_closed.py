from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.bundle import load_bundle
from execcon_v2.bundle_set import load_bundle_set
from execcon_v2.clean_grade import stage_and_grade
from execcon_v2.convergence import converge
from execcon_v2.inputs import assert_treatment_purity, build_convergence_input
from execcon_v2.qualify import qualify_candidates
from execcon_v2.validate import ValidationError, validate_canary_report, validate_experiment_identity
from execcon_v2.artifact_binding import artifacts_from_bundle

TASK_ID = "business_finance/american_option_pricing_ls"
REQUIRED_SPECIALISTS = {"numerics_stats", "runtime_base"}


def fail(report: dict, path: Path, reason: str) -> int:
    report.update({"status": "blocked", "reason": reason, "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--canary", type=Path, required=True)
    ap.add_argument("--bundle-set", type=Path, required=True)
    ap.add_argument("--bundle-root", type=Path, required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--official-task-factory", type=str, default=None, help="module:function factory returning a fresh official grading task")
    args = ap.parse_args()
    report = {"schema_version": 1, "run_type": "experiment", "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "stages": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        canary = json.loads(args.canary.read_text(encoding="utf-8"))
        report["stages"].append("canary_loaded")
        validate_canary_report(canary, required_runs=3, expected_task_id=TASK_ID)
        bundle_set = load_bundle_set(args.bundle_set, bundle_root=args.bundle_root)
        report["stages"].append("bundle_set_validated")
        candidates = []
        for entry in bundle_set["candidates"]:
            bundle = load_bundle(args.bundle_root / entry["bundle_hash"])
            if bundle["identity"].get("task_id") != bundle_set["task_id"]:
                raise ValueError("bundle task identity mismatch")
            identity = bundle["identity"]
            candidates.append({"candidate_id": entry["candidate_id"], "specialist": entry.get("specialist"), "bundle_hash": entry["bundle_hash"], "session_id_hash": identity["session_id_hash"], "producer_id": identity["producer_id"], "provenance": {"task_id": identity["task_id"], "spec_sha256": identity["spec_sha256"], "pool_sha256": identity["pool_sha256"], "validator_version": "execcon-public-validator-v1"}, "files": bundle["files"], "evidence": entry.get("evidence", {})})
        qualification = qualify_candidates(candidates, required_outputs=["results.json", "exercise_boundary_tier2.npy"], required_specialists=sorted(REQUIRED_SPECIALISTS), expected_provenance={"task_id": bundle_set["task_id"]})
        qualified = set(qualification["complete_candidate_ids"])
        report["qualification"] = qualification
        identity = {"bundle_set_hash": bundle_set["bundle_set_hash"], "required_outputs": ["results.json", "exercise_boundary_tier2.npy"], "algorithm": "execcon-v2-coherent-candidate-selector"}
        e0 = build_convergence_input(args.spec, candidates, evidence_visible=False, bundle_set_hash=bundle_set["bundle_set_hash"], experiment_identity=identity)
        e1 = build_convergence_input(args.spec, candidates, evidence_visible=True, bundle_set_hash=bundle_set["bundle_set_hash"], experiment_identity=identity)
        assert_treatment_purity(e0, e1)
        validate_experiment_identity(e0, e1, expected_bundle_set_hash=bundle_set["bundle_set_hash"])
        d0 = converge(e0, required_outputs=identity["required_outputs"], expected_bundle_set_hash=bundle_set["bundle_set_hash"], qualified_candidate_ids=qualified)
        d1 = converge(e1, required_outputs=identity["required_outputs"], expected_bundle_set_hash=bundle_set["bundle_set_hash"], qualified_candidate_ids=qualified)
        report["decisions"] = {"E0": d0, "E1": d1}
        report["stages"].append("convergence_complete")
        for treatment, decision in (("E0", d0), ("E1", d1)):
            if decision["status"] != "selected":
                raise ValueError(f"{treatment} unresolved")
            bundle_dir = args.bundle_root / decision["selected_bundle_hash"]
            staged_decision = {"artifacts": artifacts_from_bundle(bundle_dir, decision)}
            if not args.official_task_factory:
                return fail(report, args.output, "official grader task factory is required")
            module_name, function_name = args.official_task_factory.split(":", 1)
            import importlib
            factory = getattr(importlib.import_module(module_name), function_name)
            with __import__("tempfile").TemporaryDirectory() as tmp:
                def official_grade(base: Path) -> dict:
                    from execcon_v2.grader_adapter import grade_with_task
                    task = factory()
                    try:
                        return grade_with_task(task, base / "output")
                    finally:
                        close = getattr(task, "close", None)
                        if callable(close):
                            close()
                grade = stage_and_grade(staged_decision, sandbox=Path(tmp), grader=official_grade)
            report.setdefault("grades", {})[treatment] = {"status": "official_graded", "staged": grade["staged"], "grade": grade["grade"]}
        report.update({"status": "complete", "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "official_grader_invoked": True})
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0
    except (ValidationError, ValueError, KeyError, OSError) as exc:
        return fail(report, args.output, f"{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
