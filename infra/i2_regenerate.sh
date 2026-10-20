#!/usr/bin/env bash
set -euo pipefail

echo "I2_REGENERATE_AT=$(date -Is)"
docker compose -f /lei/datara/docker-compose.yml up -d --build datara-api
docker exec datara-api python -m tools.datagen.run gen
docker exec datara-api python -m tools.datagen.run verify
echo "I2_REGENERATE_DONE"
