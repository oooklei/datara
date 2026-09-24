# C7 续作锚点清单（SourceBasePanel / TargetBasePanel + schemas 端点）

> 生成时间：2026-09-21（会话 Lam）、生成者：Sisyphus（主实现 agent）
> 目的：本会话因**多次上下文压缩**导致逐字锚点反复失效，无法在不损坏代码的前提下继续盲 edit。
> 本文件是**唯一可靠的状态快照**。新会话的第一条指令 = 读本文件，然后按「剩余步骤」执行。
> 任何与本文件冲突的、来自"上一会话记忆"的说法，一律以本文件为准——本文件内容是逐字经工具结果验证过的。

---

## 0. 状态更新（2026-09-24 收口会话，重要）

> ⚠️ **本文件的顶层前提已经被核实证伪**。以下为本收口会话的最终判定
> （依据逐字工具结果，优先于下方所有旧推断）：

- **`source_base` / `target_base` 不是节点类型**。它们是 `sync_template` 组件的
  **模板模式**（`dag.ts:471-482`，`modes[].build = buildSyncChain('union'|'src_flag')`），
  拖入即物化为 start→sync→sql→end 节点链。**不存在按 node.type 分发这两个面板的节点**，
  因此 1.4 的「按 node.type 分发」推断不成立。
- TargetBasePanel.vue 在收口前是**全项目零引用的孤儿组件**；SourceBasePanel.vue 不存在。
- schemas 端点与前端 listSchemas **早已完成**：`datasource.py:758` `GET /datasources/{ds_id}/schemas`、
  `datasourceApi.ts:153` `listSchemas(dsId)`（含类型 `DatasourceSchema`）。旧 S5/S6 实际无需做。
- **收口动作（2026-09-24 已完成并验证）**：
  1. 新写 `panels/SourceBasePanel.vue`（源端可开拓新表，与 TargetBasePanel 对称）。
  2. 增强 `panels/TargetBasePanel.vue`：支持 `selectedId` 自解活跃节点、保存写回
     `target_center`/`target_carrier_field`、carrierField 移入 setup（删残留 options data）。
  3. `FloatLayer.vue` 接线 `@update`/`@close`：面板 emit('update') → 写回当前文档节点 data + markDirty；
     emit('close') → 关闭浮窗。
  4. `dag.ts` 顶层 `dagProfile.floats` 注册两个浮窗（`source_base`/`target_base`，
     propsOf 传 selectedId），经工具栏「更多 ⋯」打开。
  5. **验证**：`vue-tsc -b` exit 0；`vitest run` 21 文件 186 用例全通过。
  6. **运行时 UI 验证（18090/dpkg-web 与 8090/datara-web 均部署新 dist，浏览器实测收口）**：
     - 工具栏「更多 ⋯」下拉出现「源表基准 / 目标表基准」两条菜单项（dispatch 生效）。
     - TargetBasePanel：数据源下拉 8 项来自 API；选中 dpkg-mysql-dw → 探测返回
       datara_dw / dwd_order_detail / 15 列；保存写回 `target_center`+`target_carrier_field`，
       重开自动回填 + 自动重探（已验证）。
     - SourceBasePanel：数据源下拉 + 新表名输入 + 血缘载体字段；保存写回
       `source_center`+`source_new_table`，重开自动回填（已验证）。
     - 修复两个首版缺陷：① 面板重开时不回填已保存配置；
       ② SourceBasePanel 的 watch 在微任务中清掉回填的新表名（initialized 延至 nextTick）。
  7. **部署**：新 dist 同步到 8090（datara-web）与 18090（dpkg-web）两处文档根，容器重启后均生效。
- **新的分发宿主定论**：profile.floats 注册表（stream→StreamMetricsPanel、lineage→LineageStatsPanel
  同模式），非 GraphWorkbench 硬编码分支。

---

## 1. 已验证的磁盘事实（逐字经工具结果确认，可直接信任）

上会话反复出现「读到大锚点 → 上下文被压缩 → 锚点消失 → 重读」的死循环。多轮压缩后，
连"分发宿主是哪个文件"都无法可靠锚定。为避免在 **900+ 行的宿主文件**里做错锚 edit 留下损坏代码，
选择诚实停下并产出本续作清单。**新会话请直接从"剩余步骤"开始，不要重演探查循环。**

---

## 1. 已验证的磁盘事实（逐字经工具结果确认，可直接信任）

### 1.1 前端面板目录
```
目录：D:\需求\数据治理工具\Datara\datara-web\src\graph\workbench\panels\
确认存在 8 个 .vue（含新写的两个）：
  SourceBasePanel.vue    ← C7.1 交付物（源端独立表单面板）
  TargetBasePanel.vue   ← C7.2 交付物（目标表基准表单面板）
  LineageStatsPanel.vue / WfVarPanel.vue / VersionPanel.vue
  StreamMetricsPanel.vue / AiPanel.vue / LogPanel.vue / IssuePanel.vue
```
> ⚠️ 上会话最后可见证据显示：两个新面板**已写入磁盘**（TargetBasePanel 因"文件已存在"报错，
> SourceBasePanel 在另一次读中已被视为已存在）。**新会话先 glob 该目录确认两者都在，再决定**
> 是否需要补写。若都在：跳过 C7.1/C7.2 的写，直接做分发。

### 1.2 前端字段/表单宿主
```
D:\需求\数据治理工具\Datara\datara-web\src\graph\workbench\Inspector.vue   ← 931 行（上会话已全读）
  - 23: import RowsField from './fields/RowsField.vue'
  - 24: import DepsField from './fields/DepsField.vue'
  - Inspector 是按 Node.type 做「字段级」分发的宿主（kv-table / params-table / rows-field 等）
  - 注意：Inspector 是「字段分发」，不是「面板分发」。
```

### 1.3 面板分发宿主（关键歧义点 —— 新会话必须优先核实）
```
上会话的核心未决问题：source_base / target_base 两个 float 面板由哪个宿主分发。
已确认的事实：
  - GraphWorkbench.vue（1112 行）import Panel 列表（行 32-35）：IssuePanel / LogPanel / AiPanel / VersionPanel
  - 其中 openFloat 分发调用点：241（IssuePanel）、509（LogPanel）、515（VersionPanel）、828（AiPanel）
  - 另有 profiles/ 注册表模式：profiles/stream.ts → StreamMetricsPanel、
    profiles/lineage.ts → LineageStatsPanel（按 profile 注册面板）
  - GraphWorkbench.vue 的 import 块在 30-120 行；没有发现 source_base/target_base 的现成分发分支
```
**新会话第一件事**：在 `datara-web\src\graph\workbench\` 目录下 grep：
```
pattern: source_base|target_base|SourceBasePanel|TargetBasePanel|openFloat\(|'panels/
```
定位**真正的分发宿主文件**，读取其 import 块 + 分发分支区段（逐字锚点），再落 edit。
若找不到现成分发宿主，则按 1.4 的推断处理。

### 1.4 推断（未逐字验证，需新会话确认）
上会话最后残余证据指向：`SourceBasePanel` / `TargetBasePanel` 应由 **GraphWorkbench.vue**（或
Inspector.vue 的面板分发区）按 `source_base` / `target_base` node.type 分支分发。
为最小风险，新会话先核实分发宿主，再决定导入 + 分支放哪个文件。

### 1.5 后端
```
文件：D:\需求\数据治理工具\Datara\datara-backend\api\datasource.py   ← 592 行（上会话已全读/读尾部）
  - 592 行为文件末尾：return ok(True)   （/tmp-data DELETE 成功后）
  - 无 /schemas 清单端点 → 需在 592 行后追加
已有端点清单（14 个，逐字确认）：
  GET  /datasources（128）/ POST /datasources（152）/ PUT /datasources/{ds_id}（180）
  DELETE（209）/ POST /{ds_id}/test（228）/ GET /datasources/files（266）
  GET /{ds_id}/tree（278）/ GET /{ds_id}/meta（351）/ GET /{ds_id}/databases（392）
  GET /{ds_id}/databases/{db}/tables（410）/ GET /.../tables/{t}/columns（462）
  GET /{ds_id}/search（508）/ GET /tmp-data（563）/ DELETE /tmp-data/{tmp_id}（574）
```

### 1.6 后端 schemas 端点规格（C7.4）
在 `datasource.py` **592 行后**追加一个清单端点，source_base / target_base 通用：
```
GET /datasources/{ds_id}/schemas
  → 返回 { ok: True, schemas: [ { db: str, tables: [ { name, columns: [...] } ] } ] }
  （只读探表，复用既有 datasource tree/meta 探表机制；不写库）
```

### 1.7 前端服务
```
文件：D:\需求\数据治理工具\Datara\datara-web\src\services\datasourceApi.ts（或 datara-web\src\services\datasourceApi.ts）
上会话已确认其存在（约 150 行），未逐字读全。新会话需：
  - 确认文件名与实际路径
  - 追加 schemas 服务函数（与 1.6 对应），例如 listSchemas(dsId) → Promise<SchemasResp>
```

---

## 2. 剩余步骤（**已于 2026-09-24 收口会话全部执行完毕**）

> 全部完成并经 `vue-tsc -b`（exit 0）+ `vitest run`（21 文件 186 用例）验证。
> 详细结论见 §0 状态更新——原计划的前提被证伪后按真实分发机制实现。

- [x] **S1** glob `datara-web\src\graph\workbench\panels\*.vue` → SourceBasePanel 缺失 / TargetBasePanel 存在
- [x] **S2** grep 定位分发宿主 → 实为 `dagProfile.floats` 注册表（stream/lineage 同模式），非 GraphWorkbench 硬编码
- [x] **S3** 补写 `panels/SourceBasePanel.vue`（源端可开拓新表）
- [x] **S4** `dag.ts` import 两个面板 + `dagProfile.floats` 注册 2 个条目（propsOf 传 selectedId）
- [x] **S5** 核实现读过时：schemas 端点早已存在于 `datasource.py:758`，无需新增
- [x] **S6** 核实现读过时：`listSchemas` 早已存在于 `datasourceApi.ts:153`，无需新增
- [x] **S7** 类型校验收尾：`vue-tsc -b` exit 0 + `vitest run` 全绿；（附带 FloatLayer 事件接线，使面板 emit 生效）

## 3. 工程原则（新会话务必遵守）
1. **锚点不到位，不做 edit**：任何对既有 900+ 行文件的修改，必须先在本会话内逐字读到锚点原文。
2. **不重复探查循环**：读到一个锚点就立刻用掉它，不要攒着、不要为了"多确认一次"反复重读。
3. **诚实优先**：宁可停下交付状态报告，也不要盲写可能损坏代码的 edit。
4. **路径以本文件为准**：若发现路径大小写/拼写与本文件不同（如 Datara vs Datara），以 glob/grep 实际返回为准。
