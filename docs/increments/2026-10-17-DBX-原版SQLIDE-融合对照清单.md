# DBX × 原版 SQLIDE 融合对照清单（2026-10-17，P1-7 / D9 执行令产出）

> 目的：落实设计 §13.17-9 D9——「全面学习和研究 DBX 代码、使用文档等相关资料，与现有原版 SQLIDE 进行融合；若存在冲突和歧义，优先级以 DBX 为准。原版 SQLIDE 在界面操作层面具备自身特色和优势，在条件允许的情况下可进行吸收融入。」
> 输入基线：DBX=`D:\dbx-main` 本地快照（研读日 2026-10-17）；原版 SQLIDE=Datara 现行 `/ide`（`datara-web/src/views/ide/` + `datara-backend/api/ide.py`）；承接映射 v2.2（`2026-10-17-DBX-DS-源码研读与复刻映射.md`，九能力锚点不重复展开）。
> 研读方法：3 子智能体并行（原版前端/原版后端/DBX 补研）+ 主智能体亲核补研（DBX 补研 agent 对 `D:\dbx-main` 误报不存在，主智能体实证路径有效后直接研读，事故经心跳 #52 披露）。
> O7 边界：本文仅登记带源码锚点的实证结论；标注「待精读」处不落笔为事实。本文是 A5 冻结前议程输入，不直接改 R5 契约。

## 1. 能力面对照总表

| 能力 | DBX（锚点） | 原版 SQLIDE（锚点） | 冲突判定 | 重构落点 |
|---|---|---|---|---|
| 编辑器内核 | CodeMirror 6 + composable 体系（`apps/desktop/src/components/editor/QueryEditor.vue:L26-L49`） | Monaco + 自研 Monarch `datara-sql` 语言（`views/ide/components/SqlEditor.vue:L4-L10`、tokenizer `L47-L108`） | **冲突→DBX 为准**（CodeMirror 6；R5-A 已选 CM6 一致） | CM6 + DBX composable 分层 |
| 自动补全 | 语义补全引擎 + select* 展开（`lib/sql/sqlCompletion`、`lib/sql/semantic/completion`，QueryEditor.vue:L88-L90） | 触发字符 `$/{`：全局参数/内置时间参数/函数式日期/表字段/关键字（`SqlEditor.vue:L193-L281`） | 不冲突（能力互补） | DBX 语义引擎为基 + 原版变量补全语义吸收（见 §4） |
| 语句切分运行 | 语句边界缓存 + 可执行区间（`useQueryEditorStatementBoundaries`、`lib/sql/executableStatementRangeCache`，QueryEditor.vue:L68） | 选中片段优先，否则全文（`SqlEditor.vue:L499-L517`） | **冲突→DBX 为准**（按语句边界运行） | CM6 语句边界 + 选中优先兼容 |
| SQL 格式化 | 格式化+压缩双操作，按库类型门控（`lib/sql/sqlFormatter`，QueryEditor.vue:L72；跨 tab 重放防护 `QueryEditor.vue:L1-L16`） | Ctrl+Shift+F 格式化（`views/ide/IdeView.vue:L37-L43`） | 不冲突 | DBX formatter + 原版快捷键吸收 |
| 变量语法 | SQL 参数语法开关（`lib/sql/sqlVariableSyntax`，QueryEditor.vue:L75） | `${var}` Monarch 分色 + 补全（`SqlEditor.vue:L47-L108`、`L193-L281`）；后端渲染 `${name}`/`$[date]`/`date(N)`+明文快照（`datara-backend/common/vars_render.py:L103-L154`） | 不冲突（Datara 变量统筹 §3.3 已裁定原版为权威） | 后端 vars_render 语义 + 前端 CM6 高亮/补全 |
| 查询执行 | typed options 执行+多语句批+progress 事件+取消（映射 v2.2 §1 行 1-2） | 异步 taskId+SSE+KILL QUERY 取消+并发池/TTL（`api/ide.py:L57-L75`、`L384-L441`、`L477-L506`） | 不冲突（形态差异：Tauri emit vs Web SSE；语义对齐） | R5-A 17 方法已冻结；取消/批执行按 DBX 语义 |
| 结果分页 | 虚拟滚动+独立分页组件（`components/grid/DataGrid.vue:L11`、`DataGridPagination.vue`，DataGrid.vue:L84） | 内存分页+`/ide/result` 服务端重放分页+页间漂移提示（`views/ide/components/ResultPanel.vue:L85-L149`、`api/ide.py:L538-L615`） | 不冲突（前后端分工互补） | 服务端重放分页（原版架构）+ DBX 网格交互 |
| 数据编辑 | 行级编辑+插入行对话框+DML 预览+危险确认（`DataGrid.vue`、`DataGridInsertRowsDialog.vue`、`lib/sql/dmlChangePreview` QueryEditor.vue:L70、`DangerConfirmDialog.vue` DataGrid.vue:L81） | ExplorerTree 行级编辑能力（`views/ide/components/ExplorerTree.vue`） | 不冲突（DBX 形态更完整） | R5-B 范围，按 A5 议程裁定；提交 SQL 生成细节待精读 |
| 历史与资产 | SQL 历史+文件式保存 SQL（映射 v2.2 §1 行 6-7） | IdeHistory 全文+渲染 SQL+逐条日志 JSON（`common/models.py:L394-L421`） | 不冲突 | R5-A 已含 history/scripts |
| 导出 | CSV/text/xlsx/库导出/表导入导出/Mongo dump（commands `csv_export.rs`、`text_export.rs`、`xlsx_export.rs`、`database_export.rs`、`table_import.rs`、`mongodb_*`） | CSV/JSON/XLSX 流式导出+exported 标记（`api/ide.py:L692-L852`） | 不冲突（DBX 覆盖更广） | R5 范围按 A5 议程裁 |
| 对象树 | database→schema→对象 + ObjectSourceKind 13 类 + DDL 双轨（映射 v2.2 §1 行 8/DDL 行） | ExplorerTree + datasource tree INFORMATION_SCHEMA（`api/datasource.py:L428-L480`） | **冲突→DBX 为准**（对象枚举粒度/只读门控） | R5-A MetaTree 9 类已对齐 |
| 连接管理 | PoolKind 分级+metadata pool+Agent 守护驱动+JDBC 改写+driver_profile 持久化（`commands/connection.rs:L9-L14`、`L82-L105`；`crates/dbx-core/src/connection/` 7 模块） | pymysql 短连接工厂+SELECT 1 测试（`common/dsconn.py:L38-L74`）；数据源中心独立页面（`router/routes.ts:L38-L39`） | **冲突→DBX 为准**（连接池分级抽象/驱动适配层） | Datara 数据源中心保留 UI 形态，池化/能力分级按 DBX |
| 凭证存储 | SQLite Storage 统一存储（`commands/connection_secrets.rs:L1` legacy 空壳注记）；macOS Keychain 仅辅助读取（`commands/keychain.rs:L1-L4`） | 密码明文存储（`common/models.py:L243-L264`） | **冲突→DBX 为准**+Datara 安全基线加严 | 禁明文；存储方案 R6 加固裁定 |
| 执行上下文 | 跨 Schema 注入按库类型分级（映射 v2.2 §1 行 4） | 未发现等价机制（ide.py 无 schema 注入） | **冲突→DBX 为准** | A5 议程已含 |

## 2. 融合点清单（DBX 主导，原版无或弱）

1. 连接池分级抽象（10 类连接池枚举 + metadata 池分离）与驱动适配层（Agent 守护进程/JDBC 配置改写/Mongo legacy 回退——`connection.rs:L25-L105`）。
2. 驱动运行时进程治理：pid/内存/CPU/uptime 监控、可停止/重启（`crates/dbx-core/src/connection/driver_runtime.rs:L9-L39`）——Agent/ExternalDriver/PluginConnection 三类特殊连接的运行时形态（深语义待精读）。
3. 结果网格语义面：key columns/值变换/单元格详情/过滤 builder/列头操作/提取器（`DataGrid.vue:L82-L90` 子组件群）。
4. 数据编辑闭环：插入行对话框+DML 变更预览+危险确认（§1 数据编辑行）。
5. 语句边界执行与执行目标选择器（`SqlExecutionTargetPicker.vue`，QueryEditor.vue:L51；`resolveExecutableSql` L66）。
6. 编辑器工程面：搜索/goto 面板、Intention popup、表结构 Peek 插入、拖拽表名（useQueryEditorTableDrop）、代码快照、Vim 键位（QueryEditor.vue:L12-L62）。
7. 结构对比/数据对比/schema 缓存/全局搜索（commands `schema_diff.rs`、`data_compare.rs`、`schema_cache.rs`、`global_search.rs`）——原版 SQLIDE 无对应能力，登记为 DBX 特色待议。
8. 错误类型化模型（Agent/DuckDB/取消/超时分类，映射 v2.2 §1 行 3）。

## 3. 冲突判定表（D9：冲突歧义以 DBX 为准）

| # | 冲突点 | DBX 立场 | 原版立场 | 判定 |
|---|---|---|---|---|
| C1 | 编辑器内核 | CodeMirror 6 | Monaco+自研 Monarch | DBX；原版 Monarch 语言资产（`datara-sql`、`${var}` 分色规则）作为语义参照移植 |
| C2 | 语句运行粒度 | 语句边界精确切分+缓存 | 选中优先/全文兜底 | DBX 语义为基；「选中优先」作为兼容行为保留提议（A5 裁定） |
| C3 | 对象枚举 | 13 类 ObjectSourceKind+只读门控 | INFORMATION_SCHEMA 库/表/字段三层 | DBX 粒度；R5-A MetaTree 9 类为收敛子集，扩展路径留 A5 |
| C4 | 连接模型 | 池化分级+驱动进程化 | pymysql 短连接 | DBX 池化；短连接形态仅保留在测连场景语义 |
| C5 | 凭证存储 | SQLite Storage（macOS Keychain 辅助） | 明文 | DBX 方向+Datara 安全基线加严，禁明文 |
| C6 | 编辑器交互工程 | composable 巨阵（补全/悬停/拖拽/Vim/诊断） | Monaco 原生能力+轻封装 | DBX 交互语义为准；Monaco 特有能力逐项评估移植成本 |

## 4. 原版 SQLIDE 特色吸收项登记（界面操作层）

1. **悬浮表/视图生成 SQL**：对象悬浮即时产出 SELECT/DDL 草稿（`IdeView.vue:L37-L43`）。
2. **结果 Tab 回显 SQL + 单元格复制**（`IdeView.vue:L37-L43`）。
3. **三快捷键**：Ctrl+Enter 运行 / Ctrl+S 保存 / Ctrl+Shift+F 格式化（`IdeView.vue:L37-L43`）。
4. **结果页间漂移提示**：服务端重放分页时诚实提示数据可能漂移（`ResultPanel.vue:L85-L149`）——数据正确性 UX，必收。
5. **服务端重放分页架构**：历史 SQL 可重放出任意页（`api/ide.py:L538-L615`）——审计与重复查看优势，必收。
6. **`${var}` 变量分色+分类补全**（全局参数/内置时间参数/函数式日期，`SqlEditor.vue:L193-L281`）——变量统筹 §3.3 的前端落点，移植至 CM6。
7. **失败即停+警告收集+取消标记** 执行循环语义（`api/ide.py:L192-L289`）——后端执行语义与 DBX 对齐后保留。
8. **数据源中心独立页面**（`routes.ts:L38-L39`）与 IDE 解耦的 UI 信息架构——保留。

## 5. 命令面全量盘点（DBX src-tauri/src/commands/，77 文件按域分组）

- 执行/取消：query.rs、query_cancel.rs、external_sql.rs、list_sql_files.rs、sql_file.rs
- 连接：connection.rs、connection_secrets.rs（legacy 空壳）、keychain.rs（macOS Keychain 读）、ssh_config.rs、ssh_keys.rs、ssh_prompt.rs、tunnel_profiles.rs
- 资产/历史：history.rs、saved_sql.rs、tab_runtime_cache.rs、global_search.rs
- 导出/导入：csv_export.rs、text_export.rs、xlsx_export.rs、query_result_export.rs、table_export.rs、table_import.rs、database_export.rs、mongodb_import_export.rs、mongodb_dump.rs、sqlite_backup.rs、local_backup.rs、transfer.rs
- 对象/元数据：schema_diff.rs、schema_cache.rs、data_compare.rs、dialect_cmd.rs、document_cmd.rs、docs.rs
- 特殊数据源：mongo_cmd.rs、redis_cmd.rs、redis_pubsub_server.rs、hbase_cmd.rs、mq_cmd.rs、mqtt_cmd.rs、nacos_cmd.rs、etcd_cmd.rs、zookeeper_cmd.rs、external_db.rs、vector_cmd.rs、salesforce_oauth.rs
- AI/MCP：ai.rs、ai_multi_config.rs、agents.rs、mcp.rs、mcp_bridge.rs、mcp_http_server.rs、mcp_native_installation.rs、prompt_template.rs、user_skills.rs
- 插件：plugins.rs、plugin_download.rs、plugin_download_file.rs、plugin_media.rs、plugin_storage.rs
- 壳/平台（**不属于 SQL IDE 能力面，不复刻**）：window_controls.rs、update*.rs、launch_args.rs、deep_link.rs、fs_open.rs、system_fonts.rs、support_info.rs、diagnostics.rs、app_settings.rs、background_image.rs、cloud_sync.rs、config_cmd.rs

## 6. 使用文档面（DBX）

- README/README.zh-CN：产品定位「25MB 驾驭 100+ 数据库；桌面/Docker/CLI；内置 AI 助手与 MCP Server」+ 27+ 数据库徽标清单（`README.zh-CN.md:L2-L49`）。
- docs/：官网工程（Next.js）+ 开发者专题文档（表导入基准、PG 分区表计划、PG 错误定位、MQTT、Mongo 备份恢复、数据安全迁移、后台备份、后端错误处理规范等，`docs/` 目录 Glob 实锚）；**未发现面向终端用户的系统化使用手册**（官网承载）。
- 补充：`commands/docs.rs` 命令存在，疑为内置文档能力，语义待精读。

## 7. 边界与待精读

- 待精读：`commands/docs.rs`、`global_search.rs` 深语义；DataGrid 提交 SQL 生成链（后端侧 commands 对应物）；Agent/ExternalDriver/PluginConnection 深语义（已有进程运行时层锚点）；schema_diff/data_compare 算法深度；原版 `views/datasource/` 页面内部。
- 本文不改变：R5-A 只读边界（U1/U3）、A5 冻结门流程、DBX 不深绑裁定（D4）、主权边界（D6 外部组件零真源化）。
- 评审分工：Codex 评审本清单（P1-7 分工）；裁定项进入 A5 冻结前议程。
