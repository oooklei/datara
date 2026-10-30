---
design_type: phase
created_at: 2026-10-29
---

# dbx 统一后端迁移可行性设计（phase-1）

> 研究问题：datara 有数据源管理、dbx 也有新建连接（数据源）。能否只使用 dbx 的数据源管理，datara 直接复用（只读查看配置）？
>
> 结论：**「只读镜像配置」受阻**（dbx 永不返回明文密码，datara 直连执行必须自备密码，矛盾）。
> 可行方向是**「dbx 作为唯一数据访问层与执行真源，datara 后端瘦身为前端 + 薄身份服务」**。本文档即该方向的分阶段可行性方案。

## Intent Contract

```yaml
intent: >-
  将 dbx 作为 datara 的唯一数据访问层与执行真源（连接管理、查询执行、schema、MQ 管理、
  ER/血缘可视化、AI、操作日志），datara 后端瘦身为「前端 + 薄身份服务」，
  编排与资源管理独立，实现「一个执行真源、一个管理真源」。
constraints:
  - 不破坏 dbx 现有能力（连接/查询/schema/MQ/ER/血缘/AI/history）
  - 已发版组件不可变（componentRef 固定），组件声明纯 JSON 禁函数
  - 前端验证入口固定 http://192.168.1.9:18091/（禁 8090）
  - 编排独立（codex 已在做），不依赖 dbx 插件机制
  - 多用户/多项目隔离必须保留（dbx 为单用户，无法替代）
  - 治理链条砍掉：不做变更前策略校验/影响预览/二次确认/台账，
    只要「操作日志 + 定期事后影响分析」
  - 变量解析链、发布闸门等既有域规范不因本次迁移而放宽
success_criteria:
  - datara 后端除薄身份服务外，无 pymysql/psycopg/SQLAlchemy 直连数据库调用
  - 所有 SQL 执行经 dbx API（按 connection_id，不传密码）
  - 操作日志由 dbx /history 承载，可追溯每次执行的 SQL
  - 定期影响分析作为编排定时 DAG 读 dbx /history 执行，不阻塞主流程
  - 多用户/多项目隔离可用
  - 前端 http://192.168.1.9:18091/ 全功能可用
risk_level: high   # 架构级替换：执行路径、密码托管、身份模型同时变动
```

## Verification Contract

```yaml
verify_steps:
  - run tests: datara-backend 测试套件全绿；新增 dbx 代理 adapter 契约测试（按 connection_id 执行、不传密码）
  - check: datara 后端 grep 无 pymysql/psycopg/SQLAlchemy create_engine 直连调用（白名单：薄身份服务自身库）
  - check: 同步/即席查询结果与迁移前抽样比对一致
  - check: dbx /history 对每次经 dbx 的执行有留痕
  - confirm: 前端 http://192.168.1.9:18091/ 全功能可用；多用户/多项目隔离生效
```

## Governance Contract

```yaml
approval_gates:
  - 本设计批准（当前）
  - 每阶段切换前用户批准
  - 密码托管迁移（datara 本地密码 → dbx）单独批准
rollback:
  - 过渡期保留 datara 直连降级开关，可回退到直连执行
  - 每阶段独立可回滚，不跨阶段耦合
ownership:
  - 用户：架构裁定、阶段批准、密码迁移批准
  - Agent：设计与实施
```

## Scope

| 范围 | 内容 |
|---|---|
| **In** | dbx 作为唯一数据访问层（连接/查询/schema/MQ/ER/血缘/AI/history）；datara 前端改为直连 dbx API + 编排 API；薄身份服务（多用户/多项目）；编排（codex 独立 DAG）对接：SQL 节点→dbx、Python/shell 节点→资源管理；资源管理服务（Python/shell）；定期影响分析定时 DAG（读 dbx /history） |
| **Out** | datara 自研数据源管理（废弃，改用 dbx）；datara 自研 SQL IDE（废弃，用 dbx）；datara 自研执行引擎直连（废弃）；R5-B DDL 变更管控闭环（作废）；datara AI（去，用 dbx AI）；dbx 插件化编排（不采用，编排独立） |

## Decisions

| # | decision | choice | rejected alternatives |
|---|---|---|---|
| D1 | 执行真源 | **dbx 唯一执行真源**（按 connection_id 执行，不传密码） | datara 直连 DB-API |
| D2 | 管理真源 | **dbx 连接管理**（datara 数据源页废弃/只读镜像） | datara 自研数据源管理 |
| D3 | 同步 transform | **表达式下推 SQL**（受控子集编译器，配置期 fail-fast） | 拉回 datara Python 算；SQL/拉回双执行 |
| D4 | 编排载体 | **独立 DAG**（codex 已在做，后面对接改造） | dbx 插件（Workbench 面板 + sidecar） |
| D5 | 审计 | **dbx /history 操作日志**（已具备：load/save/search/options/delete + 保留策略） | R5-B 台账（policy/impact/execution 三表 + 补偿） |
| D6 | 影响分析 | **定期事后 DAG**（读 /history 的执行 SQL → 分析 → 存结果，不阻塞） | 变更前阻塞式影响预览 |
| D7 | 身份 | **薄身份服务**（多用户/多项目/角色） | 依赖 dbx 单用户（无 RBAC） |
| D8 | 认证/可用性 | **固定内部令牌 + 失败重试**（接受 dbx 为同步链路硬依赖，两者同内网） | dbx 高可用多实例；保留直连降级通道 |
| D9 | 迁移分期 | **四阶段**：P1 配置统一 → P2 同步代理 → P3 其余执行点 → P4 下线直连 | 一次性整体迁移；同步先行 |

## Surface

**APIs**
- dbx（复用，不改造）：连接 `/api/connection/{save,list,test,test-info,test-ssh-tunnel}`；查询 `/api/query/{execute,execute-multi,execute-batch,execute-script,execute-in-transaction,execute-script-2pc,execute-conditional-update}`；schema `/api/schema/{columns,ddl,cache}`；历史 `/api/history/{save,search,options}`、`/api/history/{id}`；MQ `/api/mq/*`；AI `/api/ai/*`。
- datara 前端：改为薄代理/直连 dbx API + 编排 API；不再自建数据源与 SQL IDE 接口。
- 编排（codex）：对 datara 暴露 DAG 定义/触发/状态接口；其 SQL 节点调 dbx，Python/shell 节点调资源管理。

**storage**
- dbx 承载：连接配置（密码只存 dbx，永不外泄）、查询历史（操作日志）。
- 薄身份服务：用户/项目/角色（独立库，与 dbx 的 owner 隔离对齐）。
- 编排：DAG 定义、运行记录、影响分析结果。

**components**
- dbx：连接管理、查询执行、schema、MQ 管理、ER/血缘可视化、AI、历史。
- datara 前端 SPA：工作流画布、任务/运行视图、影响分析结果视图。
- 编排 DAG（codex）：SQL/Python/shell 节点编排。
- 资源管理：Python/shell 执行运行时。
- 定期影响分析 DAG：定时读 dbx /history → 影响分析。

**files-touched（方向性，实施期细化）**
- datara-backend：datasource/*（废弃/改造为只读镜像）、sql_ide/*（废弃）、execution/*（迁移为 dbx 代理）、identity/*（保留/增强为薄身份服务）、api/*（改为代理）、run_sql 等执行入口（改走 dbx）。
- datara-newweb：views/datasource/*（废弃）、数据源相关 service（删除）、新增编排/影响分析视图。

## Risks & Open Questions

| # | 风险/问题 | 说明 | 处置 |
|---|---|---|---|
| R1 | 密码托管迁移 | datara 本地密码 → dbx；迁移期双写/过渡 | 单独批准；提供安全迁移与回退 |
| R2 | 流式 ETL | dbx MQ 是管理控制台（tenant/topic/message view），非「消费→转换→生产」管道 | 若需流式消费 MQ，仍由编排 + 资源运行时承担，dbx 仅做管理/查看 |
| R3 | 性能 | dbx 代理增加一跳；大表同步需评估服务端分页会话（result_session_id + page_size/row_offset） | P2 实测；必要时批处理 |
| R4 | 影响分析时效 | 「定期事后」非实时 | 明确周期（如每日）；按需缩短 |
| R5 | 身份与 dbx 隔离对齐 | dbx 单用户 + owner 隔离；datara 多用户/多项目如何映射到 dbx 连接可见性 | 薄身份服务设计期定义映射 |
| R6 | 编排接口契约 | codex 编排与 datara 的接口未定 | 编排对接阶段定义 |
| R7 | 治理链砍掉的后果 | 失去变更前拦截能力 | 用户已裁定：以「能跑通 + 操作日志 + 定期影响分析」为准 |
