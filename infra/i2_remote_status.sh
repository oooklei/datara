#!/usr/bin/env bash
set -euo pipefail
echo "I2_REMOTE_STATUS_AT=$(date -Is)"
docker exec datara-api sh -lc 'find /datara/files -maxdepth 4 -type f -name "reconcile.json" -print'
docker exec datara-api sh -lc 'find /datara/files -maxdepth 4 -type f -name "orders_part.csv" -o -name "orders_part.txt" -o -name "orders_part.xlsx" -print'
docker exec datara-api sh -lc 'find /app /datara -type f -name "reconcile.json" -print 2>/dev/null || true'
