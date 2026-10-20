#!/usr/bin/env bash
set -euo pipefail

printf 'R3_S6_MIGRATION_VERIFY_AT=%s\n' "$(date -Is)"
docker exec datara-rebuild-api python -m rebuild.governance.migration_apply --dry-run
docker exec datara-rebuild-api python -m rebuild.governance.migration_apply --apply
docker exec datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -B -e "
SELECT table_name, table_rows
FROM information_schema.tables
WHERE table_schema=0x6461746172615F72656275696C645F6930
  AND (table_name LIKE 0x72656275696C645F676F7665726E616E63655F25
       OR table_name=0x72656275696C645F736368656D615F6D6967726174696F6E)
ORDER BY table_name;
SELECT revision, status, checksum, attempt_count, created_at, updated_at, generated_at, started_at, finished_at
FROM datara_rebuild_i0.rebuild_schema_migration;
"'
docker inspect -f 'api_status={{.State.Status}} api_health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' datara-rebuild-api
docker logs --since=10m datara-rebuild-api 2>&1 | awk '/ERROR|Traceback|Exception/ {n++} END {printf "api_log_error_markers_10m=%d\n", n+0}'
