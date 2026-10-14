from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.mcp import decode_read_bytes, command_stdout
from execcon_v2.safe_json import write_public_json
from execcon_v2.settings import load_settings

TASK_ID = "business_finance/american_option_pricing_ls"

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "h1_canary.json")
    args = parser.parse_args()
    settings = load_settings(require_model_key=False)
    from simple_agentic_evals import EvalClient

    results = []
    for index in range(args.runs):
        row = {"run": index + 1, "task_id": TASK_ID, "stage": "h1", "status": "error"}
        client = EvalClient(base_url=settings.eval_service_url, api_key=settings.eval_service_api_key, timeout=600.0)
        task = client.task(settings.dataset, settings.benchmark, 1, task_id=TASK_ID, resource_mode="accumulative", at_stage=1)
        try:
            task.start()
            row["session_id_hash"] = sha256(task.session_id.encode("utf-8"))
            api_bytes = task.fetch_input("input/problem_spec.md")
            task.start_remote_sandbox(timeout=600.0)
            if task.remote_mcp_server is None:
                raise RuntimeError("remote sandbox returned no MCP server")
            with task.mcp_session(task.remote_mcp_server, timeout=180.0) as mcp:
                root = command_stdout(mcp, "pwd").strip().splitlines()[-1]
                remote = decode_read_bytes(mcp.call_tool("read_bytes", {"path": "base/input/problem_spec.md"}))
                listing = command_stdout(mcp, "find base/input -type f -printf '%P\\t%s\\n' | LC_ALL=C sort")
            row.update({
                "status": "ok" if api_bytes == remote else "error",
                "root_basename": Path(root).name,
                "api_size": len(api_bytes),
                "remote_size": len(remote),
                "api_sha256": sha256(api_bytes),
                "remote_sha256": sha256(remote),
                "raw_bytes_equal": api_bytes == remote,
                "input_listing": listing.splitlines(),
            })
        except Exception as exc:
            row.update({"error_type": type(exc).__name__, "error": str(exc)})
        finally:
            try:
                task.close()
                row["closed"] = True
            except Exception as exc:
                row.update({"closed": False, "close_error": f"{type(exc).__name__}: {exc}"})
            finally:
                client.close()
        results.append(row)

    report = {
        "schema_version": 1,
        "run_type": "canary",
        "model_required": False,
        "input_path": "input/problem_spec.md",
        "scope": "h1",
        "task_id": TASK_ID,
        "runs": results,
        "all_passed": len(results) == args.runs and all(r["status"] == "ok" and r.get("closed") is True for r in results),
        "gate_status": "PASS" if len(results) == args.runs and all(r["status"] == "ok" and r.get("closed") is True for r in results) else "FAIL",
        "eligible_for_inference": len(results) == args.runs and all(r["status"] == "ok" and r.get("closed") is True for r in results),
    }
    write_public_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["all_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
