"""Read-only-safe legacy workflow rerun probe.

The rebuilt validation service intentionally does not expose ``/instances``.
This helper is for an isolated legacy API container only.  It never creates a
workflow; callers provide an existing terminal instance and credentials via
arguments/environment.  A missing route is reported as ``legacy_route_missing``
so it cannot be mistaken for a passing E2E.

Example::

    python tools/legacy_rerun_e2e.py --base http://192.168.1.9:18099 \
      --token "$DATARA_TOKEN" --instance-id "$DATARA_INSTANCE"
"""

from __future__ import annotations

import argparse
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def request(base: str, path: str, token: str, *, method: str = "GET") -> tuple[int, dict]:
    body = b"{}" if method == "POST" else None
    req = Request(
        base.rstrip("/") + path,
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urlopen(req, timeout=20) as response:  # noqa: S310 - explicit test target
            return response.status, json.loads(response.read().decode() or "{}")
    except HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            payload = json.loads(raw or "{}")
        except json.JSONDecodeError:
            payload = {"raw": raw[:200]}
        return exc.code, payload
    except URLError as exc:
        raise RuntimeError(f"legacy endpoint unavailable: {exc.reason}") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--instance-id", required=True)
    args = parser.parse_args()

    instance_path = f"/api/v1/instances/{args.instance_id}"
    status, detail = request(args.base, instance_path, args.token)
    if status == 404 and (not detail or detail.get("detail") == "Not Found"):
        print(json.dumps({"status": "legacy_route_missing"}))
        return 2
    if status != 200:
        raise RuntimeError(f"instance lookup failed: HTTP {status} {detail}")
    state = ((detail.get("data") or {}).get("state") or "").lower()
    if state not in {"success", "succeeded", "failure", "failed", "kill", "stopped", "canceled"}:
        raise RuntimeError(f"instance is not terminal: {state or 'unknown'}")

    code, rerun = request(args.base, instance_path + "/rerun", args.token, method="POST")
    if code != 200 or (rerun.get("code") not in (None, 0)):
        raise RuntimeError(f"rerun failed: HTTP {code} {rerun}")
    data = rerun.get("data") or {}
    if not data.get("instanceId") and not data.get("commandId") and not data.get("attempts"):
        raise RuntimeError(f"rerun response lacks command/attempt evidence: {rerun}")
    print(json.dumps({"status": "ok", "sourceInstance": args.instance_id, "rerun": data}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
