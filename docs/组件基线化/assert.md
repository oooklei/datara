# 数据校验（C25）· type=`assert`

> 基线化设计册 · 分组：M-B2 ETL/计算类 · 状态：🔵 designing（规格草案待确认）
> 七节纪律见 [README](./README.md)；本册随逐组件五步循环推进回写，未经用户确认的规格草案仅落第 1/2 节。

## 1. 语义分析

**执行模型**：dag-engine + master 内联执行（无 worker executor，master/engine.py:_exec_assert）。
**master 内联执行**：
- 校验对象解析（_assert_target）：手选 ds.table 优先；上游模式显式「上游节点引用」优先，未选则自动扫描直接上游
- 规则集（_assert_rules）：行数区间/主键唯一/非空率/自定义 SQL 断言
- 通过 → success 出口；不达标 on_fail=warn → failure 出口（告警放行）；on_fail=fail → 节点 FAILURE
- 出口路由复用 conditions/switch 分支机制（chosen 缓存 + sourceHandle 匹配）
**表单角色**：校验对象（手选/上游引用）+ 校验数据源/表 + 规则集 + 不达标动作
**现状缺口**：assertUpstream/assertDs/assertTable/ruleColumns 带 showIf + pick（不可序列化）；rulesHint 为 hint 字段（空 label）；summary 为函数；ports 为函数（hasPortsFn）。

## 2. 八项表单规格（草案）

### params（8 项）

| key | label | uiType | required | default | options | 说明 |
|---|---|---|---|---|---|---|
| assertSrc | 校验对象 | select | | manual | manual/upstream | 校验对象来源 |
| assertUpstream | 上游节点引用 | resource | | | | 显式上游节点引用（showIf → conditions） |
| assertDs | 校验数据源 | resource | ✓ | | dsTypes=[mysql,greatdb] | 校验数据源（showIf → conditions） |
| assertTable | 校验表 | resource | ✓ | | | schema → 表（showIf → conditions） |
| rules | 规则集 | rows | ✓ | | | key=规则，value=参数 |
| ruleColumns | 规则列参考 | resource | | | | 手选表字段，可选（showIf → conditions） |
| rulesHint | （说明条） | hint | | | | 固定文案 |
| onFail | 不达标动作 | select | | fail | fail/warn | 不达标动作 |

### inputs / outputs / conditions / constraints / exclusions / refs / exports

- **inputs**：空
- **outputs**：空
- **conditions**（4 条，替代 showIf）：

| id | when | show |
|---|---|---|
| c-upstream | assertSrc=upstream | assertUpstream |
| c-manual | assertSrc=manual | assertDs, assertTable, ruleColumns |

- **constraints**：空
- **exclusions**：空
- **refs**：空（数据源/表引用经 resource 字段，不声明 upstream 域）
- **exports**（2 项）：

| key | from | type | desc |
|---|---|---|---|
| assert_ok | output | bool | 校验是否通过 |
| failed | output | array | 不通过的规则列表 |

### lineage（血缘声明，执行类必填）

| role | pick | assetType | 说明 |
|---|---|---|---|
| source | assertDs | datasource | 校验数据源 |
| target | assertTable | table | 校验表 |

**注**：数据校验执行器的读写端由校验对象动态决定，声明级血缘以「校验数据源引用字段」+「校验表引用字段」为 pick 锚点。

## 3. 表单声明对照（旧 → 新）

| 旧声明 | 新段落 | 迁移方式 |
|---|---|---|
| form.assertSrc（select） | params 段 | 平移 |
| form.assertUpstream（resource, showIf+pick） | params 段 | 平移；showIf → conditions；pick → refs 注记 |
| form.assertDs（resource, showIf+pick, required） | params 段 | 平移；showIf → conditions；pick → refs 注记 |
| form.assertTable（resource, showIf+pick, required） | params 段 | 平移；showIf → conditions；pick → refs 注记 |
| form.rules（rows, required） | params 段 | 平移 |
| form.ruleColumns（resource, showIf+pick） | params 段 | 平移；showIf → conditions；pick → refs 注记 |
| form.rulesHint（hint, 空 label） | params 段 hint 字段 | 平移；空 label → 固定文案 |
| form.onFail（select） | params 段 | 平移 |
| `summary: () => ...` 函数 | render.summaryRules 兜底模板 | 决策 2 |
| ports 函数（hasPortsFn） | render.ports 声明位 | 端口声明保留在前端 profile |

## 4. 执行契约（前后端改动记录）

**实现方式**：五步循环第 3 步，规格以 BaselineSpec JSON 写入 `t_baseline_progress`（status=designing, rev=1），catalogHash=83929cf7c3c5c660。

**前端**：八段 DSL 声明（params=8 / exports=2 / lineage=2 / conditions=2）；assertUpstream/assertDs/assertTable/ruleColumns showIf → conditions；rulesHint 空 label → 固定文案；summary 常量函数迁移至 render.summaryRules 兜底模板；ports 函数保留在前端 profile。

**前端入口**：`/dag` → GraphWorkbench（palette「数据计算」分组拖拽）；`/meta/baseline` → BaselineWorkbenchView（底稿编辑/体检/认可发 v1）。

**后端**：零改动，master 内联执行（_assert_target + _assert_rules）。

**体检**（10 项全过）：contract=dag-engine+master 内联（无 worker executor）；params 8 项完整；conditions 替代 showIf；exports 2 项完整；lineage 校验数据源 + 校验表锚点完整。

**验证**：pytest 261 全绿，vitest 351 全绿。

## 5. 血缘与变量声明

见 §2 lineage：声明级校验数据源 + 校验表锚点；运行态字段级血缘由 worker/lineage 落库。

## 6. 1.9 实测记录

| 批次 | 数据流 | 结果 | 备注 | 日期 |
|---|---|---|---|---|
| — | — | — | — | — |

## 7. 认可记录

（待用户在工作台点「认可发 v1」后回写）
