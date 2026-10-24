"""Unified high-priority 1.9 regression for the rebuilt backend.

Usage::

    python -m tools.high_priority_e2e --base http://192.168.1.9:18098 \
      --username codex-smoke --password '...'

The script intentionally creates no definitions and only runs the seeded Trial
snapshot; it is safe for the isolated validation database.
"""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def call(base: str, path: str, *, token: str | None = None, method: str = "GET", body: dict | None = None) -> dict:
    payload = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(base.rstrip("/") + path, data=payload, headers=headers, method=method)
    with urlopen(request, timeout=20) as response:  # noqa: S310 - explicit validation endpoint
        if response.status != 200:
            raise RuntimeError(f"{path}: HTTP {response.status}")
        return json.loads(response.read().decode())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--project-id", type=int, default=1)
    parser.add_argument("--definition-id", type=int, default=1)
    parser.add_argument("--snapshot-id", type=int, default=2)
    parser.add_argument("--stream-job-id", type=int, default=1)
    args = parser.parse_args()
    try:
        health = call(args.base, "/api/v1/rebuild/health")
        if health.get("code") != 0:
            raise RuntimeError("health envelope is not successful")
        login = call(args.base, "/api/v1/rebuild/login", method="POST", body={"username": args.username, "password": args.password})
        token = login["data"]["token"]
        specs = call(args.base, "/api/v1/rebuild/components/spec", token=token)
        spec_count = len(specs.get("items", []))
        if spec_count < 4:
            raise RuntimeError(f"component catalogue too small: {spec_count}")
        trial = call(
            args.base,
            f"/api/v1/rebuild/trial/definitions/{args.definition_id}/run",
            token=token,
            method="POST",
            body={"project_id": args.project_id, "snapshot_id": args.snapshot_id, "dependency_mock": True},
        )
        trial_data = trial["data"]
        if trial_data.get("status") != "SUCCEEDED" or len(trial_data.get("tasks", [])) < 6:
            raise RuntimeError(f"trial did not succeed: {trial_data}")
        stats = call(args.base, f"/api/v1/rebuild/execution/run-stats?project_id={args.project_id}&limit=50", token=token)
        metrics = call(args.base, f"/api/v1/rebuild/stream/jobs/{args.stream_job_id}/metrics?from=2026-10-24T00:00:00Z&to=2026-10-26T00:00:00Z", token=token)
        if not stats.get("data", {}).get("items"):
            raise RuntimeError("run statistics are empty")
        metric_rows = metrics.get("data", {}).get("metrics") if isinstance(metrics.get("data"), dict) else metrics.get("data")
        if not metric_rows:
            raise RuntimeError("stream metrics are empty")
        stat_rows = stats.get("data", {}).get("items") if isinstance(stats.get("data"), dict) else stats.get("data")
        print(json.dumps({"health": "ok", "component_count": spec_count, "trial": "SUCCEEDED", "task_count": len(trial_data["tasks"]), "run_stats": len(stat_rows or []), "stream_metrics": len(metric_rows)}, ensure_ascii=False))
        return 0
    except (HTTPError, URLError, KeyError, RuntimeError, ValueError) as exc:
        print(f"high_priority_e2e failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
