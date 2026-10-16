# Datara 平台重建设计文档

> **唯一权威设计文件（2026-10-16 用户裁定 A 恢复）**：本稿是用户逐字研究讨论的原始重建设计正本（出生提交 `6e9faf3`），自 `docs/archive/superpowers/specs/` 恢复为本路径并恢复设计真源地位。执行状态附录为 [`2026-10-14-datara-platform-rebuild-design-执行附录.md`](2026-10-14-datara-platform-rebuild-design-执行附录.md)（原评审修订版，已降级为执行状态与裁定留痕）；本稿 §13.17 汇总并回的用户批准裁定。设计语义冲突时以本稿为准，执行状态以附录与台账为准。

> 状态：设计基线
>
> 日期：2026-10-14
>
> 适用范围：新 Backend、独立测试页面、后续正式前端融合
>
> 说明：本文档是用户最新裁定下的新重建设计基线。现有 Backend 和现有前端保留用于参考，不作为新架构的运行时依赖。

> 执行约束：增量门禁、用户要求留痕、影响分析和运行资源要求均以权威台账 `docs/increments/重建执行约法与台账.md` 及增量目录的当前计划/执行附录为准。本稿接收经用户批准的设计修订（以 §13.17 等裁定章节追加方式并回，不回写改动用户原文）；旧稿原先"不再接收修订/目录权威已失效"的说明因裁定 A 失效。

## 1. 目标与边界

Datara 重建为统一的数据开发、工作流调度、数据同步、流处理、数据治理和 AI 辅助平台。第一阶段只建设可验证的 Backend 和独立测试页面；正式前端在 Backend API、数据模型和运行协议冻结后再融合重构。

### 1.1 必须满足

- 新 Backend 重新设计和实现，不兼容旧变量语法和旧接口。
- 工作流草稿支持试运行；正式运行必须绑定已发布的不可变版本。
- 核心节点优先实现：流类、同步类、SQL、Python、SHELL、依赖。
- SQL IDE 作为相对独立的子系统，与核心节点并行开发。
- SQL IDE 参考 DBX，支持表、视图、存储过程、函数等对象编辑及跨 Schema 查询。
- 所有变量引用都校验、补全并展示现时值。
- SQL、Python、Shell 支持上传文件。
- 所有运行记录拥有数据库生成的时间戳。
- 工作流结果支持成功、失败、跳过等数据行统计。
- 实时流任务具备数据生产、处理和实时观摩验证链路。
- AI 只作为全系统悬浮助手，不新增一级菜单。

### 1.2 明确不做

- 不恢复旧 Backend 作为新系统运行依赖。
- 不在新系统中兼容旧变量写法。
- 不在首期堆叠大量专用 DAG 组件。
- 不把 ETL 单独作为工作流分类；ETL 作为普通 DAG 的一种业务用途。
- 不在 Backend 冻结前改造正式前端。
- 豁免注记（D-1 = B，2026-10-14）：只保留已批准的三项正式前端菜单展示层调整——`App.vue` 中“同步任务”“数仓建模”的菜单分组，以及 `routes.ts` 中 `/std/*` 路由退出 demo 标记。豁免仅限导航/路由展示属性，不授权页面业务功能改造；正式页面功能仍冻结至 Backend 冻结后融合。

### 1.3 已批准的验证与前端边界补充（2026-10-14）

- 本次重建的唯一增量编号为 `R0-R11`；历史重建记录 `I0-I11` 对应映射为 `R0-R11`。旧系统主题/资产 `I18-I24` 等编号保持原样；旧的 `I19-数据开发IDE对象编辑.md` 主题文档按裁定改名为 `I25-数据开发IDE对象编辑.md`，避免与新增量编号混淆。
- 独立验证前端不提供人工账号/密码登录页面。验证运行环境使用不进入静态页面、源码、浏览器 localStorage 或 URL 的统一 Backend 验证 key 向 Backend 换取短时、最小权限 token，再把 token 注入验证页面运行上下文；key 只由受控验证运行器/部署环境注入，不能作为公开浏览器页面的输入项。正常用户认证 API 仍由 Backend 提供，不以验证 bootstrap 取代。
- 每个独立测试页面必须以被测产品/组件自身的前端交互逻辑为参考（例如 Dolphin Scheduler、DBX、DataX、Vanna、OpenMetadata/DataHub 的相关 UI 与使用文档/源码），并以真实表单字段、默认值、校验、交互顺序和结果反馈作为验收依据；不得将 Datara 旧版正式前端当作参考标准，也不得把仅能点击 API 按钮的调试面板称作功能验证页。
- 上述规则适用于 R0-R11 的独立验证页。正式 Datara 前端仍冻结至 Backend/API/数据模型/运行协议整体冻结后，才开展融合重构；既有批准保留的三项菜单展示层调整属于独立豁免，页面功能改造仍冻结。

### 1.4 内部系统权限范围裁定

按用户裁定，Datara 为内部系统，首期不实现敏感值识别、列级脱敏、敏感值加密/脱敏展示或基于密级的内容隐藏。`security_level` 如因历史资产存在可作为治理元数据字段展示/迁移，但不得据此伪称已经实现敏感数据安全控制。仍须保留账号角色、项目成员/操作权限、工作流与治理对象的访问授权及操作审计；不以“内部系统”为由取消基本权限校验。

## 2. 总体架构

```text
新 Backend
├── identity
├── project
├── workflow
├── workflow_version
├── task_definition
├── task_instance
├── schedule
├── variable
├── datasource
├── sql_ide
├── data_asset
├── metadata
├── lineage
├── execution
├── execution_metric
├── quality
├── data_transfer
├── standard
├── security
├── semantic
└── ai_copilot

独立测试页面
├── Backend API 验证页
├── 节点表单验证页
├── SQL IDE 验证页
├── 运行与日志验证页
└── 数据统计与血缘验证页

正式前端
└── Backend 冻结后融合重构
```

核心原则是：SQL IDE、工作流节点、AI 助手共享同一套数据源、变量解析、执行、日志和统计服务，不允许各自建立独立执行引擎。

## 3. 核心领域模型

### 3.1 项目和工作流

```text
project
project_member
project_variable
workflow_definition
workflow_version
workflow_node
workflow_edge
workflow_variable
workflow_schedule
workflow_publish_record
```

工作流版本状态：

```text
DRAFT
PUBLISHED
RUNNING
DISABLED
ARCHIVED
```

正式运行必须绑定 `workflow_version_id`。草稿试运行生成独立的 `workflow_draft_snapshot`，不改变已发布版本。

### 3.2 任务类型

首期 Palette：

```text
FLOW
SYNC
SQL
PYTHON
SHELL
DEPENDENCY
```

首期流类组件：

```text
START
END
CONDITION
FORK
JOIN
WAIT
SUB_WORKFLOW
```

后续任务类型采用插件化扩展，不在首期加入大量 Spark、Flink、HTTP、Kafka 专用节点。

## 4. 试运行和正式运行

### 4.1 试运行

```text
当前草稿
→ 静态校验
→ 生成草稿快照
→ 创建 TRIAL 实例
→ 执行
→ 输出日志、变量值和数据统计
```

支持：

- 当前草稿运行；
- 单节点运行；
- 从指定节点运行；
- 测试变量覆盖；
- 依赖模拟；
- Dry Run；
- SQL 预检查；
- 结果转正式版本。

### 4.2 正式运行

```text
已发布版本
→ 创建 FORMAL 实例
→ 调度或手工运行
→ 绑定固定变量快照
→ 记录完整执行证据
```

运行实例通过 `instance_type` 区分：

```text
TRIAL
FORMAL
STREAM
```

## 5. 变量规范

统一变量语法：

```text
${global.xxx}
${project.xxx}
${workflow.xxx}
${task.xxx}
${env.xxx}
${run.xxx}
${tmp.xxx}
$[yyyy-MM-dd]
```

优先级：

```text
run > task > workflow > project > global > env > builtin
```

所有使用变量的表单、编辑器和脚本输入都必须支持：

- 语法校验；
- 变量补全；
- 类型提示；
- 当前值预览；
- 来源展示；
- 未定义检测；
- 类型不匹配检测；
- 循环引用检测。

每次执行生成变量快照：

```text
task_instance_variable_runtime
```

记录表达式、作用域、变量名、解析值、类型、来源、解析时间和执行尝试编号。

## 6. 核心节点设计

### 6.1 SQL

- 多语句执行；
- 参数和变量替换；
- 前置和后置 SQL；
- 事务模式；
- 读写模式；
- Explain；
- 影响行数统计；
- SQL 文件上传；
- SQL 资产绑定；
- 试运行和正式运行。

### 6.2 Python

- 在线编辑；
- `.py` 和 `.zip` 上传；
- 依赖文件；
- requirements；
- 参数注入；
- 结构化结果统计；
- 标准输出和错误输出。

### 6.3 Shell

- `.sh` 和 `.bash` 上传；
- 工作目录；
- 解释器；
- 参数和环境变量；
- 返回码；
- 超时和重试；
- 结构化统计文件。

### 6.4 同步

同步表单包含：

```text
源数据源
源表
目标数据源
目标表
字段探查
类型探查
自动映射
用户调整映射
表达式转换
过滤条件
分区和增量字段
主键和冲突处理
批大小和并发度
```

字段映射必须记录：

```text
source_column
target_column
source_type
target_type
transform_expression
nullable
default_value
mapping_status
```

### 6.5 依赖

参考 DolphinScheduler 的依赖表单，支持：

- 工作流依赖；
- 任务依赖；
- 文件依赖；
- 表状态依赖；
- 外部任务依赖；
- 时间范围；
- 轮询周期；
- 超时；
- 满足和失败策略。

## 7. 数据开发 IDE

SQL IDE 与核心节点并行建设，参考 DBX 的数据源能力分级、查询编辑、结果网格、SQL 历史、SQL 资产、异步执行和数据导出能力。

### 7.1 对象范围

```text
数据库
Schema
表
视图
字段
索引
函数
存储过程
触发器
```

对象均支持：

- 查看定义；
- 编辑定义；
- 语法校验；
- 依赖分析；
- 差异对比；
- 版本保存；
- 发布执行；
- 执行日志。

### 7.2 跨 Schema 查询

补全和执行上下文需要支持数据库内跨 Schema：

```sql
select a.id, b.name
from ods.order_info a
join dwd.customer_info b
  on a.customer_id = b.customer_id;
```

前提是数据源能力矩阵允许跨 Schema 查询。

### 7.3 结果网格

支持多结果集、分页、虚拟滚动、筛选、排序、行详情、JSON 展开、复制、CSV/JSON/Excel 导出、结果转图表和结果保存为数据集。

## 8. 实时流处理验证

建设一个可运行的实时观摩工作流：

```text
实时数据生产
→ 消息队列
→ 流处理任务
→ 聚合/融合
→ 结果存储
→ 实时观摩
```

生产节点支持固定速率、随机数据、异常数据、重复数据、延迟数据、乱序数据和突发流量。

观摩页面显示：

```text
生产速率
消费速率
处理速率
输入数
输出数
成功数
失败数
跳过数
重复数
积压量
偏移量
窗口结果
错误样本
```

## 9. 运行日志和结果统计

运行相关表：

```text
workflow_instance
task_instance
task_instance_attempt
task_instance_log
task_instance_output
task_instance_variable_runtime
workflow_result_stat
task_instance_data_stat
task_data_stat_segment
task_data_error_sample
execution_event
```

每张运行相关表必须拥有数据库生成的非空时间字段：

```text
created_at
updated_at
generated_at
```

运行执行表额外拥有：

```text
started_at
finished_at
event_time
attempt_no
```

统一工作流统计表 `workflow_result_stat` 至少记录：

```text
input_record_count
output_record_count
success_record_count
failed_record_count
skipped_record_count
rejected_record_count
filtered_record_count
duplicate_record_count
inserted_record_count
updated_record_count
deleted_record_count
read_bytes
write_bytes
batch_count
data_quality_status
extra_metrics
```

任务级、阶段级和错误样本表保存细节，重试按 `attempt_no` 隔离，最终汇总不得重复计算。

## 10. 前端测试页面和融合规则

测试页面必须参考现有原版系统的布局、Palette、图标、DAG 交互、节点弹窗、运行页、日志页、变量编辑器和调度页，不得只做脱离原系统的临时表单。

首期测试页面：

```text
项目测试页
工作流测试页
节点配置测试页
变量测试页
SQL IDE 测试页
试运行测试页
正式运行测试页
日志和变量快照测试页
数据统计测试页
流处理观摩测试页
```

测试页面阶段完成以下门禁后，正式前端才允许融合：

- API 契约冻结；
- 数据模型冻结；
- 节点协议冻结；
- 变量协议冻结；
- 执行状态冻结；
- 统计协议冻结；
- 时间戳规范冻结；
- 试运行和正式运行行为验收通过。

## 11. AI 助手

AI 仅作为全系统悬浮图标和侧边抽屉，不新增一级菜单。

根据当前页面携带：

```text
项目
工作流
节点
SQL
数据源
变量
运行记录
数据统计
元数据
血缘
```

AI 通过统一工具调用 SQL 执行、工作流校验、运行诊断、元数据检索、血缘分析和结果可视化，不允许另建执行引擎。

推荐组合：

```text
Datara Backend
+ OpenMetadata 或 DataHub
+ 数仓语义层
+ 自研 AI Agent
+ Vanna 工具调用思想
```

## 12. 验收原则

每个增量必须同时提供：

```text
数据模型
API 契约
后端实现
自动化测试
独立测试页面
运行证据
文档更新
```

没有可执行测试和运行证据的功能，不进入“完成”状态。

## 13. 评审修订与现有资产承接

本章是对本设计文档的评审闭环，优先于前文中仅列出模块名称但未展开的表述。

### 13.1 治理域不是占位模块

新 Backend 的治理域包含：

```text
data_asset       数据资产主索引
metadata         元数据目录、字段、负责人、标签
lineage          表级、字段级、设计态、运行态血缘
quality          质量规则、质量任务、异常样本、评分
standard         数据元、代码、命名、映射、评审发布
security         密级、业务域、列级脱敏、访问审计
semantic         指标、维度、业务术语和口径
```

#### 现有 I18-I23 承接决策

现有系统中的 I18-I23 资产不废弃：

| 现有资产 | 重建处理 |
|---|---|
| I18 数仓建模 | 迁移模型、字段、关系和版本；新 Backend 成为后续运行真源 |
| I19 元数据/标签 | 迁移资产扩展、标签和业务域；保留实时内省能力 |
| I20 指标 | 迁移指标定义、结构化取数配置和版本 |
| I21 质量 | 迁移规则、任务、异常样本和告警关联 |
| I22 标准 | 迁移数据元、码表、命名和映射规则；保留标准评审发布 |
| I23 权限 | 迁移角色、权限点、密级、业务域、脱敏规则和审计记录 |

迁移原则：旧表在迁移期间只读；新 Backend 通过迁移适配器导入新模型；迁移完成后新模型为运行真源。旧模型不再接受新写入，但保留回溯查询。

平台治理真源定义为：

```text
Datara 新 Backend：工作流、运行、任务、变量、数据资产和治理状态真源
OpenMetadata/DataHub：可选外部目录和 AI 上下文投影，不作为 Datara 执行真源
```

### 13.2 治理域模型和边界

核心模型：

```text
data_asset
metadata_table
metadata_column
metadata_tag
metadata_owner
lineage_edge
lineage_field_edge
quality_rule
quality_task
quality_run
quality_exception
standard_data_element
standard_code_set
standard_naming_rule
standard_mapping_rule
security_policy
mask_rule
access_audit
semantic_metric
semantic_dimension
business_term
```

边界：

- 元数据采集首期采用实时内省、数仓模型和运行事件三类来源；
- 血缘首期支持 SQL 解析、同步映射、工作流声明和运行回写；
- 质量首期支持完整性、唯一性、准确性、及时性和一致性规则；
- 标准首期支持数据元、码表、命名、类型精度、取值域和映射合规；
- 安全首期支持最小 RBAC、密级、业务域、列级脱敏和访问审计；
- 不在首期实现外部统一主数据、跨企业数据交换和复杂策略编排。

### 13.3 调度与执行运行时

调度触发类型：

```text
MANUAL
CRON
DEPENDENCY
EVENT
TRIAL
```

调度字段：

```text
timezone = Asia/Shanghai
misfire_policy = FIRE_ONCE | SKIP | FIRE_ALL_LIMITED
concurrency_policy = ALLOW | FORBID | QUEUE
priority
max_running_instances
retry_policy
timeout_policy
alert_policy
```

运行拓扑：

```text
API：接收配置、创建实例、查询状态
Master/Scheduler：解析调度、生成实例、分派任务
Worker：执行 SQL/Python/Shell/Sync
Stream Worker：管理长驻流任务
Logger：收集日志和运行事件
Alert：发送邮件、站内消息等告警
Redis：会话、进度广播、短期状态
MySQL：元数据、实例、统计、审计
Kafka：流处理验证和消息链路
```

批任务是有限生命周期实例；流任务是长驻 `STREAM_JOB`，需要独立的启动、停止、心跳、故障恢复、位点、漂移和终止状态模型，不与批任务强行共享完成语义。

### 13.4 权限模型

首期采用最小 RBAC：

```text
ADMIN
DEVELOPER
OPERATOR
VIEWER
```

权限点示例：

```text
project:read/write
workflow:read/write/publish/run/delete
task:read/write/run
datasource:read/use/manage
sql:read/execute/write-ddl
schedule:read/manage
lineage:read
quality:read/write/run
standard:read/write/approve
security:read/manage
audit:read
```

数据级控制沿用并重建现有 `clearance`、`biz_domain`、`maskRow` 机制：

- 表级密级判定；
- 业务域匹配；
- 列级脱敏；
- 统一读取出口；
- 访问允许/拒绝审计。

所有新 API 都必须携带用户上下文，测试页面使用现有 token header 约定的重新实现版本。

### 13.5 变量类型和生命周期

变量类型：

```text
STRING
INTEGER
DECIMAL
BOOLEAN
DATE
DATETIME
JSON
ARRAY
```

变量定义增加：

```text
type
default_value
nullable
format
timezone
business_calendar
description
```

`$[yyyy-MM-dd]` 默认使用 `Asia/Shanghai`，支持显式时区和业务日历；`tmp` 变量只在当前工作流实例有效，实例结束后失效；密码类变量只保留引用和执行上下文，不进入普通日志。

### 13.6 SQL IDE 结果和 DDL 管控

查询结果协议固定为：

```text
execution_id
result_set_id
columns
rows
row_count
page
page_size
has_more
storage_ref
truncated
generated_at
```

小结果可短期内存缓存，大结果写入项目运行结果存储，页面只通过分页接口读取；超过限制必须截断并提供导出任务；取消操作向执行器发出 cancel/kill 信号，最终状态必须为 `CANCELLED` 或 `CANCEL_FAILED`。

存储过程、函数、视图、触发器和表结构编辑属于 DDL 写路径，必须经过：

```text
权限校验
→ 依赖检查
→ 影响对象预览
→ DDL 脚本快照
→ 用户确认
→ 执行
→ 结果记录
→ 失败回滚或补偿脚本
```

本系统首期不提供自动审批流，但必须记录操作者、脚本、对象、执行时间、结果和失败原因。

### 13.7 流处理运行时

首期沿用现有运行资源：Kafka 作为消息队列，Redis 作为进度广播和短期观摩数据，MySQL 保存作业状态、位点和统计；后续允许增加其他 MQ 适配器。

流作业模型独立于批实例：

```text
stream_job
stream_job_attempt
stream_checkpoint
stream_metric_snapshot
stream_failure_event
```

状态：

```text
CREATED
STARTING
RUNNING
PAUSED
STOPPING
STOPPED
FAILED
RECOVERING
```

### 13.8 部署与环境基线

`192.168.1.9` 为唯一运行验证资源，沿用项目现有容器拓扑。重建验证 Web 使用独立宿主端口 `18091`；既有 `8090` 不再作为本次重建 browser-use 入口，`18090` 已被其他验证栈占用：

```text
mysql-meta
mysql-src
mysql-dw
redis
zookeeper
kafka
datara-api
datara-master
datara-worker
datara-alert
datara-logger
datara-web
```

重建 Web 入口：`http://192.168.1.9:18091/`。端口切换只改变宿主机 Web 暴露端口，不改变容器内 Nginx 的 `80` 端口和 `/api` 反向代理契约。

配置通过环境变量和远程部署配置注入；本机不作为容器运行资源。日志统一写入远程隔离目录，验证证据包括 compose 状态、容器日志、接口响应、浏览器操作、数据库行和服务健康检查。

### 13.9 AI 契约纳入冻结范围

AI 工具注册表、工具参数模型、工具返回结构、权限上下文和审计字段属于 Backend 契约的一部分，必须在 Backend 冻结前完成：

```text
search_schema
validate_sql
run_sql
get_workflow
validate_workflow
inspect_workflow_run
get_task_metrics
get_lineage
```

AI 首期可以不接真实 LLM，但必须先完成工具契约、假 Agent 测试和悬浮助手测试页，避免 Backend 冻结后重新解冻接口。

### 13.10 量化验收基线

首期基线：

```text
Backend 单元/契约测试通过率：100%
关键 API 集成测试：100%
核心节点端到端场景：SQL/Python/Shell/Sync/Dependency/Stream 各至少 1 条
变量引用校验覆盖：所有核心节点表单和编辑器入口
运行表时间戳完整率：100%
执行结果统计完整率：100%
SQL IDE 元数据补全 P95：≤ 2 秒（远程测试环境）
调度触发延迟 P95：≤ 10 秒
流观摩指标刷新周期：≤ 5 秒
异常注入场景：失败、重试、取消、断点恢复、重复数据、乱序数据
```

运行证据统一存放在：

```text
D:\需求\数据治理工具\Datara\docs\increments\evidence\I<编号>\
```

### 13.11 评审结论

本轮评审提出的问题全部纳入修订：

- 治理域补全并承接 I18-I23；
- 调度、执行、权限和部署拓扑补全；
- SQL IDE 拆分只读和 DDL 写路径；
- 变量类型、流运行时和结果集协议补全；
- SYNC 执行器、datasource 前置和远程测试库补入计划；
- 每个增量配置最小前端验证页；
- 测试页面与正式前端隔离；
- AI 工具契约纳入 Backend 冻结；
- 异常注入、并发、迁移、mock 双轨和量化基线补入验收。

### 13.12 跨文档一致性闭环（2026-10-14）

为避免架构模块在计划中“有名无实”，本设计与增量计划采用以下固定对应关系：

| 设计域 | 计划增量 | 冻结前必须存在 |
|---|---|---|
| `identity/project/datasource` | I1 | token、成员/RBAC、数据源连通性和能力矩阵 |
| `workflow/workflow_version/task_definition` | I1/I2/I4 | 版本、草稿快照、节点配置和六类执行器 |
| `schedule/execution/execution_metric/task_instance` | I2/I7/I9 | 实例、调度、事件、统计、重试和取消 |
| `variable` | I2 | 类型、作用域、补全、现值、运行快照 |
| `data_asset/metadata/lineage/quality` | I3/I9 | I18-I23 承接、采集、表/字段血缘、质量规则和运行回写 |
| `standard/security/semantic` | I3 | 标准、权限/密级、业务域、审计、指标和术语 |
| `data_transfer` | I4/I9 | SYNC、探查映射、断点统计和血缘回写 |
| `sql_ide` | I5/I6 | 只读查询协议与 DDL 写路径管控 |
| `ai_copilot` | I10/I11 | 工具契约、假 Agent、悬浮助手和审计 |

### 13.13 全量运行表时间戳契约

以下表均属于运行记录范围，全部由数据库默认生成非空 `created_at`、`updated_at`、`generated_at`；I2 负责统一迁移模板和首轮真实 MySQL 断言，I8 新增流表时复用模板，I9 做最终完整性稽核：

```text
workflow_instance
task_instance
task_instance_attempt
task_instance_log
task_instance_output
task_instance_variable_runtime
workflow_result_stat
task_instance_data_stat
task_data_stat_segment
task_data_error_sample
execution_event
stream_job_attempt
stream_checkpoint
stream_metric_snapshot
stream_failure_event
```

`started_at`、`finished_at`、`event_time`、`resolved_at` 等是业务时间字段，不能替代系统生成时间戳。验收证据必须逐表包含建表定义、插入记录、数据库返回值和容器日志摘要。

### 13.14 冻结门禁与 AI 契约

AI 工具不是冻结后的附加功能。以下内容在 I10 完成并进入 I11 冻结快照：工具名和版本、输入输出 Schema、权限上下文、审计字段、错误码、超时/重试/预算策略、假 Agent 测试和悬浮助手验证页。I11 必须验证这些契约与普通 Backend API 一起冻结；冻结后只做正式前端融合，不允许新增或改变 AI/Backend 契约。

I0-I10 均须提供独立路由组下的最小前端验证页，并通过 `192.168.1.9` 的 browser-use、Backend、MySQL/Redis/Kafka、Worker 日志和页面结果闭环。正式前端菜单、正式页面和旧 mock 双轨在 Backend 冻结前保持不变。

### 13.15 旧治理数据迁移的源 schema 证据门（2026-10-15）

I18-I23 完整承接裁定仍有效，但旧主题设计稿/ORM 不自动等同于运行中 `datara_meta` 的当前物理 schema。每个迁移源表在字段映射、parity 与任何目标导入之前，必须绑定当前只读采集的 schema identity、采集时间与摘要，并记录列名、类型、可空性、默认值、主键、唯一键及可验证外键/索引；采集不得产生旧源库 DDL/DML。历史 schema inventory 只能作差异线索，不能单独证明当前合同。

若旧主题设计、保留 ORM、历史 inventory 与当前只读物理 schema 不一致，必须在迁移计划/证据中逐列解释：能够无损承接的显式映射；不可映射的阻断项；是否需要新增规范化字段/关系。不得按字段名近似、设计稿想当然或空值填充掩盖差异；若不能无损表达，先更新本设计及实施计划并按变更治理处理，再实现映射。目标设计承诺完整承接，不代表可以省略源证据。

I22 特别状态：`docs/increments/evidence/R3/remote-schema-inventory.txt` 是 `2026-10-14T17:55:28+08:00` 的历史列清单，其 `t_std_element`、`t_std_approval`、`t_std_mapping` 列与旧 I22 设计稿不一致，且当前重建工作树没有可作为当前合同的旧 Std ORM/API。该清单不得用作 I22 mapper 的唯一输入；须先取得版本绑定的当前只读 schema 证据并完成逐列复核。此门仅阻断 I22 字段映射/parity/import，不撤销 I18-I23 全量承接决策，也不授权任何源/目标写入。
### 13.16 R2-13 测试库与数据库时间戳实测（2026-10-15）

R2-13 在 `192.168.1.9` 的隔离 schema `datara_rebuild_i0` 上完成只读验收：仅查询目标 schema 的 `information_schema`、治理/迁移表计数与时间戳、已存在验证资产 #10/#11 以及项目 #8 审计记录；远端应用/API/容器状态与受限 API 访问日志只读采集。没有触碰 `datara_meta`、源库、数仓或目标数据写入。

证据 `docs/increments/evidence/R2/r2-13-20261015175857.json` 与同名 PNG 证明目标 MySQL 8.0.46 中 42 张治理/迁移表的 130 个时间列定义均采用 `CURRENT_TIMESTAMP` 默认；逐表已存记录的 `created_at/updated_at/generated_at` 均无 NULL。两条迁移 revision/checksum 与当前 Backend 注册内容一致，状态均为 `completed` 且有 started/finished 时间。真实页面选择既有项目、打开既有资产与 Activity/Audit：31 条审计的数据库 `generated_at`、API 响应和页面控件逐条一致；页面/健康探测 HTTP 200，页面业务请求全为 GET。外部资产 `row_count` 在目标数据中为 NULL，页面如实显示“—”；此结果不构成源业务数据行数探查。工作流实例/任务执行表尚未在本增量创建，必须在对应后续增量建表时继续执行 §13.13 的完整字段契约和表级验收。

验证通道：browser-use 同页绑定/导航两次分别在 30s 与 60s 超时，按已批准经验规则改用 Playwright 对同一 18091 验证页执行真实控件操作；R2-13 证据同时归档 `browser-entry-20261015.txt`、`remote-final-20261015.txt`。此记录是 §13.13 的局部治理 schema 实测，不替代工作流运行表的未来验收。

### 13.17 裁定 A 并回：执行提速与承接裁定的设计边界（2026-10-16，自执行附录回补）

> 背景：2026-10-14 评审曾以薄壳修订版替换本稿权威地位（编辑权易主未经用户逐字确认）。2026-10-16 用户裁定 A 恢复本稿为唯一设计真源；原评审修订版降级为 [`2026-10-14-datara-platform-rebuild-design-执行附录.md`](2026-10-14-datara-platform-rebuild-design-执行附录.md)。本节把附录中经用户批准、仍约束设计边界的裁定并回本稿；执行状态细节以附录与台账为准。本节为追加章节，不回写改动 §1-§13.16 用户原文。

1. **编号体系与增量重排（P2，2026-10-15 用户批准）**：执行计划重排为 9 个增量 `R0-R4、R5-IDE、R6-R8`。本稿 §1.3 所述"唯一增量编号 R0-R11"及原计划 R0-R11/I0-I11 映射关系保持为历史基线；重排不删减业务能力——原 R9 任务中心归 R7，统计生产归 R4（SYNC）与 R8（STREAM）；原 R10-A/R10-B 合并为 R5-IDE 的 R5-A 只读与 R5-B DDL 两个独立子门禁（DDL 8 步管控不降级）；原 R11 AI 工具契约按所依赖领域冻结，浮动助手与全平台验收归 R8。
2. **P1-P4 执行规则**（流水线并行、增量合并、证据分级 JSON+PNG 成对与 remote-final、双执行者文件所有权）作为设计边界外的执行裁定继续有效；红线（人工确认闸、失败证据保留、诚实状态、TDD 红绿、token/key 边界、验收前不提交实现）不受提速影响。
3. **R2-01..15 评审修复矩阵**：作为对 §1-§12 模块级表述的强制设计边界继续有效（治理五域、调度语义、最小 RBAC、DDL 管控、变量类型、流状态机、结果集协议、部署拓扑、AI 契约、量化基线、SYNC 执行器、datasource 前置、测试库供给、验证页门禁、IDE 子门禁）；矩阵全文与验收证据列见附录 §2。
4. **治理五域真源与 I18-I23 承接**：`metadata`/`lineage`/`quality`/`data_asset`/`data_transfer` 为自研真源，OpenMetadata/DataHub 仅作外部导入投影；I18-I23 资产完整承接（与 §13.1 一致且更细化）。I18 规范化承接模型采用附录 §5.2 的 exact mapping（2026-10-15 用户批准）；D-R3-S8 方案 A（扩展新 Backend 规范化模型完整承接）继续有效，执行边界见附录 §6 与台账。
5. **统计产出语义**：统计由实际执行器写入而非任务中心计算——R4 SYNC 记录读取/写入/新增/更新/成功/失败/跳过/过滤、期望与实际计数、耗时、attempt；R8 STREAM 记录输入/处理/输出/失败/跳过、吞吐/延迟/位点/重启与观测区间；R7 只消费展示并回溯 run/task/attempt；所有统计行保留三类数据库时间戳与源运行 ID。与 §9 统计表契约互为补充，不降低 §9 要求。
6. **差异注记——变量作用域**：附录 §4 曾将作用域收窄为 global/workflow/task/runtime 四级；本稿 §5 七级优先级链 `run > task > workflow > project > global > env > builtin` 为设计真源。若后续增量确需收窄作用域层级，须先取得用户批准并修订本稿，不得以附录单方收窄为准。
7. **附录 §8 权威链回补说明**：附录 §8.1-8.4（R5-IDE 九类对象八项操作、结果网格扩展、元数据补全 P95≤2s、R8 观摩查询接口结构）的源头即本稿 §7.1、§7.3、§13.10 与原计划附录 A7，属裁定 B 时期的指针修复；其内容本稿已具备，无需重复并回，附录仅作执行引用。
8. **验收标准正本确立（2026-10-17 用户批准，心跳 #42 发布令）**：[核心业务功能实现规范与验收标准](2026-10-17-核心业务功能实现规范与验收标准.md)（标准稿 v3，main `3378175`）为 R0-R11 全域验收与质量检查生效正本；效力位阶=用户裁定原文 > 标准稿 v3 > 各域契约文档。本稿 §1.2/§1.3/§6.5/§7.1/§11 的能力语义由标准稿 v3 验收化承接（§0 优先级总则 + S1 复刻/S2 验证分层/S3 变量/S4 DS 全链路/S5 AI 助手 + A1-A7 门禁 + §4 逐域清单）。R4 依赖契约字段级细节（`failure_waiting_seconds`+「源分钟 ×60→契约秒」换算、`group_relation: AND|OR`、Dependence 嵌套模型）以标准稿 v3 S4 表 + A2 v2.1 为准，本稿 §6.5 不重复展开表单字段级定义。标准稿修订走其 §5 治理流程（提案→用户批准→版本递增），重大语义变更逐批并回本节登记。

