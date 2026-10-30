# dbx 内部令牌补丁（待集成）

`auth.baseline.rs` 是 DBX v0.6.60 官方标签的原文件。移植时先应用 `main.patch.v0.6.60`，再将 `auth.rs`、`internal_auth.rs`、`internal_connection.rs` 复制到 `crates/dbx-web/src/`。内部取参端点为 `GET /internal/connection/{id}/params`，普通 `/api/connection/list` 仍脱敏。1.9 主机 `/lei/apps/dbx` 的源码清单实际为 v0.6.29，不得直接覆盖 v0.6.60 运行镜像。令牌必须由服务端环境变量 `DBX_INTERNAL_TOKEN` 提供，长度至少 32 字节，禁入浏览器静态产物。

Datara 嵌入部署必须同时设置 `DBX_DATARA_GATEWAY_ONLY=1`、同一内部令牌与 `DBX_INTERNAL_ALLOWED_CIDRS`（逗号分隔的网关来源 IP 或 CIDR；未配置即拒绝取参）。该模式下静态资源可读取，DBX 数据 API 只接受内部令牌；普通 DBX 会话、关闭密码校验和登录/检查端点都不能绕过 Datara owner 网关。Datara 网关自行响应 iframe 的 `auth/check`。未设置该开关时内部令牌通道也关闭，保留 DBX 独立部署原行为。

旧认证补丁曾在本机 WSL 独立目录通过 `rustc --test` 与 `cargo check`。新增内部取参端点尚需针对精确 v0.6.60 完整源码执行 `cargo check`、定向单测和 1.9 镜像构建；不得把旧通过结果当作新增端点的验收。
