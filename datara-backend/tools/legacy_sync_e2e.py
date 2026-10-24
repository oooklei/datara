"""Read-only regression for the legacy sync/file_sync monitoring contract.

The script deliberately does not create or mutate workflows.  Credentials are
provided through ``--username/--password`` or ``DATARA_LEGACY_USERNAME`` /
``DATARA_LEGACY_PASSWORD`` and are never printed.  It is intended for the
isolated legacy API container (for example ``192.168.1.9:18099``).

Example::

    python -m tools.legacy_sync_e2e --base http://192.168.1.9:18099 \
      --wf-code 1 --expect-read 125 --expect-write 120 --expect-bad 5
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _request(base: str, path: str, *, method: str = "GET", body: dict[str, Any] | None = None,
             token: str | None = None) -> dict[str, Any]:
    payload = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = Request(base.rstrip("/") + path, data=payload, headers=headers, method=method)
    with urlopen(req, timeout=20) as response:  # noqa: S310 - explicit validation target
        return json.loads(response.read().decode("utf-8"))


def _data(envelope: dict[str, Any], path: str) -> Any:
    if envelope.get("code") not in (None, 0):
        raise RuntimeError(f"{path}: API code={envelope.get('code')}")
    return envelope.get("data", envelope)


def _page_rows(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = value.get("items", value.get("rows", []))
    return value if isinstance(value, list) else []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True)
    parser.add_argument("--username", default=os.getenv("DATARA_LEGACY_USERNAME"))
    parser.add_argument("--password", default=os.getenv("DATARA_LEGACY_PASSWORD"))
    parser.add_argument("--wf-code", type=int, required=True)
    parser.add_argument("--expect-read", type=int)
    parser.add_argument("--expect-write", type=int)
    parser.add_argument("--expect-bad", type=int)
    args = parser.parse_args()
    if not args.username or not args.password:
        parser.error("credentials are required via --username/--password or DATARA_LEGACY_USERNAME/DATARA_LEGACY_PASSWORD")
    try:
        login = _data(_request(args.base, "/api/v1/login", method="POST",
                               body={"user_name": args.username, "user_pwd": args.password}), "/login")
        token = login.get("token") if isinstance(login, dict) else None
        if not token:
            raise RuntimeError("login response did not contain a token")
        summary = _page_rows(_data(_request(args.base, "/api/v1/sync-tasks?page_no=1&page_size=200", token=token), "/sync-tasks"))
        row = next((item for item in summary if int(item.get("wfCode", -1)) == args.wf_code), None)
        if row is None:
            raise RuntimeError(f"workflow {args.wf_code} is not present in sync monitor")
        instances = _page_rows(_data(_request(args.base, f"/api/v1/sync-tasks/{args.wf_code}/instances?page_no=1&page_size=20", token=token), "/sync-tasks/{wf}/instances"))
        if not instances:
            raise RuntimeError(f"workflow {args.wf_code} has no recorded instances")
        latest = instances[0]
        values = {"read": latest.get("readRows"), "write": latest.get("writeRows"), "bad": latest.get("badRows")}
        expected = {"read": args.expect_read, "write": args.expect_write, "bad": args.expect_bad}
        for key, wanted in expected.items():
            if wanted is not None and int(values[key] or 0) != wanted:
                raise RuntimeError(f"{key} rows: expected {wanted}, got {values[key]}")
        print(json.dumps({"status": "ok", "workflow": args.wf_code, "instance": latest.get("instanceId"),
                          "readRows": values["read"], "writeRows": values["write"], "badRows": values["bad"]}, ensure_ascii=False))
        return 0
    except (HTTPError, URLError, KeyError, ValueError, RuntimeError) as exc:
        print(f"legacy_sync_e2e failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
