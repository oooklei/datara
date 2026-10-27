#!/bin/sh
set -eu

KEY="$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' datara-rebuild-api | sed -n 's/^REBUILD_VALIDATION_KEY=//p')"
test -n "$KEY"
TOKEN="$(curl -fsS -X POST \
  -H 'Content-Type: application/json' \
  -H 'X-Backend-Validation-Scope: high-priority-e2e' \
  -H "X-Backend-Validation-Key: $KEY" \
  --data '{}' \
  http://127.0.0.1:18091/api/v1/rebuild/validation-token \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"]["token"])')"
unset KEY
test -n "$TOKEN"
printf '%s\n' "$TOKEN" | docker run --rm -i \
  -v /lei/datara/evidence:/evidence \
  -v /lei/datara/evidence/ms-playwright:/root/.cache/ms-playwright:ro \
  datara-e2e-browser:hp01 \
  python /evidence/FE-NAV-E2E-01/audit.py
STATUS=$?
unset TOKEN
exit "$STATUS"
