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
        # Executable components must expose the version-pinned resource form
        # contract.  This is intentionally checked against the deployed spec
        # response (rather than the seed source) so stale catalogues fail the
        # same high-priority regression used by the isolated environment.
        executable_specs = {
            item.get("type"): item
            for item in specs.get("items", [])
            if item.get("type") in {"sql", "python", "shell"}
        }
        expected_extensions = {
            "sql": {".sql"},
            "python": {".py", ".zip"},
            "shell": {".sh", ".bash"},
        }
        if set(executable_specs) != set(expected_extensions):
            raise RuntimeError("executable component specs are incomplete")
        for component_type, extensions in expected_extensions.items():
            params = {
                row.get("key"): row
                for row in (executable_specs[component_type].get("form") or {}).get("params", [])
            }
            source_mode = params.get("sourceMode")
            resource_ref = params.get("resourceRef")
            capability = (resource_ref or {}).get("cap") or {}
            if (source_mode or {}).get("default") != "inline":
                raise RuntimeError(f"{component_type}: sourceMode default contract failed")
            if capability.get("kind") != component_type or set(capability.get("extensions") or []) != extensions:
                raise RuntimeError(f"{component_type}: resourceRef capability contract failed")
            if capability.get("versioned") is not True or capability.get("allowLatest") is not False:
                raise RuntimeError(f"{component_type}: resourceRef version pinning contract failed")
            if not any(
                condition.get("id") == "c-resource-mode"
                and "resourceRef" in (condition.get("show") or [])
                for condition in (executable_specs[component_type].get("form") or {}).get("conditions", [])
            ):
                raise RuntimeError(f"{component_type}: resourceRef visibility condition missing")
        # Variables are a critical workflow dependency.  Exercise the same
        # save/list contract used by the frontend against the isolated DB;
        # overwriting this deterministic probe keeps repeated runs harmless.
        variable_name = "high_priority_e2e_marker"
        saved_variable = call(
            args.base,
            f"/api/v1/rebuild/variables?project_id={args.project_id}",
            token=token,
            method="POST",
            body={
                "scope": "project",
                "name": variable_name,
                "value_type": "string",
                "value": "isolated-ok",
            },
        )
        if (saved_variable.get("data") or {}).get("saved") is not True:
            raise RuntimeError("variable save contract failed")
        listed_variables = call(
            args.base,
            f"/api/v1/rebuild/variables?project_id={args.project_id}&scopes=project",
            token=token,
        )
        variable_rows = listed_variables.get("data") or []
        if not any(row.get("name") == variable_name for row in variable_rows):
            raise RuntimeError("saved variable was not returned by list contract")
        # Exercise the resolver contract as part of the remote high-priority
        # smoke, rather than treating a successful write/list as proof that
        # the value is usable by IDE/workflow consumers.
        variable_context = {"project_id": args.project_id}
        checked = call(
            args.base,
            "/api/v1/rebuild/variables/check-reference",
            token=token,
            method="POST",
            body={"expression": "${project." + variable_name + "}", "context": variable_context},
        )
        checked_data = checked.get("data") or {}
        if checked_data.get("valid") is not True or checked_data.get("diagnostics"):
            raise RuntimeError("variable reference resolution contract failed")
        preview = call(
            args.base,
            "/api/v1/rebuild/variables/preview",
            token=token,
            method="POST",
            body={"expression": "value=${project." + variable_name + "}", "context": variable_context},
        )
        preview_data = preview.get("data") or {}
        if preview_data.get("resolved_value") != "isolated-ok":
            raise RuntimeError("variable preview contract failed")
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
        # The stream requirement is a live producer/observer chain, not merely
        # a read of pre-seeded metric rows.  Generate a bounded deterministic
        # batch on the isolated running job, then observe the same window and
        # assert that the persisted metric contains the produced records.
        stream_window_from = "2026-10-25T00:00:00Z"
        stream_window_to = "2026-10-25T23:59:59Z"
        produced = call(
            args.base,
            f"/api/v1/rebuild/stream/jobs/{args.stream_job_id}/produce",
            token=token,
            method="POST",
            body={
                "count": 3,
                "partition_id": "high-priority-e2e",
                "start_offset": 0,
                "event_time": "2026-10-25T12:00:00Z",
                "payload": {"value": 1},
                "schema": {"value": "integer"},
                "aggregate": {"key_field": "partition", "value_field": "value", "window_size": 3},
            },
        )
        produced_data = produced.get("data") or {}
        if produced_data.get("produced") != 3 or (produced_data.get("metric") or {}).get("input_count") != 3:
            raise RuntimeError("stream producer did not persist the expected batch")
        observed = call(
            args.base,
            f"/api/v1/rebuild/stream/jobs/{args.stream_job_id}/observe",
            token=token,
            method="POST",
            body={"from": stream_window_from, "to": stream_window_to, "limit": 500},
        )
        observed_data = observed.get("data") or {}
        observed_metrics = observed_data.get("metrics") if isinstance(observed_data, dict) else observed_data
        if not any((row.get("input_count") or 0) >= 3 for row in (observed_metrics or [])):
            raise RuntimeError("stream observation did not include the produced batch")
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
        print(json.dumps({"health": "ok", "component_count": spec_count, "variables": "ok", "trial": "SUCCEEDED", "task_count": len(trial_data["tasks"]), "run_stats": len(stat_rows or []), "stream_produced": produced_data.get("produced"), "stream_metrics": len(metric_rows), "llm_models": len(llm_rows or []), "api_definitions": len(api_rows or []), "api_key_call_logs": "ok"}, ensure_ascii=False))
        return 0
    except (HTTPError, URLError, KeyError, RuntimeError, ValueError) as exc:
        print(f"high_priority_e2e failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
