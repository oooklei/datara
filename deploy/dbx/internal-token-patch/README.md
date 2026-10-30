# dbx 内部令牌补丁（待集成）

`auth.baseline.rs` 是 DBX v0.6.60 官方标签的原文件；`auth.rs` 加载 `internal_auth.rs`，在认证中增加仅限数据 API 的内部令牌通道，并保留该版本原有的会话撤销逻辑。移植时两个 `.rs` 文件必须一起复制到 `crates/dbx-web/src/`。1.9 主机 `/lei/apps/dbx` 的源码清单实际为 v0.6.29，旧版基线和未部署补丁分别保存在 `auth.baseline.0.6.29.rs`、`auth.patch.0.6.29.rs`，不得覆盖 v0.6.60 运行镜像。令牌必须由服务端环境变量 `DBX_INTERNAL_TOKEN` 提供，长度至少 32 字节。浏览器静态产物不得包含该值。

Datara 嵌入部署必须同时设置 `DBX_DATARA_GATEWAY_ONLY=1` 与同一内部令牌。该模式下静态资源可读取，DBX 数据 API 只接受内部令牌；普通 DBX 会话、关闭密码校验和登录/检查端点都不能绕过 Datara owner 网关。Datara 网关自行响应 iframe 的 `auth/check`。未设置该开关时保留 DBX 独立部署原行为。

本机 WSL 用独立目录核验：`rustc --edition 2021 --test crates/dbx-web/src/internal_auth.rs` 的单测通过；`CARGO_BUILD_JOBS=1 cargo check -q -p dbx-web --no-default-features` 通过。尚未构建镜像或启用运行时；启用该模式前必须确认 Datara owner 网关与内部令牌已配置，否则 IDE 数据 API 将返回 401。
