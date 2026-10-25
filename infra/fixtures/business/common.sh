#!/usr/bin/env bash
set -euo pipefail

FIXTURE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$FIXTURE_DIR/../../.." && pwd)"
SRC_SERVICE="${DATARA_FIXTURE_SRC_SERVICE:-datara-mysql-src}"
DW_SERVICE="${DATARA_FIXTURE_DW_SERVICE:-datara-mysql-dw}"
COMPOSE_FILE="${COMPOSE_FILE:-$REPO_ROOT/docker-compose.yml}"
COMPOSE=(docker compose -f "$COMPOSE_FILE")

die() { printf '[INFRA-DATA-01] ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '[INFRA-DATA-01] %s\n' "$*"; }

assert_validation_host() {
  local addresses
  addresses="$(hostname -I 2>/dev/null || true)"
  case " $addresses " in
    *" 192.168.1.9 "*) ;;
    *) die "container execution is restricted to validation host 192.168.1.9 (found: ${addresses:-unknown})" ;;
  esac
}

assert_runtime() {
  command -v docker >/dev/null 2>&1 || die "docker is required"
  docker compose version >/dev/null 2>&1 || die "docker compose v2 is required"
  [ -f "$COMPOSE_FILE" ] || die "compose file not found: $COMPOSE_FILE"
  local service
  for service in "$SRC_SERVICE" "$DW_SERVICE"; do
    [ -n "$("${COMPOSE[@]}" ps --status running -q "$service")" ] || die "compose service is not running: $service"
  done
}

mysql_stdin() {
  local service="$1" database="$2"
  "${COMPOSE[@]}" exec -T "$service" sh -lc \
    'test -n "${MYSQL_ROOT_PASSWORD:-}" && exec env MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --user=root --default-character-set=utf8mb4 --batch --raw "$1"' \
    sh "$database"
}

mysql_scalar() {
  local service="$1" database="$2" query="$3"
  printf '%s\n' "$query" | mysql_stdin "$service" "$database" | tr -d '\r' | tail -n 1
}
