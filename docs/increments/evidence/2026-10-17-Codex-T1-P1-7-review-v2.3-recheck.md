# Codex T-1 第五轮复验回执：DBX × 原版 SQLIDE 融合对照清单 v2.3

- 评审对象：`docs/increments/2026-10-17-DBX-原版SQLIDE-融合对照清单.md`
- 评审版本：v2.3，提交 `fca0bc3`
- 对照依据：v2.2 复验回执 `2026-10-17-Codex-T1-P1-7-review-v2.2-recheck.md` 的唯一 FAIL 项；监督线 #115 裁定二；Trae #117 派单。
- 复验范围：§2.4 N 列规则④与原矩阵格值的一致性；确认变更范围及独立源码证据。
- **结论：PASS**。规则④从“G=U 一律推出 N=U”改为仅对依赖 G/source 获取路径传递 U；独立生成器/入口按各自源码证据判定，解决了 v2.2 的规则/格值矛盾。

## 核验

1. **变更范围**：`fca0bc3` 只将清单版本更新为 v2.3，改写 §2.4 规则④及对应说明/登记；矩阵格值未变，与 #115 裁定“无需改格，仅修订规则④措辞”一致。
2. **原冲突格**：
   - SEQUENCE × OceanBase Oracle mode：`G=U, N=V`，N 有专用 builder `object_source_sql.rs:L130-L131` 证据，规则明确不再由 G 的 U 无条件覆盖独立 builder 结论。
   - MATERIALIZED_VIEW × OceanBase Oracle mode：`G=U, N=C`，N 有通用原文执行回退 `object_source_sql.rs:L188-L190` 证据；C 仍表达受条件约束的路径，不冒称专用方言 builder。
   - SQLite 族多个对象：`G=U, N=NA`，规则将 NA 限定为独立确认的入口不存在/不适用，与 U（证据不足）区分；本结论不授权将未来缺证据的 N 值默认为 NA，缺少入口边界证据时仍应标 U。
3. **其他复验面**：v2.2 已通过的全格 L/G/N、NA 语义和 PACKAGE/PACKAGE_BODY 共享证明未回退；本轮没有发现规则④的新矛盾。O7 的运行时/权限不确定性边界保留。

## 边界

本回执只关闭 T-1 复验第 1 项的规则④一致性缺口；不代表 DBX 驱动能力已做运行时实测，也不替代 A5 冻结或改变 R5 契约。本次为文档复验，未运行测试，未修改 v2.3 正文或业务代码，未触碰 `datara-web`、AI Copilot、AOCI；无远端 push。
