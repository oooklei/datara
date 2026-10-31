# 1.9 运行容器简名

2026-11-01 用户要求：Datara、DBX、DolphinScheduler 运行容器名称不超过 12 个字符。Compose **服务键**保留原名以维持网络 DNS 与依赖关系；`container_name` 使用以下简名。手动启动的 `dt-rebuild` 必须带 `datara-rebuild-api` 网络别名，以兼容当前 Nginx 代理。

| 系统 | 容器简名 |
| --- | --- |
| Datara 前端/重建 API | `dt-web`、`dt-rebuild` |
| Datara 其他服务 | `dt-api`、`dt-master`、`dt-worker`、`dt-alert`、`dt-logger`、`dt-oldweb` |
| Datara 中间件 | `dt-zk`、`dt-kafka`、`dt-redis`、`dt-db-meta`、`dt-db-src`、`dt-db-dw` |
| DBX | `dbx` |
| DolphinScheduler | `ds-api`、`ds-master`、`ds-worker`、`ds-alert`、`ds-zk`、`ds-pg`；临时初始化服务为 `ds-init` |

配置位置：Datara 的仓库根目录 `docker-compose.yml` 与 1.9 `/lei/datara/docker-compose.yml`；DBX `/lei/apps/dbx/deploy-1.9/docker-compose.yml`；海豚 `/lei/apps/ds-3.4.3-deploy-20261029/docker-compose.yml`。Kafka 保留 `datara-kafka` 网络别名，避免旧客户端按原广播地址连接失败。

本次改名直接更新容器名称，没有重建镜像，故 `Created`/`StartedAt` 不因改名而刷新。发布核查须同时比较实时容器的镜像 ID、创建时间、Compose 服务配置和 HTTP 响应。1.9 隔离证据：`/lei/datara/deployments/codex-main-20261101-0635/name-audit/`。
