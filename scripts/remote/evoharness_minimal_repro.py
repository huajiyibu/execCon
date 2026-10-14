#!/usr/bin/env python3
"""Minimal, credential-free reproduction for ALE h1 runtime/MCP issues.

Credentials are read from EVAL_SERVICE_API_KEY at runtime and are never printed.
This script performs no model call and never invokes the hidden grader.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path

from simple_agentic_evals import EvalClient

TASK_ID = "business_finance/american_option_pricing_ls"
DATASET = "evovling_agents"
BENCHMARK = "ale"


def tool_text(response: dict) -> str:
    result = response.get("result") or {}
    content = result.get("content") or []
    return "\n".join(
        str(item.get("text") or "")
        for item in content
        if isinstance(item, dict) and item.get("type") in (None, "text")
    ).strip()


def decode_read_bytes(response: dict) -> bytes:
    raw = tool_text(response)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = raw
    if isinstance(payload, dict):
        encoded = payload.get("content_b64") or payload.get("data") or payload.get("content")
    else:
        encoded = payload
    if not isinstance(encoded, str):
        raise RuntimeError("read_bytes did not return base64 text")
    return base64.b64decode(encoded, validate=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("evoharness_repro_report.json"))
    args = parser.parse_args()

    api_key = os.environ.get("EVAL_SERVICE_API_KEY")
    if not api_key:
        raise SystemExit("EVAL_SERVICE_API_KEY is required")

    report = {
        "schema_version": 1,
        "task_id": TASK_ID,
        "dataset": DATASET,
        "benchmark": BENCHMARK,
        "model_call": False,
        "grader_call": False,
        "checks": {},
    }
    client = EvalClient(api_key=api_key, timeout=180.0)
    task = client.task(
        DATASET,
        BENCHMARK,
        1,
        task_id=TASK_ID,
        resource_mode="accumulative",
        at_stage=1,
    )
    try:
        task.start()
        report["checks"]["session_started"] = True
        api_bytes = task.fetch_input("input/problem_spec.md")
        report["checks"]["api_input"] = {
            "size": len(api_bytes),
            "sha256": hashlib.sha256(api_bytes).hexdigest(),
        }
        task.start_remote_sandbox(timeout=180.0)
        server = task.remote_mcp_server
        if server is None:
            raise RuntimeError("remote sandbox returned no MCP server")

        with task.mcp_session(server, timeout=90.0) as mcp:
            runtime_response = mcp.call_tool(
                "run_command",
                {"command": "software/python.sh --version", "timeout": 60},
            )
            report["checks"]["runtime_probe"] = runtime_response

            cache_response = mcp.call_tool(
                "run_command",
                {
                    "command": "mkdir -p /home/user/.cache/uv && printf cache_write_ok",
                    "timeout": 60,
                },
            )
            report["checks"]["cache_probe"] = cache_response

            read_response = mcp.call_tool(
                "read_bytes",
                {"path": "base/input/problem_spec.md"},
            )
            report["checks"]["read_bytes_raw"] = read_response
            try:
                remote_bytes = decode_read_bytes(read_response)
                report["checks"]["read_bytes_decoded"] = {
                    "status": "ok",
                    "size": len(remote_bytes),
                    "sha256": hashlib.sha256(remote_bytes).hexdigest(),
                    "api_remote_equal": remote_bytes == api_bytes,
                }
            except Exception as exc:
                report["checks"]["read_bytes_decoded"] = {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }

        report["status"] = "completed"
    except Exception as exc:
        report["status"] = "error"
        report["error_type"] = type(exc).__name__
        report["error"] = str(exc)
    finally:
        try:
            task.close()
            report["session_closed"] = True
        except Exception as exc:
            report["session_closed"] = False
            report["close_error"] = f"{type(exc).__name__}: {exc}"
        client.close()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": report.get("status"), "output": str(args.output)}, ensure_ascii=False))
    return 0 if report.get("status") == "completed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
