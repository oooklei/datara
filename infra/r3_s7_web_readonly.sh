#!/usr/bin/env bash
set -euo pipefail

printf 'R3_S7_WEB_INVENTORY_AT=%s\n' "$(date -Is)"
docker inspect -f 'web_status={{.State.Status}} web_image={{.Config.Image}} {{range .Mounts}}mount={{.Source}}:{{.Destination}} {{end}}' datara-web
docker exec datara-web sh -lc 'nginx -T 2>&1 | grep -E "^[[:space:]]*(root|alias|location|proxy_pass)[[:space:]]" | head -80'
curl -sS -o /dev/null -w 'r3_validation_page_http=%{http_code}\n' http://127.0.0.1:18091/rebuild-validation-r3.html
curl -sS -o /dev/null -w 'web_health_http=%{http_code}\n' http://127.0.0.1:18091/
