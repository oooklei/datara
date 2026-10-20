#!/usr/bin/env bash
set -euo pipefail
cd /lei/datara

printf 'RUNTIME_ENV_CHECK_AT=%s\n' "$(date -Is)"
for name in MYSQL_ROOT_PASSWORD DATARA_ADMIN_PWD DATARA_DEV_PWD DATARA_ANALYST_PWD DATARA_VIEWER_PWD REBUILD_DB_URL REBUILD_TOKEN_SECRET REBUILD_VALIDATION_KEY REBUILD_MYSQL_SRC_URL; do
  if grep -q "^${name}=" .env 2>/dev/null; then
    printf '%s=present_in_dotenv\n' "$name"
  else
    printf '%s=not_in_dotenv\n' "$name"
  fi
done
for container in datara-rebuild-api datara-mysql-meta; do
  docker inspect -f '{{.Name}} {{.State.Status}}' "$container"
done
