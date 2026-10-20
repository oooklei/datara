#!/usr/bin/env bash
set -euo pipefail

src='/lei/datara/rebuild-source/rebuild/api/app.py'
candidate='/lei/datara/rebuild-source/.r3-s6-stage-IuZlyI/app.py.new'
backup='/lei/datara/backups/r3-s6-IuZlyI/app.py.before'
expected_old='c4fd19775e514c65e8efb8667d3c9f02424f9e0e629623932a6d3a1131b72a7b'
expected_new='f36a2c3025852ce092c6289695a61259aa2f07aba5d0818f11a5a1f57ebe036e'

test "$(sha256sum "$src" | cut -d' ' -f1)" = "$expected_old"
test "$(sha256sum "$backup" | cut -d' ' -f1)" = "$expected_old"
test "$(sha256sum "$candidate" | cut -d' ' -f1)" = "$expected_new"
test -s /lei/datara/rebuild-source/rebuild/governance/api.py
docker exec datara-rebuild-api python -m rebuild.governance.migration_apply --dry-run

chmod --reference="$src" "$candidate"
chown --reference="$src" "$candidate"
mv "$candidate" "$src"
test "$(sha256sum "$src" | cut -d' ' -f1)" = "$expected_new"
printf 'R3_S6_API_SWITCH_AT=%s\n' "$(date -Is)"
docker restart datara-rebuild-api

for attempt in $(seq 1 30); do
  health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' datara-rebuild-api)"
  if [[ "$health" == 'healthy' ]]; then break; fi
  sleep 2
done
test "$health" = 'healthy'
docker exec datara-rebuild-api python -c 'import json,urllib.request; data=json.load(urllib.request.urlopen("http://127.0.0.1:8001/openapi.json")); paths=sorted(p for p in data["paths"] if p.startswith("/api/v1/rebuild/governance/")); print("governance_openapi_paths=%d" % len(paths)); assert len(paths) >= 10'
docker exec datara-rebuild-api python -c 'import json,urllib.request; print("api_health="+json.load(urllib.request.urlopen("http://127.0.0.1:8001/api/v1/rebuild/health"))["data"]["status"])'
docker logs --since=5m datara-rebuild-api 2>&1 | awk '/ERROR|Traceback|Exception/ {n++} END {printf "api_log_error_markers_5m=%d\n", n+0}'
