# Python（C13）· type=`python`

> 基线化设计册 · 分组：M-B2 ETL/计算类 · 状态：🔵 designing（规格草案待确认）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写，未经用户确认的规格草案仅落第 1/2 节。

## 1. 语义分析

**执行模型**：dag-engine + worker executor（executors/python.py）。
**worker 执行器**：
- subprocess python 运行 `{tmp_dir}/{instance_id}/task_{task_id}.py`；exit 0 → success
- requirements 字段本期仅校验格式并打印日志提示，不做运行时安装（依赖预装归镜像层）
- 环境变量经 build_env 注入子进程（PYTHONUNBUFFERED=1 + param.env）
- 输出：parse_kv_outputs(stdout_text)（键值对解析）
**表单角色**：脚本内容编辑 + 环境变量键值表 + 依赖清单（仅校验/留痕）
**现状缺口**：requirementsHint 为 hint 字段（空 label）；summary 为函数。

## 2. 八项表单规格（草案）

### params（4 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| script | 脚本内容 | text | | | | Python 脚本内容 |
| env | 环境变量 | rows | | | | 键值表，注入子进程 |
| requirements | 依赖清单 | text | | | | requirements.txt 格式，仅校验/留痕 |
| requirementsHint | （说明条） | hint | | | | 固定文案：依赖需预装镜像层 |

### inputs / outputs / conditions / constraints / exclusions / refs / exports

- **inputs**：空
- **outputs**：空
- **conditions**：空
- **constraints**：空
- **exclusions**：空
- **refs**：空
- **exports**（1 项）：

| key | from | type | desc |
|---|---|---|---|
| stdout | output | object | 解析后的键值对输出 |

### lineage（血缘声明，执行类必填）

| role | pick | assetType | 说明 |
|---|---|---|---|
| source | script | script | 脚本内容（无外部资产） |
| target | script | script | 脚本内容（无外部资产） |

**注**：Python 执行器无外部数据资产，血缘豁免（脚本内容非数据资产）。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.script（text） | params 段 | 平移 |
| form.env（rows） | params 段 | 平移 |
| form.requirements（text） | params 段 | 平移 |
| form.requirementsHint（hint, 空 label） | params 段 hint 字段 | 平移；空 label → 固定文案 |
| `summary: () => ...` 函数 | render.summaryRules 兜底模板 | 决策 2 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=4 / exports=1）；requirementsHint 空 label → 固定文案；summary 常量函数迁移至 render.summaryRules 兜底模板。

**前端入口**：`/dag` → GraphWorkbench（palette「数据计算」分组拖拽）；`/meta/baseline` → BaselineWorkbenchView（底稿编辑/体检/认可发 v1）。

**后端**：零改动，executor=python 消费键不变（executors/python.py）。

**体检**（10 项全过）：contract=dag-engine+binding executor=python；params 4 项完整；exports 1 项完整；血缘豁免。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

Python 执行器无外部数据资产：血缘豁免。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| — | — | — | — | — |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
