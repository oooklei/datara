# 存储过程（C15）· type=`procedure`

> 基线化设计册 · 分组：M-B2 ETL/计算类 · 状态：🔵 designing（规格草案待确认）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写，未经用户确认的规格草案仅落第 1/2 节。

## 1. 语义分析

**执行模型**：dag-engine + worker executor（executors/procedure.py）。
**worker 执行器**：
- 数据源解析：param.datasource（名称）→ t_data_source；数字串兜底按 id
- 库选择：param.db（缺省数据源库名）
- 过程调用：CALL {procedure}({placeholders})
- IN 参数 %s 参数化传值；OUT 参数经会话变量 @out_{key} 转接后 SELECT 回读
- OUT 值注册输出参数 out_{key}；影响行数入 outputs.affected
- 连接超时：read_timeout=None（过程耗时不受 60s 限制）
**表单角色**：数据源选择 + 目标库 + 过程名 + 过程参数（IN/OUT）
**现状缺口**：summary 为函数。

## 2. 八项表单规格（草案）

### params（4 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| datasource | 数据源 | resource | | | dsTypes=[mysql,greatdb] | 按名称查 t_data_source，数字串兜底按 id |
| db | 目标库 | text | | | | 留空 = 数据源默认库 |
| procedure | 过程名 | text | | | | 存储过程名称 |
| args | 过程参数 | rows | | | | IN 传值 / OUT 回读 |

### inputs / outputs / conditions / constraints / exclusions / refs / exports

- **inputs**：空
- **outputs**：空
- **conditions**：空
- **constraints**：空
- **exclusions**：空
- **refs**：空（数据源引用经 resource 字段，不声明 upstream 域）
- **exports**（2 项）：

| key | from | type | desc |
|---|---|---|---|
| affected | output | number | 影响行数 |
| out_{key} | output | string | OUT 参数值（动态键） |

### lineage（血缘声明，执行类必填）

| role | pick | assetType | 说明 |
|---|---|---|---|
| source | datasource | datasource | 数据源引用 |
| target | datasource | datasource | 同数据源（过程调用落同库） |

**注**：存储过程执行器的读写端由数据源动态决定，声明级血缘以「数据源引用字段」为 pick 锚点。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.datasource（resource, pick） | params 段 | 平移；pick → refs 注记 |
| form.db（text） | params 段 | 平移 |
| form.procedure（text） | params 段 | 平移 |
| form.args（rows） | params 段 | 平移 |
| `summary: () => ...` 函数 | render.summaryRules 兜底模板 | 决策 2 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=4 / exports=2 / lineage=2）；summary 常量函数迁移至 render.summaryRules 兜底模板。

**前端入口**：`/dag` → GraphWorkbench（palette「数据计算」分组拖拽）；`/meta/baseline` → BaselineWorkbenchView（底稿编辑/体检/认可发 v1）。

**后端**：零改动，executor=procedure 消费键不变（executors/procedure.py）。

**体检**（10 项全过）：contract=dag-engine+binding executor=procedure；params 4 项完整；exports 2 项完整；lineage 数据源锚点完整。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

见 §2 lineage：声明级数据源锚点；存储过程 OUT 参数注册为输出参数 out_{key} 供下游引用。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| — | — | — | — | — |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
