"""Plan, import, or clean up isolated ecommerce simulation variables.

Dry-run is the default and does not contact Datara. Mutations require a WSL
runtime (or an explicit opt-in to the isolated validation host), an explicit
project ID, a target URL, and DATARA_SIM_TOKEN in memory. Only variables
carrying this fixture's exact namespace marker can be updated or deleted. No
governance object or project is created by this tool.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


FIXTURE = Path(__file__).with_name("ECOM_SIM_20261030.json")
NAMESPACE = "ECOM_SIM_20261030"
PREFIX = "ecom_sim_20261030_"
MARKER = f"simulation-fixture:{NAMESPACE}"
VALIDATION_HOST = "192.168.1.9"


def variable_definitions(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    if fixture.get("namespace") != NAMESPACE:
        raise ValueError("unexpected fixture namespace")
    summary = fixture["expected"]
    return [
        {"scope": "global", "name": PREFIX + "quality_threshold", "value_type": "decimal", "value": "0.01", "description": MARKER + " acceptable quality failure rate"},
        {"scope": "project", "name": PREFIX + "biz_date", "value_type": "date", "value": "2026-10-23", "description": MARKER + " order partition"},
        {"scope": "project", "name": PREFIX + "currency", "value_type": "string", "value": fixture["currency"], "description": MARKER + " settlement currency"},
        {"scope": "project", "name": PREFIX + "source_schema", "value_type": "string", "value": "ecom_sim_20261030", "description": MARKER + " isolated fact schema"},
        {"scope": "project", "name": PREFIX + "batch_size", "value_type": "integer", "value": "2000", "description": MARKER + " nightly batch size"},
        {"scope": "project", "name": PREFIX + "safety_stock", "value_type": "integer", "value": "10", "description": MARKER + " inventory safety stock threshold"},
        {"scope": "project", "name": PREFIX + "paid_orders", "value_type": "integer", "value": str(summary["paid_orders"]), "description": MARKER + " expected paid orders"},
        {"scope": "project", "name": PREFIX + "net_paid_cents", "value_type": "integer", "value": str(summary["net_paid_cents"]), "description": MARKER + " expected net paid cents"},
    ]


def is_wsl() -> bool:
    release = Path("/proc/sys/kernel/osrelease")
    return sys.platform == "linux" and release.exists() and "microsoft" in release.read_text(encoding="utf-8").lower()


def mutation_allowed() -> bool:
    """WSL by default; the isolated validation host needs an explicit opt-in."""
    if is_wsl():
        return True
    if os.environ.get("DATARA_SIM_ALLOW_HOST", "").strip() != VALIDATION_HOST:
        return False
    addresses = subprocess.run(["hostname", "-I"], capture_output=True, text=True, check=False).stdout
    return VALIDATION_HOST in addresses.split()


class DataraClient:
    def __init__(self, base_url: str, token: str):
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme != "http" or not parsed.netloc or parsed.path not in ("", "/"):
            raise ValueError("target must be an http origin without a path")
        if not token:
            raise ValueError("DATARA_SIM_TOKEN is required for network actions")
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url + "/api/v1/rebuild" + path,
            data=body,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                envelope = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Datara {method} {path.split('?')[0]} returned HTTP {exc.code}") from None
        if not isinstance(envelope, dict) or envelope.get("code") != 0:
            raise RuntimeError(f"Datara {method} {path.split('?')[0]} rejected the request")
        return envelope.get("data")


def existing_variables(client: DataraClient, project_id: int, definitions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Fetch the fixture's own scopes (project + global) in one list call.

    ``project_id`` stays required by the platform contract even for ``global``
    rows; the platform resolves ``global`` to its ownerless key internally.
    """
    scopes = ",".join(sorted({row["scope"] for row in definitions}))
    query = urllib.parse.urlencode({"project_id": project_id, "scopes": scopes})
    rows = client.request("GET", "/variables?" + query)
    if not isinstance(rows, list):
        raise RuntimeError("variable list has unexpected shape")
    wanted = {(row["scope"], row["name"]) for row in definitions}
    return {row["name"]: row for row in rows if isinstance(row, dict) and (row.get("scope"), row.get("name")) in wanted}


def apply_variables(client: DataraClient, project_id: int, definitions: list[dict[str, Any]]) -> list[str]:
    existing = existing_variables(client, project_id, definitions)
    actions = []
    for definition in definitions:
        name = definition["name"]
        current = existing.get(name)
        if current is not None and current.get("scope") != definition["scope"]:
            raise RuntimeError(f"refusing to overwrite {name} in a different scope")
        if current is not None and not str(current.get("description", "")).startswith(MARKER):
            raise RuntimeError(f"refusing to overwrite non-fixture variable {name}")
        if current is not None and all(current.get(field) == definition[field] for field in ("value", "value_type", "description")):
            actions.append(f"unchanged {name}")
            continue
        query = urllib.parse.urlencode({"project_id": project_id})
        client.request("POST", "/variables?" + query, definition)
        actions.append(f"saved {name}")
    return actions


def cleanup_variables(client: DataraClient, project_id: int, definitions: list[dict[str, Any]]) -> list[str]:
    existing = existing_variables(client, project_id, definitions)
    actions = []
    for definition in definitions:
        name = definition["name"]
        current = existing.get(name)
        if current is None:
            actions.append(f"absent {name}")
            continue
        if not str(current.get("description", "")).startswith(MARKER):
            raise RuntimeError(f"refusing to delete non-fixture variable {name}")
        query = urllib.parse.urlencode({"project_id": project_id, "scope": definition["scope"]})
        client.request("DELETE", "/variables/" + urllib.parse.quote(name, safe="") + "?" + query)
        actions.append(f"deleted {name}")
    return actions


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply-variables", action="store_true")
    mode.add_argument("--cleanup-variables", action="store_true")
    parser.add_argument("--project-id", type=int)
    parser.add_argument("--target", help="Datara HTTP origin, required for network actions")
    args = parser.parse_args()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    definitions = variable_definitions(fixture)
    if not args.apply_variables and not args.cleanup_variables:
        print(json.dumps({"mode": "dry-run", "namespace": NAMESPACE, "variables": definitions, "governance_objects": "not imported: no matching delete API"}, ensure_ascii=False, indent=2))
        return
    if not mutation_allowed():
        parser.error("mutations are allowed only from local WSL, or with DATARA_SIM_ALLOW_HOST on the isolated validation host")
    if args.project_id is None or args.project_id <= 0 or not args.target:
        parser.error("--project-id and --target are required for network actions")
    client = DataraClient(args.target, os.environ.get("DATARA_SIM_TOKEN", ""))
    actions = (apply_variables if args.apply_variables else cleanup_variables)(client, args.project_id, definitions)
    print(json.dumps({"namespace": NAMESPACE, "project_id": args.project_id, "actions": actions}, ensure_ascii=False))


if __name__ == "__main__":
    main()
