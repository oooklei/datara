"""Read-only smoke check for the isolated newweb validation container.

Run from the 1.9 host (or a network path that can reach it):
``python isolated_web_smoke.py --base http://127.0.0.1:18101``
"""
from __future__ import annotations

import argparse
import json
import sys
from urllib.request import Request, urlopen

ROUTES = ("/", "/open/key", "/open/api", "/open/llm", "/dag", "/ide", "/p/1", "/p/1/ide", "/p/1/resources", "/p/1/dep")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:18101")
    args = parser.parse_args()
    base = args.base.rstrip("/")
    result = {}
    failed = []
    for route in ROUTES:
        try:
            request = Request(base + route, method="GET")
            with urlopen(request, timeout=10) as response:
                body = response.read()
                status = response.status
            result[route] = {"status": status, "bytes": len(body)}
            if status < 200 or status >= 300 or len(body) == 0:
                failed.append(route)
        except Exception as exc:  # pragma: no cover - exercised by remote probe
            result[route] = {"error": str(exc)}
            failed.append(route)
    print(json.dumps({"base": base, "routes": result, "ok": not failed, "failed": failed}, ensure_ascii=False, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
