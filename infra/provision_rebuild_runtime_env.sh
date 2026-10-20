#!/usr/bin/env bash
set -euo pipefail
cd /lei/datara

test -f .env || { echo 'RUNTIME_ENV_PROVISION_FAILED: .env missing'; exit 2; }
for name in MYSQL_ROOT_PASSWORD DATARA_ADMIN_PWD DATARA_DEV_PWD DATARA_ANALYST_PWD DATARA_VIEWER_PWD; do
  grep -q "^${name}=" .env || { printf 'RUNTIME_ENV_PROVISION_FAILED: required variable %s missing\n' "$name"; exit 2; }
done
for name in REBUILD_DB_URL REBUILD_TOKEN_SECRET REBUILD_VALIDATION_KEY REBUILD_MYSQL_SRC_URL; do
  if grep -q "^${name}=" .env; then
    printf 'RUNTIME_ENV_PROVISION_FAILED: refusing to overwrite existing %s\n' "$name"
    exit 3
  fi
done

db_password="$(openssl rand -hex 32)"
source_password="$(openssl rand -hex 32)"
token_secret="$(openssl rand -hex 48)"
validation_key="$(openssl rand -hex 32)"

docker exec -i datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot' <<SQL
ALTER USER 'datara_rebuild_i0'@'%' IDENTIFIED BY '${db_password}';
GRANT ALL PRIVILEGES ON datara_rebuild_i0.* TO 'datara_rebuild_i0'@'%';
SQL

docker exec -i datara-mysql-src sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot' <<SQL
CREATE USER IF NOT EXISTS 'datara_rebuild_reader'@'%' IDENTIFIED BY '${source_password}';
ALTER USER 'datara_rebuild_reader'@'%' IDENTIFIED BY '${source_password}';
GRANT SELECT, SHOW VIEW ON ec_retail.* TO 'datara_rebuild_reader'@'%';
SQL

umask 077
env_tmp="$(mktemp /lei/datara/.env.rebuild.XXXXXX)"
cat .env > "$env_tmp"
{
  printf '\nREBUILD_DB_URL=mysql+pymysql://datara_rebuild_i0:%s@mysql-meta:3306/datara_rebuild_i0\n' "$db_password"
  printf 'REBUILD_TOKEN_SECRET=%s\n' "$token_secret"
  printf 'REBUILD_VALIDATION_KEY=%s\n' "$validation_key"
  printf 'REBUILD_MYSQL_SRC_URL=mysql+pymysql://datara_rebuild_reader:%s@datara-mysql-src:3306/ec_retail\n' "$source_password"
} >> "$env_tmp"
chmod 600 "$env_tmp"
mv "$env_tmp" .env
chmod 600 .env

unset db_password source_password token_secret validation_key
echo 'RUNTIME_ENV_PROVISION_OK: rebuild secrets stored in /lei/datara/.env; rebuild DB isolated; source profile read-only'
