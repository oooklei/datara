# 字段映射-联合（C36）· type=`field_map_union`

> 基线化设计册 · 分组：M-B1 同步类 · 状态：⏳ 1.9 实测通过（待认可发 v1）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写。

## 1. 语义分析

**执行模型**：直通配置节点（`PASSTHROUGH_TYPES`），自身不执行。目标表基准专用：多 schema 源表 → 目标表字段联合映射。
**worker 消费键**：`fieldMap→fieldMap`；`addSchemaFlag + srcSchemaField→strategy=src_flag + flagColumn`；`aggOperator：union_all→strategy=union / union_distinct→去重`（执行器 _STRATEGIES=union/src_flag/partition，sync.py:333）。
**cap 联动**：columnMap 六键同 field_map，但 fmSrcIndex=1、fmTgtIndex=0（输入顺序与复制映射相反：[0]=目标端表、[1]=源端探测表）。
**特殊语义**：记录来源标识列（src_schema）是系统追加列，**不在上游列域内**（原声明注释明确不设 dataScope，避免 F3 值域闸门误伤）——八段化后该语义以注记保留，refs 段不得为 srcSchemaField 声明 upstream 域。
**现状缺口**：srcSchemaField 带 showIf；`summary` 为函数；aggOperator 选项文案（union all 追加合并）。

## 2. 八项表单规格（草案）

### inputs（1 项）

| key | label | uiType | required | cap | 说明 |
|---|---|---|---|---|---|
| inputs | 输入（上游节点输出） | resource | | upstreamOutputs max=2 | 前两个为目标端表/源端探测表，配对顺序决定联合方向；**留空=拍平直通**（2026-10-01 由 ✓ 放宽，同 [field_map](./field_map.md)） |

### params（4 项）

| key | label | uiType | required | default | options / cap | 说明 |
|---|---|---|---|---|---|---|
| fieldMap | 字段映射（源字段 → 目标字段） | mapEditor | | | mode=columnMap（fmSrcIndex=1, fmTgtIndex=0） | 留空=同名全列 |
| addSchemaFlag | 记录来源标识列 | bool | | true | | 开启后每行落来源 schema 标识 |
| srcSchemaField | 标识列名 | text | | src_schema | | **系统追加列，非上游列域** |
| aggOperator | 聚合算子 | select | | union_all | union_all=追加合并 / union_distinct=合并去重 | 目标表基准第 4 步 |

### outputs（1 项）

| key | label | uiType | cap | 说明 |
|---|---|---|---|---|
| outputs | 输出 | resource | upstreamOutputs max=5 | 默认为映射后全字段 + 标识列 |

### conditions（1 条，替代 showIf）

| id | when | show |
|---|---|---|
| c-schema-flag | addSchemaFlag = true | srcSchemaField |

### constraints / exclusions / exports

均空。

### refs（0 条，显式注记）

srcSchemaField 不声明 upstream 引用域（系统追加列语义，见 §1）。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.inputs / form.outputs（upstreamOutputs） | inputs / outputs 段 | 决策 3 同 field_map |
| form.fieldMap（cap 六键，fmSrc/fmTgt 反向） | params 段 | 平移 |
| form.addSchemaFlag / srcSchemaField / aggOperator | params 段 | 平移；showIf → conditions |
| `summary: (d) => ...` 函数 | render.summaryRules（草案） | 决策 2 |
| 注释「dataScope 不声明」 | refs 段显式空注记 | 语义保留 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（inputs=1 / outputs=1 / params=4 / conditions=1）；fmSrcIndex=1/fmTgtIndex=0（与复制映射反向）；addSchemaFlag 控制 srcSchemaFlag 显示（showIf → conditions）；aggOperator 选项文案（union_all=追加合并 / union_distinct=合并去重）；srcSchemaField 系统追加列语义以 refs 空注记保留（不声明 upstream 域）；cap.columnMap 纯数据冻结。

**后端**：零改动，passthrough 节点；worker 执行器消费键 fieldMap/addSchemaFlag+srcSchemaField/aggOperator 不变（sync.py:333 _STRATEGIES=union/src_flag/partition）。

**体检**（10 项全过）：passthrough 豁免 executor；conditions 替代 showIf；refs 显式空注记合规；cap 可序列化；血缘豁免。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

直通配置节点不执行：血缘豁免。多 schema 源表→目标表的表级边由 sync 执行器（partition/src_flag 策略）落库。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| wf=99 v2 | endpoint_select → field_map_union → sync（250K） | ✅ field_map_union state=success，config 拍平正确（addSchemaFlag=true, aggOperator=union_all, srcSchemaField=src_schema）；sync read=250000 write=250000 | 直通节点配置拍平进执行节点；同步 250K 行实测通过 | 2026-09-28 |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
