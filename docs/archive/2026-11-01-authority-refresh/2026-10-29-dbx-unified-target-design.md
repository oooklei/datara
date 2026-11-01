---
design_type: phase
created_at: 2026-10-29
rewritten_at: 2026-10-30
---

# dbx 统一后的系统瘦身与目标设计

> 前提（已裁定）：
> - dbx 为唯一数据访问层（连接/查询/schema/MQ/ER/血缘/AI/历史）；dbx 是单用户工具，**连接与配置的 owner 化由 datara 薄后端治理**。
> - 编排采用 **方式 A**：DolphinScheduler 为 DAG/调度事实源，datara 编排网关为唯一业务入口。
> - 脚本开发与 dbx 对象树同源（按库/schema 粒度），双编辑入口。
> - 数仓建模与 dbx ER 等价；治理链（R5-B）作废。

## 一、前端：删除的功能与菜单

| # | 功能/菜单 | 路由 | 删除原因（→ 替代） |
|---|---|---|---|
| 1 | 数据源管理 | `/ds/list` | → dbx 连接管理 |
| 2 | 数据开发 IDE（旧实现） | `/ide`（复用） | → dbx SQL IDE（`/ide` 保留，见下方保留说明） |
| 3 | 数仓建模 | `/model/*` | → dbx ER 图（等价） |
| 4 | 血缘分析 | `/meta/lineage` | → dbx 血缘可视化 |
| 5 | 元数据目录 | `/meta/catalog` | → dbx schema 浏览 |
| 6 | 资产地图 | `/meta/asset-map` | → dbx schema + ER |
| 7 | LLM 模型配置 | `/open/llm` | → dbx AI |
| 8 | AI 助手（全局） | — | → dbx AI |

删除文件：`views/datasource/DataSourceListView.vue`、`views/dwmodel/*`、`views/meta/LineageAnalysisView.vue`、`views/meta/MetadataCatalogView.vue`、`views/meta/AssetMapView.vue`、`views/system/llm-models/*`；service：`datasourceApi.ts`、`sqlIdeApi.ts`、`sqlIdeDdlApi.ts`、`modelApi.ts`、`llmApi.ts`、`aiAgentApi.ts`、`aiToolsApi.ts`；菜单项：`ds-list`、`sql-ide`、`dw-modeling`、`meta-lineage`、`meta-catalog`、`meta-asset-map`、`llm-config`、`ai-assistant`。

> 保留（2026-10-30 用户裁定）：`views/ide/DbxIdeView.vue` 即 dbx SQL IDE 外壳（iframe `/ide/` + 变量面板），`/ide` 入口与 `dbxVariableBridge.ts` 一并保留，不作为删除项。

## 二、数据治理菜单（保留 10 项）

保留：标签、标准、指标目录、指标看板、一致性检查、质量规则、检查任务、异常数据核查、质量报告、质量告警。
- 指标/质量执行改走 dbx/编排（结果回写 datara 元数据库）。
- 后端：`rebuild/metrics/*` 保留；`rb/impact`、`rb/policy`、`rb/ledger`、`rb/lineage` 删除。

## 三、后端：删除与替换的 API

### 删除（由 dbx 承担）

| API 域 | 路由 | 替代 |
|---|---|---|
| 数据源 CRUD | `POST/GET/PUT/DELETE /api/v1/rebuild/projects/{id}/datasources[/{dsid}]` | dbx `/api/connection/{save,list,test}` |
| 数据源探针 | `POST /api/v1/rebuild/datasources/validate` | dbx `/api/connection/test-info` |
| 连接测试 | `POST .../datasources/{dsid}/test` | dbx `/api/connection/test` |
| 元数据浏览 | `GET .../datasources/{dsid}/{schemas,objects,columns}` | dbx `/api/schema/{columns,ddl,cache}` |
| SQL IDE / DDL 管控 | `/api/v1/rebuild/sql-ide-ddl/*` | 废弃（用 dbx 执行） |
| AI / LLM | `/api/v1/rebuild/llm-models`、AI router | dbx `/api/ai/*` |
| 数仓建模 | `/api/v1/rebuild/models`、`/model-dicts` | dbx ER |
| 血缘 | `rb/lineage` | dbx 血缘可视化 |
| 治理链 | `rb/policy`、`rb/ledger` | 废弃 |

### 删除（模块整体废弃）

- `rebuild/datasource/*`（pool/metadata/contracts/repository/models/dbx_sync）
- `rebuild/sql_ide/*`
- `rebuild/ai_bridge/*`、`rebuild/ai_agent/*`、`rebuild/ai_tools/*`、`rebuild/llm/*`
- `rebuild/model/*`
- `rebuild/rb/policy/*`、`rebuild/rb/ledger/*`、`rebuild/rb/lineage/*`

### 替换（改走 dbx / DolphinScheduler / 脚本运行时）

| API 域 | 路由 | 替换为 |
|---|---|---|
| 同步/流/即席执行 | `/api/v1/rebuild/{execution,sync,stream,trial}` | dbx `/api/query/{execute,execute-batch}` |
| 工作流/调度 | `/api/v1/rebuild/workflows`、schedule | DolphinScheduler |
| 依赖 | `/api/v1/rebuild/dependency` | DolphinScheduler 依赖 |
| 变量 | `/api/v1/rebuild/variables` | **保留并扩展为变量真源**，投影到海豚参数（见 §九） |
| 指标 | `/api/v1/rebuild/metrics` | DolphinScheduler 运行记录 + datara 元数据 |
| 组件目录 | `/api/v1/rebuild/components` | DolphinScheduler 任务节点定义 |
| 质量检查执行 | `qc` 执行入口 | dbx `/api/query/*` |
| 操作日志/审计执行 | — | dbx `/api/history/{search,save}` |

## 四、后端：保留与新增

**保留**
- 身份与连接治理：`login`、`logout`、`session`、`users`、`projects`、`members`、`permissions`
  - **连接与配置 owner 化**：admin 默认可见全部连接与配置；其他用户默认可见/可使用/可运行自己创建的连接与配置；**owner 支持显式共享**给指定用户。
- 安全：`/api/v1/rebuild/sec/*`（权限管理、访问审计）
- 开放：`/api/v1/open/*`（API-Key、API 管理）
- 脚本开发：`/api/v1/rebuild/scripts`（脚本存储与执行；对象树同源 dbx，按库/schema 粒度，双编辑入口）
- 变量域：`/api/v1/rebuild/variables`（七级变量定义/解析/校验，编排变量真源）
- 运维：`/api/v1/rebuild/{monitor,runtime-nodes,ssh-nodes}`
- 指标与质量：`/api/v1/rebuild/metrics`（执行走 dbx/编排）

**新增**
- 编排网关：DolphinScheduler 定义/触发/状态/调度查询（代理海豚 API）；Worker 分组/环境/Yarn 队列 CRUD（已实现）；**任务组 CRUD（R8，新增）**；**资源文件 CRUD（R9，新增）**；dbx 内部端点取连接参数（§10.9）

## 五、最终目标系统设计（干净）

> 仅描述「有什么」。

### 前端菜单

- **总览**：工作台
- **任务中心**：DolphinScheduler 编排视图（DAG 画布、运行实例、调度、变量、依赖、告警）
- **数据集成**：脚本开发（左侧 dbx 对象树，按库/schema 逐级查询；右侧脚本编辑器；双编辑入口）
- **数据治理**：标签、标准、指标目录、指标看板、一致性检查、质量规则、检查任务、异常数据核查、质量报告、质量告警（10 项）
- **项目管理**（顶栏）：项目列表、项目成员、项目级变量与配置、**任务组管理**（项目级，R8）
- **部署运维**（顶栏）：运行时节点、**监控中心**（原「集群监控」，含海豚 master/worker/DB 监控，见 §10.11）、SSH 节点、**Worker 分组**、**环境管理**、**Yarn 队列**、**集群管理**（见 §10.10）、**资源文件**（R9）
- **系统管理**（顶栏）：权限管理、访问审计、API 管理、API-Key 管理

### 后端

- **身份与连接治理**：用户/项目/成员/角色/权限；连接与配置 owner 化（admin 全见，其他人默认仅自己，支持显式共享）
- **安全**：权限管理、访问审计
- **开放平台**：API-Key、API 管理
- **脚本开发**：脚本存储与执行（对象树同源 dbx，按库/schema 粒度，双编辑入口）
- **部署运维**：运行时节点、监控中心（datara 自有节点监控 + 海豚 master/worker/DB 监控，见 §10.11）、SSH 节点
- **编排资源与运行环境**：Worker 分组 / 环境管理 / Yarn 队列 / 集群管理的代理与 owner 化治理（供节点表单下拉，见 §10.10）
- **编排网关**：对接 DolphinScheduler（DAG 定义、调度、触发、实例、日志）
- **变量域**：七级变量定义/解析/校验/投影（编排变量真源，运行时注入海豚）
- **指标与质量**：指标目录/看板/一致性 + 质量规则/任务/异常/报告/告警（执行走 dbx/编排）

### 外部依赖

- **dbx**：连接管理、查询执行、schema 浏览（库/schema 粒度）、MQ 管理、ER 图、血缘可视化、AI、操作日志（历史）
- **DolphinScheduler 3.4.3**：DAG/调度事实源（可视化 DAG、Cron、依赖、补数、告警、多租户、运行历史）；所有需要数据库的节点（SQL/PROCEDURE/DATAX/SQOOP/HIVE/POSTGRESQL/DB2/…）统一从 dbx 取连接参数后原生执行（见 §10.9）
- **脚本执行运行时**：Python/shell worker

## 六、编排融合（方式 A）

**架构**：datara 编排网关为唯一业务入口；DolphinScheduler 为 DAG/调度事实源。

```
前端 DAG 画布 → datara 编排网关 → DolphinScheduler API → Worker 原生执行
                    │                                        │
                    │                                        └─ 执行前 → dbx 内部端点取连接参数 → 内存构造
                    └─ owner 归属 / 权限校验 / dbx 连接绑定 / 变量注入 / 审计
```

**海豚 API 映射**（已核实控制器）
| datara 能力 | 海豚 API |
|---|---|
| DAG 定义/版本 | `WorkflowDefinitionController` |
| 任务/节点定义 | `TaskDefinitionController` |
| 调度 | `SchedulerController` |
| 触发/实例 | `ExecutorController`、`WorkflowInstanceController`、`TaskInstanceController` |
| 血缘 | `WorkflowLineageController` |
| 审计 | `AuditLogController` |
| 多租户/资源 | `TenantController`、`UsersController`、`ProjectController`、`QueueController`、`WorkerGroupController` |
| 变量/参数 | `ProjectParameterController` |

**要点**
- 海豚侧不存业务数据源；**所有需要数据库的节点**（SQL/PROCEDURE/DATAX/SQOOP/HIVE/…）的 `datasource` 字段统一存 dbx `connectionId`，datara 网关校验可见性。
- 执行前由海豚 master 从 dbx 内部端点取连接参数 → 内存构造 `DataSourceParameters` → 下发 worker 原生执行；**不引入自定义任务类型**。
- 前端画布：只取海豚的**编排可视化（DAG 画布，单页 iframe embed）+ 运行后台底座**，datara 提供外层壳与其余页面（见 §十），仍走 datara 编排网关。
- 多租户：海豚 tenant/user/project 与 datara 身份映射（或 SSO）。

## 七、实现路径

1. **P1 配置统一**：前端数据源页删除，连接管理入口切 dbx；密码托管迁移到 dbx；datara 只读镜像 dbx 连接（带 owner 过滤）；owner 共享机制上线。
2. **P2 执行代理化**：同步/即席/质量执行改走 dbx（按 connection_id，不传密码）；transform 下推 SQL。
3. **P3 编排与脚本开发落地**：DolphinScheduler 后台底座接入；编排网关上线；海豚 UI 改造（§10.8：dbx 数据源下拉、脚本库挂接、embed 模式、变量面板）；海豚后端数据源解析改走 dbx 内部端点（§10.9）；datara 脚本开发页上线（SQL→dbx；Python/shell→自选 SSH 节点试运行）；datara 实例/定义/血缘页上线；操作日志改读 dbx history；**部署运维资源环境页上线（worker 分组 / 环境管理 / Yarn 队列 / 集群管理，代理海豚 Controller，见 10.10）**；**监控中心扩展海豚 master/worker/DB 监控（代理 `MonitorController`）+ 海豚首页任务运行监控三张统计卡（代理 `DataAnalysisController`，见 10.11）**。
4. **P4 收尾**：datara 直连驱动与数据源模块物理删除；后端仅保留身份与连接治理/安全/开放/脚本开发/运维/编排网关/变量域/指标与质量。

## 八、脚本开发定义

- **页面结构**：左侧 dbx 对象树（**按每个库/schema 逐级查询**，同源 dbx `/api/schema/*`）+ 右侧脚本编辑器（SQL/Python/shell）+ 脚本存储与执行。
- **双编辑入口**：同一脚本存储，dbx IDE 与 datara 脚本开发均可编辑（共享存储/版本）。
- **owner 化**：脚本与配置按创建者归属，admin 全见，其他人默认仅自己，支持显式共享。

**执行分流（三类脚本，各一条路径）**

| 脚本类型 | 试运行（即时反馈） | 正式运行（走 DAG 调度） |
|---|---|---|
| **SQL** | dbx `/api/query/*`（按 connectionId，不传密码） | 海豚原生 SQL 节点 → worker 原生执行（执行前从 dbx 内部端点取连接参数，见 §10.9） |
| **Python** | 用户**自选可试运行的 SSH 节点**（datara SSH 主机注册表，按 owner 可见性过滤）→ 上传脚本到该主机临时目录 → 执行 → 回传 stdout/stderr/退出码 | 海豚原生 PYTHON 节点，按其**worker 组**运行（海豚在组内分派机器） |
| **shell** | 同上，用户自选 SSH 节点试运行 | 海豚原生 SHELL 节点，按其**worker 组**运行 |

试运行与正式运行是**功能分流**：试运行要即时交互反馈、不经过 DAG 调度，正式运行要走 worker 组分派、日志归档、失败重试。两条路径天然不同，不是一个功能两头跑。

- **「可试运行的 SSH 节点」**：datara 资源管理里的 SSH 主机条目，带 `owner / 可见范围 / 是否允许试运行` 标记；试运行选择器只列当前用户可见且允许试运行的主机。
- **正式运行的位置**：**复用海豚 worker 组**，不新增工作站概念。节点表单选 worker 组（一个组可含多台机器），由海豚在组内分派，与海豚原生语义一致；`worker 组` 与 `datara SSH 主机` 的对应关系由运维在两侧维护（同机不同名或组内子集），不做运行时耦合。
- **运行位置类节点**：`SHELL`/`PYTHON`/`REMOTESHELL` 的正式运行位置统一为节点表单所选 **worker 分组**（海豚原生字段）；其中 `REMOTESHELL` 去掉 SSH 数据源、改本地执行（见 10.8 M10）。
- **试运行与正式运行互不约束**：试运行选哪台 SSH 主机，不影响正式跑在哪个 worker 组的哪台机器；避免「试运行通、上线跑到别处」的错觉——这一点在 UI 上明确提示。
- **与海豚关系**：脚本以**脚本 ID 引用**方式挂接到海豚对应类型节点（见 §10.8），不在海豚侧复制脚本正文；执行时由节点解析脚本 ID → 取正文/版本 → 下发到该节点 worker 组的机器执行。

## 九、编排变量贯穿（海豚 DAG 视图改造）

### 9.1 目标

| # | 目标 | 验收信号 |
|---|---|---|
| V1 | 系统变量体系贯穿 | DAG 任意节点可用 `${run.x}` / `${task.x}` / `${workflow.x}` / `${project.x}` / `${env.x}` / `${global.x}` / `${builtin.x}` 与 `$[time]`，取值符合七级优先级 |
| V2 | 工作流变量自身可定义 | DAG 视图内可新增/编辑/删除 workflow 与 task 作用域变量，保存即校验 |
| V3 | 运行时变量值输出到日志 | 任务日志含最终参数快照；运行详情含工作流级变量快照；敏感值脱敏 |

### 9.2 参数映射（海豚 3.4.3）

| datara scope | 海豚载体 | 注入方 |
|---|---|---|
| run | 命令参数（`start-process-instance` / `execute`） | 编排网关 |
| task | 节点 `localParams` | DAG 视图保存时投影 |
| workflow | 工作流定义 `globalParams` | DAG 视图保存时投影 |
| project | 项目参数 | 变量域同步 |
| env | 无对应，走命令参数（限定键） | 编排网关 |
| global | 无对应，走命令参数（限定键） | 编排网关 |
| builtin | 海豚内置参数保留；datara 侧补 `builtin.*` | 编排网关 |
| tmp | 不注入（运行时瞬态） | — |

### 9.3 注入协议

- **解析时机**：网关触发前用变量域 `resolve_all(context)` 一次性解析完七级链，产出扁平 map。
- **键格式**：`scope.name`（如 `workflow.dt`、`env.region`）。海豚占位符是扁平 map 查找且内置键本就带点号（`system.biz.date`），限定键可直接被 `${...}` 命中。
- **裸名别名**：同时注入每个变量名按优先级裁决后的**胜出值**（如 `dt`），保证海豚原生 `${dt}` 与存量 DAG 继续可用。
- **顺序无关**：同名冲突已在 datara 侧裁决完毕，海豚「命令 > local > global > project」的合并顺序不再影响正确性。
- **时间表达式**：`$[time]` 与海豚 `TimePlaceholderUtils` 语法一致，直接复用，不另造轮子。
- **校验**：`SYNTAX / UNDEFINED / TYPE_MISMATCH / SCOPE_INVISIBLE / CYCLE` 五种诊断码任一命中即拒绝发布 DAG。

### 9.4 DAG 视图改造点（海豚 UI 源码）

| 位置 | 改造内容 |
|---|---|
| 工作流定义创建/编辑表单 | 新增「变量」步骤：七级变量列表（只读展示 project/env/global/builtin）、workflow 作用域增删改（name/type/value/default/nullable/sensitive/description） |
| DAG 节点侧栏 | 新增「变量」页签：task 作用域定义 + 上游 OUT 引用（对应 `varPool`） |
| 运行实例详情 | 变量页签增强：标注来源 scope、生效值、脱敏标记，支持导出 |
| 前端 API 层 | 新增变量代理模块，转发到 datara 编排网关（不直连变量域，避免绕过 owner 校验） |
| 保存闸门 | 保存/发布前调用校验接口，诊断码非空即阻断并定位到具体节点 |

### 9.5 持久化与投影

- **真源**：datara 变量域。workflow 作用域绑工作流定义 code，task 作用域绑节点 code。
- **投影方向**：保存 DAG 时，workflow 变量写入海豚 `globalParams`（限定键 `workflow.*`），task 变量写入节点 `localParams`（限定键 `task.*`）。
- **反向导入**：存量海豚 DAG 的 `globalParams` / `localParams` 导入为 datara 变量定义（保留裸名并标记 legacy），保证存量可运行。
- **一致性**：以 datara 变量域为准；海豚侧参数被视为投影产物，UI 编辑一律回写变量域。

### 9.6 运行时日志输出

- **任务级**：SQL/DataX/Sqoop/Hive 等原生节点插件与 shell/python worker 包装在启动时打印最终参数 map（`prepareParamsMap`），`sensitive` 变量输出为 `***REDACTED***`。
- **工作流级**：网关在触发成功后写入变量注入快照（含各 scope 来源与生效值），运行详情变量页签读取该快照。
- **不改造海豚内核**：`CuringParamsServiceImpl` 的合并逻辑保持原样，靠「网关注入 + 任务插件打印」实现，避免内核分叉导致升级成本。

### 9.7 边界

- 海豚不存业务数据源；敏感变量值由网关运行时注入，不落海豚元数据库明文。
- env/global 作用域只在 datara 侧定义，海豚 UI 只读展示。
- 变量快照与日志同生命周期，随运行记录归档与清理。

## 十、海豚嵌入设计（任务中心）

### 10.1 裁定与目标

| # | 裁定 | 说明 |
|---|---|---|
| E1 | **只用海豚的「编排可视化 + 运行后台底座」** | 取海豚两样东西：①DAG 画布（编排可视化）；②master/worker/api/元数据库（运行底座）。**不取**海豚的整套门户外壳（登录、用户/租户管理、数据源、审计、监控大盘、项目管理体系）——这些 datara 已有或已替代 |
| E2 | 嵌入形态 | **单页画布 iframe（embed 模式）**：只加载 DAG 画布路由，隐藏海豚自身导航/头部；datara 提供外层壳、菜单、项目与身份上下文。与 dbx IDE 集成同构 |
| E3 | 免登打通 | 用户只登 datara；海豚侧无登录页、不校验密码/会话 |
| E4 | 禁用海豚鉴权 | datara 持固定内部令牌（同 dbx D8）调用海豚；海豚侧新增内部信任通道 |
| E5 | 关闭海豚审计 | `api.audit-enable: false`（`application.yaml` L144 已就绪）；编排操作审计由 datara 侧记录 |
| E6 | 联调环境 | 本地源码联调（`D:\dolphinscheduler-dev`）；部署/E2E 在 192.168.1.9 隔离工作目录 |
| E7 | 完整性 | DAG 画布须连带其**全部配套元素**一并嵌入：组件与页面、相关配置/展示/设定；最终必须**可设计、可试运行、可调度运行**（见 10.7 验收） |
| E8 | 数据源唯一真源 | 海豚侧**所有需要数据库实例的节点组件**（SQL/PROCEDURE/DATAX/SQOOP/DB2/POSTGRESQL/HIVE/…）的数据源，一律挂接 **dbx 连接**，不使用海豚自有数据源表 `t_ds_datasource`。**例外**：运行位置类节点（`SHELL`/`PYTHON`/`REMOTESHELL`）不挂数据源，统一挂 **worker 分组**（见 10.8 M10） |

### 10.2 海豚鉴权链（已核实源码）

| 环节 | 位置 | 行为 |
|---|---|---|
| 拦截注册 | `AppConfiguration#addInterceptors` L104-110 | `loginInterceptor` 挂在 `/**/*`，排除 `/login/**`、`/users/register`、swagger、`/ui/**`、`/error`、oauth2 等 |
| 拦截实现 | `LoginHandlerInterceptor#preHandle` L64-96 | 取 `token` header；无则 `authenticator.getAuthUser(request)`；用户为空/停用 → 401；否则写 `Constants.SESSION_USER` |
| 会话解析 | `AbstractAuthenticator#getAuthUser` L114-132 | `sessionId` header → 否则 `sessionId` cookie → `SessionService.getSession` → `User` |
| 会话存储 | `SessionServiceImpl`（`SessionDao`） | 会话落海豚库（`t_ds_session`），非 Redis |
| 审计开关 | `application.yaml` L139-144 | `api.audit-enable: false`；`api.base-url`、`api.ui-url` |

**结论**：海豚无「按用户创建会话」的 REST 端点；要免登必须由 datara 侧注入可信身份。

### 10.3 免登打通（禁用海豚鉴权）

**方案**：datara 持有固定内部令牌（与 dbx D8 同构），海豚侧新增**内部信任通道**，跳过密码/会话校验。

**海豚实例（1.9 隔离环境）**：UI 入口 `http://192.168.1.9:12345/dolphinscheduler/ui`；API 根 `http://192.168.1.9:12345/dolphinscheduler`。编排网关以此为基础地址：`/ui/**` 静态资源由 datara 反代（`/ds-ui/**`），`/projects/**`、`/monitor/**` 等 API 统一经编排网关代理（10.3 内部信任通道）。

- **海豚侧补丁（唯一内核改动）**：`LoginHandlerInterceptor#preHandle` 增加前置分支——请求头带 `X-Datara-Internal-Token`（预共享密钥）时，从 `X-Datara-User` 解析海豚用户名 → `userService.queryUser(userName)` → 写 `SESSION_USER`，直接放行；否则走原生 token/session 逻辑。
  - 令牌校验失败 → 401，**不回落**原生逻辑（避免越权）。
  - 海豚用户名映射：datara 用户 → 海豚用户（1:1 或映射表），由 datara 编排网关维护。
- **datara 编排网关**：所有对海豚 API 的调用统一加 `X-Datara-Internal-Token` + `X-Datara-User`；同时完成 owner 校验、变量注入、审计。
- **海豚 UI 嵌入**：iframe 内海豚 UI 的 axios 层（`dolphinscheduler-ui/src/service/service.ts` L86 已有 `config.headers.set('sessionId', ...)`）改为优先设置内部头；凭证由宿主经 postMessage 下发（见 10.4）。

### 10.4 嵌入机制（单页画布 iframe + postMessage 桥）

**形态**：datara 任务中心是一个 iframe，`src` 指向海豚的**单个 DAG 画布路由**并带 `?embed=1`；海豚 UI 在 embed 模式下隐藏自身左侧导航与顶部栏（仅一处 CSS/条件渲染改动），只渲染画布本体及其弹窗/抽屉。

**为什么不是整站嵌入**：E1 已裁定只取「编排可视化 + 运行底座」。整站嵌入会把海豚的用户/租户/数据源/审计/监控一起带进 datara，与 dbx 承担数据源、datara 承担身份与审计相冲突，且形成两套导航。

**为什么不是源码级组件移植**：海豚画布依赖 pinia store、x6、naive-ui、i18n 与路由参数，整块搬迁等于重写；iframe + embed 模式只改条件渲染，升级成本最低。

- **宿主**：`views/task/TaskCenterView.vue` 承载 iframe，负责：
  - 项目/环境组上下文（datara 项目 → 海豚 `projectCode` 映射）
  - 免登凭证下发（postMessage `datara:ds-session`）
  - 变量桥（复用 §九 变量域，只读注入）
  - 画布路由切换（打开哪个 DAG、新建、从列表点进来）
- **海豚侧**：新增 `useDataraBridge.ts`，监听 `datara:ds-session` → `userStore.setSessionId(...)`（`store/user/user.ts` L46-47）+ 设置内部头；新增 `embed` 模式开关（路由 query 或注入的全局标记）。
- **静态资源与 API 代理**：datara 反代 `/ds-ui/**` → 海豚 UI；`/dolphinscheduler/**` → 海豚 API（或由编排网关统一收口）。
- **同源化**：iframe 与宿主同域（datara 域），规避跨域 cookie/自定义头限制。
- **画布内的配套元素留在画布内**：节点侧栏/节点表单/试运行弹窗/定时弹窗/版本下拉/日志抽屉都属画布自身，随画布一起可用，**不拆到 datara 页面**——拆开就断闭环。

### 10.5 编排面归属（谁提供哪一页）

**A. 画布内保留（随 iframe 一起，海豚 UI 自带）**

| 元素 | 海豚来源 |
|---|---|
| DAG 画布本体（节点/连线/缩放/对齐/树形图/格式化） | `views/projects/workflow/definition/components/dag/*`（x6） |
| 节点侧栏与任务类型面板 | `store/project/task-type.ts` `TASK_TYPES_MAP` + `views/projects/task/components/node/tasks/*` |
| 节点表单（参数/资源/依赖/自定义参数/超时/优先级） | `views/projects/task/components/node/*` |
| 试运行弹窗（`whether_dry_run` 开关 + 启动参数） | `views/projects/workflow/definition/components/start-modal.tsx` |
| 定时弹窗（Cron/时区/上下线） | `views/projects/workflow/definition/timing/*` |
| 版本下拉、保存/发布、上线/下线 | 画布工具栏 |
| 任务日志抽屉 | 画布/实例页共用 |

**B. datara 自建页面（调海豚 API，不进 iframe）**

| datara 页面 | 依赖海豚 API | 说明 |
|---|---|---|
| 工作流定义列表 | `WorkflowDefinitionController`（分页/查询/删除/复制） | datara 自己的列表与筛选（owner/项目） |
| 工作流实例 / 任务实例列表与详情 | `WorkflowInstanceController`、`TaskInstanceController` | 含甘特图、重跑/停止/恢复/失败重试 |
| 工作流关系/血缘 | `WorkflowLineageController` | 复用海豚血缘数据，datara 渲染 |
| 项目参数（→ datara 变量域） | `ProjectParameterController` | 真源在 datara 变量域（§九） |
| **告警配置** | **不用海豚告警 API** | **沿用旧前端告警配置（邮件/短信等）**；海豚任务/实例失败由编排网关感知 → 按 datara 告警规则发送（见 §10.10） |
| 资源文件 / UDF | 海豚资源 API | 与 datara 资源管理合并展示 |
| Worker 分组 / 环境 / Yarn 队列 / 集群 | 对应 Controller | 由 datara「部署运维」页面承载（见 §10.10） |

**C. 不接入**

海豚登录页（E3）、审计日志页（E5，datara 承担）、数据源页（dbx 承担）、用户管理（datara 身份承担）。
**海豚监控大盘页（`/monitor/*`）不进 iframe**，其 master/worker/DB 监控数据由 datara「监控中心」承载（见 10.11）。
**海豚首页 `/home`（任务运行监控）不进 iframe**，其任务实例/工作流实例/工作流定义三张统计卡由 datara「监控中心」承载（见 10.11）。

### 10.6 边界与不做

- **内核/前端源码改动**只限六处：10.3 内部信任分支、10.4 embed 模式开关、10.8 M3 数据源下拉、10.8 M10 REMOTESHELL 执行路径、10.8 M11 Yarn 队列 input→select、10.9 数据源解析改走 dbx。其余内核逻辑不动，升级成本可控。
- 海豚不存业务数据源；所有需要数据库的节点 `datasource` 字段统一存 dbx `connectionId`。
- 不接入海豚登录页/审计页/用户管理/监控大盘/首页（任务运行监控）；这些由 datara 承担。
- **不接入海豚告警管理/告警实例/实例管理页**：告警沿用 datara 旧前端配置（邮件/短信），实例由 datara 自建页承载（见 10.10）。
- 不改海豚的调度算法、worker 执行模型、DAG 存储结构。
- **不新增自定义任务类型**（`DynamicTaskTypeController` 不用）；SQL/DataX/Sqoop/Hive 等全部走原生节点 + dbx 连接参数。

### 10.7 验收标准（可设计 / 可试运行 / 可调度运行）

三条闭环必须在 datara 宿主内**不跳出 iframe、不二次登录**完成；每条都绑定已核实的海豚入口。

| # | 能力 | 验收动作（全部在 datara 任务中心 iframe 内完成） | 依赖海豚入口 |
|---|---|---|---|
| A1 | **可设计** | 新建/打开 DAG → 拖节点 → 配节点表单（参数/资源/依赖/自定义参数）→ 连线 → 保存 → 重新打开内容一致 | 画布路由 `/projects/:code/workflow/definitions/:code` |
| A2 | 可设计（脚本挂接） | Python/shell 节点可从 datara 脚本库选脚本挂上；保存后重开仍指向同一脚本 ID | 10.8 节点表单脚本选择器 |
| A3 | 可设计（数据源） | **任意**含数据源字段的节点（SQL/PROCEDURE/DATAX/SQOOP/DB2/…）数据源下拉均来自 dbx 连接（按 owner 可见性过滤）；选中项回写 `datasource = connectionId`；节点表单的「数据源类型」随所选 dbx 连接自动带出。**PROCEDURE 同此**（其 `type` + `datasource` 双字段由共享字段统一接管） | 10.9 数据源挂接 |
| A4 | 可设计（运行位置） | 运行位置类节点（`SHELL`/`PYTHON`/`REMOTESHELL`）只出现 **worker 分组**下拉（海豚原生字段）；`REMOTESHELL` **不再出现数据源选择**；保存后重开仍指向同一 worker 组 | 10.8 M10 |
| B1 | **可试运行** | 画布「试运行」开关置真 → 启动 → 生成实例 → 任务实例日志可见 → 结果符合预期（`dryRun=1` 语义） | `ExecutorController` L146/L265 `dryRun`；`start-modal.tsx` `whether_dry_run` |
| B2 | 可试运行（脚本） | 脚本开发页对 Python/shell 选一台**允许试运行的 SSH 节点**执行，回传 stdout/stderr/退出码；选择器不含无权限主机 | §八 执行分流 |
| C1 | **可调度运行** | 配置 Cron → 上线定时 → 定时触发实例 → 实例/任务实例/甘特图可查 → 停止/重跑/恢复可用 | 定时弹窗 + datara 实例页 |
| C2 | 可调度运行（位置） | **SHELL / PYTHON / REMOTESHELL** 节点正式运行落在**该节点所选 worker 组**的机器上（海豚原生下拉），与试运行所选 SSH 主机无关 | 节点表单 worker 组（海豚原生，三者均已带 `Fields.useWorkerGroup`） |
| C3 | 可调度运行（资源可选） | 在「部署运维」建好 worker 分组与环境后，节点表单的 worker 组下拉与环境下拉均出现对应项且保存后回读一致；未建分组/环境时下拉为空并给出明确提示而非报错 | 10.10 R1/R2；datara 部署运维页 |
| D1 | 免登 | 三条闭环全程无海豚登录页、无密码输入；datara 切换项目后 iframe 上下文随之切换 | 10.3 内部信任通道 |
| D2 | 审计归属 | 海豚审计页不出现；datara 侧可查到本次设计/试运行/调度的操作记录 | E5；datara 编排网关 |
| D3 | 变量桥 | §九 变量在节点表单中可只读查看并按解析链生效（节点参数 > 工作流变量 > 环境组 > 全局） | 10.4 postMessage 桥 |
| D4 | 单壳 | iframe 内不出现海豚左侧导航/顶部栏；datara 只有一套导航 | 10.4 embed 模式 |
| E1 | 监控中心 | 部署运维 → 监控中心可见 datara 运行时节点 **与**海豚 master 节点 / worker 节点 / DB 连接池三区块；master/worker 显示心跳时间与离线标记；点节点下钻运行中实例只读可查；海豚监控大盘页不出现 | 10.11；`MonitorController` 四个端点 |
| E2 | 监控中心（任务运行监控） | 监控中心可见海豚首页同源的三张统计卡：任务实例状态统计（时间区间可切换）、工作流实例状态统计（时间区间可切换）、工作流定义统计（按用户）；状态文案/配色与 datara 一致；海豚首页 `/home` 不出现 | 10.11；`DataAnalysisController` 三个端点 |

**判定**：A1–A3 / B1–B2 / C1–C3 / D1–D4 / E1–E2 全绿 = 海豚集成走通。任一不绿即为阻断项，不得以「单页 iframe 能打开」替代验收。

### 10.8 海豚改造清单（脚本挂接 + 数据源挂接）

用户要求：datara 里创建的脚本，要能在海豚**对应类型的节点**里挂接上。已核实海豚任务面板是**前端硬编码白名单**驱动，新数据源下拉必须改源码。

| # | 位置 | 现状（已核实） | 改造 |
|---|---|---|---|
| M1 | `store/project/task-type.ts` L25-167 `TASK_TYPES_MAP` | 前端硬编码任务类型白名单；`setTaskTypes` L184 用 `filter((type) => !!TASK_TYPES_MAP[type])` **过滤掉未知类型** | **不改**：保持海豚原生类型全集，不新增任何自定义任务类型条目 |
| M2 | **删除**（原计划新增 `use-dbx-sql.ts`） | — | **取消**：所有 SQL 类节点直接用海豚原生 `tasks/use-sql.ts`，其数据源字段由 M3 统一接管 |
| M3 | `views/projects/task/components/node/fields/use-datasource.ts` | **共享字段**：L195 `params.sourceField \|\| 'datasource'`，被所有含数据源的任务类型复用；L190 `queryDataSourceList` 调海豚 `/datasource`，`value = item.id`；L39 `datasourceTypes` 为海豚枚举。**PROCEDURE 也走这里**（`tasks/use-procedure.ts` L66 `Fields.useDatasource(model)`，`model.type` 默认 `MYSQL` + `model.datasource`） | 改一处即覆盖全部任务类型：L190 改调 datara 编排网关「dbx 连接列表」，`value` 用 dbx `connectionId`；L39 类型清单改由所选连接的 dbx 类型带出（只读） |
| M4 | Python 节点表单（`tasks/use-python.ts`） | 只有脚本文本框 + 资源引用 | 新增「从脚本库选择」：调 datara 脚本库（按类型 `python` 过滤、owner 可见性过滤）→ 回写 `scriptId` + 只读展示脚本名/版本；同时保留手写脚本作为兜底 |
| M5 | shell 节点表单（`tasks/use-shell.ts`） | 同上 | 同上，类型过滤 `shell` |
| M6 | worker 侧 Python/shell 任务执行 | 海豚 worker 直接执行脚本文本 | 执行前若节点带 `scriptId`，经 datara 编排网关取脚本正文/版本（内部令牌），再在当前 worker 执行；取不到则任务失败并给出明确诊断码 |
| M7 | 节点运行位置 | 海豚已有 worker 组，无需新增 | **不改**：复用海豚原生 worker 组字段（一个组多台机器，组内分派）；不引入「工作站」新概念 |
| M8 | 画布 embed 模式 | 无 | 路由 `?embed=1` 时隐藏左侧导航与顶部栏（10.4） |
| M9 | `TaskExecutionContextFactory`（master）及数据源任务插件 | 原实现用 `Integer` 数据源 ID 和 `findDataSourceById(code)` | `datasource` 直接存 dbx 字符串 `connectionId`；各任务插件参数、资源收集和运行上下文统一改为字符串，master 按字符串调用 datara 内部接口解析，不建立整数映射（详见 10.9） |
| M10 | 运行位置类节点：`SHELL`（`tasks/use-shell.ts` L59）、`PYTHON`（`use-python.ts` L60）、`REMOTESHELL`（`use-remote-shell.ts` L58） | 三者**原生都已挂** `Fields.useWorkerGroup(projectCode)`（一个组多台机器，海豚在组内分派）；其中 `REMOTESHELL` 额外挂了 SSH 数据源（L65-67） | **统一挂 worker 分组**：`SHELL`/`PYTHON` **无需改造**（原生 worker 组字段即正式运行位置，与 §八 执行分流一致）；`REMOTESHELL` **去掉 SSH 数据源字段**，只保留 worker 分组，worker 侧 `RemoteShellTask` 不再按 `datasource` 建 SSH 连接，改为在被分派的 worker 机器上本地执行（与 SHELL 节点同路径）。**REMOTESHELL 不参与 10.9 的 dbx 数据源改造** |
| M11 | `fields/use-queue.ts`（F6） | 原生 `type: 'input'`（L24），让用户手填 yarnQueue 字符串 | 改为 `type: 'select'`，`onMounted` 调 datara 编排网关 `GET /orchestration/queues`（已实现 Queue CRUD）填充 options；Yarn 节点表单的 yarnQueue 字段从手填改为下拉选（详见 §10.10 F6） |

**一致性约束**：`scriptId` 只存引用，不复制正文；脚本改版本后 DAG 是否跟随由节点上的「锁定版本」开关决定（默认锁定，避免线上脚本被悄悄改掉）。

### 10.9 数据源挂接（dbx 唯一真源）

**目标（E8）**：海豚里**凡是需要数据库实例的节点组件**——`SQL`、`PROCEDURE`、`DATAX`、`SQOOP`、`DB2`、`POSTGRESQL`、`HIVE`、`SPARK` 等凡 `params` 带 `sourceField` 的任务类型——数据源一律来自 **dbx 连接**，不再使用海豚 `t_ds_datasource`。

**范围例外**：`REMOTESHELL` 不走数据源，改挂 **worker 分组**（M10），因此**不在本节改造范围**。

**PROCEDURE 的特别说明**：它有两个字段——`type`（数据源类型，`tasks/use-procedure.ts` L47 默认 `MYSQL`）与 `datasource`（实例，L48），两者都由共享字段 `Fields.useDatasource(model)`（L66）产出。改造后由「所选 dbx 连接」一次性带出 `type`（只读）并回写 `datasource = connectionId`，无需为 PROCEDURE 单独写表单逻辑。

**源码接线点**（已核实 3.4.3 源码；2026-10-30 用户裁定直接存字符串 ID）

| 层 | 位置 | 事实 |
|---|---|---|
| 前端 | `node/fields/use-datasource.ts` L195 | 所有含数据源的任务类型共用该字段（`params.sourceField \|\| 'datasource'`），只有 L190 一处调 `/datasource` |
| master | `TaskExecutionContextFactory` | 按字符串 `connectionId` 从 datara 内部接口取得 `DataSourceParameters`，不再查 `t_ds_datasource` |
| 任务插件 | SQL、PROCEDURE、DATAX、CHUNJUN、SQOOP 等含数据源字段的参数与执行上下文 | 原字段/资源键为 `Integer`；统一改为 `String`，保存、序列化、资源收集、worker 执行均保留原始 `connectionId` |

**改造**

1. **前端（M3）**：L190 改调 datara 编排网关 `GET /api/v1/rebuild/orchestration/datasources`（返回当前用户可见的 dbx 连接：`{id, name, type, host, database}`）；`value` 用 dbx `connectionId`；「数据源类型」由所选连接带出并置为只读。节点表单不再提供「新建数据源」入口。
2. **master 与任务插件（M9）**：任务参数中的 `datasource`、Sqoop 源/目标和所有相关执行上下文字段直接保存 dbx 字符串 `connectionId`；扩展 `ResourceParametersHelper` 的字符串键通道，master 调用编排网关 `GET /internal/dbx/connections/{id}/params`，返回 `{type, connectionParams}` 并组装 `DataSourceParameters`。SQL、PROCEDURE、DATAX、CHUNJUN、SQOOP 等相关插件必须同步改造和编译验证；禁止引入整数代理 ID。
3. **类型映射**：dbx 连接类型 → 海豚 `DbType` 枚举需一张映射表（如 `mysql→MYSQL`、`postgresql→POSTGRESQL`、`oracle→ORACLE`、`clickhouse→CLICKHOUSE`、`hive→HIVE`）；映射缺失时任务在**保存期**即报错，不留到运行期。

**密码传递方案（唯一决策）**

海豚 worker 要建 JDBC 连接，`DataSourceParameters.connectionParams` 必须含**明文密码**；而 dbx 的既定约束是「密码只存 dbx、永不外泄」。两者直接矛盾，采用：

**dbx 新增内部专用端点** `GET /internal/connection/{id}/params`：仅接受固定内部令牌 + 仅白名单内网 IP（DS master/worker 主机），返回含密码的连接参数，每次调用落审计。

密码只在 master 内存中构造 `DataSourceParameters` 并下发 worker，**不落海豚元数据库**；`t_ds_datasource` 保持空表。

**边界**

- 连接可见性：编排网关按 owner 过滤，用户看不到他人未共享的连接；即便知道 id 也取不到参数。
- 连接测试统一走 dbx `/api/connection/test`，海豚侧 `/datasource/test` 不暴露给用户。
- 数据源删除/改密在 dbx 侧完成后即时生效，海豚侧无需同步动作（每次运行前实时解析）。

### 10.10 部署运维与项目级：海豚节点表单外部引用字段全覆盖

#### 节点表单外部引用字段全景（海豚原生，已核实源码）

海豚 DAG 画布每个节点表单上的下拉选择器，对应的是一套**独立管理的外部资源**。下表列出所有与"选"相关的字段（排除内联参数 `localParams`/`customParams` 和静态枚举）：

| # | 字段 | 类型 | 写入节点 | 海豚原生端点 | datara 编排网关 | datara 前端配置页 | 归属维度 | owner 规则 |
|---|---|---|---|---|---|---|---|---|
| **F1** | `workerGroup` | select（必填） | SHELL/PYTHON/REMOTESHELL/JAVA/… | `GET /projects/{code}/worker-group` | ✅ 已有 CRUD | ✅ 部署运维 → R1 Worker 分组 | 全局资源 | admin 全见；显式共享 |
| **F2** | `environmentCode` | select（按 workerGroup 过滤） | 所有类型 | `GET /environment/query-environment-list` | ✅ 已有 CRUD | ✅ 部署运维 → R2 环境管理 | 全局资源（绑定 workerGroup） | 同 F1 |
| **F3** | `datasource` + `type` | select ×2（必填） | SQL/PROCEDURE/DATAX/SQOOP/HIVE/… | 已改调 **datara** `/orchestration/datasources` | ✅ 代理 dbx 连接 | ✅ dbx 连接管理（只读镜像） | dbx 连接 | dbx owner 化 |
| **F4** | `taskGroupId` + `taskGroupPriority` | select + int | 所有类型 | `GET /task-group/query-list-by-projectCode` | ❌ **缺失** → R8 | ❌ 项目管理 → R8 任务组 | **项目级** | 项目 owner 全见；显式共享 |
| **F5** | `resourceList` | tree-select（多文件） | JAVA/SPARK/FLINK/… | `GET /resources/list?type=FILE` | ⚠️ 仅 share，**缺失 CRUD** → R9 | ❌ 部署运维 → R9 资源文件 | 全局文件树 | admin 全见；显式共享 |
| **F6** | `yarnQueue` | 原生是 input 文本框 | SPARK/FLINK/SEA_TUNNEL | 无（原生手填） | ✅ 已有 Queue CRUD | ✅ 部署运维 → R3 Yarn 队列 | 全局资源 | admin 全见；显式共享 |
| F7 | `taskPriority` | select（静态枚举） | 所有类型 | 无（原生写死 HIGHEST→LOWEST） | — | — | 静态值 | — |
| F8 | `preTasks` | select（当前 DAG 节点） | 所有类型 | 无（运行时 taskStore） | — | — | DAG 内部引用 | — |

**缺口即方案来源**：F4 后端前端全缺、F5 CRUD 缺、F6 有后端前端但节点表单还是 input。F1/F2/F3 已闭环。F7/F8 是内部引用，不产生缺口。

#### 配置项全集（部署运维 + 项目级）

| # | 配置项 | 必要性 | 海豚来源 | datara 页面 | 归属 | 生效条件 / 备注 |
|---|---|---|---|---|---|---|
| **R1** | **Worker 分组** | **必须** | `WorkerGroupController` | 部署运维 → Worker 分组 | 全局 | F1 下拉来源；分组 = 一组 worker 机器 |
| **R2** | **环境管理** | **必须** | `EnvironmentController` | 部署运维 → 环境管理 | 全局（绑 workerGroup） | F2 下拉来源；变量解析链含环境组级（§九） |
| **R3** | **Yarn 队列** | **条件必须** | `QueueController` | 部署运维 → Yarn 队列 | 全局 | F6 原生是 input 文本框；需改海豚前端 `use-queue.ts` 为 select，调 datara `/queues` |
| **R4** | **集群管理** | **条件必须** | `K8sNamespaceController` | 部署运维 → 集群管理 | 全局 | 仅 K8s 系任务生效 |
| **R5** | **K8S 命名空间** | **暂不必要** | — | 不单列菜单项 | — | 见下方判断 |
| **R6** | 告警管理 | **不采用** | — | 沿用旧前端配置 | — | 见下方桥接 |
| **R7** | 实例管理 | **不采用** | — | datara 自建页（10.5 B） | — | — |
| **R8** | **任务组** | **必须**（新增） | `TaskGroupController` + `t_ds_task_group` | **项目管理 → 项目详情** → 任务组管理 | **项目级** | F4 下拉来源；同一 taskGroup 内节点按 taskGroupPriority 串行；不同组并行。**按 projectCode 隔离** |
| **R9** | **资源文件** | **条件必须**（新增） | `ResourceController` + 海豚资源文件系统 | 部署运维 → 资源文件 | 全局文件树 | F5 树选择器来源；存放 jar/py/sh 等依赖文件；跨项目共享 |

#### R8 任务组（新增，P0）

海豚语义：同一 `taskGroup` 内的节点按 `taskGroupPriority` **顺序串行执行**（不是并行）；不同 taskGroup 之间并行。这是海豚控制"哪些任务必须串行"的核心机制。

| 层 | 改造 |
|---|---|
| **后端** | 编排网关新增 `/task-groups` CRUD（`GET /task-groups?projectCode=`、`POST/PUT/DELETE`），代理海豚 `TaskGroupController`（端点前缀 `/task-group`）；列表强制按 `projectCode` 过滤，不接受前端任意传码。**删除映射**：海豚 3.4.3 无物理删除端点，datara `DELETE /task-groups/{id}` 映射为 `POST /task-group/close-task-group`（`id` 入参），前端文案为「关闭」，状态置 `0`（已关闭） |
| **datara 前端** | 项目管理 → 项目详情 → 新增「任务组管理」子标签页。按项目隔离，表格视图（name / description / createTime / owner），新建/编辑/删除。快捷入口：部署运维子导航加一个"当前项目任务组"入口 |
| **海豚前端** | **不改**：原生 `use-task-group.ts` 已调海豚 `/task-group/query-list-by-projectCode`，只要海豚 API 经编排网关代理即可 |
| **owner 规则** | 项目级：项目 admin 全见；其他成员**默认仅自己创建的**；项目管理员可显式共享给指定成员 |

#### R9 资源文件（新增，P1）

海豚语义：资源文件是节点执行时的依赖文件（jar、py、sh、data 等），存在海豚 master/worker 可访问的文件系统（HDFS 或本地路径 `/dolphinscheduler/resources/`）。

| 层 | 改造 |
|---|---|
| **后端** | 编排网关补齐 `/resources` CRUD：`GET /resources`（目录树，内部代理海豚 `GET /resources/list?type=FILE`）、`POST /resources`（创建目录/上传文件）、`PUT /resources`（重命名）、`DELETE /resources`；保留已有 `/resources/{kind}/{key}/share`。代理海豚 `ResourceController`（端点前缀 `/resources`） |
| **datara 前端** | 部署运维 → 新增「资源文件」页面，树视图（目录/文件），支持拖拽上传、创建目录、重命名、删除、下载 |
| **海豚前端** | **不改**：原生 `use-resources.ts` 调海豚 `GET /resources/list?type=FILE`，读的是同一份海豚资源文件系统；datara「资源文件」页经编排网关读写同一份数据，节点表单因此始终有值。**可见性差异（已裁定接受）**：海豚表单展示全局文件树，datara 页按 owner 过滤（admin 全见） |
| **owner 规则** | 全局资源（文件跨项目共享使用）；admin 全见；显式共享给指定用户 |

#### F6 Yarn 队列 input→select（P2，海豚前端改造）

海豚原生 `use-queue.ts` 是 `type: 'input'`（L24），让用户手填队列名字符串。datara 后端 Queue CRUD 和前端 Yarn 队列配置页已有，只差节点表单改下拉。

| 层 | 改造 |
|---|---|
| **海豚前端** | `views/projects/task/components/node/fields/use-queue.ts`：`type: 'input'` → `type: 'select'`；`onMounted` 在 embed 模式调 datara 编排网关 `GET /orchestration/queues`（已实现）填充 options，非 embed（海豚独立运行）回退原生 `/queues/list`，保证下拉始终有值 |
| **datara 后端** | 已有 Queue CRUD（代理海豚 `QueueController`） |
| **datara 前端** | 已有部署运维 → Yarn 队列配置页 |

#### owner 规则统一

| 资源类型 | 归属 | owner 规则 |
|---|---|---|
| Worker 分组 / 环境 / Yarn 队列 / 集群 / 资源文件 | **全局** | admin 全见；其他用户**默认不可见**；可显式共享给指定用户（被共享者在节点表单下拉可见、可选） |
| **任务组** | **项目级** | 项目 admin 全见；项目成员默认仅自己创建的；可显式共享给项目内成员 |
| dbx 连接 | dbx 真源 | dbx owner 化；datara 只读镜像（编排网关代理时带 owner 过滤） |

#### 其他（不变）

| # | 裁定 | 备注 |
|---|---|---|
| R5 K8S 命名空间 | **暂不必要**（与 R4 绑定） | 不单列菜单项、不写实现；触发条件：K8s 系任务落地时作为 R4 子视图引入 |
| R6 告警管理 | **不采用海豚** | 沿用旧前端告警配置（邮件/短信）；失败感知由编排网关监听实例状态 → 按 datara 规则发送 |
| R7 实例管理 | **不采用海豚** | datara 自建实例页（10.5 B 类） |

**边界**

- 所有节点表单下拉数据必须经**编排网关代理**返回（带 owner 过滤），前端不直连海豚 API。
- Worker 组绑定环境（`environment_worker_group`）：环境列表按当前选中的 workerGroup 自动过滤（海豚原生逻辑，不改）。
- 任务组按 `projectCode` 隔离：同一任务组名在不同项目下互不影响。
- 资源文件全局共享：上传一次，所有项目的节点可选。
- 这些配置项的改动**实时生效**（每次保存工作流 / 每次运行读取最新值），不要求重启海豚。

#### K8S 命名空间管理的必要性判断（设计侧结论）

**结论：当前不必要，且不单独立项；仅在「集群管理」落地且确有 K8s 系任务时才随之引入。**

理由（三条，均基于海豚源码语义）：

1. **命名空间是集群的附属，不是独立维度**。海豚的 `t_ds_k8s_namespace` 与 `t_ds_cluster` 是「集群 → 命名空间」的从属关系（namespace 挂在 cluster 下）；没有集群就没有命名空间。既然 R4 集群管理本身是「条件必须」，R5 只能**跟随 R4**，不能先于它存在。
2. **当前 datara 工作流形态不需要 K8s 系任务**。datara 编排以 SQL/PROCEDURE/DATAX/SQOOP + Python/shell（worker 本地执行）+ 同步/流任务为主。K8s 系任务（KUBEFLOW/MLflow/Jupyter/Pytorch…）在目标场景（§一、§八）中未出现，命名空间无消费方。
3. **命名空间还承担 tenant → K8s namespace 映射**（多租户隔离）。datara 的多租户由 datara 身份与项目承担（§五、§六），海豚 tenant 与 datara 身份映射即可，无需为每个 datara 用户建 K8s namespace。

**因此**：R5 不单列菜单项、不写实现。**触发条件**——若后续新增 K8s 系任务类型（在任务面板白名单 M1 中新增 K8S/KUBEFLOW/… 条目），则 R4 + R5 一并落地，R5 作为 R4 页面内的子视图（集群 → 命名空间二级列表）。

#### 告警桥接（不采用海豚告警，沿用旧前端配置）

海豚告警组/告警实例/告警插件**不接入**（`alert/` 模块整体不用）。改为：

1. datara 侧保留旧前端告警配置能力（**邮件 / 短信等通道与规则**，旧路由 `/dep/alarm` 已实证存在）。
2. **失败感知**：datara 编排网关监听海豚 `WorkflowInstanceController` / `TaskInstanceController` 状态（或轮询实例状态），识别 `FAILURE` / 超时 / 失败重试耗尽。
3. **告警发送**：命中 datara 告警规则（按项目/工作流/告警组）→ 走 datara 既有告警通道发送。
4. **审计**：告警触发记录写入 datara 审计（D2），海豚侧不出现告警页。

**边界**

- worker 分组 / 环境的下拉数据必须经**编排网关代理**返回（带 owner 过滤），前端不直连海豚 API。
- 队列/集群配置为全局资源配置，**按 admin 或显式共享可见**；普通用户不新建，只在节点表单选用。
- 这些配置项的改动**实时生效**（每次保存工作流 / 每次运行读取最新值），不要求重启海豚。

### 10.11 监控中心（master / worker / DB）

用户裁定：datara 的**监控中心**（部署运维 → 原「集群监控」页 `/dep/monitor`）要把海豚的 **master / worker / DB** 监控也展示起来。

**定位**：监控中心是**只读观测面**，不引入海豚监控大盘页（`/monitor/*` 不进 iframe，见 10.5 C）。datara 页面承载，**代理海豚 `MonitorController`**，与 datara 自有节点监控（`rebuild/monitor`）合并展示。

**海豚来源（已核实 `MonitorController.java`）**

| 海豚端点 | 返回 | 字段 |
|---|---|---|
| `GET /monitor/{nodeType}`（`nodeType` = `MASTER`/`WORKER`/`ALERT_SERVER`） | `List<Server>` | `id, host, port, serverDirectory, heartBeatInfo, createTime, lastHeartbeatTime` |
| `GET /monitor/databases` | `List<DatabaseMetrics>` | `dbType, state(YES/NO), maxConnections, maxUsedConnections, threadsConnections, threadsRunningConnections, date` |
| `GET /monitor/masters/workflow-executors?masterAddress=` | `List<WorkflowExecutorDTO>` | `id, name, projectCode, workflowDefinitionCode, state, startTime, runTimes` |
| `GET /monitor/workers/task-executors?serverAddress=` | `List<TaskExecutorDTO>` | `id, name, taskType, projectCode, workflowInstanceId, workflowInstanceName, startTime` |
| `GET /projects/analysis/task-state-count?startDate&endDate&projectCode` | `TaskInstanceCountVO` | `totalCount, taskInstanceStatusCounts[{count, state}]` |
| `GET /projects/analysis/workflow-state-count?startDate&endDate&projectCode` | `WorkflowInstanceCountVO` | `totalCount, workflowInstanceStatusCounts[{count, state}]` |
| `GET /projects/analysis/define-user-count?projectCode` | `WorkflowDefinitionCountVO` | `count, userList[{userName, userId, count}]` |

> `Server.heartBeatInfo` 为心跳 JSON 字符串（`BaseHeartBeat`：`cpuUsage` 等系统指标 + 磁盘/内存/负载）。datara 侧解析为结构化字段后渲染，**不在前端解析海豚私有 JSON**。
>
> 后三行来自 `DataAnalysisController.java`（`@RequestMapping("projects/analysis")`），即海豚**首页 `/home`（任务运行监控）** 的数据源；`state` 为海豚状态枚举字符串，datara 侧映射为本地文案与配色。

**已核实（2026-10-29 实测 1.9 实例）**：登录 `POST /login`（`userName`/`userPassword`）→ `data.sessionId`；上述 6 个端点全部 `code=0`。实例现状：master `172.23.0.7:5678`（心跳 `2026-10-29 20:28:34`）、worker ×1、DB `POSTGRE_SQL`（`state=YES`，`maxConnections=100`，`threadsConnections=35`）。

**状态枚举（datara 侧映射文案/配色，实测全集）**

| 统计卡 | 海豚 state 全集 |
|---|---|
| 任务实例状态 | `SUBMITTED_SUCCESS`、`RUNNING_EXECUTION`、`PAUSE`、`FAILURE`、`SUCCESS`、`NEED_FAULT_TOLERANCE`、`KILL`、`DELAY_EXECUTION`、`FORCED_SUCCESS`、`DISPATCH` |
| 工作流实例状态 | `SUBMITTED_SUCCESS`、`RUNNING_EXECUTION`、`READY_PAUSE`、`PAUSE`、`READY_STOP`、`STOP`、`FAILURE`、`SUCCESS`、`SERIAL_WAIT`、`FAILOVER` |

> 海豚首页 `/home` 的两张状态卡各返回**全集**（含 count=0 项），datara 侧按上表固定顺序渲染，不因某状态计数为 0 而丢项。

**datara 监控中心页面结构**（在现有 `/dep/monitor` 页内扩展，不新增菜单项）

| 区块 | 内容 | 海豚端点 |
|---|---|---|
| **任务运行监控（海豚首页 `/home`）** | ① 任务实例状态统计（按时间区间，饼图 + 明细）② 工作流实例状态统计（按时间区间，饼图 + 明细）③ 工作流定义统计（按用户柱状） | `GET /projects/analysis/task-state-count`；`GET /projects/analysis/workflow-state-count`；`GET /projects/analysis/define-user-count` |
| 运行时节点（**已有**） | datara 自有 ZK 注册节点心跳与指标 | `rebuild/monitor`（保留不动） |
| **Master 节点** | 列表 + 心跳时间 + CPU/内存/磁盘/负载 + 下线标记；点击节点下钻该 master 上的**运行中工作流实例** | `GET /monitor/MASTER`；下钻 `GET /monitor/masters/workflow-executors` |
| **Worker 节点** | 列表 + 心跳时间 + CPU/内存/磁盘/负载；点击节点下钻该 worker 上的**运行中任务实例** | `GET /monitor/WORKER`；下钻 `GET /monitor/workers/task-executors` |
| **数据库（DB）** | 连接池健康：类型、最大连接、已用连接、活跃连接、状态（YES/NO） | `GET /monitor/databases` |
| 告警服务（可选） | ALERT_SERVER 节点状态 | `GET /monitor/ALERT_SERVER`（告警不采用海豚，见 10.10 R6；仅展示存活状态） |

**后端改造（编排网关新增代理）**

- 新增 `GET /api/v1/rebuild/orchestration/monitor/{nodeType}`、`.../databases`、`.../masters/workflow-executors`、`.../workers/task-executors`，内部转调海豚 `MonitorController`（内部信任通道，见 10.3），**带 owner 过滤**（master/worker/DB 为全局资源，admin 全见；其他角色按显式授权）。
- 新增 `GET /api/v1/rebuild/orchestration/monitor/task-state-count`、`.../workflow-state-count`（接受 `startDate`/`endDate` 可选，默认当天 0 点至当前）、`.../define-user-count`，内部转调海豚 `DataAnalysisController`（`/projects/analysis/*`）。`projectCode` 由 datara 项目上下文解析，**不接受前端任意 projectCode**（避免跨项目越权）。
- `heartBeatInfo` 在**后端解析**为 `{cpuUsage, memoryUsage, diskUsage, loadAverage, ...}` 后返回，前端只渲染。
- 心跳超时判定：`lastHeartbeatTime` 距今超过阈值（默认 30s，可配）标记为「离线/未心跳」，与 datara 自有节点三态（在线/离线/未知）统一。

**边界**

- 监控数据**只读**，不提供海豚监控大盘的任何写操作（上下线、重启等一律不暴露）。
- master/worker 下钻的运行中实例只读展示，**跳转运行详情走 datara 实例页**（10.5 B 类），不回海豚实例页。
- DB 监控展示的是**海豚元数据库**连接池状态（`t_ds_` 所在库），不是 dbx 业务库；dbx 侧监控不在本页范围。
- **海豚首页 `/home` 不进 iframe**：其三张统计卡（任务实例状态 / 工作流实例状态 / 工作流定义）由 datara 监控中心用自有图表渲染，数据经编排网关代理 `DataAnalysisController`；海豚侧 `/home` 路由在 embed 模式下不暴露。
- 前端不直连海豚 `/monitor/*` 与 `/projects/analysis/*`，统一经编排网关代理。
