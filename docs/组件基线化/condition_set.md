# 条件设定（C35）· type=`condition_set`

> 基线化设计册 · 分组：M-B1 同步类 · 状态：⏳ 1.9 实测通过（待认可发 v1）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写。

## 1. 语义分析

**执行模型**：直通配置节点（`PASSTHROUGH_TYPES`），自身不执行。源表数据筛选条件（默认全量）+ 增量列。
**worker 消费键**：`filterExpr→readerWhere`（连接型拼入 SQL WHERE，与增量条件 AND 组合括号包裹；文件型按 `列 op 值` 逐行过滤）；`incrementalColumn + incrementalExpr→incremental {column, expr}`（sync.py:342-346 平铺键兼容）。
**值域闸门**：`incrementalColumn` 带 `dataScope: 'upstream-columns'`（F3：增量列必须是上游真实存在的列）——八段化后归位 refs 段（scopes 含 upstream）。
**现状缺口**：incrementalExpr 带 showIf；`summary` 为函数。

## 2. 八项表单规格（草案）

### inputs（1 项）

| key | label | uiType | required | cap | 说明 |
|---|---|---|---|---|---|
| inputs | 输入（上游节点输出） | resource | | upstreamOutputs max=3 | 筛选对象；**留空=拍平直通**（2026-10-01 由 ✓ 放宽，同 [field_map](./field_map.md)） |

### outputs（1 项）

| key | label | uiType | cap | 说明 |
|---|---|---|---|---|
| outputs | 输出（上游节点输出） | resource | upstreamOutputs max=3 | 下游可见的输出登记 |

### params（3 项）

| key | label | uiType | required | default | 说明 |
|---|---|---|---|---|---|
| filterExpr | 筛选条件（WHERE） | text(multiline) | | | 留空=全量同步；如 `create_time > ${last_sync_time} AND status = 1` |
| incrementalColumn | 增量列名 | text | | | 留空=全量同步；必须是上游真实存在的列（refs.upstream） |
| incrementalExpr | 增量条件表达式 | text | | | 如 `${yyyyMMdd-1}`，运行时变量替换后 > 比较 |

### conditions（1 条，替代 showIf）

| id | when | show |
|---|---|---|
| c-incr-expr | incrementalColumn 非空 | incrementalExpr |

### refs（1 条）

| field | scopes | 说明 |
|---|---|---|
| filterExpr | wf, time | WHERE 中允许工作流变量与时间变量引用（`${last_sync_time}`、`${yyyyMMdd-1}`） |
| incrementalExpr | time | 增量表达式允许时间变量 |

**注意**：incrementalColumn 不声明变量域（它是列名，值域由 upstream-columns 闸门约束，语义保留为「约束即 refs 的 upstream 列域」——落 constraints 注记或实现时以 refs.scope=upstream-columns 扩展表达，见 §3 决策 4）。

### constraints / exclusions / exports

均空。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.inputs / form.outputs（upstreamOutputs） | inputs / outputs 段 | 决策 3 |
| form.filterExpr（multiline） | params 段 | 平移 |
| form.incrementalColumn（dataScope: upstream-columns） | params 段 + refs 注记 | **决策 4**：dataScope 的 upstream-columns 语义映射为 refs.scopes 扩展值（upstream-columns），F3 值域闸门消费点不变 |
| form.incrementalExpr（showIf） | params 段 + conditions | showIf → conditions |
| `summary: (d) => ...` 函数 | render.summaryRules（草案） | 决策 2 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（inputs=1 / outputs=1 / params=3 / conditions=1 / refs=2）；filterExpr 多行 text；incrementalColumn 值域闸门语义映射为 refs.scopes 含 upstream-columns（决策 4）；refs 含 wf/time scopes（filterExpr 允许工作流变量与时间变量引用 `${last_sync_time}` / `${yyyyMMdd-1}`）；incrementalExpr showIf → conditions；summary 函数迁移至 render.summaryRules。

**后端**：零改动，passthrough 节点；worker 消费键 filterExpr→readerWhere / incrementalColumn+incrementalExpr→incremental 不变（sync.py:342-346）。

**体检**（10 项全过）：passthrough 豁免 executor；refs wf/time scopes 合规（决策 4 dataScope 映射）；conditions 替代 showIf；血缘豁免。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

直通配置节点不执行：血缘豁免。增量条件参与运行态血缘过滤语义（readerWhere 落血缘记录）。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| wf=97 v5 | endpoint_select → field_map → condition_set → sys_exec_c6bdbfe4 | ✅ state=success，config 输出 params={} | 直通节点配置拍平进执行节点；同步 250K 行实测通过 | 2026-09-28 |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
