# 1.9 运行容器简名

2026-11-01 用户要求：Datara、DBX、DolphinScheduler 运行容器名称不超过 12 个字符。Compose **服务键**保留原名以维持网络 DNS 与依赖关系，`container_name` 使用简名。改 `container_name` 不得改变服务键或网络别名。

## 1. 现时核验（以本仓库 Compose 为准）

| 系统 | 服务键（DNS/别名） | `container_name` | 字符数 | 状态 |
| --- | --- | --- | --- | --- |
| Datara 前端 | `newweb` | `dt-web` | 6 | ✅（`deploy/wsl-frontend/compose.yaml`） |
| Datara 重建 API | `datara-rebuild-api` | `dt-rebuild` | 9 | ✅（根 `docker-compose.yml`） |
| Datara 重建 API（单服务 Compose） | `datara-rebuild-api` | `dt-rebuild` | 10 | ✅（`docker-compose.rebuild.yml`） |
| Datara 旧 API | `api` | `dt-api` | 6 | ✅ |
| Datara master/worker/alert/logger | `datara-master`/`datara-worker`/`datara-alert`/`datara-logger` | `dt-master`/`dt-worker`/`dt-alert`/`dt-logger` | 9 | ✅ |
| Datara 旧前端 | `oldweb` | `dt-oldweb` | 9 | ✅ |
| Datara 中间件 | `zookeeper`/`kafka`/`redis`/`mysql-meta`/`mysql-src`/`mysql-dw` | `dt-zk`/`dt-kafka`/`dt-redis`/`dt-db-meta`/`dt-db-src`/`dt-db-dw` | ≤10 | ✅ |
| DBX | — | `dbx` | 3 | ✅ |
| DolphinScheduler | — | `ds-api`/`ds-master`/`ds-worker`/`ds-alert`/`ds-zk`/`ds-pg`；临时初始化 `ds-init` | ≤8 | ✅ |

## 2. 发布核验

1. 在 1.9 隔离目录重建并验证：nginx `/api/` 可达、`/ide/` 与 `/dolphinscheduler/` 反代正常、Datara/DBX/海豚容器名全部 ≤12。
2. nginx 上游 `datara-rebuild-api:8001` 仍按 Compose 服务键或网络别名解析。

Kafka 保留 `datara-kafka` 网络别名，避免旧客户端按原广播地址连接失败。

## 3. 核查方法

改名不重建镜像，故 `Created`/`StartedAt` 不因改名刷新。发布核查须同时比较：实时容器名、镜像 ID、Compose 服务配置、HTTP 响应。
