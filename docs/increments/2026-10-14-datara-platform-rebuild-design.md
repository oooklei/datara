# Datara 平台重建设计（评审修订版）

> 唯一权威设计文件：`docs/increments/2026-10-14-datara-platform-rebuild-design.md`；`docs/superpowers/specs/2026-10-14-datara-platform-rebuild-design.md` 仅为 superseded 历史副本，冲突时以本文件为准。
> 版本：2026-10-14；编号体系：R0-R11；运行资源：192.168.1.9；默认时区：Asia/Shanghai（UTC+8）。
> 本文是重建域的设计基线。正式前端功能继续冻结，隔离验证页只调用新 Backend API；菜单展示层 D-1=B 豁免见 §1.2。验证门禁不要求操作前端登录页；测试运行环境使用统一验证 key 经 Backend 认证 API 取得短期 token，再驱动业务控件。

## 1. 范围、真源与边界

### 1.1 重建域

重建域包含身份与项目、数据源、工作流定义/DAG、任务执行、调度、实例/日志/指标、变量、SQL IDE、同步、流运行时、治理资产和 AI 工具契约。治理资产不是空架构：`metadata` 是资产目录与 schema 快照真源，`lineage` 是表级/字段级解析结果真源，`quality` 是规则/运行/异常结果真源，`data_asset` 是资产引用与标签聚合真源，`data_transfer` 是同步探查、映射和执行记录真源。OpenMetadata/DataHub 可作为外部导入源，但不与自研表争夺写入真源。

### 1.2 菜单展示层豁免

按用户裁定 D-1=B，保留 App.vue“同步任务”“数仓建模”归组和 routes.ts `/std/*` 去 demo 三项展示层变更。豁免只覆盖菜单分组、入口和路由元信息；正式页面功能、mock 数据和业务交互仍冻结，必须通过新 Backend 契约与隔离验证页后再融合。

### 1.3 设计依据与前端验证边界（本次裁定）

- 新 Backend 与隔离验证页的功能/交互基准来自对应成熟系统的开发文档、用户文档、源码实现及其前端真实页面（按功能选择 DBX、Apache DolphinScheduler、Vanna、OpenMetadata/DataHub 等）；每个增量先形成“目标能力—来源文档/版本—源码模块/契约—参考前端页面/表单/用户操作流—Datara 新 Backend 适配—可验证场景”对照表。测试页须复现参考产品的关键业务步骤和表单语义并调用 Datara 新 API；不得以旧 Datara 页面为模板，也不得退化成 API 按钮面板。
- Datara 旧前端只在全部新 Backend 契约冻结并通过各增量验收后，进入重建计划之外的前端融合阶段；既有页面、mock、旧 API 可用于资产盘点/兼容性分析，但不得作为新 Backend 的行为真源，也不得提前改造正式页面。融合阶段不新增或改写 R0-R11 编号。
- 隔离验证页是临时、独立的 Backend 验收客户端，不是旧 Datara 产品原型复制，也不是 API 按钮面板。页面布局、字段分组、步骤顺序、探查/校验/预览/运行/结果反馈等交互，以本增量对应参考产品真实前端为蓝本；表单字段和动作绑定新 Backend API/schema，并预置非秘密测试数据。不得复制参考产品代码或无关品牌视觉。
- 登录认证与业务控件验收分离：R1 提供受保护的 token 签发契约（建议 `POST /auth/token`）；测试运行环境持有统一验证 key，认证 API 校验 key 并映射到受限测试身份/权限范围，签发短期 token，再由受控自动化上下文注入隔离验证页。页面不显示登录表单、不持有验证 key，仅使用短期 token 调用受保护业务 API。不得要求人工点击登录页作为每个增量门禁，不得增加绕过鉴权的公开业务 API，不得把 key、账号口令或 token 编译进静态 HTML/JS 或写入截图、证据、仓库。key 与 token 不落业务日志；签发接口纳入 R1 的认证/授权、过期、撤销和越权测试。
- browser-use 优先；发生已记录的控件桥阻塞时，按 R2-14 用 Playwright 操作同一隔离验证页。两者均验证真实 UI 控件及其后端效果；纯 API/HTTP 检查只作辅助，不替代前端牵引门禁。

## 2. 评审修复矩阵（15 项）

| 编号 | 评审问题 | 冻结设计与实现边界 | 验收证据 |
|---|---|---|---|
| R2-01 | 治理域有名无实 | 明确 data_asset/metadata/lineage/quality/data_transfer 五域模型、采集/解析/规则/同步边界；自研元数据为内部真源，外部平台只做导入适配 | 五域 API/表模型矩阵、表级+字段级血缘样例、质量规则执行样例 |
| R2-02 | 调度语义缺失 | cron、手动、依赖、补数四种触发；Asia/Shanghai；misfire=skip/fire_once/catchup；concurrency=allow/forbid/queue；优先级、重试、超时、告警和 worker 执行模型写入契约 | schedule policy、命令、实例 `schedule_time/generated_at` 与终态日志 |
| R2-03 | 权限模型缺失 | 最小 RBAC：user/role/permission/project_member；权限点覆盖定义读写、运行、数据源、IDE DDL、治理写、AI 查询；行/列权限作为 datasource policy 执行边界，内部系统不做敏感值脱敏设计 | token、成员、权限拒绝/允许矩阵和数据范围断言 |
| R2-04 | DDL 写路径无管控 | 表/视图/函数/存储过程/触发器编辑拆为 draft→差异→备份点→发布；默认 dry-run，显式确认后执行；记录操作者、SQL hash、目标 schema、前后定义、回滚脚本 | DDL 审计记录、拒绝危险语句、备份/回滚演示 |
| R2-05 | 变量类型系统缺失 | string/number/boolean/date/datetime/array/object 六类；global/workflow/task/runtime 四级作用域；Asia/Shanghai 解析 `$[yyyy-MM-dd]` 与 offset；tmp 仅实例生命周期；输入校验、补全、现时值和运行快照均为同一 VariableService | 类型不匹配、补全列表、现时值、任务日志变量输出和实例快照 |
| R2-06 | 实时流运行时空白 | Kafka 为标准 MQ；STREAM 是长驻 job，不复用一次性批实例终态语义；独立 stream_job/stream_attempt/offset/heartbeat，启动/停止/漂移/恢复/位点提交有状态机 | Kafka 生产观摩工作流、停止/重启续位点、心跳/指标/日志 |
| R2-07 | SQL IDE 结果集协议缺失 | 异步 task 返回 taskId；结果落临时结果存储并带 TTL，分页 cursor/offset、列元数据、rowsTotal、截断标记、导出句柄；取消映射数据库 KILL/连接回收；禁止无上限驻留 | 大结果截断、分页连续性、取消、导出和过期清理证据 |
| R2-08 | 部署拓扑缺失 | 192.168.1.9 compose：api/master/worker/alert/logger + MySQL/Redis/ZK/Kafka/Web；配置来自 env/.env.example，日志统一卷和 health；本机不启动运行资源 | compose config、health、容器依赖、日志卷和环境变量清单 |
| R2-09 | AI 契约游离 | AI 只调用冻结 Backend 工具：inspect_workflow_run、get_task_metrics、get_lineage、query_catalog、explain_sql；工具 schema、权限、审计、预算、超时进入模块契约和冻结门禁；AI 为全系统浮动图标，不增加菜单项 | tool schema、拒权、审计和确定性回答样例 |
| R2-10 | 验收无量化基线 | API P95≤500ms（不含执行）、IDE 首屏≤2s、调度触发延迟≤10s、批任务指标完整率100%、流观摩吞吐/延迟按测试数据记录；证据统一落 `docs/increments/evidence/Rn/` | 带时间戳的 JSON/日志/截图索引与实测数字 |
| R2-11 | SYNC 执行器缺失 | SYNC 纳入 catalog、master dispatch、scheduler/failover 和 worker executor；全量/增量、断点、批提交、映射计划和行级 metrics 同一执行链 | sync executor 单测、探查映射调整、真实工作流成功/失败行数 |
| R2-12 | datasource 前置缺失 | 先完成 datasource CRUD、连接测试、schema/table/column 探查、连接池/超时；SQL、同步、IDE、治理和变量补全均只引用 datasource service | 数据源连通/失败、跨 schema 树、SQL/同步共享连接契约 |
| R2-13 | 测试数据库供给缺失 | 运行测试库由 192.168.1.9 compose 的 MySQL schema 提供；本机只做 SQLite/fixture 逻辑测试，真实 MySQL 方言、默认时间戳和数据行统计必须远端验证 | schema 初始化、默认 CURRENT_TIMESTAMP、探查和对账证据 |
| R2-14 | 每增量浏览器门禁、登录前置与控制桥阻塞 | 每个后端增量配独立验证页/路由，不注册正式菜单；用测试身份经 Backend auth API 获取短期 token 后直接驱动业务控件，登录页人工点击不是门禁；R1 单独验 auth/RBAC。browser-use 优先，控件桥一次有界重试仍阻塞即 Playwright 驱动同页真实控件；API-only 不替代 UI，Playwright 失败才 BLOCKED_BROWSER | Token 获取来源/有效期、真实控件操作、后端状态、截图（无凭据）、API/日志/资源证据；流程见 `.agents/skills/browser-use-playwright-fallback/SKILL.md` |
| R2-15 | SQL IDE 单增量过大 | 拆 R10-A 只读：浏览、补全、查询、历史、结果分页、导出；R10-B 写路径：对象编辑、差异、备份、发布、回滚、DDL 权限。二者分别设计、实现和验收 | R10-A/R10-B 两份验证单，写路径不得混入只读门禁 |

## 3. 身份、调度和运行表统一契约

所有运行记录表至少拥有数据库生成的 `created_at`、`updated_at`、`generated_at`；实例、任务、attempt、command、task_log、output、variable_runtime、data_stat、workflow_run_metric、stream_attempt 均不得由前端伪造时间。上海时区用于业务解释，数据库时间戳保存实际生成时刻；API 同时返回 ISO 字段与显示时区。

一次性 DAG 以 workflow_instance 为主链；STREAM 以 stream_job 为主链，允许多个长驻 attempt。每次触发在 command→instance→task_instance→task_log/output/data_stat/metric 之间保留 instance_id、trigger_source、origin_instance_id 和 generated_at 关联。

## 4. 变量规范

变量编辑器统一使用 SQL IDE 风格的 token 补全：输入 `$`、`${` 或 `$[` 时按作用域、类型和可见项目返回候选；选中候选展示名称、类型、来源和现时值。保存/运行前执行类型、作用域、是否允许延迟求值、日期格式和引用存在性校验。任务日志允许输出本次运行解析后的变量键值及来源；内部系统按用户裁定不做敏感值脱敏分支。

## 5. 治理与 AI 真源

### 5.1 五域模型、写入责任与真源

| 域 | 规范对象/责任 | 写入生产者 | 内部真源与外部边界 |
|---|---|---|---|
| `metadata` | 数据源、schema、表/视图/函数/存储过程、字段、描述、采集批次与快照 | datasource 探查器、周期采集器、受控导入器 | Datara 的治理 schema 保存目录和快照；OpenMetadata/DataHub 仅作为可追溯导入源，不直接成为工作流执行状态或元数据写入真源 |
| `data_asset` | 统一资产身份、项目归属、标签关联、质量/血缘/指标导航引用 | 资产目录服务、导入映射器 | 内部 `asset_id` 与外部 `(source_system, external_id)` 映射是关联真源；外部原始 ID 不覆盖内部主键 |
| `lineage` | 作业/SQL/同步映射产生的表级及字段级 upstream/downstream 边、解析来源、置信/状态 | SQL/工作流解析器、SYNC 执行器、显式校正 API | 内部 lineage edge 与字段边保存解析结果；源 SQL/映射版本及解析批次保留，解析失败不得伪造边 |
| `quality` | 规则定义/版本、运行、输入输出计数、异常样本引用与状态 | 规则服务、Quality worker | 新治理 API 的规则和运行历史为重建域真源；旧 `Qc*` ORM/表保留作为旧资产迁移输入，不再由退役的 `/api/v1/qc/*` 写入 |
| `data_transfer` | 同步端点、探查 schema、字段映射版本、全量/增量计划、checkpoint、运行及成功/失败/跳过行数 | datasource 探查器、SYNC 编排器/执行器 | 新 Backend 记录映射与执行状态；外部传输工具仅作为执行适配器，不能绕过 Datara instance/metrics 留痕 |

数仓建模、指标、标签、标准、质量、血缘、权限和审计的旧 I18-I23 资产统一先盘点，不在本设计阶段静默删除。`DwModel*` 是建模/关系/版本迁移候选；`MetaTableExt/MetaTag/MetaTagging` 是目录/标签候选；旧 `LineageEdge/LineageField` 与 `Qc*` 是血缘/质量候选。指标、标准、访问授权及操作审计按各自旧表/API 的实物清单映射。处置默认如下：语义相同则经 source-id、行数、字段映射及幂等核验后迁移至新域；仍被旧运行链路引用则暂时冻结只读；无消费者且无业务数据的历史实现，在用户批准和回滚窗口后废弃。任何一项在表/API/菜单/消费者清单核完之前都不标“已迁移”或“已废弃”。`Qc*` ORM/表保留，旧 QC API 已按批次 1 退役；治理 API 和数据仍可审计。

### 5.2 I18–I23 规范化承接模型

用户于 2026-10-14 明确裁定方案 A：扩展新 Backend 的规范化模型并完整承接旧 I18–I23 业务语义。旧库继续只读；源记录只允许迁入隔离目标 `datara_rebuild_i0`，且须先快照、dry-run、逐表/逐关系核对后才允许执行。现有 R3 通用表保留并演进，不以 `properties_json`、拼接文本或单一快照 JSON 替代可查询、可授权、可建立关系的业务实体；JSON 快照仅用于原始证据/历史差异辅助。

| 旧域与语义 | 新规范化实体（名称为契约候选，迁移前需在 R3-S9 冻结物理命名） | 关键关系与保真要求 |
|---|---|---|
| I18 业务域、数仓分层、引擎字典 | `governance_domain`、`warehouse_layer`、`model_engine` | 按旧自然键保留源 ID 映射、名称、规则/方言、排序与启用状态；模型引用均以新主键关联。 |
| I18 模型、字段、ER 关系、版本 | `warehouse_model`、`warehouse_model_field`、`warehouse_model_relation`、`warehouse_model_version` | 保存模型状态/版本/目标数据源/schema、画布坐标、字段类型精度/可空/默认值/主键/分区/字典引用、关系两端字段与关系类型、每个历史版本完整快照/变更说明/作者/时间；关系字段从 JSON 文本解析为规范化关系字段行，同时保留原始字段载荷供审计。物化 DDL 作为历史文本留档，不自动重放。 |
| I19 元数据扩展、标签与挂接 | 现有 `asset`/`asset_field`/`tag`/`asset_tag` 加 `asset_metadata_extension` | 旧 `(ds_id, db_name, table_name)` 对齐统一 asset identity；业务域、owner、备注等扩展落专表；保留标签分类/颜色/说明和 target_type/target_key 关联，无法解析的旧 target 保留 unresolved 映射，不丢弃。 |
| I20 指标及版本 | 现有 `semantic_metric` 加 `semantic_metric_version`、`metric_dimension` | 规范化指标代码/名称/类型/业务域/业务定义/技术定义/来源类型与引用/字段/输出表/任务/统计周期/维度/单位/状态/当前版本；保留版本快照、变更说明、作者和时间。 |
| I21 质量规则、任务、任务规则关系、运行、异常、报告、告警 | 现有 `quality_rule`/`quality_run` 加 `quality_task`、`quality_task_rule`、`quality_exception`、`quality_report`、`quality_alarm_policy` | 保留旧 cron/enabled/状态/最近运行、规则集合及顺序、触发方式/起止时间/结果/分数/统计、异常目标/样例 SQL/命中数/处理状态、报告范围/周期/内容、告警指标/运算符/阈值/启用与触发时间。旧 QC 执行 API/engine 仍退役；本模型承接历史业务记录与新治理 API，不恢复旧 `/api/v1/qc/*`。 |
| I22 标准元素、码表/码值、命名规则、映射、审批、校验报告 | 现有 `standard` 加 `standard_element`、`standard_code_set`、`standard_code_value`、`standard_naming_rule`、`standard_mapping`、`standard_approval`、`standard_check_report` | 保留中英文名称、数据类型/长度、标准状态/版本/负责人、码值编码/名称/顺序、命名表达式及适用对象、映射目标/元素或码表/差异状态、审批业务类型/动作/申请载荷/意见/状态/时间、检查范围/汇总/问题清单/结果。码值与父码表建立 FK，映射到标准元素/码表建立可空 FK；历史审批目标保留 source identity。 |
| I23 用户及全局角色/权限映射 | 既有 `rebuild_user`/`rebuild_project_member` + `legacy_identity_mapping` | `t_user` 记录登录名、角色和状态；保留稳定源 ID 并逐项映射旧静态角色权限至 R1 已冻结的 `Role/Permission/ROLE_PERMISSIONS` 契约，不另造动态 RBAC 真源。只有在完整源盘点找到旧项目绑定记录时才迁移项目成员关系；否则不伪造历史成员关联。凭据仅在算法/格式兼容并通过验证时迁移哈希，否则走重置，不迁移明文口令。不将旧身份表作为新 Backend 运行时真源。 |

所有迁移实体统一附 `source_system`、`source_table`、`source_id`（组合唯一）、`migration_batch_id`、`created_at`、`updated_at`、`generated_at`；业务记录按本体保存原创建/更新时间，`generated_at` 表示新系统迁移/生成时点，批次时间单独记录。目标表使用外键、唯一约束及稳定自然键；多对多关系拆为关联表。源表主键仅作为来源键，不复用为目标主键。迁移项保存源/目标键、状态、校验摘要、错误及重试次数，保证可重入、可定位、可回滚。每表校验精确行数、字段规范化摘要、源 ID 覆盖率、关系条数、孤儿数、版本/审批链完整率与时间戳；目标不得少于任一来源记录，冲突必须显式报告，不可静默覆盖。迁移前做目标 schema 快照；回滚只能删除本迁移批次拥有且未被新业务引用的目标记录，绝不触碰旧库。

迁移排序：身份与项目键映射 → 字典/资产身份 → 模型及字段/关系/版本、元数据扩展/标签 → 指标及维度/版本 → 标准元素/码表/码值/规则/映射 → 审批/校验报告 → 质量规则/任务关联/运行/异常/报告/告警 → 全域关系与总量核对。用户/角色数据映射先 dry-run；遇到登录名冲突、项目归属不唯一、权限点无目标或凭据算法不兼容时停止对应记录组，保留已提交的无关组并提交裁定，不进行猜测合并。

### 5.3 采集、解析、规则执行边界

- 元数据采集按 datasource 授权读取 schema/table/column 及对象定义，保存采集时间、数据源版本、对象指纹与失败明细；增量采集允许 tombstone 标记，但不自动物理删除历史资产。
- 血缘解析器消费 SQL、工作流版本和 SYNC 映射版本，先产出可审阅的解析批次，再发布表级/字段级边；来源不明、动态 SQL 无法解析、字段映射不完整时保留 `unknown/unresolved`，并记录原因，不猜测下游字段关系。
- 质量规则定义与执行分离；执行快照绑定规则版本、数据源/资产、时间窗口、运行实例及输入/成功/失败/跳过行数。异常可引用样本位置或主键，默认不复制整行数据到治理库。
- `data_asset` 是导航聚合和稳定内部身份，不复制成 metadata/lineage/quality 的并行事实表；标签、标准和指标通过稳定 asset identity 关联，各子域保留本域版本和审计。
- 元数据训练可纳入数仓 schema、对象定义、字段注释、标准/指标及经授权的样例数据摘要；需要保留 source、采集时间、权限范围和来源对象版本。AI 检索只读取授权后的目录/血缘/规则资料，不把模型答案回写为正式元数据，除非用户通过对应编辑接口确认。

外部平台导入必须具备 adapter、source identity、字段映射版本、dry-run 冲突报告、幂等键、导入计数和回滚方案；外部更新不能覆盖 Datara 本地人工校正或工作流/运行状态。内部首期不做敏感值识别、脱敏、密级驱动隐藏或加密展示分支。

AI 不添加左侧菜单项，采用全系统浮动助手图标和上下文入口；工具面与普通 API 同步冻结，回答必须给出对象、来源时间和失败原因，不能替代执行确认。

## 6. 设计冲突裁定记录

### D-R3-S8：I18–I23 旧资产承接策略（2026-10-14）

- 冲突事实：R3-S8 只读盘点发现新治理 schema 缺少旧 I18 模型版本/关系、I20 指标维度与版本、I21 质量任务/异常/报告/告警、I22 标准码值/审批/命名规则/映射/检查报告等可查询关系模型；旧 I18 有 45 行、I22 有 3 行，通用 `properties_json` 不能证明无损表达。详细证据见 `evidence/R3/s8-source-inventory-20261014.md`。
- 影响范围：R3 governance ORM/migrations/API、R3-S9 迁移器与 parity 检查、隔离验证页、R2-01 治理域状态以及依赖这些实体的 R5 lineage、R6 治理目录/质量/标准、R11 AI 工具；旧库保持只读，正式前端仍冻结。
- 候选方案：A. 扩展新 Backend 规范化模型并完整承接；B. 旧治理库长期只读，重建域延期承接。
- 用户裁定：A，批准扩展新 Backend 规范化模型、更新设计/计划后完整承接；不需要对本裁定重复征求批准。
- 执行边界：新增和迁移仅面向隔离 `datara_rebuild_i0`；需先提交 S9 影响分析，做目标快照/dry-run/逐表逐关系 parity 和回滚设计，再实施。不得改写或删除旧表/旧 API，不恢复已退役 QC router/engine，不触碰正式前端；如身份键、权限映射、重复业务键或无法解析关系存在未决冲突，停止对应记录组并将证据留台账。
- 一致性要求：同一批准和实体清单同步回写实施计划、R3 状态、执行台账；设计/计划/台账的模型范围与验收阈值必须一致。

## 7. 实测基线回写

截至 2026-10-14 Asia/Shanghai，后端全量回归最近一次为 `584 passed / 60.91s`（含 QC 权限回归断言）；QC 退役后上一轮全量为 `583 passed / 65.47s`。R3 governance runner 专项 `4 passed / 0.12s`，QC 退役控件级 Playwright `21/21`、浏览器错误 `0`。远端 `datara-api` health `UP`，数据库/Redis/ZK 均健康，QC OpenAPI routes `0`、标准 routes `24`，重建治理 API `11` routes healthy，六张旧 QC 表保留且各 `0` 行；完整细节见 `evidence/R3/batch1-postdeploy-20261014.txt`。`536 passed / 47.20s` 为更早基线，不再作为最新数字。192.168.1.9 实测调度/依赖/补数和旧 IDE 探索结果仍只代表各自历史证据，不得替代 R4 SYNC 或 R10-A/R10-B 新 Backend 验收；门禁不要求人工点击登录页。
