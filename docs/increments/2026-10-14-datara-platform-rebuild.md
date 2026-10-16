# Datara Platform Rebuild Implementation Plan

> **唯一权威增量计划（2026-10-16 用户裁定 A 恢复）**：本稿是用户逐字研究讨论的原始重建计划正本（出生提交 `6e9faf3`），自 `docs/archive/superpowers/plans/` 恢复为本路径并恢复计划真源地位。执行状态附录为 [`2026-10-14-datara-platform-rebuild-执行附录.md`](2026-10-14-datara-platform-rebuild-执行附录.md)（原评审修订版，承载 9 增量重排、P1-P4 执行规则、R2-01..15 状态跟踪与 S9/I18-I23 子增量计划）；本文末"修订章（2026-10-16 裁定 A 并回）"汇总经用户批准的执行重排。设计冲突以正本设计文档为准，执行现状以附录与台账为准。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不依赖旧 Backend 和冻结正式前端的前提下，增量建设 Datara 新 Backend、独立测试页面、DBX 级数据开发 IDE、核心 DAG 节点、运行统计和实时流验证链路。

**Architecture:** 新 Backend 采用领域模块化结构，共享变量解析、数据源能力、执行、日志和统计服务。SQL IDE 与工作流核心节点并行开发；每个增量先完成契约、后端、测试和独立页面，所有门禁通过后才进入下一增量，正式前端最后融合。

**Tech Stack:** 以现有 `datara-backend` 的 Python 工程和 `datara-web` 的 Vue/TypeScript 工程为承载；数据库迁移沿现有 Backend 规范；测试使用现有 Backend/Web 测试框架；运行验证使用项目规定的隔离测试环境。

---

## 强制增量门禁

每个 Task/增量开始前，必须先完成 `D:\需求\数据治理工具\Datara\docs\increments\重建执行约法与台账.md` 中的“开始前影响分析”和步骤细化；每个增量结束前，必须由参照对应产品/组件自身前端流程制作的独立页面牵引，使用 browser-use 验证浏览器交互、Backend、中间件、资源、环境、执行器和后台日志，并把用户要求、命令、证据和遗留任务写入项目主目录台账。页面不得复刻 Datara 旧前端或退化成 API 按钮面板。页面不设人工登录表单；验证运行器从部署环境读取统一 Backend 验证 key，向后端换取短时受限 token 并注入页面上下文，key 不得出现在静态产物、URL 或浏览器持久存储中。

若发现与总体设计冲突，必须暂停受影响步骤，取得用户批准后立即刷新项目主目录中的设计文档、计划文档、接口/数据库契约和验收标准；未刷新前不得继续。

本段流程说明自 2026-10-16 用户裁定 A 起继续有效：本稿即 `docs/increments/` 下的唯一权威增量计划正本；执行状态、9 增量重排与 R2 跟踪见文末修订章与执行附录。Agent worktree 仅用于代码隔离，不作为共享文档和执行状态的权威位置。

验证环境固定为：

```text
本机：代码检测、静态检查、类型检查、业务逻辑稽核
192.168.1.9：部署、容器服务、中间件、运行资源、接口联调、browser-use 端到端验证
```

重建前端验证入口固定为 `http://192.168.1.9:18091/`。不得使用既有 `8090`；`18090` 已被并行验证栈占用。Web 容器内部仍监听 `80`，API 代理契约不变。

计划中的部署和运行命令必须在 `192.168.1.9` 隔离工作目录执行；本机命令不得被视为部署或端到端验收证据。

### 每个增量的固定执行顺序

```text
上一增量验收证据
→ 影响分析
→ 设计/计划调整
→ 当前增量步骤细化
→ 失败测试
→ Backend/中间件/资源实现
→ 前端测试页面
→ browser-use 端到端验证
→ 后台日志与数据库证据
→ 台账更新
→ 增量验收
→ 下一增量
```

### 每个增量不得提前完成的条件

- 没有上一增量影响分析；
- 没有细化的可执行步骤；
- 没有前端实际操作记录；
- 没有 browser-use 验证；
- 没有 Backend 和后台日志证据；
- 没有中间件、资源和环境检查；
- 没有更新用户要求和未实现任务台账。

评审修订后的硬性补充：

- I0 必须先完成远程测试环境和现有 I18-I23 资产盘点；
- 每个后端增量必须同时提供最小独立验证页，不得等到 §8 才首次出现前端；
- `192.168.1.9` 才是部署、容器、中间件和端到端验证环境；
- 本机只执行代码检测和业务逻辑稽核；
- SQL IDE 拆分为只读能力和 DDL 写路径；
- AI 工具契约在 Backend 冻结前完成；
- 远程运行证据写入 `D:\需求\数据治理工具\Datara\docs\increments\evidence\I<编号>\`。

### 跨文档一致性基线（2026-10-14 修订）

以下矩阵是本计划与总体设计的强制交集；旧章节中的简化步骤不得覆盖本矩阵。任何模块没有对应增量、验证页、测试和远程证据时，不得宣称 Backend 冻结。

| 设计模块 | 计划增量 | 最小交付与验证 |
|---|---|---|
| `identity/project/datasource` | I1 | token、成员/RBAC、数据源 CRUD/连通性/能力矩阵；远程连接与拒绝场景 |
| `workflow/workflow_version/task_definition` | I1/I2/I4 | 版本、节点、试运行快照、六类执行器；验证页和 Worker 日志 |
| `schedule/execution/execution_metric/task_instance` | I2/I7/I9 | 实例、调度、事件、统计协议；时间戳、重试、取消、汇总证据 |
| `variable` | I2 | 类型、作用域、补全、现时值、运行快照；日志与数据库证据 |
| `data_asset/metadata/lineage/quality` | I3/I9 | I18-I23 承接、采集、表/字段血缘、质量规则、运行回写；治理验证页 |
| `standard/security/semantic` | I3 | 标准、权限/密级/业务域/审计、指标/术语；迁移和查询证据 |
| `data_transfer` | I4/I9 | SYNC 执行器、探查映射、批次/断点/统计、血缘回写；远程真实数据源验证 |
| `sql_ide` | I5/I6 | 只读查询协议与 DDL 写路径分离；分页、取消、快照、补偿和权限证据 |
| `ai_copilot` | I10/I11 | 工具契约、假 Agent、悬浮助手；纳入冻结清单和远程审计证据 |

#### 运行表时间戳闭环

以下运行表全部必须由数据库默认生成非空 `created_at`、`updated_at`、`generated_at`，并在 I2 的远程真实 MySQL 测试中逐表断言；不得只验证其中四张：

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

其中流运行表由 I8 建表，但必须复用 I2 固化的时间戳迁移模板和 I9 的完整性稽核；`started_at/finished_at/event_time` 是业务时间字段，不替代三类系统生成时间戳。

#### 门禁统一解释

I0-I10 每个增量都必须有独立路由组下的最小验证页；正式前端菜单和正式页面仍然冻结。browser-use 的远程端到端证据不可用单元测试、curl 或静态扫描替代。AI 工具契约、权限上下文、审计字段和错误码在 I10 完成，并在 I11 的冻结快照、端到端验证和 import 扫描中作为必检项。原“第 11 节 AI 悬浮助手”仅是能力细分说明，不表示把 AI 推迟到 Backend 冻结之后。

## 0. 开发约束和工作区边界

**Files:**
- Reference: `docs/increments/2026-10-14-datara-platform-rebuild-design.md`（同目录设计正本，裁定 A 恢复）
- Reference: `docs/README.md`
- Reference: `datara-backend/pyproject.toml`
- Reference: `datara-web/package.json`
- Reference: `datara-backend/tests/`
- Reference: `datara-web/tests/`

- [ ] **Step 1: 建立新重建工作的模块清单**

  以设计文档为唯一业务范围，建立以下工作项清单并写入增量记录：基础契约、变量、运行、节点、SQL IDE、同步、流观摩、统计、测试页面、前端融合、AI。

- [ ] **Step 2: 确认旧系统只读参考边界**

  将现有 Backend 和正式前端标记为参考对象；新实现不得复用旧 API 作为新 API 的隐式依赖。检查命令：

  ```powershell
  git status --short
  Get-ChildItem datara-backend,datara-web -Directory
  ```

  预期：开始开发前工作区无未授权修改，旧代码仅作为对照材料。

> **执行顺序裁定（唯一有效版本）**：以下 `R0-R11` 是唯一可执行的增量顺序（已批准映射：原重建 I0-I11 分别对应 R0-R11）。文档后部原有的“§1-§12”内容已降级为实现细节参考，不再构成独立增量、独立门禁或第二套执行顺序；其中 checkbox 只能作为对应 R 增量的实现提示，不能单独勾选为完成，也不能绕过 R0-R11 的影响分析、参考产品前端牵引和远程证据。旧系统 I18-I24 等资产编号不作改写。

## 评审修订后的增量顺序

以下顺序是对后续任务的拆分和覆盖，优先于原计划中把 datasource、前端验证和治理域放在后面的安排。

### I0：远程环境、资产盘点和迁移基线

**Files:**
- Create: `docs/increments/I0-rebuild-impact-analysis.md`
- Create: `docs/increments/evidence/I0/`
- Reference: `docker-compose.yml`
- Reference: `docs/increments/I18-数仓建模设计.md`
- Reference: `docs/increments/I19-元数据与标签管理设计.md`
- Reference: `docs/increments/I20-指标管理设计.md`
- Reference: `docs/increments/I21-数据质量管理设计.md`
- Reference: `docs/increments/I22-数据标准管理设计.md`
- Reference: `docs/increments/I23-权限管理设计.md`

- [ ] **Step 1: 在本机完成静态依赖和业务资产盘点**

  检查旧 API 引用、模型、迁移、节点执行器、变量、鉴权和 I18-I23 数据资产；本机只记录检查结果，不启动容器验收。

- [ ] **Step 2: 在 192.168.1.9 校验运行资源**

  在远程隔离目录执行：

  ```bash
  docker compose config
  docker compose ps
  docker compose logs --tail=200 mysql-meta redis kafka datara-api datara-master datara-worker
  ```

  将容器状态、健康检查、数据库连接、Redis、Kafka 和日志路径写入 `docs/increments/evidence/I0/`。

  同时明确并登记远程隔离测试库供给：使用 `192.168.1.9` 上的 `mysql-meta` 建立本次重建专用 schema/用户，使用现有 `mysql-src` 和 `mysql-dw` 作为同步与跨 Schema 验证数据源；本机 SQLite 或本机临时数据库不得作为 MySQL 默认时间戳和端到端验收依据。

- [ ] **Step 3: 形成 I18-I23 迁移清单**

  为每张旧表标记 `MIGRATE`、`READ_ONLY_COMPAT` 或 `RETIRE_AFTER_MIGRATION`，禁止直接删除旧资产。

- [ ] **Step 4: 运行 I0 验收**

  I0 没有远程资源证据不得进入 I1。

### I1：身份、项目、数据源和最小权限（PARTIAL）

**Files:**
- Create: `datara-backend/rebuild/identity/`
- Create: `datara-backend/rebuild/project/`
- Create: `datara-backend/rebuild/datasource/`
- Create: `datara-web/src/views/rebuild/validation/identity/`
- Test: `datara-backend/tests/rebuild/test_identity_project_datasource.py`

- [x] **Step 1: 实现 token 会话和最小 RBAC**（token 登出撤销和权限拒绝已完成；Redis 持久会话仍待增强）
- [x] **Step 2: 实现项目创建/列表和基础权限点**（成员接口已建立，完整成员管理待补）
- [x] **Step 3: 实现数据源校验端点和能力矩阵**（真实 MySQL 连通性探查已完成，CRUD/连接池待补）
- [x] **Step 4: 新 Backend 使用隔离库运行时配置注入；凭据不进入普通日志**（凭据引用模型待补）
- [x] **Step 5: 配置独立验证页，使用独立路由组，不注册正式菜单**
- [ ] **Step 6: 在 192.168.1.9 完成 browser-use 登录、数据源连接和权限拒绝验证**（API、真实 MySQL、登出 401、权限 403 已验证；18091 控件级证据待补）

### I2：变量、时间戳和执行实例

**Files:**
- Use: `datara-backend/rebuild/variable/`
- Use: `datara-backend/rebuild/execution/`
- Create: `datara-web/src/views/rebuild/validation/variables/`
- Test: `datara-backend/tests/rebuild/test_variables_execution.py`

- [ ] **Step 1: 固化变量类型、作用域、时区和 tmp 生命周期**
- [ ] **Step 2: 实现变量补全、校验、当前值和运行快照**
- [ ] **Step 3: 实现批实例、任务尝试、事件和生成时间戳**
- [ ] **Step 4: 在验证页展示变量实际运行值**
- [ ] **Step 5: 在 192.168.1.9 验证 MySQL 默认时间戳和重试快照**

### I3：I18-I23 治理资产迁移和治理域基线

**Files:**
- Create: `datara-backend/rebuild/governance/`
- Create: `datara-backend/rebuild/migration/`
- Create: `datara-web/src/views/rebuild/validation/governance/`
- Test: `datara-backend/tests/rebuild/test_governance_migration.py`

- [ ] **Step 1: 建立 data_asset、metadata、lineage、quality、standard、security、semantic、data_transfer 模型边界**
- [ ] **Step 2: 实现 I18-I23 只读盘点和新模型导入适配器**
- [ ] **Step 3: 实现表级/字段级、设计态/运行态血缘基线**
- [ ] **Step 4: 实现质量规则、标准规则、密级、业务域、脱敏和访问审计基线**
- [ ] **Step 5: 验证新模型为唯一新写入真源，旧资产只读，并登记 OpenMetadata/DataHub 仅作为可选外部目录投影**
- [ ] **Step 6: 在 192.168.1.9 验证迁移数据、权限判定和血缘查询**

### I4：核心节点执行器，包含 SYNC

**Files:**
- Use: `datara-backend/rebuild/task/executors/`
- Create: `datara-backend/rebuild/task/executors/sync.py`
- Create: `datara-web/src/views/rebuild/validation/tasks/`
- Test: `datara-backend/tests/rebuild/test_core_executors.py`

- [ ] **Step 1: 实现 FLOW、SQL、PYTHON、SHELL、DEPENDENCY、SYNC 六类执行器契约**
- [ ] **Step 2: 实现 SYNC 全量/增量、批提交、失败样本、断点和统计执行器**
- [ ] **Step 3: 为每类执行器配置最小验证页**
- [ ] **Step 4: 在 192.168.1.9 验证真实数据源、Worker、日志和统计**

### I5：SQL IDE 只读能力

**Files:**
- Use: `datara-backend/rebuild/sql_ide/`
- Create: `datara-web/src/views/rebuild/validation/sql-ide-readonly/`
- Test: `datara-backend/tests/rebuild/test_sql_ide_readonly.py`

- [ ] **Step 1: 实现数据库、Schema、表、视图、函数、存储过程和字段懒加载**
- [ ] **Step 2: 实现跨 Schema 补全和查询**
- [ ] **Step 3: 实现查询、取消、分页、多结果集和结果存储协议**
- [ ] **Step 4: 实现历史、SQL 资产和导出**
- [ ] **Step 5: 在 192.168.1.9 验证大结果、截断、分页和取消**

### I6：SQL IDE DDL 写路径

**Files:**
- Create: `datara-backend/rebuild/sql_ide/ddl.py`
- Create: `datara-backend/rebuild/sql_ide/ddl_policy.py`
- Create: `datara-web/src/views/rebuild/validation/sql-ide-ddl/`
- Test: `datara-backend/tests/rebuild/test_sql_ide_ddl.py`

- [ ] **Step 1: 实现表、视图、函数、存储过程和触发器定义查看/编辑**
- [ ] **Step 2: 实现权限、依赖、影响对象和脚本快照校验**
- [ ] **Step 3: 实现用户确认、执行记录、失败补偿和回滚脚本**
- [ ] **Step 4: 在 192.168.1.9 验证 DDL 成功、失败和无权限场景**

### I7：调度与执行运行时

**Files:**
- Create: `datara-backend/rebuild/schedule/`
- Create: `datara-backend/rebuild/runtime/`
- Create: `datara-web/src/views/rebuild/validation/schedule/`
- Test: `datara-backend/tests/rebuild/test_schedule_runtime.py`

- [ ] **Step 1: 实现 MANUAL、CRON、DEPENDENCY、EVENT 和 TRIAL 触发**
- [ ] **Step 2: 实现 Asia/Shanghai、misfire、并发、优先级、超时和重试**
- [ ] **Step 3: 实现 Master 分派、Worker 执行、Alert 通知和 Logger 事件链**
- [ ] **Step 4: 在 192.168.1.9 验证调度延迟、并发和失败重试**

### I8：实时流运行时和观摩

**Files:**
- Use: `docker-compose.yml`
- Create: `datara-backend/rebuild/stream_runtime/`
- Create: `datara-web/src/views/rebuild/validation/stream/`
- Test: `datara-backend/tests/rebuild/test_stream_runtime.py`

- [ ] **Step 1: 固化 Kafka、Redis、MySQL 运行时职责**
- [ ] **Step 2: 实现 stream_job、attempt、checkpoint、metric 和 failure 模型**
- [ ] **Step 3: 实现生产、消费、聚合、融合、暂停、恢复、漂移和故障恢复**
- [ ] **Step 4: 实现异常、重复、乱序、延迟和突发流量注入**
- [ ] **Step 5: 在 192.168.1.9 验证长驻进程、位点恢复和实时观摩**

### I9：统计、质量、血缘和运行报告

**Files:**
- Use: `datara-backend/rebuild/execution_metrics/`
- Create: `datara-backend/rebuild/quality/`
- Create: `datara-web/src/views/rebuild/validation/metrics/`
- Test: `datara-backend/tests/rebuild/test_metrics_quality_lineage.py`

- [ ] **Step 1: 汇总工作流、任务、阶段、重试和错误样本统计**
- [ ] **Step 2: 将质量规则结果写入运行统计和告警链**
- [ ] **Step 3: 将 SQL、同步和工作流运行回写到血缘**
- [ ] **Step 4: 在 192.168.1.9 验证成功、失败、跳过、重试和异常注入**

### I10：AI 工具契约和悬浮助手验证

**Files:**
- Create: `datara-backend/rebuild/ai_copilot/`
- Create: `datara-web/src/views/rebuild/validation/ai/`
- Test: `datara-backend/tests/rebuild/test_ai_tools.py`

- [ ] **Step 1: 固化工具参数、返回 UI 组件、权限上下文和审计字段**
- [ ] **Step 2: 使用假 Agent 完成工具调用测试，不依赖真实 LLM**
- [ ] **Step 3: 接入悬浮助手验证页，不增加正式菜单**
- [ ] **Step 4: 在 192.168.1.9 验证模型配置、调用预算、失败重试和工具审计**

### I11：Backend 冻结与正式前端融合

**Files:**
- Create: `docs/increments/evidence/I11/`
- Modify: `datara-web/src/views/`
- Modify: `datara-web/src/components/`
- Test: `datara-web/tests/e2e/`

- [ ] **Step 1: 执行 import 扫描，禁止新 rebuild 模块隐式引用旧 API，白名单除外**
- [ ] **Step 2: 确认 API、数据库、事件、变量、统计、AI 工具契约冻结**
- [ ] **Step 3: 将验证页以独立路由组迁移到正式页面，删除 mock 双轨依赖**
- [ ] **Step 4: 执行旧用户、数据源、模型、指标、标准和权限迁移回归**
- [ ] **Step 5: 在 192.168.1.9 完成全链路 browser-use 和后台日志验收**

以上 I0-I11 替代原计划中“先集中做后端、最后才出现前端验证”的执行顺序；每个增量均需最小验证页和远程运行证据。

## 附录 A：原始任务细分参考（非独立执行顺序）

本附录保留原始任务拆分，便于实施时复用测试命令、文件边界和验收细节；实际执行编号、完成状态和门禁均以项目 `docs/increments/` 下的权威计划 R0-R11 为准。

### A1. 新 Backend 骨架与契约

**Files:**
- Create: `datara-backend/rebuild/common/`
- Create: `datara-backend/rebuild/contracts/`
- Create: `datara-backend/rebuild/identity/`
- Create: `datara-backend/rebuild/project/`
- Create: `datara-backend/rebuild/workflow/`
- Create: `datara-backend/rebuild/task/`
- Test: `datara-backend/tests/rebuild/test_contracts.py`

- [ ] **Step 1: 编写领域标识和枚举契约测试**

  测试必须覆盖 `workflow_version` 状态、`instance_type`、核心节点类型和统一错误码；先断言契约导入失败或字段不存在。

- [ ] **Step 2: 实现基础契约模块**

  定义项目、工作流版本、节点、边、实例、任务类型和错误码模型；所有外部输入使用明确类型，不接受未声明字段。

- [ ] **Step 3: 增加工作流版本和草稿快照模型**

  实现草稿、发布、禁用、归档状态转换；发布后版本内容不可变；试运行引用 `workflow_draft_snapshot`。

- [ ] **Step 4: 运行契约测试**

  ```powershell
  python -m pytest datara-backend/tests/rebuild/test_contracts.py -q
  ```

  预期：所有枚举、状态转换和字段约束通过。

### A2. 时间戳、实例和统一执行框架

**Files:**
- Create: `datara-backend/rebuild/execution/`
- Create: `datara-backend/rebuild/execution/models.py`
- Create: `datara-backend/rebuild/execution/events.py`
- Create: `datara-backend/rebuild/execution/service.py`
- Create: `datara-backend/rebuild/execution/migrations/`
- Test: `datara-backend/tests/rebuild/test_execution_timestamps.py`

- [ ] **Step 1: 编写全量运行表时间戳数据库测试**

  对跨文档一致性基线列出的全部运行表逐表插入，断言 `created_at`、`updated_at`、`generated_at` 均为非空，且 `generated_at` 由数据库默认生成；测试必须在 `192.168.1.9` 的真实 MySQL 执行，不能用 SQLite 替代。

- [ ] **Step 2: 创建运行实例、统计、错误样本和事件表**

  增加 `workflow_instance`、`task_instance`、`task_instance_attempt`、`task_instance_log`、`task_instance_output`、`task_instance_variable_runtime`、`workflow_result_stat`、`task_instance_data_stat`、`task_data_stat_segment`、`task_data_error_sample`、`execution_event`，统一保存 `instance_type`、版本、尝试编号和上海时区展示信息；流运行表沿用同一迁移模板。

- [ ] **Step 3: 实现试运行和正式运行入口**

  `TRIAL` 只能引用草稿快照，`FORMAL` 只能引用已发布版本；两者共享执行器但隔离运行记录。

- [ ] **Step 4: 验证时间和状态流转**

  ```powershell
  python -m pytest datara-backend/tests/rebuild/test_execution_timestamps.py -q
  ```

  预期：试运行、正式运行、取消、失败、完成状态及时间字段全部通过。

### A3. 变量服务和运行值快照

**Files:**
- Create: `datara-backend/rebuild/variable/`
- Create: `datara-backend/rebuild/variable/parser.py`
- Create: `datara-backend/rebuild/variable/validator.py`
- Create: `datara-backend/rebuild/variable/runtime_snapshot.py`
- Test: `datara-backend/tests/rebuild/test_variables.py`
- Test: `datara-web/src/services/__tests__/variableCompletion.test.ts`

- [ ] **Step 1: 编写作用域、优先级和表达式测试**

  覆盖 `${global.x}`、`${project.x}`、`${workflow.x}`、`${task.x}`、`${run.x}` 和 `$[yyyy-MM-dd]`；断言未定义变量、类型错误和循环引用失败。

- [ ] **Step 2: 实现变量解析和校验**

  固定优先级 `run > task > workflow > project > global > env > builtin`，返回变量来源、类型、当前值和错误位置。

- [ ] **Step 3: 实现运行变量快照**

  创建 `task_instance_variable_runtime`，记录表达式、作用域、解析值、来源、`attempt_no`、`resolved_at`、`created_at` 和 `generated_at`。

- [ ] **Step 4: 实现测试页面补全数据服务**

  返回变量名、作用域、类型、当前值和来源；编辑器输入 `${` 时展示候选项，并在失焦和保存时再次调用后端校验。

- [ ] **Step 5: 运行变量测试**

  ```powershell
  python -m pytest datara-backend/tests/rebuild/test_variables.py -q
  npm --prefix datara-web run test -- --run src/services/__tests__/variableCompletion.test.ts
  ```

### A4. 核心节点执行器

**Files:**
- Create: `datara-backend/rebuild/task/executors/flow.py`
- Create: `datara-backend/rebuild/task/executors/sql.py`
- Create: `datara-backend/rebuild/task/executors/python.py`
- Create: `datara-backend/rebuild/task/executors/shell.py`
- Create: `datara-backend/rebuild/task/executors/dependency.py`
- Create: `datara-backend/tests/rebuild/test_core_executors.py`

- [ ] **Step 1: 编写六类执行器契约测试**

  FLOW、SYNC、SQL、PYTHON、SHELL、DEPENDENCY 六类执行器必须返回统一结果：状态、日志引用、变量快照引用、输入数、输出数、成功数、失败数、跳过数、错误样本引用。

- [ ] **Step 2: 实现流类执行器**

  支持开始、结束、条件、并行、合并、等待和子工作流，验证拓扑顺序、失败传播和等待超时。

- [ ] **Step 3: 实现 SQL 执行器**

  支持多语句、变量替换、事务、影响行数、前置后置 SQL、超时、重试和 SQL 文件内容。

- [ ] **Step 4: 实现 Python 和 Shell 执行器**

  支持上传资源、参数注入、工作目录、环境变量、结构化统计、标准输出、错误输出和退出码。

- [ ] **Step 5: 实现依赖执行器**

  支持工作流、任务、文件、表状态和外部任务依赖；记录轮询次数、最近检查时间、等待时长和最终结果。

- [ ] **Step 6: 运行核心执行器测试**

  ```powershell
  python -m pytest datara-backend/tests/rebuild/test_core_executors.py -q
  ```

### A5. SQL IDE 后端能力

**Files:**
- Create: `datara-backend/rebuild/sql_ide/`
- Create: `datara-backend/rebuild/sql_ide/metadata.py`
- Create: `datara-backend/rebuild/sql_ide/objects.py`
- Create: `datara-backend/rebuild/sql_ide/query.py`
- Create: `datara-backend/rebuild/sql_ide/history.py`
- Create: `datara-backend/rebuild/sql_ide/resources.py`
- Test: `datara-backend/tests/rebuild/test_sql_ide.py`

- [ ] **Step 1: 编写 SQL IDE 契约测试**

  覆盖数据库、Schema、表、视图、函数、存储过程、字段、跨 Schema 查询、SQL 历史、异步执行和结果导出。

- [ ] **Step 2: 实现数据源能力矩阵**

  返回连接、浏览、跨 Schema、执行、Explain、分页、导入导出、Schema Diff 和异步执行能力。

- [ ] **Step 3: 实现元数据懒加载接口**

  支持数据库、Schema、表、视图、函数、存储过程和字段按需加载；补全接口支持别名、CTE、跨 Schema 对象。

- [ ] **Step 4: 实现对象查看和编辑接口**

  返回对象定义、依赖、差异和发布脚本；编辑结果必须先校验，再进入执行队列。

- [ ] **Step 5: 实现查询、历史和结果导出接口**

  支持当前语句、选中语句、全部语句、停止、分页、多结果集和 CSV/JSON/Excel 导出。

- [ ] **Step 6: 运行 SQL IDE 后端测试**

  ```powershell
  python -m pytest datara-backend/tests/rebuild/test_sql_ide.py -q
  ```

### A6. 文件资源和同步映射

**Files:**
- Create: `datara-backend/rebuild/resources/`
- Create: `datara-backend/rebuild/sync/`
- Create: `datara-backend/tests/rebuild/test_resources_and_sync.py`

- [ ] **Step 1: 编写上传和映射测试**

  覆盖 SQL、Python、Shell 文件上传，源表和目标表探查，自动映射、手工调整、类型转换和映射模板。

- [ ] **Step 2: 实现资源版本和绑定**

  创建 `task_resource`、`task_resource_version`、`task_resource_binding`，上传文件必须产生不可变版本。

- [ ] **Step 3: 实现同步探查服务**

  返回源字段、目标字段、类型、可空性、默认值、主键和推荐映射；用户修改后再次校验。

- [ ] **Step 4: 实现同步执行计划**

  生成字段映射、转换表达式、过滤条件、分区、增量字段、批大小、并发和冲突处理计划。

- [ ] **Step 5: 运行资源和同步测试**

  ```powershell
  python -m pytest datara-backend/tests/rebuild/test_resources_and_sync.py -q
  ```

### A7. 工作流结果统计和流处理观摩

**Files:**
- Create: `datara-backend/rebuild/execution_metrics/`
- Create: `datara-backend/rebuild/stream_demo/`
- Create: `datara-backend/tests/rebuild/test_execution_metrics.py`
- Create: `datara-backend/tests/rebuild/test_stream_demo.py`

- [ ] **Step 1: 编写统计口径测试**

  断言工作流级、任务级、阶段级统计可汇总，重试不会重复累计，无法精确统计时标记 `unknown` 或 `estimated`。

- [ ] **Step 2: 创建统计表和错误样本表**

  创建 `workflow_result_stat`、`task_instance_data_stat`、`task_data_stat_segment`、`task_data_error_sample`，全部带数据库生成时间戳。

- [ ] **Step 3: 实现统一统计采集器**

  SQL 使用影响行数，Python/Shell 使用结构化返回，流任务记录 consumed/emitted/failed/dead-letter/lag/offset。

- [ ] **Step 4: 实现实时生产工作流**

  提供固定速率、异常、重复、延迟和乱序数据生产，连接消息队列、流处理、聚合、融合和结果存储。

- [ ] **Step 5: 实现观摩查询接口**

  返回生产速率、消费速率、积压、偏移、窗口结果、成功失败跳过和错误样本。

- [ ] **Step 6: 运行统计和流处理测试**

  ```powershell
  python -m pytest datara-backend/tests/rebuild/test_execution_metrics.py datara-backend/tests/rebuild/test_stream_demo.py -q
  ```

### A8. 独立 Backend 测试页面

**Files:**
- Create: `datara-web/src/views/rebuild/project/`
- Create: `datara-web/src/views/rebuild/workflow/`
- Create: `datara-web/src/views/rebuild/task/`
- Create: `datara-web/src/views/rebuild/variable/`
- Create: `datara-web/src/views/rebuild/sql-ide/`
- Create: `datara-web/src/views/rebuild/run/`
- Create: `datara-web/src/views/rebuild/stream/`
- Create: `datara-web/src/services/rebuild/`
- Test: `datara-web/tests/rebuild/`

- [ ] **Step 1: 建立 API 客户端和错误展示**

  所有测试页面只调用新 Backend API，统一显示请求 ID、错误码、生成时间和执行 ID。

- [ ] **Step 2: 按原版结构实现工作流和节点对照页**

  保留原版 Palette、DAG、节点双击弹窗、属性面板、运行页和日志查看器的主要交互，用新 API 驱动数据。

- [ ] **Step 3: 实现变量和试运行页**

  支持补全、当前值、变量覆盖、单节点运行、从节点运行和变量快照查看。

- [ ] **Step 4: 实现 SQL IDE 验证页**

  支持资源树、跨 Schema 补全、对象编辑、SQL 执行、结果网格、历史和导出。

- [ ] **Step 5: 实现运行统计和流观摩页**

  展示工作流统计、任务统计、错误样本、变量运行值、生产速率、消费速率和积压。

- [ ] **Step 6: 运行前端测试**

  ```powershell
  npm --prefix datara-web run test
  npm --prefix datara-web run build
  ```

### A9. Backend 冻结门禁

**Files:**
- Create: `docs/increments/rebuild-backend-freeze-checklist.md`
- Create: `datara-backend/tests/rebuild/test_freeze_contract.py`

- [ ] **Step 1: 固化接口快照**

  固化 OpenAPI、事件消息、节点配置、变量解析、错误码、分页协议和 AI 工具注册表/参数/返回结构/权限上下文/审计字段。

- [ ] **Step 2: 固化数据库快照**

  校验运行表时间戳、版本绑定、试运行隔离、统计口径和重试去重。

- [ ] **Step 3: 执行端到端验收**

  至少跑通：SQL、Python、Shell、同步、依赖、流观摩、试运行、正式运行、重试、取消、失败、统计汇总和 AI 假 Agent 工具调用；同时验证所有运行表的三类系统时间戳。

- [ ] **Step 4: 标记 Backend FROZEN**

  只有契约、测试页面和运行证据全部通过，才允许正式前端进入融合阶段。

### A10. 正式前端融合

**Files:**
- Modify: `datara-web/src/views/`
- Modify: `datara-web/src/components/`
- Modify: `datara-web/src/services/`
- Test: `datara-web/tests/e2e/`

- [ ] **Step 1: 将测试页面组件化**

  将已经通过验收的测试页面组件迁移为正式页面组件，不重新设计 Backend 契约。

- [ ] **Step 2: 融合原版 Palette 和节点弹窗**

  逐组件替换原页面，同时保留原版交互，并接入新节点配置和变量校验。

- [ ] **Step 3: 融合 SQL IDE**

  接入数据源树、跨 Schema 补全、对象编辑、执行结果、历史和文件资源。

- [ ] **Step 4: 融合运行中心**

  接入试运行、正式运行、变量快照、日志、数据行统计、错误样本和流处理观摩。

- [ ] **Step 5: 运行端到端回归**

  ```powershell
  npm --prefix datara-web run test:e2e
  ```

### A11. AI 悬浮助手

**Files:**
- Create: `datara-backend/rebuild/ai_copilot/`
- Create: `datara-web/src/components/rebuild/ai-assistant/`
- Test: `datara-backend/tests/rebuild/test_ai_tools.py`
- Test: `datara-web/tests/rebuild/ai-assistant.spec.ts`

- [ ] **Step 1: 定义工具调用契约**

  实现 `search_schema`、`validate_sql`、`run_sql`、`get_workflow`、`validate_workflow`、`inspect_workflow_run`、`get_task_metrics` 和 `get_lineage`。

- [ ] **Step 2: 接入当前页面上下文**

  悬浮助手自动携带当前项目、工作流、任务、SQL、数据源、变量、运行和血缘上下文。

- [ ] **Step 3: 实现结果组件**

  支持文本、表格、图表、日志、执行进度和配置草稿，不新增一级导航菜单。

- [ ] **Step 4: 运行 AI 工具测试**

  ```powershell
  python -m pytest datara-backend/tests/rebuild/test_ai_tools.py -q
  npm --prefix datara-web run test -- --run tests/rebuild/ai-assistant.spec.ts
  ```

### A12. 完成定义

- [ ] 每个增量均有数据模型、API 契约、后端实现、自动化测试和独立测试页面。
- [ ] 所有运行相关表具备 `created_at`、`updated_at`、`generated_at`。
- [ ] 草稿试运行和正式运行隔离，正式运行绑定已发布版本。
- [ ] 变量可以补全、校验、展示现时值，并在运行日志输出快照。
- [ ] SQL IDE 支持对象编辑和跨 Schema 查询。
- [ ] 同步支持探查映射和用户调整。
- [ ] SQL/Python/Shell 支持文件上传。
- [ ] 流处理有真实生产和观摩验证链路。
- [ ] 工作流结果支持成功、失败、跳过等数据统计。
- [ ] Backend 冻结前不修改正式前端。
- [ ] AI 工具契约、假 Agent 和悬浮助手验证在 Backend 冻结前完成；Backend 冻结后只允许做正式前端融合，不得新增或变更 AI/Backend 契约。
