# DBX 直连鉴权交接

- 任务包：权威设计 §四 owner 隔离、§七 P1；目标文件 `deploy/dbx/internal-token-patch/{auth.rs,internal_auth.rs,README.md}`。
- 已落地：`40f783b` 新增 `DBX_DATARA_GATEWAY_ONLY=1` 模式。该模式下 DBX 数据 API 无内部令牌即返回 401，即使 DBX 密码关闭或有原生会话；原版静态资源仍可提供。内部令牌路由扩至 Datara 网关当前所需的隧道、提示词、启动读接口。
- 验证：本机 WSL `rustc --edition 2021 --test .../internal_auth.rs` 5/5 通过；隔离 DBX v0.6.60 源码 `CARGO_BUILD_JOBS=1 cargo check -q -p dbx-web --no-default-features` 最终补丁通过；`rtk git diff --check` 通过。
- 运行中：本机 WSL 独立源码 `/root/datara-dbx-auth-build-v06060` 正以单作业、低优先级构建可运行二进制；`exec` 会话 ID `60866`。不可仅因轮询超时重启。未修改 1.9 容器。
- 未完：构建结束后在 WSL 隔离环境以不同内部令牌验证直连 401/正确令牌正常访问/静态资源 200；再制定不冲撞 1.9 并行服务的部署切换。当前 1.9:4224 直连仍可无授权读连接，owner 隔离未完成。
