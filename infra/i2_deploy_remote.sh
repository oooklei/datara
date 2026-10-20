#!/usr/bin/env bash
set -euo pipefail

echo "I2_REMOTE_DEPLOY_AT=$(date -Is)"
docker compose -f /lei/datara/docker-compose.yml up -d --build datara-rebuild-api
docker inspect -f '{{.Name}} {{.State.Status}}' datara-rebuild-api
curl -fsS http://127.0.0.1:18091/api/v1/rebuild/health
echo
echo "I2_REMOTE_DEPLOY_DONE"
