# 阶段0 D/E 报告补充版（范围补齐 + 命令留痕）

> 日期：2026-10-16（Asia/Shanghai）· 作者：Trae 实施线（起草 agent + 实施线抽核）· 性质：只读复核报告
> - 目的：补齐 0.4 矩阵（`docs/increments/2026-10-16-阶段0-0.4差异复用矩阵.md` §4）所列旧报告两缺陷——①范围补 `rebuild/project/` 域；②补命令输出/环境/文件清单摘要。本报告不推翻、不改写旧报告结论，冲突处如实标注。
> - 旧报告锚：`trae/phase0-audit@76d540c`（`trae-D-sync-dependency-resource-etl.md`、`trae-E-stream-stats.md`，main 未合入原件）；本报告复核锚：canonical main @ `9e2029d15d1ca5d88a8185ca6c0ea3e57f1f8a88`。
> - 边界重申（沿 0.4 矩阵）：本报告不判任何域 GREEN；A/B/C 逐资产明细仍待用户/Codex 裁定；correction-plan 隔离 WIP 不计作 main 能力。

## 1. 环境与锚点（命令留痕）

复核执行时间：2026-10-16 20:46 (+08:00)。以下每条命令均为实际执行并原样记录输出。

```
PS> git rev-parse main
9e2029d15d1ca5d88a8185ca6c0ea3e57f1f8a88

PS> git log --oneline -1 main
9e2029d docs(handoff): add Trae impl-line heartbeat #17 (Q-answer ledger c9a6631, R4-SYNC backfill 64c1632, matrix v4 ef6ff1b, adapter notes 4c7200a)

PS> git branch --contains 76d540c
+ trae/phase0-audit
```

`git branch --contains 76d540c` 仅命中 `trae/phase0-audit`（`+` 表示该分支检出在 worktree `.worktrees/trae-phase0-audit`，实测其 HEAD 即 `76d540c071aaa72ce4821164e1cf84abe6c0229e`）；canonical main **不包含** 76d540c，与矩阵"不合入原件"表述一致。

```
PS> git ls-tree -r --name-only main docs/increments/evidence/phase0
（无任何输出：main 上该目录当前零跟踪文件）
```

即 main 的 phase0 证据目录为空，旧 D/E 原件与本补充版均需经 pathspec 纳入（提交由主会话完成）。

```
PS> git --version
git version 2.55.0.windows.5

PS> $PSVersionTable.PSVersion
Major  Minor  Patch  PreReleaseLabel BuildLabel
-----  -----  -----  --------------- ----------
7      6      6

PS> Get-Date -Format "yyyy-MM-dd HH:mm:ss zzz"
2026-10-16 20:46:02 +08:00
```

环境备注：Windows + PowerShell 7.6.6；D/E 域内容命中一律使用 Grep 工具（非 shell grep）在 `datara-backend\rebuild` 上执行，大小写不敏感、输出带文件与行号。

## 2. rebuild 树文件清单摘要（按域分组）

```
PS> git ls-tree -r --name-only main datara-backend/rebuild
（共 56 个文件，7 个代码域 + 根包，完整清单见 git；下表为按域分组摘要）
```

| 域 | 文件数 | 关键文件（≤5 个/域） |
|---|---|---|
| sync | **0（域不存在）** | — |
| dependency | **0（域不存在）** | — |
| resource | **0（域不存在）** | — |
| stream | **0（域不存在）** | — |
| stats | **0（域不存在）** | — |
| variables | **0（域不存在）** | — |
| project | 4 | models.py、repository.py、contracts.py、__init__.py |
| sql_ide | 4 | ddl_plan.py、ddl_policy.py、ddl_diff.py、__init__.py |
| api | 2 | app.py（`create_app` API 工厂）、__init__.py |
| common | 2 | db.py（SQLAlchemy Base）、__init__.py |
| datasource | 6 | pool.py、repository.py、metadata.py、models.py、contracts.py、__init__.py |
| governance | 31 | api.py、service.py、models.py、repository.py、revisions/（v0001–v0003；legacy_i19–i23 导入/映射/预览共 15 文件） |
| identity | 6 | contracts.py、models.py、repository.py、passwords.py、provision_admin.py、__init__.py |
| 根包 | 1 | __init__.py |
| **合计** | **56** | — |

与旧报告基线的树对比（留痕）：

```
PS> git ls-tree -r --name-only 059b5f9 datara-backend/rebuild
（共 52 个文件：api/common/datasource/governance/identity/project 六域 + 根包，无 sql_ide）
```

要点：旧报告基线 `059b5f9` 时 rebuild 为 **6 域 52 文件**——`project/`（4 文件）**当时已存在**，但旧 D/E 报告的"仅 5 域"清单未列它，即矩阵缺陷①所指；`sql_ide/` 为 059b5f9 → 9e2029d 期间新增域。截至 9e2029d，sync/dependency/resource/stream/stats/variables 六个域在 rebuild 树中均不存在。

## 3. D 域复核发现（sync/dependency/resource/etl）

Grep 执行方式：`Grep(pattern=<p>, path=datara-backend\rebuild, -i, content+行号)`。

### 3.1 etl 引用面

pattern：`etl`（-i）。命中 **4 行**：

- `rebuild\api\app.py:34`、`rebuild\governance\api.py:69`、`rebuild\datasource\pool.py:19`、`rebuild\identity\provision_admin.py:21` — 内容全部为 `logger = logging.getLogger(__name__)`。

语义注记（实读确认）：4 处命中均为 `logging.getLogger` 中子串 `etL` 的大小写不敏感误命中，**rebuild 内不存在任何 ETL 逻辑、注释或历史兼容代码**。旧 D 报告对 `rebuild/api/app.py`、`rebuild/governance/api.py` 的 etl 字样标注"性质未确认，需读源码判定"——本复核将该未决项落定为：**误命中，非 ETL 语义**（属证据补强，不推翻旧报告）。

### 3.2 dependency（库级入口）

pattern：`depend`（-i）。命中 13 行，无 dependency 域目录：

- `rebuild\sql_ide\ddl_plan.py:52,75` — DDL 计划提示文案："later dependency checks and human review"、"Dependency impact is unknown and requires a later dependency review"。
- `rebuild\sql_ide\ddl_policy.py:183,230` — "dialect-dependent" 说明与 finding `dependency_analysis_unavailable`（"No metadata service was consulted; dependency impact remains unknown."）。
- `rebuild\governance\legacy_dry_run.py:201-223` — I18 迁移批次 dry-run 的 `dependency_issues` / `dependency_not_importable` 导入前置校验。
- `rebuild\governance\legacy_i20_importer.py:428` — `raise I20ImportRejected("cyclic I20 metric dependency")` 循环依赖拒绝。

语义注记：命中均为 SQL IDE 的依赖分析提示与 legacy 迁移导入的依赖校验，**不存在工作流依赖组件（DolphinScheduler 式表单/表达式/预览）的任何 rebuild 实现**，与旧 D 报告②节结论一致。

### 3.3 resources 端点与资源版本服务

pattern：`resource`（-i）命中 39 行；pattern：`resources`（-i）**零命中**。`resource` 命中全部为审计日志字段 `resource_type`/`resource_id`：

- `rebuild\governance\models.py:265-266` — 审计表列定义 `resource_type: Mapped[str]`、`resource_id: Mapped[str]`。
- `rebuild\governance\api.py`（25 处，如 L1050-1059、L1183-1184、L1279-1280、L1355-1356、L1461-1462、L1564-1586、L1717-1718）— asset/tag/lineage_edge/quality_rule 等审计动作的资源标识与 `project_id` 参数。
- `rebuild\identity\provision_admin.py:60-61`（`resource_type="rebuild_user"`）、`rebuild\governance\legacy_i19_importer.py:307-308`、`legacy_i20_importer.py:234-235`、`legacy_importer.py:191-192`（`resource_type="migration_batch"`）、`repository.py:35-44`、`service.py:39-48`（审计透传）。

语义注记：`resources` 复数零命中表明 rebuild 无任何资源端点文件；`resource_*` 命中均为审计日志的资源标识字段，**不存在"有身份、有版本、有大小/类型限制和权限边界的资源版本服务"**，与旧 D 报告③节结论一致。

### 3.4 sync

rebuild 树无 sync 域（§2 清单为证），Grep 未单列 pattern——域不存在已由文件清单直接证明，与旧 D 报告①节"rebuild 实际仅 5 域，无 sync 域"结论一致（域数更新见 §6）。

## 4. E 域复核发现（stream/stats）

### 4.1 kafka

pattern：`kafka`（-i）。**零命中**，如实记录：rebuild 内无任何 Kafka 引用（topic、producer/consumer、配置均无）。

### 4.2 流统计表

pattern：`stream_metric_snapshot|stream_failure_event`（-i）。**零命中**，如实记录：两流表在 rebuild 无模型/迁移/引用。

### 4.3 统计四表

pattern：`workflow_result_stat|task_instance_data_stat|task_data_stat_segment|task_data_error_sample`（-i）。**零命中**，如实记录：四张统计表在 rebuild 无模型/迁移/采集器引用，与旧 E 报告"后端 0/4 表，无采集器"一致。

### 4.4 stream 字样与 stats 目录

pattern：`stream`（-i）命中 3 行，全部为 `rebuild\governance\api.py:1372,1394,1396` 血缘查询的 `direction` 参数取值 `upstream`/`downstream`（"up/down**stream**" 子串误命中），非流运行时语义。

stats 目录：`git ls-tree -r --name-only main datara-backend/rebuild` 完整清单中**无 stats/ 目录**（§2 为证）。

小结：rebuild 无 stream/execution 域、无 Kafka、无统计四表实现，与旧 E 报告①②③节结论一致。

## 5. P 域补扫（rebuild/project/）——旧报告范围缺项补齐

```
PS> git ls-tree -r --name-only main datara-backend/rebuild/project
datara-backend/rebuild/project/__init__.py
datara-backend/rebuild/project/contracts.py
datara-backend/rebuild/project/models.py
datara-backend/rebuild/project/repository.py
```

对 4 个文件全部实读（Read），另实读 `api/app.py` 核对 API 接线。语义级发现：

**该域承载 I1"项目与成员"能力**：项目实体 + 成员权限契约 + 仓储 + 项目作用域鉴权闸门，是 datasource 域与 governance 域 API 的 `project_id` 归属基础；非工作流编排意义上的"项目配置"。

- `__init__.py:1` — 模块 docstring：「I1 项目与成员契约。」
- `models.py:12-22` — `ProjectRecord`（ORM，表名 `rebuild_project`）：`name` unique+index、`owner_id` index、`description` Text 默认空、`created_at`/`updated_at` 默认取 Asia/Shanghai 时区 naive 时间（`models.py:25-26` `_now_shanghai`）。项目本体会随 `api/app.py` lifespan 建表（`app.py:122-130`，与 `UserRecord`/`ProjectMemberRecord`/`ProjectDatasourceRecord` 同批）。
- `contracts.py:1-16` — frozen dataclass `Member(user_id, role, is_owner)` 与纯函数 `can_manage_project`（owner 或 `Role.ADMIN`）；模块 docstring：「项目成员权限，不依赖旧 Backend。」成员实体模型 `ProjectMemberRecord` 位于 identity 域（`repository.py:6` 导入）。
- `repository.py:10-32` — `ProjectRepository`：`create`（name 空白校验）、`list_for_user`（outerjoin `ProjectMemberRecord`，owner 或成员可见，distinct 按 id 排序）、`list_all`。`api/app.py:308,321` 实际使用。
- `api/app.py` 接线：`POST /api/v1/rebuild/projects`（L301，创建项目，owner=当前用户）；`GET /api/v1/rebuild/projects`（L314，ADMIN 全量、普通用户按 owner-or-member 过滤）；`POST /api/v1/rebuild/projects/{project_id}/members`（L695，需 `Permission.MANAGE_USER`，按 username 添加成员并赋角色）；`project_permission_error`（L238-257）为项目级鉴权闸门（项目不存在 404 / ADMIN 放行 / owner 放行 / 成员角色 `authorize` / 其余 403），全部 `/projects/{project_id}/datasources*` 端点（L397-677）及 governance 路由内资源操作均经其鉴权。
- 能力边界（如实记录）：项目本体仅有 create/list，**无 update/delete 端点**；成员仅有 add，`app.py` 内**无成员 list/remove 端点**；`can_manage_project` 在 rebuild 内仅见定义（contracts.py:15），未见调用点——`app.py` 实际使用 identity 的 `authorize` + `ProjectMemberRecord` 做成员鉴权。

补扫结论：旧 D/E 报告"rebuild 仅 5 域、无 sync/stream 等域"的盘点漏列了当时已存在的 `project/` 域；本节以实读补齐其语义画像。project 域的存在**不改变**旧报告关于 sync/dependency/resource/stream/stats 缺位的任何结论。

## 6. 与旧报告差异对照

| 维度 | 旧 D/E 报告（76d540c，基线 059b5f9） | 本补充版（复核锚 9e2029d） |
|---|---|---|
| 范围 | 未列锚点树已有的 `rebuild/project/` 域（矩阵缺陷①） | 已补：§5 实读 4 文件 + API 接线，给出语义画像 |
| 命令留痕 | 仅"复现命令"片段，无原始 stdout/stderr、无环境信息、无文件清单摘要（矩阵缺陷②） | §1 环境与锚点、§2 树清单+基线对比、§3/§4 Grep pattern+逐条命中均留痕 |
| 复核锚 | 76d540c 树（报告基线 main `059b5f9`） | canonical main @ `9e2029d`（实查，非沿用） |
| rebuild 域数表述 | "实际仅 5 域（api/common/datasource/governance/identity）" | 实查 7 域 56 文件：上述 5 域 + project（059b5f9 已存在，旧报告漏列）+ sql_ide（两锚之间新增） |
| rebuild 内 etl 字样性质 | "性质未确认，需读源码判定" | 已落定：4 处全为 `logging.getLogger` 的 `etL` 子串误命中，非 ETL 逻辑 |
| D/E 核心结论 | 无 sync/dependency/resource/stream/stats 域、无 Kafka、统计 0/4 表 | 复核一致，未发现推翻性证据；仅作证据补强 |

冲突情况：无实质冲突。唯一表述级修正是"仅 5 域"应读作"漏列已存在的 project 域"（sql_ide 为锚点迁移期间新增，非旧报告笔误）。

## 7. pending 与边界重申

- 本报告**不判任何域 GREEN**；仅记录 main @ 9e2029d 的只读复核事实。
- A/B/C 槽逐资产明细仍待用户/Codex 裁定；correction-plan 及 phase0-q-correction worktree 的隔离 WIP **不计作 main 能力**，其变化不在本报告范围。
- 本报告证据仅锚定复核时点（2026-10-16 20:46 +08:00，main @ 9e2029d）；此后 main 前移需重新复核。
- 旧 D/E 原件未合入 main（`git branch --contains 76d540c` 为证），保留为历史线索；本补充版按 pathspec 纳入 `docs/increments/evidence/phase0/`。
- 沿 0.4 矩阵：目录清单/Grep 命中仅证明"存在/不存在"，语义判断均以实读文件内容为据；未实读文件不做语义断言。
