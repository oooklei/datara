#!/usr/bin/env bash
set -euo pipefail

schema='datara_rebuild_i0'
api_source='/lei/datara/rebuild-source/rebuild'
printf 'R3_S6_SNAPSHOT_AT=%s\n' "$(date -Is)"

configured_schema="$(docker exec datara-rebuild-api python -c 'import os; from sqlalchemy.engine import make_url; print(make_url(os.environ["REBUILD_DB_URL"]).database)')"
if [[ "$configured_schema" != "$schema" ]]; then
  echo 'R3_S6_SNAPSHOT_REFUSED: API is not configured for the isolated schema' >&2
  exit 4
fi

governance_tables="$(docker exec datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=0x6461746172615F72656275696C645F6930 AND table_name LIKE 0x72656275696C645F676F7665726E616E63655F25"')"
if [[ "$governance_tables" != '0' ]]; then
  echo 'R3_S6_SNAPSHOT_REFUSED: target already contains governance tables; require a fresh impact review' >&2
  exit 5
fi

install -d -m 700 /lei/datara/backups
backup_dir="$(mktemp -d /lei/datara/backups/r3-s6-XXXXXX)"
chmod 700 "$backup_dir"
install -m 600 "$api_source/api/app.py" "$backup_dir/app.py.before"
docker exec datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysqldump -uroot --no-data --skip-comments --databases datara_rebuild_i0' > "$backup_dir/datara_rebuild_i0-before.sql"
chmod 600 "$backup_dir/datara_rebuild_i0-before.sql"
test -s "$backup_dir/app.py.before"
test -s "$backup_dir/datara_rebuild_i0-before.sql"
printf 'backup_dir=%s\n' "$backup_dir"
printf 'schema_dump_lines=%s\n' "$(wc -l < "$backup_dir/datara_rebuild_i0-before.sql" | tr -d ' ')"
sha256sum "$backup_dir/app.py.before" "$backup_dir/datara_rebuild_i0-before.sql"
echo 'R3_S6_SNAPSHOT_OK: schema-only dump and app source backup; no database schema/data mutation'
