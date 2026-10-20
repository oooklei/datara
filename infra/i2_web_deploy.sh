#!/usr/bin/env bash
set -euo pipefail

echo "I2_WEB_DEPLOY_AT=$(date -Is)"
docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}' datara-web
rm -rf /lei/datara/datara-web/dist/*
tar -xzf /tmp/datara-i2-web.tgz -C /lei/datara/datara-web/dist
docker restart datara-web
curl -fsS http://127.0.0.1:18091/rebuild-validation-i2.html >/dev/null
echo "I2_WEB_HTTP=200"
