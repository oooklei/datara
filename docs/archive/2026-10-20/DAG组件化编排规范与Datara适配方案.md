# DAG 组件化流程编排：最佳实践规范与 Datara 适配方案

> 参考实现源码分析：`D:\dolphinscheduler-dev\dolphinscheduler-dev`（DolphinScheduler dev-SNAPSHOT，已从 `process_*` 重命名为 `workflow_*`）、`D:\n8n-master\n8n-master`（n8n 2.36.0）
> 目标项目：`D:\需求\数据治理工具\Datara`（datara-web = Vue3 + Vue Flow + dagre + Element Plus；datara-backend = FastAPI + SQLAlchemy + Redis Streams + ZooKeeper）
> 性质：只读分析 + 方案设计，未修改任何源码文件。
>
> **配套文档**：
> - 逐组件落地册见 [`DAG组件逐项前后端设计与使用规范.md`](./DAG组件逐项前后端设计与使用规范.md)——含 37 个组件的权威路由总表、逐组件前后端设计/实现映射/使用规范，以及 25 条缺口清单（G-01~G-25）与 P0/P1/P2 改造路线。本文回答"应该怎么设计"，那一份回答"每个现有组件长什么样、怎么用、哪里没做完"。
> - **落地补齐件**见 [`DAG组件声明契约与Plan产物设计.md`](./DAG组件声明契约与Plan产物设计.md)——回答"上述设计如何变成可校验的代码"：组件声明契约 CDL（单一真源、27→9 基元收敛、纯数据化）、Plan 编译产物（全局唯一闸门 + `planHash`）、非终态 deadline 状态机、端口/输出/变量声明契约，以及 G-01~G-25 的修法映射与 6 阶段迁移路线。
> - **组件治理**见 [`组件管理与发布治理设计.md`](./组件管理与发布治理设计.md)——回答"组件这个对象本身怎么被管起来"：红线（发布必须绑定真实执行契约 / 声明与 dropPolicy 纯数据；原第三条工作流 `componentRef` 版本冻结已移出红线清单，待治理功能基线化后启用）、`t_component` 三表结构、组件状态机、发布闸门 7 项检查、`design_component`/`publish_component` 权限、dropPolicy DSL，以及 M0（只读目录，已交付）→M1（设计与草稿）→M2（发布治理）→M3（内置组件 CDL 化，**2026-09-28 改道为逐组件基线化即入库**，见 [`组件基线化与逐组件发版设计.md`](./组件基线化与逐组件发版设计.md) 与治理设计 §22）路线。**M0 的实测基线**（`catalogHash=83929cf7c3c5c660`、75 组件、30 个无执行实现）出自本文档 §6。

---

> **修订说明（2026-09-26）**：本文成文早于 2026-09-25「同步编排端点合一与设计态分离」重构（见 [`docs/同步编排端点合一与设计态分离设计.md`](./同步编排端点合一与设计态分离设计.md)，已落地并经 1.9 部署验证）。本次修订：
> - §2 Step6 R2 重写为 upstreamMax 引用数上限；§7.3 表达式求值归属更正；新增 §2.11「端点合一与设计态/运行态分离」、§7.4「配置引用与数据引用分层」；§10.2 差距矩阵 G5/G6/G15 更新；§10.4 改造清单全量标注状态。
> - 旧组件 `src_select`/`tgt_select`/`field_map`/`field_map_union`/`condition_set` 为**只读兼容路径**（`OLD_NODE_TYPES` 兼容旧画布执行，引擎保留完整消费链），不新增、不标注为死代码待删。

## 0. 结论速览（TL;DR）

### 0.1 三条最重要的结论

**① 组件注册必须单源，这是第一优先级。**

| 实现 | 组件清单副本数 | 后果（源码实证） |
|---|---|---|
| DolphinScheduler | **3 处**：SPI jar（`@AutoService(TaskChannelFactory.class)`）＋ `task-type-config.yaml` ＋ UI 的 `TASK_TYPES_MAP` + 独立表单组件 | `useTaskTypeStore.setTaskTypes()` **全仓零调用**（死代码）；`TaskType` 联合类型在 3 个文件重复声明；`SAGEMAKER: userSagemaker` 拼写错误长期存活；`use-switch.ts` 的 watcher 监听 `model.workflowName` 而读取 `model.workflowDefinitionName`，**分支选项永远不刷新** |
| n8n | **1 处**：节点类的 `description` 对象 | 前后端零漂移；加节点**不改前端一行** |
| **Datara** | **6 处**：`src/graph/profiles/dag.ts:nodeTypes` / `worker/executor.py:EXECUTORS` / `master/engine.py:WORKER_TYPES` / `master/scheduler.py:WORKER_TYPES` / `master/failover.py:WORKER_TYPES` / `master/dag.py:WORKER_TYPES` | **已产生 P0 缺陷**：4 个流/展示类型（`stream_input`/`stream_fuse`/`stream_output`/`page_board`）既不在 `engine.py` 的 18 个内联 handler 也不在 11 个 `WORKER_TYPES` → 走 master 引擎必落 `executor_not_implemented` FAILURE |

**② 表单必须「数据驱动 + 类型闭合 + 默认值剥离」。**
DS 是 37 个手写 composable + 700 行 `formatParams/formatModel` if-else；n8n 是 1 个 2400 行 `ParameterInput.vue` `v-else-if` 调度器 × **26 个闭合的** `NodePropertyTypes` 联合。Datara 的 `NodeSchema.form: FieldSchema[]` + 单 `Inspector.vue` **已经是 n8n 型（优于 DS）**，但 `FieldSchema.type` 已膨胀为 **27 个成员**的开口联合，且每个新增选择器变体都要同时扩 `type` 和 `pick` 配置对象（F60 / I4 / I7 / I12 T10-T12 四轮叠加）—— 这正是 n8n 用「一个 `resourceLocator` + `modes`」避免的坑。

**③ 定义用文档、执行用关系表 —— Datara 已选对，不要改。**
DS 三表 + 三 log 表（可跨工作流复用单任务、可按节点索引查询，代价是版本簿记 + 关系表 delete-then-reinsert + 700 行手写序列化）；n8n 纯 JSON 文档（零迁移、零映射，代价是不能按节点查询）。Datara 已选 **`graph_json` 文档（n8n 型定义） + `t_task_instance` 行（DS 型执行）**，这个混合模型对数据治理工具是正确的：设计态要演进（编排组件会持续增加），运行态要可查询（治理场景要审计）。**保持。**

### 0.2 一句话方案

> **用 n8n 的「单一描述符 + 通用渲染器」重构 Datara 的组件契约，用 DolphinScheduler 的「逻辑/物理任务分离 + 事件驱动状态机」夯实执行引擎，把 Datara 已有的「拖边即引用 + 能选择不填空」打造成差异化护城河。**

### 0.3 Datara 已超越两者的地方（不要在重构中弄丢）

| 能力 | 说明 | 位置 |
|---|---|---|
| **拖边即引用** | 拖一条边到 `field_map` 节点，`inputs` 自动填为「直接连入的上游节点 + 端口」 | `formLinkage.ts` |
| **能选择不填空** | 23 类字段中 `table-picker`/`field-select`/`topic-select`/`dir-select`/`runtime-node`/`datasource`/`probe`/`upstream-refs`/`field-map` 全是系统取值选择器 | `Inspector.vue` + `dag.ts` |
| **设计态/运行态分离** | `runtimeOnly` 组件（`sync`/`file_sync`）不在 palette；`materialize_sync_exec()` 幂等物化 | `engine.py:48-105` |
| **边即分支条件** | 5 种 `edgeKinds`（`flow`/`branch`/`branch_true`/`branch_false`/`dep`），条件求值读 `sourceHandle` | `dag.ts:1092-1098`、`master/dag.py:52-58` |
| **显式 SKIP 级联** | 边三态 `ready`/`broken`/`skipped` + `_skip_cascade()`；DS 是「上游失败 → 后继永不满足条件 → 静默卡住」 | `engine.py:451/560` |
| **乐观锁 + 回滚 + 服务端草稿** | `base_version` 乐观锁、`/versions`、`/rollback`、`datara.dag.snap.{docId}` | `graph.ts`、`wf_definition.py` |

---

## 1. 两套参考实现的范式对照

### 1.1 总体架构差异

| 维度 | DolphinScheduler | n8n | Datara 现状 |
|---|---|---|---|
| **定义存储** | 规范化 3 表 + 3 log 表（`t_ds_workflow_definition` / `t_ds_task_definition` / `t_ds_workflow_task_relation` + 各自 `_log`） | 单表 4 个 JSON 列（`nodes` / `connections` / `settings` / `staticData`） | 单表 `graph_json` JSON 列 |
| **图的内存表示** | 关系表行 (`pre_task_code`/`post_task_code`)，**根节点用 `pre_task_code = 0` 哨兵** | `nodes: INode[]` + `connections: IConnections`（源优先双层索引） | `GNode[]` + `GEdge[]` |
| **坐标系** | 独立 `locations` 列（JSON 字符串数组），与定义解耦 | 位置内嵌在每个 node 里 | 位置内嵌在 `GNode` |
| **画布库** | `@antv/x6` 1.34（命令式 Graph + SVG markup） | 自研 Vue Flow 封装 | `@vue-flow/core` 1.48（声明式） |
| **组件形态** | 每类型一个手写 composable → 自定义 JSON 描述符方言 | 一个通用 `ParameterInput.vue` 调度器 | 单 `Inspector.vue` + `FieldSchema[]` |
| **组件清单来源** | 3 处副本 | 1 处（节点类 `description`） | 6 处副本 |
| **逻辑/物理任务分离** | `ILogicTaskChannel` 标记接口，`isLogicTask()` = `instanceof` | 能力存在性（`execute`/`poll`/`trigger`/`webhook`/`supplyData`/`requestDefaults`） | 硬编码 18+11 handler dict |
| **执行引擎** | 事件总线 + 生命周期事件（`TaskStartLifecycleEvent` / `TaskFinishLifecycleEvent`…）+ 状态动作（`AbstractWorkflowStateAction`） | **栈机**：`nodeExecutionStack` 数组 + `shift()` 循环 | 轮询推进：`triggerCandidateTasks` → `_try_activate` |
| **分支条件存储** | **双写**：X6 边 label + `taskParams.conditionResult`（可失步） | 边是唯一真源（IF 节点输出 handle 名 = 分支名） | **双写**：`node.params.branches[]` + 边 `sourceHandle` |
| **命令队列** | `t_ds_command`（**无 state 列**），`(id/idStep) % totalSlot = slot` 分片，`CommandEngine` 单线程轮询 + 线程池扇出，`WorkflowExecutionFactory @Transactional` + **删不掉就抛异常** 实现 exactly-once | 无命令表，直接 `scalingService.addJob` 进内存队列 | `t_command`（**有 `state` 列**），master 2s 轮询 + `LeaderGate` 单主 |
| **流式状态回传** | Netty RPC + `TaskExecutorLifecycleEvent`（内存事件总线，**无持久化消息表**，靠 master failover 重建） | WebSocket push | worker 写 Redis Stream `datara:stream:task_state`，master 消费组 `datara-master` |
| **表达式** | `${key}` 全局参数 + `VarPool` 变量池 + `dealOutParam()` 依赖注入 | `ExpressionString = \`={{${string}}}\`` 字符串约定 + 惰性 `Proxy` + `new Function` 沙箱 + VM 池 `acquireIsolate()` | `master/variables.py`（simpleeval 沙箱 `_safe_eval`）+ `common/vars_render.py`（${var} 渲染 + 日期模板，不含表达式求值）+ `${run.instanceId}` / `${run.loopIter}` 保留名 |
| **版本/发布** | `version` 自增 + `_log` 表全量留档 + `release_state`（`ONLINE ⇒ 前端只读`） | `versionId` + `versionCounter` + `WorkflowHistory` + `activeVersionId` | `base_version` 乐观锁 + `/versions` + `/rollback` |
| **草稿持久化** | **无**（离开页面即丢未保存改动） | `WorkflowHistory` + checksum 乐观并发 | localStorage 快照 + 服务端版本 |

### 1.2 各自的核心优点与代价

#### DolphinScheduler

**优点**
- **插件 SPI 成熟**：`@AutoService(TaskChannelFactory.class)` → `ServiceLoader` → `PrioritySPIFactory`（同名同优先级**硬抛异常**，优先级高的覆盖低的）→ `TaskPluginManager` 静态注册表。第三方任务类型可独立发 jar。
- **逻辑/物理分离干净**：`ILogicTaskChannel` 是标记接口，`AbstractLogicTaskChannel.createTask()` 直接抛 `UnsupportedOperationException` —— 逻辑任务在 master JVM 跑，物理任务派 worker。判定靠 `instanceof` 而非硬编码名单。
- **exactly-once 命令消费**：`WorkflowExecutionFactory` 用 `@Transactional` + 「命令行删不掉就抛异常」实现，配合 `id % totalSlot` 分片避免多 master 重复消费。
- **任务参数插件化反序列化**：`TaskChannel.parseParameters(String taskParams)` 由插件自己决定目标类，无中心化类型注册表。

**代价 / 缺陷（必须避免）**
- **组件清单三处副本**（见 §0.1）。
- **无客户端环检测**：`use-canvas-init.ts` 只有 `allowLoop: false`（自环）+ `allowMulti: false`（重复边），多节点环（A→B→C→A）可以在浏览器里画出来，只能靠后端保存时拒绝。
- **分支条件双写可失步**：实证 bug —— `use-cell-update.ts:98-110` 的 `setNodeEdge(code, preTaskCode)` 调用 `buildEdge(String(task), id)` 只传 2 个参数，`label` 和 `isStream` 走默认值，于是**确认一个 CONDITIONS 节点会把它两条上游边的分支名和 stream 虚线全部抹掉**，直到下次回填才恢复。
- **改上游关系会丢标签**、**双击编辑依赖子组件挂载顺序**（`useTaskEdit.onMounted` 里 `graph.value` 为空则静默不工作）、**90s 硬编码轮询**（`ui-setting.apiTimer: 10000` 存了但没用）、**保存后整页 `location.reload()`**。
- **参数校验全手写**：每个插件的 `XxxParameters.checkParameters()` 返回 `false` 并自己打日志，无声明式校验。

#### n8n

**优点**
- **零前端节点代码**（核心不变式）：前端对每个 `NodePropertyTypes` 成员**恰好一个渲染器**，对每个节点类目（default/agent/sticky/add-nodes）**恰好一个画布渲染器**。节点特有行为只允许存在于 `INodeType` 的执行方法里，所有**表现层都是 `INodeTypeDescription` 里的数据**。
- **表达式是字符串约定而非类型**：`ExpressionString = \`={{${string}}}\``。`ParameterInput.vue:1598` 把表达式分支放在所有类型分支**之前**，所以**任何字段**输入 `=` 都会变成表达式编辑器 —— 零 opt-in 成本。若设计成独立的 `'expression'` 类型，则每个字段都要 opt-in、都要一个配套组件。
- **句柄数也是表达式**：`inputs: '={{ $json.fields.length }}'` 让 Switch 的 N 个输出由同一张通用卡片渲染，无任何 Switch 专属渲染代码。
- **执行引擎是持久化数据上的栈机**：`nodeExecutionStack` 是一个普通数组，分支 / 循环 / 并行 / 等待-恢复全都是这个数据结构的后果而非功能，且因为可序列化，**恢复 = 重新进入循环**。
- **只存非默认值**：`updateNodeParameter` 先 `getNodeParameters(..., toDefaults=false)` 剥离默认值再写盘，写完再 `getNodeParameters(..., toDefaults=true)` 重新应用 —— 升级节点 `default` 不需要工作流迁移。
- **优雅降级**：`requireNodeTypeDescription()` 对未知类型返回合成描述符（`properties: []`），节点能加载、能渲染成「未安装」卡片、不会崩画布。
- **凭据与定义彻底分离**：`INode.credentials` 只存 `{id, name}` 引用，加密体在独立表；描述符只带 `INodeCredentialDescription[]`，前端**永远看不到密文**。
- **结构化 computeds + effect scope**：每节点一个 `effectScope` + `structuralComputed(..., isEqual)`，加一个节点只校验一个节点，删一个只拆一个 scope。

**代价**
- **描述符体积**：`nodes.json` 是很大的静态载荷；新增一个 `NodePropertyTypes` 成员是**破坏性变更**，必须在 `ParameterInput.vue` 加一个分支。抽象的代价集中付在**一个文件一处**，永不付在 per-node 代码上。
- **执行模型是「数据管道」而非「作业」**：栈机 + item 流，进程内 `new Function` 表达式的安全面更大（靠 `isCodeGenerationAllowed()` 探测降级 + `task-runners` 独立进程隔离）。

### 1.3 取舍决策表：抄谁的

| 子问题 | 采纳 | 理由 |
|---|---|---|
| 组件清单 | **n8n（1 处）** | DS 三处副本已实证失控；Datara 六处已出 P0 缺陷 |
| 表单渲染 | **n8n（闭合类型 + 通用调度器）** | Datara 已是此型，只需「闭合」+「收敛 pick 爆炸」 |
| 条件字段显示 | **n8n（`displayOptions`）** | Datara 已有 `showIf` 函数式，同构，保留 |
| 默认值剥离 | **n8n** | 提升 schema 演进韧性，Datara 已有 `defaults` 但未剥离 |
| 未知组件降级 | **n8n（合成描述符）** | 防旧版前端打开新组件的工作流时崩画布 |
| 定义存储 | **n8n（文档）** | Datara 已选；设计态演进快于查询需求 |
| 执行记录 | **DS（行）** | Datara 已选；治理场景必须可按节点审计 |
| 逻辑/物理分离 | **DS（`instanceof` 标记接口）** | 能力检测优于硬编码名单，可扩展 |
| 就绪判定 | **Datara（边三态 + 显式 SKIP 级联）** | DS 的「上游失败 → 后继永不满足条件」是静默卡死，不可观测 |
| 分支条件存储 | **收敛为「边唯一真源」** | 两边都是双写，都出过 bug |
| 等待/输入齐备 | **n8n（`requiredInputs` + 索引级 padding）** | 多输入 Join 需要按索引对齐而非按数量 |
| 表达式 | **n8n（`${}` 已是 Datara 的约定，保留）** | Datara 已有 `${run.instanceId}` 保留名 + `simpleeval` 沙箱，比 `new Function` 安全 |
| 命令队列 | **Datara（有 `state` 列 + `LeaderGate`）** | 简于 DS 的 id-slot 分片；单机/小集群足够 |
| 状态回传 | **Datara（Redis Stream）** | 优于 DS 的「内存事件总线 + failover 重建」；比 WS 简单 |
| 坐标存储 | **n8n（内嵌 node）** | 少一个 `locations` 列，少一处 JSON 解析 |
| 版本/发布 | **两者并集** | Datara 已有乐观锁 + 回滚，**缺发布态（离线/上线）** —— 需补 |

---

## 2. 全链路交互规范

从「用户从 Palette 拖一个组件」到「状态回到画布」的 10 步。每步给出：**前端动作 / 数据结构 / 不变量 / 反例**。

### Step 0 —— 加载与回填（Load）

**前端**
1. 拉取工作流定义文档（`GET /workflow-definitions/{id}` → `graph_json`）。
2. **归一化（normalize）**：丢弃 `type` 缺失的节点；`ensureNodePosition(node.position)` 补默认坐标；丢弃引用不存在节点名的边。
3. **补默认值**：`for (node) resolveNodeParameters(node, descriptorOf(node.type))` —— 逐字段应用 schema `defaults`。
4. **补动态端口**：`ports(node)` 求值 `portsOf(data)`（Datara 已有此模式，`conditions`/`switch` 端口随 `branches` 变化）。
5. **未知组件降级**：`descriptorOf(type)` 找不到 → 返回 `{ form: [], ports: [fallbackIn, fallbackOut], icon: '?' }`，并在画布上打「未知组件」角标 + 阻断保存。
6. 若所有节点均无坐标 → 延迟 1s 触发无头 dagre 布局（DS 模式：`detail/index.tsx` `if (!locations) setTimeout(submit, 1000)`）。
7. `graph.fromJSON(doc)` / 直接喂 Vue Flow `:nodes` `:edges`。

**不变量**
- 归一化是**纯函数、幂等、可单测**的（n8n `useWorkflowNormalization.ts` 只有 25 行；Datara 的 `graph/model/deriveDoc.ts` 是「任务定义→图文档派生」模块而非加载归一化，归一化 2/3/5 三步需在 GraphWorkbench 加载路径落实——未知组件降级已由 `FALLBACK_SCHEMA` 实现，补默认坐标/默认值剥离待补）。
- 加载路径**永不写库**（DS 保存后 `location.reload()` 是反例）。

**反例**：DS 的 `node.removeMarkup(); node.setMarkup(NODE.markup.concat(NODE_STATUS_MARKUP))` —— 每次状态刷新全量重置 markup，所以自动布局（`fromJSON` 重建 cell）之后必须重刷状态。**根因是把「节点结构」和「运行状态」混在同一个 DOM 契约里。** 正确做法：状态作为独立的 overlay 层（Datara 的 `LogPanel`/`IssuePanel` 应承担），或用 `v-if` 局部 patch 而非全量 `setMarkup`。

### Step 1 —— Palette 呈现

**前端**
- Palette 分组来自组件描述符的 `groups`（Datara 已有 7 组 32 项），**不得硬编码**。
- 每项显示：图标 + `label` + `code`（C11）+ `desc` 首句。
- 「置顶/收藏」为本地偏好，不入图文档。

**不变量**：Palette 渲染的集合 === 后端 catalog 中 `runtimeOnly !== true` 的集合。

### Step 2 —— 拖拽开始（DragStart）

**前端**（DS `use-dag-drag-drop.ts:48-54` 是标准写法）
```ts
function onDragStart(e: DragEvent, type: string) {
  if (readonly.value) { e.preventDefault(); return }
  dragged.value = { type, offsetX: e.offsetX, offsetY: e.offsetY }
}
```
- 记录**元素内偏移**（`e.offsetX/offsetY`，相对 Palette 行，不是页面）。
- `readonly` 时**在源头 `preventDefault()`**，不是等到 drop 再 return（DS 两处都做了，源头那道是必要的）。
- n8n 的做法更进一步：拖拽载荷是**完整意图图** `{ nodes: AddedNode[], connections: AddedNodeConnection[] }`，已在拖拽时算好（`NodeItem.vue:168-176` 的 `getAddedNodesAndConnections`），drop 时只做 `jsonParse`。这样「拖一个带自动子节点的复合模板」零成本。

**Datara 建议**：把 `demo_pipeline` / `src_base_orch` / `tgt_base_orch` / `file_sync_orch` 这 4 个模板节点改成 n8n 式**意图图载荷** —— 拖入时一次落下 8~9 个节点和整条链，而不是落 1 个节点再靠用户连线。

### Step 3 —— 落点与坐标计算（Drop）

**坐标数学**（DS `use-dag-drag-drop.ts:57-75`，Datara 直接照抄）
```ts
function onDrop(e: DragEvent) {
  e.stopPropagation(); e.preventDefault()
  if (readonly.value || !dragged.value) return
  const { type, offsetX, offsetY } = dragged.value
  // clientToLocal 是 scroller/pan 启用时的正确逆变换
  const p = toGraphCoords(e)          // Vue Flow: screenToFlowCoordinate({x: e.clientX, y: e.clientY})
  const id = allocateNodeId()         // 后端发号 or 本地 uuid
  addNode({ id, type, position: { x: p.x - offsetX, y: p.y - offsetY } })
}
```
- **`screenToFlowCoordinate` / `clientToLocal` 必须在 drop 时调用**，不能用 DragStart 时的坐标（画布可能已平移）。
- **减掉元素内偏移**，让节点在光标下居中，而不是偏移一个抓取点。
- **网格吸附**：DS **没做**（`grid:{size:10,visible:true}` 只是背景网格，坐标是浮点数，存进 `locations` 的是浮点）—— **这是缺陷**。Datara 已有 dagre 布局，建议：落点坐标 `Math.round(x / 8) * 8`，且**拖动结束时也吸附**。
- **防重叠**：n8n `getNewNodePosition()` 的做法可直接借鉴 —— 候选框与已有节点重叠则按网格步进，直到不重叠，再夹到视口内。

**不变量**
- 节点坐标永远落在 `graph_json`，是**定义的一部分**（n8n 型），不是独立 `locations` 列。
- 坐标只影响呈现，**不影响执行语义**（执行顺序只由边决定）。

### Step 4 —— 节点落库前的合法性闸门（Datara 已有、需强化）

**落点后立即校验，任一 error 拒绝落点：**
1. 组件 `type` 在 catalog 中且 `runtimeOnly !== true`。
2. 同类型节点数 < `maxNodes`（n8n 的 `INodeTypeDescription.maxNodes`；Datara 需为 `page_board`、`assert` 等单例组件加上）。
3. 必填字段可为空 —— 但**必须在 Inspector 打开时可见**（n8n 的做法：先落点、`openDetail: true` 立即打开配置面板，未配置的节点画布上带「未配置」角标）。

**Datara 已有**：`requiredMissing(nodeSchema, data)` 三处共用（画布角标 / 校验面板 / 保存闸门）—— **这个设计是对的，保留**。

### Step 5 —— 打开配置表单（Configure）

**触发源（3 个，语义必须区分）：**

| 触发 | n8n 机制 | Datara 现状 |
|---|---|---|
| 刚拖入，自动打开 | `AddedNode.openDetail = true` → `addNode()` 的 `nextTick` 后 `ndvStore.setActiveNode(name, 'added_new_node')` | Palette 拖入 → 是否自动开 Inspector？需确认 |
| 画布双击节点 | `cell:dblclick` → `editTask(code)` | 已有 |
| 右侧 Inspector 常驻编辑 | 同一份 schema 渲染 | 已有（`Inspector.vue`） |

**表单渲染管线（规范）**
```
FieldSchema[]  ──(showIf 求值)──▶  可见字段
      │
      ├─(defaults 剥离/应用)──▶  绑定值
      ├─(options / probe / pick 异步取数)──▶  选项列表
      └─(validator)──▶  FormRules ──▶  el-form rules
```

**必守的 5 条规范：**
1. **创建与编辑复用同一份 schema。** DS 的 `useShell({from, readonly, data, model})` 用 `!data?.id` 区分新建/编辑（只为「环境名仅新建时自动选」），本质是同一份。**禁止为「编辑态」单独写一套表单。**
2. **`showIf` 必须是纯函数** `(data) => boolean`，不得有副作用/网络请求（网络取数只能在 `probe`/`pick` 声明式字段里）。
3. **条件字段的隐藏必须清理值**（n8n `ParameterInputList` 明确「cleans up hidden params」）。否则「切到模式 B 再切回来」会残留脏参数，运行期行为不可预测。
4. **选项列表必须有 loading / 空态 / 失败态三态。** `probe` 拉表失败时必须显示错误并阻断保存，不能静默空列表让用户以为「表不存在」。
5. **只读态（`readonly`）必须贯穿**到 Palette、画布、右键菜单、表单、边编辑五处，而不是只禁用输入框。

### Step 6 —— 连边与连边校验（Connect）

**DS 的 `validateConnection` 是标准写法，值得抄的部分：**
```ts
connecting: {
  allowMulti: false,   // 禁止同对节点重复边
  allowBlank: false,   // 必须终止在节点上
  allowLoop: false,    // 禁止自环
  allowEdge: false,    // 禁止边连边
  allowPort: false,    // 边挂在节点上而非端口上（Datara 需要挂端口，改为 true）
  validateConnection(data) {
    const { sourceCell, targetCell } = data
    // ① 目标节点该输入端口未占用
    if (occupied(targetCell, handle)) return false
    // ② 源节点该输出端口未超出 maxOut
    if (outDegree(sourceCell) >= spec.maxOut) return false
    // ③ 分支边：sourceHandle 必须命中源节点已声明的 branches
    if (sourceCell.data.branches && !matchBranch(sourceCell, handle)) return false
    return true
  }
}
```

**Datara 必须补的 4 条（当前缺失）：**

| # | 规则 | 后果（不补则） |
|---|---|---|
| **R1 环检测** | `detectCycle` 已有（`dag.ts` validators），但需在**连边时**前置拒绝（DS 完全没有，是它的缺陷） | 用户画出 A→B→C→A，保存才报错，paint-first 后失 |
| **R2 输入端口占用**（2026-09-26 修订） | 普通节点单入边不变；**配置型节点**（字段映射、条件设定等）通过 `inputs[]` 引用多个上游输出，引用数上限由字段级 `pick.upstreamMax` 控制（缺省 1，现有 2/3/5 三档，见 `src/graph/profiles/dag.ts`），执行引擎沿边收集引用配置 | 若不校验 upstreamMax，引用超限时下游配置解析结果不确定 |
| **R3 分支边 ↔ branches 双向一致** | 出边 `sourceHandle ∈ branches[].id`；且**每个 branch 至少一条出边**（或显式标记为「未连」） | DS 的双写失步 bug 在 Datara 的等价形态 |
| **R4 跨类型端口兼容** | `upstream-refs` 类组件要求入边来自 `srcNodeType` 白名单 | 连错线，运行时才炸 |

**R3 的正解（学 DS 的 `postTaskOptions`，同时避免它的双写）**：
> **分支的「条件」真源 = `node.params.branches[]`（含 `id`/`name`/`expr`）；分支的「路由」真源 = 出边集合。**
> 在 `branches` 编辑器里，每个 branch 的目标选择器**只列出「已从本节点连出、且 `sourceHandle === branch.id` 的边所指向的节点」** —— 即**先画边，再在表单里确认标签**。这样两个真源在构造上就不会失步，且用户仍不需要手打节点 id。
> 这是 Datara「拖边即引用」理念在分支场景的自然延伸，**目前 `branches` 字段缺这个约束**（DS 有，Datara 没有）。

### Step 7 —— 自动布局（Layout，可选）

**dagre 配置（Datara 已有 `layout/dagre.ts`，建议对齐 DS 的两个细节）：**
```ts
{
  rankdir: 'TB',        // Datara 默认；DS 用 'LR'
  align: 'UL',
  nodesep: 50, ranksep: 50, padding: 50,
  ranksepFunc(node) {  // DS 亮点：按最宽「出边标签」动态加 ranksep
    return Math.max(50, maxOutgoingEdgeLabelWidth(node) + 20)
  }
}
```
- **入参隔离**：`graph.toJSON()` → 过滤出节点/边 → `layout(...)` → `fromJSON(newModel)`，前后各一次 `cleanSelection()`。
- **布局后必须重算端口与状态**（若状态是 DOM overlay）。
- **布局不改变执行语义**，因此可以随时跑、可撤销。

### Step 8 —— 保存（Save）

**三种存储模型对比**

| 模型 | 形态 | 优点 | 代价 | 采纳 |
|---|---|---|---|---|
| DS 规范化 | 3 表 + 3 log 表，版本自增，关系表 delete-then-reinsert | 跨工作流复用单任务；按节点查；血缘天然 | 版本簿记；3 次批量写；700 行手写序列化；关系表全删全插 | ❌ |
| n8n 文档 | 单表 JSON 列 | 零映射零迁移；加 `INode` 字段免迁移 | 不能按节点查 | ✅ 定义态 |
| **混合（Datara 现状）** | 定义 `graph_json` + 执行 `t_task_instance` | 设计态演进 + 运行态可审计 | 需要显式物化设计态→运行态 | ✅ **保持** |

**保存契约（规范）**
1. **图是拓扑的唯一真源。** DS 的 `onSave` 从图重算 `connects`，`workflowTaskRelationList` 内存副本只用于表单选项 —— 这个方向对，但 DS **两处表示会静默分叉**。Datara 已有 `deriveDoc.ts`，**规范要求：内存中不保留第二份边集合**，所有派生（`fromNode` 剪枝、拓扑序、可达性）都从 `GEdge[]` 现算。
2. **保存前跑全量校验闸门**（DS 只在 save 时靠后端拒绝；Datara 已有前端 `dagProfile.validators` **8 条** + `requiredMissing`，**必须保留且要在服务端复跑一遍** —— 见 §3.3.4）。注意：当前 `SaveBody.graph_json` 是裸 `dict`，**服务端零校验**，这是缺口 G-21（详见逐组件文档 §9.2-P0-6）。
3. **剥离默认值**（n8n 模式）：落盘只存「非默认值」的字段。收益：`sql` 组件新增一个带默认值的参数时，历史工作流零迁移。
4. **乐观锁**：`base_version` 不匹配返回 409 + 当前版本，前端提示「他人已修改」并提供 diff。Datara 已有。
5. **保存 ≠ 发布。** DS 把 `releaseState` 混在 update body 里（`definition/detail/index.tsx:102`），导致「编辑」与「上线」一个动作，且 `ONLINE` 后前端整页只读。**Datara 应拆成两个动作、两个权限**（见 §10）。

### Step 9 —— 运行（Run）

**命令链路（DS 范式 + Datara 现状）**
```
前端 POST /instances            (api/instance.py)
   └─ api/commands.py: submit_command(db, type='START_PROCESS', param, priority)
        └─ INSERT t_command(state='wait', priority, ...)   ← API 不执行，只投递
             └─ master 2s 轮询 consume_commands (master/scheduler.py:67-137)
                  ├─ LeaderGate.check()                       ← 仅 leader
                  ├─ _cmd_start: 建实例 + 逐节点预建任务行 + 起 WorkflowExecuteRunnable
                  └─ COMPLEMENT_DATA → 展开 N 条 START_PROCESS（complementGroup 串行组）
```

**DS 的三条可借鉴机制：**

1. **「预建任务行」**：实例创建时**一次性为每个节点 INSERT 一行 `t_task_instance`**（状态 `SUBMITTED`）。好处：实例详情页立即能看到完整任务清单；状态更新是 UPDATE 而非 INSERT；无需 JOIN。**Datara 已采用（`_cmd_start` 逐节点预建）—— 保持。**

2. **命令 exactly-once**：DS 用 `@Transactional` + 「删不掉 `t_ds_command` 行就抛异常」。Datara 用 `state` 列做软标记（`wait` → 消费中 → 已处理），等价且更简单。**保持 Datara 方案。**

3. **补数展开在 master 而非 API**：DS 的 `COMPLEMENT_DATA` 由 master 展开成 N 条命令，`complementGroup` 串行组阻塞。Datara `_cmd_complement` 已如此。**保持。**

### Step 10 —— 状态回传与观察（Observe）

**三条链路，各有取舍：**

| 链路 | 方案 | 延迟 | 可靠性 | 采纳 |
|---|---|---|---|---|
| worker → master | **Redis Stream**（Datara `datara:stream:task_state`，消费组 `datara-master`，`XAUTOCLAIM` 自愈） | 秒级 | 持久化，可重放 | ✅ Datara |
| master → 前端 | 轮询（DS 90s 硬编码，**缺陷**）| 最差 90s | 无状态 | ❌ |
| master → 前端 | **SSE**（**规划中，现状轮询**——2026-09-26 标注）| 秒级 | 断线自动重连 + 重放 `since_seq` | ✅ 规划 |

**推荐：SSE 端点 `GET /instances/{id}/stream`**（2026-09-26 标注：**规划中，现状轮询**，本段为规划方案），事件 `task_state_changed` / `instance_finished`。前端收到后**只 patch 单个节点的状态**（不触发全图重渲染）。回退策略：SSE 不可用时降级到 3s 轮询（不要 90s）。

**节点状态渲染规范**：状态是 `GNode.data.__runState` 的一个枚举字段（`running`/`success`/`failure`/`skipped`/`waiting`/`retry`），由通用 `DataNode.vue` 读它渲染角标。**不新增状态专用节点组件。**（DS 因为节点是 SVG markup + `foreignObject` 注入 Vue 组件，才被迫做「全量 setMarkup」，是其最大渲染债。Vue Flow 天然是声明式，无此债。）

### 2.11 端点合一与设计态/运行态分离（2026-09-25 已落地，2026-09-26 补记）

本节补记 2026-09-25「同步编排端点合一与设计态分离」重构（见 [`docs/同步编排端点合一与设计态分离设计.md`](./同步编排端点合一与设计态分离设计.md)，已落地并经 1.9 部署验证）。

**① C37 `endpoint_select` 组件（端点合一）**
- `baseMode` 三分拣：`src_base` / `tgt_base` / `file_sync`，一个组件覆盖原 src/tgt 端点选择场景；
- 双具名输出口 `sourceRef` / `targetRef`（passthrough 声明式输出，运行期不产出数据）。

**② probeResult 双形态**
- 前端：逗号分隔文本（`schema.table`）；
- engine：数组 + 文本双兼容解析（读取兜底见 §5.7）。

**③ `runtimeOnly` 组件（`sync`/`file_sync`）**
- palette 不出现；W1 必填校验与保存闸门排除（`requiredMissing` 不检查）——**设计态不落地**，仅运行态物化后存在。

**④ 装载物化 `materialize_sync_exec`**
- 工作流装载时物化 `sys_exec_*` 执行节点；
- md5 确定性 id 保 failover 幂等（重复装载产生同一 id，不重复落库）；
- `assert` 入边改写；多 `endpoint_select` 防御（跳过并告警）。

**⑤ 拖边即引用**
- 连边自动写 `target.data.inputs` 引用 `nodeId:port`（port = `sourceHandle || ''`，具名口为 `sourceRef`/`targetRef`）；
- 程序化建边遵守同一不变量：链构建器统一 `edges.forEach(onEdgeCreated)`；
- 删边三入口（画布删边 / 删节点 / 派生重建）统一收敛。

**⑥ 旧组件兼容**
- `OLD_NODE_TYPES`（`src_select`/`tgt_select`/`field_map`/`field_map_union`/`condition_set`）为**只读兼容路径**，兼容旧画布文档；引擎保留完整执行路径与消费链（`engine.py` 的 src_select/tgt_select 直通条目及 L930-958/L1413-1452 消费链），**不得标注为死代码待删、不得删除**。

---

## 3. 组件（节点）设计规范

### 3.1 唯一真源：组件描述符契约（NodeSpec）

**规范：组件清单、参数 schema、端口、执行路由、图标、分类、默认值，必须来自同一份描述符。**

**前端形态**（`datara-web/src/graph/profiles/types.ts` 需补齐字段）
```ts
export type ExecutorKind = 'master' | 'worker' | 'passthrough' | 'materialize' | 'template'

export interface PortSpec {
  id: string
  label: string
  /** 端口可由表达式/数据动态产生；返回数组即多端口 */
  dynamic?: (data: Record<string, unknown>) => PortSpec[]
  /** 允许的入边源节点类型白名单；空 = 任意 */
  acceptFrom?: string[]
  /** 该端口最大入边数，默认 1 */
  maxIn?: number
}

export interface NodeSchema {
  type: string
  label: string
  code: string                     // C1..C37 组件编号，全局唯一且不复用
  desc: string
  icon: string
  color: string
  groups: string[]                 // palette 分组
  categories: string[]             // 业务分类：general/sync/etl/stream
  /** ★ 关键字段：执行路由，由它派生 master handler 表与 worker EXECUTORS 表 */
  executor: ExecutorKind
  runtimeOnly?: boolean            // 不出现在 palette（sync / file_sync）
  singleInstance?: boolean         // 全图最多一个（assert / page_board）
  inputs: PortSpec[] | ((d: any) => PortSpec[])
  outputs: PortSpec[] | ((d: any) => PortSpec[])
  maxOut?: number                  // 如 conditions/switch = branches.length
  defaults: Record<string, unknown>
  form: FieldSchema[]
  validators?: Validator[]
  summary?: (d: any) => string     // 画布节点副标题
  /** schema 版本；+1 时走默认值剥离 + 迁移钩子 */
  version: number
}
```

**后端镜像**（新增 `datara-backend/components/catalog.py`）
```python
@dataclass(frozen=True)
class ComponentSpec:
    type: str
    label: str
    code: str
    executor: Literal["master", "worker", "passthrough", "materialize"]
    categories: tuple[str, ...]
    runtime_only: bool = False
    single_instance: bool = False
    max_out: int | None = None
    defaults: Mapping[str, Any] = field(default_factory=dict)
    form: tuple[FieldSpec, ...] = ()
    # 执行侧（同一个类上挂，替代 6 处副本）
    master_handler: Callable | None = None      # executor == 'master'
    worker_executor: Callable | None = None    # executor == 'worker'
    params_model: type[BaseModel] | None = None  # pydantic，服务端校验

# 派生（全部由 catalog 计算，不允许手写副本）
WORKER_TYPES  = frozenset(s.type for s in CATALOG if s.executor == "worker")
MASTER_TYPES  = frozenset(s.type for s in CATALOG if s.executor == "master")
EXECUTORS     = {s.type: s.worker_executor for s in CATALOG if s.worker_executor}
MASTER_HANDLERS = {s.type: s.master_handler for s in CATALOG if s.master_handler}
```

**服务端 descriptor 端点**（对齐 n8n 的 `types/nodes.json`，但走 API 以便鉴权与分页）
```
GET /api/v1/components                     → 精简版（palette 用：type/label/icon/groups/categories/executor/runtimeOnly）
GET /api/v1/components/{type}              → 完整版（Inspector 用：form/ports/defaults/validators）
GET /api/v1/components/catalog.digest     → 内容 hash，用于 CI 与前端一致性校验
```

**一致性保障（CI 门禁，双保险）**
1. **代码生成**：`python -m components.codegen --out ../datara-web/src/graph/profiles/generated.ts`，产物**入库**（避免运行时依赖后端）。
2. **CI 校验测试**：
   - `datara-backend/tests/test_catalog_consistency.py`：断言 `WORKER_TYPES`/`MASTER_TYPES`/`EXECUTORS`/`MASTER_HANDLERS` 均由 catalog 推导（静态检查：源码中不得出现硬编码类型名字面量）；断言每个 `executor=='worker'` 的组件都有 `worker_executor`（**这条直接防住 P1 流节点缺陷复发**）。
   - `datara-web/src/graph/profiles/__tests__/generated.test.ts`：断言 `nodeTypes` 的 key 集合与 `generated.ts` 一致。

### 3.2 前端组件规范

#### 3.2.1 字段类型必须是「闭合联合」

**现状问题**：`FieldSchema.type` 已 27 个成员，分 4 轮增量叠加（F60 / I4 / I7 / I12 T10-T12），每加一个「选择器变体」就要同时扩 `type` 和 `pick` 的可选字段：
```
text|number|select|textarea|script|branches
|params-table|kv-table|expr|var-ref|bool|runtime-node
|args-table|datasource|hint|var-table|deps-list|exec-node-tag|probe
|table-picker|field-select|topic-select|dir-select|token-insert|upstream-ref|upstream-refs|field-map
```
后果：`table-picker` / `field-select` / `topic-select` / `dir-select` 本质是**同一个控件的 4 个配置变体**（都是「按某个 params 键去某数据源选东西」），却占了 4 个 `type` + `pick` 里 6 个可选字段的组合爆炸。

**规范（学 n8n 的 `resourceLocator` + `modes`）**：收敛为
```ts
export type FieldKind =
  // 基础输入
  | 'text' | 'textarea' | 'number' | 'bool' | 'select' | 'expr' | 'var-ref' | 'hint'
  // 代码
  | 'script' | 'sql' | 'json'
  // 表格
  | 'kv-table' | 'params-table' | 'field-map' | 'deps-list' | 'args-table' | 'var-table'
  // 资源选择器（统一 + modes + pick）
  | 'resource'
  // 结构化编辑器
  | 'branches' | 'runtime-node' | 'exec-node-tag' | 'upstream-refs' | 'token-insert'
```
```ts
export interface ResourcePick {
  /** 取值来源：数据源表 / 数据源字段 / 运行节点目录 / 运行时节点 / Kafka topic */
  source: 'dsTable' | 'dsColumn' | 'runtimeDir' | 'runtimeNode' | 'kafkaTopic' | 'workflow'
  /** 从 params 的哪个键取上游 datasource 引用 */
  dsKey?: string
  tableKey?: string
  nodeKey?: string
  /** 直传 or {schema, table} */
  writeAs?: 'table' | 'schemaTable'
  /** 直连上游 or 直连指定序号的父节点端口 */
  src?: 'dsTable' | 'upstream'
  upstreamIndex?: number
  multiple?: boolean
  /** 下拉直接插入到另一个 textarea（如 C11 的 token-insert） */
  insertKey?: string
  /** 多选上限，如 field-map 的配对上限 */
  limit?: number
}
```
**收益**：`Inspector.vue` 的控件分发从 27 个 `v-else-if` 降到 ~18 个，其中 5 个变体共用一个 `ResourcePicker.vue` 组件 + `pick.source` 决定内部取数。新增一种「从 X 选 Y」的资源源 = 加一个 `source` 枚举值 + 一段取数函数，**不动分发链**。

**硬规则**：新增 `FieldKind` 成员 = 必须在 `Inspector.vue` 加一个分支 + **必须更新本文件顶部的组件登记表**（`docs` 里的「控件清单」），二者不一致则 CI 失败。这就是 n8n 说的「抽象的代价集中付在一个文件一处」。

#### 3.2.2 条件显示与校验

- `showIf?: (data) => boolean` —— 纯函数，**禁止副作用**。
- 隐藏时**清值**（n8n `ParameterInputList` 明确行为）。
- `validator` 直接产出 `FormRules`，与保存闸门 `requiredMissing` **共用同一批规则**（Datara 已做到 `requiredMissing` 三处共用 —— **保持**）。

#### 3.2.3 画布节点渲染规范

- **单一 `DataNode.vue`** 渲染所有 32 个可拖组件（Datara 已是此型，正确）。
- 节点尺寸由 `calculateNodeSize(config, inPorts.length, outPorts.length)` 计算（n8n），**不得硬编码 220×48**（DS 硬编码 `width:220, height:48`，长任务名只能截断到 18 字符）。
- 状态角标读 `data.__runState`，**不新增状态组件**。
- 未配置节点：右上角「未配置」角标（⚠️），保存闸门拦截。
- 未知组件（catalog 中不存在）：**渲染为带 ⚠️ 的占位卡片**（n8n `requireNodeTypeDescription` 降级），**不崩画布**。

#### 3.2.4 交互细节清单（逐条抄）

| # | 规范 | 来源 |
|---|---|---|
| 1 | 缩放绑 `Ctrl/Meta + 滚轮`，普通滚轮滚页面 | DS `scaling.min/max 0.2~2` + `mousewheel.modifiers` |
| 2 | 网格 `size: 10` 背景 + `snapline` 对齐辅助线 | DS `use-canvas-init.ts:70-73` |
| 3 | 框选/多选/橡皮筋：`selecting{rubberband, rubberEdge, movable, showNodeSelectionBox:false}` | DS |
| 4 | 右键菜单打开时锁滚轮（否则画布跟着滚） | DS `use-node-menu.ts:67-83` `lockScroller()` |
| 5 | 右键菜单项按状态/权限计算 | DS `dag/index.tsx:126-156` |
| 6 | 表单保存后**节点名截断显示但保留全名**（tooltip 显示全名） | DS 临时 tool |
| 7 | 未命名节点取消时**回滚节点本体** | DS `taskCancel` `if (!currTask.value.name) removeNode(...)` |
| 8 | 复制节点时深拷贝定义并分配新 id，**边不复制** | DS `copyTask` |
| 9 | 删除节点时**级联删除所有关联边**（DS `removeTasks` 会做，n8n 靠 store 的 `DELETE` 事件） | Datara 需确认 |

### 3.3 后端组件规范

#### 3.3.1 执行器注册（单源）

> **现状（2026-09-26 核实）：未实现（规划）。** `components/catalog.py` 与 `@register` 装饰器均不存在，执行器注册仍为 `worker/executor.py:EXECUTORS` 裸 dict + master 硬编码名单。

**规范**：
```python
# components/catalog.py —— 唯一注册点
@register(executor="worker")
def sql(ctx: TaskContext) -> TaskResult:
    ...
```
`register` 装饰器把函数挂到 `ComponentSpec.worker_executor`，**并自动断言**：
- `executor='worker'` → 必须提供 `worker_executor`，且 `params_model` 必填（否则 CI 失败）
- `executor='master'` → 必须提供 `master_handler`
- `executor='materialize'` → 必须提供 `materialize_fn`
- 未在 catalog 中注册的 `@register` 类型直接抛错（防止再出现孤儿执行器）

**替代现状**：`worker/executor.py:64-71` 的 `EXECUTORS` 裸 dict + `master/engine.py:598-621` 的 18 项 handler dict + 3 份 `WORKER_TYPES` tuple。

#### 3.3.2 参数模型与校验

**规范（取 DS 的插件化反序列化 + n8n 的声明式校验优点）**
```python
class SqlParams(BaseModel):
    model_config = ConfigDict(extra="forbid")     # 多余字段直接报错，防前端 schema 漂移
    datasource_id: int = Field(gt=0)
    sql: str = Field(min_length=1)
    sql_type: Literal["QUERY", "NON_QUERY"] = "QUERY"
    fetch_size: int = Field(default=10000, ge=1, le=1000000)
    timeout_sec: int = Field(default=600, gt=0)

    @model_validator(mode="after")
    def check_semantics(self):
        if self.sql_type == "NON_QUERY" and self.fetch_size != 10000:
            raise ValueError("非查询语句不接受 fetch_size")
        return self
```
- **入口收敛为一个函数**：`components/validate.py::parse_params(node_type, raw: dict) -> BaseModel`。
  - 服务端保存工作流时调用（**这是 Datara 当前 P2 缺口：服务端零校验**）；
  - worker 构造任务时调用；
  - master 分支求值时调用。
- **三种校验错误分级**：`ValidationError`（用户可修，422） / `SemanticError`（画布契约违例，409） / `RuntimeError`（执行期失败，任务 FAILURE）。
- `extra="forbid"` 是**防 schema 漂移的关键**：前端多传一个字段就立刻暴露，而不是被静默忽略。

#### 3.3.3 组件的四分类与执行路由

| 类别 | `executor` | 执行位置 | Datara 现状组件 |
|---|---|---|---|
| **逻辑控制** | `master` | master JVM/Python 进程内 | `start` `end` `conditions` `switch` `fork` `join` `merge` `delay` `dependent` `loop` `variable` `assert`（12） |
| **物理执行** | `worker` | 派发到 worker | `sql` `shell` `python` `ssh` `procedure` `http` `file` `notify`（8）+ `smoke`（非画布） |
| **直通配置** | `passthrough` | 不执行，仅**向出边声明具名输出** | `endpoint_select` `field_map` `field_map_union` `condition_set`（4） |
| **设计态模板** | `template` / `materialize` | 落点时展开为多节点 / 实例启动时物化 | `demo_pipeline` `src_base_orch` `tgt_base_orch` `file_sync_orch`（4）；`sync` `file_sync`（`runtimeOnly`，物化产生） |

**规范要点**
- **判定靠能力而非名单**（DS 的 `isLogicTask()` = `instanceof ILogicTaskChannel` 值得抄）。Datara 改为：`ComponentSpec.executor` 声明式 + catalog 派生表。
- **`passthrough` 的语义必须显式**：`endpoint_select` 的 `outputs: [{id:'sourceRef'},{id:'targetRef'}]` 是**数据引用声明**，运行期不产出数据，只被下游 `field_map` / `upstream-refs` / `probe` 读取。**这必须写进组件文档并在保存时校验「所有 `passthrough` 节点必须至少有一条下游消费边」**（否则是死配置）。
- **物化的幂等性**：`materialize_sync_exec()` 已实现幂等（检测到 `sys_exec_` 前缀即返回），**补一条 `assert` 存在性依赖的显式校验**（现状 P10：无 `assert` 的同步链不会被物化 → sync 配置无处落地，应在保存闸门直接报 error）。

#### 3.3.4 服务端图校验（Datara P2 缺口的正解）

> **现状（2026-09-27 核实）：已实现，落在 `datara-backend/api/graph_rules.py`（非本节原规划的 `components/graph_rules.py`）。**
> 实施计划 20260926 Task A1 已交付 `validate_graph()`，规则集 R0–R6：R0 结构基础 / R1 环检测（Kahn）/ R2 类型合法性 / R3 无条件必填 / R4 悬挂边 / R5 引用有效性（F4）/ R6 componentRef（D2）。
> 已由 `api/wf_definition.py` 的 save（宽松模式）与 publish（`require_component_ref=True` 严格模式）双路径接入，返回违规清单 `[{rule, nodeId, message}]`。
> 目录快照缺失时 R2/R3 降级并 error 日志，R0/R1/R4 不依赖目录照常执行。
> **与本节原规划的差异**：落地规则编号与口径以实现为准（R0–R6），与下列「与前端 `dag.ts` validators 一一对应」的 7 条设想清单不完全一致；`single_start`/`single_end` 等未纳入服务端规则集，理由见实施计划 R0–R6 口径说明。

**规范：把前端 `dag.ts` 的 7 条 validator 在服务端复刻一份，用同一份规则描述驱动。**

```python
# api/graph_rules.py —— 与 src/graph/profiles/dag.ts 的 validators 一一对应
RULES = [
    Rule("no_cycle",           severity=ERROR,   desc="依赖成环"),
    Rule("edge_target_exists", severity=ERROR,   desc="边引用不存在的节点（断链）"),
    Rule("single_start",       severity=ERROR,   desc="开始节点必须且只能 1 个"),
    Rule("single_end",         severity=WARN,    desc="结束节点至多 1 个"),
    Rule("no_isolated",        severity=WARN,    desc="孤立节点"),
    Rule("no_dup_edge",        severity=WARN,    desc="重复依赖边"),
    Rule("input_port_free",    severity=ERROR,   desc="同一输入端口被多条边占用"),
    Rule("branch_edge_match",  severity=ERROR,   desc="出边 sourceHandle 未命中已声明分支"),
    Rule("branch_all_routed",  severity=WARN,    desc="存在未连出边的分支"),
    Rule("passthrough_consumed", severity=WARN,  desc="直通配置节点无下游消费边"),
    Rule("required_complete",  severity=ERROR,   desc="必填字段缺失（排除 runtimeOnly）"),
    Rule("stream_subgraph",    severity=ERROR,   desc="流子图混编/源汇缺失/游离"),
    Rule("params_valid",       severity=ERROR,   desc="节点参数不满足 params_model"),
    Rule("materialize_anchor", severity=ERROR,   desc="同步链缺对账校验节点，无法物化"),
]
```
- 服务端 `POST /workflow-definitions/{id}/save` 在**事务内**跑全量规则，返回 `422 + [{nodeId, rule, severity, message, fix}]`。
- `fix` 字段给前端 IssuePanel 直接渲染成「点击修复」动作（`docs/数据同步业务问题.txt` 记录的三类告警就属于这类）。
- **前端 `IssuePanel` 应消费服务端的 `rule` 枚举**，而不是各页面各写提示文案 —— 这是 Datara 文档里「契约文案 ↔ 串行拓扑 ↔ 校验口径 ↔ 运行时口径 四者互相脱节」的**根治手段**。

### 3.4 新增一个组件的标准流程（SOP）

```
1. 后端 components/specs/<type>.py
     - 定义 ComponentSpec（含 form 描述、ports、defaults、params_model）
     - 若 executor=worker：同文件 @register 实现执行器
     - 若 executor=master：同文件实现 master_handler
2. 运行 python -m components.codegen  → 更新 datara-web/src/graph/profiles/generated.ts
3. 前端零改动（或仅追加一条「控件用法示例」到 Inspector 控件登记表）
4. CI：pytest test_catalog_consistency.py + vitest generated.test.ts 必须通过
5. 补 docs：组件卡片（准入/退出/配置字段/端口/变量/验收点）
```
**与两套参考实现的差异**：
- vs DS：省掉「改 yaml + 改 `TASK_TYPES_MAP` + 手写一个表单组件」三步。
- vs n8n：多一步 codegen（因为 Datara 前后端跨语言，无法像 n8n 那样一个 TS 类同时供两端）。**用 codegen + digest 校验把「跨语言漂移」变成 CI 可检测的错误。**

### 3.5 组件评审 Checklist（每个组件必过）

**定义层**
- [ ] `code`（C##）唯一且不复用
- [ ] `executor` 与实际执行位置一致
- [ ] `runtimeOnly` / `singleInstance` 声明正确
- [ ] `inputs`/`outputs` 端口 id 稳定（**一旦发布不可改**，是跨节点引用的契约键）
- [ ] `maxOut` 与分支/并行语义一致
- [ ] `defaults` 覆盖全部 `form` 字段（CI 断言：`form` 的每个 `key` 都在 `defaults` 或显式 `required`）

**配置层**
- [ ] 所有用户可填的**枚举/资源/表/字段**都用选择器，不用自由文本（0922 需求硬指标）
- [ ] 选择器有 loading/空/失败三态，失败时阻断保存
- [ ] 敏感字段（口令/密钥）**不入 `graph_json`**，改存引用 id（n8n `Cipher` 模式）
- [ ] `showIf` 隐藏时清值
- [ ] 参数模型 `extra="forbid"`
- [ ] 变量/表达式字段声明可引用的上游输出（`outputs` 元信息）

**运行层**
- [ ] 幂等：重复执行不产生重复副作用（`worker/executor.py` 的 XACK + DB 幂等需推广到全部执行器）
- [ ] 可重试：重试不产生重复副作用
- [ ] 可 kill：收到 `set_kill` 后进程真正终止
- [ ] 日志：结构化输出 + 关键变量脱敏
- [ ] 产出：写入 `outputs` 供下游引用；`outputs` 契约与 schema 一致
- [ ] 超时：内部有超时上限（防 master 的 timeout 扫描成为唯一防线）

**可观测层**
- [ ] 有明确的「成功判据」可被 `assert` 消费
- [ ] 血缘：读表/写表可被 `sqlparser.py` 提取，供 `lineage` 使用
- [ ] 告警：失败时的错误信息可定位（`issue` 面板可读）

---

## 4. 持久化与版本规范

### 4.1 三层存储

| 层 | 内容 | 存哪 | 生命周期 |
|---|---|---|---|
| **定义（草稿）** | `graph_json` 全文 | `t_wf_definition.graph_json` | 手动保存 + 自动草稿 |
| **定义（历史）** | 每次保存的快照 | `t_wf_definition_version`（Datara 已有） | 保留 N 个 |
| **发布态** | `release_state` + `published_version_id` | `t_wf_definition` | Datara **缺，需补** |
| **执行** | 实例 + 任务实例 + 日志索引 | `t_instance` / `t_task_instance` / `t_task_log` | 按保留策略 |

### 4.2 发布态（Datara 必须补，DS 有）

**规范**
- `release_state ∈ {DRAFT, PUBLISHED}` + `published_version_id`。
- **DRAFT 可编辑，PUBLISHED 只读**（DS 的 `readonly = releaseState === 'ONLINE'`，这条值得抄 —— 它把「编辑权」和「运行权」变成互斥状态，避免「正在跑的实例对应定义被改坏」）。
- **运行只能跑 `published_version_id`，不能跑草稿。** 这条比 DS 更严（DS 的 `startWorkflowInstance` 传 `version`，默认取当前 version），但对数据治理是必须的：**跑的就是你审过的那一版**。
- 发布需独立权限位（`workflow:publish`），编辑权限（`workflow:edit`）不足以发布。
- 编辑已发布定义时，**产生新草稿版本，不影响已发布版本**（`version` 与 `release_state` 解耦）。

### 4.3 草稿自动保存（Datara 局部有，需补齐）

- 现状：`datara.dag.snap.{docId}` localStorage 快照 —— 只在单浏览器有效，换设备/换人丢。
- 规范：`PUT /workflow-definitions/{id}/draft`（幂等、不 bump version、`updated_at` 驱动「未保存」提示），前端 debounce 3s + `beforeunload` 兜底。
- **DS 的教训**：无草稿，离开页面即丢（`dag/index.tsx` 只在组件内存里）。不要学。

### 4.4 敏感信息

**规范（n8n 模式）**
- `graph_json` 中**永不出现**明文口令/密钥/Token。
- 节点参数里存 `{ "__ref": "secret://{datasourceId}/password" }`。
- 后端执行时由 `common/dsconn.py` 统一解引用，API 响应中该字段**永不回显**。
- 日志与 `outputs` 中做脱敏（n8n `sensitiveOutputFields`）。

---

## 5. 执行引擎规范

### 5.1 三层架构

```
API 层        只投递命令，不执行（Datara api/commands.py 已正确）
   ↓ t_command(state='wait')
Master        LeaderGate 单主 → 命令消费 → 构建执行图 → 事件推进
   ↓ Redis Stream datara:stream:tasks:{high|normal|low}
Worker        消费 → 幂等执行 → 写 task_state → XACK
```

### 5.2 就绪判定（Datara 优于 DS，保持）

**Datara 现状**（`engine.py:519 _try_activate` + `451 _advance_downstream` + `560 _skip_cascade`）：边三态 `ready` / `broken` / `skipped`。
- 上游成功 → 出边 `ready`
- 上游失败 → 出边 `broken` → 级联 `SKIP`
- 上游被跳过 → 出边 `skipped` → 全 skipped 才跳过后继（对齐 DS 的 `isAllPredecessorsSkipped`）

**保持。** 对比 DS：`isTriggerConditionMet` 要求「所有前驱都 inactive 且未 failed/paused/killed」，上游失败导致后继**永不满足条件**，虽然 `isEndOfTaskChain` 会兜底，但中间过程不可观测。**Datara 的显式 SKIP 是正确选择。**

### 5.3 失败策略（`failPolicy`）

**Datara 现状**：`stop` / `continue`（`engine.py:397 _constraints`）。
**规范**：引入 DS 的 `FailureStrategy` 接口化，并明确 4 种终局：

| 策略 | 语义 | 现状 |
|---|---|---|
| `stop` | 失败即 kill 全实例所有活动任务 | ✅ |
| `continue` | 失败仅断该路径，下游 SKIP | ✅ |
| `continue_downstream` | 失败但**继续跑下游**（如「校验失败也往下走通知」）| ❌ 缺 |
| `end_chain` | 结束本条链，不影响其他并行链 | ❌ 缺 |

并行分支场景下 `stop` 与 `end_chain` 的差别巨大（一个并行分支失败是否拖垮其他分支），必须显式建模。

### 5.4 分支求值（收敛双写）

**规范（关键）**：
```
真源 A（条件）: node.params.branches[] = [{ id, name, expr, default? }]
真源 B（路由）: edges where edge.source === node.id
约束: edge.sourceHandle ∈ { b.id for b in branches }        （合法性，save 时 ERROR）
       每 b ∈ branches 至少一条出边                            （完整性，save 时 WARN）
       无 b.default 时必须有且仅有一条出边未被任何 expr 命中        （兜底，save 时 WARN）
求值: master 取上游 outputs → simpleeval 逐条 eval(b.expr) → 命中集的并集 = 放行边集
       未放行边的下游 → SKIP
```
**当前 Datara 差距**：`master/dag.py:52-58 branch_match` 已经**只从边读条件**（`sourceHandle ∈ {id, name, expr}` 或 `label == name`）—— 这是**好的**，避免了 DS 的双写。但缺少：
1. 保存时对上述三条约束的校验（`branch_edge_match` / `branch_all_routed` / 兜底检查）。
2. `branches` 表单里的「目标选择器」只列出实际出边目标（§3.2 Step6-R3）。

**assert 节点 `onFail` 语义（2026-09-26 补写，预制用例已对齐此语义）**：
- `onFail ≠ 'warn'` 且规则校验不通过 → 节点 **FAILURE**，下游全部跳过（SKIP 级联），`notify` 等下游节点不可达；
- `onFail = 'warn'` → 节点 **SUCCESS**，但 `chosen='failure'` 触发失败分支（供「校验失败也走通知/兜底链」场景）。

### 5.5 并行 Fork / 汇聚 Join

- **Join 策略**（Datara 已有 `all_terminal` / `all_success` / `any_success`）：**保持**。建议补 `all_failure`（对账场景常用）与 `quorum(n)`。
- **补一条 n8n 规则**：多输入 Join 应对齐**输入索引**（`inputs[0]` 来自哪个上游），缺失输入填 `[]` 而不是丢弃，否则下游字段映射会错位。
- **循环**（`loop` + `_loop_exit_gate_ok`）：现状是「仅约束 iter0 出口链，iter>0 体内不受限」。**规范**：循环体首节点必须有一条入边来自循环出口节点，且 `_index` 变量（`${run.loopIter}`）必须可写；**保存时校验「循环体内不含不可重入的 passthrough 物化节点」**。

### 5.6 流式任务与批式任务

**现状风险（P1）**：`stream_input`/`stream_fuse`/`stream_output`/`page_board` 未进任何派发表。
**规范（取 n8n 的「能力存在性」而非 DS 的硬编码名单）**：
```python
# catalog 中声明
ComponentSpec(type="stream_input", executor="worker_stream", ...)
ComponentSpec(type="stream_fuse",   executor="worker_stream", ...)
ComponentSpec(type="page_board",    executor="ui_view", ...)   # 只渲染，不执行

# engine 分派（唯一分支点）
if spec.executor == "master":       spec.master_handler(key, resolved); return
if spec.executor == "worker":       self._dispatch_worker(key, resolved, snapshot); return
if spec.executor == "worker_stream": self._dispatch_stream(key, resolved, snapshot); return
if spec.executor == "passthrough":  return                      # 纯声明
if spec.executor == "ui_view":      return                      # 渲染期组件，运行期忽略
raise CatalogError(f"未声明 executor 的组件：{type}")            # 永不静默 executor_not_implemented
```
- **`ui_view`（`page_board`）是 Datara 独有的组件类别** —— 看板/展示节点，运行期不执行但要在画布/运行态面板上展示聚合结果。建议新增 `t_task_instance.notes` 字段或复用 `outputs` 存聚合快照，master 终结时算一次。
- **`executor_not_implemented` 必须改成启动期失败**：实例创建时就跑 `catalog.resolve_all(node_types)`，任一未声明 → 422 拒绝启动，**而不是跑到该节点才 FAILURE**。这是把 P1 从「运行期故障」提前为「保存期故障」。

### 5.7 同步链读取兜底（现状实现，2026-09-26 补记）

同步执行链在引擎/worker 侧有三层确定性兜底，配置缺失时按次序回落，**不静默失败**：
1. **`_probe_reader_table`**（engine）：`probeResult` 中**唯一表名**优先作为 reader 表；probeResult 为空或多表时回落 `tgtTable`。
2. **`_resolve_schemas`**（engine）：`readerSchemasText` 文本键优先；`autoSchema` 开启时运行时探测并补新增 schema。
3. **readerType 兜底**（`worker` sync.py）：节点未显式声明 `readerType` 时，按 `readerDs` 数据源类型推断兜底。

---

## 6. 状态机规范

### 6.1 任务状态（Datara 9 态，与 `docs/increments/02-DAG组件清单与定义.md` §1.1 逐字一致 —— 保持）

```
SUBMITTED ──► WAITING_DEPENDENCY ──► RUNNING ──► SUCCESS
     │                │                │  │
     │                │                │  ├─► RETRY ──► RUNNING (attempt+1)
     │                │                │  └─► FAILURE
     │                │                │
     └────────────────┴────────────────┴──► SKIP / KILL / FAULT_TOLERANCE
```

**写权分工（现状 `state.py:5-6` docstring 写得很好，保持并文档化）**
| 状态 | 写入方 |
|---|---|
| `submitted` / `retry` / `waiting_dependency` / `skip` / `fault_tolerance` / `kill` | **master 独占** |
| `running` + 全部终态 | worker 上报 → master 落库（worker **不直接写终态**，保证单一写者） |

**规范补充**
1. **非法迁移必须抛错并告警**，不能静默 `UPDATE ... SET state=?`。加 `assert_valid_transition(old, new)` 于唯一的状态写入口。
2. `RETRY` 作为独立状态是 Datara 的选择（DS 用 attempt 字段）。**保持，但必须暴露 `attempt` / `max_attempts` 到 API 与画布**，否则用户看到「retry」不知重试到第几次。
3. `FAULT_TOLERANCE`（容错认领失联任务）是 worker 直接写的例外，**必须在 `worker/state.py` 保留注释说明**（现状已有，好）。
4. **终态集合与活跃集合的判定要单一真源**：`TERMINAL_STATES` / `ACTIVE_STATES` 已在 `state.py` 定义，**任何新代码不得内联字面量**（CI 静态检查）。

### 6.2 实例状态

```
SUBMITTED ──► RUNNING ──► SUCCESS / FAILURE / KILL
                │
                └─ 部分任务 SKIP 但至少一个成功 → SUCCESS（Datara 现状）
```
**规范**：明确「SKIP 不算 FAILURE」并在 API 与 UI 文案上区分「成功（含跳过）」vs「完全成功」，否则治理场景的验收结论会误导。

### 6.3 状态回传（补 SSE）

```
GET /instances/{id}/stream        (text/event-stream)
event: task_state   data: {taskId, state, attempt, outputs?, endTime?}
event: instance_state data: {instanceId, state, endTime?}
event: log_append   data: {taskId, seq, line}      # 增量日志
```
- 每个事件带单调 `seq`，断线重连时 `Last-Event-ID: <seq>` 续传（Redis Stream 的 `XRANGE` 天然支持）。
- 前端 `EventSource` 不可用时降级到 3s 轮询。
- **保留 `sync_logs=true` 的悬空实例检测**（`api/instance.py:64-71`：终态但无 `t_task_log` 索引）—— 这是很好的数据完整性自检，Datara 独有，保持并推广为常态化巡检。

---

## 7. 变量与表达式规范

### 7.1 三级 + 保留名（现状 `docs/increments/02-DAG组件清单与定义.md` §1.2 已定义，保持）

```
节点参数  >  工作流变量  >  环境组变量  >  全局变量
保留名（不可覆盖）: ${run.instanceId}  ${run.loopIter}  ${run.taskId}  ${run.taskCode}  ${run.attempt}  ${run.now}
```

### 7.2 节点间数据引用（Datara 的 `outputs` 机制，需规范化）

**规范**
- 节点的**出参契约**在 `ComponentSpec.outputs[i].schema` 声明：`{ name, type, desc }[]`。
- 运行期值存 `t_task_instance.outputs`（JSON）。
- 下游用 `${upstream.<nodeId>.<port>.<field>}` 引用；`vars_render.py` 负责在**任务下发前**做一次全量渲染（**渲染在 worker，赋值在下发前**——现状 `common/vars_render.py` 已是此分工，保持）。
- **强类型可选**：为 `assert` 组件提供列级对账能力时，`outputs.schema` 必须有 `type`，否则对账只能靠 SQL 重查。

### 7.3 表达式安全（保持 simpleeval，不学 n8n 的 `new Function`）

- **表达式求值归属（2026-09-26 更正）**：`master/variables.py`（四级变量链 + simpleeval 安全求值 `_safe_eval`）与 `worker/stream/ops.py`（流算子侧同款 simpleeval 依赖）。`common/vars_render.py` **不做表达式求值**——它只负责 `${var}` 占位渲染 + `$[日期模板]` 求值（引擎与 IDE 共用的渲染核心）。
- 变量名解析走**白名单前缀**（`run.` / `upstream.` / `wf.` / `env.` / `global.`），非白名单前缀一律解析为空并**在任务日志里 WARN**（不抛错，避免一条坏变量杀死整个任务）。
- **长度/深度上限**：单表达式 ≤ 4KB，嵌套深度 ≤ 8，防 ReDoS 与栈溢出。

### 7.4 配置引用与数据引用分层（2026-09-26 新增）

Datara 存在**两层引用机制，勿混同**：

| 层 | 形态 | 现状 |
|---|---|---|
| **配置引用** | 连边自动写 `inputs[]` 具名引用（`nodeId:port`）+ 执行引擎沿边收集，**保存/执行前解析为字面配置** | ✅ 已实现（§2.11 拖边即引用、§2 Step6-R2 upstreamMax） |
| **数据引用** | 运行期取上游**数据**（§7.2 的 `outputs` 机制，`${upstream.<nodeId>.<port>.<field>}`） | **未来规划**，现状未实现 |

**`sourceHandle` 双语义**（极易踩坑）：
- **分支节点上** = 分支路由键：`branch.id` / `branch.name` / 表达式（或 `label == branch.name` 匹配，见 §7.5）；
- **引用拼接上** = 端口名：具名口为 `sourceRef` / `targetRef`；
- **flow 边的 `sourceHandle` 引擎不消费**（无执行语义）。

### 7.5 分支表达式（`branches[].expr`）

**规范**
- 只允许白名单函数（`len` `contains` `startsWith` `endsWith` `upper` `lower` `int` `float` `coalesce` `isNull` `now` `dateAdd` `in` `between` `matches`）。
- 语法错误 → 该分支判为 `false` + 记 WARN，**不中断整个求值**。
- 未命中任何分支时：有 `default` 分支走 default；无 default 则**全部下游 SKIP + 实例 FAILURE**（明确失败优于静默跳过）。**保存时校验兜底存在性。**

---

## 8. 可观测性规范

| 维度 | 规范 | 现状 |
|---|---|---|
| **任务日志** | 每个任务一份日志文件 + `t_task_log` 索引（`seq`/行数/字节数），支持 `skipLineNum` 增量拉取 + 全量下载 | ✅ `logger/` |
| **变量追踪** | 每次变量渲染记录「哪个变量、来自哪个节点、渲染成什么」（脱敏），存 `t_task_context` | 建议补 |
| **血缘** | `common/sqlparser.py`（SQLGlot）自动提取读写表，落 `t_lineage`；`LineageView.vue` 消费 | ✅ |
| **Issue 面板** | **统一消费服务端 `rule` 枚举**（§3.3.4），每条带 `fix` 动作；画布角标、Issue 面板、保存闸门三处共用同一份校验结果 | 部分（前端 7 条 validator 已有，服务端缺） |
| **画布运行态** | 节点角标状态 + hover 显示「开始/结束/耗时/重试次数/worker」；SSE 驱动 | 部分（需 SSE） |
| **执行报告** | 实例终结时生成一份可下载的执行报告（拓扑图 + 每节点耗时 + 失败原因 + 变量追踪）—— Datara 已有 `i12_execution_report.md` 的雏形，建议产品化为 `GET /instances/{id}/report` | 建议补 |
| **数据完整性巡检** | 常态化扫描：终态无日志索引的实例、孤儿 `t_task_instance`、catalog 未知 type 的 `graph_json` | 部分（`sync_logs=true`） |
| **告警** | `alert/main.py` 已有；建议按 `docs/increments/02-DAG组件清单与定义.md` 的「失败即通知」+ 告警组路由 | ✅ |

---

## 9. 反模式清单（明确禁止）

| # | 反模式 | 出现于 | 后果 | 规范 |
|---|---|---|---|---|
| A1 | 组件清单多处副本 | DS（3 处）、Datara（6 处） | 漂移 → P0 缺陷 | 单一 catalog + codegen + CI digest 校验（§3.1） |
| A2 | 分支条件双写（边 label + params） | DS（已出 bug）、Datara（潜在） | 失步 → 路由错乱 | 条件在 params，路由在边，加双向校验（§5.4） |
| A3 | 无客户端环检测 | DS | 画出环，保存才报错 | 连边时前置 `detectCycle` |
| A4 | 画布拓扑与内存关系表双真源 | DS | 静默分叉 | 只存边集合，其余现算（§2 Step8） |
| A5 | 状态刷新全量重置节点 markup | DS `removeMarkup()+setMarkup()` | 性能债 + 布局后状态丢失 | 状态是数据字段，声明式渲染 |
| A6 | 硬编码节点尺寸/名字截断 | DS `width:220,height:48` + 截断 18 字 | 长名不可读 | 按端口数算尺寸，tooltip 显示全名 |
| A7 | 每类型一个手写表单组件 | DS（37 个） | 组合爆炸，无法批量改 | 闭合类型 + 通用调度器（§3.2.1） |
| A8 | 手写 if-else 参数序列化 | DS `formatParams` 700 行 | 加字段必改 3 处 | pydantic model 单一序列化（§3.3.2） |
| A9 | 「执行器未实现」在运行期才失败 | Datara P1 | 跑到一半炸 | 启动期全量 `resolve_all`，失败即拒（§5.6） |
| A10 | 明文密钥进 `graph_json` | 两家都需注意 | 泄漏 | 引用式 + 脱敏（§4.4） |
| A11 | 保存 ≠ 发布，发布态与编辑态混在一个动作 | DS | 已发布定义被改坏 | 双动作双权限，运行只跑已发布版（§4.2） |
| A12 | 90s 硬编码轮询 / 存了配置不用 | DS `apiTimer:10000` 未用 | 状态感知延迟 90s | SSE + 3s 轮询兜底（§6.3） |
| A13 | 保存/执行后 `location.reload()` | DS（2 处） | 丢客户端状态，闪烁 | 局部 patch |
| A14 | 选择器失败时静默空列表 | 通用 | 用户误以为「资源不存在」 | loading/空/失败三态，失败阻断保存 |
| A15 | 隐藏的条件字段不清值 | 通用 | 切模式残留脏参数 | 隐藏即清值 |
| A16 | `executor_not_implemented` / `undefined` 被静默吞掉 | Datara `dag.py:LOGICAL_TYPES` 死常量、`engine.py:606` 死代码 | 维护者误以为已实现 | CI 断言 catalog 完备；死代码清理纳入检查 |

---

## 10. Datara 适配评估

### 10.1 现状成熟度打分

| 子系统 | 成熟度 | 依据 |
|---|---|---|
| 画布交互（拖拽/连边/布局/选择/右键） | ★★★★☆ | Vue Flow 声明式，无 DS 的 markup 债 |
| 组件描述 + 通用表单 | ★★★★☆ | 已是 n8n 型；欠「闭合类型」与「默认值剥离」 |
| 组件清单治理 | ★☆☆☆☆ | **6 处副本，已出 P0** |
| 图校验（前端） | ★★★★☆ | 7 条 validator + `requiredMissing` 三处共用 |
| 图校验（服务端） | ★☆☆☆☆ | `SaveBody.doc: dict`，零契约校验 |
| 执行引擎 | ★★★★☆ | 事件推进 + 边三态 + SKIP 级联 + 重试/超时/失败重跑，优于 DS |
| 状态机 | ★★★★☆ | 9 态 + 写权分工清晰；缺非法迁移断言 |
| 持久化/版本 | ★★★☆☆ | 乐观锁 + 回滚 + 本地草稿；缺发布态与服务端草稿 |
| 状态回传 | ★★☆☆☆ | Redis Stream 落库好，但到前端靠轮询，无 SSE |
| 组件可观测 | ★★★☆☆ | 日志/血缘/告警有；缺变量追踪与执行报告 |
| 自动化测试 | ★☆☆☆☆ | 前端 198 个测试（纯函数为主，`environment:'node'` 无组件测试）；后端仅 2 个流测试，**engine/dag/scheduler 零覆盖** |

### 10.2 差距矩阵

| # | 差距 | 严重度 | 证据 | 目标方案 |
|---|---|---|---|---|
| **G1** | 流/展示节点走 master 引擎必失败 | **P0** | `engine.py:598-621`：4 类型不在 handler 也不在 `WORKER_TYPES` | catalog 声明 `executor`，启动期 `resolve_all` 校验（§5.6） |
| **G2** | 组件清单 6 处副本 | **P0** | `dag.ts` / `EXECUTORS` / `engine.py` / `scheduler.py` / `failover.py` / `dag.py` | 单一 catalog + codegen + CI（§3.1） |
| **G3** | 服务端零 DAG 契约校验 | **P0** | `wf_definition.py` `SaveBody.doc: dict` | pydantic `GraphDocument` + 14 条规则（§3.3.4） |
| **G4** | 引擎零自动化测试 | **P1** | `datara-backend/tests/` 仅 2 个流测试 | `master/engine.py` 状态机 + `dag.py` 校验 + `scheduler.py` 命令展开 pytest（§10.3 P1-1） |
| **G5** | 0922 要求的 4 分类 × ~5 场景 md 手册与逐场景日志台账缺失 | **P1（阻塞验收）** | `i12_proofs/` 目录已不存在，原证据失效待重建；现可验证现状：组件 4 分类见 `src/graph/profiles/dag.ts` 注册表与 palette 7 分组代码 | 见 §10.3 P0-4（**这是用户明确要求的交付物，优先于技术重构**） |
| **G6** | 发布态（离线/上线）无消费闭环 | **PARTIAL**（2026-09-26 修订） | `common/models.py:59` 已落库 `release_state`（online/offline，缺省 offline），但无消费闭环；设计态闸门走 `runtimeOnly` 而非发布态 | §4.2（发布流程接入仍待做） |
| **G7** | 无 SSE，状态感知延迟 | P1 | 前端无 stream 订阅 | §6.3 |
| **G8** | 左右面板不可收起（违反 `DAG页面改进和优化任务.txt` e 条） | P1 | `GraphWorkbench.vue` 无折叠开关（`IdeView.vue:52-54` 有同类实现可参照） | 抄 `IdeView` 的 `leftCollapsed` |
| **G9** | 多 `endpoint_select` 同画布不支持物化 | P1 | `engine.py:77-80` warning 跳过 | 物化键改为「以每个 `endpoint_select` 为根的连通子图」，而非全图单例 |
| **G10** | 无 `assert` 的同步链不物化 | P1 | `engine.py:75-76` | 保存闸门 `materialize_anchor` 规则直接报 error |
| **G11** | 默认值未剥离，schema 演进无韧性 | P2 | `dag.ts` 有 `defaults` 但保存全量 | 落盘剥离默认值（n8n 模式） |
| **G12** | `FieldKind` 27 成员开口联合 + `pick` 组合爆炸 | P2 | `types.ts:9-40` 四轮叠加 | 收敛为 `resource` + `modes`（§3.2.1） |
| **G13** | `branches` 表单未约束目标来自实际出边 | P2 | `dag.ts:269-291` | 抄 DS `postTaskOptions`（§2 Step6-R3） |
| **G14** | 死代码/死常量 | P2 | `dag.py:12-14 LOGICAL_TYPES`（无引用、缺 7 类型）待清理；`engine.py:606 src_select/tgt_select` **非死代码**——`OLD_NODE_TYPES` 旧画布兼容执行路径，引擎保留完整消费链（2026-09-26 修订：不得删） | 清理 `LOGICAL_TYPES` + CI 防复发；旧组件仅清理前端 palette 残留（已完成） |
| **G15** | Palette 分组与置顶 | **已落地**（2026-09-26 修订） | palette 现为 7 分组 + 置顶（本地偏好），原「Tab 由 5 收敛为 2」问题不再存在 | 已解决；如需恢复 5 Tab（同步/ETL/流/普通/Palette）属产品决策，分类目录树可保留在工作流 Tab 内 |
| **G16** | 无组件挂载测试 | P2 | `vitest.config.ts` `environment:'node'` | 加 `jsdom`/`happy-dom` + `GraphWorkbench` 挂载测试（连边/落点/保存闸门） |
| **G17** | 敏感信息是否入 `graph_json` 未验证 | P2 | 待核查 SSH/数据源口令字段 | §4.4 引用式 |
| **G18** | 循环 `_index` 语义与物化互斥未校验 | P2 | `engine.py:504 _loop_exit_gate_ok` | 保存时校验「循环体内无 materializable 组件」 |

### 10.3 路线图

#### 阶段 P0 — 止血（1~2 周，不动架构，先把 P0 缺陷和阻塞验收的交付物补上）

| 任务 | 产出 | 验收 |
|---|---|---|
| **P0-1 修 G1** | `engine.py` 分派表补 `stream_*`/`page_board`；新增 `executor='ui_view'` 类别；`_cmd_start` 启动期做 `resolve_all` 前置校验，缺声明 → 422 拒绝启动 | 4 个流组件的 DAG 实例能 `START_PROCESS` 成功；未声明 executor 的节点在**启动前**被拒 |
| **P0-2 建 G2 骨架** | 新建 `components/catalog.py`；`WORKER_TYPES` 3 副本 + `dag.py` 副本全部改为 `from components.catalog import WORKER_TYPES`；写 `test_catalog_consistency.py` | `grep -rn '"stream_input"' datara-backend/master/` 返回 0 行；CI 红灯即失败 |
| **P0-3 补 G3 服务端校验** | ~~`components/graph_rules.py` 14 条规则~~ → **已交付**（`api/graph_rules.py` R0–R6，2026-09-27）；~~`api/wf_definition.py` 改用 `GraphDocument` pydantic 模型~~ → **未采纳**（保留 `dict`，运行时校验） | ✅ 已达成：save/publish 返回违规清单 `[{rule, nodeId, message}]`；~~`extra="forbid"`~~ 未做 |
| **P0-4 补 G5 交付物** | 4 分类 × ~5 场景 = **20 篇操作手册 md**（意图/业务意义/操作步骤/每节点配置参数/注意事项/验收标准/验收方法/运行要求/日志位置）+ 逐场景日志取证台账 | 每篇可被第三方独立复现；`docs/use-cases/` 建索引 |
| **P0-5 补 G4 最小集** | `tests/test_engine_transitions.py`（状态机全迁移 + 非法迁移抛错）、`tests/test_dag_rules.py`（14 条规则各 1 用例）、`tests/test_scheduler_commands.py`（6 种命令展开 + 补数串行组） | pytest 通过；覆盖率：`engine.py` 行覆盖 ≥ 60% |

> **P0-4 与技术重构无依赖关系，可并行，且它是 0922 文档的硬性交付物。优先级不低于代码重构。**

#### 阶段 P1 — 组件契约单源化（3~4 周）

| 任务 | 产出 |
|---|---|
| **P1-1 catalog 完整化** | 32+4 个组件全部 `ComponentSpec` 化；`@register` 装饰器 + 完备性断言；codegen 产出 `generated.ts`；`vitest generated.test.ts` + `pytest digest` 双校验 |
| **P1-2 params 模型** | 每个 worker/master 组件一个 pydantic `params_model`（`extra="forbid"`）；`parse_params()` 单一入口；`worker/executors/*.py` 内的手写 dict 读取改为模型访问 |
| **P1-3 物化修正（G9/G10）** | 物化单位从「全图单例」改为「以每个 `endpoint_select` 为根的连通子图」；保存闸门加 `materialize_anchor` |
| **P1-4 契约文档回写（G14/M4）** | `docs/increments/02-DAG组件清单与定义.md` 回写至 C1~C37 现状；删除 `LOGICAL_TYPES` 死常量（`src_select/tgt_select` 为旧画布兼容执行路径，**保留不删**，仅清理前端 palette 残留——已完成） |
| **P1-5 发布态（G6）** | `release_state` + `published_version_id` + `workflow:publish` 权限；运行只跑已发布版；DAG 页 ONLINE 只读（抄 DS） |
| **P1-6 SSE（G7）** | `GET /instances/{id}/stream`；前端 `EventSource` + 降级轮询；节点状态局部 patch |
| **P1-7 面板折叠（G8）** | 抄 `IdeView.vue` 的 `leftCollapsed`，Palette/Inspector 可收起 |
| **P1-8 Palette Tab（G15）** | （2026-09-26 修订：G15 已由「7 分组 + 置顶」落地，本项转为产品决策项——如需恢复 5 Tab 再执行，分类目录树保留在工作流 Tab） |

#### 阶段 P2 — 表单与交互收敛（3~4 周）

| 任务 | 产出 |
|---|---|
| **P2-1 `FieldKind` 收敛（G12）** | 27 成员开口联合 → 闭合联合；5 个 pick 变体合并为 `resource` + `ResourcePick.modes`；`Inspector.vue` 分发链同步精简；控件登记表更新 |
| **P2-2 默认值剥离（G11）** | 保存路径剥离默认值；`version` 字段 + 迁移钩子；新增参数免迁移验证用例 |
| **P2-3 分支一致性（G13）** | `branches` 目标选择器只列出实际出边目标；`branch_edge_match` / `branch_all_routed` / 兜底校验 |
| **P2-4 未知组件降级** | `derivedDoc` 对 catalog 缺失 type 返回合成描述符 + ⚠️ 占位卡片；旧前端打开新工作流不崩 |
| **P2-5 组件挂载测试（G16）** | vitest 换 `jsdom`；`GraphWorkbench` 连边/落点/保存闸门/未配置角标用例 |
| **P2-6 变量追踪与执行报告（G17/可观测）** | `t_task_context` 变量追踪表；`GET /instances/{id}/report` |
| **P2-7 高级语义** | `failPolicy` 补 `continue_downstream`/`end_chain`；Join 补 `all_failure`/`quorum`；循环体可重入校验（G18） |

### 10.4 代码级改造清单（可直接派工）

| 文件 | 动作 | 阶段 |
|---|---|---|
| `datara-backend/components/catalog.py` | **[TODO]** **新建**：`ComponentSpec` / `CATALOG` / 派生表 / `resolve_all` | P0-2 → P1-1 |
| `datara-backend/components/codegen.py` | **[TODO]** **新建**：`catalog` → `generated.ts` | P1-1 |
| `datara-backend/api/graph_rules.py` | **[DONE]** 已交付（原规划路径 `components/graph_rules.py` 未采用）：`validate_graph()` R0–R6，save/publish 双模式接入 | P0-3 |
| `datara-backend/components/validate.py` | **[TODO]** **新建**：`parse_params()` 单一入口 + 三级错误 | P1-2 |
| `datara-backend/worker/executor.py` | **[TODO]** `@register` 装饰器接入 catalog；`EXECUTORS` 改为派生 | P0-2 → P1-1 |
| `datara-backend/worker/executors/*.py`（11 个） | **[TODO]** 改用 `params_model`；`@register(executor="worker", params_model=XxxParams)` | P1-2 |
| `datara-backend/master/dag.py` | **[PARTIAL]** ~~`LOGICAL_TYPES` 删除~~（**已完成**：全仓已无 `LOGICAL_TYPES`）；`WORKER_TYPES` 改导入未做；服务端规则集已由 `api/graph_rules.py` R0–R6 承担，不在本文件 | P0-2 / P0-3 |
| `datara-backend/master/engine.py` | **[PARTIAL]** ~~P0 三项 G1/G2/G3 均未动：流节点分派表 `engine.py:598-621` 未修~~ → **G1 已修（2026-09-27 核实）**：`stream_input/stream_fuse/stream_output` 接入 `engine.py:628-630` 内联 handler dict → `_exec_stream()`（批引擎只做编排面状态占位，数据面由常驻流任务承载，见 I8 裁定②），不再落 `executor_not_implemented`。**注意机制与原规划不同**：未纳入 `WORKER_TYPES`（`dag.py:13`/`engine.py:37`/`failover.py:22`/`scheduler.py:35` 四处定义均不含流三类型），因 `_exec_stream` 同步收口不驻留 RUNNING，`engine.py:451` 超时看门狗与 `engine.py:1789` resume 循环、`failover.py:97`「逻辑节点」语义均自洽。G2/G3 未动：18 项 handler dict 改 catalog 派生未做；`WORKER_TYPES` 改导入未做；~~删 `src_select/tgt_select`~~（2026-09-26 修订：**保留旧画布兼容执行路径不删**，仅清理前端 palette 残留——已完成） | P0-1 / P0-2 / P1-3 |
| `datara-backend/master/scheduler.py` / `failover.py` | **[TODO]** `WORKER_TYPES` 改导入 | P0-2 |
| `datara-backend/master/materialize.py` | **[PARTIAL]** **新建**：从 `engine.py` 抽出 `materialize_sync_exec` 供 catalog 与规则引用——本体已实现且超文档预期（含 md5 确定性 id 幂等、assert 入边改写，见 §2.11④），抽出独立模块、连通子图校验、`materialize_anchor` 未做 | P1-3 |
| `datara-backend/api/wf_definition.py` | **[DONE]** ~~`SaveBody.doc: dict` → `GraphDocument` 未做~~（保留 `dict`，改由 `api/graph_rules.py` 运行时校验）；~~`release_state` 发布流程未接~~ → **已接**（2026-09-27 核实）：`POST /{wf}/publish` 严格模式（`require_component_ref=True`）与 `POST /{wf}/offline` 已落，save 走宽松模式；save/publish 均调 `validate_graph()` | P0-3 / P1-5 |
| `datara-backend/api/instance.py` | **[DONE]** ~~`[TODO]` 加 `GET /{id}/stream`（SSE）~~ → **已实现**（2026-09-27 核实） | P1-6 |
| `datara-backend/api/component.py` + `api/component_design.py` | **[DONE]** ~~`api/components.py` 新建~~ → 实际拆为两个文件（2026-09-27 核实）：`api/component.py` 只读目录（`/components`、`/stats`、`/catalog`、`/{type}`，M0）；`api/component_design.py` 治理写路径（草稿/冻结/发布/下线/回滚/影响面，B1–B5 + D1–D3）。~~`/catalog.digest`~~ 未单设端点，digest 在 `/catalog` 与 `common/dag_catalog.json` 内 | P1-1 |
| `datara-backend/common/models.py` | **[PARTIAL]**（`release_state` 已落库 ✅ `models.py:59`；`published_version_id` / `t_task_instance.notes` 未做）`t_wf_definition` 加 `release_state` / `published_version_id`；`t_task_instance` 加 `notes` | P1-5 / P2-6 |
| `datara-backend/tests/test_catalog_consistency.py` | **[TODO]** **新建** | P0-2 |
| `datara-backend/tests/test_dag_rules.py` / `test_engine_transitions.py` / `test_scheduler_commands.py` | **[TODO]** **新建** | P0-5 |
| `datara-web/src/graph/profiles/generated.ts` | **[TODO]** **新建**（codegen 产物，入库） | P1-1 |
| `datara-web/src/graph/profiles/types.ts` | **[TODO]** `FieldKind` 收敛为闭合联合；`ResourcePick` 合并；`NodeSchema` 补 `executor`/`singleInstance`/`maxOut`/`version`；新增 `PortSpec` | P2-1 / P1-1 |
| `datara-web/src/graph/profiles/dag.ts` | **[TODO]** 改为「re-export generated + 人工补充 `summary`/图标/中文 label」；删除 `WORKER_TYPES` 镜像概念 | P1-1 |
| `datara-web/src/graph/workbench/Inspector.vue` | **[TODO]** 分发链按新 `FieldKind` 精简；新增 `ResourcePicker.vue` 统一 5 变体 | P2-1 |
| `datara-web/src/graph/workbench/GraphWorkbench.vue` | **[PARTIAL]**（环检测前置已做 ✅；`leftCollapsed`/`rightCollapsed`、SSE 订阅未做）加折叠开关；加 SSE 订阅；加环检测前置 | P1-6 / P1-7 |
| `datara-web/src/graph/workbench/GraphWorkbench.vue`（加载路径） | **[TODO]**（未知组件降级已由 `FALLBACK_SCHEMA` 实现，其余两步未做）补「归一化 3 步」（补默认坐标 / 剥离-应用默认值 / 未知组件降级）；注意 `graph/model/deriveDoc.ts` 是「任务定义→图文档派生」模块，不承担加载归一化，勿在此实现 | P2-2 / P2-4 |
| `datara-web/src/services/graphApi.ts` | **[TODO]** 加 `saveDraft` / `publish` / `components` / `stream` | P1-1 / P1-5 / P1-6 |
| `datara-web/vitest.config.ts` | **[TODO]** 加 `jsdom` 环境项目（组件测试） | P2-5 |
| `datara-web/src/graph/workbench/Palette.vue` | **[TODO→产品决策]**（2026-09-26：G15 已由 7 分组 + 置顶落地）恢复 5 Tab | P1-8 |
| `docs/increments/02-DAG组件清单与定义.md` | **[TODO]** 回写至 C1~C37 现状 | P1-4 |
| `docs/use-cases/` | **[TODO]** **新建**：20 篇场景手册 + 索引 | P0-4 |

> 状态标记为 2026-09-26 全量复核结果：**[DONE]** 已完成、**[PARTIAL]** 部分完成、**[TODO]** 未动工。

### 10.5 风险与「不做的事」

**风险**

| 风险 | 影响 | 缓解 |
|---|---|---|
| codegen 引入构建耦合 | 后端 Python 变更需重新生成 TS | 产物入库 + CI 校验 digest；前端构建不依赖 Python |
| catalog 大重构一次性风险高 | P1-1 改动面覆盖全部 36 个组件 | 分三步：① 只做派生表替换（不动结构）→ ② 加 codegen（生成全集但前端仍以 dag.ts 为准，双跑对比）→ ③ 切换为 generated.ts 为准 |
| `FieldKind` 收敛影响 32 个组件表单 | 回归面大 | 收敛时提供旧→新映射表 + 一次性适配脚本；每收敛一类跑一次全组件表单快照测试 |
| 服务端校验会让存量非法工作流无法保存 | 用户被阻塞 | 规则分级：新增 ERROR 规则先跑「只读体检」`GET /workflow-definitions/{id}/diagnose`，存量问题给报告不阻塞；新保存才拦截 |
| SSE 在多实例部署下需 sticky 或共享通道 | 状态丢失 | 事件源落 Redis Stream（已有），SSE 只做读转发，天然支持多实例 |
| 20 篇场景手册工作量被低估 | 验收延期 | P0-4 与技术重构并行；用 `tools/i12_*_usecases.py` 已有种子脚本自动生成骨架，人工只填「意图/意义/注意事项/验收」 |

**明确不做（避免范围蔓延）**

1. **不改成 DS 的三表规范化存储** —— 定义态文档模型更适合组件持续演进。
2. **不引入 `new Function` 类表达式引擎** —— `simpleeval` 沙箱 + 白名单足够，且更安全。
3. **不做 n8n 式的 item 级数据管道**（`$json` 逐条流）—— Datara 是**作业编排**（SQL/脚本/同步），不是数据管道；节点间传的是「表引用/结果集引用」，不是逐条 item。
4. **不做 n8n 式的独立 task-runner 进程池** —— Datara 的 worker 已经是独立进程 + Redis Stream，隔离性等价。
5. **不追求 n8n 的社区插件市场** —— 治理工具的组件是内部受控资产，`catalog` 单源 + codegen 已足够。
6. ~~**不把 palette 做成拖拽时携带整条链**~~（**已被推翻**，2026-09-26 修订：C29-C31 `template.build` 已实现模板拖入携带整链——拖拽载荷为意图图，drop 时一次落下整条链，见 §2 Step2/§2.11）；P0-4 场景手册交付仍优先于进一步的模板能力扩展。
7. **不引入 Cycle/Gaea 之类的图算法库** —— 环检测/拓扑排序 `dag.ts` 已有且有测试，够用。

---

## 附录 A：DolphinScheduler 关键源码索引

| 主题 | 路径 |
|---|---|
| DAG 编辑器（31 文件） | `dolphinscheduler-ui/src/views/projects/workflow/components/dag/` |
| 拖放 + 坐标数学 | `dag/use-dag-drag-drop.ts:48-86` |
| 连边校验（CONDITIONS 限 2 出边） | `dag/use-canvas-init.ts:87-131` |
| 节点/边样式（SVG markup） | `dag/dag-config.ts:140-298` |
| 状态注入（DOM splice） | `dag/use-node-status.ts:46-67` |
| 拓扑映射（`preTaskCode:0` 根哨兵） | `dag/use-business-mapper.ts:34-100` |
| 37 类型注册表 | `ui/src/views/projects/task/components/node/tasks/index.ts:56-94` |
| 任务表单方言 | `ui/src/components/form/types.ts:20-33` + `get-elements-by-json.ts:24` |
| 参数序列化（700 行 if-else） | `ui/src/views/projects/task/components/node/format-data.ts:31-727` |
| 任务定义版本化保存 | `dolphinscheduler-service/.../process/ProcessServiceImpl.java:430` (`saveTaskDefine`) / `:518` (`saveWorkflowDefine`) / `:550` (`saveTaskRelation`) |
| 表 DDL | `dolphinscheduler-dao/src/main/resources/sql/dolphinscheduler_mysql.sql:325/431/486/561/609/902` |
| SPI 发现 + 优先级冲突 | `dolphinscheduler-spi/.../PrioritySPIFactory.java` |
| 任务插件注册表 | `dolphinscheduler-task-api/.../TaskPluginManager.java` |
| 逻辑任务判定（`instanceof`） | `dolphinscheduler-task-api/.../utils/TaskTypeUtils.java` |
| 插件化参数反序列化 | `dolphinscheduler-task-plugin/*/.../XxxTaskChannel.parseParameters()` |
| 定义图构建 | `dolphinscheduler-master/.../engine/graph/WorkflowGraph.java` |
| 运行时就绪判定 | `WorkflowExecutionGraph.isTriggerConditionMet` |
| SKIP 传播 | `WorkflowExecutionGraph.isAllPredecessorsSkipped` + `SuccessorFlowAdjuster.java` |
| 失败策略 | `dolphinscheduler-master/.../workflow/policy/{End,Continue}WorkflowFailureStrategy.java` |
| 命令构造 | `dolphinscheduler-master/.../AbstractWorkflowTrigger.java` + `WorkflowManualTrigger.java:90` |
| 命令消费（exactly-once） | `dolphinscheduler-master/.../engine/command/CommandEngine.java` + `IdSlotBasedCommandFetcher.java` + `WorkflowExecutionFactory.java` |
| 命令分片 SQL | `dolphinscheduler-dao/.../CommandMapper.xml:59` |
| 日志路由（本地优先/远端兜底） | `dolphinscheduler-api/.../logging/LogClientDelegate.java:98-110` |

## 附录 B：n8n 关键源码索引

| 主题 | 路径（v2.36.0：`packages/frontend/editor-ui/`） |
|---|---|
| 字段类型闭合联合（26 成员） | `packages/workflow/src/interfaces.ts:1808-1832` |
| `INodeProperties` 描述符 | `packages/workflow/src/interfaces.ts:2043-2082` |
| `displayOptions` 条件显示 | `packages/workflow/src/interfaces.ts:2008-2025` |
| `INodeTypeDescription`（含动态 `inputs`/`outputs`） | `packages/workflow/src/interfaces.ts:2957-3003` |
| 通用表单调度器（2400 行 `v-else-if`） | `packages/frontend/editor-ui/src/features/ndv/parameters/components/ParameterInput.vue:1526-1620` |
| 表达式分支前置（`=` 约定） | 同上 `:1598` |
| `displayOptions` 表达式两遍解析 | `.../ndv/settings/composables/useNodeSettingsParameters.ts:298-443` |
| 参数写入（默认值剥离/重应用） | 同上 `:71-175` |
| 拖拽载荷 = 意图图 | `.../features/shared/nodeCreator/components/ItemTypes/NodeItem.vue:168-176` |
| drop 侧反序列化 | `.../app/views/NodeView.vue:1628-1644` |
| 节点物化（补默认/版本/webhook） | `.../app/composables/useCanvasOperations.ts:1373-1415` |
| `openDetail` 三种呈现 | 同上 `:1145-1171` |
| 动态句柄数 | `packages/workflow/src/node-helpers.ts:1171-1192` |
| 校验问题分类 | `packages/workflow/src/node-helpers.ts:1256-1313` |
| 归一化 + 未知类型降级 | `.../app/composables/useWorkflowNormalization.ts:26-100` |
| 描述符静态 JSON 预渲染 | `packages/cli/src/services/frontend.service.ts:453-465` |
| 描述符 store（`name→version→descriptor`） | `.../app/stores/nodeTypes.store.ts:128-148` |
| 存储实体（4 个 JSON 列 + 版本） | `packages/@n8n/db/src/entities/workflow-entity.ts:25-114` |
| 执行栈机主循环 | `packages/core/src/execution-engine/workflow-execute.ts:1577-1680` |
| 能力存在性分派 | 同上 `:1302-1440` |
| `ExecuteContext` 绑定（`nodeType.execute.call(context)`） | 同上 `:1041-1124` |
| 输入齐备 + 索引 padding | 同上 `:2400-2477` |
| 等待恢复（栈是数据） | 同上 `:1451-1461` |
| 起始节点能力选择 | `packages/workflow/src/workflow.ts:821-894` |
| 凭据 AES-256 隔离 | `packages/core/src/encryption/cipher.ts:13-30` |
| 声明式节点（无 `execute()`） | `packages/core/src/execution-engine/routing-node.ts:139-142` |
| effect scope 结构化 computeds | `.../app/stores/workflowDocument/useWorkflowDocumentNodesIssues.ts:105-124` |
| 落点网格 + 碰撞避让 | `.../app/utils/nodeViewUtils.ts:210-270` |

## 附录 C：Datara 关键源码索引

| 主题 | 路径 |
|---|---|
| 36 个组件 schema（1190 行） | `datara-web/src/graph/profiles/dag.ts` |
| 字段类型（27 成员开口联合） | `datara-web/src/graph/profiles/types.ts:9-60` |
| 通用 Inspector 表单 | `datara-web/src/graph/workbench/Inspector.vue` |
| Palette（7 组 32 项） | `datara-web/src/graph/workbench/Palette.vue` |
| 画布主体 | `datara-web/src/graph/workbench/GraphWorkbench.vue` |
| 拖边即引用 | `datara-web/src/graph/profiles/formLinkage.ts` |
| 5 种边类型 | `datara-web/src/graph/profiles/dag.ts:1092-1098` |
| 7 条图校验 | `datara-web/src/graph/profiles/dag.ts:1131-1160` |
| dagre 布局 | `datara-web/src/graph/layout/dagre.ts` |
| 文档模型 + topoSort | `datara-web/src/graph/model/index.ts` |
| 乐观锁 + undo/redo | `datara-web/src/stores/graph.ts` |
| 执行器注册（裸 dict） | `datara-backend/worker/executor.py:64-71` |
| 11 个执行器 | `datara-backend/worker/executors/*.py` |
| 编排引擎（1758 行） | `datara-backend/master/engine.py` |
| 分支边匹配 | `datara-backend/master/dag.py:52-58` |
| 4 份 `WORKER_TYPES` | `master/engine.py:37` / `scheduler.py:32` / `failover.py:22` / `dag.py:16-18` |
| 命令消费（6 种） | `datara-backend/master/scheduler.py:67-137` |
| 9 态 + 写权分工 | `datara-backend/master/state.py:5-26` |
| 设计态物化 | `datara-backend/master/engine.py:48-105` |
| 节点分派（缺口现场） | `datara-backend/master/engine.py:598-621` |
| Redis Streams 队列 | `datara-backend/common/queue.py` |
| LeaderGate 单主 | `datara-backend/master/main.py:50-62` |
| API 只投递命令 | `datara-backend/api/commands.py:8-13` |
| 服务端零校验 | `datara-backend/api/wf_definition.py` (`SaveBody.doc: dict`) |
| 悬空实例自检 | `datara-backend/api/instance.py:64-71` |
| 变量渲染 | `datara-backend/common/vars_render.py`（${var} + 日期模板） |
| 表达式求值（simpleeval） | `datara-backend/master/variables.py`（引擎侧）+ `worker/stream/ops.py`（流算子侧） |
| 血缘（SQLGlot） | `datara-backend/common/sqlparser.py` |
| 状态与日志 | `datara-backend/logger/` + `worker/state.py` |
| 用例种子脚本（4 分类） | `datara-backend/tools/i12_*_usecases.py` |
| 组件清单文档（需回写） | `docs/increments/02-DAG组件清单与定义.md` |
| 需求源 | `docs/DAG页面改进和优化任务-0922.txt`、`docs/DAG页面改进和优化任务.txt` |
| 组件/表单需求 | `docs/同步编排端点合一与设计态分离设计.md`、`docs/数据同步业务问题.txt` |
