# 嵌入网关白屏与超时收口

## 根因

- DBX `connection/liveness-events` 原先同步等待上游 SSE，阻塞重建 API 事件循环，导致项目接口、会话接口和海豚嵌入请求出现 499/502。
- 重启后后端容器 IP 变化，8090 nginx 仍缓存旧 upstream IP，继续产生连接拒绝 502。

## 修复与部署

- `datara-backend/rebuild/dbx/ide_proxy.py`：liveness 改为非阻塞本地 SSE 心跳，避免长连接拖垮网关。
- 1.9 已更新并重启 `datara-rebuild-api`；随后重启 `datara-newweb-web` 使 nginx 重新解析后端地址。

## 回验

- 8090 `/api/v1/rebuild/projects` 未登录返回 `401`，不再超时/502。
- 现场日志确认 DBX 启动请求 `database-backups` 返回 `200`。
- 本机 DBX IDE 契约测试：`21 passed`。

## 待用户复测

- 刷新数据开发 IDE，确认不白屏。
- 打开任务编排，确认嵌入画布正常加载；若会话失效，应显示重试而非空白。
