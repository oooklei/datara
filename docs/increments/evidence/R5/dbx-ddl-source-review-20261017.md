# DBX 对象 DDL 源码复核与 Datara 门禁建议

- 日期：2026-10-17
- 源码基线：`D:\dbx-main`（只读研读）
- 需求基线：Datara 权威设计 §7.1、§13.6；handoff #38、#39、#40、#41
- 用途：R5-A/A5 规格决策输入，不是 A2/A5 冻结、Datara 实现完成或用户批准记录。

## 结论

DBX 具备对象定义读取、source-backed 对象编辑和表结构 SQL 生成能力；但它们不是一个统一的草稿、版本、审批、发布、审计及回滚系统。DBX 的编辑流程在桌面端构造 SQL 后直接执行；schema diff 的依赖图属于源端到目标端迁移规划，不能推断为对象编辑器的通用依赖分析 API。驱动和对象类型差异必须明示。

Datara 权威设计 §7.1 要求数据库、Schema、表、视图、字段、索引、函数、存储过程、触发器的定义查看/编辑、语法校验、依赖分析、差异对比、版本保存、发布执行和日志；§13.6 要求写操作遵循权限检查 → 依赖检查 → 影响预览 → DDL 快照 → 人工确认 → 执行 → 结果记录 → 失败回滚/补偿。DBX 只能作为参考实现与交互样本，不能证明 Datara 已满足这些要求。

## 源码证据矩阵

| 能力 | DBX 源码证据 | 证实的行为 | 对 Datara 的限制 |
|---|---|---|---|
| 对象来源类型 | `crates/dbx-types/src/types.rs:209-231` `ObjectSourceKind` | 包含 View、MaterializedView、Procedure、Function、Trigger、Event、Sequence、Synonym、Job、Package、PackageBody、Type、TypeBody；不包含 Table 或 Index。 | 对象树矩阵须另列 Table、Index；Index 是表结构子对象，不能套用 source kind 枚举。 |
| 定义读取 | `crates/dbx-web/src/main.rs:663,689`；`crates/dbx-web/src/routes/schema.rs:350-374,750-792`；`crates/dbx-core/src/schema/mod.rs:9130+、10635+` | `/schema/object-source` 读取 source-backed 对象定义；`/schema/ddl` 获取表 DDL。实际对象/驱动支持由 provider 路径决定。 | 按 database type × object type 登记 list/get-definition 能力、授权条件和缺失能力；不能将一种驱动能力泛化为所有数据源。 |
| Source-backed 编辑 | `apps/desktop/src/components/objects/ObjectSourceDialog.vue:165-213`；`apps/desktop/src/lib/table/objectSourceEditor.ts:55-89` | UI 调用构造可执行语句，再调用执行查询保存；没有证据表明它先保存项目级草稿或进入统一发布审批。 | Datara 必须另行满足项目隔离、版本/快照、确认、审计和失败补偿。 |
| 表结构编辑 | `apps/desktop/src/components/structure/TableStructureEditor.vue`；`crates/dbx-sql-schema/src/table_structure_sql.rs:43-74` | 结构化表草稿生成 columns/indexes/FK 等 SQL 并作输入模型校验；校验不等于数据库编译对象定义。Index 随表结构建模。 | 能力需按数据库方言区分。结构草稿校验不可标成通用 DDL 语法校验。 |
| SQLite 表结构写入 | `crates/dbx-web/src/main.rs:771-774`；`crates/dbx-core/src/schema/table_structure_sql/sqlite_rebuild.rs:59,69` | 有 SQLite 专属表结构变更 preview/apply 路由。 | 不构成其他数据库具有相同 preview/apply 生命周期的证据。 |
| 依赖与迁移差异 | `crates/dbx-sql-schema/src/schema_diff.rs:609-771,2011+` | `DependencyGraph` 用于 schema diff / migration planning；可提取、排序部分对象依赖并生成同步计划。 | 不等同于对象编辑器的通用依赖检查、影响预览或草稿 diff。Datara 的写路径依赖/影响分析仍是独立需求。 |
| 版本、发布、DDL 审计、回滚 | 桌面对象源保存调用链；设计 §13.6 | 本次检查未发现按项目保存对象版本、发布状态、§13.6 字段完整的 DDL 专项审计和统一回滚/补偿流程。 | 在 Datara 实现并验收前保持未完成；普通查询历史不能替代 DDL 审计。 |

## 建议的 Datara 能力分层（待标准 owner 按 §5 会签）

1. **R5-A 前置研究**：完成 DBX 对象 × 数据源驱动 × operation 的实锚矩阵，并在 A5 冻结前作映射决议。矩阵至少列 `list / get-definition / structured-edit-or-source-edit / generator / validation / dependency-analysis / execute / rollback`。
2. **R5-A 只读契约**：验收只读对象目录、矩阵允许的定义读取、表/Schema 元数据、跨 Schema 查询与补全、一般 SQL 非执行解析，以及后续冻结的查询生命周期能力。R5-A 不执行 DDL，也不假设有通用对象依赖 API 或 DDL 编译验证接口。
3. **R5-B 或经 §5 批准的等价写入阶段**：交付对象草稿、结构化 DDL 生成、真实语法验证、依赖和影响分析、diff、项目级版本/快照、人工确认、发布执行、操作者/脚本/对象/时间/结果/失败原因审计，以及失败回滚/补偿。最终验收仍完整覆盖 §7.1/§13.6。

## 对象粒度与矩阵字段

- `Table`：表结构元数据、列和约束；`Index` 作为表结构子对象呈现和变更。
- `View`、`Function`、`Procedure`、`Trigger`：source-backed 对象，逐驱动确认定义读取和 SQL 生成/执行支持。
- 其余 DBX `ObjectSourceKind`（MaterializedView、Event、Sequence、Synonym、Job、Package/Body、Type/Body）逐项标注“支持/不支持/未核实”和源码锚；不得因枚举存在而宣称支持。
- 每一项另记录分页/过滤、schema 作用域、权限、数据库版本差异、错误语义、是否有副作用与可否回滚。

## 下一步

- 将此矩阵并入 DBX–DS 研读映射 v2/v3 的 R5-A 章节（映射 owner 单写）。
- A5 owner 按用户既定优先级提出 R5-A/R5-B 分层修订，并根据 §5 完成审批、版本和双边会签；本报告本身不改变阶段冻结状态。
- 任何仅有目录或定义查询的实现不得标为“对象编辑完成”；R5-A 只读通过不得授权 DDL 写操作。

