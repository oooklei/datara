# SSH 脚本（C14）· type=`ssh`

> 基线化设计册 · 分组：M-B2 ETL/计算类 · 状态：🔵 designing（规格草案待确认）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写，未经用户确认的规格草案仅落第 1/2 节。

## 1. 语义分析

**执行模型**：dag-engine + worker executor（executors/ssh.py）。
**worker 执行器**：
- 两种节点寻址（互斥，execNodeTag 优先）：
  - execNodeTag（I7 标签路由）：t_ssh_node 中 enabled+online 且含该标签的节点按轮转起点排序逐个尝试；连接失败/不可达 → 转派下一节点；全部不可达 → failure
  - runtimeNode（原有）：param.runtimeNode（名称）→ t_runtime_node；纯数字兜底按 id
- 认证：cred "-----BEGIN" 开头按私钥内容（RSA/Ed25519/ECDSA 依次尝试），否则按密码明文；空凭证无认证连接
- 执行：远端 `cd {runtime_dir} && bash -s 2>&1`，脚本经 stdin 下发；stdout 逐行实时日志
- 输出：parse_kv_outputs(stdout_text)（键值对解析）
**表单角色**：执行节点标签选择 + 运行时节点选择 + 脚本内容编辑
**现状缺口**：runtimeNode 带 showIf + pick（不可序列化）；summary 为函数。

## 2. 八项表单规格（草案）

### params（3 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| execNodeTag | 执行节点标签 | select | | | | I7 标签路由，优先于 runtimeNode |
| runtimeNode | 运行时节点 | resource | | | | 按名称查 t_runtime_node，数字串兜底按 id（showIf → conditions） |
| script | 脚本内容 | text | | | | 远端 bash 脚本内容 |

### inputs / outputs / conditions / constraints / exclusions / refs / exports

- **inputs**：空
- **outputs**：空
- **conditions**（1 条，替代 showIf）：

| id | when | show |
|---|---|---|
| c-runtime-node | execNodeTag 为空 | runtimeNode |

- **constraints**：空
- **exclusions**：空
- **refs**：空（运行时节点引用经 resource 字段，不声明 upstream 域）
- **exports**（1 项）：

| key | from | type | desc |
|---|---|---|---|
| stdout | output | object | 解析后的键值对输出 |

### lineage（血缘声明，执行类必填）

| role | pick | assetType | 说明 |
|---|---|---|---|
| source | script | script | 脚本内容（无外部资产） |
| target | script | script | 脚本内容（无外部资产） |

**注**：SSH 执行器无外部数据资产，血缘豁免（脚本内容非数据资产）。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.execNodeTag（select） | params 段 | 平移 |
| form.runtimeNode（resource, showIf+pick） | params 段 | 平移；showIf → conditions；pick → refs 注记 |
| form.script（text） | params 段 | 平移 |
| `summary: () => ...` 函数 | render.summaryRules 兜底模板 | 决策 2 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=3 / exports=1 / conditions=1）；runtimeNode showIf → conditions（execNodeTag 为空时显示）；summary 常量函数迁移至 render.summaryRules 兜底模板。

**前端入口**：`/dag` → GraphWorkbench（palette「数据计算」分组拖拽）；`/meta/baseline` → BaselineWorkbenchView（底稿编辑/体检/认可发 v1）。

**后端**：零改动，executor=ssh 消费键不变（executors/ssh.py）。

**体检**（10 项全过）：contract=dag-engine+binding executor=ssh；params 3 项完整；conditions 替代 showIf；exports 1 项完整；血缘豁免。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

SSH 执行器无外部数据资产：血缘豁免。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| — | — | — | — | — |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
