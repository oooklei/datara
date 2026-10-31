# DBX 运行时发布交接卡（2026-10-31）

## 已落地

- 1.9 `/lei/apps/dbx/crates/dbx-web/src/auth.rs` 将内部路由判定接入 `internal_auth::internal_api_allowed`，覆盖 `migration/status` 等 Datara 网关只读接口。
- 1.9 镜像 `dbx:datara-gateway-closeout` 已构建并由 `deploy-1.9/docker-compose.yml` 强制重建发布；数据卷未变更。

## 验证

- `GET http://192.168.1.9:4224/ide/api/migration/status` 无令牌：HTTP 401。
- 1.9 `datara-rebuild-api` 容器携带 `X-Datara-Internal-Token`：HTTP 200，`state=not_required`、`keyStatus=ready`。
- Datara IDE 会话 cookie 经 `http://192.168.1.9:8090/ide/api/migration/status`：HTTP 200，返回迁移状态 JSON。
- DBX 容器日志正常启动，监听 `0.0.0.0:4224`，基路径 `/ide`。

## 遗留与下一步

- 远端 DBX 源码/镜像变更尚未同步本机 main；等待用户通知后再同步。
- 前端浏览器验证脚本仍受“编排环境接口 401”影响，需在下一票测试域补齐隔离验证；不影响本票迁移接口 200 验收。
- 下一票前端：两个嵌入系统顶部增加“刷新”按钮/菜单，触发 iframe 重载并保留当前项目上下文。
