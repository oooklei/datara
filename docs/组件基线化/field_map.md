# 字段映射-复制（C34）· type=`field_map`

> 基线化设计册 · 分组：M-B1 同步类 · 状态：⏳ 1.9 实测通过（待认可发 v1）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写。

## 1. 语义分析

**执行模型**：直通配置节点（`PASSTHROUGH_TYPES`），自身不执行；`fieldMap` 配置在派发拍平时合入 sys_exec 执行节点 param，worker 执行器（executors/sync.py:347）消费 `fieldMap` 做列映射搬运。
**UI 契约**：2 输入（[0]=源端表、[1]=目标端表，来自上游 endpoint_select 的 sourceRef/targetRef）+ flex 布局字段对照（mapEditor）+ 输入/输出选择。
**cap 联动**：`cap.mode=columnMap`（纯数据）声明列枚举来源：srcNodeType/tgtNodeType=endpoint_select、srcDsKey=srcDs、srcTableKey=srcTable、tgtDsKey=tgtDs、tgtTableKey=tgtTable、fmSrcIndex=0、fmTgtIndex=1——mapEditor 据此跨节点枚举源/目标列。**cap 本身可序列化，随声明冻结**。
**现状缺口**：无 showIf；`summary` 为函数。

## 2. 八项表单规格（草案）

### inputs（1 项）

| key | label | uiType | required | cap | 说明 |
|---|---|---|---|---|---|
| inputs | 输入（上游节点输出） | resource | | upstreamOutputs max=2 | 前两个为源端表/目标端表，顺序决定映射方向；**留空=拍平直通**（2026-10-01 由 ✓ 放宽：引擎 PASSTHROUGH 容忍空 inputs，wf97 v5 250K 行实测；required 声明曾致存量文档重存 422） |

### params（1 项）

| key | label | uiType | required | cap | 说明 |
|---|---|---|---|---|---|
| fieldMap | 字段映射（源字段 → 目标字段） | mapEditor | | mode=columnMap（六键如 §1） | 留空=同名全列映射 |

### outputs（1 项）

| key | label | uiType | cap | 说明 |
|---|---|---|---|---|
| outputs | 输出 | resource | upstreamOutputs max=5 | 默认为映射后全字段 |

### conditions / constraints / exclusions / refs / exports

均空。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.inputs（upstreamOutputs） | inputs 段 | **决策 3**：旧表单的 inputs/outputs 字段语义即节点数据面声明，归位 inputs/outputs 段（与端口声明统一） |
| form.fieldMap（mapEditor+cap） | params 段 | 平移（cap 纯数据原样） |
| form.outputs（upstreamOutputs） | outputs 段 | 同 inputs 迁移 |
| `summary: (d) => ...` 函数 | render.summaryRules（草案） | 同 endpoint_select 决策 2 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（inputs=1 / outputs=1 / params=1）；fieldMap 使用 mapEditor + cap.columnMap（六键：srcNodeType/tgtNodeType=endpoint_select、srcDsKey=srcDs、srcTableKey=srcTable、tgtDsKey=tgtDs、tgtTableKey=tgtTable、fmSrcIndex=0/fmTgtIndex=1）；cap 纯数据随声明冻结；summary 函数迁移至 render.summaryRules。

**后端**：零改动，passthrough 节点（PASSTHROUGH_TYPES），worker 执行器（executors/sync.py:347）消费 fieldMap 不变。

**体检**（10 项全过）：contract=passthrough 豁免 executor 绑定；inputs/outputs/params 段完整；cap 可序列化；summary 已规则化；conditions/constraints/exclusions/exports/refs 均空合规；血缘豁免。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

直通配置节点不执行：血缘豁免。字段级血缘由 sync 执行器成功后经 worker/lineage 落库（field_map 的映射关系是血缘数据源之一）。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| wf=97 v5 | endpoint_select → field_map → sys_exec_c6bdbfe4 | ✅ state=success，config 输出 params={} | 直通节点配置拍平进执行节点；同步 250K 行实测通过 | 2026-09-28 |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
