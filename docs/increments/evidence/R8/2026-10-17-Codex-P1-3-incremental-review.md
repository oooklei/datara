# Codex P1-3 增量复核回执

日期：2026-10-17（Asia/Shanghai）  
复核范围：Trae commits `d3910e5`, `fd757dd`, `5a71821` 及当前 canonical main；验收基线 `f9ad2c6`。  
结论：**PARTIAL，P1-3 不关闭**。本回执是增量复核，不替代最终八工具/真实执行链/持久化审计验收。

## 1. 运行证据

- Codex 独立复跑：在 `datara-backend` 执行 `pytest -q tests/rebuild/test_r8a_ai_tools_api.py`，结果 **13 passed in 17.45s**。
- Trae `5a71821` 提交说明另报 `rebuild 347 passed, 1 xfailed` 与 `ai_copilot 12 passed`；本回执未复跑这两组，不将其记作本轮独立验证。
- 子智能体仅提供补研；下述判断由主智能体对 canonical 源码和冻结契约复核后采纳。

## 2. 断言结果

| ID | 结果 | 源码/测试锚点 | 发现与后续 |
|---|---|---|---|
| R8A-01 路由/字段 | PARTIAL | `datara-backend/rebuild/ai_bridge.py`：`GET /api/v1/rebuild/ai/tools`、`POST /api/v1/rebuild/ai/tool-calls`；测试 `test_r8a_ai_tools_api.py` | 路径和八工具注册项覆盖；FE camelCase↔wire snake_case 的真实序列化映射仍未验。 |
| R8A-02 注册表能力声明 | PARTIAL / 裁定项 | `ai_bridge.py` 注册表八项均 `enabled=True`；dispatcher 对无 handler 回 `DEPENDENCY_UNAVAILABLE`；测试要求全 enabled | 冻结契约仅规定 enabled 为 boolean，Codex 清单 R8A-02 则按 PoC 规定仅已接线工具 enabled、其余 disabled 并返回 `TOOL_DISABLED`。当前全 true 与仅部分 handler 接线的事实不一致，FE 会把不可调用工具识别为可用。监督线需确认 enabled 是能力可用还是注册许可；确认前不得报 R8A-02 PASS。 |
| R8A-03 统一调用/上下文 | PARTIAL | `ai_bridge.py` 请求校验与 `R8A_CONTEXT_TYPES`；`test_post_invalid_params_and_bad_page_context` | 统一入口、坏 context 与 null 有基本覆盖；十类 context、各类 ref 结构和 envelope 类型未逐一验证。 |
| R8A-04 统一响应/错误 | PARTIAL | `ai_bridge.py` `envelope`/`finish_error`；对应 API 测试 | 未知工具、预算、部分依赖错误有覆盖；错误路径 audit_id/必需字段、错误码全表、retryable 映射及 `server_time` 的 DB 来源未全部实测。 |
| R8A-05 认证/项目权限 | PARTIAL | `ai_bridge.py` principal、permission/project/member 检查；权限拒绝测试 | 静态顺序为先鉴权和项目成员检查再取 handler；测试只比对拒绝码/消息，未以 spy 证明 handler/SQL port 零调用，也未逐次确认失败审计记录。 |
| R8A-06 错误归一 | PARTIAL | `ai_bridge.py` `ERROR_MESSAGES`、dispatch 分支 | 错误词表已集中；handler 异常统一 INTERNAL_ERROR。超时、取消、NOT_FOUND 等冻结码的来源映射和 retryable 组合仍未逐项覆盖。 |
| R8A-07 审计 | FAIL（错误路径）/ PARTIAL（成功路径） | `ai_bridge.py` `audit_record`, `finish_error`, handler dispatch；测试审计用例 | `5a71821` 已修正 writer-failure fixture，明确注入 `fail=True`；13 项测试通过。但 envelope 参数错误、`finish_error` 和无 handler 分支在 writer 异常时吞错，仍返回普通业务错误和 audit_id，无法保证失败调用恰有可回链记录。成功 handler 后 writer 失败则返回 INTERNAL_ERROR，符合 fail-closed；不能据此推导所有路径合格。 |
| AUD-01 审计字段 | FAIL | `ai_bridge.py` `audit_record` | 审计记录有身份、project、payload、outcome/error、latency、refs；缺 `started_at`/`finished_at`，且 `budget` 恒为空对象，与冻结契约 §4 要求的 DB 生成时间和实际预算不符。 |
| SQL-RO-01 执行授权与 R5-A port | NOT VERIFIED | `AiBridgePorts.handlers` 注入边界；run_sql 无 handler 测试 | 当前无 run_sql 实际 R5-A `executeSql` 端口及只读拒绝/委派的运行证据；`DEPENDENCY_UNAVAILABLE` 是诚实缺件反馈，不能作为 SQL 执行能力交付。 |
| HOST-01 create_app 挂载 | PARTIAL | `datara-backend/rebuild/api/app.py:create_app`（`fd757dd`） | 可选 `ai_bridge_ports` 显式注入；默认不挂载，符合未具备安全端口时 fail-closed。未发现生产 runtime factory 创建并注入 ports 的证据，默认部署仍无路由，生产可用性未验。 |
| TDD-01 审计故障红线 | PASS（限定范围） | `test_post_audit_writer_failure_never_fakes_success`（`5a71821`） | 测试现在注入失败 writer，并断言 ERROR/INTERNAL_ERROR、result=null、无 sink 记录；但未断言 handler 调用次数，不能证明“handler ran”注释所述副作用。 |

## 3. 需处理事项与责任

1. **Trae：**修复所有失败分支的审计 writer 异常语义，至少不得返回暗示已有 audit record 的普通结果；失败码选择按冻结契约/监督裁定，不自行新增协议码。补齐 handler 未调用的 spy、项目拒绝逐次审计断言。
2. **Trae：**按冻结 §4 补 `started_at`、`finished_at` 的存储端生成及实际 budget 使用值；给出持久化 writer 集成证据。
3. **监督线：**裁定 `enabled` 的权威语义，并据此协调 R8-A 契约、Codex 验收清单、测试与实现；目前三者不能同时成立。
4. **Trae/监督线：**补生产宿主 factory 注入和 run_sql→既有 R5-A execute port 的后续步骤证据；本次不把 mock handler 或未接线依赖计作交付。
5. **FE/契约责任方：**以真实 HTTP JSON 确认 camelCase↔snake_case 映射；当前不在本线改 datara-web。

## 4. 冻结边界

`5a71821` 的 13 项测试已由 Codex 本轮复跑通过；这只证明当前集成测试覆盖的桥接行为，不证明八工具可用、生产宿主接线、R5-A SQL 执行或审计持久化完整。R8-A v1 和 `generate_sql` 不作为第九个注册工具的裁定保持不变。复核未修改 Trae 实现、未调用 AOCI、未远端 push。
