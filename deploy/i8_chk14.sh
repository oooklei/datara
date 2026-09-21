#!/bin/bash
echo "=== 容器内 poll/_brokers_alive 函数全文 ==="
docker exec datara-worker sed -n '154,215p' /app/worker/stream/sources.py
echo "=== 宿主侧对照 ==="
sed -n '154,215p' /mnt/lei/datara/datara-backend/worker/stream/sources.py
echo "=== md5 对照 ==="
docker exec datara-worker md5sum /app/worker/stream/sources.py
md5sum /mnt/lei/datara/datara-backend/worker/stream/sources.py
echo "=== __pycache__ 检查 ==="
docker exec datara-worker ls -la /app/worker/stream/__pycache__/ 2>/dev/null | head -8
docker exec datara-worker python -c "import sys; sys.path.insert(0,'/app'); import worker.stream.sources as m; print('module file:', m.__file__); import inspect; src=inspect.getsource(m.KafkaSource.poll); print(src)"
