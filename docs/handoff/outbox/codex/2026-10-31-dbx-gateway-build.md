# DBX B4 鉴权封口交接

## 已落地（1.9 隔离环境）

- `/lei/apps/dbx/crates/dbx-web/src/auth.rs` 已替换为仓库中的 `deploy/dbx/internal-token-patch/auth.patch.0.6.29.rs`。
- 已复制 `internal_auth.rs`、`internal_connection.rs`，并在 `main.rs` 注册内部连接参数路由及 `ConnectInfo`。
- `/lei/apps/dbx/deploy-1.9/docker-compose.yml` 已启用 `DBX_DATARA_GATEWAY_ONLY=1`、内部令牌和私网允许段。
- `/lei/apps/dbx/deploy-1.9/.env` 已从 `datara-rebuild-api` 现有 `DBX_INTERNAL_TOKEN` 同步令牌；未回显、未写入仓库。

## 验证前状态

- 切换前复现：`GET http://192.168.1.9:4224/ide/api/connection/list` 无授权返回 200 且有连接列表。
- DBX 补丁镜像构建句柄：本机会话 `19596`，已通过前端 Vite 阶段，当前仍在下载 Rust 基础镜像层，尚未进入 Rust 编译终态。

## 下次第一步

1. 继续轮询会话 `19596`，直到明确成功或编译错误。
2. 成功后执行 `docker compose up -d --force-recreate dbx`，确认容器使用 `dbx:datara-gateway-20261031`（必要时更新 compose image）。
3. 回测匿名 `/ide/api/connection/list` 为 401；再通过 Datara 网关带内部令牌验证连接列表和 `/internal/connection/{id}/params`。

## 涉及节号

计划 §二 #1、§三 B4-B6；权威设计 §四 DBX 鉴权边界。
