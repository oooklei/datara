#!/usr/bin/env bash
# I6 master 白名单自检（1.9 远端执行）
docker exec datara-master python -c "from master.engine import WORKER_TYPES; from master.failover import WORKER_TYPES as F; print('ENGINE:', WORKER_TYPES); print('FAILOVER:', F)"
docker exec datara-master python -c "
from master.engine import WORKER_TYPES as E
assert 'sync' in E, 'sync missing in engine'
print('MASTER_WHITELIST_OK')
"
