# 组件基线化总进度册

> 上游设计：[组件基线化与逐组件发版设计.md](../组件基线化与逐组件发版设计.md)（2026-09-28 定稿）
> 本文 = 37→35 type 逐组件循环的唯一进度台账；每组件五步循环完成后回写本表与对应设计册。

## 0. 实测口径注记（2026-09-28 执行首日复核）

设计定稿统计「37 个 DAG type」，执行首日实测目录快照（`datara-backend/common/dag_catalog.json`，catalogHash=83929cf7c3c5c660，随代码演进）：

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
| 1 | endpoint_select | C37 | 端点选择 | ✅ | 八段规格完成，10 项体检全过，1.9 实测通过（wf=97 v5，config 输出正确，同步 250K 行）；认可发 v1（2026-09-29 11:46，admin，spec_hash 3b5cb7e1…） |
| 2 | field_map | C34 | 字段映射-复制 | ✅ | 八段规格完成，10 项体检全过，1.9 实测通过（wf=97 v5，直通配置拍平正确）；认可发 v1（2026-09-29 11:46，admin，spec_hash 98265896…） |
| 3 | field_map_union | C36 | 字段映射-联合 | ✅ | 八段规格完成，10 项体检全过，1.9 实测通过（wf=99 v2，config 拍平正确，sync 250K 行）；认可发 v1（2026-09-29 11:46，admin，spec_hash 894f9081…） |
| 4 | condition_set | C35 | 条件设定 | ✅ | 八段规格完成，10 项体检全过，1.9 实测通过（wf=97 v5，直通配置拍平正确）；认可发 v1（2026-09-29 11:46，admin，spec_hash 56e59cfa…） |
| 5 | src_base_orch | C29 | 源表基准编排 | ✅ | 八段规格完成（含模板链），10 项体检全过，1.9 实测通过（展开链与 template.chain 声明一致）；认可发 v1（2026-09-29 11:46，admin，spec_hash a846e0c9…） |
| 6 | tgt_base_orch | C30 | 目标表基准编排 | ✅ | 八段规格完成（含模板链），10 项体检全过，1.9 实测通过（展开链与 template.chain 声明一致）；认可发 v1（2026-09-29 11:46，admin，spec_hash 5ac867ef…） |
| 7 | file_sync_orch | C31 | 文件同步编排 | ✅ | 八段规格完成（含模板链），10 项体检全过，1.9 实测通过（展开链与 template.chain 声明一致）；认可发 v1（2026-09-29 11:46，admin，spec_hash 5a00e3f4…） |
| 8 | sync | C17 | 数据同步（运行态） | ✅ | 八段规格完成（runtimeOnly），10 项体检全过，1.9 实测通过（wf=97 v5, read=250000, write=250000, 5423 rows/s, 目标表 dwd_order_sync_test 数据验证一致）；认可发 v1（2026-09-29 11:46，admin，spec_hash 2ae8cd08…） |
| 9 | file_sync | C24 | 文件入仓执行（运行态） | ✅ | 八段规格完成（runtimeOnly），10 项体检全过，1.9 实测通过（wf=98 v2, rows_read=5, rows_written=5, 目标表 dwd_file_sync_test 数据验证一致）；认可发 v1（2026-09-29 11:46，admin，spec_hash 76208dfe…） |

### M-B2 ETL/计算类（9）

| # | type | 编号 | 名称 | 状态 | 认可记录 |
|---|---|---|---|---|---|
| 10 | sql | C11 | SQL | ✅ | 八段规格完成经用户确认（params=5 / exports=5 / lineage=2 / conditions=1）；认可发 v1（2026-09-29 13:05，admin，spec_hash 10fab62e…） |
| 11 | shell | C12 | Shell | ✅ | 八段规格完成经用户确认（params=2 / exports=1）；认可发 v1（2026-09-29 13:05，admin，spec_hash 6c9e0a25…） |
| 12 | python | C13 | Python | ✅ | 八段规格完成经用户确认（params=4 / exports=1）；认可发 v1（2026-09-29 13:05，admin，spec_hash 90580834…） |
| 13 | ssh | C14 | SSH 脚本 | ✅ | 八段规格完成经用户确认（params=3 / exports=1 / conditions=1）；认可发 v1（2026-09-29 13:05，admin，spec_hash c568e8ee…） |
| 14 | procedure | C15 | 存储过程 | ✅ | 八段规格完成经用户确认（params=4 / exports=2 / lineage=2）；认可发 v1（2026-09-29 13:05，admin，spec_hash ff1ec82d…） |
| 15 | http | C16 | HTTP | ✅ | 八段规格完成经用户确认（params=8 / exports=2 / conditions=2）；认可发 v1（2026-09-29 13:05，admin，spec_hash 375b1244…） |
| 16 | file | C22 | 文件读取 | ✅ | 八段规格完成经用户确认（params=16 / exports=3 / lineage=2 / conditions=3）；认可发 v1（2026-09-29 13:05，admin，spec_hash 9906842b…） |
| 17 | assert | C25 | 数据校验 | ✅ | 八段规格完成经用户确认（params=8 / exports=2 / lineage=2 / conditions=2）；认可发 v1（2026-09-29 13:05，admin，spec_hash e09b85b3…） |
| 18 | notify | C26 | 通知 | ✅ | 八段规格完成经用户确认（params=6 / exports=2 / conditions=1）；认可发 v1（2026-09-29 13:05，admin，spec_hash 80b277ac…） |

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

## 5. 前端入口路径

| 入口 | 路由 | 组件 | 用途 |
|---|---|---|---|
| 画布/palette | `/dag` | TaskCenterView → GraphWorkbench | 拖拽组件到画布编排工作流 |
| 基线化工作台 | `/meta/baseline` | BaselineWorkbenchView | 底稿编辑/八项体检/1.9 实测记录/认可发 v1 |
| 组件设计器 | `/meta/components/design/:type?` | ComponentDesignView | M1 四 Tab 组件设计器（基本信息/端口/表单字段/dropPolicy），**非**八段 DSL 编辑入口 |
| 组件目录 | `/meta/components` | ComponentCatalogView | 组件只读清单 |

> **注记（2026-09-29 勘误）**
> 1. **路由为 hash 模式**（vue-router `createWebHashHistory`），上表路由的实际 URL 带 `#` 前缀，形如 `/#/meta/baseline`、`/#/meta/components/design/:type?`、`/#/dag?doc=<工作流id>`。
> 2. **两个「设计器」不要混淆**：八段 DSL 编辑器（EightSectionEditor，`datara-web/src/components/baseline/EightSectionEditor.vue`）位于**基线化工作台 `/#/meta/baseline`** 选中组件后的设计区（M-B0 交付）；而 `/#/meta/components/design/:type` 是 **M1 时期的四 Tab 组件设计器**（基本信息/端口/表单字段/dropPolicy，服务用户自建组件的草稿编辑/冻结/发布闸门），并非八段 DSL 的编辑入口。
> 3. §0 所记 catalogHash=83929cf7c3c5c660 为当日快照存档（标注「随代码演进」，原值保留不改）；2026-09-29 executionModel 口径修正重导后的最新快照 hash 为 `9f5ab910a66f3392`（以 `scripts/export_dag_catalog.py` 输出为准）。

**Palette 分组**（dag profile）：
- 「数据计算」：sql, shell, python, ssh, procedure, http, file, assert
- 「通用」：notify
- 「逻辑控制」：start, end, conditions, switch, fork, join, merge, delay, dependent, loop
- 「数据同步」：src_base_orch, tgt_base_orch, file_sync_orch, endpoint_select, field_map, field_map_union, condition_set
- 「流处理」：stream_input, stream_fuse, stream_output, page_board
- 「变量」：variable
- 「运维/自检」：smoke
- 「模板」：demo_pipeline

## 6. M-B0 基建交付清单（2026-09-28）

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

## 7. 修订轮次上线（2026-09-30）

已发版组件不再「基线化一次性」：published 底稿锁定（保存 409/6002），修订走「复制上版开新轮 → 手动认可发 vN」闭环。

| 项 | 说明 |
|---|---|
| 开修订 | `POST /components/{type}/baseline/redraft`（design_component 权限）：published→designing，底稿复制最新已发版 spec，draft_rev 连续递增不重置；修订期间 registry 持续供给已发版本 |
| 放弃修订 | `POST /components/{type}/baseline/discard_draft`：底稿重置回最新已发版，status 回 published（修订改动丢弃） |
| 认可发版 | publish 分型：修订中发 v(N+1)，上一版在 t_component_version 永久留档（多行 published）；未开修订 409 提示先开轮 |
| 状态判定 | 不新增状态枚举：修订中 = `status=designing && publishedVersion>0`（progress 行下发 publishedVersion） |
| 前端三态 | 工作台保存栏：published 态只读（.ro）+「复制 vN 开修订」入口；修订中「保存底稿 / 放弃修订 / 认可发 vN+1」+ 紫徽标；目录页蓝徽标「修订中（vN 已发）」 |
| 1.9 实测 | 浏览器回归 15/15 + API 全链探针 11/11（redraft→改底稿→体检→publish v2→versions [2,1] 双留档→discard 回滚）；sql 组件实测发至 v2，其余 17 组件 v1 不变 |

设计全文：`docs/superpowers/specs/2026-09-30-baseline-revision-design.md`（含 R1/R2/R3 缺陷修复与决策记录 D1-D4）。
