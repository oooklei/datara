# 血缘遗留项收尾批次设计（2026-10-01）

状态：已实施（2026-10-01，Task 1-6 全部落地；两级审查 APPROVED；后端 pytest 334 passed / 前端 vitest 419 + vue-tsc 0 错；Task 5 评估结论见 §5）

## 1. 背景与目标

血缘三层汇总 9 任务已全部收口（批次一 39fa045 / 批次二 2cfe942，1.9 实测通过）。
本批次处理 §6.3 遗留表中可低风险落地的项，属收尾优化，不引入新功能面：

| # | 遗留项 | 处置 |
| --- | --- | --- |
| 1 | 详情抽屉「最近采集」 | 实现（后端补时间元数据 + 前端链路） |
| 2 | deriveImpact O(V×E) | 实现（预建邻接 Map，O(V+E)） |
| 3 | magic string 未常量化 | 实现（后端 SRC_TYPE/file: 前缀统一常量） |
| 4 | rebuild 部分写库失败路径未测 | 补测试 |
| 5 | field 挂靠仅首边 | 先评估出结论（可能不改码） |

非目标：wf97 存量 save 422（已有 redesign 兜底）、dep_focus overlay 化、前端边 kind 常量化、_collect_opaques 缓存化。

## 2. Task 1：详情抽屉「最近采集」

**后端**（api/lineage.py GET /lineage/graph）：
- 节点新增 `lastCollected: string | null`：该节点所有聚合行（design+runtime，与 /lineage/stats 的 lastTime 同口径）`create_time` 的 max，经 `fmt_dt` 序列化（None → null，缺数据不硬造）。
- 实现：node_acc 聚合时随行累积 max（table 级用边行、field 级用父边行），不新增查询，O(E) 单遍。

**前端**（数据驱动，Inspector.vue 零改动）：
- lineageApi.ts：graph node 类型补 `lastCollected?: string | null`。
- lineageUtils.ts buildLineageGraphDoc：透传至 `node.data.lastCollected`（GNode data 类型最小扩展）。
- lineage.ts lineageRelated：存在时追加关联项 `最近采集 {lastCollected}`；缺失不加。
- 已确认：Inspector.vue related 区按 schema.related 产出的 `{text,color?}` 数据驱动渲染（155 行瘦身版 L128-135），无需触碰该文件（其为 M 状态他线重构文件，严禁纠缠）。

## 3. Task 2：deriveImpact 预建邻接 Map

lineageUtils.ts deriveImpact 现为每节点全行扫描+shift（O(V×E)）。改为一次遍历预建
adjOut/adjIn 邻接 Map + visited Set 遍历，O(V+E)。对外 ImpactSubgraph 契约与行为语义完全不变，以现有测试锚定。

## 4. Task 3：后端常量化

- common/lineage_extract.py 顶部定义 `SRC_TYPE_DESIGN = "design"`、`SRC_TYPE_RUNTIME = "runtime"`、`FILE_NAME_PREFIX = "file:"`。
- api/lineage.py（src_type == "design" 三处、_bare/_split_fq 的 "file:" 前缀）与 lineage_extract.py 内部字面量替换为常量；api 侧从 common.lineage_extract 导入。
- 不动：common/db.py 迁移默认值字面量、Query pattern 校验字面量、测试断言字面量（测试即真值锚）、worker/ 侧（runtime 值由列默认保证）。

## 5. Task 5：field 挂靠仅首边评估（结论回写处）

现状：rebuild/worker 落库时 LineageField.edge_id 挂到同 (from,to) 表对的首条表级边（edge_by_pair.setdefault）。
评估维度：① 错位场景精确刻画（同表对多语句 / 多实例时 /fields、/trace 可见性）；② graph 聚合是否免疫
（field 级按字段行自身表对分组，L291-292 注释已声明不复现挂靠）；③ 修复成本（挂靠键改 (wf_code,node_id,stmt_no) 的 schema/查询面）；④ 建议（维持现状 or 修复 + 理由）。

> 评估结论：**已完成（基于 api/lineage.py、worker/lineage.py、common/models.py 及两测试文件实读）**
> ① 错位场景（design 成因，rebuild L494-496 `edge_by_pair.setdefault` 跨语句/跨节点按表对挂首边）：同 wf 存在 ≥2 条同 (from,to) 表级边（不同 node_id 或 stmt_no，如同节点多条 INSERT..FROM 同源同目标、或两节点产同表对）且该表对有字段时，字段行全挂首边。后果：/fields **无损**（输出仅 target/from/transform 且按 target+src 去重；首边必过 wf/to 过滤，uk_lineage 保证其 (wf,node,stmt,from,to) 键唯一、不被 _latest_edges 去重）；/trace（design instance_id="0" 共享）字段全归首边、真实产出语句/节点的边 fields 为空，node_id 过滤视角误导为"该节点无字段映射"；/graph field 级 refs 仅/错记首边 (wf,node,stmt)。runtime 成因基本不存在：worker _collect L210-214 字段按语句内 edge_ids 精确挂边，仅常量/CTE 来源兜底 first_edge（限同 stmt）；多实例各挂各实例边，旧字段随旧实例被"最新实例"口径隐藏属声明语义非缺陷。
> ② graph 免疫性：field 级按字段行自身 (from_table,from_field,bare(to),to_field) 分组（L302-306），拓扑/节点/sources/tmp 免疫；但 refs 取父边 (wf,node,stmt)（L328-330），design 错挂时 refs 归错或缺。/tables 纯表级边不涉字段，免疫；/stats fieldCount 计最新边上的字段行，design 首边存活，计数不丢。
> ③ 修复成本：零 schema 迁移。_f_edge 增携带 node_id/stmt_no（调用点 endpoint L242-246、field_map L318-322、sql L359 + _fkey 去重键）；rebuild 挂靠键改 (node_id,stmt_no,from,to) 并保留同表对兜底（防 CTE/常量字段变孤儿被跳过）；存量 design 行经 save/publish 或 POST /lineage/redesign 重算自然收敛，runtime 行无需迁移。查询面（/fields、/trace、graph refs）走 edge_id join 自动正确；uk_field(edge_id,…) 不阻同字段挂多边，/fields 呈现不变。估 0.5-1 人日含测试。
> ④ 建议：**建议修复（零迁移、低成本），优先级低**。影响面仅 design /trace 与 graph refs 的归属展示（无 /fields 丢数、无拓扑影响），触发条件（同 wf 同表对多语句/多节点 + 字段解析）概率低；若近期不动，维持现状风险可控。
> 未验证：存量库中同表对多语句工作流实际占比；修复后同字段挂多边对 /stats fieldCount 口径的影响。

## 6. 验收与执行约定

- 后端 pytest 全绿（基线 329 + 新增）；前端 vitest 全绿（基线 415 + 新增）+ vue-tsc 0 错。
- 执行方式：子代理驱动（implementer → spec 审查 → 质量审查 → 修复回环）；并行分派后端/前端/评估三路（文件面无交叠）。
- 收口：两级审查通过 → 全量回归 → commit（严格只 add 本任务组文件，均为干净文件，无外科手术需要）→ 文档回写（本 spec 状态、§6.3 遗留表勾销）→ 1.9 部署复验（涉及聚合端点：docker cp + py_compile + 五后端重启 + graph 探针验 lastCollected）。
- 工作区纪律：大量 M-B2/I12 历史未提交改动，绝不整体 add；PowerShell 5.1（禁 &&、grep 用 Select-String、多行 python -c 改脚本文件）。
