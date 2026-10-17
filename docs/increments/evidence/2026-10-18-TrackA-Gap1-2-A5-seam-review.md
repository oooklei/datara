# Track A Gap 1+2 与 A5 执行契约差异复核

- 日期：2026-10-18
- 对象：`42a39b1`（`ProductionSqlExecutionPort`）及 `60492d4`（port 测试）
- 基线：A5 v1.0 冻结候选 §2–§6、P2-2 设计 §11、监督线 #265 证据纪律、核心业务功能实现规范 v4 §3。
- 结论：**底层 `SqlExecutionPort` 签名兼容；不得将此二提交单独视为完整 A5 execution seam 或 R5-A GREEN。** 在 A5 全量执行语义视角存在 P1 缺口，测试证据也未满足完整 A1/#265 定位要求。
- 评审方式：3 个并行只读子任务分别核执行/取消、测试证据、契约 seam；主代理复核实际提交和源码锚点。未改业务代码、未运行测试、未调用 AOCI。

## 发现

| 级别 | 发现 | 源码/契约锚点 | 处理方向 |
|---|---|---|---|
| P1（完整 A5 seam） | `timeout_ms` 被接口接受但生产 port 未使用：`execute()` 传给 `_execute_readonly` 时遗漏；后者直接 `cursor.execute` 与 `fetchall`。 | `datara-backend/rebuild/sql_ide/execution.py:47–56,81–83,98–120`；`run_sql.py:156–171`；A5 §4.5–§4.8 | 实施 driver deadline 与超时后连接隔离/discard；或明确此对象仅是底层同步 driver primitive，由外层 durable task orchestrator 负责 timeout/status，且不得宣称满足 A5 timeout。 |
| P1（完整 A5 seam） | 未提供并发活动查询的 cancel/status 控制：port 只有同步 `execute()`，没有可供取消器命中的执行句柄/driver cancel；finally 仅 rollback/close。 | `execution.py:47–92`；`contracts.py:30–50`；A5 §3 #10–#11、§4.5–§4.8 | 将 cancel/status 与执行生命周期放入明确的上层任务 orchestrator，确保驱动确认终止/连接 discard 后才进入 canceled；补上状态恢复接口。 |
| P1（资源上限） | `row_limit` 只限制返回列表；先 `fetchall()` 读取所有行再裁切，内存与读取量没有边界。 | `execution.py:119–129`；A5 §3 #9/#12、§5–§6 | 采用 server-side/cursor bounded fetch，或最多读取 `row_limit+1` 并正确标记 truncation；若需精确 total_rows，应另行评估成本且不得隐含全量取数。 |
| 责任边界 | 此 port 返回内存结果 `{execution_id,columns,rows,row_count,total_rows,truncated}`，不创建持久化 task/history/result snapshot/SSE event/audit。`execution_id` 不得冒充 taskId/historyId/resultSetId。当前 `run_sql` 单语句门也不覆盖 A5 多语句合同。 | `execution.py:118–131`；`run_sql.py:99–132`；A5 §3 #9–#12、§4.1/4.4/4.5/4.8 | 可作为底层只读执行器；完整 SQL IDE 生命周期须由上层 adapter 实现，并将 R8 单语句能力与 A5 SQL IDE 多语句能力分别验收。 |
| 安全核验 | `SqlExecutionFailed` 包装字符串中包含原 driver exception 且保留异常 cause；现有 run_sql handler 外发为稳定错误，但日志/traceback 是否暴露原文需验证。 | `execution.py:133–136`；`run_sql.py:179–180`；A5 §2.1/§5 | API response 与普通日志只使用稳定 errorCode/sanitized details；禁止序列化 driver 文本或 cause/traceback；以测试断言验证。 |
| A1 / #265 证据 | #269 给出 19/19 与 53/53 两条命令和计数，但未给原始 stdout 路径。新增测试提交 `60492d4` 的父提交是实现 `42a39b1`；仓库当前未发现早于实现、带时间戳的 RED 原始输出，故 A1 TDD 红灯尚未证明。该证据缺口不表示测试报告为假。 | handoff `#269 Claude Track A`；`git log` 提交顺序；规范 v4 §3 A1；监督线 #265 | 提供两个测试命令的原始输出归档路径；如有实现前 RED 原始输出则补路径/时间戳，否则如实记 A1 RED 未证明，不将测试通过数升格为 GREEN。 |

## 当前判定与回执

1. `ProductionSqlExecutionPort` 与现有 `SqlExecutionPort` Protocol 签名兼容，并实现按 project/datasource 查找、MySQL/PostgreSQL DB-side read-only 与 finally rollback/close；这些是 Track A 底层装配方向的有效进展。
2. 对完整 A5 execution/cancel/replay 契约，当前仍为 **未满足/待上层实现或明确责任分层**；候选契约不能据此改标 RED→GREEN。
3. 测试报告记录为“Claude 报告 19/19、53/53；Codex 未独立复现，原始输出路径缺失，A1 RED 未证明”。未运行测试。
4. 本报告转交 Claude 实施线及监督线处理；建议在后续 Track A 交付心跳逐项答复上述 P1、责任分层、异常脱敏及 A1 原始输出。未替实施线直接修改源码。
