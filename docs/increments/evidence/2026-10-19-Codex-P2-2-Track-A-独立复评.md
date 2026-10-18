# P2-2 Track A 独立复评（Codex）

**日期：** 2026-10-19（Asia/Shanghai）  
**终判：FAIL（本轮终局）**。#322 所列运行时接线修复及定向本地测试通过；Track A GREEN 门仍未满足既有 A1、A3 证据条件。不得以此宣告 GREEN，也不得派生新验收维度。

## 复评基线

- 裁定索引 #257：只对既有裁定基线判 PASS/FAIL，本轮终局；新发现走冻结后勘误。
- 裁定索引 #265：独立复核须附测试命令与输出定位；Track A 可继续实施，GREEN 仍须满足既定前置。
- 裁定索引 #283、#322：原 Codex 复核记录指出的生产 app/handler 接线缺口、缺依赖 fail-closed、以及 A3 JSON/PNG 与 `remote-final` 证据要求。
- 标准《核心业务功能实现规范与验收标准》§3：A1 要求保留带时间戳的 TDD 红灯证据；A2 要求独立复评；A3 要求 evidence JSON+PNG 成对且有 `remote-final`。

## 结果

| 基线项 | 判定 | 证据 |
|---|---|---|
| #322 生产接线 | **PASS** | `datara-backend/rebuild/api/app.py:753-761` 默认 app 从 `app.state.execution_port`、`app.state.audit_writer` 组装 bridge；`datara-backend/rebuild/ai_bridge.py` 的生产 handler 使用 execution port 和 writer。 |
| #322 请求实际消费与审计 | **PASS** | `TestDefaultAppProductionAssembly::test_run_sql_handler_calls_app_state_execution_port`、`::test_audit_written_via_app_state_audit_writer`：默认 app 的真实请求执行，写入真实 DB 审计记录。 |
| #322 fail-closed | **PASS** | `::test_missing_execution_port_fail_closed`、`::test_missing_audit_writer_fail_closed`：缺依赖时默认 bridge 路由不挂载；`tests/rebuild/test_r8a_ai_tools_api.py` 保留审计失败不得返回成功的断言。 |
| 定向复验 | **PASS** | 命令与机读 stdout 见下节：45 passed。 |
| A1 TDD 红灯留证 | **FAIL** | 本轮交付含绿灯输出；未找到与本次生产接线/缺口修复绑定的、带时间戳的原始 RED 命令及失败输出。既有 `2026-10-18-TrackA-Gap1-2-A5-seam-review.md` 已登记同一 A1 证据缺口，本轮没有新证据解除它。 |
| A3 成对与远端归档 | **FAIL** | `evidence/R8/tracka-runtime-wiring-evidence.json` 与同名 PNG 均存在；仓库中 Track A 本轮没有 `remote-final`。`evidence/R2/*remote-final*` 属于 2026-10-15 R2，不满足 Track A 证据要求。 |

因此，代码接线修复得到本轮局部 PASS，但因既有 A1、A3 门禁未闭合，**P2-2 Track A 本轮整体复评为 FAIL**。本结论仅按已有基线判定；本轮已终结。

## 定向测试复现

在 `datara-backend/` 运行：

```text
python -m pytest tests/sql_ide/test_repair_integration.py tests/sql_ide/test_factory.py tests/rebuild/test_r8a_ai_tools_api.py -v --tb=short
```

Codex 实际执行时通过 `rtk proxy` 调用上述 Python 命令。结果：`45 passed in 32.64s`，覆盖 17 个 repair integration、11 个 factory 和 17 个 AI tools API 测试。完整、UTF-8 机读输出：[`2026-10-19-TrackA-Codex-independent-revalidation.txt`](2026-10-19-TrackA-Codex-independent-revalidation.txt)，第 22–26 行含默认 app、实际 handler/审计及 fail-closed 断言，第 56 行为 pytest 汇总。

## 三轮互换备案

在本次复评前，当前仓库已有三份 Codex 对同一 P2-2 Track A 对象的未通过复核记录：

1. `2026-10-18-TrackA-Gap3-4-Codex-review.md`；
2. `2026-10-18-TrackA-Gap1-2-A5-seam-review.md`；
3. `2026-10-18-TrackA-runtime-wiring-verdict.md`。

本轮仍未通过整体门禁，按用户 2026-10-19 令触发强制互换并在 S3 报监督线：Codex 接下一轮实施，原实施者 Claude 接下一轮复评。涉及 `remote-final` 的外部运行证据须按监督线派单与现有环境流程办理；本轮未运行部署或远端命令。

## 执行边界

仅检查仓库源码、测试、提交与既有证据，并在本地复跑上述定向测试；未修改业务源码、未运行部署/远端命令、未调用 AOCI、未 push。此文件为单文件提交。
