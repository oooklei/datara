# DBX v0.6.60 内部取参补丁（2026-10-30）

- 涉及节号：权威 §10.9，用户裁定 DBX `connectionId` 直接作为海豚节点数据源字符串 ID。
- 改动文件：`deploy/dbx/internal-token-patch/auth.rs`、`internal_auth.rs`、`internal_connection.rs`、`main.patch.v0.6.60`、`README.md`。内部端点 `GET /internal/connection/{id}/params` 仅在 gateway-only、固定令牌、明确来源 CIDR 均通过后返回 DBX 保存的连接配置；状态调用均写不含密码的结构化审计记录。
- 验证：`rustc --edition 2021 --crate-type lib --emit metadata` 编译 `internal_auth.rs` 通过；`git apply --reverse --check main.patch.v0.6.60` 对修改后的 v0.6.60 `main.rs` 通过。`cargo check` 因稀疏检出缺 `src-tauri/Cargo.toml` 尚未执行，不能宣称 DBX 端点已编译或运行。
- 遗留：在完整 v0.6.60 源码执行 `cargo check` 和取参安全测试；接 Datara 网关并在 1.9 构建部署。1.9 `/lei/apps/dbx` 为 v0.6.29，不能据此覆盖运行镜像。
