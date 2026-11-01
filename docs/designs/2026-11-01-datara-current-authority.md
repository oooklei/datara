# Datara 现时权威设计（2026-11-01 基线）

> **文档地位**：本文件是 Datara 现时**唯一实施权威**，取代 2026-10-29 dbx 统一设计线（已归档至 `docs/archive/2026-11-01-authority-refresh/`）。
> **基线声明**：后续所有开发、修改、部署、验收以本文件为准；与归档区冲突时以本文件为准。
> **权威序**：用户最新明确裁定 > 本文件 > `docs/agents/协作规程.md` > 其余文档。归档区（`docs/archive/`、`docs/increments/archive/`、`docs/handoff/archive/`）只作考古。

---

## 一、已裁定前提

| # | 裁定 | 说明 |
|---|---|---|
| P1 | **dbx 为唯一数据访问层** | 连接、查询、schema、对象树、SQL IDE、血缘、AI 由 dbx 承载；datara 不直连业务库。 |
| P2 | **海豚为 DAG 画布 + 运行底座** | 只取海豚两样：① DAG 画布（编排可视化）；② master/worker/api/元数据库（运行底座）。**不取**海豚门户外壳（登录、用户/租户管理、数据源、审计、监控大盘、项目管理体系）。 |
| P3 | **编排网关取消**（2026-11-01 用户裁定） | 前端画布改为 **iframe 同源直连海豚 UI**，不经 datara 后端代理；datara 后端只承担外壳、身份、会话与自有域 API。 |
| P4 | 脚本开发与 dbx 对象树同源 | 按库/schema 粒度，双编辑入口。 |
| P5 | 单一前端入口 `http://192.168.1.9:8090/` | 禁止多套并行部署。 |

---

## 二、系统边界与角色

| 系统 | 承担 | 不承担 |
|---|---|---|
| **datara-newweb**（前端 SPA） | 门户外壳、菜单、项目/身份上下文、自建列表与观测页、iframe 宿主 | 画布编辑、数据访问 |
| **datara-rebuild-api**（后端） | 身份/会话/门卫、变量域、资源/任务组/告警/监控/治理/开放平台等自有域 API | **代理海豚画布编辑**（编排网关已取消） |
| **dbx** | 唯一数据访问层 + SQL IDE + 对象树 + 血缘 | 编排、调度 |
| **海豚 DolphinScheduler** | DAG 画布 + 运行底座（master/worker/元数据库） | 门户外壳、业务数据源（节点 `datasource` 存 dbx `connectionId`） |

---

## 三、目标架构

```
┌──────────────────────────────────────────────────────────────────┐
│  datara-newweb SPA  http://192.168.1.9:8090/  （唯一前端入口）        │
│  外壳 / 菜单 / 项目 / 身份 + 自建列表与观测页                          │
│  （工作流定义列表、实例观测、监控、资源、任务组、变量、治理）            │
└───────────────┬───────────────────────────────┬──────────────────┘
                │ iframe 同源直连                 │ iframe 同源直连
                ▼                                ▼
   /dolphinscheduler/ → 海豚 1.9:12345          /ide/ → dbx 1.9:4224
   画布编辑/保存/发布/调度 闭环                 数据访问 + SQL IDE
   （postMessage 桥下发免登凭证）               （nginx 注入嵌入令牌）
                │                                │
                └───────────────┬────────────────┘
                                ▼
                  datara-rebuild-api : 8001
                  身份 / 会话门卫 / 嵌入会话签发
                  + 自有域 API（变量/资源/任务组/告警/监控/治理/开放平台）
```

**三条唯一正确路径**：

1. **画布编辑**：前端 → nginx `/dolphinscheduler/` 同源反代 → 海豚 UI（**不经 datara 后端**）。
2. **数据访问 / IDE**：前端 iframe `/ide/` → nginx 注入 `X-Datara-Embed-Token`（来自 `/embed/session` 的 HttpOnly cookie）→ dbx（自验自过滤）。
3. **datara 自有域**：前端 → `/api/` → rebuild 后端。

---

## 四、集成机制

### 4.1 nginx 同源反代（`deploy/wsl-frontend/nginx.conf`）

| 路径 | 上游 | 说明 |
|---|---|---|
| `/` | 本地静态 | SPA fallback（`try_files ... /index.html`） |
| `/assets/` | 本地静态 | 强缓存 `max-age=31536000, immutable` |
| `/api/` | `datara-rebuild-api:8001` | 禁 gzip（保强 ETag）、SSE 直通、`resolver 127.0.0.11` |
| `/ide/api/` | rewrite → `/api/v1/rebuild/dbx/ide-proxy/` | DBX API 必须经 Datara owner proxy |
| `/ide/` | `http://192.168.1.9:4224/ide/` | 注入 `X-Datara-Embed-Token $cookie_datara_dbx_embed` |
| `/dolphinscheduler/` | `http://192.168.1.9:12345/dolphinscheduler/` | 海豚同源反代，SSE 直通 |

### 4.2 统一嵌入会话

- `GET|POST /api/v1/rebuild/embed/session?project_id=`：统一执行项目权限门禁，返回 DBX/编排子会话入口，不暴露内部令牌。
- 签发 HttpOnly cookie `datara_dbx_embed`（path=`/ide`，TTL 900s）；nginx 读取为 `X-Datara-Embed-Token` 注入 dbx。
- `GET /api/v1/rebuild/orchestration/session` 返回海豚 token/user/projectCode（供 iframe 路由）。

### 4.3 postMessage 桥

- `dsBridge.ts`：`datara:ds-session` / `datara:ds-ready`，强制同 origin + `contentWindow` 校验，拒绝跨源/跨帧注入。
- `dbxVariableBridge.ts`：`datara:variables` / `datara:bridge-ready`，向 `#dbx-ide-frame` 下发变量。

### 4.4 变量注入

- 宿主拉取当前项目/环境组变量现值，经 `datara:variables` 下发 iframe（dbx）。
- dbx 侧就绪后回发 `datara:bridge-ready`，宿主补发一次（覆盖时序）。

---

## 五、前端结构

### 5.1 路由（`datara-newweb/src/router/routes.ts`，History 模式，逐条具名）

| 路径 | name | 类型 | 说明 |
|---|---|---|---|
| `/login` | `login` | 自建 | 登录 |
| `/` | `home` | 自建 | 工作台 |
| `/dag` | `dag-entry` | 自建+iframe | 任务中心（自建列表 + 海豚画布 embed） |
| `/ide` | `dbx-sql-ide` | **iframe** | dbx SQL IDE（`/ide/`） |
| `/dep/ssh` | `dep-ssh` | 自建 | SSH 节点 |
| `/dep/runtime` | `dep-runtime` | 自建 | 运行时节点 |
| `/dep/monitor` | `dep-monitor` | 自建 | 监控中心 |
| `/dep/worker-group` | `dep-worker-group` | 自建 | Worker 分组（`OrchestrationResourceView`） |
| `/dep/environment` | `dep-environment` | 自建 | 环境管理 |
| `/dep/queue` | `dep-queue` | 自建 | Yarn 队列 |
| `/dep/cluster` | `dep-cluster` | 自建 | 集群管理 |
| `/resources` | `resource-mgmt` | 自建 | 脚本开发 |
| `/open/key` | `open-key` | 自建 | API-Key |
| `/open/api` | `open-api` | 自建 | API 管理 |
| `/sys` | `system-admin` | 自建 | 系统 |
| `/meta/tag` | `meta-tag` | 自建 | 标签 |
| `/std/element` | `std-element` | 自建 | 标准 |
| `/ind/list` | `ind-list` | 自建 | 指标目录 |
| `/ind/board` | `ind-board` | 自建 | 指标看板 |
| `/ind/consistency` | `ind-consistency` | 自建 | 一致性 |
| `/sec/perm` | `sec-perm` | 自建 | 权限 |
| `/sec/audit` | `sec-audit` | 自建 | 审计 |
| `/qc/rule` | `qc-rule` | 自建 | 质量规则 |
| `/qc/task` | `qc-task` | 自建 | 质量任务 |
| `/qc/exception` | `qc-exception` | 自建 | 质量异常 |
| `/qc/report` | `qc-report` | 自建 | 质量报告 |
| `/qc/alarm` | `qc-alarm` | 自建 | 质量告警 |
| `/p/:projectId` | `project-workbench` | 自建 | 项目工作台 |
| `/p/:projectId/system` | `project-system-admin` | 自建 | 项目设置 |
| `/p/:projectId/ide` | `project-dbx-sql-ide` | **iframe** | 项目内 dbx IDE |
| `/p/:projectId/:pathMatch(.*)*` | `project-segment` | 自建 | 项目功能段（未知段渲染「未知功能段」） |
| `/proj` | — | redirect | → `/` |
| `/p/:projectId/dep` | — | redirect | → `/dep/monitor` |

**注意**：`/task-group` 无对应路由（菜单项存在），见 §十一 冲突 3。

### 5.2 菜单（`datara-newweb/src/navigation/menu.ts`）

| 分组 | 菜单项 |
|---|---|
| overview | 工作台 |
| task-center | 任务中心（`/dag`）、任务组管理（`/task-group`） |
| integration | SQL IDE、同步任务/流处理（embedded）、脚本开发（`/resources`） |
| governance | 标签、标准、指标目录、指标看板、一致性、质量（五项） |
| operations（topbar） | 监控、SSH、Worker 分组、环境、Yarn 队列、集群 |
| system（topbar） | 权限、审计、API 管理、API-Key、调用日志（embedded） |
| future | （空） |

---

## 六、后端 API 域（`/api/v1`）

### 6.1 域清单（前缀均含 `/api/v1`）

> 依据 `datara-backend/rebuild/api/app.py` `include_router` 挂载与各域模块自身的 `APIRouter(prefix=...)`。

| 域 | 前缀 | 载体模块 | 职责 |
|---|---|---|---|
| 治理 | `/rebuild/governance` | `rebuild.governance.api` | 资产/标签/血缘/质量规则·运行·异常·报告/告警策略/标准/指标/legacy 导入 |
| DBX 项目内 | `/rebuild/dbx/projects/{project_id}` | `rebuild.dbx.api` | 连接、query/execute、对象树 |
| DBX IDE owner proxy | `/rebuild/dbx/ide-proxy/*` | `rebuild.dbx.ide_proxy` | 前端 `/ide/api/*` 经 nginx rewrite 到此 |
| 嵌入会话 | `/rebuild/embed/session` | `rebuild.orchestration.api` | 统一下发 dbx embed cookie + 海豚 token（§4.2） |
| 海豚会话 | `/rebuild/orchestration/session` | `rebuild.orchestration.api` | 海豚 iframe 路由所需 token/user/projectCode |
| 变量 | `/rebuild/variables` | — | 七级变量定义/解析/校验/投影/运行快照（§8.2） |
| 编排 datara 域 | `/rebuild/orchestration` | — | 见 §6.2（自建列表 + 资源/监控/任务组/worker-group/env/queue/cluster/告警） |
| 资源 | `/rebuild/resources` | — | 脚本资源 CRUD、分享、下载 |
| 工作流 | `/rebuild/workflows` | — | 工作流域 |
| 执行 | `/rebuild/execution` | — | 执行统计、重跑入口 |
| 同步 / 流处理 | `/rebuild/sync`、`/rebuild/stream` | — | 同步任务、流处理 |
| 运维 | `/rebuild/monitor`、`/rebuild/runtime-nodes`、`/rebuild/ssh-nodes` | — | 监控、运行时节点、SSH 节点 |
| 调度 | `/rebuild/scheduling` | — | 定时 |
| 组件 | `/rebuild/components` | — | 组件目录 |
| 依赖 | `/rebuild/dependency` | — | 依赖 |
| SQL IDE DDL | `/rebuild/sql-ide-ddl` | `rebuild.rb.api` | 只读 DDL |
| SQL IDE（项目内） | `/projects/{project_id}/sql-ide` | `rebuild.sql_ide.routes` | 项目作用域 SQL IDE |
| 模型字典 / 模型 | `/rebuild/model-dicts`、`/rebuild/models` | `rebuild.model.api` | 模型字典、模型实例 |
| LLM 模型 | `/rebuild/llm-models` | `rebuild.llm` | LLM 模型 |
| AI bridge | `/rebuild/ai/*` | `rebuild.ai_bridge` | `/tools`、`/chat`、`/tool-calls` |
| 安全 | `/rebuild/sec`、`/rebuild`（acl 模块） | `rebuild.sec.api`、`rebuild.acl.api` | 权限、ACL |
| 开放平台 | `/open/*` | `rebuild.apikey`、`rebuild.openapi_admin` | API-Key、openapi_admin |
| 项目影响 | `/rebuild/projects/{project_id}/impact` | `rebuild.impact.api` | 每日影响分析 |
| 内部通道 | `/internal/dbx/connections/{id}/params`、`/internal/scripts/{id}/content`、`/internal/alarm/dispatch` | `rebuild.orchestration.api` | dbx 连接参数、脚本内容、告警派发（内部令牌） |

### 6.2 orchestration 域路由分类

**datara 自建页消费（保留）**：

`datasources`、`scripts`、`scripts/{id}/content`、`resources`（含 share/download/sync）、`task-groups`、`worker-groups`、`environments`、`queues`、`clusters`、`monitor/*`、`alarm-rules`、`alarm-records`、`workflow-definitions`（列表）、`workflow-instances`（列表/详情/任务/甘特图/变量）、`task-instances`、`task-instances/{id}/log`、`workflow-schedules`（列表）。

**疑似残留海豚代理（待确认消费方，见 §十一）**：

`workflow-definitions/{code}/release`、`DELETE workflow-definitions/{code}`、`workflow-schedules/{id}/{action}`、`workflow-instances/start`、`workflow-instances/{id}/control`。

---

## 七、部署架构

### 7.1 容器清单

| 系统 | 容器 | 端口 | 说明 |
|---|---|---|---|
| Datara 前端 | `datara-newweb-fe` | `8090:80` | **唯一入口**（`deploy/wsl-frontend/compose.yaml`） |
| Datara 重建 API | `datara-rebuild-api` | `8001` | `docker-compose.rebuild.yml` |
| dbx | `dbx` | `4224` | `/lei/apps/dbx/deploy-1.9/docker-compose.yml` |
| 海豚 | `ds-*` | `12345` | `/lei/apps/ds-3.4.3-deploy-20261029/` |
| Datara 其他 | `dt-zk`、`dt-kafka`、`dt-redis`、`dt-db-meta`、`dt-api(8000)`、`dt-master`、`dt-worker`、`dt-alert`、`dt-logger`、`dt-oldweb(18091)`、`dt-db-src(3310)`、`dt-db-dw(3309)` | — | 根 `docker-compose.yml` |

### 7.2 网络

- 前端容器与 rebuild 后端同处 `datara_default` 网络，nginx 按容器名解析 `datara-rebuild-api:8001`。
- dbx 与海豚在各自网络，前端经**宿主端口**（`192.168.1.9:4224` / `192.168.1.9:12345`）跨网络访问。

### 7.3 命名约束

- 运行容器名 ≤ 12 字符；Compose **服务键**保留原名以维持 DNS 与依赖关系，`container_name` 用简名（见 `docs/agents/container-names.md`）。
- ⚠️ 现时前端容器实为 `datara-newweb-fe`（15 字符）、后端 `datara-rebuild-api`（17 字符），**超 12 字符**，待修正（见 §十一）。

---

## 八、数据与变量体系

### 8.1 数据分层主链路

```
源库 ──(同步)──> ODS ──(ETL 清洗)──> DWD ──(工作流)──> DWS ──(工作流)──> DIM / ADS
                                                                    └──> TMP（临时层）
```

- 写端库默认内置源库 ODS。
- 三种同步模式：**源表基准**、**目标表基准**、**文件同步**。
- 血缘：表级 + 字段级，由 DAG 组件解析汇总为「表 → 字段」血缘。

### 8.2 七级变量（编排变量真源）

| scope | 载体 | 注入方 | 可持久化 |
|---|---|---|---|
| run | 命令参数 | 编排层 | 否 |
| task | 节点 `localParams` | DAG 视图保存时投影 | 是 |
| workflow | 工作流定义 `globalParams` | DAG 视图保存时投影 | 是 |
| project | 项目参数 | 变量域同步 | 是 |
| env | 命令参数（限定键） | 编排层 | 是 |
| global | 命令参数（限定键） | 编排层 | 是 |
| builtin | 海豚内置参数 + datara 补 `builtin.*` | 编排层 | 否 |
| tmp | 运行时瞬态 | 不注入 | 否 |

- 优先级 `PRECEDENCE = (run, task, workflow, project, env, global, builtin)` + 瞬时 `tmp`。
- 变量 API：`/rebuild/variables`（增删改查、`complete`、`check-reference`、`preview`、`run-snapshot`）。

---

## 九、身份与权限

### 9.1 平台 RBAC

| 角色 | 说明 |
|---|---|
| admin | 全部权限 |
| developer | 开发 |
| operator | 运维 |
| viewer | 只读 |

- 单平台角色；项目角色只影响本项目，且只降权不增权。

### 9.2 资源授权治理

- 单一 `PolicyService` 判定入口；平台角色优先。
- 统一 `rebuild_resource_acl`。
- 分享授「资格」不授「权限」：**有效权限 = min(分享上限, 角色上限)**。
- 路线：P0 身份统一 → P4 收尾。

---

## 十、开发约束与配套

### 10.1 源码真源（`docs/agents/source-truth.md`）

- Datara、DBX、海豚源码真源位置、双向同步与发版门禁（`python scripts/release_source.py preflight`）。
- 所有修改先落真源；其他分支/工作区发布内容必须先合并回真源。

### 10.2 容器命名（`docs/agents/container-names.md`）

- 容器名 ≤ 12 字符；改名须同步 Compose/发布配置并验证服务间访问。

### 10.3 协作（`docs/agents/协作规程.md`）

- 七席位最小运行合同；`RUNNING / epoch 3`；只做本机稽核。

### 10.4 Issue / Triage

- Issues 存 GitHub Issues（`oooklei/datara`），经 `gh` CLI。
- 五个默认 triage labels：`needs-triage`、`needs-info`、`ready-for-agent`、`ready-for-human`、`wontfix`。

### 10.5 环境边界

- **本机**：代码检测、静态/类型/逻辑稽核。
- **192.168.1.9**：部署、容器、中间件、联调、browser-use E2E；前端验证入口固定 `http://192.168.1.9:8090/`。
- 页面不设登录表单（验证 key 换短时 token 注入，key 禁入静态产物/URL/浏览器持久存储）。
- 部署/E2E 验收证据必须出自 1.9 隔离工作目录。

---

## 十一、已知冲突与待办（现时）

| # | 冲突 | 处置 |
|---|---|---|
| 1 | 编排网关已裁定取消，但 `app.py#L1866-1875` 仍全量挂载 `build_orchestration_router`（注释仍写「编排网关（设计 §十）」），前端仍调 `/rebuild/orchestration/*` | 保留 datara 自有域（列表/实例/资源/监控），**清理残留海豚代理路由**（见 §6.2），并改注释 |
| 2 | `routes.ts#L62-63`、`menu.ts#L125/L305/L315/L325/L335` 注释仍写「经编排网关代理海豚」「2026-10-29 dbx 统一目标设计」 | 统一改为「同源 iframe 直连」，设计引用改指本文件 |
| 3 | 菜单 `task-group`（`/task-group`）在 `routes.ts` 无对应路由（`menu.ts#L119-127`） | 补路由（后端 `/rebuild/orchestration/task-groups` 已就绪）或删菜单项 |
| 4 | 菜单 `routeName:'depMonitor'`（`menu.ts#L281`）与路由 `name:'dep-monitor'`（`routes.ts#L61`）不一致 | 统一为 `dep-monitor` |
| 5 | 容器名超限：前端 `datara-newweb-fe`（15）、`docker-compose.rebuild.yml` 的 `datara-rebuild-api`（17） | 按 `docs/agents/container-names.md` §2 改 `dt-web` / `dt-rebuild`（服务键不变） |
| 6 | `docs/agents/domain.md` 原指向根 `GLOSSARY.md`，实际缺失 | 已改为以本文件 §二/§八/§九 为术语权威；不提前创建 GLOSSARY |
| 7 | `release/.../infra/docker-compose.yml` 旧五模块全栈与 rebuild 单后端并存 | 归档旧模板，只留现行结构 |

---

## 十二、权威序

1. 用户最新明确裁定与 `docs/handoff/STATE.md` 裁定记录；
2. **本文件**（现时唯一实施权威）；
3. `docs/agents/协作规程.md`；
4. 已在 192.168.1.9 形成运行证据、且已进入当前 Git 历史的实现；
5. 需求输入材料：`docs/*.txt`；
6. 其余历史/归档 → 只作考古。
