# DB-token-02：digest 键硬化策略核准报告

## 1. 任务与结论

- 派单：`s349-gov-c-exec-confirm-dw-audit-20261021`，DB-token-02。
- 前置预研：`DB-token-01` 已确认本地 `token VARCHAR(255)` 无法容纳 260～262 byte 的 validation/capability token；`user_id=0` 与非空用户外键冲突；1.9 已带外改成 `VARCHAR(512)`，但迁移台账没有对应 revision。
- 新边界：合法 Unicode 用户名可令 token 达到约 651～736 bytes，固定 `VARCHAR(512)` 仍不完整。
- **推荐监督线核准方案 B：SHA-256 digest 键硬化。** `token_digest CHAR(64)` 作为主键，数据库不再保存 raw bearer token；`user_id` 改 nullable FK。外部 token 词形和 claims 保持不变。

## 2. 二选一评审

### A. 冻结 raw token 长度上界

不推荐。当前合法输入已突破 512 bytes；若扩到 `VARCHAR(768)`，按 MySQL `utf8mb4` 最坏 4 bytes/字符计算，主键理论占用 3072 bytes，已触及常见 InnoDB 索引键上限。后续 claims 或编码变化仍会造成结构漂移。

### B. digest 键硬化

推荐。对 raw token 计算 `sha256(token.encode("utf-8")).hexdigest()`，得到固定 64 个 ASCII 字符：

- 数据库主键长度固定，不受 JWT 长度、Unicode 或未来 claims 增长影响；
- 不持久化 bearer token 原文，降低数据库泄露后的直接会话劫持风险；
- `ActiveTokenStore.add`、`discard`、`__contains__` 的调用契约保持 raw token 入参，仅在存储边界统一摘要；
- `revoke_user(user_id)` 仍按用户列删除，不受主键变化影响；
- 现有会话可通过迁移时对旧 token 计算摘要继续生效。

## 3. 目标结构与兼容语义

终态 `rebuild_active_token`：

- `token_digest CHAR(64)`：ASCII/BINARY 语义，非空，主键；
- 删除旧 `token` 原文列；
- `user_id INT NULL`，外键仍指向 `rebuild_user(id)`；
- `username`、`role`、`capability`、`issued_at`、`expires_at` 保持现有契约和索引；
- 普通登录 token 写真实 `user_id`；
- validation/i23 capability token 的外部 claims 继续保留 `user_id=0`，数据库行写 `user_id=NULL`，表达非持久用户主体。

## 4. 版本化迁移方案

建议 revision：`i1_0001_active_token_digest_nullable`，由 identity 域通过共享 `MigrationRunner` 执行，包含 checksum、迁移台账、幂等跳过和每次启动后的 postflight。

生产 MySQL 优先使用影子表，避免多步 `ALTER TABLE` 的隐式提交留下半迁移状态：

1. 迁移前记录旧表行数、主键、FK、索引和孤儿行计数；孤儿或重复摘要非零时 fail closed。
2. 创建目标结构影子表。
3. 从旧表复制：`token_digest=SHA2(token, 256)`；保留其他字段；既有普通用户 `user_id` 原样复制。
4. 校验新旧行数一致、digest 非空且唯一、FK 无孤儿。
5. 原子换名：旧表改为受控 backup 名，影子表改为 `rebuild_active_token`。
6. postflight 通过后把 revision 记为 completed；backup 延迟删除，纳入部署窗口清理步骤。

SQLite 测试路径使用重建表并由 Python 逐行计算 SHA-256，不依赖 SQLite 缺失的 `SHA2()` 和有限的 ALTER 能力。

1.9 当前 10 行 token 均为 208 bytes，`user_id=0`、孤儿 FK、超过 255/262 的行均为 0；可计算 digest 并保持现有会话有效。现有 `VARCHAR(512)` 会作为迁移输入被正式收编，不再作为未登记漂移遗留。

## 5. 强制 postflight

`MigrationRunner` 返回后每次启动均验证：

- raw `token` 列不存在；
- `token_digest` 为 64 长度、非空、主键；
- `user_id` nullable 且 FK 目标为 `rebuild_user.id`；
- 既有 user_id 索引仍存在；
- revision checksum 与迁移台账一致。

已 completed 后若发生删列、改列、主键/FK/nullable 漂移，应抛迁移错误并阻止应用启动，不自动修复带外漂移。

## 6. 测试矩阵

1. 旧 raw-token 表首次迁移为 digest 主键，行数守恒。
2. 旧会话迁移后 `token in active_tokens` 仍为真，`discard(token)` 正确删除。
3. `add`、`__contains__`、`discard` 对同一 raw token 使用一致 SHA-256。
4. 262 byte 与 736 byte token 均可登记，数据库不保存原文。
5. 普通登录行保留真实 `user_id`。
6. validation/i23 外部 claims 保持 `user_id=0`，数据库行为 `NULL`，FK 开启时签发成功。
7. `revoke_user` 事务语义和返回计数不退化。
8. 首跑 applied、重跑 skipped、checksum 冲突 fail closed。
9. 重复 digest、空 digest、孤儿 FK、行数不守恒均在换名前拒绝。
10. completed 后删列、改 nullable、改 PK/FK/索引均被 postflight 拒绝。
11. MySQL 1.9 前后快照对照：行数、会话有效性、revision completed、容器健康。

## 7. 风险与执行边界

- MySQL DDL 可能隐式提交，必须先快照并使用影子表；不得直接串行 DROP/ALTER 后假设事务可回滚。
- 摘要碰撞按唯一约束和迁移前重复校验 fail closed，不覆盖记录。
- backup 表需延迟删除，避免验证窗口内无法恢复；删除动作另留证据。
- 本报告仅提交策略供监督线核准；未实施模型、迁移、1.9 DDL 或重启。
- 遵守 S349 红线：不触碰 `ai_bridge.py`、`rebuild/api/app.py`、`ai_tools.py`、`test_ai_tools_production_handlers.py` 四件原子单元现态。

## 8. 待核准项

请监督线核准：**采用方案 B（digest 键硬化）作为 DB-token-02 的 token 上界策略**。核准后 Codex 按本报告实施 identity 模型、ActiveTokenStore、版本化迁移、测试与 1.9 对照验收。
