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


def call(base: str, path: str, *, token: str | None = None, headers_extra: dict[str, str] | None = None, method: str = "GET", body: dict | None = None, statuses: tuple[int, ...] = (200,)) -> dict:
    payload = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if headers_extra:
        headers.update(headers_extra)
    request = Request(base.rstrip("/") + path, data=payload, headers=headers, method=method)
    with urlopen(request, timeout=20) as response:  # noqa: S310 - explicit validation endpoint
        if response.status not in statuses:
            raise RuntimeError(f"{path}: HTTP {response.status}")
        return json.loads(response.read().decode())


def expect_rejected(base: str, path: str, *, headers_extra: dict[str, str], statuses: tuple[int, ...] = (401, 403)) -> None:
    """Assert an auth-protected request is rejected without leaking response details."""
    request = Request(base.rstrip("/") + path, headers={"Content-Type": "application/json", **headers_extra})
    try:
        with urlopen(request, timeout=20):  # noqa: S310 - explicit validation endpoint
            raise RuntimeError(f"{path}: revoked credential was accepted")
    except HTTPError as exc:
        if exc.code not in statuses:
            raise RuntimeError(f"{path}: unexpected rejection HTTP {exc.code}") from exc


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
        llm = call(args.base, "/api/v1/rebuild/llm-models?offset=0&limit=50", token=token)
        api_defs = call(args.base, "/api/v1/open/definitions", token=token)
        issued = call(
            args.base,
            "/api/v1/open/api-keys",
            token=token,
            method="POST",
            body={"name": "high-priority-e2e", "scopes": {"permissions": ["security:read"], "projectIds": []}},
            statuses=(200, 201),
        )
        issued_data = issued.get("data") or {}
        plain_key = issued_data.get("plainKey") or issued_data.get("plain_key")
        if not plain_key:
            raise RuntimeError("API-Key issuance did not return one-time plaintext")
        key_logs = call(args.base, "/api/v1/open/call-logs", headers_extra={"X-API-Key": plain_key})
        key_id = (issued_data.get("key") or {}).get("id")
        if key_id is not None:
            try:
                call(args.base, f"/api/v1/open/api-keys/{key_id}/revoke", token=token, method="POST")
            finally:
                # Prove revocation is enforced, while keeping the one-time key out of logs.
                expect_rejected(args.base, "/api/v1/open/call-logs", headers_extra={"X-API-Key": plain_key})
        if not stats.get("data", {}).get("items"):
            raise RuntimeError("run statistics are empty")
        metric_rows = metrics.get("data", {}).get("metrics") if isinstance(metrics.get("data"), dict) else metrics.get("data")
        if not metric_rows:
            raise RuntimeError("stream metrics are empty")
        llm_rows = llm.get("data", {}).get("items") if isinstance(llm.get("data"), dict) else llm.get("data")
        api_rows = api_defs.get("data", {}).get("items") if isinstance(api_defs.get("data"), dict) else api_defs.get("data")
        if llm_rows is None or api_rows is None:
            raise RuntimeError("LLM/API management read models are unavailable")
        if key_logs.get("code") != 0:
            raise RuntimeError("scoped API-Key call-log read failed")
        stat_rows = stats.get("data", {}).get("items") if isinstance(stats.get("data"), dict) else stats.get("data")
        print(json.dumps({"health": "ok", "component_count": spec_count, "trial": "SUCCEEDED", "task_count": len(trial_data["tasks"]), "run_stats": len(stat_rows or []), "stream_metrics": len(metric_rows), "llm_models": len(llm_rows or []), "api_definitions": len(api_rows or []), "api_key_call_logs": "ok"}, ensure_ascii=False))
        return 0
    except (HTTPError, URLError, KeyError, RuntimeError, ValueError) as exc:
        print(f"high_priority_e2e failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
