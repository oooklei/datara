# dbx 内部令牌补丁（待集成）

`auth.baseline.rs` 是 DBX v0.6.60 官方标签的原文件；`auth.rs` 加载 `internal_auth.rs`，在认证中增加仅限数据 API 的内部令牌通道，并保留该版本原有的会话撤销逻辑。移植时两个 `.rs` 文件必须一起复制到 `crates/dbx-web/src/`。1.9 主机 `/lei/apps/dbx` 的源码清单实际为 v0.6.29，旧版基线和未部署补丁分别保存在 `auth.baseline.0.6.29.rs`、`auth.patch.0.6.29.rs`，不得覆盖 v0.6.60 运行镜像。令牌必须由服务端环境变量 `DBX_INTERNAL_TOKEN` 提供，长度至少 32 字节。浏览器静态产物不得包含该值。

本机 WSL 用独立目录核验：`rustc --edition 2021 --test crates/dbx-web/src/internal_auth.rs` 的单测通过；`CARGO_BUILD_JOBS=1 cargo check -q -p dbx-web --no-default-features` 通过。尚未构建镜像或启用运行时；datara owner 网关尚未完整接线，在它生效前启用内部通道会留下绕过 owner 校验的风险。
