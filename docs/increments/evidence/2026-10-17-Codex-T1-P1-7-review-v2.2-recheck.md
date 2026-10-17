# Codex T-1 复验回执：DBX × 原版 SQLIDE 融合对照清单 v2.2

- 评审对象：`docs/increments/2026-10-17-DBX-原版SQLIDE-融合对照清单.md`
- 评审版本：v2.2，提交 `043e18c`
- 对照依据：v2.1 复验回执 `2026-10-17-Codex-T1-P1-7-review-v2.1-recheck.md` 的三处缺口；Trae #112 另列单元格完备性、NA 语义和 PACKAGE/PACKAGE_BODY 共享证明。
- **结论：FAIL（空格/裸值及合并证明已补；N 列统一规则与表格内容仍自相矛盾）**。

## 逐项核验

| 项目 | 结论 | 依据与判断 |
|---|---|---|
| 每格 L/G/N 状态 | **PASS** | §2.4 八行 × 八路由组均显式填写 `L=… G=… N=…`，前次指出的空白格与无前缀裸值已消除。未知保留 U，未见把 U 改写为已支持。 |
| NA 语义 | **PASS** | §2.4 明确 NA 为入口不存在/操作不适用，与 Unknown（U）区分；`G=N → N=NA` 等格有逐项状态表达。 |
| N 列统一规则 | **FAIL** | §2.4 规则④明确写 `G=U → N=U`，但矩阵多格在 G=U 时给了 N=V/C/NA：SEQUENCE×OceanBase 为 `G=U N=V`（专用 builder）；MATERIALIZED_VIEW×OceanBase 为 `G=U N=C`；SQLite 族下 SEQUENCE、MATERIALIZED_VIEW、EVENT、SYNONYM、PACKAGE/PACKAGE_BODY、TYPE、TYPE_BODY、JOB 多行均为 `G=U N=NA`。这与规则④直接冲突。另一方面，SEQUENCE×OceanBase 有专用 builder 证据，说明“G=U 一律推出 N=U”本身可能过强。作者需选择并一致化：要么将规则④改成“仅当 N 依赖 G/source 获取时 G=U 才推出 N=U；有独立 builder/入口时以该操作的独立源码证据判定”，并逐格注明；要么将所有冲突格按原规则改为 N=U。不能同时保留现有规则和现有格值。 |
| PACKAGE/PACKAGE_BODY 合并证明 | **PASS（范围内）** | §2.4 给出 Oracle Agent 同一清单 SQL、同一分派集及 openGauss `is_body` 分支锚点，足以支持该合并行按共享路由组表示；正文仍明确列出 body 分支。若后续实证显示对象状态不同，再拆行。 |

## 结论与建议

v2.2 已解决“矩阵有空格/裸值”和 NA 词义问题；但按本轮列明的第 1 项标准检查，N 列规则是矩阵判定的一部分，规则与数据矛盾使该项尚不能整体 PASS。建议只修正规则与受影响格的一致性，保留独立 builder 的证据差异及 O7 Unknown 边界，之后即可复验关闭。

本回执只审查文档，不修改 v2.2、R5 契约或业务代码；未运行测试，无远端 push，未调用 AOCI 工具。
