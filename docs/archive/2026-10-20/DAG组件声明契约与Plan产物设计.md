# DAG 组件声明契约与 Plan 产物设计（P0 架构补齐）

> 状态：设计稿（待评审）· §7.1 阶段 0 的 CI 规则 2 **已落地为可执行脚本**
> 关联：`DAG组件化编排规范与Datara适配方案.md`（通用方案）、`DAG组件逐项前后端设计与使用规范.md`（37 组件逐项卡 + G-01～G-25 缺口）
> 定位：本文件是上述两份文档的**落地补齐件**，只解决 4 个结构性问题，不重复组件清单。
> 已交付代码：`scripts/check_dag_route_completeness.py`（零依赖，路由完备性静态断言，退出码 1 = CI 失败）

---

## 0. 结论摘要

Datara 的**执行内核**设计质量高于多数开源系统（单一真源 `graph_json`、状态单写者、`param`/`param_resolved` 分离、同步链拍平）。短板集中在**设计态的契约层**，四个结构性问题按杠杆排序：

| 优先级 | 问题 | 后果 | 本文对应设计 |
|---|---|---|---|
| **P0-1** | **无 Plan 产物**：配置完整性只靠 3 条 `warn` 级前端校验，然后直接运行 | 存得下、跑崩在半夜；`end` 带出边的图能存能跑、**静默做错事** | §4 Plan |
| **P0-2** | **组件声明不可序列化**：含 5 个函数值字段（`FieldSchema` 3 + `NodeSchema` 2） | 后端**永远无法复用同一份声明**，5 份副本漂移无解 | §3.2 纯数据原则 |
| **P0-3** | **无非终态 deadline**：3 条静默挂起路径 | 编排器最致命的一类 bug | §5 状态机 |
| **P0-4** | **无 `inputs`/typed `outputs`/变量 I/O 声明** | 弱类型输出静默失败；变量引用无法校验 | §6 契约 |

一句话：**先把"确定性消解边界"立起来（Plan），再把"契约"变成纯数据（CDL），最后才是继续加组件。**

---

## 1. 事实基线（可复核）

以下数字均可从源码直接复核，作为本文设计的输入前提。

| 事实 | 数值 | 位置 |
|---|---|---|
| `FieldSchema.type` 开口联合成员 | **27** | `datara-web/src/graph/profiles/types.ts:12-37` |
| `FieldSchema.pick` 键数 | **17** | `types.ts:42-77` |
| `FieldSchema` 中函数值字段 | **3**（`showIf` / `onChange` / `text`） | `types.ts:84,86,88` |
| `NodeSchema` 中函数值字段 | **2**（`summary` / `ports`） | `types.ts:182` 附近 |
| **函数字段合计** | **5**（跨 `FieldSchema` 3 + `NodeSchema` 2） | 见 §1.1 |
| `FieldSchema.probe` 键数 | 3 | `types.ts:40` |
| ViewProfile 总数 | **7** | `profiles/index.ts` |
| 含 `nodeTypes` 的 profile | 4：`dag` 34 / `etl` 17 / `stream` 10 / `topo` 13 | `dag/etl/stream/topo.ts` |
| 仅 Palette 的 profile | 3：`er` / `lineage` / `relation` | 三者 `nodeTypes` 为 0 |
| `nodeTypes` 条目（dag） | 34 | `dag.ts` |
| Palette 可见 type（dag） | 32（隐藏 2：`sync` / `file_sync`，均为 runtimeOnly） | `dag.ts` |
| 组件定义副本数 | **5**（`nodeTypes` / `palette` / Master handler / `WORKER_TYPES` / `EXECUTORS`） | 全局 |
| `dagProfile.validators` | 8 条（其中 `warn` 级 3 条，`error` 级 5 条） | `dag.ts:1131-1179` |
| 服务端 `graph_json` schema 校验 | **0**（裸 `dict`） | `SaveBody` |
| 静默挂起路径 | 3 条 | 见 §5.2 |
| 无路由的可见 type | **3 条**：`stream_input`(C18) / `stream_fuse`(C19) / `stream_output`(C20) | `dag.ts`；**已由 §7.1 CI 规则 2 与 M0 目录导出器双向实测确认** |
| Master handler 键 | 18（12 逻辑 + 6 passthrough），但**仅 16 个有前端 `NodeSchema`** | `engine.py:599-608` |
| 有路由但无前端 `NodeSchema` 的 type | **3**：`smoke` / `src_select` / `tgt_select` | 仅后端 |
| 跨 profile 重名 type | **1**：`op_script`（`etl` 与 `stream` 各定义一份，**当前内容完全一致**） | M0 目录导出器实测 |
| palette 容器格式 | **不统一**：`dag`/`stream` 用 `items`，`etl` 用 `types` 且展开 `...dagProfile.palette` | M0 目录导出器实测；`Palette.vue:32` 已注明 `types` 为「老」、`items` 为「新」 |
| 无执行实现的组件（全系统） | **30**（`dag` 3 + `etl` 17 + `stream` 10） | M0 实测：后端全文检索无这些 type |
| `WORKER_TYPES` ↔ `EXECUTORS` | 11 ↔ 11，**一一对应无缺口** | `dag.py:16` / `worker/executors/*.py` |

**关于 `warn` 级 3 条**：孤立节点（`dag.ts:1152`）、重复边（`dag.ts:1154`）、必填未配置（`dag.ts:1161`）。第三条正是"未配置"闸门——它是 `warn`，因此**可以带着空必填字段直接运行**。

### 1.1 修正与补充（2026-09-26 · M0 实测）

上文基线经 M0 组件目录导出器全量实测后，有 4 处需要更正/补充。**这些都是"按 `dag.ts` 单文件推断全局"造成的偏差**：

| 项 | 旧表述 | 实测更正 |
|---|---|---|
| 函数字段 | 3 个（仅 `FieldSchema`） | **5 个**：`FieldSchema` 3 个（`showIf`/`onChange`/`text`）+ `NodeSchema` 2 个（`summary`/`ports`）。§3.2 的替代方案必须同时覆盖 `summary`/`ports`，否则组件摘要仍无法被后端复用 |
| 组件总数 | 隐含"= 34" | **不是单一集合**。全系统 **74** 个组件，分布在 4 个 profile（`dag` 34 / `etl` 17 / `stream` 10 / `topo` 13）；另有 3 个仅画布工具的 profile（`er`/`lineage`/`relation`，`nodeTypes` 为 0） |
| 无路由组件 | 4 个（含 `page_board`） | **3 个**（DAG 引擎口径）。`page_board` 已在代码与 CI 检查中按 `nonExecutable` 豁免（它是画布辅助节点，本就不该派发）；真正缺派发实现的只有 `stream_input`/`stream_fuse`/`stream_output` |
| "缺实现"的范围 | 隐含"= 3" | **全系统 30 个**。`dag` 3 个之外，`etl` 17 个与 `stream` 10 个组件在后端**全文检索不到任何执行实现**（`routes.ts` 标注 F56a 演示态）。只报 DAG 的 3 个会掩盖这个更大的问题 |
| Master handler 覆盖 | 18 个 handler ≈ 18 个组件 | **仅 16 个有前端 `NodeSchema`**。`src_select`/`tgt_select` 是纯后端保留字段，加上 `smoke`，共 **3 个类型有路由但前端无声明**（前端不可见、不可拖出） |

**由此暴露的 3 个新碎片化事实**（M1 收敛的直接对象）：

1. **组件定义分散在 4 个文件**，而非集中一处。任何"组件清单"若只看 `dag.ts` 都会漏掉 40 个组件。
2. **`op_script` 跨 profile 重复定义**：`etl` 与 `stream` 各一份 —— 复核后确认**两份内容完全一致**（label / icon / color / desc / defaults / form 逐项相同），属复制粘贴而非语义冲突。因此真实风险不是"同名不同义"，而是**改一处忘另一处的静默漂移**（无任何约束会提醒维护者两处要同步）。这恰好说明为什么需要注册表唯一真源，而不是在文档里记一句"这两个要一起改"。
3. **palette 容器格式不统一**：`dag`/`stream` 用 `items: [{type}]`，`etl` 用 `types: ['x']` 且末组 `...dagProfile.palette` 展开继承。**收敛方向已由既有代码定好**：`Palette.vue:32` 的兼容注释明确写着「`types: string[]`（老）与 `items: PaletteItem[]`（新，支持灰置 phase）」——即以 `items` 为目标形态、`types` 为待淘汰遗留。任何按单一格式解析 palette 的工具（含本项目的 M0 导出器）都必须显式兼容两种。

### 1.2 组件的执行实现归属（M1 发布闸门的依据）

M0 顺带确立了一个**此前没有显式声明**的事实：组件「由谁执行」不能从派发方式反推，必须显式建模。目录中每个组件带 `executionModel`：

| `executionModel` | profile | 含义 | 组件数 |
|---|---|---|---|
| `dag-engine` | `dag` | Master 派发点 / Worker executor 真正实现 | 34（其中 26 可路由） |
| `demo-only` | `etl` / `stream` | **无任何执行实现**，F56a 演示态 | 27 |
| `canvas-device` | `topo` | 画布拓扑元件（`shape=device`、`form=[]`），设计上不执行 | 13 |

`canvas-device` 应归入 `nonExecutable` 而非 `UNROUTED`，否则会虚增「缺执行实现」的数量——这是 M0 首版的一处分类错误，已修正。

> **对 M1 的直接约束**：`demo-only` 组件**不得**声称绑定 executor（M0 已加断言阻断）。
> 「发布必须绑定执行契约」这条红线若不区分 `demo-only`，就会给 27 个演示组件开后门、重演 G-14。
> 发布闸门必须以 `executionModel` 为准，而非仅看 `route != 'UNROUTED'`。

> M0 已把这三项做成**可机器校验的断言**（`datara-backend/common/dag_catalog.json` 的
> `crossProfileDuplicateTypes` / `paletteFormat` / `consistencyErrors`），
> 由 `tests/test_component_catalog.py` 回归，避免它们再次静默劣化。

---

## 2. 为什么必须先动结构

### 2.1 三个症状，同一个根因

| 症状 | 根因 |
|---|---|
| `fork.parallel` UI 有输入框，后端不读、前端也不用 | 声明**无后端校验**，无法发现"暴露了没人消费的字段" |
| `join` 摘要写"全部成功才触发"，实际默认 `all_terminal` | 摘要是**手写文案**，与参数语义无绑定 |
| `stream_*` / `page_board` 4 个组件可拖出、可保存、**运行必失败** | 声明与路由**无一致性校验** |

三者都不是"漏写了某个功能"，而是**没有任何环节在问"这份声明还自洽吗"**。

### 2.2 加一个组件的当前真实成本

```
1. 前端 nodeTypes 加条目（type/code/icon/category/defaults/summary/form[]）   ← 唯一"声明"
2. 前端 palette 加可见性
3. 前端写专用 summary 文案
4. 前端写 form[]（若引入新控件类型 → 改 FieldSchema.type 联合 + 写渲染分支）
5. 若引入新依赖形态 → 改 FieldSchema.pick 联合 + pickerLogic.ts + 改 onChange
6. Master 加 handler 或 WORKER_TYPES 条目
7. worker 加 executor + 注册
8. 手工保证 1/2/3/6/7 五处 type 字符串拼写一致
```

**8 步、5 份必须手工对齐的副本**。n8n 加组件是 1 步、1 份。差距不在编码量，在**没有单一真源**。

### 2.3 硬阻塞：声明不是纯数据

```ts
// types.ts:84,86,88 —— 三个函数值字段
showIf?: (data: Record<string, unknown>) => boolean
onChange?: (data: Record<string, unknown>, value: unknown) => void
text?: (data: Record<string, unknown>) => string
```

**只要这 3 个字段是 `Function`，整份 `FieldSchema[]` 就无法 JSON 序列化。** 后果是连锁的：

- 后端拿不到声明 → 无法按同一份规则校验 → **P0-4「服务端零校验」在技术上无法直接解决**；
- 声明只能打包进 Vue bundle → 无法版本化、无法服务给其他客户端；
- 声明无法进 Git diff 评审 → 组件变更不可审计。

**所以 §3 的纯数据化不是"重构洁癖"，它是解锁服务端校验的前置条件。** 必须排在 Plan 之后、之前。

---

## 3. 设计一 · 组件声明契约（CDL, Component Declaration Language）

### 3.1 单一真源与生成物

一份 CDL 声明，四处生成，**零手工同步**：

```
                     ┌─────────────────────────────┐
   component.cdl ──► │  唯一真源（纯数据，可 Git diff）│
   (YAML/TS 对象字面量) └──────────────┬──────────────┘
                                     │ codegen（构建期，可选 CI 强制）
        ┌────────────────┬───────────┼───────────┬────────────────┐
        ▼                ▼           ▼           ▼                ▼
  types.ts 生成物   pydantic 校验   Palette 条目  文档卡片卡     CI 断言输入
  （前端表单）      （后端）        （可见性）    （§3 逐项卡）  （§7 阶段 0）
```

生成物清单（必须全部由同一源产出，缺一即视为漂移）：

| # | 生成物 | 替换现状 |
|---|---|---|
| 1 | TS `FieldSchema[]` | 手写 `form[]` |
| 2 | Pydantic `ParamModel` + 校验器 | **不存在** → 解锁服务端校验 |
| 3 | Palette 条目（icon/category/visible/runtimeOnly） | `palette` 数组 |
| 4 | Master 路由缺失检测表 | 手工比对 `_execute_node` handler 字典 |
| 5 | 文档组件卡 | 手工同步两份 md |
| 6 | CI 断言输入：form key ↔ 后端读取点 | 手工 grep |

### 3.2 纯数据原则（P0-2 解法）

**铁律：CDL 里不允许出现函数、类实例、RegExp 字面量之外的任何可执行值。**

**五个**函数值字段的替代表达（跨 `FieldSchema` 3 个 + `NodeSchema` 2 个）：

| 位置 | 现状 | 替身 | 说明 |
|---|---|---|---|
| `FieldSchema` | `showIf?: (data) => boolean` | `when?: Predicate` | 声明式谓词 DSL，见 §3.5 |
| `FieldSchema` | `onChange?: (data, value) => void` | `onSet?: SideEffect[]` | 声明式副作用（清空/联动/告警） |
| `FieldSchema` | `text?: (data) => string` | `hint?: HintRef` | 静态文案或 `{ i18nKey, vars: FieldRef[] }` |
| `NodeSchema` | `summary?: (data) => string` | `summaryRef?: { template, vars: FieldRef[] }` | **由声明生成，禁止手写**——直接修掉 G-05（`join` 摘要写"全部成功"实际 `all_terminal`）那类"摘要说谎" |
| `NodeSchema` | `ports?: (data) => PortHint[]` | `portHints?: { key, label, when?: Predicate }[]` | 端口提示按 `key` 声明，**不依赖运行期数据**；需要动态文案时组合 `hint` + `when` |

> `summary` / `ports` 的存在意味着**"声明不可序列化"的范围比原先估计更大**：即使把
> `FieldSchema` 的 3 个函数全部替换掉，`NodeSchema` 仍会残留 2 个函数，后端依旧无法
> 复用同一份声明。阶段 4 的验收条件因此必须是"`FieldSchema` + `NodeSchema` 函数值
> 字段合计 = 0"，只清前者不算收敛完成。

**`onChange` 的替代是本次收敛里最需要克制的地方。** 它现在被用来做"分型切换时清空对方参数"（如 `file` 切 `sourceMode` 清 `httpUrl`）。替代方案不是把任意逻辑塞进 DSL，而是**改成后端可校验的不变式**：

```yaml
# 声明：sourceMode 与 httpUrl 互斥
params:
  - key: sourceMode
    type: select
    options: [local, http, sftp]
    required: true
    default: local
  - key: httpUrl
    type: text
    when: { field: sourceMode, op: eq, value: http }
    requiredWhen: { field: sourceMode, op: eq, value: http }   # ← 必填随分型
    exclusiveGroup: source                                        # ← 与 sourceMode 同组
```

由 **Pydantic 模型 + `exclusiveGroup`/`requiredWhen` 校验**在后端保证互斥与清空语义，而不是在前端用 `onChange` 副作用维持。这样"清空对方参数"从**约定**升级为**不变量**。

> 迁移期允许 `onChange` 暂存（`legacy: true` 标记），但**每个 legacy 字段必须在 §7 阶段 4 前清零**，并由 CI 计数阻断。

### 3.3 基元收敛：27 → 9

**收敛判据**：新基元必须同时满足 ① 能表达全部 27 项现有语义；② 参数化配置而非新增类型；③ 渲染实现可复用。

| # | 新基元 | 吸收的现有 type | 关键参数 |
|---|---|---|---|
| 1 | `text` | `text`, `textarea`, `script` | `multiline?: bool`, `rows?`, `language?: 'sql'\|'py'\|'sh'\|'txt'` |
| 2 | `number` | `number` | `min?`, `max?`, `step?`, `unit?` |
| 3 | `bool` | `bool` | — |
| 4 | `select` | `select`, `exec-node-tag` | `options?` \| `optionsFrom?: CapabilityRef` |
| 5 | `expr` | `expr`, `var-ref` | `scope?: VarScope[]`, `vars?: CapabilityRef` |
| 6 | `hint` | `hint` | `content \| { i18nKey, vars }` |
| 7 | `rows` | `params-table`, `kv-table`, `args-table`, `var-table`, `deps-list`, `branches` | `rowSchema: RowField[]`, `keyField`, `valueShape` |
| 8 | `resource` | `datasource`, `table-picker`, `field-select`, `topic-select`, `dir-select`, `runtime-node`, `upstream-ref`, `upstream-refs` | `capability: CapabilityRef`, `multi?`, `valueShape?` |
| 9 | `mapEditor` | `field-map`, `token-insert`, `probe` | `srcCap: CapabilityRef`, `tgtCap: CapabilityRef`, `transform?` |

**27 → 9，收敛比 3:1。** 三个设计要点：

1. **`rows` 是最大的收敛源（6 → 1）**。`params-table`/`kv-table`/`args-table`/`var-table`/`deps-list`/`branches` 本质都是"可编辑行集合 + 行内字段定义"，差异只在列。`rowSchema` 完全覆盖差异。
2. **`resource` 消灭全部 `pick` 键**。`dsKey`/`tableKey`/`nodeKey`/`writeAs`/`src`/`upstreamIndex`/`multiple`/`upstreamMax`/`upstream-ref*` 共 11 个键，本质是"我要什么候选列表，候选从哪来，写回什么形态"。这三个问题由 §3.4 的 `CapabilityRef` 统一回答。
3. **`mapEditor` 保留为专用基元**（不强行塞进 `rows`）。字段映射的**左右两列候选来自图上不同节点**，本质是"图内引用 + 列枚举"的组合，通用 `rows` 表达不了。诚实保留 1 个专用控件，比硬塞进通用基元更好维护。

### 3.4 能力引用 `CapabilityRef`（取代 17 个 `pick` 键）

碎片化的根源是每个组件自己发明"我要什么元数据"。统一为**能力声明**：

```yaml
# 统一能力契约
capabilities:
  datasource.list:  { params: { dsTypes?: string[] } }
  table.list:       { params: { dsFrom: FieldRef } }                 # 依赖另一个字段
  column.list:      { params: { dsFrom: FieldRef, tableFrom: FieldRef } }
  topic.list:       { params: { dsFrom: FieldRef } }
  dir.list:         { params: { nodeFrom: FieldRef } }
  runtimeNode.list: { params: { tags?: string[] } }
  upstream.nodes:   { params: { from: 'self', filterType?: string } }
  upstream.outputs: { params: { from: 'nodeId', multi: bool } }
  workflow.list:    { params: { includeSelf?: bool } }
  varCatalog:       { params: { scope?: VarScope[] } }
  param.preview:    { params: { target: FieldRef } }                 # 对标 DS 参数预览
  schema.probe:     { params: { dsA: FieldRef, dsB: FieldRef } }    # 取代 probe 字段
```

**关键收益——`dependsOn` 从"命名约定"变成"声明依赖"**：

```yaml
# 现状：pickerLogic.ts 靠字符串约定猜依赖
PICK_DEF = { tableKey: 'table', nodeKey: 'runtimeNode', ... }   # 隐式、易漏

# 新：依赖显式声明，可自动推导加载顺序与禁用态
- key: table
  type: resource
  capability: table.list
  params: { dsFrom: { field: datasource } }      # ← 依赖关系在数据里
  onDependencyError: disable                      # 依赖失败=控件禁用+行内提示，不阻塞其余字段
```

`onDependencyError: disable` 把当前"依赖为空就降级为可手填"的隐式行为（`field-select` 的 `src='upstream'` 分支）**升级为显式声明**。

**`param.preview` 是新增能力**，对标 DolphinScheduler 的参数预览：真跑一次探测，用结果填下拉。这解决"元数据耦合"的根本问题——**用户不必猜有哪些表，而是点一下按钮拿到真实候选**。

### 3.5 条件谓词 DSL（取代 `showIf`）

```ts
type Predicate =
  | { field: string; op: 'eq'|'ne'|'in'|'nin'|'gt'|'gte'|'lt'|'lte'|'exists'|'empty'; value?: unknown }
  | { all: Predicate[] }        // AND
  | { any: Predicate[] }        // OR
  | { not: Predicate }          // NOT
```

覆盖现有 `showIf` 用法（全部是"某字段等于某值"或"两字段都在候选集内"）。DSL 是**可序列化、可被后端复算、可被 CI 静态检查**的；`Function` 三者都不能。

**后端复算是关键收益**：服务端校验时能用**同一套谓词**判断"这个节点在当前分型下缺哪些必填"，从而实现 §4.3 的分级阻断——不需要后端理解前端逻辑。

### 3.6 完整 CDL 声明示例：`field_map`（C34）

作为收敛后的样板，替换现有 8 个 `form[]` 条目 + 2 个 `pick` 对象：

```yaml
type: field_map
code: C34
label: 字段映射
category: [sync]
icon: field-map
summary: 按源列→目标列映射重塑记录            # 由 keyLabel/desc 生成，非手写
inputs:                                       # §6 设计：声明式入端口
  - name: in
    label: 输入流
    maxCount: 1
outputs:                                      # §6 设计：声明式出端口
  - name: out
    label: 输出流
    vars: [record, mappedCount, unmappedFields]
exec:
  route: passthrough                          # master | passthrough | worker
  handler: _exec_passthrough
  executor: null
lifecycle:
  retry: { max: 0, strategy: none }           # 纯内存变换，重试无意义
  deadline: { softSec: 10, hardSec: 30 }
  idempotency: content                        # content=同输入必同输出，可去重
  timeoutAction: fail
params:
  - key: inputs
    type: resource
    capability: upstream.outputs
    params: { from: self, multi: true }
    required: true
    label: 输入引用
  - key: mappings
    type: mapEditor
    label: 字段映射
    required: true
    srcCap: { capability: column.list, params: { dsFrom: { nodeType: sql, field: datasource },
                                                tableFrom: { nodeType: sql, field: table } } }
    tgtCap: { capability: column.list, params: { dsFrom: { nodeType: file, field: datasource },
                                                tableFrom: { nodeType: file, field: table } } }
    transform: { type: expr, allowVar: true }
  - key: strict
    type: bool
    label: 严格模式
    default: true
    hint: 开启后未覆盖的目标列校验失败并终止整批
  - key: skipEmpty
    type: bool
    label: 跳过空值
    default: false
  - key: unmappedAction
    type: select
    label: 未映射源列处理
    default: passthrough
    options:
      - { value: passthrough, label: 原样透传 }
      - { value: drop,       label: 丢弃 }
      - { value: fail,       label: 报错 }
    when: { field: strict, op: eq, value: false }
readVars:  [record]
writeVars: []
catalog:
  palette: true
  runtimeOnly: false
  nonExecutable: false
```

**这段声明同时消灭了 4 个问题**：

1. `pick` 的 8 个 `srcNodeType`/`tgtNodeType`/`srcDsKey`/`fmSrcIndex` 等键 → 变成 `srcCap`/`tgtCap` 的 `params`，**可读且可校验**；
2. 手写 summary 文案 → 由 `label` + `vars` 生成，**不会与实际行为脱节**（修掉 `join` 摘要说谎那类问题）；
3. 后端拿到 `exec.route` + `exec.handler` → **可在 CI 检测"声明了但没路由"**（`stream_*` 4 个组件会立刻暴露）；
4. `lifecycle` 显式声明重试/超时/幂等 → 非终态 deadline 有了配置来源（§5）。

### 3.7 全 27 项收敛映射表

| 现有 type | 新基元 | 备注 |
|---|---|---|
| `text` | `text` | — |
| `textarea` | `text` | `multiline: true` |
| `script` | `text` | `multiline: true` + `language` |
| `number` | `number` | — |
| `bool` | `bool` | — |
| `select` | `select` | — |
| `exec-node-tag` | `select` | `optionsFrom: runtimeNode.list` |
| `expr` | `expr` | — |
| `var-ref` | `expr` | `readonly: true` |
| `hint` | `hint` | — |
| `params-table` | `rows` | `rowSchema: [{key,name,type:varSource}]` |
| `kv-table` | `rows` | `rowSchema: [{key,name,type:text,desc}]` |
| `args-table` | `rows` | `rowSchema: [{key,name},{key,direction,enum:[IN,OUT]},{key,expr}]` |
| `var-table` | `rows` | `rowSchema: VarDef`（复用现有 `VarDef` 接口） |
| `deps-list` | `rows` | `rowSchema: DepDef`（复用现有 `DepDef` 接口） |
| `branches` | `rows` | `rowSchema: BranchDef`，`keyField: name` |
| `datasource` | `resource` | `capability: datasource.list` |
| `table-picker` | `resource` | `capability: table.list`, `valueShape` |
| `field-select` | `resource` | `capability: column.list`, `multi` |
| `topic-select` | `resource` | `capability: topic.list` |
| `dir-select` | `resource` | `capability: dir.list` |
| `runtime-node` | `resource` | `capability: runtimeNode.list` |
| `upstream-ref` | `resource` | `capability: upstream.nodes`, `multi: false` |
| `upstream-refs` | `resource` | `capability: upstream.outputs`, `multi: true` |
| `field-map` | `mapEditor` | `srcCap` + `tgtCap` |
| `token-insert` | `mapEditor(mode: insert)` | 或独立 `insert` 模式，复用列枚举能力 |
| `probe` | `mapEditor(mode: probe)` | `capability: schema.probe` |

**注意最后两项**：`token-insert`（点选表插入 SQL 骨架）和 `probe`（探测两端同名表）本质都是"**用列/表枚举能力驱动一个动作**"，与 `field-map` 同源。三者合并为 `mapEditor` 的三个 `mode`，而不是三个独立类型——这是本次收敛能拿到 3:1 的关键。

---

## 4. 设计二 · Plan 产物（P0-1 解法，全局唯一闸门）

### 4.1 问题陈述

当前"配置是否完整"的判定链条是：

```
前端 8 条 validator（3 条 warn）→ 保存（服务端 0 校验）→ 运行 → 失败在半路
```

后果具体到三个已确认缺陷：

- `end` 带出边的图：**能存、能跑、结果错**（`_exec_end` 直接标记下游完成，语义被跳过）；
- 必填未配置：`dag.ts:1161` 是 `warn` → **带着空 SQL 也能提交运行**；
- 分支无匹配：节点永不置 `READY` → **挂起，无报错**。

Plan 把这个链条改成：

```
定义(版本化) ──► compile() ──► Plan + errors
                                    │
                        errors 非空 ──┴──► 阻断，不创建运行实例
                        errors 为空 ──────► 持久化 Plan + plan_hash → 创建运行实例
```

### 4.2 `compile()` 契约

```python
def compile(definition: Graph, ctx: CompileContext) -> Plan:
    """纯函数：同 definition + 同 ctx → 同 Plan（含同 plan_hash）。
    禁止访问 DB 写路径；允许读元数据（表存在性等）以支持外部依赖校验。
    校验规则全部来自 CDL 声明（§3），后端与前端同源。
    """
```

**纯函数是硬要求。** 若 `compile()` 有副作用或不确定性，`plan_hash` 就失去意义，复现性承诺失效。外部状态（表是否存在）通过 `ctx` 显式传入，纳入 hash 的 `inputs` 段。

### 4.3 Plan 结构

```python
class Plan(TypedDict):
    planVersion: int                  # 语义化，结构变则升
    definitionRef: DefinitionRef      # { workflowId, definitionVersion, definitionHash }
    compileAt: str                    # ISO8601
    compileContext: dict              # 参与 hash 的外部输入（表存在性快照等）
    nodes: list[PlanNode]             # 展平后的可执行节点（含物化节点）
    edges: list[PlanEdge]             # 展平后的边
    variables: list[VarBinding]       # 编译期已确定的变量绑定
    errors: list[PlanIssue]           # 空 = 可运行
    warnings: list[PlanIssue]
    planHash: str                     # sha256(canonical_json(上述除 planHash))
    catalogHash: str                  # 编译时所用 CDL 目录版本
```

```python
class PlanNode(TypedDict):
    nodeId: str                       # 逻辑节点 id
    execId: str                       # 物化后执行 id（原 id 或 sys_exec_*）
    type: str
    resolvedParams: dict              # 已绑定；仍含表达式的值单独标记，见下
    deferredExprs: list[str]          # 必须运行期求值的表达式路径（如循环体内引用 loop.*）
    outputs: list[OutputDecl]         # 声明的输出 schema
    requires: list[str]               # 前置 execId
    deadline: Deadline                # { softSec, hardSec }
    retries: RetryPolicy              # { max, strategy, backoffSec }
    idempotencyKey: str               # f"{runId}:{nodeId}:{loopIter}:{attempt}"
    route: Literal['master','passthrough','worker']
    capabilityChecks: list[Check]     # 编译期已验证的外部依赖
```

**`deferredExprs` 是这个设计里最容易被忽略但最重要的一处**：绝大多数参数应在编译期绑定，但**循环体内引用 `loop.*`、依赖上游实际输出的表达式必须延迟**。若强行在编译期求值，要么报错（`loop.*` 作用域还不存在），要么写入错误的空值。`deferredExprs` 显式列出这些路径，**使"哪些值还没定"成为 Plan 的一部分，而不是隐式约定**。

### 4.4 校验分级

| 级别 | 含义 | 处理 |
|---|---|---|
| `ERROR` | 必然导致运行失败或结果错误 | **阻断运行** |
| `WARN` | 可能有设计问题，不必然失败 | 允许运行，进 Plan 存档 + 运行页警示 |

`ERROR` 清单（每条都对应一个已确认缺陷）：

| 校验项 | 现状 | 修掉的问题 |
|---|---|---|
| `type` 必须在 CDL 目录内 | 无 | 未知 type 静默失败 |
| **声明了但无路由** | 无 | `stream_*`/`page_board` 4 个组件运行必失败 |
| 必填完整性（`requiredWhen` 随分型） | `warn` | 带空必填运行 |
| 可达性（不可达节点） | 无阻断 | 节点永不执行 |
| `end` 出度必须为 0 | 无 | 静默做错事 |
| 分支必有兜底（`branches` 非空 或 存在 default 端口） | 无 | 分支无匹配 → 挂起 |
| `dependent` 目标工作流/节点存在 | 无 | 永久 `WAITING` |
| `loop.maxIterations` 必须显式配置 | 无（靠后端缺省） | UI 不暴露 → 用户无死循环护栏感知 |
| 变量引用存在（`${wf.x}` 的 `x` 已定义） | 无 | 运行期才发现变量不存在 |
| 无环、悬空边 | 已有 `error` ✅ | — |
| 单一 `start` | 已有 `error` ✅ | — |
| 依赖字段存在（`params.dsFrom` 指向真实字段） | 无 | 声明自身错误 |

`WARN` 清单：孤立节点、重复边、多个 `end`、`mappings` 未覆盖全部目标列（可由 `strict` 提升为 `ERROR`）。

**关键设计点**：全部 `ERROR` 规则由 CDL 的 `required` / `requiredWhen` / `exclusiveGroup` / `Predicate` / `exec.route` **声明式导出**，后端不硬编码组件知识。这是 §3 纯数据化的直接回报——**没有 §3，§4 的分级校验只能写成一堆 if-else，且必然与前端漂移**。

### 4.5 `planHash` 与四项收益

```
planHash = sha256( canonical_json(Plan minus planHash) )
```

| 收益 | 机制 |
|---|---|
| **可复现** | 重跑历史运行用**存档 Plan**，不读当前定义 → 定义后续编辑不影响历史可追溯性 |
| **可审计** | 合规环境里 Plan 可签名；"这次改动只影响字段映射"由 Plan diff 证明 |
| **可检测漂移** | 运行开始时校验 `planHash`，对不上即事故（防定义在运行中途被改） |
| **可解释失败** | 失败时能给出"编译期已知 N 个 warning 未处理 + 运行时错误 M"，而非一句 `executor_not_implemented` |

### 4.6 与现有物化逻辑的对接

Datara 已有两处物化，都应收敛为"Plan 的展开步骤"，而非独立的运行时副作用：

| 现有逻辑 | 位置 | 改造 |
|---|---|---|
| `materialize_sync_exec` 拍平同步链 | `engine.py` | 移入 `compile()`，产出显式 `sys_exec_*` PlanNode；运行期不再动态改图 |
| `param` → `param_resolved` 绑定 | `engine.py:1554` | 移入 `compile()`，产出 `resolvedParams` + `deferredExprs`；运行期只做 `deferredExprs` 求值 |
| `graph_json` 复制到实例 | `SaveBody` | 升级为 `Plan` 存档 + `planHash` |

**这一步同时消灭 G-14 的一半**：`stream_*` 之所以运行必失败，是因为它既不在 handler 字典也不在 `WORKER_TYPES`。Plan 的 `ERROR: 声明了但无路由` 会在**保存/编译时**就报出来，而不是运行时。

---

## 5. 设计三 · 非终态必有 deadline（P0-3 解法）

### 5.1 三条静默挂起路径

| # | 路径 | 机制 | 现状后果 |
|---|---|---|---|
| 1 | 分支无匹配 | `_exec_conditions`/`_exec_switch` 遍历 `branches` 无命中 → 不置 `READY` | 节点永久 `PENDING`，**无任何错误** |
| 2 | `dependent` 目标缺失 | `_parse_deps` 中 `wfCode==0` 被静默丢弃 → 无 deps 也无错误 | 永久 `WAITING` |
| 3 | `stream_*` 无路由 | 不在 handler 也不在 `WORKER_TYPES` | `FAILURE: executor_not_implemented`（唯一"响亮的失败"） |

### 5.2 目标状态机

```
                      ┌──────────┐
   创建 ──────────►  PENDING   │  编译/物化完成
                      └────┬─────┘
                           │ 前置满足
                      ┌────▼────┐
                      │ READY   │
                      └────┬────┘
                           │ 派发
                      ┌────▼─────┐   hard deadline 到期
                      │ RUNNING  ├──────────────────► TIMEOUT
                      └────┬─────┘                        （终态）
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
    ┌─────────┐      ┌─────────┐      ┌──────────┐
    │ SUCCEEDED│     │ FAILED  │      │ CANCELLED│
    └─────────┘      └────┬────┘      └──────────┘
                          │ onError 路由
                          ▼
                  跳过下游 / 走 error 分支 / 终止整运行

   ┌──────────┐  soft deadline 到期（未收到任何心跳/进度）
   │ BLOCKED  ├───────────────────────────────► ORPHANED（终态）
   └──────────┘  上游迟到时仍可复活为 READY
```

**三条铁律**：

1. **每个非终态携带 `deadline`**，来源为 CDL 的 `lifecycle.deadline`（§3.6）。缺省值由**组件类别**决定（逻辑流控 24h、worker 1h、探针 5m），而非全局统一。
2. **`TIMEOUT` 与 `ORPHANED` 是终态**，触发 `onError` 路由 —— 不再"永远等待"。
3. **`ORPHANED` 可复活**：上游迟到仍可回到 `READY`。这保留了流式/长依赖场景的弹性，同时消灭永久挂起。

### 5.3 挂起路径的具体修法

| 路径 | 修法 | 配置来源 |
|---|---|---|
| 分支无匹配 | ① 优先：`branches` 显式声明兜底分支（`isDefault: true`）；② 无兜底则 `ERROR` 阻断编译 | CDL `branches.rowSchema` + `onSet` |
| `dependent` 目标缺失 | `_parse_deps` 识别 `wfCode==0` → 编译期 `ERROR: 依赖目标不存在` | CDL `requiredWhen` + 编译期存在性检查 |
| `loop` 无上限 | `maxIterations` **提升为必填**（`required: true`），或提供"按数据量自动收敛"选项 | CDL `lifecycle` |
| 挂起兜底 | Master 定时扫描：非终态超 `deadline` → 置 `TIMEOUT`/`ORPHANED` + 告警 | Plan 的 `deadline` 字段 |

---

## 6. 设计四 · 端口 / 输入 / 输出 / 变量声明（P0-4 解法）

现状：只有 `NodeSchema.outputs`（**出端口**），入端口、输出**数据 schema**、变量 I/O 全部隐式。

```ts
// 目标：每个组件的完整契约
interface ComponentContract {
  inputs?:  PortDecl[]   // 入端口：连什么、连几个
  outputs: PortDecl[]    // 出端口：暴露什么、产什么
  readVars:  VarRefPattern[]   // 读哪些变量（供编译期校验）
  writeVars: VarRefPattern[]   // 写哪些变量（供变量面板与影响分析）
  lifecycle: { deadline, retries, idempotency, timeoutAction }
  exec: { route, handler?, executor? }
}
interface PortDecl {
  name: string
  label: string
  maxCount?: number          // 缺省 1；'unbounded' 显式声明
  dataSchema?: DataSchema    // 该端口流过的数据形状（§6.1）
}
interface DataSchema { fields: { name, type, desc?, nullable? }[] }
type VarRefPattern = 'params.*' | 'outputs.*' | 'loop.*' | string
```

### 6.1 分类要素矩阵（哪些组件必须声明什么）

| 组件类别 | `inputs` | `outputs`(端口) | `dataSchema` | `readVars` | `writeVars` |
|---|---|---|---|---|---|
| 源（`stream_input`,`file`） | — | 必须 | 必须 | 声明 | 声明 |
| 变换（`sql`,`field_map`） | 自动派生（不必手填） | 必须 | 必须 | 声明 | 声明 |
| 分支（`conditions`,`switch`） | 自动派生 | 端口按 `branches` 动态 | 不需要 | 声明 | — |
| 执行（`shell`,`http`,`sync`） | 自动派生 | 必须 | **必须（typed）** | 声明 | 声明（含 `OUTPUT`） |
| 逻辑（`variable`,`delay`） | — | 无/仅副作用 | 不需要 | 声明 | **写即目的** |
| 宿主（`page_board`） | — | 无 | — | — | — |

**三条规则**：

1. **输入必须自动派生，禁止手填**。手填输入就制造了与图的第二真源，必然漂移。Datara 的 `upstream-refs` + 拖边即引用做对了，**CDL 里 `inputs` 只描述"能连几个、能连什么类型"，不描述"实际连了谁"**。
2. **输出必须带 `dataSchema`**。否则 `${outputs.x}` 弱类型、静默失败——现状 `http` 取不到路径就给 `""`，下游拿到空串毫无察觉（G-11 同类）。
3. **变量 I/O 必须声明**。零声明导致：无法校验引用、无法做变量面板、无法做"谁在用这个变量"的影响分析。

### 6.2 变量 I/O 声明解锁的三件事

| 能力 | 现状 | 声明后 |
|---|---|---|
| 引用校验 | 运行期才发现 `${wf.xxx}` 不存在 | **编译期 `ERROR`** |
| 变量面板 | 无；用户只能靠记忆 | 从 `writeVars` 聚合出**目录**（谁定义、类型、说明） |
| 影响分析 | 不可能 | 改一个变量 → 列出所有读写它的节点 |

第三条对数据治理场景价值最高：**变量是跨工作流的隐式耦合，没有影响分析就没有安全的重构。**

---

## 6.9 附：M0「组件目录」已交付（2026-09-26）

M0 是组件管理能力（设计 → 发布 → 拖入）的**只读前置**，不含任何写能力。已落地：

| 交付物 | 路径 | 说明 |
|---|---|---|
| 目录导出器 | `scripts/export_dag_catalog.py` | 从 4 个含 `nodeTypes` 的 profile 源码解析组件 → JSON；`--check` 为 CI 漂移守卫 |
| 目录快照 | `datara-backend/common/dag_catalog.json` | **Git 内唯一真源**，可 diff、可评审；**刻意不落库**（落库会产生"生成物与源码不同步"的漂移陷阱） |
| 只读 API | `datara-backend/api/component.py` | `GET /components`、`/stats`、`/catalog`、`/{type}` |
| 前端清单页 | `datara-web/src/views/meta/ComponentCatalogView.vue` | 路由 `/meta/components`；**主动展示注册表漂移**，不做"看起来正常"的列表 |
| 回归测试 | `datara-backend/tests/test_component_catalog.py`（20 项）、`datara-web/src/services/__tests__/componentApi.test.ts`（10 项） | 含漂移守卫的绕过回归 |

M0 顺带把 §1.1 的 4 项更正与 3 个新碎片化事实变成了**可执行断言**，这是它超出"做个列表"的实际价值。

**M0 明确不做**（避免范围蔓延）：组件新建/编辑、CDL 编辑器、`t_component` 落库、发布与版本冻结、executor 绑定校验。这些属 M1～M3。

**M1 起步的前置结论**（已由 M0 证实，非推测）：
- 用户组件必须落 `t_component` / `t_component_version`（复用 `t_wf_definition` 的 `version` + `release_state` 模式与 `t_wf_definition_log` 审计模式）；
- **type 全局唯一性必须成为约束**——`op_script` 跨 profile 重复定义已证明仅靠 profile 内唯一不够；两处定义当前一致，风险是同步漂移而非语义冲突；
- palette 容器格式收敛为 `items`（既有 `Palette.vue:32` 已把 `types` 标为「老」，方向无需重新决策），否则设计器无法统一渲染；
- **发布闸门必须以 `executionModel` 为准**（见 §1.2）：`demo-only` 的 27 个组件没有执行实现，若仅按 `route != UNROUTED` 判定就会给它们开出后门。

---

## 7. 迁移路线（6 阶段，无 big-bang）

每阶段独立可交付、独立可回滚，**任一阶段中断都不留下半成品状态**。

| 阶段 | 内容 | 风险 | 交付物 | 出口判据 |
|---|---|---|---|---|
| **0 · 立纪律**（无行为变更） | ① CI 断言：`form` 中每个 `key` 必须在后端被读取 → **删 `fork.parallel`**；② 修正 `join` 摘要；③ `page_board` 加 `nonExecutable`；④ 补 4 条 validator（先 `warn`） | 极低 | `scripts/check_dag_route_completeness.py`（**已落地**）+ 摘要修正 + `nonExecutable` | 硬缺口从 4 降为 3（`page_board` 移出失败集） |
| **1 · 影子 Plan**（只报告不阻断） | 实现 `compile()`，产出 Plan + issues，**不改变现有运行路径**；新增"编译报告"页 | 低（纯新增） | `compile` 模块 + 报告页 | 存量 100% 工作流可编译；报告页能列出全部 issues |
| **2 · Plan 阻断** | `errors` 非空阻断运行；`Plan` 持久化 + `planHash` | **中**（会拦住现有脏图） | 存档表 + 运行前闸门 | 存量脏图已清理完毕（阶段 1 报告清零） |
| **3 · CDL 目录后端下发** | CDL 声明落为单一真源；`GET /api/v1/components`；前端改为消费；**解锁服务端校验** | 中 | CDL 源 + 端点 + 前端适配 | 前端 `nodeTypes` 手写 `form[]` 清零；5 副本 → 1 |
| **4 · 基元收敛** | 27 → 9；`pick` 17 键 → `CapabilityRef`；5 个函数字段 → DSL/声明式摘要；**legacy 计数归零** | 中（前端渲染层） | 新 `FieldRenderer` + 9 基元 | ~~`FieldSchema.type` 联合 = 9；`FieldSchema`+`NodeSchema` 函数值字段 = 0~~ → **部分达成（2026-09-27 核查）**：`FieldKind` 已收敛 9 基元（B3，`SPEC_UI_TYPES` 前后端同口径）；但**运行时类型 `src/graph/profiles/types.ts` 仍含 6 个函数字段**（`FieldSchema.showIf:113` / `onChange:115` / `text:117`，`NodeSchema.summary:223` / `ports:227` / `related:233`），验收条件「函数值字段 = 0」**未达成**。已达成的是**导出/序列化层**归零：目录导出将函数字段折叠为 `hasWhen` 布尔等纯数据标记，故「组件声明只定结构」在 catalog 产物上成立、在 `types.ts` 类型层不成立。`DropPolicy`（`types.ts:188-193`）本身已是纯数据，红线 2 在该类型上成立。详见实施计划 §8.3，收敛属 M3 范围 |
| **5 · 契约声明** | `inputs`/`dataSchema`/`readVars`/`writeVars` 补齐；变量面板；typed 输出 | 中 | 变量面板 + 静态校验 | `${outputs.x}` 弱类型失败被编译期拦截 |
| **6 · 组件资产化** | 节点"另存为组件"；子工作流（组件展开成链）；模板从代码函数改为数据 | 高 | 资产表 + 版本 | 组件可跨工作流/环境复用与评审 |

**阶段 0 和 1 是纯增益、零风险，建议立即做。** 阶段 2 是第一个有行为变化的闸门，**必须在阶段 1 报告清零后才开**。

### 7.1 阶段 0 的 CI 断言（可直接落地）

```
规则 1（字段消费）：对每个 component，CDL params[].key 必须在后端参数模型有读取点
                    → 违例即失败。阶段 0 用现有 form[] + grep 近似实现
规则 2（路由完备）：CDL 声明的 type 必须命中 Master handler ∪ WORKER_TYPES ∪ 显式 nonExecutable
                    → 阶段 0 会立刻抓出 stream_input/fuse/output、page_board
规则 3（联合收敛）：FieldSchema.type 成员数 ≤ 9；FieldSchema 中不得出现 Function 类型字段
                    → 阶段 4 前作为趋势指标，阶段 4 后作为硬门禁
规则 4（编号唯一）：CDL type/code 一一对应，无重复、无空 code（显式 `null` 除外）
```

**规则 2 是最高性价比的一条**：它是一个纯静态检查，不需要 Plan、不需要 CDL 纯数据化，**用当前的 `dag.ts` + `engine.py` + `dag.py` 就能跑**。

**已落地并实测**：`scripts/check_dag_route_completeness.py`（零依赖，仅标准库 + 正则）。

实测输出（2026-09 基线）：

```
nodeTypes           : 34
master handler 键   : 18
WORKER_TYPES 键     : 11
EXECUTORS 键        : 11
模板豁免            : 4  [demo_pipeline, file_sync_orch, src_base_orch, tgt_base_orch]
非可执行宿主豁免    : 1  [page_board]

[FAIL] 声明了但无路由 —— 可拖出、可保存、运行必失败：3 项
   - stream_fuse     code=C19  categories=stream  runtimeOnly=False
   - stream_input    code=C18  categories=stream  runtimeOnly=False
   - stream_output   code=C20  categories=stream  runtimeOnly=False
[OK] WORKER_TYPES 与 EXECUTORS 一一对应
EXIT=1
```

**实测把"4 个运行必失败"精确化为两类**，这是纯人工分析得不到的结论：

| 类别 | type | 性质 | 修法 |
|---|---|---|---|
| **硬缺口**（3） | `stream_input` / `stream_fuse` / `stream_output` | 无论怎么声明都无执行路径 —— Master 无 handler、worker 无 executor | 需 P2 独立 `stream_job`；短期应在 Palette 隐藏 |
| **缺声明**（1） | `page_board` | 语义上是页面宿主、**本就不该有执行路径**，但未标注 `nonExecutable` → 被当普通节点运行 → `executor_not_implemented` | 加 `nonExecutable: true` 即可，**成本一行** |

同时实测确认了一个**正面结论**：`WORKER_TYPES`(11) 与 `EXECUTORS`(11) 严格一一对应，**worker 侧无缺口**。此前 G-20 的担忧在 worker 侧不成立——漂移只存在于"前端声明 vs 后端路由"这一侧，这与 §2.1 的诊断一致。

脚本同时输出反向断言（`WORKER_TYPES` 有但无 `EXECUTORS`），当前为空。

---

## 8. 验收标准

### 8.1 契约层

- [ ] CDL 声明可 `JSON.stringify` / `yaml.safe_load` 往返无损
- [ ] CDL 中 `Function` 类型字段数 = **0**
- [ ] `FieldSchema.type` 成员数 ≤ **9**
- [ ] `pick` 键数 = **0**（全部并入 `CapabilityRef.params`）
- [ ] `exec.route` 在 34 个组件上 100% 命中 handler ∪ `WORKER_TYPES` ∪ `nonExecutable`

### 8.2 Plan 层

- [ ] `compile()` 幂等：同输入两次调用 `planHash` 相同
- [ ] `Plan` 中 `deferredExprs` 非空节点有显式记录（无隐式延迟求值）
- [ ] §4.4 的 12 条 `ERROR` 全部有对应校验实现与单测
- [ ] 存量全部工作流编译 `errors` 为空（阶段 2 前置条件）
- [ ] 存档 Plan 可重放：重放结果与原始运行一致
- [ ] 运行启动时 `planHash` 校验生效（定义被中途改动能被检出）

### 8.3 运行时

- [ ] 非终态节点 100% 携带 `deadline`
- [ ] §5.1 的 3 条挂起路径全部产生终态（不再有无错挂起）
- [ ] `loop.maxIterations` 为必填或显式自动收敛
- [ ] `TIMEOUT` / `ORPHANED` 触发 `onError` 路由

### 8.4 表单层

- [ ] 表单字段全部由 CDL 驱动（无硬编码 `form[]`）
- [ ] 分型切换的互斥/清空由 `exclusiveGroup` + 后端校验保证（非前端副作用）
- [ ] `param.preview` 能力可用（点选获取真实候选，对标 DS 参数预览）
- [ ] 表达式支持**点选变量**而非仅手写（对标 Retool）

---

## 9. 与 G-01～G-25 缺口映射

| 缺口 | 本文章节 | 解决/缓解 |
|---|---|---|
| G-01 分支无匹配挂起 | §5.3 | ✅ 解决 |
| G-02 `switch '*'` 语义 | §3.5 + §5.3 | ✅ 由 `Predicate` 显式定义 |
| G-03 `fork.parallel` 无消费 | §7.1 规则 1 | ✅ 解决 |
| G-04 `fork` 出边与并行数不一致 | §4.4 `ERROR` 清单 | ✅ 解决 |
| G-05 `join` 策略语义 | §3.6（summary 由声明生成） | ✅ 摘要不再手写说谎 |
| G-06 `merge` 等待集不校验 | §4.4 | ✅ |
| G-07 `dependent` 永久 `WAITING` | §5.3 | ✅ 解决 |
| G-08 `loop.maxIterations` 未暴露 | §5.3 | ✅ 解决 |
| G-09 循环内变量作用域 | §4.3 `deferredExprs` | ✅ 显式化 |
| G-10 嵌套 `sync` 拍平假设 | §4.6 | ⚠️ 缓解（拍平移入 compile） |
| G-11 输出提取失败静默空串 | §6.1 规则 2 | ✅ `dataSchema` 强制 |
| G-12 `condition_set` 语义弱 | §3.7（并入 `rows`） | ⚠️ 需重新定义语义 |
| G-13 `field_map` 未覆盖目标列 | §4.4 `WARN`/可升级 `ERROR` | ✅ |
| G-14 `stream_*` 运行必失败 | §7.1 规则 2 + §4.6 | ✅ 编译期暴露 + **根治已落地**（`extract_stream_subgraph` 提取流子图 + scheduler 随批实例注册 stream_job，流节点不进入 Master 任务状态机） |
| G-15 `page_board` 无后端 | §6（`nonExecutable`） | ⚠️ 标记已解决，宿主实现属 P2 |
| G-16 端点/连接器运行时缺失 | §6.1 规则 2（`capabilityChecks`） | ⚠️ 编译期可发现，运行期仍需实现 |
| G-17 `page_board` 执行语义 | §6（`nonExecutable`） | ⚠️ 同上 |
| G-18 定时/循环恢复 | §5.2（`ORPHANED` 可复活） | ⚠️ 部分 |
| G-19 多注册表漂移 | §3.1（5 → 1） | ✅ 解决 |
| G-20 执行器/能力缺口 | §7.1 规则 2 | ✅ 暴露 |
| G-21 保存无 schema 校验 | §3.1 生成物 2 + §7 阶段 3 | ✅ 解决 |
| G-22 `t_task_definition` 未使用 | §4.3 `definitionRef` | ⚠️ 定义版本化落点 |
| G-23 多 Master 竞争 | §4.2 纯函数 + 单写者 | ⚠️ 非本文重点 |
| G-24 输出契约弱类型 | §6.1 规则 2 | ✅ 解决 |
| G-25 `end` 出边无校验 | §4.4 `ERROR` 清单 | ✅ 解决 |

**覆盖统计**：✅ 完全解决 **14** 项；⚠️ 部分缓解 **10** 项；❌ 未触及 **1** 项（G-23 多 Master 竞争，属运行时一致性问题，另文处理）。

**最关键的三条**：G-19（注册表漂移）、G-21（服务端零校验）、G-14（4 个组件运行必失败）——**已全部 [DONE]**：G-19 由"单一真源 + 纯数据声明"解锁；G-21 由 R0-R12 规则引擎收口；G-14 由流子图提取 + stream_job 注册完整落地。

---

## 10. 一页纸总结

| 层 | 现状 | 目标 | 关键动作 |
|---|---|---|---|
| **组件声明** | 5 份副本、散落 4 个 profile、27 个控件类型、17 个 `pick` 键、5 个函数字段、**不可序列化** | 1 份纯数据 CDL，9 个基元，声明式能力引用 | 阶段 0/3/4 |
| **闸门** | 8 条 validator（3 条 `warn`）+ 服务端 0 校验 | **Plan 编译期全阻断** + `planHash` | 阶段 1/2 |
| **运行时** | 3 条静默挂起路径；无 deadline | 非终态必有 deadline；`TIMEOUT`/`ORPHANED` 为终态 | 阶段 2 + §5 |
| **契约** | 只有出端口；输出弱类型；变量 I/O 零声明 | `inputs` + typed `dataSchema` + `readVars`/`writeVars` | 阶段 5 |
| **复用** | 组件是代码，模板是代码函数 | 组件是**可版本化、可评审、可跨环境复用的资产** | 阶段 6 |

**执行顺序的硬约束**：`阶段 0 → 1 → 3 → 4 → 2 → 5 → 6`。
即：**先让声明可序列化（3、4），再开闸门（2）**。顺序反了会导致 Plan 校验逻辑硬编码组件知识，随后必然与前端漂移——那就是回到今天的 5 副本问题。

