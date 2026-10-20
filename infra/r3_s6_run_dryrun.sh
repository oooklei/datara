#!/usr/bin/env bash
set -euo pipefail

live='/lei/datara/rebuild-source/rebuild/governance'
staged='/lei/datara/rebuild-source/.r3-s6-stage-IuZlyI/governance'
if [[ ! -e "$live" ]]; then
  test -d "$staged"
  mv "$staged" "$live"
fi

docker exec datara-rebuild-api python -c 'from pathlib import Path; root=Path("/app/rebuild/governance"); files=sorted(root.rglob("*.py")); [compile(p.read_text(encoding="utf-8"),str(p),"exec") for p in files]; print("REMOTE_GOVERNANCE_COMPILE_OK files=%d" % len(files))'
docker exec datara-rebuild-api python -m rebuild.governance.migration_apply --dry-run
docker exec datara-mysql-meta sh -lc 'export MYSQL_PWD="$MYSQL_ROOT_PASSWORD"; mysql -uroot -N -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=0x6461746172615F72656275696C645F6930 AND table_name LIKE 0x72656275696C645F676F7665726E616E63655F25"'
