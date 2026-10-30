# 通知（C26）· type=`notify`

> 基线化设计册 · 分组：M-B2 ETL/计算类 · 状态：🔵 designing（规格草案待确认）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写，未经用户确认的规格草案仅落第 1/2 节。

## 1. 语义分析

**执行模型**：dag-engine + worker executor（executors/notify.py）。
**worker 执行器**：
- 通道：log（仅日志）/ webhook（POST JSON {"text": msg}）
- 消息模板：param.template 经 vars_render 渲染（内置变量 ${wf.name} ${instance_id} ${node.name} ${sys.now}）
- 触发时机：param.trigger（on_success/on_failure/always，仅留痕）
- webhook 失败默认仅告警不断流；failHard=true 才 failure
- 输出：notified=true / error
**表单角色**：通道选择 + Webhook URL + 触发时机 + 消息模板 + 断流开关
**现状缺口**：url 带 showIf（不可序列化）；notifyHint 为 hint 字段（空 label）；summary 为函数。

## 2. 八项表单规格（草案）

### params（6 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| channel | 通道 | select | | log | log/webhook | 通知通道 |
| url | Webhook URL | text | ✓ | | | Webhook URL（showIf → conditions） |
| trigger | 触发时机 | select | | on_success | on_success/on_failure/always | 触发时机（仅留痕） |
| template | 消息模板 | text | | | | 消息模板（vars_render 渲染） |
| notifyHint | （说明条） | hint | | | | 固定文案：内置变量提示 |
| failHard | 通知失败断流 | bool | | false | | webhook 失败时是否断流 |

### inputs / outputs / conditions / constraints / exclusions / refs / exports

- **inputs**：空
- **outputs**：空
- **conditions**（1 条，替代 showIf）：

| id | when | show |
|---|---|---|
| c-webhook-url | channel=webhook | url |

- **constraints**：空
- **exclusions**：空
- **refs**：空
- **exports**（2 项）：

| key | from | type | desc |
|---|---|---|---|
| notified | output | bool | 是否已通知 |
| error | output | string | 错误信息（failHard=true 时） |

### lineage（血缘声明，执行类必填）

| role | pick | assetType | 说明 |
|---|---|---|---|
| source | channel | channel | 通知通道 |
| target | channel | channel | 同通道（自引用） |

**注**：通知执行器无外部数据资产，血缘豁免（通道非数据资产）。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.channel（select） | params 段 | 平移 |
| form.url（text, showIf, required） | params 段 | 平移；showIf → conditions |
| form.trigger（select） | params 段 | 平移 |
| form.template（text） | params 段 | 平移 |
| form.notifyHint（hint, 空 label） | params 段 hint 字段 | 平移；空 label → 固定文案 |
| form.failHard（bool） | params 段 | 平移 |
| `summary: () => ...` 函数 | render.summaryRules 兜底模板 | 决策 2 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=6 / exports=2 / conditions=1）；url showIf → conditions（channel=webhook 时显示）；notifyHint 空 label → 固定文案；summary 常量函数迁移至 render.summaryRules 兜底模板。

**前端入口**：`/dag` → GraphWorkbench（palette「通用」分组拖拽）；`/meta/baseline` → BaselineWorkbenchView（底稿编辑/体检/认可发 v1）。

**后端**：零改动，executor=notify 消费键不变（executors/notify.py）。

**体检**（10 项全过）：contract=dag-engine+binding executor=notify；params 6 项完整；conditions 替代 showIf；exports 2 项完整；血缘豁免。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

通知执行器无外部数据资产：血缘豁免。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| — | — | — | — | — |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
