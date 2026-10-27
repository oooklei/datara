#!/usr/bin/env python3
"""Exercise quality-batch-B writes against the isolated 192.168.1.9 stack."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


def unwrap(response: requests.Response, label: str) -> Any:
    body = response.json()
    if response.status_code >= 400 or body.get("code") != 0:
        raise RuntimeError(f"{label}: HTTP {response.status_code}, code={body.get('code')}, msg={body.get('msg')}")
    return body.get("data")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18091")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    result: dict[str, Any] = {"ticket": "F-QUALITY-B-WRITE-01", "checks": {}}
    try:
        key = args.key_file.read_text(encoding="utf-8").strip()
        token = unwrap(requests.post(
            f"{base}/api/v1/rebuild/validation-token",
            headers={
                "X-Backend-Validation-Key": key,
                "X-Backend-Validation-Scope": "high-priority-e2e",
                "Content-Type": "application/json",
            },
            json={}, timeout=30,
        ), "validation-token")["token"]
        session = requests.Session()
        session.headers.update({"token": token, "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        root = f"{base}/api/v1/rebuild/governance/projects/{args.project_id}"

        open_items = unwrap(session.get(
            f"{root}/quality-exceptions", params={"page": 1, "page_size": 50, "status": "open"}, timeout=30,
        ), "list-open-exceptions")["list"]
        if not open_items:
            raise RuntimeError("no open exception fixture")
        exception_id = int(open_items[0]["id"])
        disposed = unwrap(session.patch(
            f"{root}/quality-exceptions/{exception_id}",
            json={"status": "resolved", "fix_note": f"E2E verified {stamp}"}, timeout=30,
        ), "dispose-exception")
        result["checks"]["exception_disposed"] = disposed["status"] == "resolved" and bool(disposed["handled_at"])

        report = unwrap(session.post(
            f"{root}/quality-reports",
            json={"title": f"质量批B验收-{stamp}", "scope": "project", "period": "e2e"}, timeout=30,
        ), "create-report")
        reports = unwrap(session.get(f"{root}/quality-reports", params={"page": 1, "page_size": 50}, timeout=30), "list-reports")
        result["checks"]["report_persisted"] = any(row["id"] == report["id"] for row in reports["list"])

        alarm = unwrap(session.post(
            f"{root}/quality-alarm-policies",
            json={"name": f"质量批B告警-{stamp}", "scope": "project", "metric": "failed_rows", "operator": ">", "threshold": 0, "enabled": True},
            timeout=30,
        ), "create-alarm")
        disabled = unwrap(session.patch(
            f"{root}/quality-alarm-policies/{alarm['id']}/enabled", json={"enabled": False}, timeout=30,
        ), "disable-alarm")
        result["checks"]["alarm_created_and_disabled"] = disabled["enabled"] is False
        result.update({
            "timestamp": datetime.now(timezone.utc).isoformat(), "environment": base,
            "project_id": args.project_id, "exception_id": exception_id,
            "report_id": report["id"], "alarm_policy_id": alarm["id"],
        })
        if not all(result["checks"].values()):
            raise RuntimeError("one or more checks failed")
        result["verdict"] = "PASS"
    except Exception as exc:
        result.update({"verdict": "FAIL", "error": str(exc)})
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"VERDICT: FAIL - {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VERDICT: PASS checks={len(result['checks'])} report={result['report_id']} alarm={result['alarm_policy_id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
