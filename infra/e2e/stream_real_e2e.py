#!/usr/bin/env python3
"""Run the high-priority real stream production/observation acceptance flow.

The script exchanges the server-side validation key for a short-lived token,
creates an isolated stream job, produces and processes records, exercises
failure recovery, and writes a secret-free JSON evidence file.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


class AcceptanceFailure(RuntimeError):
    pass


def unwrap(response: requests.Response, label: str) -> Any:
    try:
        body = response.json()
    except ValueError as exc:
        raise AcceptanceFailure(f"{label}: non-JSON response HTTP {response.status_code}") from exc
    if response.status_code >= 400 or body.get("code") != 0:
        raise AcceptanceFailure(
            f"{label}: HTTP {response.status_code}, code={body.get('code')}, msg={body.get('msg')}"
        )
    return body.get("data")


def require(condition: bool, label: str) -> None:
    if not condition:
        raise AcceptanceFailure(label)


def run(base_url: str, project_id: int, key_file: Path) -> dict[str, Any]:
    validation_key = key_file.read_text(encoding="utf-8").strip()
    require(bool(validation_key), "validation key is empty")

    token_response = requests.post(
        f"{base_url}/api/v1/rebuild/validation-token",
        headers={
            "X-Backend-Validation-Key": validation_key,
            "X-Backend-Validation-Scope": "high-priority-e2e",
            "Content-Type": "application/json",
        },
        json={},
        timeout=30,
    )
    token = unwrap(token_response, "validation-token")["token"]
    session = requests.Session()
    session.headers.update(
        {"token": token, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    )

    checks: dict[str, bool] = {}
    now = datetime.now(timezone.utc)
    window_from = (now - timedelta(minutes=5)).isoformat()
    window_to = (now + timedelta(minutes=5)).isoformat()
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    root = f"{base_url}/api/v1/rebuild/stream/jobs"
    workflow_root = f"{base_url}/api/v1/rebuild/workflows"

    workflow = unwrap(
        session.post(
            workflow_root,
            json={
                "project_id": project_id,
                "name": f"实时流观摩-{stamp}",
                "description": "F-STREAM-REAL-E2E-01 实时生产、聚合、融合与恢复观摩",
                "workflow_type": "STREAM",
            },
            timeout=30,
        ),
        "create-stream-workflow",
    )
    workflow_id = int(workflow["definition_id"])
    checks["stream_workflow_created"] = workflow["workflow_type"] == "STREAM"

    created = unwrap(
        session.post(
            root,
            json={
                "project_id": project_id,
                "name": f"实时流观摩-{stamp}",
                "workflow_id": workflow_id,
                "mq_topic": f"datara.stream.e2e.{stamp.lower()}",
                "runtime_config": {
                    "mode": "fixed_rate",
                    "rows_per_sec": 5,
                    "columns": ["key", "amount"],
                },
            },
            timeout=30,
        ),
        "create-job",
    )
    job_id = int(created["id"])
    checks["created"] = created["state"] == "CREATED" and created["workflow_id"] == workflow_id

    started = unwrap(
        session.post(f"{root}/{job_id}/transitions", json={"action": "start"}, timeout=30),
        "start-job",
    )
    activated = unwrap(
        session.post(f"{root}/{job_id}/transitions", json={"action": "activate"}, timeout=30),
        "activate-job",
    )
    checks["running"] = started["state"] == "STARTING" and activated["state"] == "RUNNING"

    produced = unwrap(
        session.post(
            f"{root}/{job_id}/produce",
            json={
                "count": 6,
                "partition_id": "p-e2e",
                "start_offset": 0,
                "payload": {"key": "orders", "amount": 7},
                "schema": {"key": "string", "amount": "integer"},
                "aggregate": {"key_field": "key", "value_field": "amount", "window_size": 3},
            },
            timeout=30,
        ),
        "produce-events",
    )
    aggregate = produced["metric"]["window_result"]["aggregate"]
    checks["produced"] = produced["produced"] == 6 and produced["last_offset"] == 5
    checks["aggregated"] = bool(aggregate) and sum(item["count"] for item in aggregate) == 6

    fused = unwrap(
        session.post(
            f"{root}/{job_id}/fuse",
            json={
                "key_field": "id",
                "streams": {
                    "orders": [{"id": 1, "amount": 7}, {"id": 2, "amount": 8}],
                    "profiles": [{"id": 1, "tier": "gold"}, {"id": 2, "tier": "silver"}],
                },
            },
            timeout=30,
        ),
        "fuse-events",
    )
    checks["fused"] = fused["fused"] == 2 and len(fused["result"]) == 2

    params = {"from": window_from, "to": window_to, "limit": 100}
    metrics = unwrap(session.get(f"{root}/{job_id}/metrics", params=params, timeout=30), "metrics")
    observed = unwrap(
        session.post(
            f"{root}/{job_id}/observe",
            json={"from": window_from, "to": window_to, "limit": 100},
            timeout=30,
        ),
        "observe",
    )
    checkpoints = unwrap(session.get(f"{root}/{job_id}/checkpoints", timeout=30), "checkpoints")
    checks["metrics_visible"] = len(metrics) >= 2 and observed["snapshot_count"] >= 2
    checks["checkpoint_visible"] = any(
        row["partition_id"] == "p-e2e" and row["offset_value"] == 5 for row in checkpoints
    )

    failed = unwrap(
        session.post(f"{root}/{job_id}/transitions", json={"action": "fail"}, timeout=30),
        "fail-job",
    )
    recovering = unwrap(
        session.post(f"{root}/{job_id}/transitions", json={"action": "recover"}, timeout=30),
        "recover-job",
    )
    resumed = unwrap(
        session.post(f"{root}/{job_id}/transitions", json={"action": "activate"}, timeout=30),
        "resume-job",
    )
    recovery_events = unwrap(
        session.get(f"{root}/{job_id}/recovery-events", params=params, timeout=30),
        "recovery-events",
    )
    checks["failed_state"] = failed["state"] == "FAILED"
    checks["recovery_started"] = recovering["state"] == "RECOVERING"
    checks["recovery_activated"] = resumed["state"] == "RUNNING"
    checks["recovery_events_visible"] = len(recovery_events) >= 1

    continued = unwrap(
        session.post(
            f"{root}/{job_id}/produce",
            json={"count": 2, "partition_id": "p-e2e", "payload": {"key": "orders", "amount": 9}},
            timeout=30,
        ),
        "produce-after-recovery",
    )
    checks["checkpoint_resumed"] = continued["last_offset"] == 7
    current = unwrap(session.get(f"{root}/{job_id}", timeout=30), "get-job")
    checks["observable_running_job"] = current["state"] == "RUNNING" and current["id"] == job_id

    require(
        all(checks.values()),
        f"acceptance checks failed: {[name for name, passed in checks.items() if not passed]}",
    )
    return {
        "ticket": "F-STREAM-REAL-E2E-01",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "environment": base_url,
        "project_id": project_id,
        "workflow_id": workflow_id,
        "job_id": job_id,
        "job_name": current["name"],
        "state": current["state"],
        "last_offset": continued["last_offset"],
        "metric_points": len(metrics) + 1,
        "recovery_events": len(recovery_events),
        "checks": checks,
        "verdict": "PASS",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18091")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--key-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args.base_url.rstrip("/"), args.project_id, args.key_file)
    except Exception as exc:
        result = {"ticket": "F-STREAM-REAL-E2E-01", "verdict": "FAIL", "error": str(exc)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"VERDICT: FAIL - {exc}")
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VERDICT: PASS job={result['job_id']} checks={len(result['checks'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
