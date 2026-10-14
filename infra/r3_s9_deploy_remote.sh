#!/usr/bin/env bash
set -euo pipefail

ROOT=/lei/datara
STAGE="$ROOT/rebuild-source/r3-s9-stage"
BACKUP="$ROOT/rebuild-source/backups/r3-s9-20261015"

test -d "$BACKUP/rebuild"
test -f "$BACKUP/docker-compose.rebuild.yml"
test -f "$STAGE/rebuild/api/app.py"
test -f "$STAGE/rebuild/governance/legacy_source_reader.py"
test -f "$STAGE/docker-compose.rebuild.yml"

cp -a "$STAGE/rebuild/." "$ROOT/rebuild-source/rebuild/"
cp "$STAGE/docker-compose.rebuild.yml" "$ROOT/docker-compose.rebuild.yml"

# Derive the encoded URL password from the already-running MySQL container; never print it.
mysql_meta_id="$(docker ps --filter label=com.docker.compose.project=datara --filter label=com.docker.compose.service=mysql-meta --format '{{.ID}}')"
test -n "$mysql_meta_id"
url_password="$(docker exec "$mysql_meta_id" printenv MYSQL_ROOT_PASSWORD | python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.stdin.read().rstrip("\n"), safe=""))')"
test -n "$url_password"
export REBUILD_LEGACY_META_URL="mysql+pymysql://root:${url_password}@mysql-meta:3306/datara_meta"
unset url_password mysql_meta_id

cd "$ROOT"
docker compose -f docker-compose.yml -f docker-compose.rebuild.yml config --quiet
docker compose -f docker-compose.yml -f docker-compose.rebuild.yml up -d --no-deps --force-recreate datara-rebuild-api
unset REBUILD_LEGACY_META_URL

for attempt in $(seq 1 30); do
  if docker exec datara-rebuild-api curl -fsS http://127.0.0.1:8001/api/v1/rebuild/health >/dev/null; then
    break
  fi
  sleep 2
done

docker exec datara-rebuild-api curl -fsS http://127.0.0.1:8001/api/v1/rebuild/health
docker inspect -f '{{.Id}} {{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' datara-rebuild-api
docker exec datara-rebuild-api sh -lc 'env | cut -d= -f1 | grep -qx REBUILD_LEGACY_META_URL'
