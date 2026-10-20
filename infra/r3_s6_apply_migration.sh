#!/usr/bin/env bash
set -euo pipefail

printf 'R3_S6_APPLY_AT=%s\n' "$(date -Is)"
test -s /lei/datara/backups/r3-s6-IuZlyI/app.py.before
test -s /lei/datara/backups/r3-s6-IuZlyI/datara_rebuild_i0-before.sql
docker exec datara-rebuild-api python -m rebuild.governance.migration_apply --apply
docker inspect -f 'api_status={{.State.Status}} api_health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' datara-rebuild-api
docker logs --since=5m datara-rebuild-api 2>&1 | awk '/ERROR|Traceback|Exception/ {n++} END {printf "api_log_error_markers_5m=%d\n", n+0}'
