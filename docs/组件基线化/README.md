# 组件基线化总进度册

> 上游设计：[组件基线化与逐组件发版设计.md](../组件基线化与逐组件发版设计.md)（2026-09-28 定稿）
> 本文 = 37→35 type 逐组件循环的唯一进度台账；每组件五步循环完成后回写本表与对应设计册。

## 0. 实测口径注记（2026-09-28 执行首日复核）

设计定稿统计「37 个 DAG type」，执行首日实测目录快照（`datara-backend/common/dag_catalog.json`，catalogHash=6d15aab4b46cf221，随代码演进）：

- dag profile 全量 **35 type** = 33 可拖（paletteVisible=true）+ 2 runtimeOnly（`sync`/`file_sync`，运行态物化消费）
- **同步类恰好 9 个**，与设计「同步类 9 组件」完全一致，M-B1 范围不受影响
- 37 与 35 的差额属设计期统计口径（含展示型 page_board/模板 demo_pipeline 的归类差异），以本表 35 行为执行真源；后续若目录新增 type，先补本表再进入循环

## 1. 生命周期状态图例

| 状态 | 语义 |
|---|---|
| pending 未开始 | 仅持有底稿导出的初始声明，语义分析未动 |
| designing 设计中 | 语义分析产出规格草案，待/已确认，底稿编辑中 |
| testing 待实测 | 底稿八段声明完成，本地全绿，待 1.9 真实数据流实测 |
| confirming 待认可 | 1.9 实测通过，等用户在工作台点「认可发 v1」 |
| published 已发 v1 | 治理三表落库，D1-D3 语义全套生效 |

## 2. 总进度表（35 type）

状态：⬜pending / 🟡规格草案待确认 / 🔵designing / 🧪testing / ⏳confirming / ✅published

### M-B1 同步类（9）

| # | type | 编号 | 名称 | 状态 | 认可记录 |
|---|---|---|---|---|---|
| 1 | endpoint_select | C37 | 端点选择 | 🟡 | 规格草案完成，待用户确认 |
| 2 | field_map | C34 | 字段映射-复制 | 🟡 | 规格草案完成，待用户确认 |
| 3 | field_map_union | C36 | 字段映射-联合 | 🟡 | 规格草案完成，待用户确认 |
| 4 | condition_set | C35 | 条件设定 | 🟡 | 规格草案完成，待用户确认 |
| 5 | src_base_orch | C29 | 源表基准编排 | 🟡 | 规格草案完成，待用户确认 |
| 6 | tgt_base_orch | C30 | 目标表基准编排 | 🟡 | 规格草案完成，待用户确认 |
| 7 | file_sync_orch | C31 | 文件同步编排 | 🟡 | 规格草案完成，待用户确认 |
| 8 | sync | C17 | 数据同步（运行态） | 🟡 | 规格草案完成，待用户确认 |
| 9 | file_sync | C24 | 文件入仓执行（运行态） | 🟡 | 规格草案完成，待用户确认 |

### M-B2 ETL/计算类（9）

| # | type | 编号 | 名称 | 状态 | 认可记录 |
|---|---|---|---|---|---|
| 10 | sql | C11 | SQL | ⬜ | — |
| 11 | shell | C12 | Shell | ⬜ | — |
| 12 | python | C13 | Python | ⬜ | — |
| 13 | ssh | C14 | SSH 脚本 | ⬜ | — |
| 14 | procedure | C15 | 存储过程 | ⬜ | — |
| 15 | http | C16 | HTTP | ⬜ | — |
| 16 | file | C22 | 文件读取 | ⬜ | — |
| 17 | assert | C25 | 数据校验 | ⬜ | — |
| 18 | notify | C26 | 通知 | ⬜ | — |

### M-B3 流处理类（4）

| # | type | 编号 | 名称 | 状态 | 认可记录 |
|---|---|---|---|---|---|
| 19 | stream_input | C18 | 流输入 | ⬜ | — |
| 20 | stream_fuse | C19 | 流融合 | ⬜ | — |
| 21 | stream_output | C20 | 流输出 | ⬜ | — |
| 22 | page_board | — | 页面组件（展示型） | ⬜ | — |

### M-B4 逻辑控制类（13）

| # | type | 编号 | 名称 | 状态 | 认可记录 |
|---|---|---|---|---|---|
| 23 | start | C1 | 开始 | ⬜ | — |
| 24 | end | C2 | 结束 | ⬜ | — |
| 25 | conditions | C3 | 条件分支 | ⬜ | — |
| 26 | switch | C4 | 切换 | ⬜ | — |
| 27 | fork | C5 | 并行分叉 | ⬜ | — |
| 28 | join | C6 | 汇合（AND） | ⬜ | — |
| 29 | merge | C7 | 合并（OR） | ⬜ | — |
| 30 | delay | C8 | 延时执行 | ⬜ | — |
| 31 | dependent | C9 | 依赖 | ⬜ | — |
| 32 | loop | C10 | 循环迭代 | ⬜ | — |
| 33 | variable | C21 | 变量组件 | ⬜ | — |
| 34 | smoke | C38 | 冒烟 | ⬜ | — |
| 35 | demo_pipeline | — | 示例管道模板 | ⬜ | — |

## 2.5 M-B1 同步类规格草案汇总（2026-09-28，待用户确认）

9 个设计册已完成第 1/2/3 节（语义分析 / 八项表单规格 / 声明对照）：

| type | code | 执行模型 | 八段要点 |
|---|---|---|---|
| endpoint_select | C37 | 直通（passthrough） | params 16 + conditions 10 + requiredIf 2 + outputs 2 |
| field_map | C34 | 直通 | inputs/outputs 各 1（upstreamOutputs）+ mapEditor cap |
| field_map_union | C36 | 直通 | params 4 + conditions 1 + refs 显式空注记 |
| condition_set | C35 | 直通 | params 3 + refs（wf/time 变量域）+ upstream-columns 语义 |
| sync | C17 | runtimeOnly worker | params 4 + exports 7 + 血缘锚点（srcDs/tgtDs） |
| file_sync | C24 | runtimeOnly worker | params 5 + conditions 1 + exports 4 + 血缘锚点（filePath/tgtDs） |
| src_base_orch | C29 | 模板（落图即展开） | 八段空 + template.chain 声明式链 |
| tgt_base_orch | C30 | 模板 | 八段空 + template.chain |
| file_sync_orch | C31 | 模板 | 八段空 + template.chain |

**规格草案中的 8 项设计决策**（随草案一并请用户确认）：
1. **tgtTable 单字段化**：endpoint_select 双 key 同名分型（required 两态 showIf 互斥）→ 单字段 + constraints.requiredIf（八段同段 key 唯一约束）。
2. **summary 声明化**：`summary: (d) => ...` 函数 → `render.summaryRules` 分型模板规则数组（无 when 为兜底）。
3. **inputs/outputs 段语义**：旧表单的 inputs/outputs 字段（upstreamOutputs 选择器）即节点数据面声明，归位八段的 inputs/outputs 段；纯配置参数归 params。
4. **dataScope 映射**：`dataScope: 'upstream-columns'`（F3 值域闸门）→ refs.scopes 扩展值 `upstream-columns`，闸门消费点不变。
5. **常量 text 函数字面量化**：hint 的常量 text 函数 → 字符串字面量。
6. **defaults 并入 default**：file_sync 等组件 defaults 值并入对应 params 字段 default 显式声明。
7. **合并兜底键不双真源**：file_sync defaults 中与 endpoint_select 文件区重复的键（fileType/delimiter 等）不入 params，注记保留（合并配置优先）。
8. **模板链声明化**：src/tgt/file_sync_orch 的 `template.modes[].build` TS 函数 → `template.chain` 声明式节点/边清单（纯数据，随 spec 冻结）；展开器改消费声明式链，build 函数退役——本组组件 M-B1 实现阶段的主要前端改动。

## 3. 逐组件五步循环纪律（复述设计 §8）

1. **语义分析**：读 executor 实现 + 旧声明 → 设计册产出八段表单规格草案
2. **用户确认规格草案**（不确认不动手实现）
3. **实现**：前端八段声明 + 必要后端微调
4. **验证**：pytest/vitest 全绿 → 单独过 1.9 真实数据流
5. **认可发 v1**：工作台点认可 → 治理三表落库 → 本表与设计册回写归档

纪律：1.9 不可达时该组件挂 testing（待实测），不阻塞下一组件的**设计**；发版必须等实测通过 + 用户认可。

## 4. 设计册索引

每组件一册 `./<type>.md`，章节固定七节：语义分析 → 八项表单规格 → 表单声明对照 → 执行契约（前后端改动记录）→ 血缘与变量声明 → 1.9 实测记录 → 认可记录。

- M-B1：[endpoint_select](./endpoint_select.md) · [field_map](./field_map.md) · [field_map_union](./field_map_union.md) · [condition_set](./condition_set.md) · [src_base_orch](./src_base_orch.md) · [tgt_base_orch](./tgt_base_orch.md) · [file_sync_orch](./file_sync_orch.md) · [sync](./sync.md) · [file_sync](./file_sync.md)
- M-B2：[sql](./sql.md) · [shell](./shell.md) · [python](./python.md) · [ssh](./ssh.md) · [procedure](./procedure.md) · [http](./http.md) · [file](./file.md) · [assert](./assert.md) · [notify](./notify.md)
- M-B3：[stream_input](./stream_input.md) · [stream_fuse](./stream_fuse.md) · [stream_output](./stream_output.md) · [page_board](./page_board.md)
- M-B4：[start](./start.md) · [end](./end.md) · [conditions](./conditions.md) · [switch](./switch.md) · [fork](./fork.md) · [join](./join.md) · [merge](./merge.md) · [delay](./delay.md) · [dependent](./dependent.md) · [loop](./loop.md) · [variable](./variable.md) · [smoke](./smoke.md) · [demo_pipeline](./demo_pipeline.md)

## 5. M-B0 基建交付清单（2026-09-28）

| 项 | 产物 | 状态 |
|---|---|---|
| 进度表 | `t_baseline_progress`（type 唯一 / status / draft_spec / draft_rev / check_report / test_records / confirmed_by/confirmed_at） | ✅ |
| 工作台 | 前端 `/meta/baseline` 三区（清单看板 / 设计区 / 证据区） | ✅ |
| 八段编辑器 | 低代码表单编辑器（八段 tab + 字段属性 + 实时预览，纯数据声明） | ✅ |
| 认可发版 | `POST /components/{type}/baseline/publish`（体检落报告不拦截 → 写 t_component(scope=builtin)+t_component_version(v1,published)+t_component_log） | ✅ |
| 底稿导出 | `scripts/export_baseline_drafts.py`（35 type 初始底稿 + 进度初始化，--apply 入库） | ✅ |
| 清库归档 | `scripts/archive_and_purge.py`（工作流定义+实例导出 JSON 归档 → 确认后清空） | ✅ |
| 血缘预留 | spec.lineage 声明 + `GET /components/{type}/lineage-decl` + 声明级 `/lineage/graph` stub | ✅ |
| 验证 | pytest / vitest 全绿 | ✅ |
