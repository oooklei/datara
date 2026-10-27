#!/usr/bin/env python3
"""Verify the R8-A registry and seven non-SQL production tool bridges."""

from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

import requests


TOOLS: dict[str, dict[str, Any]] = {
    "search_schema": {"project_id": 35, "keyword": "order", "limit": 5},
    "validate_sql": {"project_id": 35, "datasource_id": 1, "sql": "SELECT 1"},
    "get_workflow": {"project_id": 35, "workflow_id": 1},
    "validate_workflow": {"project_id": 35, "definition": {"nodes": [], "edges": []}},
    "inspect_workflow_run": {"project_id": 35, "run_id": "ai-bridge-smoke", "include_tasks": True},
    "get_task_metrics": {
        "project_id": 35,
        "time_window": {"from": "2026-10-26T00:00:00Z", "to": "2026-10-27T00:00:00Z"},
        "group_by": "status",
    },
    "get_lineage": {
        "project_id": 35,
        "entity_type": "TABLE",
        "entity": "ecommerce.orders",
        "direction": "BOTH",
        "depth": 3,
    },
}
FORBIDDEN = {"TOOL_DISABLED", "TOOL_NOT_FOUND", "TOOL_VERSION_MISMATCH", "INTERNAL_ERROR"}


def payload(response: requests.Response, label: str) -> Any:
    body = response.json()
    if response.status_code >= 400:
        raise RuntimeError(f"{label}: HTTP {response.status_code}")
    if isinstance(body, dict) and body.get("code") == 0:
        return body.get("data")
    return body


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18091")
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    key = args.key_file.read_text(encoding="utf-8").strip()
    token_data = payload(requests.post(
        f"{base}/api/v1/rebuild/validation-token",
        headers={"X-Backend-Validation-Key": key, "X-Backend-Validation-Scope": "high-priority-e2e"},
        json={}, timeout=30,
    ), "validation-token")
    token = token_data["token"]
    headers = {"token": token, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    registry = payload(requests.get(f"{base}/api/v1/rebuild/ai/tools", headers=headers, timeout=30), "registry")
    enabled = {entry["name"] for entry in registry if entry.get("enabled")}
    expected = set(TOOLS) | {"run_sql"}
    checks: dict[str, Any] = {"registry_all_enabled": enabled == expected, "tools": {}}

    for tool, params in TOOLS.items():
        response = payload(requests.post(
            f"{base}/api/v1/rebuild/ai/tool-calls",
            headers=headers,
            json={
                "tool_call_id": str(uuid.uuid4()),
                "tool": tool,
                "tool_version": 1,
                "params": params,
                "page_context": {"context_type": "PROJECT", "context_ref": {"project_id": 35}},
            }, timeout=35,
        ), tool)
        code = (response.get("error") or {}).get("code")
        checks["tools"][tool] = {
            "status": response.get("status"),
            "error_code": code,
            "details": (response.get("error") or {}).get("details"),
        }

    bridge_failures = [name for name, item in checks["tools"].items() if item["error_code"] in FORBIDDEN]
    checks["bridge_failures"] = bridge_failures
    checks["verdict"] = (
        "PASS" if checks["registry_all_enabled"] and len(checks["tools"]) == 7 and not bridge_failures else "FAIL"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(checks, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VERDICT: {checks['verdict']} registry={len(enabled)}/8 tools={len(checks['tools'])}/7")
    return 0 if checks["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
