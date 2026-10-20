#!/usr/bin/env bash
set -euo pipefail

echo "I2_REMOTE_PREFLIGHT_AT=$(date -Is)"
command -v docker
docker ps --format '{{.Names}} {{.Status}}'
docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}' datara-api
docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}' datara-rebuild-api
docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}' datara-mysql-src
docker inspect -f '{{.Name}} {{range .Mounts}}{{.Source}}:{{.Destination}} {{end}}' datara-mysql-dw

for script in /lei/datara/infra/bin/install.sh /lei/datara/infra/bin/reset.sh /lei/datara/infra/bin/import.sh /lei/datara/infra/bin/uninstall.sh; do
  bash -n "$script"
done
echo "I2_REMOTE_SHELL_SYNTAX_OK"

docker exec datara-api sh -lc 'python -c "import pathlib, yaml; yaml.safe_load(pathlib.Path(\"/app/tools/datagen/tables.yaml\").read_text(encoding=\"utf-8\")); yaml.safe_load(pathlib.Path(\"/app/tools/datagen/dirty_rules.yaml\").read_text(encoding=\"utf-8\")); print(\"I2_REMOTE_YAML_OK\")"'
