from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.bundle import freeze_bundle, load_bundle
from execcon_v2.mcp import command_stdout, decode_read_bytes, tool_text
from execcon_v2.safe_json import write_public_json
from execcon_v2.settings import load_settings
from execcon_v2.stages import get_stage

REQUIRED_OUTPUTS = ["results.json", "exercise_boundary_tier2.npy"]


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_json(value) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha_bytes(raw)


def usage(resp: dict) -> int:
    u = resp.get("usage") or {}
    return int(u.get("total_tokens") or (u.get("billing_usage") or {}).get("openai_usage", {}).get("total_tokens") or 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("h1", "h2", "h3"), default="h1")
    parser.add_argument("--specialist", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--work-root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=None, help="optional explicit candidate report path")
    parser.add_argument("--max-turns", type=int, default=32)
    args = parser.parse_args()
    stage = get_stage(args.stage)
    if args.specialist not in stage.specialists:
        parser.error(f"specialist {args.specialist!r} is not available in {args.stage}")
    settings = load_settings()

    from simple_agentic_evals import EvalClient

    run_dir = args.work_root / "runs" / args.candidate_id
    file_dir = run_dir / "files"
    report_path = args.output or (run_dir / "candidate.json")
    run_dir.mkdir(parents=True, exist_ok=True)
    file_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "schema_version": 1,
        "candidate_id": args.candidate_id,
        "specialist": args.specialist,
        "stage": args.stage,
        "task_id": stage.task_id,
        "status": "running",
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trajectory": [],
        "model_calls": 0,
        "tool_calls": 0,
        "total_tokens": 0,
    }

    client = EvalClient(base_url=settings.eval_service_url, api_key=settings.eval_service_api_key, timeout=900.0)
    task = client.task(
        settings.dataset,
        settings.benchmark,
        stage.cohort,
        task_id=stage.task_id,
        resource_mode=stage.resource_mode,
        at_stage=stage.harness,
    )
    try:
        task.start()
        report["session_id_hash"] = sha_bytes(task.session_id.encode("utf-8"))
        report["resources"] = {
            "mode": task.resources.get("mode"),
            "stage": task.resources.get("stage"),
            "names": task.resources.get("names") or [],
        }
        missing_pool = set(stage.specialists) - set(report["resources"]["names"])
        if missing_pool:
            raise RuntimeError(f"stage pool is missing specialists: {sorted(missing_pool)}")

        task.start_remote_sandbox(timeout=600.0)
        with task.mcp_session(task.remote_mcp_server, timeout=180.0) as mcp:
            tools = mcp.list_tools()[:5]
            root = command_stdout(mcp, "pwd").strip().splitlines()[-1]
            spec_bytes = decode_read_bytes(mcp.call_tool("read_bytes", {"path": "base/input/problem_spec.md"}))
            report["tool_calls"] += 1
            spec_text = spec_bytes.decode("utf-8")
            tool_schema = [
                {"type": "function", "function": {"name": t["name"], "description": t.get("description", ""), "parameters": t.get("inputSchema", {})}}
                for t in tools
            ]
            specialist_description = next(
                (item for item in task.resources.get("items", []) if item.get("name") == args.specialist),
                {"name": args.specialist},
            )
            system_prompt = f"""You are the {args.specialist} specialist in an isolated ALE sandbox.
Complete the task fully and independently. Read the complete public problem specification before coding.
Use only the provided sandbox tools and allowed software. Write every required deliverable under base/output.
The required files are results.json and exercise_boundary_tier2.npy. Keep one coherent candidate output; do not claim success unless files are actually written.
Specialist metadata: {json.dumps(specialist_description, ensure_ascii=False)}"""
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task.user_prompt + "\n\nFull public specification:\n" + spec_text},
            ]
            llm = httpx.Client(trust_env=False, timeout=httpx.Timeout(600.0, connect=30.0))
            final_text = ""
            try:
                for turn in range(1, args.max_turns + 1):
                    payload = {
                        "model": settings.model,
                        "messages": messages,
                        "tools": tool_schema,
                        "reasoning_effort": "none",
                        "max_tokens": 8192,
                        "temperature": 0.2,
                    }
                    response = llm.post(
                        settings.dmxapi_base_url + "/chat/completions",
                        headers={"Authorization": "Bearer " + settings.dmxapi_api_key},
                        json=payload,
                    )
                    response.raise_for_status()
                    data = response.json()
                    report["model_calls"] += 1
                    report["total_tokens"] += usage(data)
                    message = data["choices"][0]["message"]
                    final_text = message.get("content") or final_text
                    calls = message.get("tool_calls") or []
                    event = {"turn": turn, "content": message.get("content"), "tool_calls": []}
                    if not calls:
                        report["trajectory"].append(event)
                        break
                    messages.append({"role": "assistant", "content": message.get("content") or "", "tool_calls": calls})
                    for call in calls:
                        name = call["function"]["name"]
                        arguments = json.loads(call["function"].get("arguments") or "{}")
                        result = mcp.call_tool(name, arguments)
                        result_text = tool_text(result)
                        report["tool_calls"] += 1
                        event["tool_calls"].append(
                            {"name": name, "arguments": arguments, "result_sha256": sha_bytes(result_text.encode("utf-8")), "result_preview": result_text[:2000]}
                        )
                        messages.append({"role": "tool", "tool_call_id": call["id"], "content": result_text[:24000]})
                    report["trajectory"].append(event)
            finally:
                llm.close()

            required_output_set = set(REQUIRED_OUTPUTS)
            listing = command_stdout(mcp, "find base/output -maxdepth 1 -type f -printf '%P\\n' | LC_ALL=C sort")
            files = []
            for rel in [line.strip() for line in listing.splitlines() if line.strip() and line.strip() in required_output_set]:
                data = decode_read_bytes(mcp.call_tool("read_bytes", {"path": f"base/output/{rel}"}))
                report["tool_calls"] += 1
                local = file_dir / rel
                local.parent.mkdir(parents=True, exist_ok=True)
                local.write_bytes(data)
                files.append({"path": rel, "size": len(data), "sha256": sha_bytes(data)})
            report["claim"] = final_text
            report["files"] = files
            report["root_basename"] = Path(root).name
            from execcon_v2.public_validator import PublicValidationError, validate_outputs
            try:
                validation = validate_outputs(file_dir)
                public_self_check = "pass"
            except PublicValidationError as exc:
                validation = {"validator_version": "execcon-public-validator-v1", "error": str(exc)}
                public_self_check = "fail"
            checks = {
                "required_outputs_present": set(REQUIRED_OUTPUTS).issubset({f["path"] for f in files}),
                "public_self_check": public_self_check,
                "public_validator": validation,
            }
            report["runtime_checks"] = checks
            report["status"] = "validated" if checks["required_outputs_present"] and checks["public_self_check"] == "pass" else "ineligible"
            report["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            write_public_json(report_path, report)
            if report["status"] != "validated":
                print(json.dumps({"candidate_id": args.candidate_id, "status": report["status"], "validation": validation}, ensure_ascii=False, indent=2))
                return 2

            identity = {
                "task_id": stage.task_id,
                "cohort": stage.cohort,
                "harness": stage.harness,
                "resource_mode": stage.resource_mode,
                "stage": args.stage,
                "model": settings.model,
                "model_settings_sha256": sha_json({"max_tokens": 8192, "temperature": 0.2, "reasoning_effort": "none"}),
                "spec_sha256": sha_bytes(spec_bytes),
                "pool_sha256": sha_json({"stage": args.stage, "specialists": list(stage.specialists), "resources": report["resources"]}),
                "prompt_sha256": sha_bytes(system_prompt.encode("utf-8")),
                "tool_schema_sha256": sha_json(tool_schema),
                "code_sha256": sha_bytes(Path(__file__).read_bytes()),
                "output_protocol_sha256": sha_json(REQUIRED_OUTPUTS),
                "producer_id": f"{args.candidate_id}:{args.specialist}",
                "session_id_hash": report["session_id_hash"],
            }
            bundle = freeze_bundle(args.work_root / "bundles", identity, file_dir)
            load_bundle(bundle)
            report["bundle_hash"] = bundle.name
            report["status"] = "complete"
            write_public_json(report_path, report)
            print(json.dumps({"candidate_id": args.candidate_id, "status": report["status"], "bundle_hash": bundle.name, "files": files}, ensure_ascii=False, indent=2))
            return 0
    except Exception as exc:
        report.update({"status": "error", "error_type": type(exc).__name__, "error": str(exc), "finished_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        write_public_json(run_dir / "candidate.json", report)
        raise
    finally:
        try:
            task.close()
        except Exception as close_exc:
            report.setdefault("cleanup_errors", []).append(f"task.close: {type(close_exc).__name__}: {close_exc}")
        try:
            client.close()
        except Exception as close_exc:
            report.setdefault("cleanup_errors", []).append(f"client.close: {type(close_exc).__name__}: {close_exc}")


if __name__ == "__main__":
    raise SystemExit(main())
