# DBX v0.6.60 内部令牌补丁交接卡（2026-10-30）

## 最小任务包

- 权威：`docs/designs/2026-10-29-dbx-unified-target-design.md` §五、§七 P1。
- 目标文件：`deploy/dbx/internal-token-patch/README.md`、`auth.rs`、`internal_auth.rs` 及同目录的版本基线。
- 验收：同版本补丁仅增加内部数据 API 通道；令牌长度、精确匹配和 API 范围单测；DBX 主程序类型检查；按具体文件提交。

## 结果

- 提交 `9fb2c553`。`auth.rs` 相对官方 v0.6.60 `auth.baseline.rs` 只增加内部模块加载与认证分支；保留原版会话撤销代码。旧版 v0.6.29 补丁单独保存作版本溯源。
- 本机 WSL：`rustc --edition 2021 --test crates/dbx-web/src/internal_auth.rs`，3 passed；`CARGO_BUILD_JOBS=1 cargo check -q -p dbx-web --no-default-features`，退出码 0。`git diff --cached --check` 对本票文件通过。
- 未构建或部署 DBX 镜像，未执行 §10.7 E2E。

## 遗留项与下次第一步

- 完整原版 IDE 的 owner 网关仍缺 AI 配置、流式接口及其他初始化域；不得先启用内部通道或切换 `/ide/api/` 路由。
- 下次先按 §五、§七 P1 为 AI 配置与流式接口声明单独 DBX 任务包，核对 v0.6.60 路由和当前网关源码，再实现与验证。共享索引可能有其他任务的暂存项，继续用 `git commit --only -- <本票文件>`。
