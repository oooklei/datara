"""Read-only deployment contract probe for the isolated Datara stack.

Usage::
    python -m tools.deployment_contract_smoke

The probe deliberately performs no login, mutation, or data creation.  It
checks the two externally supported entry points (rebuild API on 18098 and
the product web host on 18091) and fails closed on redirects or non-2xx
responses.  Override URLs with ``DATARA_API_BASE``/``DATARA_WEB_BASE``.
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


API_BASE = os.getenv("DATARA_API_BASE", "http://192.168.1.9:18098").rstrip("/")
WEB_BASE = os.getenv("DATARA_WEB_BASE", "http://192.168.1.9:18091").rstrip("/")

# These are product routes, not validation pages.  Keeping this list here
# makes a stale web image (which may still return index.html for every path)
# visible in deployment evidence without exercising authenticated mutations.
WEB_ROUTES = ("/", "/dag", "/open/key", "/open/api", "/open/llm", "/p/1", "/p/1/ide")


def probe(url: str, *, accept: str = "*/*") -> tuple[int, str, str]:
    req = Request(url, headers={"Accept": accept, "Cache-Control": "no-cache"})
    try:
        with urlopen(req, timeout=10) as response:
            body = response.read(512).decode("utf-8", "replace")
            return response.status, response.headers.get("Content-Type", ""), body
    except (HTTPError, URLError, TimeoutError) as exc:
        code = getattr(exc, "code", 0) or 0
        return int(code), "", str(exc)


def main() -> int:
    status, content_type, body = probe(f"{API_BASE}/api/v1/rebuild/health", accept="application/json")
    if status != 200:
        raise RuntimeError(f"API health returned HTTP {status}: {body[:160]}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("API health did not return JSON") from exc
    if payload.get("code") != 0 or payload.get("data", {}).get("status") != "ok":
        raise RuntimeError(f"API health envelope is not successful: {payload}")

    routes: dict[str, int] = {}
    for route in WEB_ROUTES:
        route_status, route_type, route_body = probe(f"{WEB_BASE}{route}", accept="text/html")
        if route_status != 200:
            raise RuntimeError(f"web route {route} returned HTTP {route_status}: {route_body[:120]}")
        if route == "/" and "<html" not in route_body.lower():
            raise RuntimeError("web root did not return an HTML document")
        routes[route] = route_status

    print(json.dumps({"api": {"status": status, "content_type": content_type}, "web": routes}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # pragma: no cover - CLI failure presentation
        print(f"deployment_contract_smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
