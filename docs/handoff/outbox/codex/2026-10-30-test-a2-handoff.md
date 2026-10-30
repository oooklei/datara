# 测试域 A2 收口交接卡（2026-10-30）

- 任务包：`docs/plans/2026-10-30-consolidation-and-simulation-todo.md` §三 A.2；`docs/designs/2026-10-29-dbx-unified-target-design.md` §三。验收为 1.9 隔离工作目录 `tests/rebuild` 全量 0 failed（环境噪声除外）。
- 已落地文件：本卡。代码与测试文件未修改。
- 诊断结论：`datara-backend/tests/rebuild/test_sql_ide_route_coverage_matrix.py` 已由 `a022bb09` 删除，符合权威 §三退役旧 SQL IDE 的契约；本机执行 `pytest -q tests/rebuild/test_trial_e2e.py tests/rebuild/test_trial_runner_extensions.py --tb=short` 得 17 passed，**DIAGNOSTIC_ONLY_NOT_PASS_EVIDENCE**。本机全量测试已按用户最新环境指令中止，未形成结果。
- 远测状态：1.9 SSH 连通。运行队列 `queues/snapshot.json` 中可见测试租约 `LEASE-IMPL-V4-01-A-GROUP` 截止 2026-10-23，当前不可作为有效租约。未在 1.9 执行测试、部署或验收。
- 未完事项：取得集成管理的有效 1.9 隔离测试租约；将当前提交制品部署到隔离工作目录并记录提交身份、命令、时间、退出码及执行者；运行 `tests/rebuild` 全量，按实际失败逐项修复；其余待办按原计划 A1/A3/B4-6/C7-12/D13-14 分域处理，A1 与 D13 保留用户裁定门槛。
- 下次第一步：测试域会话先核对有效租约与 1.9 隔离工作目录，再运行全量 `tests/rebuild`。涉及节号：权威 §三、§四、§10.7；待办 §三 A.2。
