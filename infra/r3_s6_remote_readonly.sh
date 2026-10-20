#!/usr/bin/env bash
set -euo pipefail

printf 'R3_S6_READONLY_AT=%s\n' "$(date -Is)"
docker inspect -f 'api_status={{.State.Status}} api_image={{.Config.Image}} {{range .Mounts}}mount={{.Source}}:{{.Destination}} {{end}}' datara-rebuild-api
docker inspect -f 'mysql_status={{.State.Status}} mysql_image={{.Config.Image}}' datara-mysql-meta

# Print only parsed connection identity; never print the URL or credentials.
docker exec datara-rebuild-api python -c 'import os; from sqlalchemy.engine import make_url; u=make_url(os.environ["REBUILD_DB_URL"]); print("api_db_backend=%s api_db_host=%s api_db_name=%s api_db_user=%s" % (u.get_backend_name(), u.host, u.database, u.username))'

docker exec datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -B -e "
SELECT table_name, table_type
FROM information_schema.tables
WHERE table_schema=0x6461746172615F72656275696C645F6930
  AND (table_name LIKE 0x72656275696C645F676F7665726E616E63655F25
       OR table_name=0x72656275696C645F736368656D615F6D6967726174696F6E)
ORDER BY table_name;
SELECT table_name, column_name, column_type, is_nullable, column_default, extra
FROM information_schema.columns
WHERE table_schema=0x6461746172615F72656275696C645F6930
  AND (table_name LIKE 0x72656275696C645F676F7665726E616E63655F25
       OR table_name=0x72656275696C645F736368656D615F6D6967726174696F6E)
ORDER BY table_name, ordinal_position;
SELECT COUNT(*) AS rebuild_governance_table_count
FROM information_schema.tables
WHERE table_schema=0x6461746172615F72656275696C645F6930
  AND table_name LIKE 0x72656275696C645F676F7665726E616E63655F25;
"'

docker exec datara-rebuild-api python -c 'import importlib.util; present=False
try:
 present=importlib.util.find_spec("rebuild.governance.migration_preflight") is not None
except ModuleNotFoundError:
 pass
print("remote_preflight_module=%s" % ("present" if present else "absent"))'
docker exec datara-rebuild-api sh -lc 'for f in /app/rebuild/api/app.py /app/rebuild/governance/api.py /app/rebuild/governance/migrations.py /app/rebuild/governance/migration_preflight.py /app/rebuild/identity/models.py /app/rebuild/project/models.py /app/rebuild/common/db.py; do if test -f "$f"; then sha256sum "$f"; else printf "REMOTE_FILE_ABSENT %s\n" "$f"; fi; done'
docker inspect -f 'api_health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' datara-rebuild-api
docker logs --since=10m datara-rebuild-api 2>&1 | awk '/ERROR|Traceback|Exception/ {n++} END {printf "api_log_error_markers_10m=%d\n", n+0}'
