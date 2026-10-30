# 编排网关 C.7 跨项目引用冲突收口（2026-10-31）

- 任务包：待办 `docs/plans/2026-10-30-consolidation-and-simulation-todo.md` §三 C.7；权威 `docs/designs/2026-10-29-dbx-unified-target-design.md` §四、§10.7。目标文件：`datara-backend/rebuild/api/app.py`、`datara-backend/tests/rebuild/test_governance_api.py`。验收：跨项目治理引用阻止项目删除并返回 409；治理 API 定向测试通过。
- 改动文件：`datara-backend/rebuild/api/app.py`；提交 `e38c2c8`。`ProjectGovernanceConflict` 进入既有回滚与 HTTP 409 映射。测试文件已有覆盖，本票未改。
- 验证：本机 `pytest -q tests/rebuild/test_governance_api.py`，17 passed；`git diff --check -- datara-backend/rebuild/api/app.py`，退出码 0。本机结果是逻辑验证，不替代 1.9 专用命名空间清理 E2E。
- 遗留：1.9 部署后按权威 §10.7 对专用命名空间验证一键清理零残留；现有网关 `api.py` 的定时、内部取参和告警改动仍未分离提交。
- 下次第一步：在编排网关域核验定时与内部取参的独立测试和契约，再进入 1.9 部署阶段；涉及节号：待办 §三 C.7/B.4、权威 §四/§10.7/§10.9。
