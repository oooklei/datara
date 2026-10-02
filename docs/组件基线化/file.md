# 文件读取（C22）· type=`file`

> 基线化设计册 · 分组：M-B2 ETL/计算类 · 状态：🔵 designing（规格草案待确认）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写，未经用户确认的规格草案仅落第 1/2 节。

## 1. 语义分析

**执行模型**：dag-engine + worker executor（executors/file.py）。
**worker 执行器**：
- 来源二选一：数据源中心文件源（param.datasource）或手动参数（path/format/encoding/delimiter/header/sheet）
- 流式解析（CSV/TXT csv.reader / Excel openpyxl read_only）→ schema 推断（1000 行抽样）+ 空值率
- 注册临时数据三形态：table（目标库 TEXT 列批量物化，1000 行/批）/ resultset（抽样 JSON）/ file（登记路径）
- 保留策略 immediate/days/keep 落库；清扫/转正式归 master 收口（common/tmpdata）
- 输出：rows_count / columns / tmp_name（注册时）
**表单角色**：来源模式 + 文件源/路径 + 格式/编码/分隔符/表头/Sheet + 注册参数（名/形态/目标端/保留策略）
**现状缺口**：mode 带 onChange（不可序列化）；datasource/path/format/encoding/delimiter/header/sheet/tmpName/kind/targetDs/retention/keepDays/keepHint/tmpHint 带 showIf（不可序列化）；summary 为函数。

## 2. 八项表单规格（草案）

### params（16 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| mode | 来源模式 | select | | datasource | datasource/manual | 来源模式（onChange → conditions） |
| datasource | 文件源数据源 | resource | | | dsTypes=[file] | 文件源数据源（showIf → conditions） |
| path | 文件路径 | text | | | | /datara/files 相对路径（showIf → conditions） |
| format | 格式 | select | | | csv/excel/txt | 文件格式（showIf → conditions） |
| encoding | 编码 | select | | utf-8 | utf-8/gbk/utf-8-sig | 文件编码（showIf → conditions） |
| delimiter | 分隔符 | text | | , | | CSV 分隔符（showIf → conditions） |
| header | 首行表头 | bool | | true | | 首行是否表头（showIf → conditions） |
| sheet | Sheet 名称 | text | | | | 留空 = 首个（showIf → conditions） |
| register | 注册临时数据 | bool | | true | | 是否注册临时数据 |
| tmpName | 临时数据名 | text | | | | 匹配 ^[a-z][a-z0-9_]{2,31}$（showIf → conditions） |
| kind | 临时数据形态 | select | | table | table/resultset/file | 临时数据形态（showIf → conditions） |
| targetDs | 物化目标数据源 | resource | | | dsTypes=[mysql,greatdb] | 物化目标数据源（showIf → conditions） |
| retention | 保留策略 | select | | immediate | immediate/days/keep | 保留策略（showIf → conditions） |
| keepDays | 保留天数 | number | | 0 | | 保留天数（showIf → conditions） |
| keepHint | （说明条） | hint | | | | 固定文案（showIf → conditions） |
| tmpHint | （说明条） | hint | | | | 固定文案（showIf → conditions） |

### inputs / outputs / conditions / constraints / exclusions / refs / exports

- **inputs**：空
- **outputs**：空
- **conditions**（14 条，替代 showIf + onChange）：

| id | when | show |
|---|---|---|
| c-datasource | mode=datasource | datasource |
| c-manual | mode=manual | path, format, encoding, delimiter, header, sheet |
| c-register | register=true | tmpName, kind, targetDs, retention, keepDays, keepHint, tmpHint |

- **constraints**：空
- **exclusions**：空
- **refs**：空（数据源引用经 resource 字段，不声明 upstream 域）
- **exports**（3 项）：

| key | from | type | desc |
|---|---|---|---|
| rows_count | output | number | 数据行数 |
| columns | output | number | 列数 |
| tmp_name | output | string | 临时数据名 |

### lineage（血缘声明，执行类必填）

| role | pick | assetType | 说明 |
|---|---|---|---|
| source | path | file | 文件路径 |
| target | targetDs | datasource | 物化目标数据源 |

**注**：文件读取执行器的读写端由来源模式动态决定，声明级血缘以「文件路径字段」+「物化目标数据源引用字段」为 pick 锚点。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.mode（select, onChange） | params 段 | 平移；onChange → conditions |
| form.datasource（resource, showIf+pick） | params 段 | 平移；showIf → conditions；pick → refs 注记 |
| form.path/format/encoding/delimiter/header/sheet（showIf） | params 段 | 平移；showIf → conditions |
| form.register（bool） | params 段 | 平移 |
| form.tmpName/kind/targetDs/retention/keepDays/keepHint/tmpHint（showIf） | params 段 | 平移；showIf → conditions |
| `summary: () => ...` 函数 | render.summaryRules 兜底模板 | 决策 2 |
| page（预览网格 F62） | render.page 声明位 | 页面组件映射保留在前端 profile |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=16 / exports=3 / lineage=2 / conditions=3）；mode onChange → conditions；所有 showIf → conditions；summary 常量函数迁移至 render.summaryRules 兜底模板；page 声明位保留在前端 profile。

**前端入口**：`/dag` → GraphWorkbench（palette「数据计算」分组拖拽）；`/meta/baseline` → BaselineWorkbenchView（底稿编辑/体检/认可发 v1）。

**后端**：零改动，executor=file 消费键不变（executors/file.py）。

**体检**（10 项全过）：contract=dag-engine+binding executor=file；params 16 项完整；conditions 替代 showIf+onChange；exports 3 项完整；lineage 文件源锚点 + 目标数据源锚点完整。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

见 §2 lineage：声明级文件源锚点 + 目标数据源锚点；运行态字段级血缘由 worker/lineage 落库。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| — | — | — | — | — |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
