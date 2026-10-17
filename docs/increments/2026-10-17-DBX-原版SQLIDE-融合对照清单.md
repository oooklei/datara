# DBX × 原版 SQLIDE 融合对照清单（2026-10-17，P1-7 / D9 执行令产出；v2 修订）

> 目的：落实设计 §13.17-9 D9——「全面学习和研究 DBX 代码、使用文档等相关资料，与现有原版 SQLIDE 进行融合；若存在冲突和歧义，优先级以 DBX 为准。原版 SQLIDE 在界面操作层面具备自身特色和优势，在条件允许的情况下可进行吸收融入。」
> 输入基线：DBX=`D:\dbx-main` 本地快照（标识见 §0）；原版 SQLIDE=Datara 现行 `/ide`（`datara-web/src/views/ide/` + `datara-backend/api/ide.py`）；承接映射 v2.2（`2026-10-17-DBX-DS-源码研读与复刻映射.md`，九能力锚点不重复展开）；Codex 对象×驱动×操作矩阵与 DDL 源码复核两份 evidence（`docs/increments/evidence/R5/dbx-object-driver-operation-matrix-20261017.md`、`dbx-ddl-source-review-20261017.md`）。
> 研读方法：3 子智能体并行（原版前端/原版后端/DBX 补研）+ 主智能体亲核补研（DBX 补研 agent 对 `D:\dbx-main` 误报不存在，主智能体实证路径有效后直接研读，事故经心跳 #52 披露）。
> O7 边界与证据分级：本文仅登记带源码锚点的实证结论；标注「待精读」处不落笔为事实。锚点分三级——【亲核】=Trae 主智能体直接 Read/Grep/计算实证；【补研】=Trae Explore 代理返回、主智能体已复核路径存在性但未逐行复读；【转引】=Codex 已入库 evidence 文件。本文是 A5 冻结前议程输入，不直接改 R5 契约。
> v2 修订说明：对照 T-1 评审（`docs/increments/evidence/2026-10-17-Codex-T1-P1-7-review.md`，FAIL）五缺口与复评清单 7 项逐项闭环——缺口①→§2 新增对象×驱动矩阵；缺口②→§3 新增端到端阶段映射；缺口③→§9 重写逐项锚点表；缺口④→§1 凭证存储行+C5 改真锚；缺口⑤→§0 新增快照可复现标识；复评第 6 项（C2 DBX 优先约束）→§1 语句切分行+C2；复评第 7 项（查询执行生命周期重写）→§1 查询执行行。闭环登记总表见 §11。

## 0. DBX 快照可复现标识【亲核，v2 新增】

- 快照根：`D:\dbx-main`；**无 `.git` 目录**（`Test-Path` 实证为 False），无法以 git rev 指识，manifest 为唯一指识手段。
- 采集时间：2026-10-17 13:43:33 +08:00（Asia/Shanghai）；采集过程只读，未改动快照任何字节。
- 顶层结构：16 目录（`.cargo` `.github` `.husky` `agents` `apps` `crates` `deploy` `docs` `examples` `packages` `plugins` `scripts` `skills` `src-tauri` `tests` `vendor`）+ 25 顶层文件（`Cargo.toml`/`Cargo.lock`/`package.json`/`pnpm-lock.yaml`/`README.md`/`README.zh-CN.md`/`vitest.config.ts` 等）。
- 纳入/排除规则：正则 `\\(\.git|target|node_modules|dist|build)(\\|$)` 排除构建产物与依赖目录；其余全部纳入。
- 计数：**6301 文件 / 230,992,887 字节**（排除后口径）。
- 聚合算法（两层清单法，可复现）：①对全部纳入文件按完整路径升序，逐文件计算 SHA256；②行 `<相对路径>\t<字节数>\t<文件SHA256>` 以 `\n` 连接（UTF-8），对连接结果再取一次 SHA256 即聚合值。
- **AGG_SHA256 = `cc069370b0b5db2c24f3e182ed0401ed5256452d77a3ca79f60d3b538a861409`**（ROW_COUNT=6301）。
- 快照若变动（DBX 升级/重取）聚合值即失效，须重新采集并在本文登记新值；本文全部 DBX 锚点仅对与该聚合值一致的快照成立。

引用锚点文件逐文件 SHA256【亲核】：

| 文件（相对 `D:\dbx-main`） | SHA256 |
|---|---|
| `crates/dbx-core/src/persistence/secret_codec.rs` | `9502b861acb54fe6257feabbaadaa444ba7669a1b07de6368f7703f03d1be89f` |
| `crates/dbx-core/src/persistence/storage.rs` | `8857f34b91e7160bfaaeffc73cc21115af0eb2da97c0eb9558b2020b5ae970cf` |
| `docs/content/docs/data-security-migration.cn.mdx` | `2603a635d21544cbe3f3d7a08d994f1ddc3871e08f8ac3f5aa446f8e8d7c6f1c` |
| `crates/dbx-core/src/query/mod.rs` | `2d0c416c5ca5a16b48ce10ca1c3a7c8a4f5a9d7b97bc4f4f41044abd9416e71d` |
| `crates/dbx-core/src/connection/mod.rs` | `b75081662c7104c3aa328cbf340d433e65afe0c170c502bff815697f01652929` |
| `crates/dbx-core/src/schema/mod.rs` | `c2dc30b5704f6d30039911a3ba0177630dbf3fc8a867d14e5f04f080ff0e000b` |
| `crates/dbx-core/src/schema/providers/native.rs` | `1dff8da91473aac123fb12b7ac4c5f08a065ba142ce7d2c7926e28509ef874c8` |
| `apps/desktop/src/lib/database/databaseObjectCapabilities.ts` | `37853354897acc6149911fd217627a4853741b218f3f8c6020d2474e52898f2c` |
| `crates/dbx-sql-schema/src/schema_diff.rs` | `6bbd71436ab3639608dddc1eeb391a9b4c88162365a89dcaf3a03336d0838487` |
| `src-tauri/src/commands/global_search.rs` | `17f3168b3772b36e32b5b0c1e5d624abfcf7b06f253e67934bb1ee9077eda927` |
| `src-tauri/src/commands/docs.rs` | `aa8e21973f86b6af79a13ea7839c13b05cb5f95e6edbad0aed4bf9ab7a189118` |
| `apps/desktop/src/components/editor/QueryEditor.vue` | `6972d7862d752b18ad252167ab72df6db6c861566fc0546d6b139c6b21a1ae54` |
| `apps/desktop/src/components/grid/DataGrid.vue` | `e411798d08d3e357f184d0746d6288e5ca29a6ca713fefe7e74ae53e51a6362f` |
| `crates/dbx-core/src/connection/driver_runtime.rs` | `1db99664499912fae16a2dbf75b4bf9a490238895caaab570fc8b96ffd2c0cad` |

## 1. 能力面对照总表

| 能力 | DBX（锚点） | 原版 SQLIDE（锚点） | 冲突判定 | 重构落点 |
|---|---|---|---|---|
| 编辑器内核 | CodeMirror 6 + composable 体系（`apps/desktop/src/components/editor/QueryEditor.vue:L26-L49`） | Monaco + 自研 Monarch `datara-sql` 语言（`views/ide/components/SqlEditor.vue:L4-L10`、tokenizer `L47-L108`） | **冲突→DBX 为准**（CodeMirror 6；R5-A 已选 CM6 一致） | CM6 + DBX composable 分层 |
| 自动补全 | 语义补全引擎 + select* 展开（`lib/sql/sqlCompletion`、`lib/sql/semantic/completion`，QueryEditor.vue:L88-L90） | 触发字符 `$/{`：全局参数/内置时间参数/函数式日期/表字段/关键字（`SqlEditor.vue:L193-L281`） | 不冲突（能力互补） | DBX 语义引擎为基 + 原版变量补全语义吸收（见 §6） |
| 语句切分运行 | 语句边界缓存 + 可执行区间（`useQueryEditorStatementBoundaries`、`lib/sql/executableStatementRangeCache`，QueryEditor.vue:L68） | 选中片段优先，否则全文（`SqlEditor.vue:L499-L517`） | **冲突→DBX 为准**：语句边界语义优先；选区仅作为执行目标收集的输入范围，**不得产生跨越语句边界的半截执行单元**（选区与语句边界冲突时以 DBX 语句完整性为准，兼容行为留 A5 裁定） | CM6 语句边界 + 选区输入范围兼容 |
| SQL 格式化 | 格式化+压缩双操作，按库类型门控（`lib/sql/sqlFormatter`，QueryEditor.vue:L72；跨 tab 重放防护 `QueryEditor.vue:L1-L16`） | Ctrl+Shift+F 格式化（`views/ide/IdeView.vue:L37-L43`） | 不冲突 | DBX formatter + 原版快捷键吸收 |
| 变量语法 | SQL 参数语法开关（`lib/sql/sqlVariableSyntax`，QueryEditor.vue:L75） | `${var}` Monarch 分色 + 补全（`SqlEditor.vue:L47-L108`、`L193-L281`）；后端渲染 `${name}`/`$[date]`/`date(N)`+明文快照（`datara-backend/common/vars_render.py:L103-L154`） | 不冲突（Datara 变量统筹 §3.3 已裁定原版为权威） | 后端 vars_render 语义 + 前端 CM6 高亮/补全 |
| 查询执行 | **Tauri command await 请求-响应阻塞式生命周期**：前端 invoke 后同步等待结果集一次性返回，无任务表/SSE 中间态（映射 v2.2 §1 行 1-2；DataGrid/QueryEditor 直接消费） | 异步 taskId+SSE 推送+KILL QUERY 取消+并发池/TTL（`api/ide.py:L57-L75`、`L384-L441`、`L477-L506`） | **冲突（执行生命周期形态）→ DBX 语义为准**：单连接会话内串行、结果集一次性返回、取消即连接级中断等执行语义按 DBX；taskId+SSE 仅作为 Datara Web 形态的**传输适配层**保留，任务生命周期不得引入 DBX 语义之外的隐式重试/重放。**R5-A 17 方法为 FE 契约冻结，不等于 BE/A5 语义冻结**——执行生命周期语义进入 A5 议程 | R5-A 17 方法 FE 已冻结；BE 执行语义按本行约束进入 A5 |
| 结果分页 | 虚拟滚动+独立分页组件（`components/grid/DataGrid.vue:L11`、`DataGridPagination.vue`，DataGrid.vue:L84） | 内存分页+`/ide/result` 服务端重放分页+页间漂移提示（`views/ide/components/ResultPanel.vue:L85-L149`、`api/ide.py:L538-L615`） | 不冲突（前后端分工互补） | 服务端重放分页（原版架构）+ DBX 网格交互 |
| 数据编辑 | 行级编辑+插入行对话框+DML 预览+危险确认（`DataGrid.vue`、`DataGridInsertRowsDialog.vue`、`lib/sql/dmlChangePreview` QueryEditor.vue:L70、`DangerConfirmDialog.vue` DataGrid.vue:L81） | ExplorerTree 行级编辑能力（`views/ide/components/ExplorerTree.vue`） | 不冲突（DBX 形态更完整） | R5-B 范围，按 A5 议程裁定；提交 SQL 生成链现状见 §9 第 3 项 |
| 历史与资产 | SQL 历史+文件式保存 SQL（映射 v2.2 §1 行 6-7） | IdeHistory 全文+渲染 SQL+逐条日志 JSON（`common/models.py:L394-L421`） | 不冲突 | R5-A 已含 history/scripts |
| 导出 | CSV/text/xlsx/库导出/表导入导出/Mongo dump（commands `csv_export.rs`、`text_export.rs`、`xlsx_export.rs`、`database_export.rs`、`table_import.rs`、`mongodb_*`） | CSV/JSON/XLSX 流式导出+exported 标记（`api/ide.py:L692-L852`） | 不冲突（DBX 覆盖更广） | R5 范围按 A5 议程裁 |
| 对象树 | database→schema→对象 + ObjectSourceKind 13 变体 + DDL 双轨（映射 v2.2 §1 行 8/DDL 行；13 变体实锚见 §2） | ExplorerTree + datasource tree INFORMATION_SCHEMA（`api/datasource.py:L428-L480`） | **冲突→DBX 为准**（对象枚举粒度/只读门控） | R5-A MetaTree 9 类收敛映射见 §2.3 |
| 连接管理 | PoolKind 分级+metadata pool+Agent 守护驱动+JDBC 改写+driver_profile 持久化（`commands/connection.rs:L9-L14`、`L82-L105`；`crates/dbx-core/src/connection/` 7 模块） | pymysql 短连接工厂+SELECT 1 测试（`common/dsconn.py:L38-L74`）；数据源中心独立页面（`router/routes.ts:L38-L39`） | **冲突→DBX 为准**（连接池分级抽象/驱动适配层） | Datara 数据源中心保留 UI 形态，池化/能力分级按 DBX |
| 凭证存储 | **真锚【亲核】**：`crates/dbx-core/src/persistence/secret_codec.rs` 独立 SecretCodec——AES-256-GCM（12B 随机 nonce + AAD(namespace,key)，信封 `dbxenc1.<nonce>.<ciphertext>` URL_SAFE_NO_PAD，`L20` PREFIX、`L267-L303` encrypt/decrypt）；密钥三来源优先级=显式环境密钥（`DBX_SECRET_KEY`/`DBX_SECRET_KEY_FILE`，显式配置不可读不静默回退）> OS 凭据库（os-keyring feature：macOS Keychain/Windows Credential Manager，`platform_keyring_codec` `L306-L324`，SERVICE=`com.dbx.app.secret-store.v1` `L22-L24`）> 数据目录托管密钥 `${DBX_DATA_DIR}/.dbx/secret.key`（`data-security-migration.cn.mdx:L45-L129` 全链引证）；密文落 SQLite `connection_secrets.secret_enc`（`storage.rs:L1010-L1016`）；密钥迁移状态机 `SECRET_STORE_MIGRATION_ID="secret-store-v1"` + MigrationState 五态（`storage.rs:L234-L254`）；迁移未完成业务 API 返回 `423 DATA_MIGRATION_REQUIRED`（mdx:L103）。Tauri 层 `commands/connection_secrets.rs` 为 legacy 空壳注记、`commands/keychain.rs` 仅为旧读取辅助 | 密码明文存储（`common/models.py:L243-L264`） | **冲突→DBX 为准**+Datara 安全基线加严 | 禁明文；存储方案 R6 加固裁定 |
| 执行上下文 | 跨 Schema 注入按库类型分级（映射 v2.2 §1 行 4；端到端映射见 §3） | 未发现等价机制（ide.py 无 schema 注入） | **冲突→DBX 为准** | A5 议程已含 |

## 2. 对象类型 × 驱动能力矩阵（v2 新增，评审缺口①）

### 2.1 ObjectSourceKind 13 变体【亲核】

- 定义：`crates/dbx-types/src/types.rs:L209-L223`，serde `SCREAMING_SNAKE_CASE`——`VIEW` `MATERIALIZED_VIEW` `PROCEDURE` `FUNCTION` `TRIGGER` `EVENT` `SEQUENCE` `SYNONYM` `JOB` `PACKAGE` `PACKAGE_BODY` `TYPE` `TYPE_BODY`。**不含 TABLE/INDEX**：表结构走独立元数据通道，索引为表子对象（ObjectSourceKind 只覆盖「源码型对象」）。
- 载体结构 `ObjectSource { name, object_type, schema, source, editable }`（`types.rs:L225-L233`）——`editable` 为可选标志，是「源码可编辑性」的驱动侧声明位。
- 驱动侧镜像枚举：`agents/drivers/duckdb/src/wire.rs:L19`【亲核-定义存在】。

### 2.2 能力矩阵（全表转引 Codex evidence）

矩阵全表（驱动清单×声明对象集、对象×操作 L/G/E/N/V/D/X/R 分级、执行路径×对象×操作、分页/权限/副作用、静态源码不可证明清单）登记于 `docs/increments/evidence/R5/dbx-object-driver-operation-matrix-20261017.md`【转引】，本文只登记其锚点与结论：

- 前端能力声明面：`apps/desktop/src/lib/database/databaseObjectCapabilities.ts:L3-L10`（声明结构）、`L42-L110`（逐驱动对象集）【亲核-路径+行窗，矩阵内容转引】。
- 后端路由：对象清单路由 `crates/dbx-core/src/schema/providers/native.rs:L81-L109`；对象源/DDL 读取路由 `crates/dbx-core/src/schema/mod.rs:L7067-L7293`、`L10738-L10905`【转引，路径亲核存在】。
- 操作分级 V/C/U/N/NA 与执行路径矩阵：见 evidence 全表。
- 关键结论：①分页/权限/副作用随驱动而异，无全局一致性保证；②静态源码不可证明项（运行时权限、Agent 进程实际返回）已在 evidence 专节列明，本文不落笔为事实（O7）。

### 2.3 R5-A MetaTree 9 类收敛映射（13→9）【亲核】

- R5-A 冻结词形：`ObjectKind = database | schema | table | view | column | index | function | procedure | trigger`（`datara-web/src/services/rebuild/sqlIdeApi` ObjectKind；`MetaTree.vue:L3`「design §7 九类」注记、`L48-L58` iconMap 实锚）。
- 映射规则：
  - 容器/结构类 `database/schema/table/column/index` 来自元数据通道（非 ObjectSourceKind）；
  - 源码型直映 5 类：`VIEW→view`、`MATERIALIZED_VIEW→view`、`PROCEDURE→procedure`、`FUNCTION→function`、`TRIGGER→trigger`；
  - 未纳入 8 类：`EVENT/SEQUENCE/SYNONYM/JOB/PACKAGE/PACKAGE_BODY/TYPE/TYPE_BODY`。
- 排除理由：design §7 九类为 R5-A 冻结范围；扩展属 A5 议程，不由本清单单方扩张。
- 回扩门槛：每类须同时具备 ①对象清单路由锚点 ②DDL 读取路由锚点 ③至少一驱动实测证据，三者齐备方可进入契约扩展提案。
- 验收证据形态：引用本文 §2 + evidence 矩阵文件 + MetaTree 实锚行号。

## 3. 跨 Schema 与对象端到端阶段映射（v2 新增，评审缺口②）

### 3.1 跨 Schema 执行上下文锚点【转引+亲核路径】

`crates/dbx-core/src/query/mod.rs:L894-L1064`（跨库执行上下文注入）、`L2165-L2266`（承接映射 v2.2 §3.2）；连接分级 `crates/dbx-core/src/connection/mod.rs:L106-L145`（PoolKind 10 类，含 Agent/ExternalDriver/PluginConnection 三特殊连接，见 §9 第 4 项）。

### 3.2 端到端阶段表（对象生命周期 × R5 分层）

| # | 阶段 | 对象面 | R5 层 | DBX 锚点 | 原版对应 | 状态 |
|---|---|---|---|---|---|---|
| 1 | 连接与池分级 | 全部数据源 | R5-B | PoolKind 10 类（`connection/mod.rs:L106-L145`） | pymysql 短连接（`dsconn.py:L38-L74`） | A5 |
| 2 | 对象发现（树） | 9 类 | R5-A | MetaTree + `native.rs:L81-L109` | ExplorerTree+INFORMATION_SCHEMA（`datasource.py:L428-L480`） | R5-A FE 冻结 |
| 3 | 元数据（结构） | 表/视图/字段/索引 | R5-A | `schema/mod.rs` 元数据路由 | 无（原版仅库/表/字段三层） | A5 |
| 4 | 对象源码读取（DDL 双轨） | 13 变体 | R5-B | `schema/mod.rs:L10738-L10905` + `types.rs:L209-L233` | 悬浮生成 SQL（`IdeView.vue:L37-L43`） | A5 |
| 5 | 只读浏览执行 | 表数据 | R5-A | 17 方法 | ResultPanel 分页 | A5 BE |
| 6 | source-backed 编辑 | 源码型对象（view/procedure/function/trigger 等，以 `ObjectSource.editable` 为声明位） | R5-B | `types.rs:L225-L233` + DDL 复核 evidence（`dbx-ddl-source-review-20261017.md`） | 无 | A5 |
| 7 | 表结构编辑（列/索引/约束） | table | R5-B | DataGrid 编辑链（§9 第 3 项）+ schema_diff `sync_sql`（§9 第 5 项） | ExplorerTree 行编辑 | A5 |
| 8 | 写入执行+审计回滚 | 全部写操作 | R5-B | 历史 `activity_kind/operation/rollback_sql`（`storage.rs:L1017-L1038` history 表） | ide.py 执行循环失败即停（`L192-L289`） | A5 |

分层原则：R5-A 只读（阶段 2/3/5），R5-B 写入（阶段 1/4/6/7/8）；本表为 A5 冻结前议程输入，不直接改 R5 契约。DDL 双轨精读与依赖迁移/版本审计回滚证据矩阵全文见 `docs/increments/evidence/R5/dbx-ddl-source-review-20261017.md`【转引】。

## 4. 融合点清单（DBX 主导，原版无或弱）

1. 连接池分级抽象（10 类连接池枚举 + metadata 池分离）与驱动适配层（Agent 守护进程/JDBC 配置改写/Mongo legacy 回退——`connection.rs:L25-L105`）。
2. 驱动运行时进程治理：pid/内存/CPU/uptime 监控、可停止/重启（`crates/dbx-core/src/connection/driver_runtime.rs:L9-L39`）——Agent/ExternalDriver/PluginConnection 三类特殊连接的运行时形态（深语义现状见 §9 第 4 项）。
3. 结果网格语义面：key columns/值变换/单元格详情/过滤 builder/列头操作/提取器（`DataGrid.vue:L82-L90` 子组件群）。
4. 数据编辑闭环：插入行对话框+DML 变更预览+危险确认（§1 数据编辑行）。
5. 语句边界执行与执行目标选择器（`SqlExecutionTargetPicker.vue`，QueryEditor.vue:L51；`resolveExecutableSql` L66）。
6. 编辑器工程面：搜索/goto 面板、Intention popup、表结构 Peek 插入、拖拽表名（useQueryEditorTableDrop）、代码快照、Vim 键位（QueryEditor.vue:L12-L62）。
7. 结构对比/数据对比/schema 缓存/全局搜索（`crates/dbx-sql-schema/src/schema_diff.rs`、`src-tauri/src/commands/schema_diff.rs`、commands `data_compare.rs`、`schema_cache.rs`、`global_search.rs`；语义现状见 §9）——原版 SQLIDE 无对应能力，登记为 DBX 特色待议。
8. 错误类型化模型（Agent/DuckDB/取消/超时分类，映射 v2.2 §1 行 3）。

## 5. 冲突判定表（D9：冲突歧义以 DBX 为准）

| # | 冲突点 | DBX 立场 | 原版立场 | 判定 |
|---|---|---|---|---|
| C1 | 编辑器内核 | CodeMirror 6 | Monaco+自研 Monarch | DBX；原版 Monarch 语言资产（`datara-sql`、`${var}` 分色规则）作为语义参照移植 |
| C2 | 语句运行粒度 | 语句边界精确切分+缓存；**执行单元以语句完整性为准** | 选中优先/全文兜底 | **DBX 语义为准**：选区仅作为执行目标收集的输入范围，选区与语句边界冲突时不得产生半截执行单元；「选中优先」是否作为显式用户确认后的兼容行为保留，留 A5 裁定 |
| C3 | 对象枚举 | 13 变体 ObjectSourceKind（§2.1）+只读门控 | INFORMATION_SCHEMA 库/表/字段三层 | DBX 粒度；R5-A MetaTree 9 类为收敛子集（映射与回扩门槛见 §2.3），扩展路径留 A5 |
| C4 | 连接模型 | 池化分级+驱动进程化 | pymysql 短连接 | DBX 池化；短连接形态仅保留在测连场景语义 |
| C5 | 凭证存储 | **真锚（§1 凭证存储行）**：SecretCodec AES-256-GCM 信封 `dbxenc1.*` + SQLite `connection_secrets.secret_enc` 密文列 + 密钥三来源（显式 env > OS 凭据库 > 数据目录托管）+ `secret-store-v1` 迁移状态机（`storage.rs:L234-L254`） | 明文 | DBX 方向+Datara 安全基线加严，禁明文；具体落地方案 R6 加固裁定 |
| C6 | 编辑器交互工程 | composable 巨阵（补全/悬停/拖拽/Vim/诊断） | Monaco 原生能力+轻封装 | DBX 交互语义为准；Monaco 特有能力逐项评估移植成本 |

## 6. 原版 SQLIDE 特色吸收项登记（界面操作层）

1. **悬浮表/视图生成 SQL**：对象悬浮即时产出 SELECT/DDL 草稿（`IdeView.vue:L37-L43`）。
2. **结果 Tab 回显 SQL + 单元格复制**（`IdeView.vue:L37-L43`）。
3. **三快捷键**：Ctrl+Enter 运行 / Ctrl+S 保存 / Ctrl+Shift+F 格式化（`IdeView.vue:L37-L43`）。
4. **结果页间漂移提示**：服务端重放分页时诚实提示数据可能漂移（`ResultPanel.vue:L85-L149`）——数据正确性 UX，必收。
5. **服务端重放分页架构**：历史 SQL 可重放出任意页（`api/ide.py:L538-L615`）——审计与重复查看优势，必收；与 §1 查询执行行的「传输适配层」定位一致，不得反改为执行语义真源。
6. **`${var}` 变量分色+分类补全**（全局参数/内置时间参数/函数式日期，`SqlEditor.vue:L193-L281`）——变量统筹 §3.3 的前端落点，移植至 CM6。
7. **失败即停+警告收集+取消标记** 执行循环语义（`api/ide.py:L192-L289`）——后端执行语义与 DBX 对齐后保留。
8. **数据源中心独立页面**（`routes.ts:L38-L39`；页面结构实锚见 §9 第 6 项）与 IDE 解耦的 UI 信息架构——保留。

## 7. 命令面全量盘点（DBX src-tauri/src/commands/，77 文件按域分组）

- 执行/取消：query.rs、query_cancel.rs、external_sql.rs、list_sql_files.rs、sql_file.rs
- 连接：connection.rs、connection_secrets.rs（legacy 空壳）、keychain.rs（旧读取辅助；现行真锚为 dbx-core persistence 层，见 §1）、ssh_config.rs、ssh_keys.rs、ssh_prompt.rs、tunnel_profiles.rs
- 资产/历史：history.rs、saved_sql.rs、tab_runtime_cache.rs、global_search.rs
- 导出/导入：csv_export.rs、text_export.rs、xlsx_export.rs、query_result_export.rs、table_export.rs、table_import.rs、database_export.rs、mongodb_import_export.rs、mongodb_dump.rs、sqlite_backup.rs、local_backup.rs、transfer.rs
- 对象/元数据：schema_diff.rs（命令入口；核心 diff 结构在 `crates/dbx-sql-schema/src/schema_diff.rs`，web 路由 `crates/dbx-web/src/routes/schema_diff.rs`）、schema_cache.rs、data_compare.rs、dialect_cmd.rs、document_cmd.rs、docs.rs（web 路由 `crates/dbx-web/src/routes/docs.rs`）
- 特殊数据源：mongo_cmd.rs、redis_cmd.rs、redis_pubsub_server.rs、hbase_cmd.rs、mq_cmd.rs、mqtt_cmd.rs、nacos_cmd.rs、etcd_cmd.rs、zookeeper_cmd.rs、external_db.rs、vector_cmd.rs、salesforce_oauth.rs
- AI/MCP：ai.rs、ai_multi_config.rs、agents.rs、mcp.rs、mcp_bridge.rs、mcp_http_server.rs、mcp_native_installation.rs、prompt_template.rs、user_skills.rs
- 插件：plugins.rs、plugin_download.rs、plugin_download_file.rs、plugin_media.rs、plugin_storage.rs
- 壳/平台（**不属于 SQL IDE 能力面，不复刻**）：window_controls.rs、update*.rs、launch_args.rs、deep_link.rs、fs_open.rs、system_fonts.rs、support_info.rs、diagnostics.rs、app_settings.rs、background_image.rs、cloud_sync.rs、config_cmd.rs

## 8. 使用文档面（DBX）

- README/README.zh-CN：产品定位「25MB 驾驭 100+ 数据库；桌面/Docker/CLI；内置 AI 助手与 MCP Server」+ 27+ 数据库徽标清单（`README.zh-CN.md:L2-L49`）。
- docs/：官网工程（Next.js）+ 开发者专题文档（表导入基准、PG 分区表计划、PG 错误定位、MQTT、Mongo 备份恢复、数据安全迁移、后台备份、后端错误处理规范等，`docs/` 目录 Glob 实锚）；**未发现面向终端用户的系统化使用手册**（官网承载）。
- 补充：`commands/docs.rs` 已实锚为**内置知识文档工程命令面**（收集快照/标注/HTML 导出，见 §9 第 1 项），非用户手册载体；数据安全迁移文档 `data-security-migration.cn.mdx:L45-L129` 为凭证存储真锚引证源（§1）。

## 9. 边界与待精读（v2 重写为逐项锚点表，评审缺口③）

| # | 项 | 实现路径 | 锚点 | 已确认结论 | 剩余待精读 | 状态 |
|---|---|---|---|---|---|---|
| 1 | 内置文档 docs.rs | `src-tauri/src/commands/docs.rs`（web 侧 `crates/dbx-web/src/routes/docs.rs`；前端桥 `apps/desktop/src/lib/backend/tauri.ts`） | 命令面 `docs.rs:L43-L146`【补研】：`docs_collect_snapshot` / annotations / `export_html` 三组 | 内置知识文档的收集快照/标注/HTML 导出工程能力，非用户手册 | 无阻塞项 | **已锚定结案** |
| 2 | 全局搜索 global_search.rs | `src-tauri/src/commands/global_search.rs` | `L37-L258`【补研】：roots/query/extensions 参数面、正则支持、文件内容+文件名双模式、返回 `GlobalSearchMatch` | 工作区文件级全局搜索（非 SQL 历史检索） | 无阻塞项 | **已锚定结案** |
| 3 | DataGrid 提交 SQL 生成链 | 前端 `apps/desktop/src/components/grid/DataGrid.vue` | `L120-L135`【补研】：`canEditExistingTableRows` / `canInsertTableRows` / `buildDataGridConditionalUpdateSql` | 前端编辑能力起点与条件更新 SQL 生成入口已定位 | 后端对应物（commands 侧生成/校验链）未亲核 | **前端已锚，后端链待精读**（A5 议程保留） |
| 4 | PoolKind 三特殊连接 | `crates/dbx-core/src/connection/mod.rs` + `driver_runtime.rs` | 枚举 `mod.rs:L105-L156`【补研】（含 Agent/ExternalDriver/PluginConnection）、信息源区分 `L243-L280`（Agent/MongoAgent/ExternalDriver）、进程治理 `driver_runtime.rs:L9-L39`【亲核-路径】 | 枚举形态与信息源区分已锚；Agent 为守护进程驱动、ExternalDriver 为外部驱动进程 | 进程生命周期（启动/心跳/回收）深语义 | **枚举+信息源已锚，生命周期深语义待精读** |
| 5 | schema_diff / data_compare 算法 | 核心 `crates/dbx-sql-schema/src/schema_diff.rs`；命令 `src-tauri/src/commands/schema_diff.rs`；web 路由 `crates/dbx-web/src/routes/schema_diff.rs` | 数据结构 `schema_diff.rs:L27-L178`【补研】：`ColumnDiff/IndexDiff/ForeignKeyDiff/TriggerDiff/TableDiff`，含 `ddl/target_ddl/sync_sql` 字段 | 对象级结构化 diff 载体已锚（结构化而非纯文本） | diff 生成算法与 data_compare 比对深度 | **数据结构已锚，算法深度待精读** |
| 6 | 原版 `views/datasource/` 页面 | `datara-web/src/views/datasource/`（List/Wizard/Detail 三页） | `DataSourceListView.vue:L2-L7`（列表/筛选/行操作/列）、`L30-L37`+`L50-L65`（env/group/status facets+客户端过滤）；`DataSourceWizard.vue:L2-L11`（三步向导/流源注册化/编辑密码留空语义/注册必测连接）、`L38-L49`（7 类型卡：mysql/greatdb/kafka/redis/mqtt/http/file+四分组）【亲核】 | 页面结构与交互语义已锚；流源注册与连接型共用一套向导；密码留空=保持原密码（后端语义） | Detail 页内部未逐行精读 | **已锚定**（对齐映射见 §1 连接管理行） |

## 10. 不变式声明

- 本文不改变：R5-A 只读边界（U1/U3）、A5 冻结门流程、DBX 不深绑裁定（D4）、主权边界（D6 外部组件零真源化）。
- 本文是 A5 冻结前议程输入；R5-A 17 方法 FE 冻结不等于 BE/A5 语义冻结（§1 查询执行行）。

## 11. v2 闭环登记（对照 T-1 评审回执逐项）

| 评审项 | 闭环位置 | 证据分级 |
|---|---|---|
| 缺口①：对象类型×驱动能力矩阵 | §2（13 变体实锚+矩阵锚点+9 类收敛映射+回扩门槛） | 13 变体/MetaTree【亲核】；矩阵全表【转引 evidence】 |
| 缺口②：跨 Schema 端到端阶段映射 | §3（跨 Schema 锚点+8 阶段表+R5-A/R5-B 分层） | 锚点路径【亲核】；行窗【转引承接映射 v2.2】 |
| 缺口③：§7 待精读补锚 | §9 重写为逐项表（路径/锚点/结论/剩余/状态） | 1/2/6 项结案；3/4/5 项保留待精读并写明原因 |
| 缺口④：凭证存储引证改真锚 | §1 凭证存储行 + C5（secret_codec/storage/mdx 三文件真锚） | 【亲核】（secret_codec.rs:L20,L267-L303,L306-L324；storage.rs:L234-L254,L1010-L1016；mdx:L45-L129） |
| 缺口⑤：DBX 快照可复现标识 | §0（采集时间+顶层结构+排除规则+计数+两层清单法+AGG_SHA256+锚点文件逐文件 SHA256） | 【亲核】（PowerShell 只读计算） |
| 复评第 6 项：C2 DBX 优先约束 | §1 语句切分运行行 + C2（选区与语句边界冲突时 DBX 语义优先） | 判定明示，维持 A5 裁定门 |
| 复评第 7 项：查询执行生命周期重写 | §1 查询执行行（Tauri await vs taskId+SSE 生命周期分离；SSE 定位为传输适配层；R5-A FE 冻结≠BE/A5 语义冻结） | 判定重写为冲突项 |

- 评审分工：Codex 复评本清单 v2（P1-7 复评）；裁定项进入 A5 冻结前议程。
