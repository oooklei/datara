# DB-token-01 validation token 持久化缺陷预研（Codex）

- 任务来源：`s341-gov-c-ruling-clreport-20261021`，P2 预研先行。
- 状态：预研完成，等待正式落码派单。
- 边界：仅审计本地主工作区与监督线提供的 1.9 只读实证；未修改业务代码、数据库、`.git`、`STATE.md` 或 `mailbox.jsonl`。

## 1. 结论

问题由同一张 `rebuild_active_token` 表的两个契约错位组成：

1. `ActiveTokenRecord.token` 当前声明为 `String(255)` 主键，而 `validation-runner` 的真实 capability token 为 **262 bytes**，`i23-preview-runner` 为 **260 bytes**。MySQL 严格模式下前者不能写入 255 列。
2. `ActiveTokenRecord.user_id` 当前为非空 FK `rebuild_user.id`，但两个 validation issuer 都将非持久 runner 写为 `user_id=0`；目标库没有用户 0，因此启用 FK 后写入非法。
3. 1.9 已被带外改成 `token varchar(512)`，但本地 ORM 仍为 255，且 `rebuild_schema_migration` 无 active-token revision。当前运行环境与可复建环境不一致。

推荐最小兼容修复：数据库记录把 validation runner 表达为 `user_id=NULL`，token claims 继续保留 `user_id=0` 以避免改变既有 API/测试契约；为 active-token 单独建立版本化 identity migration，并将当前 1.9 的 512 漂移纳入可审计台账。

## 2. 本地代码实锚

| 实锚 | 现状 | 影响 |
|---|---|---|
| `datara-backend/rebuild/identity/models.py:41` | `token = String(255)` 且为 PK | validation token 262 bytes 超列宽 |
| `datara-backend/rebuild/identity/models.py:42` | `user_id` 为非空 FK | 非持久 runner 的 0 无父行 |
| `datara-backend/rebuild/api/app.py:201-213` | `ActiveTokenStore.add()` 原样持久化 token/user_id | 两个错误均在此落库 |
| `datara-backend/rebuild/api/app.py:477-490` | validation bootstrap claims 与 DB 均写 `user_id=0` | FK 不成立 |
| `datara-backend/rebuild/api/app.py:512-518` | I23 capability 同样写 0 | 同类缺陷 |
| `datara-backend/rebuild/api/app.py:250-258` | `ensure_i1_schema()` 仅补 user 时间列 | 无 token 宽度/FK 修复与台账 |
| `datara-backend/rebuild/identity/contracts.py:130-145` | token 为 JSON UTF-8 + base64url + HMAC | 长度取决于 username/capability |
| `datara-backend/tests/rebuild/test_identity_api.py:316-359` | SQLite 默认未开启 FK，且未断言 DB token 行 | 现有测试未发现真实 MySQL 缺陷 |

长度实测：

- `validation-runner` + `validation:bootstrap`：262 bytes。
- `i23-preview-runner` + `legacy:i23:preview`：260 bytes。
- ASCII username 64 + capability 128：480 bytes。
- 汉字 username 64 + capability 128：651 bytes。
- emoji username 64 + capability 128：736 bytes。

因此 512 能修复当前固定 runner 及 ASCII 上界，但不能覆盖当前模型允许的所有 Unicode username。正式落码必须显式处理此边界，不能把 512 宣称为数学上完整的 token 上界。

## 3. 1.9 只读实证

监督线提供的远端核验：

- `rebuild_active_token.token` 已为 `varchar(512)` 主键。
- `user_id` 仍为 `NOT NULL` 且保留到 `rebuild_user.id` 的 FK。
- 现存 10 行 token 长度均为 208；无 `user_id=0`、无孤儿行。
- `rebuild_schema_migration` 无 active-token 对应 revision。

这说明 512 是未登记的环境漂移，尚未解决 validation runner 的 FK 语义；现有 10 行不能证明 262-byte capability token 可成功落库。

## 4. 正式实施方案

### 4.1 模型与写入语义

1. `ActiveTokenRecord.user_id` 改为 `Mapped[int | None]`、`nullable=True`，保留 FK。
2. 普通登录 token 继续持久化真实用户 ID。
3. validation bootstrap 与 I23 capability 的 token claims 继续是 `user_id=0`；调用 `ActiveTokenStore.add()` 时改存 `user_id=None`。
4. `revoke_user()` 仅处理真实用户 ID，NULL runner token 仍按 TTL 或 token discard 清理。

### 4.2 版本化迁移

新增 identity migration，例如：

- `rebuild/identity/migrations.py`
- `rebuild/identity/revisions/v0001_active_token_capacity.py`
- revision 建议：`i1_0001_active_token_capacity`

复用共享 `GovernanceMigration`/`MigrationRunner`，在 `create_app` lifespan 接入。升级过程须：

1. 校验目标表、PK、FK 与既有列；未知漂移 fail closed。
2. MySQL 将 `user_id` 改为可空，保留 FK/index。
3. 将 token 宽度规范化并登记 checksum；对已为目标宽度的 1.9 执行“验证后登记”，不重建或清空表。
4. 升级后重新反射校验 token 长度、主键、user_id nullable、FK/index；失败不得将 revision 标 completed。
5. 重跑时 skipped 后仍做 schema postflight，防止 completed 后带外漂移。

### 4.3 token 宽度决策

建议正式票明确二选一：

- **兼容最小方案**：沿 1.9 既有漂移冻结 `VARCHAR(512)`，同时为用户创建/TokenService 增加可证明的 512-byte 上界检查；超过上界必须在签发前以稳定业务错误拒绝。
- **长期稳健方案（推荐）**：active store 以 SHA-256 token digest（64 个十六进制字符）为查找键，不再用原 token 作为 PK；迁移现存行并修改 add/contains/discard。这样消除 token 内容长度与索引字节数耦合。该方案变更面较大，应单独冻结契约后实施。

若本票限定只收口已发生的 1.9 漂移，则采用最小方案，但证据必须披露 Unicode username 上界仍需约束，不能遗漏。

## 5. 必须新增的测试

1. 使用真实 `TokenService` 生成 262-byte validation token，在启用 FK 的数据库测试中签发成功。
2. validation 与 I23 DB 行 `user_id IS NULL`；响应/claims 中 `user_id=0` 保持兼容。
3. 普通登录 token DB 行仍引用真实用户 ID。
4. 反射断言 token 宽度、PK、user_id nullable、FK 与 index。
5. 迁移首次 applied、二次 skipped、checksum 冲突拒绝。
6. 1.9 式“token 已 512、user_id 仍非空”的旧结构升级后保留全部既有行，不清表。
7. completed 后删除 FK、收窄列或恢复 NOT NULL，postflight 必须 fail closed。
8. 迁移失败只记录异常类型，不把连接串或 token 写入台账/日志。
9. 针对 ASCII/汉字/emoji username 的 token 长度边界测试，锁定正式选择的上界策略。
10. `/validation-token` 错 key、bootstrap disabled、权限不足等既有负向测试零回归。

## 6. 风险与落码前置

- MySQL 修改被 FK/index 约束的列需要按实际约束名与 DDL 顺序处理；禁止手工删约束后遗漏恢复。
- raw token 属凭据，不得出现在 evidence、迁移错误或日志中；测试只记录长度/摘要。
- SQLite 默认不执行 FK，测试必须显式 `PRAGMA foreign_keys=ON`，否则无法证明修复。
- `app.py` 是多线共享热点，正式票需最小 hunk并在稳定窗复核。
- 1.9 已有带外 ALTER；正式实施必须以 migration 登记收编，不能再次只改远端库。

## 7. 建议正式派单验收锚

- 本地：identity migration/接口定向测试全绿，迁移幂等、checksum、postflight、FK 开启用例全绿。
- 1.9：迁移台账出现 completed revision；列宽/nullable/FK/index 符合冻结方案；validation 与 I23 token 能真实签发且不泄露 token；重启后二次 skipped 且 API healthy。
- 证据：仅保留长度、摘要、schema 与台账状态；不保留 validation key、token、密码。
