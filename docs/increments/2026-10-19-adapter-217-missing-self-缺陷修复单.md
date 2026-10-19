# 缺陷修复单 — adapter.py:217 missing-self（P1-6' 首个真实缺陷）

| 项 | 内容 |
|---|---|
| 缺陷编号 | P1-6'-D1 |
| 位置 | `datara-backend/ai_copilot/adapter.py` `_default_factory` → `_TenantVanna.__init__`（证据落库时行号 :217；修复提交后位于 265-267 行） |
| 发现 | P1-6' 真实执行链验证首跑（run-20261017T160551Z）步骤 3 实锚复现 |
| 状态 | **已修复**（提交 `10069ac`，2026-10-18）+ **已重跑取证**（2026-10-19，见 `docs/increments/evidence/2026-10-19-P1-6prime-默认工厂重跑证据.md`） |

## 1. 缺陷描述

`_TenantVanna.__init__` 中 `OpenAI_Chat.__init__(client=_OpenAIClientProxy(), config={"model": settings.model})` 为**未绑定调用（缺 self）**。

- vanna 2.0.2 实测签名：`OpenAI_Chat.__init__(self, client=None, config=None)`。
- 触发：每次 `_TenantVanna` 构造必 `TypeError: missing 1 required positional argument: 'self'`。
- 表象：默认工厂炸 → 所有 memory write / generate_sql 失败；adapter 脱敏后抛 `VannaAdapterError: ddl memory write failed`（根因被吞，需读码定位）。
- 实锚：首跑 run-20261017T160551Z 步骤 3 `VannaAdapterError: ddl memory write failed`；单测 `test_adapter_default_factory.py` 修复前 FAIL（TypeError）。

## 2. 影响面

- **默认工厂路径 100% 失效**：所有经 `CopilotAdapter` 默认工厂的 `add_ddl` / `add_documentation` / `add_sql` / `generate_sql` 全部失败。
- **生产装配阻塞**：生产 adapter 默认工厂不可用；P1-6' 验证当时只能靠公开组合 seam `CopilotAdapter(vanna_factory=…)` 注入修正版工厂绕过（零触碰红线）。
- **不影响**：注入自定义 vanna_factory 的路径；adapter 审计/脱敏语义（错误被 `VannaAdapterError` 正确脱敏，无泄漏）；`ChromaDB_VectorStore` 侧构造（绑定正确）。

## 3. 修复方案（TDD，已执行）

1. **先写失败测试**：`tests/ai_copilot/test_adapter_default_factory.py` 直接调 `_default_factory` 复现 missing-self TypeError（修复前 FAIL）。
2. **最小代码修复**（1 行，提交 `10069ac`）：

   ```python
   # 修复前（未绑定）
   OpenAI_Chat.__init__(client=_OpenAIClientProxy(), config={"model": settings.model})
   # 修复后（绑定）
   OpenAI_Chat.__init__(self, client=_OpenAIClientProxy(), config={"model": settings.model})
   ```

3. **语义不变**：scoped chroma 租户隔离 / `run_sql` 拒绝（执行主权归 R8-A 桥）/ `log` 静默（防 SQL 泄漏）/ 凭证不入 vanna 实例（`_OpenAIClientProxy` 无凭证 seam）。

## 4. 回归口径

| 层 | 口径 | 结果 |
|---|---|---|
| 单测 | `pytest tests/ai_copilot/test_adapter_default_factory.py`（3 用例：valid instance / api_key not stored / scoped chroma path） | 3/3 PASSED（2026-10-19 复跑确认） |
| 全链路 | PoC 以**默认工厂**重跑 9 步（训练写入 / NL→SQL / 授权执行 / 结果解释 / 隔离×4 / 审计落库 / adapter 事件） | 全绿（run-20261019T203126Z） |
| 隔离回归 | 步骤 7 四项拒绝（跨项目 / VIEWER / 写 SQL / vanna 内部 run_sql） | 全过 |
| 审计回归 | adapter 层 8 事件 started/succeeded 成对零 failed；PoC 审计 4/4 持久化 | 全过 |

## 5. 附：注入修正版工厂处置

PoC 脚本 `docs/increments/evidence/2026-10-18-P1-6prime-poc-chain.py` 中 `corrected_vanna_factory`（仅修 self 的对照版）保持注释状态；默认工厂已可用，注入版留作对照，不再需要。
