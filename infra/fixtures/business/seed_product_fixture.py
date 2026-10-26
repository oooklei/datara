#!/usr/bin/env python3
"""Seed INFRA-DATA-01 platform objects through the public rebuild API only."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping


API_PREFIX = "/api/v1/rebuild"
PROJECT_NAME = "INFRA-DATA-01 电商闭环验证"
FIXTURE_DIR = Path(__file__).resolve().parent
FILE_SYNC_PATH = "/datara/files/fixtures/orders_file_sync.csv"
DEFAULT_API_BASE = "http://127.0.0.1:18091"
DEFAULT_KEY_FILE = "/lei/datara/runtime-secrets/codex-development-api.key"


class ApiError(RuntimeError):
    pass


class HostGuardError(RuntimeError):
    pass


def host_addresses() -> set[str]:
    """Return local IPv4 addresses without invoking external commands."""
    return {
        address[4][0]
        for address in socket.getaddrinfo(socket.gethostname(), None, family=socket.AF_INET)
    }


def assert_validation_host() -> None:
    addresses = host_addresses()
    if "192.168.1.9" not in addresses:
        visible = ",".join(sorted(addresses)) or "unknown"
        raise HostGuardError(
            f"execution is restricted to validation host 192.168.1.9 (found: {visible})"
        )


class Settings:
    def __init__(self, values: Mapping[str, str]):
        self.api_base = values.get("DATARA_API_BASE", DEFAULT_API_BASE).rstrip("/")
        self.key_file = Path(values.get("DATARA_VALIDATION_KEY_FILE", DEFAULT_KEY_FILE))
        shared_password = values.get("DATARA_FIXTURE_MYSQL_PASSWORD", "")
        self.source = {
            "name": "INFRA-DATA-01 source",
            "kind": "mysql",
            "host": values.get("DATARA_FIXTURE_SRC_HOST", "datara-mysql-src"),
            "port": int(values.get("DATARA_FIXTURE_SRC_PORT", "3306")),
            "database": values.get("DATARA_FIXTURE_SRC_DATABASE", "ec_retail"),
            "username": values.get("DATARA_FIXTURE_SRC_USERNAME", "root"),
            "password": values.get("DATARA_FIXTURE_SRC_PASSWORD", shared_password),
        }
        self.dw = {
            "name": "INFRA-DATA-01 dw",
            "kind": "mysql",
            "host": values.get("DATARA_FIXTURE_DW_HOST", "datara-mysql-dw"),
            "port": int(values.get("DATARA_FIXTURE_DW_PORT", "3306")),
            "database": values.get("DATARA_FIXTURE_DW_DATABASE", "datara_dw"),
            "username": values.get("DATARA_FIXTURE_DW_USERNAME", "root"),
            "password": values.get("DATARA_FIXTURE_DW_PASSWORD", shared_password),
        }

    @classmethod
    def from_env(cls, environ: Mapping[str, str]) -> "Settings":
        return cls(environ)


class UrllibTransport:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        *,
        headers: Mapping[str, str] | None = None,
        json_body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        request_headers = dict(headers or {})
        body: bytes | None = None
        if json_body is not None:
            body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
                message = payload.get("msg") or "request rejected"
            except (UnicodeDecodeError, json.JSONDecodeError):
                message = "request rejected"
            raise ApiError(f"{method} {path} failed ({exc.code}): {message}") from None
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ApiError(f"{method} {path} failed: connection unavailable") from exc
        if not isinstance(payload, dict) or payload.get("code") != 0:
            message = payload.get("msg", "invalid API response") if isinstance(payload, dict) else "invalid API response"
            raise ApiError(f"{method} {path} failed: {message}")
        return payload


def _data(response: dict[str, Any]) -> Any:
    return response["data"]


def seed(settings: Settings, transport: Any) -> dict[str, Any]:
    assert_validation_host()
    validation_key = settings.key_file.read_text(encoding="utf-8").strip()
    if not validation_key:
        raise ApiError("validation key file is empty")
    token = _data(
        transport.request(
            "POST",
            f"{API_PREFIX}/validation-token",
            headers={
                "X-Backend-Validation-Key": validation_key,
                "X-Backend-Validation-Scope": "high-priority-e2e",
            },
        )
    )["token"]
    auth = {"Authorization": f"Bearer {token}"}

    projects = _data(transport.request("GET", f"{API_PREFIX}/projects", headers=auth))["list"]
    project = next((item for item in projects if item["name"] == PROJECT_NAME), None)
    if project is None:
        project = _data(
            transport.request(
                "POST",
                f"{API_PREFIX}/projects",
                headers=auth,
                json_body={"name": PROJECT_NAME, "description": "INFRA-DATA-01 deterministic product closure fixture"},
            )
        )
    project_id = int(project["id"])

    datasource_path = f"{API_PREFIX}/projects/{project_id}/datasources"
    datasource_rows = _data(transport.request("GET", datasource_path, headers=auth))["items"]
    datasource_ids: dict[str, int] = {}
    for role, definition in (("source", settings.source), ("dw", settings.dw)):
        existing = next((row for row in datasource_rows if row["name"] == definition["name"]), None)
        if existing is None:
            existing = _data(
                transport.request("POST", datasource_path, headers=auth, json_body=definition)
            )
            datasource_rows.append(existing)
        datasource_ids[role] = int(existing["id"])

    variable_path = f"{API_PREFIX}/variables?project_id={project_id}&scopes=project"
    variables = _data(transport.request("GET", variable_path, headers=auth))
    variable_name = "fixture_key"
    if not any(row["scope"] == "project" and row["name"] == variable_name for row in variables):
        transport.request(
            "POST",
            f"{API_PREFIX}/variables?project_id={project_id}",
            headers=auth,
            json_body={
                "scope": "project",
                "name": variable_name,
                "value_type": "string",
                "value": "INFRA-DATA-01",
                "description": "Deterministic isolated validation fixture key",
            },
        )

    return {
        "project_id": project_id,
        "datasource_ids": datasource_ids,
        "variable_names": [variable_name],
        "file_sync_path": FILE_SYNC_PATH,
    }


def dry_run_summary() -> dict[str, Any]:
    return {
        "dry_run": True,
        "object_types": ["project", "datasource:source", "datasource:dw", "variable", "file_sync:csv"],
        "file_sync_path": FILE_SYNC_PATH,
        "endpoints": [
            f"{API_PREFIX}/validation-token",
            f"{API_PREFIX}/projects",
            f"{API_PREFIX}/projects/{{project_id}}/datasources",
            f"{API_PREFIX}/variables?project_id={{project_id}}",
        ],
    }


def main(argv: list[str] | None = None, *, environ: Mapping[str, str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print planned object types and endpoints only")
    args = parser.parse_args(argv)
    if args.dry_run:
        print(json.dumps(dry_run_summary(), ensure_ascii=False, sort_keys=True))
        return 0
    try:
        settings = Settings.from_env(os.environ if environ is None else environ)
        summary = seed(settings, UrllibTransport(settings.api_base))
    except (ApiError, HostGuardError, OSError, ValueError, KeyError) as exc:
        print(f"INFRA-DATA-01 seed failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
