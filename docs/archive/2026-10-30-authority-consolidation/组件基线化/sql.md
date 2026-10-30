# SQL（C11）· type=`sql`

> 基线化设计册 · 分组：M-B2 ETL/计算类 · 状态：🔵 designing（规格草案待确认）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写，未经用户确认的规格草案仅落第 1/2 节。

## 1. 语义分析

**执行模型**：dag-engine + worker executor（executors/sql.py）。
**worker 执行器**：
- 数据源解析：param.datasource（名称）→ t_data_source；数字串兜底按 id
- 多语句分号拆分顺序执行：前置 pre → 主 sql → 后置 post；autocommit 逐语句提交
- 查询：row_count 全量计数 + result_preview 前 200 行；非查询/DDL：影响行数
- 连接池：按数据源 id LRU（maxsize=8），取用时 ping 自愈断连
- 变量占位已在 master 侧替换下发（param_resolved），worker 零解析
- 血缘采集（I5 F24 旁路）：仅已成功语句，失败/中断不阻断终态
**输出**：results（全语句摘要）/ row_count / result_preview / lineage_edges / lineage_fields
**表单角色**：数据源选择 + SQL 语句编辑 + 前置/后置 SQL + 库表侧栏选择器（点选插入）
**现状缺口**：sqlInsert 带 showIf + pick（不可序列化）；summary 为函数。

## 2. 八项表单规格（草案）

### params（5 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| datasource | 数据源 | resource | | | dsTypes=[mysql,greatdb] | 按名称查 t_data_source，数字串兜底按 id |
| sqlInsert | 库/表侧栏选择器 | mapEditor | | | | 点选插入，不替代手写（showIf → conditions） |
| sql | SQL 语句 | text | | | | 主 SQL 语句 |
| pre | 前置 SQL | text | | | | 主 SQL 前执行 |
| post | 后置 SQL | text | | | | 主 SQL 后执行 |

### inputs / outputs / constraints / exclusions / refs / exports

- **inputs**：空（无上游数据面声明）
- **outputs**：空（执行器产出统计键声明见 exports）
- **constraints**：空
- **exclusions**：空
- **refs**：空（数据源引用经 resource 字段，不声明 upstream 域）
- **exports**（5 项）：

| key | from | type | desc |
|---|---|---|---|
| results | output | array | 全语句摘要 |
| row_count | output | number | 主查询行数 |
| result_preview | output | object | 主查询预览（columns + rows） |
| lineage_edges | output | number | 血缘边数 |
| lineage_fields | output | number | 血缘字段数 |

### conditions（1 条，替代 showIf）

| id | when | show |
|---|---|---|
| c-sql-insert | datasource 非空 | sqlInsert |

### lineage（血缘声明，执行类必填）

| role | pick | assetType | 说明 |
|---|---|---|---|
| source | datasource | datasource | 数据源引用 |
| target | datasource | datasource | 同数据源（自引用，SQL 结果落同库） |

**注**：SQL 执行器的读写端由数据源动态决定，声明级血缘以「数据源引用字段」为 pick 锚点；字段级血缘由 worker/lineage 落库（I5 F24 旁路）。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.datasource（resource, pick） | params 段 | 平移；pick → refs 注记 |
| form.sqlInsert（mapEditor, showIf+pick） | params 段 | 平移；showIf → conditions；pick → refs 注记 |
| form.sql / pre / post（text） | params 段 | 平移 |
| `summary: () => ...` 函数 | render.summaryRules 兜底模板 | 决策 2 |
| page（查询结果预览 F61） | render.page 声明位 | 页面组件映射保留在前端 profile |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=5 / exports=5 / lineage=2 / conditions=1）；sqlInsert showIf → conditions（datasource 非空时显示）；summary 常量函数迁移至 render.summaryRules 兜底模板；page 声明位保留在前端 profile。

**前端入口**：`/dag` → GraphWorkbench（palette「数据计算」分组拖拽）；`/meta/baseline` → BaselineWorkbenchView（底稿编辑/体检/认可发 v1）。

**后端**：零改动，executor=sql 消费键不变（executors/sql.py）。

**体检**（10 项全过）：contract=dag-engine+binding executor=sql；params 5 项完整；conditions 替代 showIf；exports 5 项完整；lineage 数据源锚点完整。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

见 §2 lineage：声明级数据源锚点 + 运行态字段级血缘（worker/lineage I5 F24 旁路）双层结构。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| — | — | — | — | — |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
