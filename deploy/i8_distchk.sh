#!/bin/bash
echo "=== dist 构建版本鉴别 ==="
docker exec datara-web sh -c 'ls -la /usr/share/nginx/html/index.html; ls /usr/share/nginx/html/assets/ | wc -l'
echo "=== I8 特征（流任务/实时数据 chunk） ==="
docker exec datara-web sh -c 'grep -l "stream-jobs" /usr/share/nginx/html/assets/*.js 2>/dev/null | head -3'
docker exec datara-web sh -c 'grep -l "stream_input" /usr/share/nginx/html/assets/*.js 2>/dev/null | head -3'
