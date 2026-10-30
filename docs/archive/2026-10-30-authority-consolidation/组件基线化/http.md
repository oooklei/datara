# HTTP（C16）· type=`http`

> 基线化设计册 · 分组：M-B2 ETL/计算类 · 状态：🔵 designing（规格草案待确认）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写，未经用户确认的规格草案仅落第 1/2 节。

## 1. 语义分析

**执行模型**：dag-engine + worker executor（executors/http.py）。
**worker 执行器**：
- 请求：method（缺省 GET）/ headers（dict 或 [{key,value}] 表）/ body / bodyType(json|form)
- 成功码校验：successCodes（默认 2xx，支持 2xx/3xx 通配与显式码）
- 响应提取：extract（{输出名: 点路径} 或行表）；点路径 a.b[0].c 从 JSON 响应取子集
- 超时：param.timeout（秒，默认 30）
- 输出：status_code + 提取名
**表单角色**：URL + 方法 + 请求头 + 请求体 + 成功码 + 响应提取 + 超时
**现状缺口**：bodyType/body 带 showIf（不可序列化）；summary 为函数。

## 2. 八项表单规格（草案）

### params（8 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| url | URL | text | | | | 请求 URL |
| method | 方法 | select | | GET | GET/HEAD/POST/PUT/DELETE/PATCH | HTTP 方法 |
| headers | 请求头 | rows | | | | 键值表 |
| bodyType | 请求体类型 | select | | json | json/form | 请求体类型（showIf → conditions） |
| body | 请求体 | text | | | | 请求体内容（showIf → conditions） |
| successCodes | 成功状态码 | text | | 2xx | | 支持 2xx/3xx 通配与显式码，逗号分隔 |
| extract | 响应提取 | rows | | | | 输出名 → 点路径 |
| timeout | 超时（秒） | number | | 30 | | 请求超时 |

### inputs / outputs / conditions / constraints / exclusions / refs / exports

- **inputs**：空
- **outputs**：空
- **conditions**（2 条，替代 showIf）：

| id | when | show |
|---|---|---|
| c-body-type | method 非 GET/HEAD | bodyType |
| c-body | method 非 GET/HEAD | body |

- **constraints**：空
- **exclusions**：空
- **refs**：空
- **exports**（2 项）：

| key | from | type | desc |
|---|---|---|---|
| status_code | output | number | HTTP 状态码 |
| {extract_name} | output | string | 提取的响应子集（动态键） |

### lineage（血缘声明，执行类必填）

| role | pick | assetType | 说明 |
|---|---|---|---|
| source | url | url | 请求 URL |
| target | url | url | 同 URL（自引用） |

**注**：HTTP 执行器无外部数据资产，血缘豁免（URL 非数据资产）。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.url（text） | params 段 | 平移 |
| form.method（select） | params 段 | 平移 |
| form.headers（rows） | params 段 | 平移 |
| form.bodyType（select, showIf） | params 段 | 平移；showIf → conditions |
| form.body（text, showIf） | params 段 | 平移；showIf → conditions |
| form.successCodes（text） | params 段 | 平移 |
| form.extract（rows） | params 段 | 平移 |
| form.timeout（number） | params 段 | 平移 |
| `summary: () => ...` 函数 | render.summaryRules 兜底模板 | 决策 2 |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=8 / exports=2 / conditions=2）；bodyType/body showIf → conditions（method 非 GET/HEAD 时显示）；summary 常量函数迁移至 render.summaryRules 兜底模板。

**前端入口**：`/dag` → GraphWorkbench（palette「数据计算」分组拖拽）；`/meta/baseline` → BaselineWorkbenchView（底稿编辑/体检/认可发 v1）。

**后端**：零改动，executor=http 消费键不变（executors/http.py）。

**体检**（10 项全过）：contract=dag-engine+binding executor=http；params 8 项完整；conditions 替代 showIf；exports 2 项完整；血缘豁免。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

HTTP 执行器无外部数据资产：血缘豁免。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| — | — | — | — | — |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
