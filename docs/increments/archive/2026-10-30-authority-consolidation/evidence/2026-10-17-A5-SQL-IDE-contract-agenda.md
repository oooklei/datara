# A5 SQL IDE 后端契约议程（Codex 草案）

日期：2026-10-17  
状态：议程草案，未冻结；不修改标准 v3 或 R5 RED/GREEN 状态。  
依据：核心设计 §2、§7.1–§7.3、§13.6；DBX-DS 研读映射 v2.2 §1、§3.2–§3.3；R5-A/B 当前 RED 骨架契约。

## 1. 范围与约束

A5 是后端契约提案，目标是冻结 R5-A 的只读目标数据源能力及 R5-B 的写安全接缝，不代表实现已完成、标准已冻结或任何 GREEN 状态。SQL IDE 与核心 SQL 节点共用数据源、变量解析、执行、日志和统计服务（设计 §2），不得建立第二套 SQL 引擎。FE 只消费后端契约；编辑器补全、校验和页面交互重构留待后端冻结后开展。

此处“R5-A 只读”指不对目标数据源执行 DDL/DML。历史删除、SQL 脚本保存/删除属于项目内平台元数据/资产管理写操作，仍可在 R5-A 暴露，但须受项目授权、审计和资源生命周期契约约束。不得将这些平台资源写入误称为目标库只读违规，也不得以此扩大目标数据库写权限。

设计 §7.1 的对象范围包括 database/schema、table/view、procedure/function；执行附录 §169 扩为九类对象（数据库、Schema、表、视图、字段、索引、函数、存储过程、触发器）及八类操作。DBX v2.2 精读进一步区分：非 table 对象通过 DDL source 文本编辑并按 driver 重写；table 通过独立结构化编辑器生成 SQL；index 是 table 结构子对象。DBX 对象编辑参考不改变 Datara R5-A/R5-B 门禁：R5-A 只读浏览/查询；所有目标库 mutation 只能进入 R5-B 独立审批、差异、备份、人工确认、执行、审计及回滚流程（设计执行附录 §40、§51、§158–169）。

## 2. 契约域议程

### A5.1 项目/数据源上下文与能力等级

- 每次查询须绑定 project、datasource、database/schema/catalog 执行上下文；Backend 校验项目权限和 datasource 授权，不从 FE 的对象树身份推断权限。
- datasource capability matrix 按真实 driver 明示连接、对象类型、跨 schema、异步、多语句、取消、导出和 DDL 写权限；unsupported 必须返回稳定 machine code，不用静默降级。
- DBX 的 datasource type 枚举可作分级参考，Agent/ExternalDriver/PluginConnection 行为仍需单独证实，不默认具备普通 SQL driver 能力。
- 未限定对象名的 schema 注入/重写必须按 driver 显式定义，保护字符串、注释、CTE、quoted identifier 与多语句边界；不能以简单文本前缀实现。

### A5.2 统一变量解析与不可变快照

- SQL 文本中的 `${scope.name}` 与 `$[时间表达式]` 使用 R2 共享变量解析服务，复用命名空间、优先级、类型、权限和错误合同；编辑器补全/实时值预览留给前端阶段。
- 执行前服务端解析并生成不可变 snapshot，至少记录 snapshot id/hash、执行尝试、每项表达式/命名空间/变量名/解析值/类型/来源/解析时间（设计主文 §5，`task_instance_variable_runtime`）；同一快照须由 execution、分页结果、history/audit 和 export 引用，保证重放时不读取“当前值”。FE 可取得快照身份与允许展示的元数据；原始秘密值不得通过普通响应、日志、历史或导出元数据泄漏。
- 未定义、越权、类型不兼容、循环引用和秘密变量回显应有机器可判定错误；密码类值不得进入普通响应、SQL 历史、日志或导出元数据。
- 变量解析必须先于任何目标 SQL 执行；校验失败则整次请求 fail-closed，不执行未经完整解析的 SQL。原始 SQL 和解析后 SQL 的存储、哈希及可见范围应按权限分开定义。
- 变量快照持久化和生命周期必须复用 R2 的冻结模型，不在 A5 另造实体/解析优先级；R2 快照查询若未实现，A5 明确列为依赖缺口而非伪造查询能力。

### A5.3 执行、异步、取消与进度（DBX 异步特例）

- DBX `execute_query` 提交后台任务并以 oneshot/超时返回，`execute_multi` 可发进度事件；这不是 HTTP 后端持久化任务、SSE 恢复或 durable replay 的证据。Datara API 需单独定义 `executionId`、状态机、提交响应、轮询/事件恢复、取消、超时、错误和重试语义。
- FE 冻结入口是 `executeSql -> {taskId}`、`cancelExecution(taskId)`、`fetchResultPage(historyId, stmt_index, offset, limit)`；`openEventStream(taskId)` 必须保留同步 `(taskId: string) => EventSource` 签名。taskId/historyId 的 wire 类型与 FE 的 `wireIdToString` 归一规则须写清，不得以不兼容改签名掩盖后端差异（GREEN 接线计划 §298–322；FE 适配层设计 §2.5）。
- 多语句至少冻结 `use_transaction`、`continue_on_error`、`table_data_preview`、`result_key_columns` 对应语义；逐语句产生结果与错误，区分已提交、回滚、跳过、尚未执行；定义首错/部分成功、事务与继续执行的优先级、取消时事务回滚及 driver 支持边界。DBX 源码锚：`D:\dbx-main\src-tauri\src\commands\query.rs:174–289`（`execute_multi` 参数和进度），`query.rs:91–170`（异步查询）；映射见 DBX-DS v2.2 §1。
- R5-A 的结果读取需冻结任务状态终态、状态查询/事件的权威关系、事件顺序、重复帧处理、取消竞态、数据库 cancel/kill 与连接回收、超时类别和重试安全边界。不能仅凭 DBX Tauri tokio task 声称 Datara 后端任务持久或可恢复。
- SSE 逐项冻结事件名、字段及错误：`SqlLogEvent`（日志序号/时间/级别/消息及可选结构化错误）、`SqlResultEvent`（execution/history 标识、语句索引、结果集标识、列/分页元数据/数据引用）、`SqlDoneEvent`（终态、语句汇总、耗时/错误）。确切字段必须与 FE `sqlIdeApi.ts` 类型对照并逐字段签认；结构化错误 `{code,category,stage,retryable}` 与旧 `error?: string` 的承接方式属于 D6，不能静默损失分类。契约源锚：GREEN 接线计划 §310–322；FE 适配层设计 §2.5、Q10/Q11 跟踪项。
- 认证不得把 bearer token 放进 URL、localStorage 或 sessionStorage。浏览器原生 EventSource 不能自设 Authorization header，因此须冻结安全传输方案（如短时、绑定用户/项目/执行的 stream ticket 或同源认证代理），并说明签发、单次/时效、撤销及日志屏蔽；在该方案确认前 `openEventStream` 保持 RED。FE 现有 `?token=` 示例仅是未冻结草案，不能覆盖设计 §13.6 与 FE 适配层设计 §2.5 R5.5 的凭据安全边界。
- 心跳、事件 id/sequence、断线后重连、恢复游标、重放起点、重复帧与保留期必须一起冻结。FE 的消费面使用 `SqlLogEvent/SqlResultEvent/SqlDoneEvent`；若 BE 采用其他帧形式，FE service facade 提供 EventSource 兼容门面并保留同步签名。不得预设 `Last-Event-ID`、query token 或 durable replay；有恢复承诺时须有后端持久状态/重启证据（FE 适配层设计 §2.5 R5.1–R5.5、§5 Q9）。
- 结果统计统一记录 source rows、affected/inserted/updated/deleted、warnings、failed statements 与 elapsed time；源和目标计数不可混用。

### A5.4 查询结果网格与多结果集

- 设计执行附录 §173 要求多结果集、分页、虚拟滚动、筛选、排序、行详情、JSON 展开、复制、CSV/JSON/Excel 导出、结果转图表及结果保存为数据集；后两项也是 R5-A 必验能力，不能以“表格 API 可用”代替。
- Backend 负责稳定列元数据、结果集及语句边界、分页/cursor、精确/估算/未知行数含义、截断标记、key columns、类型/NULL/大对象序列化和有界存储；展示交互由 FE 消费。FE 当前 `fetchResultPage(historyId, stmt_index, offset, limit)` 请求形态见 GREEN 接线计划 §302–307；A5 应明确如何映射到设计 §13.6 的 execution/result-set/page/storage 引用协议。
- 大结果导出与交互页分页必须共享同一 execution snapshot；响应中声明精确/估算/未知行数，不把估算写成精确总数。
- 结果落临时项目运行存储，须有 TTL、分页连续性、最大行/字节限制及清理；取消后状态必须落为 `CANCELLED` 或 `CANCEL_FAILED`（设计 §13.6），不能无限驻留内存。

### A5.5 SQL 历史与 SQL 资产

- R5-A FE 的 5 个方法为 `listHistory/deleteHistory/listScripts/saveScript/deleteScript`；冻结每个方法的项目/用户隔离、分页/搜索、排序、清理、字段键形和错误。SQL 脚本保存/删除是平台资源写，不执行目标 SQL。
- 历史与命名 SQL 资产是不同实体：历史是执行证据，资产是可复用用户内容，不合并生命周期。历史应明确保存原始 SQL、状态、耗时、数据源/项目引用、执行快照引用及保留期；不得保存凭据或秘密解析值。命名资产须明确项目级文件夹/查询资源、revision、冲突、删除/恢复、权限及审计。
- DBX 源锚：`D:\dbx-main\src-tauri\src\commands\history.rs:7–55`（保存/加载/搜索/清理），`commands/saved_sql.rs:62–100`（文件式查询/文件夹 load/save/delete）；A5 参考其资源形态，不照搬 Tauri 文件系统存储为 Datara 后端真源。

### A5.6 导出

- 覆盖当前结果集导出与大表/表数据异步导出两条路径；明确格式/编码、文件大小/行数上限、权限继承、取消、失败清理、过期清理、审计与下载授权。表数据导出与查询结果导出不能共用含混状态/取消语义。
- DBX 查询临时导出仅 xlsx/html、表数据异步导出+取消+未完成清理；Datara 是否支持 CSV/JSON/Excel 按设计 §7.3 定义，不把 DBX 当前格式限制误当成产品要求。
- 任何导出必须绑定原查询/表、项目、数据源及执行快照；秘密列、脱敏策略和下载授权由 Backend 再检查。

### A5.7 对象浏览与 DDL 写入分界

- R5-A：对象树、列元数据、只读 DDL/source 读取、查询与结果均只读；无 DDL 执行、表结构保存、routine 修改。数据库→Schema→对象列表及对象过滤/分页按能力返回；函数/过程/触发器等非 table 对象的 source-kind 列表与 driver 只读限制需在矩阵中体现。
- R5-B/写阶段：非 table 对象使用 source editor + driver-aware SQL rewrite；table 结构化编辑与 SQLite rebuild 等 driver 特例需独立 contract。DBX 已证明有生产 SQL guard 和 editable gates，不能据此跳过 Datara 的人工确认、授权、风险确认及审计。
- capability gate 必须拒绝只读对象/driver 的写入，包括 DBX 源码已标出的 Event、部分 Trigger、OpenGauss Package/PackageBody 等限制。DBX v2.2 的 `ObjectSourceKind` 13 种类型不含 table/index；table 结构化编辑和 SQLite rebuild 独立，不得以非 table source editor 代替。
- table structure editor 是否纳入本轮 R5-A/R5-B 验收，受用户 U3/G3 裁定；当前议程先保留为待裁定项。

## 3. DBX 能力与前端契约逐项覆盖

L314 的七项能力是数据源能力分级、查询编辑、结果网格、SQL 历史、SQL 资产、异步执行、数据导出；DBX-DS v2.2 §3.2 补跨 Schema、对象树和对象 DDL 双轨，且旧版 SQLIDE 融合对照依 S1 单独登记。DBX 是行为参考，Datara 的后端权限/审计/执行边界仍由 Datara 设计决定。

旧版 SQLIDE 与 DBX 的融合审议应逐项记录：旧版行为/交互、DBX 源码证据、Datara 后端是否需要承接、保留或舍弃原因、驱动/权限边界及验收证据。发生冲突时 DBX 行为优先；只有不削弱 DBX 能力和后端安全契约的原版界面优势才进入后端契约/后续前端设计输入。当前草案尚未完成旧版 SQLIDE 的逐项比较，因此该比较是冻结门，不将旧版行为当作验收正本。

R5-A 恰为 17 个 FE 方法，锚于 `docs/increments/2026-10-17-R系列GREEN接线计划.md:298–322`；R5-B 恰为 5 个 FE 方法，锚于同文件 `:324–342`。不要将 R5-B 写成 4 方法，也不要把 A5 SSE 未冻结时的 17 方法整体记为 GREEN。

| DBX 能力 | A5 Backend 议程 | R5-A/B 期待面 | 冻结所需证据 |
|---|---|---|---|
| 数据源能力分级/元数据 | `listDatabases/listSchemas/listRelations/listColumns/listRoutines/listIndexes/searchObjects`（7） | 项目/数据源授权、catalog/schema 上下文、数据库→schema→对象树、列/例程/索引浏览、分页/filter、driver capability 和 unsupported code | GREEN 接线计划 §298–307；DBX `crates/dbx-core/src/connection/mod.rs:106–145`; `schema/mod.rs:652–728,975–1010,1107–1131` |
| 查询编辑/执行/校验 | `lintSql/executeSql/cancelExecution/fetchResultPage`（4） | 查询上下文、限额/超时、类型化错误、异步 task、取消、分页及多语句语义 | GREEN 接线计划 §302–307；DBX `src-tauri/src/commands/query.rs:33–89,91–170,173–289` |
| SQL 历史 | `listHistory/deleteHistory`（2） | 历史资源/分页、项目用户隔离、删除与执行证据留存策略 | GREEN 接线计划 §305–307；DBX `commands/history.rs:7–55` |
| SQL 资产 | `listScripts/saveScript/deleteScript`（3） | 项目文件夹/查询资产、权限、revision/冲突；平台资源写不等于目标库写 | GREEN 接线计划 §305–307；DBX `commands/saved_sql.rs:62–100` |
| SSE 异步进度 | `openEventStream(taskId)`（1） | 事件字段/顺序/错误、认证、安全票据、心跳、断连/恢复/重放 | GREEN 接线计划 §307–322；FE 适配层设计 §2.5；待 A5 逐字段冻结 |
| 结果网格/多结果 | `fetchResultPage` + `SqlResultEvent` | 多结果集、key columns、preview、分页、截断、筛选/排序/虚拟滚动/详情/JSON/复制、图表、数据集保存 | 设计执行附录 §173；设计 §13.6；DBX `query.rs:173–289` |
| 导出 | FE 17 方法清单当前没有专用 export 方法 | SSE/结果页的导出句柄或独立 endpoint 需在 A5/B2 明确；区分临时结果 xlsx/html 与异步表导出/取消/清理 | DBX `commands/query_result_export.rs:16–40`,`commands/table_export.rs:22–71`; 设计执行附录 §43, §173 |
| 跨 Schema | 执行上下文 + 元数据查询 | 按 driver 处理 catalog/schema 与未限定对象名；禁止不安全字符串拼接 | DBX `crates/dbx-core/src/query/mod.rs:894–1064,2165–2266` |
| 对象浏览/source | `listRelations/listColumns/listRoutines/listIndexes`；R5-B `getDefinition` | R5-A 只读对象/source；ObjectSourceKind 13 类；table/index 独立结构轨道 | DBX-DS v2.2 §1；DBX `dbx-types/types.rs:209–233`; `schema/mod.rs:10635–10659,10714–10722,10910–10937` |
| DDL 安全写入 | R5-B 五方法 `getDefinition/validatePolicy/previewImpact/submitConfirm/listExecutionRecords` | 8 步安全流程、block/warn/info、确认短语只来自用户、审计和补偿；R5-B 单独人工闸 | GREEN 接线计划 §324–342；设计 §13.6；执行附录 §40, §51, §158–169 |

## 4. 冻结门与待裁定项

冻结前须：①对 R5-A 17 与 R5-B 5 个方法逐项给出 request/response/error/status/durability 映射；②补全对象×driver×操作能力矩阵，区分 source read/editor capability 与 Datara write authorization；③确认不可变变量 snapshot 与 execution/history/result/export 的引用关系；④冻结多语句逐条结果、事务、部分成功、取消和异步状态；⑤逐字段签认 SSE 事件、安全认证及重连/恢复；⑥落实结果网格图表/数据集和导出句柄；⑦补集成级和真实控件验收证据。源码矩阵与 R5 contract review 仍在并行复核，矩阵完成后回填来源与未证实项。

待外部裁定/闭环：DDL 分阶段 U1；对象编辑范围 U3/G3；R5-A 与 R5-B 写入闸门；SQL IDE 写操作的人工确认语义；支持 driver 与导出格式范围；旧版 SQLIDE×DBX 逐项融合比较；以及标准 v3 S3 `parameterPassing`“变量引用替代”与 A2 §7.6 独立透传语义的冲突。此草案不替代这些裁定。

## 5. 标准 v3 对标状态

本草案遵循标准 v3 §0（用户原文优先）、S1（DBX 优先参照及原版 SQL IDE 融合议程）、S3（统一变量解析）、S4（DBX 九能力与跨 Schema）、A1-A7/O7 源码证据要求；落实设计 §2 共享执行/变量服务、§7.1–§7.3 对象/跨 Schema/结果网格、§13.6 查询与 DDL 分界。差异/未闭合项如 §4 所列；未获用户裁定/契约会签前不宣称冻结或 GREEN。
