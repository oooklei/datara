# Datara DAG 组件逐项前后端设计与使用规范

> 本文是 `docs/DAG组件化编排规范与Datara适配方案.md` 的**逐组件落地册**。总方案回答"应该怎么设计"，本文回答"每一个现有组件长什么样、前后端各做什么、怎么用、哪里没做完"。
>
> **结构性问题不在本文范围**。本文逐组件记录"现状 / 缺口 / 目标"，其中 G-01～G-25 的**修法**（组件声明契约 CDL、Plan 产物、deadline 状态机、端口与变量声明、6 阶段迁移路线）见 `docs/DAG组件声明契约与Plan产物设计.md`。
>
> 所有条目的事实来源（可复核）：
> - 前端：`datara-web/src/graph/profiles/dag.ts`（`nodeTypes` 权威注册表）、`types.ts`、`formLinkage.ts`、`workbench/Inspector.vue`、`workbench/GraphWorkbench.vue`
> - 后端：`datara-backend/master/dag.py`（`WORKER_TYPES`、图校验）、`master/engine.py`（`_execute_node` 派发表、各 `_exec_*`）、`worker/executor.py`（`register`/`EXECUTORS`）、`worker/executors/*.py`
> - 既有规范：`docs/increments/02-DAG组件清单与定义.md`、`docs/同步编排端点合一与设计态分离设计.md`、`datara-backend/docs/increments/D12`、`datara-backend/docs/increments/I11`

---

## 0. 阅读约定

| 标记 | 含义 |
|---|---|
| **现状** | 代码中已经存在并生效的行为，可直接依赖 |
| **缺口** | 已登记但未实现 / 实现与文档不一致，属于必须修复项 |
| **目标** | 建议改造后的形态，尚未落地，不得当作现状使用 |

关于组件编号的四个事实（重要）：

1. `dag.ts` 的 `nodeTypes` 共 **34** 个 key，与 C 编号**不是一一对应，也存在空缺与复用**：
   - `page_board` **没有 `code` 字段**，`demo_pipeline` 是 `code: ''`（空串）——两者都没有编号；
   - 旧编号 **C23（端点选择）/ C27 / C28** 已随"端点合一"改造**退役**，其能力分别并入 **C37（`endpoint_select`）/ C35（`condition_set`）/ C34（`field_map`）**；
   - 当前同步链实际占用 **C34~C37** 四个新编号，与 C17 / C24 两个运行态执行节点并存。
   - 权威台账以 `dag.ts` 的 `code` 字段为准，**不要**用"C 编号连续"做推断。
2. Master 侧 `_execute_node` 的 handler 字典 + `WORKER_TYPES` 共能路由 **37** 个 type：其中 `src_select`、`tgt_select`、`smoke` **没有** `nodeTypes` 前端条目（无法从画布拖出，只能由模板或历史图产生），属于隐性组件，必须补齐规格。
3. `nodeTypes` 中的 `src_base_orch`、`tgt_base_orch`、`file_sync_orch`、`stream_input`、`stream_fuse`、`stream_output`、`page_board`、`demo_pipeline` 共 8 个 type **不在** Master 路由表内。前 4 个是**落图即展开**的模板（正确，不需要路由）；后 4 个是**真实缺口**（见 7 与 G-14）。

---

## 1. 全量组件总表（权威路由真源）

`派发` 列含义：`master` = `_execute_node` 内 handler 字典；`passthrough` = handler 字典中的 `_exec_passthrough`；`worker` = 命中 `WORKER_TYPES` 后 `_dispatch_worker`；`worker(仅后端)` = 仅在 `WORKER_TYPES`/executor 存在、前端无条目；`未路由` = 落图即展开的模板。

| # | type | `code` | `categories` | 派发 | 后端落点 |
|---|---|---|---|---|---|
| 1 | `start` | C1 | general,sync,etl | master | `_exec_start` |
| 2 | `end` | C2 | general,sync,etl | master | `_exec_end` |
| 3 | `conditions` | C3 | general,sync,etl | master | `_exec_conditions` |
| 4 | `switch` | C4 | general,sync,etl | master | `_exec_switch` |
| 5 | `fork` | C5 | general,sync,etl | master | `_exec_fork` |
| 6 | `join` | C6 | general,sync,etl | master | `_exec_join` + `_try_activate` 策略 |
| 7 | `merge` | C7 | general,sync,etl | master | `_exec_merge` + `_try_activate` 策略 |
| 8 | `delay` | C8 | general,sync,etl | master | `_exec_delay` + `_on_timer` |
| 9 | `dependent` | C9 | general,sync,etl | master | `_exec_dependent` + `_poll_dependent` |
| 10 | `loop` | C10 | general,sync,etl | master | `_exec_loop` / `_loop_tick` / `_loop_finish` / `_loop_release_exit` |
| 11 | `variable` | C21 | general,sync,etl | master | `_exec_variable` |
| 12 | `assert` | C25 | etl,general | master | `_exec_assert` + `_assert_target` |
| 13 | `field_map` | C34 | sync | passthrough | `_exec_passthrough` |
| 14 | `field_map_union` | C36 | sync | passthrough | `_exec_passthrough` |
| 15 | `condition_set` | C35 | sync | passthrough | `_exec_passthrough` |
| 16 | `endpoint_select` | C37 | sync | passthrough | `_exec_passthrough` |
| 17 | `sql` | C11 | etl,general,sync | worker | `executors/sql.py:127` |
| 18 | `shell` | C12 | general,etl | worker | `executors/shell.py:12` |
| 19 | `python` | C13 | general,etl | worker | `executors/python.py:37` |
| 20 | `ssh` | C14 | general,etl | worker | `executors/ssh.py:166` |
| 21 | `procedure` | C15 | general,etl | worker | `executors/procedure.py:28` |
| 22 | `http` | C16 | general,etl | worker | `executors/http.py:62` |
| 23 | `file` | C22 | general,etl | worker | `executors/file.py:187` |
| 24 | `sync` | C17 | sync | worker(runtimeOnly) | `executors/sync.py:327` |
| 25 | `file_sync` | C24 | sync | worker(runtimeOnly) | `executors/file_sync.py:133` |
| 26 | `notify` | C26 | general,stream,etl | worker | `executors/notify.py:20` |
| 27 | `smoke` | — | — | worker(仅后端) | `executors/smoke.py:11` |
| 28 | `src_select` | C32 | sync | passthrough(仅后端) | `_exec_passthrough` |
| 29 | `tgt_select` | C33 | sync | passthrough(仅后端) | `_exec_passthrough` |
| 30 | `src_base_orch` | C29 | sync | 未路由（模板展开） | `buildSrcBaseChain` |
| 31 | `tgt_base_orch` | C30 | sync | 未路由（模板展开） | `buildTgtBaseChain` |
| 32 | `file_sync_orch` | C31 | sync | 未路由（模板展开） | `buildFileSyncChain` |
| 33 | `stream_input` | C18 | stream | 未路由（**缺口 G-14**） | — |
| 34 | `stream_fuse` | C19 | stream | 未路由（**缺口 G-14**） | — |
| 35 | `stream_output` | C20 | stream | 未路由（**缺口 G-14**） | — |
| 36 | `page_board` | 无 `code` 字段 | stream | 未路由（页面宿主，**缺口 G-17**） | 需后端 SSE/看板 API |
| 37 | `demo_pipeline` | `''` 空串 | general | 未路由（模板展开） | `template.modes[0].build` |

---

## 2. 跨组件通用契约

本节规则对全部 37 个组件生效，逐组件卡片只写差异部分。

### 2.1 前端通用规范

**注册**：组件是 `dag.ts` 的 `nodeTypes` 单一注册项，字段为
`type / label / icon / color / code / categories[] / desc / defaults? / form? / template? / page? / summary()`。
- `categories` 决定 Palette 分组归属，一个 type 可属多组（如 `variable` 同时在 general/sync/etl）。
- `defaults` 在拖入画布时浅拷贝写入 `node.data`，是**唯一**默认值来源；组件内不得再散落兜底常量。
- `form[]` 是**声明式**字段表，由 `Inspector.vue` 通用渲染，不为单组件写专用面板。已支持类型见第 7 节待收敛清单。
- `summary(d)` 返回字符串或对象，渲染在节点内与 Palette 预览，必须容忍缺字段（`String(d.x ?? '')`）。
- `page: { title, comp, w, h }` 表示该节点自带抽屉页面（如 `stream_output`→`StreamDataPage`、`page_board`→`BoardPage`）。

**端口**：
- 出端口写在 `outputs`（`{ id, label, kind? }`），`handle` 取 `id`。
- 分支类组件出端口数量**由 `branches[]` 动态生成**，额外固定 `default` 端口。
- 独占类组件（`start` / `end`）应限制入度 1、出度 1。
- **缺口**：`NodeSchema` 无 `inputs` 字段，入端口完全由隐式约定 + 运行时检查承担。

**落点约束**：`formLinkage.ts` 的"拖边即引用"负责自动回填 `params` / `constraints` / 字段映射。
- 硬前置：`src_select` / `tgt_select`（旧 `src_base` / `tgt_base`）必须先落图，再拉字段映射边。
- 隐式回填的字段**必须**在 Inspector 中显示为"已由连线推导"的只读态，不得让用户误以为可改。

**表达式**：`$[wf.xxx]` / `${wf.xxx}` 由 `vars_render.py` 在 Master 侧解析，前端**不得**自行求值（避免双真源）。

### 2.2 后端通用规范

**派发唯一入口**：`_execute_node`（`engine.py:567`）对每个节点按固定顺序处理：
1. 置 `RUNNING` + `start_time`；
2. **动态禁用/条件跳过**：`exclude.disabled` → SKIP；`condition` 表达式为假 → SKIP；`exclude.skipCond` 为真 → SKIP（三者均直接 `_advance_downstream`）；
3. `resolver.refresh_run_vars()` → `resolve_node(data, loop_iter)` 得到 `resolved` + `snapshot`；
4. 查 handler 字典（master 逻辑组件）→ 命中即执行返回；
5. 命中 `WORKER_TYPES` → `sync`/`file_sync` 先 `_merge_sync_chain_config` 合并链路配置，再 `_dispatch_worker`；
6. 全部未命中 → `FAILURE`，`outputs.error = "executor_not_implemented"`。

**Worker 派发消息契约**（`_dispatch_worker`，`engine.py:1548`）：

| 字段 | 来源 | 说明 |
|---|---|---|
| `taskId` | `row["id"]` | `t_task_instance.id`，worker 回写主键 |
| `instanceId` | `self.instance_id` | 实例隔离键 |
| `nodeType` / `name` | 图定义 | 回写用 |
| `attempt` | `row["attempt"]` | 重试计数 |
| `param` | `data` 剔除 `params/constraints/condition/exclude/branches/inputs/outputs` 后的**原始值** | 表达式未解析 |
| `param_resolved` | `resolver.resolve_node()` | **表达式已解析**，执行器应优先使用 |
| `var_snapshot` | 同上 | 变量溯源快照，写日志/取证 |
| `constraints` | `_constraints(node_id)` | 含 `priority`（队列权重）、超时、重试 |
| `param.partialInputs` | `_collect_partial_inputs()` | 链路字段级输入（I7 partial 模式） |

**幂等与重试**：
- 幂等主键：`(instanceId, nodeId, loop_iter, attempt)`。同 key 重复消息必须可安全重放。
- 重试由 Master 驱动（`timers_retry` → 回到 `SUBMITTED` → 再 `_execute_node`），**执行器内部不得自行重试**。
- 轮询循环 `_next_timeout()` 合并 `timers_delay / timers_retry / timers_dep` 三类定时器，最长 `POLL_INTERVAL_SEC`。
- kill 语义：`_mark_all_killed` 对 `sql/shell/python/ssh/smoke` 且处于 `RUNNING/RETRY` 的实例做进程/连接终止，其余仅置 KILL 终态。

**日志**：`LiveLog` 为 worker 侧实时日志通道，另有 `t_task_log` 持久化（10.3+）。master handler 的日志统一以 `[master]` 前缀写入 `log_lines`。

**状态写权**：仅 Master 写 `t_task_instance.state`；worker 只通过 Redis Stream 状态消息回写 `outputs` + `state` + 递增 `attempt`，由 Master 落库。

### 2.3 通用使用规范

- **单入口/单出口**：一个工作流建议恰有一个 `start`、一个或多个 `end`。多 `start` 会导致物化出多棵无源子图（validator 对 0 个和 >1 个 `start` 均报 **error**）。
- **可达性**：所有节点必须从 `start` 可达；**不可达节点保存时必须拒绝**，不得"保存后再也不执行"。
- **图规模**：`loop` 的 `maxIterations` 缺省为 `DEFAULT_MAX_ITERATIONS`；超过上限直接 `FAILURE`，**不静默截断**（但该字段 UI 未暴露，见 G-08）。
- **`end` 之后禁止再连出边** —— **这是规范要求，但当前无 validator 强制**（G-25）。

### 2.4 现有 8 条图级 validator（权威清单）

`dagProfile.validators` 实为 **8 条**（总方案文档早期写的"7 条"有误，已在总方案 §2.2 更正为 8）：

| # | 检查内容 | 级别 | 定位 |
|---|---|---|---|
| 1 | `detectCycle` —— 存在环（DAG 不允许环） | error | `dag.ts:1132` |
| 2 | `findBrokenEdges` —— 边指向不存在的节点 | error | `dag.ts:1140` |
| 3 | `start` 节点数量：0 个 → error「缺少起始节点」；>1 个 → error | error | `dag.ts:1143` |
| 4 | `end` 节点数量 >1 → **warn**（非阻断） | warn | `dag.ts:1148` |
| 5 | `findIsolated` —— 孤立节点（未连接）；`nodes.length <= 2` 时跳过 | warn | `dag.ts:1152` |
| 6 | `findDuplicateEdges` —— 重复边 | warn | `dag.ts:1154` |
| 7 | `streamSubgraphIssues` —— 流式子图完整性（I8） | warn | `dag.ts:1158` |
| 8a | 必填完整性：非 `runtimeOnly` 节点的 `required` 字段缺失 → **warn**「未配置」 | warn | `dag.ts:1161` |
| 8b | 分支出口完整性：有 `ports` 的节点 `ports(data).length === 0` → **error**；每分支应有说明与出边 | error/warn | `dag.ts:1171` |

**注意 8a/8b 都跳过 `runtimeOnly` 节点**（`sync` / `file_sync`），因为它们是运行态展开节点，设计态上本就不完整。

**当前缺失、建议补齐的 validator**（详见 §9）：
- `end` 出度必须为 0（G-25）
- `conditions` / `switch` 必须存在可连出的兜底分支（G-01）
- `fork` 出边数与 `parallel` 一致（G-03）
- `loop` 必须配置 `maxIterations`（G-08）
- 节点 `type` 必须在 `nodeTypes` 声明集合内（G-21，需服务端同步）

---

## 3. A 类 · 逻辑流控组件（C1~C10）

这 10 个组件全部由 Master 进程内联执行（`handler` 字典），**不产生 Redis 队列消息、不占 worker**。它们的共同点是：无 `ports` 函数、无 `outputs`，因此在 `DataNode.vue` 落入第三个渲染分支——**1 个匿名入端口 + 1 个匿名出端口**（handle id 为 `null`）。

### 3.1 `start` · 开始（C1）

| 项 | 内容 |
|---|---|
| 身份 | `type=start` `code=C1` `categories=[general,sync,etl]` `runtimeOnly=false` |
| 前端默认值 | `{}`（**无任何业务字段**），节点名由 `data.name` 承载 |
| 前端表单 | `form: []` 空表单；`page: { title:'节点运行详情', comp: NodeRunDetailPage, w:560, h:340 }` |
| 前端摘要 | `summary: () => '流程入口'`（常量） |
| 端口 | 匿名 target(Left) + 匿名 source(Right)，各 1 个 |
| 后端派发 | `engine.py:648 _exec_start` |
| 后端行为 | 置 `SUCCESS`，`outputs` 记录实例标识，然后 `_advance_downstream` 放行下游 |

**前端设计**：唯一职责是"图入口标记"。Inspector 对它不渲染任何业务字段，只显示名称（`data.name`）。`page` 抽屉复用 `NodeRunDetailPage`，用于运行态查看本节点的 attempt 与日志。

**后端设计**：`_exec_start` 是幂等的空操作。真实"生成 `instance_id`"发生在**工作流实例物化阶段**（`run()` 入口），而非本 handler。因此 `start` 节点被删除不会导致实例创建失败，但会导致图校验报"缺少起始节点"。

**使用规范**
- 每个工作流**必须且只能有一个** `start`：`dag.ts:1143-1147` 的 validator 对 0 个报 error、>1 个报 error。
- 不得在 `start` 之后接 `dependent`（依赖型节点应在数据就绪后作为入口使用，此时应把 `start` 放在它前面）。
- 不得给 `start` 配置 `condition` / `exclude`：虽然通用跳过逻辑（`engine.py:575-591`）允许任何节点带这些字段，但对入口节点生效会导致**实例创建后立刻全图 SKIP**，属于配置事故。

**误用与限制**
- 不要用多个 `start` 表达"多源并行"：会产生多个无源子图，`_advance_downstream` 只在物化出的行上推进，行为不可预期。
- `start` 不可携带出参给下游消费（无 `outputs` 语义）；需要变量请用 `variable`（C21）。

---

### 3.2 `end` · 结束（C2）

| 项 | 内容 |
|---|---|
| 身份 | `type=end` `code=C2` `categories=[general,sync,etl]` |
| 前端默认值 | `{}`，`form: []` |
| 前端摘要 | `summary: () => '流程出口'` |
| 端口 | 匿名 target(Left) + 匿名 source(Right) |
| 后端派发 | `engine.py:656 _exec_end` |
| 后端行为 | 置 `SUCCESS`，汇总结束并推进下游 |

**前端设计**：与 `start` 对称的无字段节点。**缺口**：出端口仍然渲染（1 个匿名 source），但语义上"结束"不应有出边；当前 `dag.ts` 的 8 条 validator **没有**"end 不得有出边"这一条（见 3.11 与第 6 节 G-07）。

**后端设计**：`_exec_end` 终结该分支。整图是否结束由 `_all_terminal()` 判定（所有行进入 `TERMINAL_STATES`），而非由 `end` 数量决定。

**使用规范**
- 允许多个 `end`（对应多分支各自收口），但 `dag.ts:1148-1149` 对 >1 个 `end` 报 **warn**（非阻断）。
- `end` 之后不得连出边：会物化出 `end` 的下游节点，且它仍会被激活执行——**语义错误且不报错**。这是当前最需要补的 validator。
- 不要用 `end` 表达"失败出口"：失败由状态机表达（节点 `FAILURE` → 下游 `SKIP`），不需要额外出口节点。

---

### 3.3 `conditions` · 条件分支（C3）

| 项 | 内容 |
|---|---|
| 身份 | `type=conditions` `code=C3` `categories=[general,sync,etl]` |
| 前端默认值 | `branches: [{ id:'br_yes', name:'是', expr:'${var} > 0' }, { id:'br_no', name:'否', expr:'' }]`（`BranchDef[]`） |
| 前端表单 | 1 个字段：`{ key:'branches', type:'branches', label:'条件分支（每分支填判断描述）' }` |
| 前端端口 | `ports: portsOf` → `branchListOf(data).map(b => ({ id:b.id, label:b.name }))`，**动态** |
| 前端摘要 | `branchListOf(d).map(b=>b.name).join(' / ') \|\| '未配置分支'` |
| 后端派发 | `engine.py:717 _exec_conditions`（`switch` 共用同一 handler） |
| 后端路由 | `dag.py branch_match` + 边 `sourceHandle` 匹配 |

**前端设计**
- 端口 = 分支数，一一对应。渲染进 `gnode-branch` 分支形态（`DataNode.vue:53`），每个分支独占一行、Handle 锚定行内右侧。
- `branch.id` 是**契约字段**：既是 Handle id，也是 `edge.sourceHandle`。改名会使已有连线断开（`GraphWorkbench.vue:760` 用 `ports.find(p => p.id === conn.sourceHandle)` 校验）。
- `expr` 允许留空（`br_no` 默认即空）表示"兜底分支"。**空 expr 的分支不参与表达式求值，靠顺序兜底**。
- validator（`dag.ts:1171-1179`）：`ports(data).length === 0` → error「未配置分支出口」。

**后端设计**
- 求值：`_exec_conditions` 对 `branches` 逐条 `eval_expr(expr, scope, resolver, loop_iter)`，**首个为真者胜**；全不匹配则**没有任何出边被置 ready**，下游永久不激活（不会自动 SKIP，只是不推进）。
- **缺口**：不存在"隐式 default 端口"。若用户删掉了兜底分支且所有分支都不匹配，实例会**挂起**而非失败，必须靠超时/人工介入。这是 P0 修复项（见 G-01）。
- 条件真源是 `params.branches[]`，路由真源是出边；两者不一致时以**表达式**决定走向，未连出的分支形同虚设。

**使用规范**
- 末位务必保留一个 `expr: ''` 的兜底分支，并把它的出边连到 `end`，避免挂起。
- 表达式只写判定式，值从 `${wf.*}` 取；不要在 `expr` 里做赋值。
- 分支数建议 ≤5，超过应改用 `switch`（值匹配）。

**误用与限制**
- 不要用 `conditions` 表达"两分支都要跑"——那是 `fork`（C5）。
- 不要在分支里读运行态变量（如 `run.loopIter`）做跨轮判定：`conditions` 在循环体内每轮都会重新求值，语义是"每轮重新分流"，容易造成部分轮次走空。

---

### 3.4 `switch` · 开关（C4）

| 项 | 内容 |
|---|---|
| 身份 | `type=switch` `code=C4` `categories=[general,sync,etl]` |
| 前端默认值 | `branches: [{id:'sw_a',name:'A',expr:'A'},{id:'sw_b',name:'B',expr:'B'},{id:'sw_d',name:'默认',expr:'*'}]` |
| 前端表单 | `{ key:'branches', type:'branches', label:'值匹配分支（填匹配值）' }` |
| 前端端口 | `ports: portsOf`（与 C3 完全相同的动态机制） |
| 前端摘要 | `${branchListOf(d).length} · 路匹配` |
| 后端派发 | `engine.py:726 _exec_switch` |

**前端设计**：与 `conditions` 共用 `portsOf`，差别只在**表单语义**（填"匹配值"而非判定式）与默认分支用 `expr:'*'` 通配。

**后端设计**：`_exec_switch` 与 `_exec_conditions` 是两个独立函数但行为对称，同样依赖 `branch_match` + `sourceHandle`。`*` 作为默认匹配值的语义——**G-02 已修复（2026-09-27）**：`engine.py:_decide_branch` 显式识别 `expr == '*'` 为默认分支（`default = branch`），不交给 `simpleeval` 求值，兜底行为确定。

**使用规范**
- `switch` 用于"按值路由"（枚举分发），`conditions` 用于"按条件路由"（布尔判定）。同一张图不要混用两种语义做同一件事。
- 必须保留默认分支并连到 `end`。

**误用与限制**
- `expr:'*'` 通配行为**已确认安全**（后端显式处理，不依赖 simpleeval）；仍建议在 `switch` 中保留 `expr:'*'` 作为末位默认分支。

---

### 3.5 `fork` · 并行分支（C5）

| 项 | 内容 |
|---|---|
| 身份 | `type=fork` `code=C5` `categories=[general,sync,etl]` |
| 前端默认值 | `{ parallel: 2 }` |
| 前端表单 | `{ key:'parallel', label:'并行度', type:'number' }` |
| 前端摘要 | `并行 ${d.parallel ?? 2}` |
| 端口 | 匿名 target + 匿名 source（**无 `ports`/`outputs`**） |
| 后端派发 | `engine.py:734 _exec_fork` |

**前端设计**：`form` 暴露 `parallel` 数字输入，但**没有** `ports` 函数按 `parallel` 生成 N 个出端口。

**后端设计**：`_exec_fork` 置 `SUCCESS` 后 `_advance_downstream`，由**出边**决定实际并行度。

**缺口（G-03，P0）**：`parallel` 字段**前后端都不消费**——前端不据此生成端口，后端不据此限制或复制出边。`parallel: 5` 配上 1 条出边，实际并行度是 1；配 5 条出边则 `parallel` 纯属摆设。修复方案二选一：
- **方案 A（推荐）**：删除 `parallel` 字段，并行度由出边数天然表达，摘要改为"并行 N 路（N=出边数）"；
- **方案 B**：`ports: (d) => Array.from({length: clamp(d.parallel,2,16)}, (_,i)=>({id:'p'+i,label:'路'+(i+1)}))`，并加 validator 校验 `出边数 === parallel`。

**使用规范**
- 并行分支的收口必须用 `join`（C6，AND）或 `merge`（C7，OR），不能直接汇到一个普通节点。
- 并行分支之间**不得共享可变状态**（如写同一张表的同一分区），worker 并行消费会撞车。

---

### 3.6 `join` · 汇聚（AND）（C6）

| 项 | 内容 |
|---|---|
| 身份 | `type=join` `code=C6` `categories=[general,sync,etl]` |
| 前端默认值 | `{}`，`form: []`（**无 policy 字段**） |
| 前端摘要 | `全部成功才触发（AND）`（常量） |
| 端口 | 匿名 target + 匿名 source |
| 后端派发 | `engine.py:740 _exec_join`；**策略判定在 `_try_activate`（`engine.py:542-550`）** |
| 后端字段 | `data.policy`，默认 `all_terminal`；可选 `all_success` / `any_success` |

**前端设计**：无表单。`policy` 是**后端已支持但前端未暴露**的字段（缺口 G-04）——用户无法在 UI 上选择 AND 之外的策略，只能改 `graph_json` 手改。

**后端设计**（两级判定，务必区分）：
1. **激活级**（`_try_activate`）：所有前驱边 `edge_status` 必须非 `None`（全部已决），否则不激活；
   - 任一前驱边 `broken`（上游 failure/kill）→ 直接 `SKIP`；
   - `policy == 'all_success'` 且任一上游 `SKIP` → `_skip_cascade`；
   - `policy == 'any_success'` 且无任一上游 `SUCCESS` → `_skip_cascade`。
2. **执行级**（`_exec_join`）：`outputs.upstreams = [{source, state}]` 摘要，然后 `SUCCESS`。

默认 `policy = all_terminal` 表示"**所有前驱都进入终态**即触发"（不要求全成功）——这与 UI 摘要"全部成功才触发"**不一致**（缺口 G-05，语义误导）。

**使用规范**
- `join` 的入边必须来自**同一层并行分支**（`fork` 的各路），否则等待语义不成立。
- 需要"至少一路成功就继续"时，当前 UI 做不到；要么改用 `merge`（C7），要么先补 `policy` 表单（G-04）。
- `join` 不做数据合并，只做时序同步与状态汇总；需要合并数据用 `merge`。

---

### 3.7 `merge` · 合并（OR）（C7）

| 项 | 内容 |
|---|---|
| 身份 | `type=merge` `code=C7` `categories=[general,sync,etl]` |
| 前端默认值 | `{}`，`form: []` |
| 前端摘要 | `任一分支完成即触发（OR）` |
| 端口 | 匿名 target + 匿名 source |
| 后端派发 | `engine.py:747 _exec_merge`；策略在 `_try_activate`（`engine.py:551-553`） |
| 后端行为 | 取**第一个** `state=='ready'` 且有行的前驱，输出 `outputs.from = <该前驱的 outputs>` |

**前端设计**：无字段，语义固定为 OR。

**后端设计**：`_try_activate` 额外规则——若**所有**入边 `status == 'skipped'`，则 `_skip_cascade`（不触发）。否则任一前驱就绪即激活。`_exec_merge` 的数据合并是"**取第一个就绪前驱的 outputs 原样透传**"，**不是真合并**（多表拼接需显式用 `field_map_union` / `union all`）。

**使用规范**
- `merge` 的语义是"择一透传"，适合"任一分支产出结果即可下游消费"。
- 需要真正合并多路数据时，`merge` **不满足要求**，应在分支内用 SQL `union all` 或 `field_map_union` 节点完成。
- 全部分支被跳过时 `merge` 自身 `SKIP`，下游按 `SKIP` 链传播。

---

### 3.8 `delay` · 延时/等待（C8）

| 项 | 内容 |
|---|---|
| 身份 | `type=delay` `code=C8` `categories=[general,sync,etl]` |
| 前端默认值 | `{ duration: 60, unit: '秒' }` |
| 前端表单 | `duration`（number，延时时长）+ `unit`（select：秒/分/时） |
| 前端摘要 | `延时 ${d.duration ?? 0}${String(d.unit ?? '秒')}` |
| 端口 | 匿名 target + 匿名 source |
| 后端派发 | `engine.py:1051 _exec_delay` + `_on_timer`（`engine.py:1585-1591`） |
| 后端字段 | `duration` / `unit` / **`until`（后端支持、前端无表单，缺口 G-06）** |

**前端设计**：两个字段，单位下拉与后端映射严格对应：

| unit | 后端系数（`engine.py:1067`） |
|---|---|
| 秒 | 1 |
| 分 | 60 |
| 时 | 3600 |

**后端设计**
- 若 `data.until` 非空 → 先 `resolve_text` 渲染，再按 4 种格式尝试 `strptime`（`%Y-%m-%d %H:%M:%S` / `%Y-%m-%d %H:%M` / `%Y%m%d %H:%M:%S` / `%Y%m%d%H%M%S`）；解析成功则忽略 `duration`。
- 否则 `until = now() + duration × unit系数`。
- 写入 `row["delay_until"]` 与 `timers_delay[key]`，**节点保持 `RUNNING`**（不是等状态）。
- `_on_timer` 到期后：仅当 `row.state == RUNNING` 才置 `SUCCESS` + `outputs.waitedUntil`；若期间节点被 kill/重试，计时器被弹出而不生效（`timers_delay.pop` 后状态检查失败即静默丢弃）。

**使用规范**
- `delay` 是**阻塞型等待**：占用一个 Master 定时器槽位，不占 worker。大量并发 `delay` 不会压垮 worker，但会拉长实例时长。
- 需要"到点自动继续"用 `until`（需先补前端字段），需要"等外部系统就绪"用 `dependent`（C9），不要用超长 `delay` 轮询替代。
- `duration` 允许 0（立即到期），但会产生一次无意义的定时器往返。

**误用与限制**
- `delay` **不解决跨实例依赖**。它只等时间，不看别的任务状态。
- 不要在 `loop` 体内放 `delay`：每轮迭代都会等一次，累计时长 = `迭代数 × duration`，极易超出预期。

---

### 3.9 `dependent` · 依赖（C9）

| 项 | 内容 |
|---|---|
| 身份 | `type=dependent` `code=C9` `categories=[general,sync,etl]` |
| 前端默认值 | `{ deps: [] }`（`DependentDef[]`） |
| 前端表单 | `{ key:'deps', type:'deps-list', label:'依赖实例/任务' }` |
| 前端摘要 | `depSummary(d)` |
| 端口 | 匿名 target + 匿名 source |
| 后端派发 | `engine.py:1074 _exec_dependent` → `WAITING_DEPENDENCY` → `timers_dep` → `_poll_dependent` |
| 后端字段 | `deps[]`：`wf` / `node` / `nodeName` / `cond` / `expected`；兼容旧字符串格式 |

**前端设计**：`deps-list` 是专用复合编辑器，负责：选工作流（`wf` 存 `wf_xxx` id 或 code）→ 选节点（`node`）→ 填 `cond`。`depSummary` 渲染为紧凑摘要。

**后端设计**
- `_exec_dependent` 置 `WAITING_DEPENDENCY` 并注册 `timers_dep[key] = now()`，**立即返回**，由主轮询循环 `_on_timer`（`engine.py:1603-1609`）周期调用 `_poll_dependent`。
- 状态保护：若节点已非 `WAITING_DEPENDENCY`（被 kill/重试/取消），定时器条目直接丢弃。
- `_parse_deps` 双格式兼容：
  - 新格式 `list[dict]`：逐条 `_resolve_wf_code`（纯数字直接当 code；`wf_xxx` 查 `WfDefinition` 转 code；查不到记 warning 并用 0）。
  - 旧格式字符串：按 `;` / `,` / 换行切块，块内按 `:` 切 `code:节点名:期望状态`，`expected` 缺省 `success`。
- 判定：`_dep_cond_ok` 校验被依赖实例的**节点状态**是否等于 `expected`（默认 `success`），全部满足才放行。

**使用规范**
- 依赖是**跨工作流**机制；同图内的先后顺序必须用边表达，不要用 `dependent`。
- 每条依赖必须显式指定 `expected`，不要依赖默认 `success`（被依赖节点若是 `FAILURE` 但你期望"失败也算完成"，默认会永久等待）。
- 依赖的工作流若被删除，`_resolve_wf_code` 返回 0 → 该依赖**永远不满足** → 实例挂起。上线前应加"依赖目标缺失则 FAILURE"的守卫（G-07）。

**误用与限制**
- 不构成循环依赖检测：两个工作流互相 `dependent` 会双方永久 `WAITING_DEPENDENCY`。
- `cond` 表达式的求值上下文是**被依赖实例**的变量空间，不是当前实例，容易写错。

---

### 3.10 `loop` · 循环容器（C10）

| 项 | 内容 |
|---|---|
| 身份 | `type=loop` `code=C10` `categories=[general,sync,etl]` |
| 前端默认值 | `{ collection: '', batchSize: 100 }` |
| 前端表单 | `collection`（text，placeholder `${loop_items}`）+ `batchSize`（number） |
| 前端摘要 | `批次 ${d.batchSize ?? 0}` |
| 端口 | 匿名 target + 匿名 source |
| 后端派发 | `engine.py:1245 _exec_loop` / `1259 _loop_tick` / `1281 _loop_finish` / `1288 _loop_release_exit` / `1300 _loop_dispatch_body` |
| 后端字段 | `collection`、`batchSize`、`condition`（终止条件）、`maxIterations`（硬上限，UI **未暴露**，缺口 G-08） |

**前端设计**：两个字段。`collection` 的语义是"要遍历的数据/表达式"，支持三种写法（见后端 `_loop_should_terminate`）：
1. 逗号分隔列表：`a,b,c` → 3 个元素，按 `batchSize` 分批；
2. 纯数字：`10` → 迭代 10 次；
3. 空 → 只跑 1 轮。

**后端设计**（`engine.py:1229-1243` 终止判定，优先级从上到下）
1. `condition` 非空 → 表达式为**真**即终止（注意：这是"继续条件"语义还是"终止条件"取决于写法，`_loop_should_terminate` 返回 True 就停）；
2. `collection` 解析后含 `,` → 按 `,` 切分，`batch = max(1, batchSize)`，当 `loop_iter >= ceil(元素数 / batch)` 时终止；
3. 解析结果是纯数字 → 当 `loop_iter >= 该数字` 时终止；
4. 兜底 → 当 `loop_iter >= 1` 时终止（**只跑一轮**）。

**迭代生命周期**
- `_exec_loop`：无循环体成员 → 直接 `_loop_finish(0)`；否则置 `RUNNING`、`loop_iter_now=1`、`_loop_dispatch_body(node, 1)`。
- `_loop_dispatch_body`：把 `loop` → 体内成员的边置 `ready@iteration`，为体内所有成员**新建** `TaskInstance`（`loop_iter=iteration`），再逐个 `_try_activate`。即**每轮迭代生成一套全新任务实例行**。
- `_loop_tick`（由体内最后一个节点完成驱动）：循环节点已终态则直接返回（保证 kill/中断能立刻掐断）；否则先判终止 → 未终止且 `iteration + 1 > maxIterations`（`DEFAULT_MAX_ITERATIONS`）→ 置 `FAILURE`（`outputs.iterations`）并推进下游；否则 `iteration+1` 继续派发。
- `_loop_finish`：置 `SUCCESS` + `outputs.iterations`，推进下游，释放出口。
- `_loop_release_exit`：把回边（`back_edges`，指向 `loop` 的边）之外、其源节点的其他出边置 `ready@0` 并激活——**循环体结束后的"逃逸边"在此放行**。
- `_loop_exit_gate_ok`（`engine.py:504-517`）：`loop_iter == 0` 时，若某前驱是回边源，则要求该回边指向的 `loop` 节点必须 `SUCCESS`；否则挡住 `@0` 的逃逸路径，避免循环未完成就逸出。

**使用规范**
- 循环体成员由**图的可达性**决定：能从 `loop` 到达但不经过回边的节点集合（`loop_members`）。画图时用一条回边（体内末节点 → `loop`）表达"重复"，用另一条出边表达"逃逸"。
- **必须**设 `maxIterations`（或让 `collection`/`condition` 有明确终止逻辑）。默认上限触顶是 `FAILURE` 而非静默截断。
- 循环体内节点每轮都是**新任务实例**（`attempt` 从 1 重新计），历史可追溯，但行数 = 迭代数 × 体内节点数，注意 `t_task_instance` 膨胀。
- 变量 `run.loopIter` / `loop_items` 在循环体内可用（`resolver.runtime_scope(loop_iter)`）。

**误用与限制**
- 不要在循环体内放 `delay`（见 3.8）。
- 不要嵌套循环：`_loop_exit_gate_ok` 与 `loop_iter` 均为单层设计，嵌套会破坏逸出闸门。
- `batchSize` 只影响"逗号列表"的批大小，**不影响**每轮执行哪些数据（当前无按批切片下发的能力，G-09）。

---

## 4. B 类 · 变量与校验（Master 内联）

### 4.1 `variable` · 变量声明（C21）

| 项 | 内容 |
|---|---|
| 身份 | `type=variable` `code=C21` `categories=[general,sync,etl]` |
| 前端默认值 | `vars: [{ name:'wf.period', value:'20261001', type:'literal', override:false }]`（`VarDef[]`） |
| 前端表单 | `vars`（`var-table`：变量名/值/类型/可否覆盖）+ `varHint` |
| 前端摘要 | `varSummary(d)` |
| 端口 | 匿名 target + 匿名 source |
| 后端派发 | `engine.py:766 _exec_variable` |

**前端设计**：`var-table` 每行 4 列——变量名、值、类型（`literal` / `expr` / `time`）、覆盖开关。hint 文案明确了三级变量优先级链：**运行实例 > 工作流定义 > 全局**。

**后端设计**（`engine.py:766-825`）
- 三种 `type` 的求值方式：
  - `literal` → 原样字符串；
  - `expr` → `eval_expr(raw, scope, resolver, loop_iter)`，失败降级为 `False`；
  - `time` → `time_var(raw, resolver.base_time)`，支持 `yyyyMMdd-1` 这类时间模板（对应 F49）。
- **覆盖规则**：`override=false`（默认）时，若变量名已存在于 `run_existing`（本次实例已注册）或 `wf_defined`（工作流级定义），则**跳过注册**并记入 `skipped` 日志（"xxx 已通配，"强制覆盖=本地"）。即默认不覆盖上层。
- 写入三处，保持一致：`set_run_vars(instance_id, items)` → `resolver.refresh_run_vars()` → `WorkflowInstance.variables["varSnapshot"]` 合并快照。
- `outputs.injected = items`（仅本次真正注入的变量）。
- 快照落到 `t_task_log`（`_snapshot_lines`），可做变量溯源。
- 异常隔离：写 `WorkflowInstance.variables` 失败仅 `logger.warning`，**不影响节点成功**（有意降级）。

**使用规范**
- `variable` 必须在**所有使用它的节点之前**执行（用边约束），否则读到的是旧值。
- 需要覆盖上层同名变量时必须显式打开 `override`，否则静默跳过——这是最常见的"变量没生效"原因。
- `expr` 只能引用当时已可见的变量空间（`_expr_scope`：变量各级 + 本节点 `params` + 运行态 `loop_iter`），**不能引用下游节点的产出**。
- 变量名建议带域前缀（`wf.` / `biz.`），避免与保留名冲突（`vars_render.py` 维护保留名清单）。

**误用与限制**
- 不要用 `variable` 做数据传递（表 → 表）：那是 `outputs` 的职责。`variable` 只注入**字符串标量**。
- `time` 类型的基准时间是 `resolver.base_time`（实例创建时刻），不是节点执行时刻——长实例中跨小时计算要注意。

---

### 4.2 `assert` · 数据校验（C25）

| 项 | 内容 |
|---|---|
| 身份 | `type=assert` `code=C25` `categories=[etl,general]` |
| 前端默认值 | `ASSERT_BASE()`（工厂函数生成） |
| 前端端口 | **静态 2 端口**：`ports: () => [{id:'success',label:'通过'},{id:'failure',label:'不通过'}]` |
| 前端表单 | `assertSrc` / `assertUpstream` / `assertDs` / `assertTable` / `rules` / `ruleColumns` / `onFail` / hint |
| 前端摘要 | 按 `assertSrc` 分支：上游模式显示"N 条规则"，手工模式显示"校验 schema.table @ 数据源（N 条规则）" |
| 后端派发 | `engine.py:827 _exec_assert`（目标解析 `885 _assert_target` / `921 _assert_upstream_target`） |
| 后端状态 | **不产出 FAILURE 终态**（除目标解析失败），而是通过 `chosen` 走 success/failure 两条出边 |

**前端设计**
- 端口是**固定两出口**（`success` / `failure`），与 `conditions`/`switch` 的动态分支不同。两条出边都是普通 `flow`/`branch` 边。
- `assertSrc` 二选一：
  - `upstream`（默认）：Inspector 用 `upstream-ref` 选上游节点，**留空则由 Master 自动扫描**；
  - `manual`：手工填 `assertDs` + `assertTable`（`table-picker`，`writeAs:'schemaTable'` 双态）+ `ruleColumns`（`field-select` 挑参考列）。
- `ruleColumns` 只在 `manual` 模式出现，因为上游模式下参考列由被校验节点自动提供。
- `onFail`：`fail`（有异常项 → 节点 `FAILURE`，不产出 failure 边）/ `warn`（→ 节点 `SUCCESS` 但走 `failure` 边）。这是**唯一**决定"校验不通过是否阻断"的开关。

**后端设计**
- **目标解析（`_assert_target`）**：
  - `manual` → 直接取 `assertDs` + `assertTable`（兼容 `table-picker` 的 `{schema,table}` 对象与裸字符串两种形态）；`ds_ref` 或 `table` 任一为空 → 返回 `None`。
  - `upstream` → 先按 `assertUpstream` 指定的节点 id 解析；解析异常或留空 → **自动扫描直接前驱**（`graph.preds` 顺序遍历，取第一个能解析出目标的）。
  - 支持的上游类型（`_assert_upstream_target`）：`sync`（取 `writerDs` + `writerTable`）、`file_sync`（取 `targetDs`/`targetTable`/`targetSchema`）、SQL 类（读该节点 `data.outputs.tables` 的 `[{k,v}]`，`v` = 实际表名 + datasource）。均无法解析 → `None`。
- **未解析到目标** → 节点 `FAILURE`，`outputs.error = "assert_target_unresolved"`，然后**照常推进下游**（不挂起）。
- **数据源不存在/连接失败/查询异常** → 均 `FAILURE` + `outputs.error`。
- **规则判定**（`_assert_rules`，仅生成 SQL 不返回结果）：行数 `rows`（`min=1,max=1000`）、唯一性 `unique`（枚举或表达式）、非空 `not_null`（可配逗号分隔列）、`sql`（自定义表达式）、正则 `name,95%` 等。**全部异常项数 = 0 视为通过**。
- **路由**：`failed.length === 0` → `chosen = {id:'success', name:'通过'}`；否则 `chosen = {id:'failure', name:'不通过'}`。`chosen` + `edge.sourceHandle` 匹配生效，**与 `conditions`/`switch` 同一套路由机制**。
- `onFail='fail'` 且有异常项 → 节点 `FAILURE`（`outputs={error:'assert_failed', failed:[...]}`），**且不走 failure 边**——即"硬失败"语义。

**使用规范**
- `assert` 应紧贴被校验节点**下游**，用于"数据落地后立刻体检"。
- 需要"校验不通过也继续处理"时，`onFail` 必须选 `warn`（并把 `failure` 边接到隔离区/quarantine 节点），否则整个实例失败。
- 需要"校验不通过就阻断"时选 `fail`（默认），此时**不要**再连 `failure` 边（不会被触发，连了会造成"看起来有隔离路径其实没有"的误解）。
- 上游自动扫描依赖前驱顺序，上游多于 1 个时**必须**显式指定 `assertUpstream`，否则结果不确定。

**误用与限制**
- `assert` 只做**数据断言**，不做业务断言（业务判断用 `conditions`）。
- 规则 SQL 由后端拼接生成，**不要在规则里写 DDL/DML**。
- 一致性校验（唯一/非空）在大表上开销高，建议配合 `condition_set` 的 `filterExpr` 先收窄范围。

---

## 5. C 类 · Worker 执行组件

本类 9 个可见组件 + 1 个隐性组件全部走 `_dispatch_worker` → Redis Stream → worker `EXECUTORS[node_type]`。

**统一契约**（详见 2.2）：`param`（原始值）/ `param_resolved`（表达式已解析，执行器应优先用）/ `var_snapshot` / `constraints` / `param.partialInputs`。
**统一返回**：执行器返回 `ExecResult(state, outputs, logs)`；`outputs` 的每个 key 会成为下游可引用的 `outputs.<key>`。
**统一失败语义**：抛异常或返回 `FAILURE` 均导致节点 `FAILURE` → 下游 `SKIP`；重试由 Master 驱动。

### 5.1 `sql` · SQL（C11）

| 项 | 内容 |
|---|---|
| 身份 | `type=sql` `code=C11` `categories=[etl,general,sync]` |
| 前端默认值 | `{ datasource:'', sql:'', pre:'', post:'' }` |
| 前端表单 | `datasource`（`dsTypes:['mysql','greatdb']`）/ `sqlInsert`（`token-insert`，选表选列插入 SQL 片段）/ `sql`（textarea）/ `pre`（前置 SQL）/ `post`（后置 SQL） |
| 前端摘要 | `String(d.datasource)` |
| 前端页面 | `page: { title:'SQL 语句预览', comp: SqlPreviewPage, w:620, h:380 }` |
| 端口 | 匿名 target + 匿名 source |
| 后端落点 | `worker/executors/sql.py:127 execute`，`@register("sql")` |
| 后端 outputs | `results`（全语句摘要）+ `row_count` + `result_preview{columns,rows}` + **血缘计数** `{lineage_edges, lineage_fields}` |

**前端设计**
- `sqlInsert` 是 `token-insert` 类型：依赖 `datasource` 已选（`showIf: d => !!d.datasource`），调 `GET /datasources/{id}/tree` 选表选列，把生成的 SQL 片段插入 `sql` 文本域光标处。**它只是文本生成器，不代替手写**。
- `SqlPreviewPage` 抽屉调 worker 的 `result_preview` 展示查询前 200 行（real 模式取实际执行结果）。

**后端设计**（`sql.py`）
- 按 **`pre` → `sql` → `post`** 三阶段顺序执行，每条语句由 `_split_sql` 切分。
- `_run_one` 返回每条的 `rowCount` / `columns` / `rows` 摘要（`_jsonable` 做 JSON 化）。
- **血缘上报**（I5 F24）：执行后统计血缘边与字段数写入 `outputs.lineage_edges` / `lineage_fields`，失败/空结果**也会上报**（不阻塞成功）。
- `outputs.results` 汇总全部语句摘要；`row_count` / `result_preview` 取**最后一条**语句的结果。
- 数据源引用兼容 `datasource` 与 `datasource_id` 两种 key。

**使用规范**
- `pre` 用于建临时表/清空，`post` 用于收尾（如建索引、更新统计信息）；三阶段共享同一连接。
- **必须**在 SQL 里用 `param_resolved` 已渲染的值（占位符在 Master 侧替换），不要在 worker 里再拼变量。
- 大结果集不要用 `SELECT *`：`result_preview` 会带列与行，需控制列宽。
- 破坏性语句（`TRUNCATE`/`DROP`）建议单独成节点并配 `notify`，便于事后追溯。

**误用与限制**
- 不支持跨数据源单节点join（`datasource` 单值）；跨源请用 `sync`（C17）。
- DDL 与 DML 混在一个节点里时，某条失败会导致**该阶段整体失败**，已执行部分不自动回滚。

---

### 5.2 `shell` · Shell 脚本（C12）

| 项 | 内容 |
|---|---|
| 身份 | `type=shell` `code=C12` `categories=[general,etl]` |
| 前端默认值 | `{ script:'' }` |
| 前端表单 | `script`（textarea，placeholder `#!/bin/bash ...`） |
| 前端摘要 | 常量 `'Shell 脚本'` |
| 后端落点 | `worker/executors/shell.py:12 execute` |
| 后端 outputs | `parse_kv_outputs(stdout)` —— 解析 stdout 中的 `KEY=VALUE` 行 |

**前端设计**：单字段。注意 `param.env` **没有前端表单**（后端 `build_env(param.get("env"))` 支持），配置环境变量需改 `graph_json`（缺口 G-10：应补 `env` 的 `kv-table` 字段）。

**后端设计**（`shell.py`）
- 脚本落盘到 `run_dir` 后以 `["bash", script_path]` 执行（`run_stream` 流式读取 + 实时日志）。
- 退出码非 0 → `FAILURE`；否则 `SUCCESS`。
- `outputs` 来自 `parse_kv_outputs`：正则匹配 stdout 的 `KEY=VALUE` 行，**这是脚本向下游传值的唯一途径**。

**使用规范**
- 向下游传值：脚本内 `echo "MY_KEY=some_value"`，下游用 `${outputs.MY_KEY}` 引用。
- 必须用 `ctx.killed` 语义（`run_stream` 已内置）：长循环脚本要能被 kill 打断。
- 环境变量走 `env`（当前需手改 JSON），**不要**在脚本里硬编码连接串。

**误用与限制**
- 脚本无沙箱：以 worker 进程用户权限执行，**等价于在 worker 主机上执行任意代码**。仅用于可信环境。
- 不要用 `shell` 做数据搬运（应用 `sync`/`file`）；它只适合环境准备、调用外部 CLI、运维脚本。

---

### 5.3 `python` · Python 脚本（C13）

| 项 | 内容 |
|---|---|
| 身份 | `type=python` `code=C13` `categories=[general,etl]` |
| 前端默认值 | `{ script:'' }` |
| 前端表单 | `script`（textarea） |
| 前端摘要 | 常量 `'Python 脚本'` |
| 后端落点 | `worker/executors/python.py:37 execute` |
| 后端 outputs | 同 `shell`：`parse_kv_outputs(stdout)` |

**前端设计**：单字段。`param.requirements` 与 `param.env` 后端支持（`_check_requirements` 校验、`build_env` 注入）但**前端无表单**（缺口 G-10 同类）。

**后端设计**（`python.py`）
- 先 `_check_requirements(param.requirements)`，缺包直接 `FAILURE`（不会尝试安装）。
- 环境固定注入 `PYTHONUNBUFFERED=1`（保证 stdout 实时可读，否则 `parse_kv_outputs` 拿不到输出）。
- 失败时把已捕获的 stdout 解析后一并作为 `outputs` 返回（便于定位）。

**使用规范**
- 输出必须 `print("KEY=VALUE", flush=True)` 才会被 `parse_kv_outputs` 捕获；`PYTHONUNBUFFERED` 已保证，但仍建议显式 flush。
- 依赖必须在 `requirements` 中声明（哪怕 worker 镜像已装），保证环境可复现。

---

### 5.4 `ssh` · 远程脚本（C14）

| 项 | 内容 |
|---|---|
| 身份 | `type=ssh` `code=C14` `categories=[general,etl]` |
| 前端默认值 | `{ runtimeNode:'', execNodeTag:'', script:'' }` |
| 前端表单 | `execNodeTag`（`exec-node-tag`）/ `runtimeNode`（`runtime-node`，`showIf: 无 execNodeTag`）/ `script`（textarea，脚本内容或远程路径，**走 stdin**） |
| 前端摘要 | `SSH @ 标签:xxx` / `SSH @ 节点` / `SSH 远程脚本` |
| 后端落点 | `worker/executors/ssh.py:166 execute` |
| 后端 outputs | `parse_kv_outputs(stdout)` |

**前端设计**
- **二选一定位**（I7 支持"只选标签 → 运行时节点 → 直连"三级寻址）：填了 `execNodeTag` 则**不显示** `runtimeNode`；两者都空 → 走直连模式（`script` 填主机地址）。
- `exec-node-tag` 编辑器把标签展开成**运行时节点候选列表**。
- 私有密钥通过 `_load_pkey` 加载，不落 `param`（安全设计，不要试图把它做成表单字段）。

**后端设计**（`ssh.py`）
- `_route_by_tag(tag)` 把标签解析成节点列表；`param.runtimeNode` 兼容 `runtime_node_id`。
- `_connect` 建立 paramiko SSH 连接，`_run_on_node` 在远程目录执行并**回传 stdout/stderr**。
- 每个候选节点独立执行；**全部失败**才返回 `FAILURE`，任一成功即 `SUCCESS`（tag 多路语义）。
- `_run_on_node` 返回 `(mode, ExecResult)`，`mode='exec'` 表示已执行（用于区分"跳过"与"失败"）。

**使用规范**
- 标签寻址（`execNodeTag`）优先于节点寻址，可随环境扩容自动分发。
- 多节点 tag 场景下**每个节点都会执行一次脚本**——脚本必须幂等。
- 凭据走节点配置，不写进 `graph_json`。

---

### 5.5 `procedure` · 存储过程（C15）

| 项 | 内容 |
|---|---|
| 身份 | `type=procedure` `code=C15` `categories=[general,etl]` |
| 前端默认值 | `{ datasource:'', db:'', procedure:'', args:[] }` |
| 前端表单 | `datasource`（mysql/greatdb）/ `db`（目标库，**空=数据源默认库**）/ `procedure`（placeholder `sp_i4_demo`）/ `args`（`args-table`：IN 参数值 / OUT 参数列名） |
| 前端摘要 | `存储过程 @ 数据源` |
| 后端落点 | `worker/executors/procedure.py:28 execute` |
| 后端 outputs | `affected` + 每个 OUT 参数 `out_{key}` |

**前端设计**：`args-table` 每行含参数方向、参数名、IN 值 / OUT 列名。**IN 走值、OUT 走列名**——这是该组件的核心契约。

**后端设计**（`procedure.py`）
- `db` 空时回落到 `ds.db_name`。
- 逐个处理 `args`：IN 参数按序绑定；OUT 参数收集到 `outputs["out_%s" % key]`，`None` 保持 `None`，其余 `str(value)`。
- `outputs["affected"]` = 影响行数。
- 存储过程名由 `procedure` 字段给出（前端 placeholder 建议带 `sp_` 前缀约定，**不做强制校验**）。

**使用规范**
- OUT 参数值通过 `outputs.out_{列名}` 引用，列名是契约，**改名即断链**。
- 存储过程内部自行管理事务；Datara 侧无法回滚。
- 建议 `procedure` 名统一前缀（`sp_`/`i4_`）便于检索与权限隔离。

---

### 5.6 `http` · HTTP 请求（C16）

| 项 | 内容 |
|---|---|
| 身份 | `type=http` `code=C16` `categories=[general,etl]` |
| 前端默认值 | `{ url:'', method:'GET', headers:[], body:'', bodyType:'json', successCodes:'2xx', extract:[], timeout:30 }` |
| 前端表单 | `url` / `method`（GET/HEAD/POST/PUT/DELETE/PATCH）/ `headers`（`kv-table`）/ `bodyType`（json/form，GET/HEAD 隐藏）/ `body`（GET/HEAD 隐藏）/ `successCodes` / `extract`（`kv-table`）/ `timeout`（秒） |
| 前端摘要 | `METHOD url` |
| 后端落点 | `worker/executors/http.py:62 execute` |
| 后端 outputs | `status_code` + 每个抽取项以其 `out_name` 为 key |

**前端设计**
- `bodyType` / `body` 用 `showIf: !['GET','HEAD'].includes(method)` 联动隐藏——典型的**分型表单**写法。
- `extract` 是"响应提取（JSON 路径）"：`kv-table` 每行 `输出名 + JSON 路径`，后端 `_walk_path` 按路径取值。
- `successCodes` 文本框支持 `2xx` / `200` / 枚举（后端 `_ok_code` 解析）。

**后端设计**（`http.py`）
- `method` 强制 `upper()`；`headers`/`extract` 经 `_norm_rows` 归一为 dict。
- `timeout` 缺省 30 秒。**注意**：`timeout` 需同时受 `constraints` 的任务超时约束，取更严者。
- 状态码不满足 `successCodes` → `ExecResult(FAILURE, {status_code}, [])`（**带 status_code 输出**，便于排障）。
- 成功时按 `extract` 逐项取值：对象/数组 → `json.dumps`；标量 → `str`；**未取到则置空串**（不报错）。每项取值写日志。

**使用规范**
- 下游引用抽取值用 `${outputs.<输出名>}`。
- 抽取路径不存在时得到空串而非失败——**若该值是必需的，必须在下游用 `conditions` 显式判空**。
- 写操作（POST/PUT/DELETE）必须考虑幂等：HTTP 重试会重复提交。建议配合 `idempotency-key` 头。
- 超长 URL 走 `body` + POST，不要拼 query（受 URL 长度限制）。

---

### 5.7 `file` · 文件读取（C22）

| 项 | 内容 |
|---|---|
| 身份 | `type=file` `code=C22` `categories=[general,etl]` |
| 前端默认值 | `{ mode:'datasource', datasource:'', path:'', format:'csv', encoding:'utf-8', delimiter:',', header:true, sheet:'', register:true, tmpName:'', kind:'table', targetDs:'（运行态-默认 datara_dw）', retention:'immediate', keepDays:7 }` |
| 前端表单 | 17 个字段（含 3 个 hint），见下 |
| 前端摘要 | `${源} → ${tmpName}（${kind}）` 或 `${源}（未注册）` |
| 前端页面 | `page: { title:'文件预览数据', comp: TmpPreviewPage, w:680, h:440 }` |
| 后端落点 | `worker/executors/file.py:187 execute` |
| 后端 outputs | `columns`（列数）/ `preview_rows` / `rows_count` / `tmp_name`（注册时） |

**前端设计**（字段分组，全部用 `showIf` 联动）
- **来源**：`mode`（`datasource` / `manual`，`onChange: c22OnModeChange`）；`datasource`（`dsTypes:['file']`）仅 datasource 模式；`path`（相对 `/datara/files`）仅 manual 模式。
- **解析**（仅 manual）：`format`（csv/txt/excel）/ `encoding`（utf-8/gbk/gb18030）/ `delimiter`（非 excel）/ `header`（bool）/ `sheet`（仅 excel，**空=第一个**）。
- **注册为临时数据**：`register`（bool，**默认 true**）/ `tmpName`（3~32 位 `a-z0-9_`）/ `kind`（`table` 全量落地 / `resultset` 仅 JSON / `file` 文件+路径+schema）/ `targetDs`（仅 kind=table）/ `retention`（`immediate` 运行结束即扫 / `days` N 天 / `keep` 转正式表）/ `keepDays`（仅 days）/ `keepHint`（仅 keep）/ `tmpHint`。
- 引用方式：注册后下游用 `${tmp.<名字>}` 引用（`tmpRefHint` 生成提示文案）。

**后端设计**（`file.py`）
- `_resolve_spec`：mode 判定为 `datasource`（有 `datasource`）或 `manual`；datasource 模式经 `_lookup_datasource` 解析为物理路径。
- `_data_rows(spec)` 按 format 解析：csv/txt 用 delimiter+encoding+header；excel 用 sheet。
- 列名经 `_safe_columns` 消毒（防 SQL 注入/非法标识符）。
- `register=false` → 只统计（`outputs.columns` / `preview_rows`）直接返回。
- `register=true` → `_materialize`（批量 `_insert_batch` 写临时表）→ `_register_tmp` 登记临时数据；按 `kind` 分流 table/resultset/file。
- `retention` 由 `t_tmp_data` 生命周期管理：immediate 运行态扫、days 定时清、keep 正式化 RENAME 去前缀。
- `_count_rows` 输出 `rows_count`；`TmpPreviewPage` 抽屉读临时表展示前若干行 + schema + 概览统计。

**使用规范**
- `register=false` 适合"只校验文件能否解析/看行数"的探查场景。
- 需要被下游 SQL 引用**必须** `register=true`。
- `tmpName` 是引用契约（`${tmp.<名字>}`），**改名即断链**；命名体现业务含义，避免 `t1`/`a`。
- `retention=keep` 会把临时表 RENAME 成正式表（去 `tmp_` 前缀），是**不可逆**操作，执行后表名变化——用于"文件直接落地成正式表"的场景。
- 大文件用 `kind=file` + 后续 `sync` 增量入库，避免整文件落表。

**误用与限制**
- `header=false` 时列名由引擎生成（`col_0`…），下游按列名引用会失效。
- Excel 多 sheet 必须显式指定 `sheet`，否则只读第一个。
- 编码选错（GBK 文件按 utf-8 读）会乱码且**不报错**，需人工确认。

---

### 5.8 `notify` · 通知（C26）

| 项 | 内容 |
|---|---|
| 身份 | `type=notify` `code=C26` `categories=[general,stream,etl]` |
| 前端默认值 | `NOTIFY_BASE` |
| 前端表单 | `channel`（`log` / `webhook`）/ `url`（webhook 模式，**required**）/ `trigger`（`on_success` / `on_failure` / `always`）/ `template`（textarea）/ `notifyHint` / `failHard`（bool） |
| 前端摘要 | `webhook → URL` 或 `日志` |
| 后端落点 | `worker/executors/notify.py:20 run_notify` |
| 后端 outputs | 无 |

**前端设计**
- `url` 用 `showIf: d => d.channel === 'webhook'` 且 `required: true`；`failHard` 的 placeholder 明确"勾选=webhook 失败时本节点 failure，不勾=只留告警"。
- `template` placeholder 列出全部可用变量：`${wf.name} ${instance_id} ${node.name} ${node.status} ${sys.now}`。
- hint 明确：webhook 发送 `{"text": <消息>}` JSON POST，**超时 10s**，失败只留告警。

**后端设计**（`notify.py`）
- `url` 与 `template` 都经 `render_text` 渲染（**worker 侧二次渲染**，与 Master 的 `param_resolved` 不同——此处仍读 `param` 原文）。
- 日志记录 `channel`、`trigger`、是否带 URL、以及渲染后的消息全文（`notify` 是**取证节点**，日志即证据）。
- `failHard` 决定 webhook 失败时返回 `FAILURE` 还是 `SUCCESS`。

**使用规范**
- 通知内容里**必须**至少包含 `${wf.name}` 和 `${instance_id}`，否则事后无法定位是哪次运行。
- 关键节点（数据落地、校验、失败出口）都应挂 `notify`，`trigger` 按需选 `on_failure` / `always`。
- `failHard=true` 会让通知失败阻断主流程——只在你确实"宁可不跑也不可不知"时使用。
- `trigger` 字段后端仅记录（当前 executor 未据此跳过），若要做"只在失败时通知"的差异化投递，需在 `conditions` + `exclude` 里表达，或补后端逻辑（G-11）。

---

### 5.9 `smoke` · 冒烟自检（无前端条目）

| 项 | 内容 |
|---|---|
| 身份 | `type=smoke` **无 `nodeTypes` 条目、无 Palette 入口** |
| 所属 | `dag.py WORKER_TYPES` 成员 + `worker/executors/smoke.py:11 execute` |
| 后端落点 | `@register("smoke")` |
| 后端参数 | `name`（缺省取 `ctx.name`）、`delaySec`（缺省 1） |
| 后端 outputs | `{ echo:'hello', delaySec:<n>, workerHost:<hostname> }` |

**前端设计**：**缺失**。这是 P0 缺口之一（G-12）：`smoke` 在 `WORKER_TYPES` 中，能被 Master 派发、能被 worker 执行，但**无法从 Palette 拖出**，也没有 Inspector 表单。

**后端设计**：延时 `delaySec` 后返回固定 `hello` + worker 主机名，用于验证"队列通、worker 通、状态回写通"。

**使用规范**
- 用途仅限部署后自检：验证 Redis Stream 消费、Master 状态机、worker 注册表三条链路。
- 如需在 UI 上使用，必须先补 `nodeTypes` 条目（含 `form: [name, delaySec]`）与 Palette 分组。

---

## 6. D 类 · 数据同步编排组件

本类组件构成 Datara 的**同步编排链**（旧称"源基准/目标基准链"）。理解本节的关键是三件事：

1. **`endpoint_select`（C37）是 C32/C33 合一后的端点选择节点**，用 `baseMode` 三态替代了原来的 `src_base` / `tgt_base` / `file_base` 三个节点；
2. **`src_select`（C32）/ `tgt_select`（C33）是纯后端兼容节点**，没有 `nodeTypes` 前端条目，只在历史 `graph_json` 里存在，由 Master 直接映射；
3. **链上所有"细节节点"自己不执行**，它们的配置在 `sync` / `file_sync` 派发前被 Master 递归收集并**拍平进执行节点的 `param`**（`_merge_sync_chain_config`），执行器只看到一个扁平参数包。

### 6.1 链路拍平机制（先读这一节，再读各组件卡）

**参与拍平的节点类型**（`engine.py` `CHAIN_DETAIL_TYPES`）：
`src_select` / `tgt_select` / `field_map` / `field_map_union` / `condition_set` / `endpoint_select`

**拍平算法**（`_merge_sync_chain_config`，`engine.py:1520-1546`）
1. 从 `sync` / `file_sync` 节点出发，沿 `graph.preds` **递归向上**遍历；
2. 遇到 `CHAIN_DETAIL_TYPES` 成员就取其配置（`_chain_upstream_config`），调 `_apply_detail_config` 写入合并字典；
3. 记录合并日志（"从《节点名》合并: key=value, …（N 项）"），与 `partialInputs` 日志一起在派发时落库；
4. 递归**同层多路**（多个上游细节节点）时，**后写入者覆盖先写入者**（`merged[key] = val`），日志会完整记录每次覆盖。

**字段映射表**（`_apply_detail_config`，`engine.py:1404-1475`，"细节节点字段 → 执行节点 param 字段"）：

| 细节节点 | 条件 | 映射 |
|---|---|---|
| `src_select` | `file_sync` 且有 `fileSync`/`filePath` | `filePath→filePath` `fileType→fileType` `fileDelimiter→delimiter` `fileEncoding→encoding` `fileHeaderRows→headerRows` |
| `src_select` | 其他（库→库） | `ds→readerDs` `table→readerTable` `schemasText→readerSchemasText` `matchType→readerMatchType` `matchPrefix→readerMatchPrefix` `autoSchema→autoSchema` |
| `tgt_select` | `file_sync` | `ds→targetDs` `table→targetTable` |
| `tgt_select` | 其他 | `ds→writerDs` `table→writerTable` |
| `tgt_select` | 通用 | `autoCreate→autoCreate` |
| `field_map` | — | `fieldMap→fieldMap` |
| `field_map_union` | — | `fieldMap→fieldMap`；`addSchemaFlag` 真时额外 `flagColumn=srcSchemaField`（空则 `src_schema`）且 `strategy=src_flag` |
| `condition_set` | — | `filterExpr→readerWhere` `incrementalColumn→incrementalColumn` `incrementalExpr→incrementalExpr` |
| `endpoint_select` | `baseMode=file_sync` | 文件组同上 + `tgtDs→targetDs` `tgtTable→targetTable` + `autoCreate`（`False` 保留 `False`，`None`/缺省→`True`） |
| `endpoint_select` | `baseMode=src_base` | `srcDs→readerDs` `srcTable→readerTable` `autoSchema→False` + `tgtDs→writerDs` `tgtTable→writerTable` + `autoCreate` |
| `endpoint_select` | `baseMode=tgt_base` | `srcDs→readerDs` + `probeResult→readerSchemasText`（`_probe_schemas_text` 归一） + `matchType→readerMatchType` + `matchPrefix→readerMatchPrefix` + `readerTable=_probe_reader_table(probeResult, tgtTable)` + `tgtDs→writerDs` + `tgtTable→writerTable` + `autoCreate` |

**`put` 的关键语义**：只有"真值"才写入（`_detail_value` 过滤）——**字符串 `''`、`False`、`0`、`None` 都不写**。因此：
- `autoCreate` 必须用 `put("autoCreate", False if cfg.get("autoCreate") is False else True)` 这种**显式三元**写法，否则 `autoCreate=false` 会被 `put` 丢掉并回落成 `True`（**危险默认值**，代码中已用注释标注）。
- 同样地，`src_base` 模式下 `autoSchema` 强制 `False`（因为源表已确定，不允许多 schema 扫描）。

**运行态再物化**：`materialize_sync_exec(graph_json)`（`engine.py:59+`）在**实例启动时**扫描含 `sys_exec_` 前缀节点的设计态图，展开成运行态可执行图，并把节点 id 重写为 `sys_exec_ + md5(...)`（`SYS_EXEC_PREFIX`）。这一步把"画布上的一条同步链"变成"运行态的一串可执行节点"，也是 `assert` 能自动发现上游目标的前提（断言目标扫描依赖这一物化结果）。

### 6.2 `endpoint_select` · 端点选择（C37，合一 C32/C33）

| 项 | 内容 |
|---|---|
| 身份 | `type=endpoint_select` `code=C37` `categories=[sync]`，**在 Palette 的"数据同步"组可见** |
| 前端默认值 | `{ baseMode:'src_base', srcDs:'', srcTable:'', probe:false, matchType:'exact', matchPrefix:'', probeResult:'', tgtDs:'', tgtTable:'', autoCreate:true, filePath:'', fileType:'csv', fileDelimiter:',', fileEncoding:'utf-8', fileHeaderRows:1, fileSheet:'' }` |
| 前端端口 | **静态 2 端口**（`outputs`）：`{id:'sourceRef',label:'源端点'}`、`{id:'targetRef',label:'目标端点'}` |
| 前端表单 | 15 个字段，4 组，全部 `showIf` 联动（见下） |
| 前端摘要 | `{基准名}｜{源} → {目标}` |
| 后端 | 自身**不执行**（`_exec_passthrough`），配置经 6.1 拍平进 `sync`/`file_sync` |

**前端设计：三态分型（`baseMode`）**

| baseMode | 语义 | 源侧字段 | 目标侧字段 |
|---|---|---|---|
| `src_base` | 源端点已确定，目标按同名/前缀新建 | `srcDs`+`srcTable`（`table-picker`，`writeAs:'schemaTable'`） | `tgtDs`+`tgtTable`（`showIf≠tgt_base` 的那一条）+ `autoCreate` |
| `tgt_base` | 目标已确定，源侧需探测多 schema | `srcDs` + `probe`（bool）+ `matchType`（exact/prefix）+ `matchPrefix` + `probeResult` | `tgtDs`+`tgtTable`（`showIf= tgt_base` 的那一条） |
| `file_sync` | 文件为源 | `filePath`+`fileType`+`fileDelimiter`+`fileEncoding`+`fileHeaderRows`+`fileSheet` | `tgtDs`+`tgtTable`+`autoCreate` |

- **两个 `tgtTable` 字段并存**（`dag.ts:568-571`）：`showIf` 互斥，一个在 `tgt_base` 显示、另一个在 `src_base`/`file_sync` 显示。两者都写 `data.tgtTable`，**不冲突**（同一 key，条件互斥）。这是为了给两种模式不同的 placeholder 文案。
- **`probeResult` 是自由文本**（`ec_retail.order_detail, ec_retail_east.order_detail`），由后端 `_probe_schemas_text` 归一：支持 `{schema,table}` 对象数组（seed 直取）与 `schema.table, ...` 字符串（取点号前段）双态。
- **两个具名出端口** `sourceRef` / `targetRef` 就是"端点合一"设计的产物：它们是**设计态端口**（供连边表达"我选的是哪一端"），运行态会被拍平成 `reader*` / `writer*` 扁平字段。`field_map` / `field_map_union` 就是从这两个端口取上游引用的（`pick.fmSrcIndex` / `fmTgtIndex` 分别为 0/1 与 1/0）。
- `shape` 未设为 `device`，故按普通节点渲染（1 匿名入 + 2 具名出）。

**后端设计**：`_exec_passthrough` 立即 `SUCCESS`（它只是"选端点"这一步的记账）。真正的配置经 6.1 拍平。`baseMode` 决定映射分支——这是**整个同步链最重要的开关**。

**使用规范**
- 选 `src_base` 还是 `tgt_base`，取决于**哪一端是确定的**：源表已知、目标要新建 → `src_base`；目标表已知、源要跨 schema 聚合 → `tgt_base`。
- `file_sync` 模式：文件源**不走 SFTP 拉取**（`file_sync.py` 的 `_stage_remote` 处理远程暂存），要远程拉取需在 `file_sync` 执行节点上配 `runtimeNode`。
- `probe=true` 必须配合填 `probeResult`，否则源侧解析为空。
- `autoCreate=false` 时目标表必须**已存在且列结构匹配**，否则 worker 侧 `FileSourceError`/建表失败。

**误用与限制**
- 不要在同一条链上放**两个** `endpoint_select`（拍平时后者覆盖前者的 `readerDs`/`writerDs`）。多源/多目标应拆成多条链。
- `matchPrefix` 只在 `tgt_base` + `probe=true` 下有意义，其他模式填了会被忽略。
- `fileHeaderRows=0` 表示无表头——此时 `file_sync` 的列名由引擎生成，字段映射会失效。

---

### 6.3 `field_map` · 字段映射-单表（C34）

| 项 | 内容 |
|---|---|
| 身份 | `type=field_map` `code=C34` `categories=[sync]` |
| 前端默认值 | `{ inputs:[], fieldMap:[], outputs:[] }` |
| 前端表单 | `inputs`（`upstream-refs`，`upstreamMax:2`，**required**，顺序约定 `[0]=源端点` `[1]=目标端点`）/ `fieldMap`（`field-map`）/ `outputs`（`upstream-refs`，`upstreamMax:5`） |
| 前端摘要 | `{N} 入 · {M} 出`（`M` 取 `outputs.length`），无 WHERE 时附 `全量同步` |
| 端口 | 匿名 target + 匿名 source |
| 后端 | `_exec_passthrough`；配置拍平为 `fieldMap` |

**前端设计**
- `inputs` 的**顺序即语义**（`fmSrcIndex:0` / `fmTgtIndex:1`）——拖边即引用把上游节点写入 `inputs` 数组，顺序不能错。
- `fieldMap` 编辑器用 `pick` 精确告诉它去哪两个上游节点取元数据：`{ srcNodeType:'endpoint_select', tgtNodeType:'endpoint_select', srcDsKey:'srcDs', srcTableKey:'srcTable', tgtDsKey:'tgtDs', tgtTableKey:'tgtTable', fmSrcIndex:0, fmTgtIndex:1 }`。
- `outputs` 上限 5 个，用于把映射后的字段集显式传给下游节点（留空=映射全字段）。

**后端设计**：拍平为 `sync` 的 `param.fieldMap`，由 `sync.py:_column_pairs` 消费（`field_map` 参数 + `flag_column` 参与列对生成）。同名列自动配对（同名透传），异名走显式映射。

**使用规范**
- **必须**同时连上 `endpoint_select` 的 `sourceRef` 与 `targetRef` 两个端口（否则 `inputs` 不足 2，映射无法生成）。
- 同名同构的表可以留空 `fieldMap`（`summary` 显示"全字段同步"），执行器按同名列透传。
- 异构映射必须逐列配置，且注意目标侧列名不存在时需 `autoCreate=true`。

---

### 6.4 `field_map_union` · 字段映射-多表（C36）

| 项 | 内容 |
|---|---|
| 身份 | `type=field_map_union` `code=C36` `categories=[sync]` |
| 前端默认值 | `{ inputs:[], fieldMap:[], outputs:[], addSchemaFlag:true, srcSchemaField:'src_schema', aggOperator:'union_all' }` |
| 前端表单 | `inputs`（`upstreamMax:2`，顺序**相反**：`[0]=目标端点` `[1]=源侧探测结果`，`fmSrcIndex:1` / `fmTgtIndex:0`）/ `fieldMap` / `addSchemaFlag`（bool）/ `srcSchemaField`（text，`showIf addSchemaFlag`）/ `aggOperator`（select，**当前只有 `union_all` 一项**）/ `outputs`（`upstreamMax:5`） |
| 前端摘要 | `union all 合成N + 源标识(字段名)` |
| 端口 | 匿名 target + 匿名 source |
| 后端 | `_exec_passthrough`；拍平为 `fieldMap` + `flagColumn` + **`strategy='src_flag'`** |

**前端设计**：与 `field_map` 的关键差异有三点，必须记住：
1. **`inputs` 顺序相反**（`fmSrcIndex:1` / `fmTgtIndex:0`）——因为多表场景下 `[0]` 是目标端点、`[1]` 是源侧探测结果。
2. **`aggOperator` 是单选下拉且只有 `union_all`**（代码注释明确"目前唯一"）。**缺口 G-13**：UI 给了"聚合方式"的选择器外观却不给其他选项，属于误导性表单；要么补 `union`/`intersect`/`min/max` 等，要么改成只读 hint。
3. **`addSchemaFlag` 默认 `true`**，会自动给每行加一个 `src_schema` 标记列，**这是多 schema 汇总的必需项**（否则分不清数据来自哪个 schema）。

**后端设计**：拍平时若 `addSchemaFlag` 为真，**强制** `flagColumn = srcSchemaField` 且 `strategy = 'src_flag'`（见 6.1 映射表）。`sync.py:_plan_targets` 按 `strategy` 决定目标表规划策略；`_schema_suffix` 用于从 schema 名推导表名后缀。

**使用规范**
- 多 schema 汇总场景**必须**保留 `addSchemaFlag`，否则重复数据无法区分来源。
- `aggOperator` 当前只有 `union all`：需要去重语义时**不能**依赖此字段，应在源侧 SQL 用 `distinct` 或在目标侧做唯一约束。
- 目标表需要包含 `srcSchemaField` 指定的那一列（否则写入失败）。

---

### 6.5 `condition_set` · 过滤与增量（C35）

| 项 | 内容 |
|---|---|
| 身份 | `type=condition_set` `code=C35` `categories=[sync]` |
| 前端默认值 | `{ inputs:[], outputs:[], filterExpr:'', incrementalColumn:'', incrementalExpr:'' }` |
| 前端表单 | `inputs`（`upstreamMax:3`，**required**）/ `outputs`（`upstreamMax:3`）/ `filterExpr`（textarea，placeholder `create_time > ${last_sync_time} AND status = 1`）/ `incrementalColumn`（text）/ `incrementalExpr`（text，`showIf incrementalColumn`，placeholder `${yyyyMMdd-1}`） |
| 前端摘要 | `{N} 入 · {M} 出 · {filterExpr 截断 30 字} / 全量同步` |
| 端口 | 匿名 target + 匿名 source |
| 后端 | `_exec_passthrough`；拍平为 `readerWhere` + `incrementalColumn` + `incrementalExpr` |

**前端设计**
- `filterExpr` 留空 = 全量同步（`summary` 显式写"全量同步"，避免用户误以为没生效）。
- `incrementalExpr` 只在填了 `incrementalColumn` 后出现；placeholder 用 `${yyyyMMdd-1}` 对应后端 `time_var` 的 F49 模板能力。
- 支持 3 入 3 出，允许多条件组合。

**后端设计**：拍平为 `readerWhere`（进 `sync.py:_parse_file_where` 做条件解析与 `_cell_match`/`_row_matches` 逐行匹配）。注意 `readerWhere` 在 `sync.py` 中走的是**应用层过滤**（`_parse_file_where` / `_row_matches`）而非 SQL 下推——`_build_union_sql` 才生成带 WHERE 的 SQL。**增量水位**由 `incrementalColumn`/`incrementalExpr` 配合 `t_sync_checkpoint`（I7 checkpoint）维护，跨实例持久。

**使用规范**
- 增量必须同时配 `incrementalColumn`（列名）与 `incrementalExpr`（取值表达式），缺一不生效。
- 表达式里引用 `${last_sync_time}` 等水位变量，是跨实例的持久值；首轮无水位时需有默认分支。
- `filterExpr` 里的 `${}` 由 Master 渲染（`resolve_node`），不要写运行时才有的变量。

**误用与限制**
- 增量列**必须带索引**，否则每轮全表扫描。
- 不要在 `filterExpr` 里做跨表条件（应用层过滤无法下推，会全量读）。

---

### 6.6 `sync` · 数据库同步执行（C17，运行态节点）

| 项 | 内容 |
|---|---|
| 身份 | `type=sync` `code=C17` `categories=[sync]`，**`runtimeOnly: true`** |
| 运行态含义 | 不出现在 Palette / 画布右键菜单；由 `materialize_sync_exec` 从设计态链展开生成（`node.id` 带 `sys_exec_` 前缀） |
| 前端默认值 | `syncExecDefaults()` |
| 前端表单 | `chainHint`（hint，说明本节点是"运行态展开节点"）/ `batchSize`（默认 1000）/ `errorThreshold`（默认 0）/ `truncate`（bool，写前截断） |
| 前端摘要 | 常量 `'同步执行链（运行态展开节点）——由 master 合并链路'` |
| 前端页面 | `page: { title:'同步执行链', comp: NodeRunDetailPage, w:620, h:420 }` |
| 后端落点 | `worker/executors/sync.py:327 execute` |
| 后端 outputs | `read_rows` / `write_rows` / `bad_rows` / `skipped_rows` / `rows_per_sec` / `batch_id(=instance_id)` / `schemas_included` |

**前端设计**
- `runtimeOnly: true` 带来三个连带效果（`types.ts:191-192` 明确）：① 不进 Palette；② **不被右键菜单调出**；③ 跳过 `dag.ts:1161-1169` 的必填完整性 validator，也跳过 `1171` 的分支 validator。
- 仍保留 `form` 与 `page`：`form` 只暴露**执行策略参数**（批次/错误阈值/截断），链路细节（端点、字段映射、过滤）**全部来自上游拍平**，因此这里刻意不提供它们——避免"两处配置同一件事"。
- `chainHint` 直接告诉用户"你是运行态展开节点，链路配置在左侧的端点选择/字段映射/过滤节点上"。

**后端设计**（`sync.py`，库→库同步的核心）
- `param.strategy` 决定目标表规划策略（`union` 缺省 / `src_flag` / …，由 6.1 拍平写入）。
- `_resolve_schemas`：按 `readerSchemasText` / `readerMatchPrefix`（`"%s%%"` 模糊匹配）/ `autoSchema` 决定读哪些源 schema。`autoSchema=True` 时自动扫描。
- `_build_union_sql`：把多 schema 拼成 `UNION ALL` 的单条读 SQL（带 `readerWhere` 下推）。
- `_plan_targets` + `_schema_suffix`：按 schema 列表规划目标表（可能一源表对应多目标表）。
- `_column_pairs`：字段映射（`fieldMap`）+ `flag_column` 生成 (src,dst) 列对；`_create_target` 按 `autoCreate` 建表。
- 写入：`_insert_batch` + `_pump`（批大小 `batchSize`，缺省 1000），累计 `read_rows`/`write_rows`。
- `errorThreshold`：坏行数超过阈值则整节点 `FAILURE`（默认 0 = 零容忍）。
- `truncate`：`TRUNCATE` 目标表后写（**破坏性**）。
- **应用层过滤**：`_parse_file_where` + `_cell_match` + `_row_matches` 逐行匹配（对应 `condition_set` 拍平来的 `readerWhere`）。
- I7 partial 模式：`_collect_partial_inputs` 把上游字段级输入写入 `param.partialInputs`（`{source, table, fields, scope, resolved, upstreamRef}`），实现"只同步部分字段"。

**使用规范**
- 库→库同步**必须**通过 `src_base_orch` / `tgt_base_orch` 模板建链（会自动铺好 `endpoint_select` → `field_map` → `condition_set` → `sync`）。
- `truncate=true` 意味着目标表每次被清空——只适合"全量快照"语义。
- `errorThreshold=0` 时任何脏数据都会让整实例失败。上线初期建议先设一个容错值观察。
- 大表务必配 `incrementalColumn` + 索引，否则每轮全表。

**误用与限制**
- 不支持跨源跨目标的一次性多对多（拍平后只有一组 `readerDs`/`writerDs`）。
- `t_tmp_data` 临时表不参与 `sync`（那是 `file` 的产物，需先转正式表或走 `file_sync`）。
- 目标表列类型不做自动推断（`autoCreate` 按源列类型建），源列类型异常会直接建错表。

---

### 6.7 `file_sync` · 文件同步执行（C24，运行态节点）

| 项 | 内容 |
|---|---|
| 身份 | `type=file_sync` `code=C24` `categories=[sync]`，**`runtimeOnly: true`** |
| 前端默认值 | `{ fileType:'csv', delimiter:',', encoding:'utf-8', headerRows:1, autoCreate:true, writeMode:'append', flagColumn:'src_schema', fieldMap:[] }` |
| 前端表单 | `chainHint` / `writeMode`（`append` union 合并 / `overwrite` 覆盖式 TRUNCATE / `src_flag` 标识位写，每行带源标识）/ `flagColumn`（仅 `src_flag`）/ `autoCreate`（bool） |
| 前端摘要 | `文件同步｜${writeMode}（运行态展开节点——master 合并链路）` |
| 后端落点 | `worker/executors/file_sync.py:133 execute` |
| 后端 outputs | 写入行数/坏行/跳过行等（与 `sync` 同构） |

**前端设计**
- `writeMode` 三态是本组件的核心决策：
  - `append`：union 合并追加；
  - `overwrite`：TRUNCATE 后写（**破坏性**，等价于全量快照）；
  - `src_flag`：每行写来源标识列（列名 `flagColumn`，默认 `src_schema`）——用于"同表多来源"场景。
- `autoCreate` 缺省 `true`；`false` 时目标表须已存在且列匹配，否则抛 `FileSourceError`。
- 与 `sync` 一样是 `runtimeOnly`：链路细节（文件路径/类型/分隔符/编码/表头行/目标端点）来自 `endpoint_select(baseMode=file_sync)` 与 `file_sync_orch` 模板拍平。

**后端设计**（`file_sync.py`）
- `_resolve_source` 三级取源：① `stagedPath`（已暂存，直接用）→ ② `filePath` + `fileName` → ③ `runtimeNode`（按运行时节点 SFTP 拉取，`_stage_remote` 落到本地暂存区）。
- `_open_after_header(spec, header_rows)`：`headerRows=0` 时无表头（列名引擎生成），`>0` 时跳过 N 行表头。
- 目标端：`_lookup_datasource(targetDs)`（失败抛 `FileSourceError("目标数据源不存在: %s")`），`targetTable` + `targetSchema`。
- `writeMode` 决定写入策略；`fieldMap` 做列映射；`flagColumn`（strip 反引号，空则回落 `src_schema`）写来源标识。
- `autoCreate=false` → 目标表不存在直接报错（不隐式建表）。

**使用规范**
- 远程文件必须配 `runtimeNode`（或走 `execNodeTag`）才会被 SFTP 拉取；本地文件放 `/datara/files` 相对路径。
- `writeMode=overwrite` 是**破坏性**操作，务必确认目标表是可重建的中间表。
- 增量场景用 `append` + 时间戳列过滤，不要用 `overwrite`。
- 远程拉取大文件时注意暂存区磁盘与超时。

**误用与限制**
- 不做字段级类型转换（与 `sync` 同），源格式与目标列类型必须兼容。
- `file_sync` 只支持**单文件**；多文件需在 `loop` 内配合 `file` 分批落地。

---

### 6.8 `src_select` / `tgt_select` · 源/目标端点（后端兼容节点，无前端条目）

| 项 | `src_select`（C32） | `tgt_select`（C33） |
|---|---|---|
| 前端条目 | **无**（不在 `nodeTypes`，不在 Palette） | **无** |
| 后端路由 | `_exec_passthrough`（handler 字典） | `_exec_passthrough` |
| 参与拍平 | 是（`CHAIN_DETAIL_TYPES`） | 是 |
| 历史字段 | `ds` / `table` / `schemasText` / `matchType` / `matchPrefix` / `autoSchema`；`file_sync` 变体用 `filePath`/`fileType`/… | `ds` / `table` / `autoCreate` |
| 替代者 | `endpoint_select`（`baseMode=src_base` / `tgt_base` / `file_sync`） | 同左 |

**为什么保留**：历史 `graph_json` 与已物化的运行态图里仍有这两类节点（含 `sys_exec_` 前缀的物化结果）。直接删除会导致老工作流无法运行。

**使用规范**
- **新编排一律用 `endpoint_select`**，不要再产出 `src_select`/`tgt_select`。
- 两者可与 `endpoint_select` **共存于一条链**（都参与拍平），但会互相覆盖同名字段（6.1 的"后写覆盖"），属配置事故。
- 清理计划：待所有历史工作流迁移到 `endpoint_select` 后，Master 侧保留读取兼容一个版本周期再移除。

---

## 7. E 类 · 流式组件（C18~C20 + 看板）

**共同现状（P0 缺口，G-14）**：`stream_input` / `stream_fuse` / `stream_output` / `page_board` 四个 type **既不在 Master 的 handler 字典，也不在 `WORKER_TYPES`**，而 `nodeTypes` 里有完整条目且在 Palette 的"流式处理"组可见。也就是说：**可以在画布上拖出、可以连线、可以保存，但运行必失败**，报 `outputs.error = "executor_not_implemented"`。

它们的正确归属是"**常驻流作业**"，不是"一次性任务"——因此**不应**简单塞进 `WORKER_TYPES`（那会变成跑完就退出的批任务）。目标形态见 9.2。

### 7.1 `stream_input` · 流输入（C18）

| 项 | 内容 |
|---|---|
| 身份 | `type=stream_input` `code=C18` `categories=[stream]`，**无 `runtimeOnly`**（可直接拖出） |
| 前端默认值 | `{ srcType:'kafka', dsRef:'', brokers:'', topic:'', group:'datara-flink', groupOverride:false, startFrom:'earliest', format:'json', delimiter:',', …cdc 字段 }` |
| 前端表单 | 按 `srcType` 分型：kafka（brokers/topic/group/groupOverride/startFrom）/ cdc（I4 源注册）/ http 拉取 / 文件尾随 / 模拟器 / Redis Stream / MQTT |
| 端口 | 匿名 target + 匿名 source |
| 后端 | **无路由（缺口）** |
| 记录格式 | 统一 `{source, ts, data}`（`desc` 明确） |

**前端设计**：`srcType` 是主分型开关，Kafka 侧 5 个字段 + CDC 侧一组。默认值里 `group:'datara-flink'` 是**写死的默认值**——注释已标注这是 I12 T12 的待确认项（G-15）：消费组默认值不应由前端硬编码，应由后端按作业分配。

**后端设计**：目标形态是常驻消费者（Kafka consumer / CDC connector / tail -F / 轮询器），把记录规范化成 `{source, ts, data}` 后投递到流总线。**当前无实现**。

**使用规范**
- 记录 schema 必须在下游（`stream_fuse`）统一，否则 union/join 无法对齐。
- `groupOverride=false` 时消费组由系统分配，避免多个作业互相抢消息。

---

### 7.2 `stream_fuse` · 流融合（C19）

| 项 | 内容 |
|---|---|
| 身份 | `type=stream_fuse` `code=C19` `categories=[stream]` |
| 前端默认值 | `{ fuseType:'union', alignMap:[], joinKeyLeft:'', joinKeyRight:'', joinWindowSec:60, joinType:'inner', filterExpr:'', fieldMap:[], groupKeys:'', aggs:[], windowType:'tumbling', windowSizeSec:60, slideSec:10, watermarkSec:5 }` |
| 前端表单 | `fuseType`（**5 分型**）+ 各型专属字段 + `sessHint` |
| 前端摘要 | 按 `fuseType` 分别显示 join 键/窗口、窗口类型/时长、或类型名 |
| 前端页面 | `page: { title:'流融合与窗口', comp: StreamNodePage, w:620, h:460 }` |
| 后端 | **无路由（缺口）** |

**前端设计：五种融合形态（`fuseType`）**

| fuseType | 专属字段 | 语义 |
|---|---|---|
| `union` | `alignMap`（kv-table，目标列 ← 各来源列，同名自动透传） | 多路归一（**字段对齐**） |
| `join` | `joinKeyLeft`（field-select，**required**，`upstreamIndex:0`）/ `joinKeyRight`（field-select，**required**，`upstreamIndex:1`）/ `joinWindowSec`（缺省 60s）/ `joinType`（`inner` / `left`） | 双流按时间窗 + 键匹配（**流批流**） |
| `filter` | `filterExpr`（textarea，**required**，placeholder `amount > 0 && status == 'paid'`） | 单流过滤 |
| `map` | `fieldMap`（kv-table，目标列 ← 转换表达式，如 `upper(name)`） | 字段转换 |
| `window` | `groupKeys`（枚举/常量，空=全量）/ `aggs`（kv-table，**required**，格式 `字段:函数:输出名`，如 `amount:sum:amt_total`）/ `windowType`（`tumbling`/`sliding`）/ `windowSizeSec` / `slideSec`（仅 sliding）/ `watermarkSec`（乱序容忍） | 窗口聚合（**流批流**） |

- `joinKeyLeft` / `joinKeyRight` 用 `field-select` + `pick:{src:'upstream', upstreamIndex:0/1}`：**左右两侧字段来源由连线顺序决定**，与 `field_map` 的 `fmSrcIndex` 同一套机制。
- `sessHint` 明确说明：window 是"微批 + 窗口聚合 + 水位线"，产出 `win_start`/`win_end` 时间戳列；union 是"字段对齐"，join 是"双流 + 键 + 时间窗匹配（等价于流批流）"；表达式由后端 `simpleeval` 安全求值。
- `joinType` 只有 `inner` / `left`，**没有 `right` / `full`**（缺口 G-16：CDC 场景常需右外连接）。

**后端设计**：目标形态是流算子（对齐 / 窗口 / 过滤 / 投影），由常驻进程消费上游流。`simpleeval` 已在 `vars_render.py` 侧接好，可复用做表达式求值。**当前无实现**。

**使用规范**
- `join` 两侧**必须**各连一条上游，且左右顺序不能反（`upstreamIndex` 0/1）。
- `window` 模式必须设 `watermarkSec`，否则乱序数据会被错误计窗。
- `aggs` 的 `字段:函数:输出名` 三段格式是契约，函数名需后端支持（`sum`/`count`/`avg`/`min`/`max` 等）。
- 表达式里不要写有副作用的调用，`simpleeval` 是白名单沙箱。

---

### 7.3 `stream_output` · 流输出（C20）

| 项 | 内容 |
|---|---|
| 身份 | `type=stream_output` `code=C20` `categories=[stream]` |
| 前端默认值 | `{ outType:'api', keepLast:100, schemaText:'', outDs:'', outTable:'', outFieldMap:[], uniqueKey:'', outBatchSize:500, kafkaBrokers:'', kafkaTopic:'', outPath:'', rollBy:'size', rollSizeMb:10, rollMinutes:60 }` |
| 前端表单 | `outType`（**4 分型**）+ 各型字段 + `apiHint` |
| 前端摘要 | api: `API 输出（Last-N）` / table: `表 x @ ds` / kafka: `Kafka → topic` / file: `文件 → path` |
| 前端页面 | `page: { title:'实时数据', comp: StreamDataPage, w:680, h:460 }` |
| 后端 | **无路由（缺口）** |

**前端设计：四种输出通道（`outType`）**

| outType | 字段 | 说明 |
|---|---|---|
| `api` | `keepLast`（内存 Last-N，缺省 100）/ `schemaText`（`category,amt,cnt` 顺序即列顺序）/ `apiHint` | 经 `GET /api/v1/stream-jobs/{id}/data?mode=poll|sse` 或 `/ws` WebSocket 暴露；鉴权走平台 token |
| `table` | `outDs`（**required**）/ `outTable`（`table-picker`，`writeAs:'table'`——注意**不带 schema**）/ `outFieldMap`（kv-table，空=同名全量）/ `uniqueKey`（**填则 upsert，不填则纯追加不去重**）/ `outBatchSize`（缺省 500，攒批后落库） | 落库需批量写，不要设 1 |
| `kafka` | `kafkaBrokers`（**required**）/ `kafkaTopic`（**required**） | 转发到下游 topic |
| `file` | `outPath`（**required**，相对 `/datara/files`）/ `rollBy`（`size`/`time`）/ `rollSizeMb`（仅 size）/ `rollMinutes`（仅 time） | 滚动切文件 |

- `apiHint` 明确了两个查询端点与鉴权方式，是前端页面化预览（`StreamDataPage`）的数据来源。
- `uniqueKey` 的"填则 upsert / 不填则不去重"是**关键语义**，hint 里已写明，但字段本身无 hint，迁移时需补。

**后端设计**：目标形态是常驻 sink。`api` 通道需要后端提供 `stream-jobs` 的 poll/SSE/WS 端点（**当前缺口**，见 G-14）。**当前无实现**。

**使用规范**
- `table` 通道的 `outTable` 用 `writeAs:'table'`（不带 schema），与 `endpoint_select` 的 `writeAs:'schemaTable'` 不同——**不要混用**。
- 高频写入必须设 `outBatchSize`（≥100），否则逐条 insert 会打爆目标库。
- 需要幂等去重**必须**设 `uniqueKey`（否则重复消费会写重复数据）。
- `file` 通道按 `rollBy` 滚动，长跑任务必须设滚动条件，否则单文件无限增长。

---

### 7.4 `page_board` · 页面看板（无编号）

| 项 | 内容 |
|---|---|
| 身份 | `type=page_board`，**`code` 字段缺失**（无 C 编号），`categories=['stream']`，**无 `runtimeOnly`**（可直接拖出） |
| 前端默认值 | `{ preset:'ecommerce' }` |
| 前端表单 | `preset`（`ecommerce` 电商实时看板 / `iot` IoT 设备监控 / `visit` 站点访问分析 / `custom` 自定义）+ `boardHint` |
| 前端摘要 | preset → 中文名（`custom` → `自定义看板`） |
| 前端页面 | `page: { title:'实时看板', comp: BoardPage, w:820, h:560 }` |
| 后端 | **无路由（缺口）** |

**前端设计**
- 与其他组件不同，本组件**几乎没有配置字段**——它是一个"渲染宿主"，能力由 `BoardPage` 组件的代码决定。
- `boardHint` 说明数据来源：主数据源 = 上游 `stream_output`（`outType='api'` 通道，走 SSE/轮询）；窗口列 `win_start` 提供时间轴。
- `BoardPage`（I11）提供卡片/折线/柱图/饼图/告警/明细六类，字段绑定由页面内配置。
- **形状**：未设 `shape:'device'`，按普通节点渲染。

**后端设计**：**不是任务节点**——它是前端页面宿主，运行时只依赖 `stream_output` 的 api 通道提供数据。**缺口 G-17**：`page_board` 目前在 Master 路由表里查不到，若用户把它当普通节点连进执行链会 `FAILURE`。目标形态是把它标记为"非执行节点"（类似 `runtimeOnly` 但语义相反——不产生任务实例，仅提供页面）。

**使用规范**
- `page_board` **必须**连到一个 `outType='api'` 的 `stream_output` 才有数据。
- 看板的字段绑定写在 `BoardPage` 内部（代码），不在 `graph_json`——因此看板布局**当前不可版本化/不可跨环境迁移**（缺口 G-18，建议把布局抽到 `node.data`）。
- 不要把 `page_board` 接进需要执行的主链。

---

## 8. F 类 · 编排模板（落图即展开，无独立运行时）

三个模板 + 一个示例，**都在 Palette 可见**，但**不进入运行图**——拖出时由 `template.modes[].build(ctx)` 一次性铺开成普通节点。

### 8.1 `src_base_orch` · 源端基准同步（C29）

| 项 | 内容 |
|---|---|
| 身份 | `type=src_base_orch` `code=C29` `categories=[sync]`，`form: []` |
| 模板模式 | 单模式 `src_base`（label「源端基准」） |
| 展开结果（8 节点） | `start` → `sql`（前置准备）→ `endpoint_select(baseMode='src_base')` → `field_map` → `condition_set` → `assert` → `end`；另有 `notify` 挂在 `assert` 的 `failure` 出口 |
| 边细节 | 从 `endpoint_select` 出发的边自动带 `sourceHandle:'sourceRef'`（`dag.ts:166 epPort`）；`assert.success` → `end`（`kind:'branch_true'`, label「通过」）；`assert.failure` → `notify`（`kind:'branch_false'`, label「不通过」） |
| 后端 | 无独立路由（展开后各节点走各自路由） |

**前端设计**
- `form: []`——模板节点本身不可配置，**所有配置在展开出的子节点上**。这是正确的设计（避免两处配置同一件事）。
- 展开后会**主动触发** `onEdgeCreated`（`dag.ts:208`）为每条边，注释明确说明"**不要**手工预填 map/cond 的 `data.inputs`，交给联动机制"——这是"拖边即引用"的一致性保证。
- 模板节点的 `defaults: {}` 无关紧要（展开时用 `chainNode` 的显式数据）。

**模板约定（三个模板共同遵守）**
1. 恒定结构：`start → sql(前置准备) → endpoint_select → field_map(_union) → condition_set → assert → end` + `notify` 挂在 `failure` 出口；
2. 模板差异只有两处：`endpoint_select.baseMode` 与 `field_map` vs `field_map_union`；
3. `assert` 用 `assertChainDefaults()`（**`onFail='warn'`**，与 schema 缺省 `'fail'` 不同——注释明确这是为了让"不通过"走通知而不是直接失败）；
4. `notify` 用 `notifyChainDefaults()`（纯日志通道，不发 webhook）。

**使用规范**
- 建同步工作流**一律从模板起步**，不要手工拼链（手工拼容易漏 `assert` 的 `failure` 出口或 `sourceRef` 端口）。
- 展开后 `sql`（前置准备）默认 `datasource:''`，**必须**先配置数据源与 SQL，否则运行必失败。
- 模板展开是**一次性**的：后续修改不会回灌模板，需要改结构就重新展开。

---

### 8.2 `tgt_base_orch` · 目标端基准同步（C30）

| 项 | 内容 |
|---|---|
| 身份 | `type=tgt_base_orch` `code=C30`，`form: []` |
| 模板模式 | 单模式 `tgt_base` |
| 展开差异 | `endpoint_select(baseMode='tgt_base')` + **`field_map_union`**（多表） |

**使用规范**：多 schema 汇总场景用本模板（而非 C29），因为它会用 `field_map_union` 铺开 `addSchemaFlag` / `srcSchemaField` / `aggOperator` 字段，且 `endpoint_select` 展开 `probe` / `matchType` / `probeResult` 三个探查字段。

---

### 8.3 `file_sync_orch` · 文件同步编排（C31）

| 项 | 内容 |
|---|---|
| 身份 | `type=file_sync_orch` `code=C31`，`form: []` |
| 模板模式 | 单模式 `file_sync` |
| 展开差异 | `endpoint_select(baseMode='file_sync', filePath:'samples/orders_part.csv')` + `field_map` |

**使用规范**：`filePath` 预置了一个示例路径（`samples/orders_part.csv`），**展开后必须改成真实路径**，否则会读到示例文件。

---

### 8.4 `demo_pipeline` · 示例最小工作流（无编号）

| 项 | 内容 |
|---|---|
| 身份 | `type=demo_pipeline`，**`code: ''`（空字符串）**，`categories=['general]`，`form: []` |
| 模板模式 | 单模式 `min`（最小工作流） |
| 展开结果（3 节点） | `start` → `sql`（`{datasource:'', sql:'', pre:'', post:''}`）→ `end`，两条 `flow` 边 |
| 定位 | 教学/占位（F63），**不是生产组件** |

**前端设计**：唯一一个**不含 `assert` / `notify`** 的模板（刻意保持最小）。

**使用规范**：仅用于新用户上手与画布连通性验证。生产工作流请用 `src_base_orch` / `tgt_base_orch` / `file_sync_orch` 或 `stream` 模板。

---

## 9. 缺口清单与改造路线

### 9.1 缺口总表

| 编号 | 缺口 | 影响 | 等级 | 涉及组件 | **状态（2026-09-27）** |
|---|---|---|---|---|---|
| G-01 | 分支无匹配时**不置任何出边 ready**，实例挂起而非失败 | 高 | **P0** | `conditions` `switch` | **[DONE]** `engine.py:_exec_conditions` 无命中 → FAILURE |
| G-02 | `switch` 默认分支用 `expr:'*'`，Master 侧无通配特殊处理，`simpleeval` 语义未验证 | 高 | **P0** | `switch` | **[DONE]** `_decide_branch` 显式识别 `expr=='*'` 为 default |
| G-03 | `fork.parallel` 前后端均不消费（不生成端口、不限制出边） | 中 | **P0** | `fork` | **[DONE]** 删除 `parallel` 字段，摘要改为静态文案 |
| G-04 | `join.policy` 后端支持三值，UI 无表单无法配置 | 中 | P1 | `join` | **[DONE]** 补 `policy` select 表单（all_terminal/all_success/any_success） |
| G-05 | `join` 实际默认 `all_terminal`，UI 摘要写"全部成功才触发"，**语义误导** | 中 | P1 | `join` | **[DONE]** 摘要随 `policy` 动态生成 |
| G-06 | `delay.until` 后端支持 4 种时间格式，UI 无字段 | 低 | P2 | `delay` | **[DONE]** 补 `until` text 字段（4 种格式 placeholder + hint） |
| G-07 | `dependent` 依赖目标不存在时永久 `WAITING_DEPENDENCY` | 高 | **P0** | `dependent` | **[DONE]** `_exec_dependent` 预检 wfCode==0 → 立即 FAILURE |
| G-08 | `loop.maxIterations` 是唯一的硬保护，但 UI 完全不暴露 | 高 | **P0** | `loop` | **[DONE]** 补 `maxIterations` number 字段（默认 100） |
| G-09 | `loop.batchSize` 只影响"是否终止"，不按批切片下发 | 中 | P1 | `loop` | **[DONE]** `_loop_batch_info` 按批切片 + `batchItems/batchIndex/batchTotal` 输出供 body 引用 |
| G-10 | `env`（shell/python）与 `requirements`（python）后端支持，UI 无字段 | 中 | P1 | `shell` `python` | **[DONE]** shell/python 补 `env`（kv 表）；python 补 `requirements`（textarea，格式校验+留痕） |
| G-11 | `notify.trigger` 后端仅记录日志，不驱动差异化投递 | 低 | P2 | `notify` | **[DONE]** `_notify_trigger_matches`：on_success/on_failure/always 按上游状态匹配，不符则跳过 |
| G-12 | `smoke` 在 `WORKER_TYPES` + 有 executor，但**无 `nodeTypes`/Palette 入口** | 中 | P1 | `smoke` | **[DONE]** 补 `smoke` nodeTypes（name/delaySec）+ palette「运维/自检」组 |
| G-13 | `field_map_union.aggOperator` 是下拉选择器但只有 `union_all` 一项 | 低 | P2 | `field_map_union` | **[DONE]** 补 `union_distinct` 选项 |
| G-14 | 4 个流式 type 可拖出/可保存/可运行，**运行必失败**（`executor_not_implemented`） | **严重** | **P0** | `stream_input` `stream_fuse` `stream_output` `page_board` | **[DONE]** 快修（`_exec_stream`）+ 完整方案：`extract_stream_subgraph` 在 `parse_graph` 前提取流子图 + 桥接批节点 → 流节点不进入 Master 任务状态机；scheduler 随批实例注册 stream_job |
| G-15 | `stream_input.group` 默认值硬编码 `'datara-flink'` | 中 | P1 | `stream_input` | **[DONE]** 前端去除硬编码默认值，由后端 `sources.py` 缺省兜底 |
| G-16 | `stream_fuse.joinType` 缺 `right` / `full`（CDC 场景常用） | 低 | P2 | `stream_fuse` | **[DONE]** 补 `right` / `full` 关联类型选项 |
| G-17 | `page_board` 是页面宿主却被当普通节点路由 | 中 | **P0** | `page_board` | **[DONE]** 接 `_exec_passthrough`（快修）；nonExecutable 第三类别已由 G-22 落地 |
| G-18 | `page_board` 布局硬编码在 `BoardPage` 组件内，不可版本化/迁移 | 中 | P1 | `page_board` | **[DONE]** `boardLayout` 抽到 data 层（auto/metrics/trend/full）+ BoardPage 联动渲染 |
| G-19 | 组件注册表至少 **5 处**副本（`nodeTypes` / `palette` / Master handler 字典 / `WORKER_TYPES` / worker `EXECUTORS`），易漂移 | 高 | **P0** | 全局 | **[DONE]** 新建 `components/catalog.py` 单一真源；4 后端文件改 import；5 条 CI 门禁 |
| G-20 | `FieldSchema.type` 是 **24 成员开口联合**，新增字段类型即破坏性变更 | 中 | P1 | 全局 | **[DONE]** 已收敛为 9 基元闭合联合（text/number/bool/select/expr/hint/rows/resource/mapEditor） |
| G-21 | `SaveBody.graph_json` 是裸 `dict`，**无 schema 校验**，脏数据可入库 | 高 | **P0** | 全局 | **[DONE]** R0-R6 + R7/R8/R9/R13 已交付；R12（组件版本存在性：缺 ref 节点对应 type 无 published 版本 → R12 警告留痕）落地；R10 边界明确（仅无条件必填，条件必填留前端 W1） |
| G-22 | `NodeSchema` 无 `inputs` / `singleInstance` / `maxOut` / 逐组件 `validators` / 组件 `version` | 高 | P1 | 全局 | **[DONE]** 补 `nonExecutable`/`inputs`/`singleInstance`/`maxOut`/`validators[]`/`version`；profile 级 schema validators 执行器 |
| G-23 | 总方案文档写"7 条 validators"，实际 `dagProfile.validators` 为 **8 条** | 低 | P2 | 文档 | **[DONE]** 文档已更正为 8（+G-25 新增 1 条 = 9） |
| G-24 | `src_select` / `tgt_select` 无前端条目（历史兼容节点） | 低 | P2 | `src_select` `tgt_select` | **[DONE]** catalog 标记 `_DEPRECATED_TYPES` + `is_deprecated_type()` 门禁；存量兼容保留 |
| G-25 | 无"`end` 不得有出边"validator，`end` 仍渲染出端口 | 中 | **P0** | `end` | **[DONE]** validators 新增 end 出度检查（统一为 maxOut=0 校验） |

### 9.2 P0（必须先做，否则存在挂起/脏数据/必失败路径）

> **2026-09-27 进度**：P0 全部 **[DONE]**（**G-01 / G-02 / G-03 / G-07 / G-08 / G-14 / G-17 / G-19 / G-21 / G-25**）。

1. ~~**G-14 + G-17 · 流式组件落地**~~ **[DONE]**：快修（`_exec_stream` 查活跃 StreamJob + `page_board` 接 `_exec_passthrough`）+ 完整方案落地：
   - `master/dag.py` 新增 `extract_stream_subgraph`：在 `parse_graph` 前识别流子图（stream_input/fuse/output）→ 结构校验（复用 `api.streamjob.extract_stream_spec` 同口径）→ 移除流节点 + 桥接批前驱→批后继边（保持 DAG 连通）→ 返回 `(桥接图, stream_spec)`；
   - `parse_graph` 返回 `(Graph, stream_spec | None)` —— 流节点**不进入 Master 的任务状态机**（无 TaskInstance 行）；
   - `scheduler._cmd_start` 在批实例启动时调用 `register_stream_job` 注册流作业（常驻作业类别，数据面由 worker/stream 承载）；failover 恢复路径不自动拉起流作业（流作业由 API 显式启停）；
   - `page_board` 的 `nonExecutable` 第三类别已由 G-22 落地。
2. ~~**G-08 · 暴露 `loop.maxIterations`**~~ **[DONE]**：已加 `maxIterations` number 字段（默认 100），摘要显示限制。
3. ~~**G-07 · `dependent` 守卫**~~ **[DONE]**：`_exec_dependent` 预检 `wfCode == 0` → 立即 `FAILURE`（`outputs.error='dependency_workflow_not_found'`），不再进入 `WAITING_DEPENDENCY`。
4. ~~**G-01 + G-02 · 分支兜底**~~ **[DONE]**：
   - `_exec_conditions` 无命中且无兜底 → 节点判 `FAILURE`（`outputs.error='conditions_no_match'`）；
   - `_decide_branch` 显式识别 `expr == '*'` 为 default 分支，不交给 `simpleeval`。
5. ~~**G-25 · `end` 出边 validator**~~ **[DONE]**：`dagProfile.validators` 新增"`end` 节点出度必须为 0"检查（`level: 'error'`）。
6. ~~**G-21 · 保存闸门**~~ **[DONE]**：服务端 `graph_rules.py` 已交付 R0-R6 + R7（分支边匹配）/ R8（分支全覆盖）/ R9（直通节点被消费）/ R13（物化锚点）+ **R12**（组件版本存在性：缺 componentRef 的节点，若对应 type 在 `comp_versions` 中无 published 版本 → R12 警告留痕，save 宽松兼容存量未回填文档，publish 路径 R6 升级为 error 拒绝）；R10 边界明确（仅覆盖无条件必填字段，showIf 条件必填依赖函数语义无法 JSON 化，留前端 W1 弹窗/Inspector/保存闸门，不做函数语义复制）。
7. ~~**G-19 · 组件注册单一真源**~~ **[DONE]**：新建 `components/catalog.py` 统一定义 `WORKER_TYPES` / `MASTER_HANDLER_TYPES` / `PASSTHROUGH_TYPES` / `STREAM_TYPES` / `NON_EXECUTABLE_TYPES` / `TEMPLATE_TYPES` / `DISPATCHABLE_EXECUTORS`；4 处后端文件（`engine.py` / `failover.py` / `scheduler.py` / `dag.py`）改为 import；CI 5 条门禁（`test_catalog_consistency.py`）防漂移。
8. ~~**G-03 · `fork.parallel`**~~ **[DONE]**：已删除 `parallel` 字段 + 动态摘要，改为静态文案"并行分发（出边数 = 并行度）"。

### 9.3 P1

> **2026-09-27 进度**：P1 全部 **[DONE]**。

- ~~**G-04 / G-05**~~ **[DONE]**：`join` 已补 `policy` select 表单（`all_terminal` / `all_success` / `any_success`），摘要随实际策略动态生成。
- ~~**G-09**~~ **[DONE]**：`_loop_batch_info` 按 `batchSize` 切片 `collection`，输出 `batchItems` / `batchIndex` / `batchTotal` 供 body 节点引用（`${loop.batchItems}`）。
- ~~**G-10**~~ **[DONE]**：shell/python 补 `env`（kv 表，后端 `build_env` 已消费）；python 补 `requirements`（textarea，格式校验 + 日志留痕）。
- ~~**G-12**~~ **[DONE]**：补 `smoke` nodeTypes（`form: [name, delaySec]`，code=C38）+ palette「运维/自检」组 + PIN_MAP 归入普通。
- ~~**G-15**~~ **[DONE]**：前端去除 `group` 硬编码默认值，由后端 `sources.py` 缺省兜底 `'datara-flink'`。
- ~~**G-18**~~ **[DONE]**：`boardLayout`（auto/metrics/trend/full）抽到 `node.data` 层，BoardPage 按布局模式联动渲染卡片/趋势/分布。
- ~~**G-20**~~ **[DONE]**：`FieldSchema.type` 已收敛为 9 基元闭合联合（text/number/bool/select/expr/hint/rows/resource/mapEditor）。
- ~~**G-22**~~ **[DONE]**：`NodeSchema` 补 `nonExecutable` / `inputs` / `singleInstance` / `maxOut` / `validators[]` / `version`；profile 级 schema validators 执行器已接入；`end` 节点 `maxOut=0` 统一校验。

### 9.4 P2

> **2026-09-27 进度**：P2 全部 **[DONE]**。

- ~~**G-06**~~ **[DONE]**：`delay` 补 `until` text 字段（4 种时间格式 placeholder + hint；后端 `_exec_delay` 已消费）。
- ~~**G-11**~~ **[DONE]**：`_notify_trigger_matches`：`on_success` / `on_failure` / `always` 按上游实际状态匹配；不符则跳过（SUCCESS 不落 worker）。
- ~~**G-13**~~ **[DONE]**：`aggOperator` 补 `union_distinct` 选项（union_all / union_distinct 二值）。
- ~~**G-16**~~ **[DONE]**：`stream_fuse.joinType` 补 `right` / `full`（inner / left / right / full 四值）。
- ~~**G-23**~~ **[DONE]**：总方案文档 validator 数量已更正（7 → 8，+G-25 新增 1 条 = 9）。
- ~~**G-24**~~ **[DONE]**：`components/catalog.py` 标记 `_DEPRECATED_TYPES` + `is_deprecated_type()` 门禁；存量兼容保留在 `PASSTHROUGH_TYPES`。

---

## 10. 逐组件验收清单

新增或修改任一组件时，逐条核对：

**注册与发现**
- [ ] `nodeTypes` 有唯一条目；`code` 与 C 编号台账一致（无编号组件显式写 `code: ''`）
- [ ] `categories` 覆盖目标 Palette 分组；`runtimeOnly` / `nonExecutable` 标注正确
- [ ] `defaults` 是默认值唯一来源；`summary()` 容忍所有字段缺失
- [ ] 若新增 type，已同步登记到组件台账（第 1 节）与 CI 漂移检查

**前端表单**
- [ ] `form[]` 全量声明式，无专用面板
- [ ] 分型字段全部用 `showIf` 联动；`required` 只加在当前分型下真正必填的字段上
- [ ] `table-picker` 的 `writeAs` 与后端期望一致（`schemaTable` vs `table`）
- [ ] 端口：`ports(data)` 或 `outputs` 至少有一项提供；分支型端口 id 与后端 `sourceHandle` 契约一致
- [ ] 拖边即引用能自动回填，且回填结果在 Inspector 中显示为只读"已推导"

**后端派发**
- [ ] type 在 Master handler 字典、`WORKER_TYPES`、或模板 `build` 三者中**恰有一处**归属
- [ ] 显式声明参数模型（Pydantic / 校验函数），非法参数在物化阶段拒绝而非运行期报错
- [ ] `outputs` 的每个 key 都有文档，且与前端 `${outputs.x}` 引用一致
- [ ] 幂等：同 `(instanceId, nodeId, loopIter, attempt)` 重放安全
- [ ] 无匹配/目标缺失/超时三类边界均有明确终态（`FAILURE` 或 `SKIP`），**不得挂起**
- [ ] 错误分类可辨（`outputs.error` 用稳定错误码，不用中文散文）

**使用侧**
- [ ] 典型用法、前置条件、限制、误用已写入组件卡
- [ ] 破坏性操作（`truncate` / `overwrite` / `retention=keep` / DDL）已在卡片中用 ⚠ 标注
- [ ] 新增/变更的字段在本文与 `docs/increments/02-DAG组件清单与定义.md` 中**两处同步**

---

## 11. 相关文档

| 文档 | 作用 |
|---|---|
| `docs/DAG组件化编排规范与Datara适配方案.md` | 通用设计规范、NodeSpec 契约、P0/P1/P2 总体路线 |
| `docs/increments/02-DAG组件清单与定义.md` | 现有 C1~C26 准入/退出/配置表单规范 |
| `docs/同步编排端点合一与设计态分离设计.md` | C32/C33 合一为 C37、设计态/运行态分离、拍平机制设计依据 |
| `datara-backend/docs/increments/D12-同步取证收口.md` | 同步取证与日志规范 |
| `datara-backend/docs/increments/I11-同步任务取证交接单.md` | 取证交接单规范（`page_board` 详情页相关） |

