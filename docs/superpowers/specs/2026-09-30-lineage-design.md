# 血缘关系三层汇总与前端呈现设计（表级 + 字段级）

* 日期：2026-09-30

* 状态：**已实施（2026-09-30，批次一 commit 39fa045 + 批次二前端 5-8 任务完成，批次二待 commit）**；设计裁定已经用户确认（设计态存储=现表加 src\_type；SELECT\*/全列映射=设计态只落表级；非 SQL 执行器/流处理=P1 声明 opaque；前端按 A-D 分期）。实施结果见 §6

* 关联：组件基线化 spec（2026-09-30-baseline-revision-design.md）、DAG与组件综合优化实施计划 §11

## 1. 背景与目标

血缘需求两个深度：**表级**（`{ds}.{db}.{table} → {ds}.{db}.{table}`）与**字段级**（`to_field ← from_field` + transform）。血缘连接定义在 DAG 工作流各类组件（同步编排 / ETL / 流处理 / 逻辑控制）的配置里。目标：

1. 设计态：从工作流定义的节点 config 静态解析血缘（发布即得，无需运行）；
2. 运行态：沿用既有执行期采集（已建成）；
3. 汇总：design ∪ runtime 统一去重、来源标记，形成全量血缘图谱；
4. 呈现：前端表级图谱增强 + 字段级图上可视化 + 实例追溯模式化。

## 2. 现状（已核实）

### 2.1 三套血缘资产并存

| 资产       | 载体                                                                                                        | 双深度       | 状态                    |
| -------- | --------------------------------------------------------------------------------------------------------- | --------- | --------------------- |
| S1 运行态采集 | worker/executors/sql.py:172→collect\_sql\_lineage；sync.py:514→collect\_sync\_lineage；worker/lineage.py 落库 | 表级+字段级均建成 | ✅ 在跑                  |
| S2 声明级   | spec.lineage.assets（role/pick/assetType）+ baseline.py:676-731 lineage-decl 与 /lineage/graph               | 仅节点无边     | stub（定位=组件能力画像，不参与汇总） |
| S3 设计态配置 | 节点 config（src/tgt 表 key、columnMap、sql\_text）                                                              | 天然可到字段级   | ❌ 从未解析（主缺口）           |

### 2.2 既有运行态能力（不重建）

* 模型 models.py:375-427：t\_lineage\_edge（uk：wf\_code/instance\_id/node\_id/stmt\_no/from\_table/to\_table/tmp\_flag）+ t\_lineage\_field（edge\_id/to\_field/from\_table/from\_field/transform）

* sqlparser.py：sqlglot MySQL 纯函数，INSERT..SELECT / INSERT..VALUES / CTAS / UPDATE；SELECT \* 不产字段级

* api/lineage.py：/lineage/tables、/lineage/fields、/lineage/stats、/lineage/trace

* 前端 LineageView\.vue（/meta/lineage）：双 level 切换、direction/depth 前端过滤、字段级侧栏弹层、?table= / ?instance=\&node= 深链

### 2.3 组件解析能力矩阵（35 组件）

| 组件类    | 组件                                                                               | 表级来源                               | 字段级来源                                        |
| ------ | -------------------------------------------------------------------------------- | ---------------------------------- | -------------------------------------------- |
| 同步编排   | sync / src\_base\_orch / tgt\_base\_orch / endpoint\_select / condition\_set     | config src/tgt 表 key 直读            | columnMap 非空→映射；留空→只落表级                      |
| 同步编排   | field\_map / field\_map\_union                                                   | 拓扑前驱输入表                            | columnMap（fmSrcIndex/fmTgtIndex 定向，union 反向） |
| 文件同步   | file\_sync\_orch                                                                 | 文件↔表边（assetType=file）              | 无                                            |
| ETL    | sql                                                                              | sql\_text → 复用 parse\_sql\_lineage | 非星号投影+transform；SELECT \* 降级表级               |
| ETL/外部 | python / shell / ssh / http / procedure / file / notify                          | opaque（不产边）                        | opaque                                       |
| 流处理    | stream\_input / stream\_fuse / stream\_output / page\_board                      | P1 opaque（topic↔表契约后置）             | 无                                            |
| 逻辑控制   | start/end/fork/join/merge/switch/conditions/delay/loop/dependent/variable/assert | 血缘穿透（拓扑自然连通）                       | 无                                            |

### 2.4 前端短板（五项）

F1 全量拉取+前端裁剪（depth 硬编码≤3，无全链）；F2 字段级无图上呈现（仅侧栏弹层）；F3 无面包屑/以此为中心/一键全链高亮；F4 实例追溯无独立 UI；F5 tmp 表与来源边无视觉区分。

## 3. 方案

### 3.1 口径

* 表级边：`{ds}.{db}.{table} → {ds}.{db}.{table}`；字段级边挂在表级边下（to\_field ← from\_field + transform）

* 来源维度 `src_type ∈ {runtime, design}`：runtime=执行事实（最准），design=配置静态解析（发布即得）；设计态行约定 instance\_id=0、node\_id=物理节点 id、stmt\_no=0

### 3.2 P1 后端：设计态解析器与落库

* 新增 `datara-backend/common/lineage_extract.py`（纯函数，风格对齐 sqlparser.py）：
  `extract_wf_lineage(nodes, edges, wf_code) -> {table_edges, field_edges, opaques}`，按上矩阵分派：

  * sql：取 config.sql\_text → parse\_sql\_lineage（设计/运行同解析器，口径天然一致）

  * 同步编排：ResourcePick（srcDsKey/srcTableKey/tgtDsKey/tgtTableKey）→ 表级；columnMap 非空 → 字段级

  * field\_map/union：沿 DAG 拓扑回溯前驱输入表 + columnMap（含 union 反向）→ 字段级

  * file\_sync\_orch：文件↔表边；控制流：跳过；python/shell/流处理：记 opaque

* 触发：工作流定义保存与发布时重算该定义血缘（delete-then-reinsert，幂等：先删该 wf\_code 的 design 行再插）；提供按需重算端点 `POST /lineage/redesign/{wfCode}`

### 3.3 P2 后端：汇总与聚合端点

* 迁移：t\_lineage\_edge / t\_lineage\_field 各加 `src_type VARCHAR(16) NOT NULL DEFAULT 'runtime'`；uk 不变（instance\_id=0 即设计态）；既有查询端点全部语义不变（默认只看 runtime 或全量，行为向后兼容）

* `GET /lineage/graph` 重写（替换 baseline.py 中 stub）：

  * 入参：`level=table|field`、`source=all|design|runtime`、`wfCode`、`table`（中心表）、`direction=upstream|downstream|both`、`depth`（0/空=全链，环检测）、`limit`

  * 逻辑：design ∪ runtime 边按 fq 表聚合去重；中心表给定时做图扩散截取；返回：
    `{nodes:[{fq, ds, table, tmpFlag, sources:[...], wfs:[...]}], edges:[{from, to, level, sources, refs:[{wfCode, nodeId, stmtNo?, transform?}]}], opaques:[{wfCode, nodeId, type}], truncated}`

  * lineage-decl 端点保留不动（单组件能力画像）

### 3.4 P3 前端：呈现改进（A-D）

* **A 表级图谱增强**：图数据改走 /lineage/graph 服务端扩散（去全量裁剪）；depth 支持 ∞ 全链；节点双击/右键「以此为中心」；顶栏面包屑（最近浏览表）；「影响分析」「源头追踪」一键全链展开+路径高亮；tmp 表虚线节点；详情抽屉升级（数据源、tmp 标记、上下游计数、最近采集、参与工作流）

* **B 字段级图上呈现**：选中表→切字段级渲染字段映射图（左来源表字段 / 右目标表字段 / field\_dep 连线 + transform 悬浮标签），数据复用 fieldLineage；现有弹层保留为「映射明细」页签；深链 `?level=field&table=x&field=y`

* **C 实例追溯模式化**：?instance=\&node= 进入时顶部实例上下文条（工作流/节点/状态/时间 + 回到全量切换），边标注 stmt\_no 次序

* **D 来源视觉体系**：运行态=实线、设计态=虚线、双源=实线+徽标；图例常驻；筛选器 design/runtime/all；仅设计态可达的表打「未验证」标记

* **E 性能兜底**：服务端 limit + 前端折叠提示（「已折叠 N 个，点击展开」）

### 3.5 分期

| 期   | 内容                                                                                                 |
| --- | -------------------------------------------------------------------------------------------------- |
| 批次一 | Task1 迁移加列 → Task2 lineage\_extract 解析器 → Task3 保存/发布触发落库 → Task4 /lineage/graph 聚合 + 第一批 1.9 部署冒烟 |
| 批次二 | Task5 前端 API+来源视觉 → Task6 字段级图上呈现 → Task7 表级交互增强 → Task8 实例追溯模式 → Task9 测试收口 + 第二批 1.9 部署实测 + 文档回写 |

## 4. 决策记录

* D1 设计态存储：**现表加 src\_type 列、instance\_id=0**（改动最小、查询兼容；否决独立表 UNION 方案）

* D2 SELECT \* / 同名全列映射：**设计态只落表级**，字段级诚实降级「待运行确认」（否决 information\_schema 实时补全）

* D3 非 SQL 执行器与流处理：**P1 声明 opaque 不采边**，P3+ 视需要尝试正则提取 SQL 字符串（否决本期强行采集）

* D4 声明级 spec.lineage 定位：保留为组件能力画像，不参与图谱汇总（lineage-decl 不动，/lineage/graph 从 stub 升级为聚合实现）

* D5 血缘解析器复用 parse\_sql\_lineage，设计态与运行态同一口径

## 5. 验收标准

1. 设计态：保存含 sql / 同步编排 / field\_map 节点的工作流后，无需运行即可在 /lineage/graph（source=design）看到表级边与 columnMap 字段级映射；重复保存幂等（无重复行）
2. 汇总：同一表既有 design 又有 runtime 边时，edges.sources 含双来源且去重；?source=runtime/ 筛选正确；?direction/depth 扩散正确（含 ∞ 全链不进环）
3. 兼容：既有 /lineage/tables、/fields、/stats、/trace 行为不变（回归通过）；LineageView 现有功能不回退
4. 前端：字段级图上呈现可用（连线+transform）；来源筛选与虚实线样式正确；实例追溯上下文条正确；vitest + vue-tsc 全绿
5. 1.9 实测：两批部署后 Playwright 全链回归（表级扩散→字段级图→来源筛选→实例追溯）+ API 探针（设计态落库→graph 聚合→幂等）全绿
6. 后端 pytest 全绿（解析器单测矩阵 + 聚合契约测试 + 迁移回归）

## 6. 实施结果（2026-09-30）

### 6.1 批次一（后端，commit 39fa045，14 文件 +2165/-71）

| 项 | 结果 |
| --- | --- |
| 存储 | t\_lineage\_edge / t\_lineage\_field 加 `src_type` 列（design/runtime，默认 runtime，存量零迁移） |
| 解析器 | `common/lineage_extract.py`：`extract_wf_lineage` 设计态解析纯函数（35 组件分派矩阵：sql→parse\_sql\_lineage；endpoint\_select 直读；field\_map/union 拓扑回溯；file\_sync\_orch 兜底 file: 边；模板/逻辑控制跳过；外部组件+流处理 opaque；信封层异常隔离） |
| 触发 | 保存/发布/删除/回滚四处 delete-then-reinsert 重算（instance\_id=0 设计态行）；`POST /lineage/redesign/{wfCode}`（design\_component 权限） |
| 聚合 | `GET /lineage/graph` 重写：design∪runtime 按 fq 聚合（sources/refs/opaques/truncated）+ 中心表 BFS 扩散（direction/depth=0 全链/limit 截断）+ seeds 超限截断 + 环检测 + file: 特判 |
| 验收 | 后端测试 269→327 passed（+58 用例：解析矩阵 34 + 设计态触发 11 + 聚合 14 等）；1.9 部署冒烟 graph 200（nodes=51 edges=46 opaques=35） |

### 6.2 批次二（前端 Task 5-8，待 commit）

* **Task 5 API+来源视觉**：fetchLineageGraph API 层；三态边视觉（runtime=实线蓝 dep / design=虚线琥珀 dep\_design / 双源=实线+「（双源）」徽标）；DataNode「未验」角标；来源筛选器三态+图例+截断提示；数据面切换（中心表下推+全连通域）；?table= 深链 matchCenter 归一（裸表名→fq）；竞态守卫 graphLoadSeq
* **Task 6 字段级图上呈现**：新增 `views/FieldLineageMap.vue`（左来源字段/右目标字段 + SVG field\_dep 连线 + transform 悬浮标签）+「映射图/映射明细」页签 + `?level=field&table=&field=` 深链定位 + 常量项/端点缺失过滤
* **Task 7 表级交互增强**：方向/深度参数下推服务端（∞ 全链=depth 0）；双击/右键「以此为中心」；面包屑最近浏览栈（上限 10）；⚡一键影响分析/源头追踪（depth=0 + dep\_focus 高亮边）；tmp 虚线节点；详情抽屉升级（数据源/tmp/来源/参与工作流/上下游计数）；影响数据独立补拉（impactSeq 守卫）
* **Task 8 实例追溯模式化**：trace 深链升级实例上下文条（工作流/节点/状态 pill/起止时间 + 回到全量）；边标注 stmt\_no 次序（annotateStmtNo #1 #2）；exitTrace 完整状态复位（changed 模式单发）；traceDetailSeq 守卫 + trace 模式交互禁用守卫
* **验收**：前端测试 368→415 用例全绿 + vue-tsc 0 错

### 6.3 已知取舍/遗留（如实记录）

| 项 | 说明 |
| --- | --- |
| 详情抽屉「最近采集」 | 未实现（后端 graph 节点契约无时间元数据，遵循不改后端约束；后续可补 createTime） |
| field 挂靠 | 仅首边（trace 展示可能错位，后端既有行为） |
| 常量化 | 边 kind magic string 未常量化 |
| 性能 | 全图模式 opaques 每请求重算（`_collect_opaques` 为缓存缝）；deriveImpact O(V×E)，200 边规模可接受、量大时建议预建邻接 Map |
| 测试缝 | rebuild 部分写库失败路径未测 |
| dep\_focus | 以 edge kind 承载瞬态高亮（后续叠加高亮需求建议 overlay 标记） |
| 端点形态归一（1.9 实测修复） | design 落数据源 **ID** 前缀（`9.ods_order→4.dwd_order_sync_test`，SQL 解析另含 datasource 配置名前缀成 `dw.9.a` 三段）/ runtime 落数据源**名**前缀或裸名（`ec_retail.ods_order→dwd_order_sync_test`），graph 原值聚合裂边（design 1 条 + runtime 16 条零合并）致双源永不命中——批次一测试全绿因夹具用了同形态 fq。已改聚合层 `_bare()` 裸表名归一（file: 特判保留、节点 fq=裸表名、ds 取首见原形态、refs/wfs/sources 归一合并），存量零迁移；1.9 复验双源命中（`ods_order→dwd_order_sync_test` sources=design+runtime，双源节点 2 个，筛选三态 12/1/12） |
| wf97 存量 save 422 | 存量文档 PUT save 触发新图校验闸门 422；设计态重算改走 `POST /lineage/redesign/{wfCode}` 兜底（功能正常） |

