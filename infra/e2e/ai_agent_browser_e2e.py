#!/usr/bin/env python3
"""Observe the deployed AI conversation/tool loop with only the absent LLM mocked."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import Route, sync_playwright


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18091")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--executable-path", type=Path)
    parser.add_argument("--screenshot", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    key = args.key_file.read_text(encoding="utf-8").strip()
    token_response = requests.post(
        f"{base}/api/v1/rebuild/validation-token",
        headers={"X-Backend-Validation-Key": key, "X-Backend-Validation-Scope": "high-priority-e2e"},
        json={}, timeout=30,
    ).json()
    token = token_response["data"]["token"]
    target = f"{base}/#/p/{args.project_id}/dashboard"
    calls: list[dict[str, Any]] = []
    tool_statuses: list[str] = []
    console_errors: list[str] = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.screenshot.parent.mkdir(parents=True, exist_ok=True)

    def llm_route(route: Route) -> None:
        body = route.request.post_data_json
        calls.append(body)
        has_tool_result = any(item.get("role") == "tool" for item in body.get("messages", []))
        message = (
            {"role": "assistant", "content": "已根据真实 search_schema 工具结果完成订单表分析。"}
            if has_tool_result else
            {"role": "assistant", "content": None, "tool_calls": [{
                "id": "call-e2e-1", "type": "function",
                "function": {"name": "search_schema", "arguments": '{"project_id":999,"keyword":"order","limit":5}'},
            }]}
        )
        route.fulfill(status=200, content_type="application/json", body=json.dumps({
            "message": message, "model": "datara-e2e-agent-simulator", "usage": {"total_tokens": 12},
        }))

    result: dict[str, Any]
    try:
        with sync_playwright() as playwright:
            launch: dict[str, Any] = {"headless": True, "args": ["--no-sandbox"]}
            if args.executable_path is not None:
                launch["executable_path"] = str(args.executable_path)
            browser = playwright.chromium.launch(**launch)
            context = browser.new_context(viewport={"width": 1600, "height": 1000})
            page = context.new_page()
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("response", lambda response: tool_statuses.append(str(response.status)) if "/ai/tool-calls" in response.url else None)
            page.route("**/api/v1/rebuild/ai/chat", llm_route)
            page.add_init_script(f"globalThis.__DATARA_TEST_TOKEN__ = {json.dumps(token)};")
            page.goto(target, wait_until="domcontentloaded", timeout=30_000)
            page.locator("[data-ai-fab]").click()
            project_input = page.locator("[data-ai-chat-project-id]")
            if project_input.count() > 0:
                project_input.fill(str(args.project_id))
            page.locator("[data-ai-chat-input]").fill("查找订单表并总结")
            page.locator("[data-ai-chat-send]").wait_for(state="visible", timeout=10_000)
            page.locator("[data-ai-chat-send]").click()
            transcript = page.locator("[data-ai-chat-transcript]")
            transcript.get_by_text("已根据真实 search_schema 工具结果完成订单表分析。").wait_for(timeout=30_000)
            text = transcript.inner_text()
            transcript.screenshot(path=str(args.screenshot))
            browser.close()
        project_ids = [item.get("project_id") for item in calls[0]["messages"] if item.get("role") == "user"]
        result = {
            "ticket": "F-AI-AGENT-CHAT-01",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "url": target,
            "llm_simulation": "protocol-only; no external model credential configured",
            "llm_turns": len(calls),
            "real_tool_http_statuses": tool_statuses,
            "transcript": text,
            "user_message_project_ids": project_ids,
            "console_error_count": len(console_errors),
            "verdict": "PASS" if len(calls) == 2 and tool_statuses == ["200"] and "search_schema" in text else "FAIL",
        }
    except Exception as exc:
        result = {"ticket": "F-AI-AGENT-CHAT-01", "url": target, "error": str(exc), "verdict": "FAIL"}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VERDICT: {result['verdict']} llm_turns={result.get('llm_turns', 0)} tool_calls={len(tool_statuses)}")
    return 0 if result["verdict"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
