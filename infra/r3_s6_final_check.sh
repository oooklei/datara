#!/usr/bin/env bash
set -euo pipefail

printf 'R3_S6_FINAL_CHECK_AT=%s\n' "$(date -Is)"
docker exec datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -B -e "
SELECT table_name, table_rows, engine
FROM information_schema.tables
WHERE table_schema=0x6461746172615F72656275696C645F6930
  AND (table_name LIKE 0x72656275696C645F676F7665726E616E63655F25
       OR table_name=0x72656275696C645F736368656D615F6D6967726174696F6E)
ORDER BY table_name;
SELECT table_name, constraint_type, COUNT(*)
FROM information_schema.table_constraints
WHERE table_schema=0x6461746172615F72656275696C645F6930
  AND (table_name LIKE 0x72656275696C645F676F7665726E616E63655F25
       OR table_name=0x72656275696C645F736368656D615F6D6967726174696F6E)
GROUP BY table_name, constraint_type ORDER BY table_name, constraint_type;
SELECT table_name, column_name, is_nullable, column_default, extra
FROM information_schema.columns
WHERE table_schema=0x6461746172615F72656275696C645F6930
  AND (table_name LIKE 0x72656275696C645F676F7665726E616E63655F25
       OR table_name=0x72656275696C645F736368656D615F6D6967726174696F6E)
  AND column_name IN (0x637265617465645F6174,0x757064617465645F6174,0x67656E6572617465645F6174,0x737461727465645F6174,0x66696E69736865645F6174)
ORDER BY table_name, ordinal_position;
"'

for table in $(docker exec datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -B -e "SELECT table_name FROM information_schema.tables WHERE table_schema=0x6461746172615F72656275696C645F6930 AND (table_name LIKE 0x72656275696C645F676F7665726E616E63655F25 OR table_name=0x72656275696C645F736368656D615F6D6967726174696F6E) ORDER BY table_name"'); do
  case "$table" in rebuild_governance_*|rebuild_schema_migration) ;; *) echo "UNEXPECTED_TABLE_NAME $table" >&2; exit 8 ;; esac
  count="$(docker exec datara-mysql-meta sh -lc "export MYSQL_PWD=\"\$MYSQL_ROOT_PASSWORD\"; mysql -uroot -N -e 'SELECT COUNT(*) FROM datara_rebuild_i0.\`$table\`'")"
  printf 'exact_row_count table=%s rows=%s\n' "$table" "$count"
done

docker inspect -f 'api_status={{.State.Status}} api_health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' datara-rebuild-api
docker exec datara-rebuild-api python -c 'import json,urllib.request; data=json.load(urllib.request.urlopen("http://127.0.0.1:8001/openapi.json")); paths=sorted(p for p in data["paths"] if p.startswith("/api/v1/rebuild/governance/")); print("governance_openapi_paths=%d" % len(paths)); assert len(paths) == 11'
docker logs --since=10m datara-rebuild-api 2>&1 | awk '/ERROR|Traceback|Exception/ {n++} END {printf "api_log_error_markers_10m=%d\n", n+0}'
