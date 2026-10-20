#!/usr/bin/env bash
set -euo pipefail

echo "I2_REMOTE_VERIFY_AT=$(date -Is)"
docker exec datara-api python -m tools.datagen.run plan
docker exec datara-api python -m tools.datagen.run verify
docker exec datara-api python -m tools.datagen.run samples --rows 5000
echo "I2_REMOTE_VERIFY_DONE"
