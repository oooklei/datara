"""I13 deployed HTTP probe.

Runs inside the datara-api container and exercises the real HTTP stack:
login -> authenticated infrastructure endpoints.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


BASE = "http://127.0.0.1:8000/api/v1"


def request(method: str, path: str, body: dict | None = None, token: str | None = None) -> dict:
    data = None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["token"] = token
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # pragma: no cover - probe diagnostic
        text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code} {text}") from exc


def main() -> None:
    login = request("POST", "/login", {"user_name": "admin", "user_pwd": "Admin@123"})
    token = login.get("data", {}).get("token")
    if not token:
        raise RuntimeError(f"login did not return token: {login}")

    checks = {
        "health": request("GET", "/health", token=token),
        "components": request("GET", "/components/stats", token=token),
        "baseline": request("GET", "/components/baseline/progress", token=token),
        "lineage": request("GET", "/lineage/stats", token=token),
        "monitor": request("GET", "/monitor/nodes", token=token),
        "alerts": request("GET", "/alerts", token=token),
    }
    summary = {}
    for name, payload in checks.items():
        data = payload.get("data")
        if isinstance(data, dict):
            summary[name] = {"code": payload.get("code"), "keys": sorted(data.keys())}
        elif isinstance(data, list):
            summary[name] = {"code": payload.get("code"), "items": len(data)}
        else:
            summary[name] = {"code": payload.get("code"), "type": type(data).__name__}
    print("i13_http_probe_ok", json.dumps(summary, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
