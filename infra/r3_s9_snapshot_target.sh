#!/usr/bin/env bash
set -euo pipefail

BACKUP_DIR=/lei/datara/backups/r3-s9-20261015
BACKUP_FILE="$BACKUP_DIR/datara_rebuild_i0-before-v2.sql"

mkdir -p "$BACKUP_DIR"
test ! -e "$BACKUP_FILE"

mysql_meta_id="$(docker ps --filter label=com.docker.compose.project=datara --filter label=com.docker.compose.service=mysql-meta --format '{{.ID}}')"
test -n "$mysql_meta_id"

# Root is used only for this read-only consistent dump of the isolated target schema.
docker exec "$mysql_meta_id" sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump --user=root --single-transaction --skip-lock-tables --no-tablespaces --set-gtid-purged=OFF datara_rebuild_i0' > "$BACKUP_FILE"
test -s "$BACKUP_FILE"
gzip -n "$BACKUP_FILE"
gzip -t "$BACKUP_FILE.gz"

sha256sum "$BACKUP_FILE.gz"
stat -c 'backup_bytes=%s' "$BACKUP_FILE.gz"
date -Is
