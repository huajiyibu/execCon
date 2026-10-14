from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "core"))

from execcon_v2.mcp import call_text, command_stdout, decode_read_bytes
from execcon_v2.safe_json import write_public_json
from execcon_v2.settings import load_settings


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect public task inputs without solving or grading.")
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--cohort", type=int, required=True)
    parser.add_argument("--harness", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    settings = load_settings(require_model_key=False)
    from simple_agentic_evals import EvalClient

    report = {
        "schema_version": 1,
        "selector": {
            "dataset": settings.dataset,
            "benchmark": settings.benchmark,
            "version": args.cohort,
            "at_stage": args.harness,
            "resource_mode": "accumulative",
            "task_id": args.task_id,
        },
    }
    with EvalClient(
        base_url=settings.eval_service_url,
        api_key=settings.eval_service_api_key,
        timeout=600.0,
    ) as client:
        task = client.task(
            settings.dataset,
            settings.benchmark,
            args.cohort,
            task_id=args.task_id,
            resource_mode="accumulative",
            at_stage=args.harness,
        )
        try:
            task.start()
            report["public_prompts"] = {
                "system_prompt": task.system_prompt,
                "user_prompt": task.user_prompt,
            }
            report["resources"] = {
                "kind": task.resources.get("kind"),
                "mode": task.resources.get("mode"),
                "stage": task.resources.get("stage"),
                "count": task.resources.get("count"),
                "names": task.resources.get("names") or [],
                "items": [
                    {
                        "name": item.get("name"),
                        "title": item.get("title"),
                        "description": item.get("description"),
                        "tools": item.get("tools") or [],
                        "present": item.get("present"),
                    }
                    for item in (task.resources.get("items") or [])
                ],
            }
            api_inputs = []
            for item in task.inputs():
                rel = str(item.get("path") or "")
                if not rel:
                    continue
                raw = task.fetch_input(rel)
                api_inputs.append({"path": rel, "size": len(raw), "sha256": sha256(raw)})
            report["api_inputs"] = api_inputs

            task.start_remote_sandbox(timeout=600.0)
            server = task.remote_mcp_server
            if server is None:
                raise RuntimeError("remote sandbox started without an MCP server")
            with task.mcp_session(server, timeout=180.0) as mcp:
                tools = mcp.list_tools()
                report["mcp_tools"] = [
                    {
                        "name": tool.get("name"),
                        "input_schema_sha256": sha256(
                            __import__("json").dumps(
                                tool.get("inputSchema") or {}, sort_keys=True, separators=(",", ":")
                            ).encode("utf-8")
                        ),
                    }
                    for tool in tools
                ]
                root = command_stdout(mcp, "pwd").strip().splitlines()[-1]
                listing = command_stdout(
                    mcp,
                    "find base/input -type f -printf '%P\\t%s\\n' | LC_ALL=C sort",
                )
                report["sandbox"] = {"root_basename": Path(root).name, "input_listing": listing.splitlines()}

                spec_candidates = []
                for line in listing.splitlines():
                    rel = line.split("\t", 1)[0].strip()
                    if not rel.lower().endswith((".md", ".txt")):
                        continue
                    remote_bytes = decode_read_bytes(
                        mcp.call_tool("read_bytes", {"path": f"{root}/base/input/{rel}"})
                    )
                    text = remote_bytes.decode("utf-8")
                    api_match = next((item for item in api_inputs if item["path"] == f"input/{rel}"), None)
                    spec_candidates.append(
                        {
                            "path": rel,
                            "size": len(remote_bytes),
                            "sha256": sha256(remote_bytes),
                            "matches_api_bytes": bool(api_match and api_match["sha256"] == sha256(remote_bytes)),
                            "text": text,
                        }
                    )
                report["public_text_inputs"] = spec_candidates
        finally:
            task.close()

    write_public_json(args.output, report)
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
