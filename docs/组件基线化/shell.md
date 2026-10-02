# Shell（C12）· type=`shell`

> 基线化设计册 · 分组：M-B2 ETL/计算类 · 状态：🔵 designing（规格草案待确认）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写，未经用户确认的规格草案仅落第 1/2 节。

## 1. 语义分析

**执行模型**：dag-engine + worker executor（executors/shell.py）。
**worker 执行器**：
- bash 运行 `{tmp_dir}/{instance_id}/task_{task_id}.sh`；exit 0 → success
- stdout 逐行实时日志；退出码非 0 → failure
- 环境变量经 build_env 注入子进程
- 输出：parse_kv_outputs(stdout_text)（键值对解析）
**表单角色**：脚本内容编辑 + 环境变量键值表
**现状缺口**：summary 为函数。

## 2. 八项表单规格（草案）

### params（2 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| script | 脚本内容 | text | | | | bash 脚本内容 |
| env | 环境变量 | rows | | | | 键值表，注入子进程 |

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

**注**：Shell 执行器无外部数据资产，血缘豁免（脚本内容非数据资产）。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.script（text） | params 段 | 平移 |
| form.env（rows） | params 段 | 平移 |
| `summary: () => ...` 函数 | render.summaryRules 兜底模板 | 决策 2 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=2 / exports=1）；summary 常量函数迁移至 render.summaryRules 兜底模板。

**前端入口**：`/dag` → GraphWorkbench（palette「数据计算」分组拖拽）；`/meta/baseline` → BaselineWorkbenchView（底稿编辑/体检/认可发 v1）。

**后端**：零改动，executor=shell 消费键不变（executors/shell.py）。

**体检**（10 项全过）：contract=dag-engine+binding executor=shell；params 2 项完整；exports 1 项完整；血缘豁免。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

Shell 执行器无外部数据资产：血缘豁免。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| — | — | — | — | — |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
