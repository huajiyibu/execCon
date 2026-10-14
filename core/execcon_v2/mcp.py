from __future__ import annotations

import base64
import json
from typing import Any


class McpToolError(RuntimeError):
    pass


def tool_text(response: dict[str, Any]) -> str:
    result = response.get("result") or {}
    content = result.get("content") or []
    return "\n".join(
        str(item.get("text") or "")
        for item in content
        if isinstance(item, dict) and item.get("type") in (None, "text")
    ).strip()


def call_text(mcp: Any, name: str, arguments: dict[str, Any]) -> str:
    response = mcp.call_tool(name, arguments)
    if not isinstance(response, dict):
        raise McpToolError(f"{name} returned a non-object response")
    if response.get("error") is not None:
        raise McpToolError(f"{name} returned a JSON-RPC error: {response['error']}")
    if not isinstance(response.get("result"), dict):
        raise McpToolError(f"{name} returned no result object")
    result = response["result"]
    if result.get("isError") or result.get("is_error"):
        raise McpToolError(f"{name} failed: {tool_text(response)}")
    return tool_text(response)


def decode_read_bytes(response: dict[str, Any]) -> bytes:
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
        raise McpToolError("read_bytes did not return base64 text")
    try:
        return base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise McpToolError("read_bytes returned invalid base64") from exc


def command_stdout(mcp: Any, command: str, timeout: float = 120.0) -> str:
    raw = call_text(mcp, "run_command", {"command": command, "timeout": timeout})
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if not isinstance(parsed, dict):
        return raw
    if "exit_code" not in parsed and "returncode" not in parsed:
        raise McpToolError("run_command returned no exit code")
    exit_code = parsed.get("exit_code", parsed.get("returncode"))
    if exit_code != 0:
        stderr = parsed.get("stderr") or ""
        raise McpToolError(f"command exited {exit_code}: {stderr[:500]}")
    return str(parsed.get("stdout") or "")
