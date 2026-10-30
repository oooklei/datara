# 编排网关域 C7 代码交接卡（2026-10-30）

- 任务包：待办 `docs/plans/2026-10-30-consolidation-and-simulation-todo.md` §三 C.7；权威 `docs/designs/2026-10-29-dbx-unified-target-design.md` §四、§10.7；研究 `docs/research/2026-10-30-ecommerce-governance-simulation.md` §4。验收为专用命名空间清理后治理对象零残留。
- 改动文件：`datara-backend/rebuild/governance/api.py`（标签、质量规则、标准、指标、质量报告、质量告警策略删除 API）、`datara-backend/rebuild/governance/project_cleanup.py`（项目治理外键依赖顺序清理，保留审计并解除项目引用）、`datara-backend/rebuild/api/app.py`（项目删除接入）、`datara-backend/tests/rebuild/test_governance_api.py`（权限、跨项目、关联与清理契约）。
- 验证命令与结果：本机 `python -m compileall -q`（上述四个 Python 文件）EXIT 0；`from rebuild.api.app import create_app` 导入 EXIT 0；`git diff --check` EXIT 0。这些是静态诊断，**不是运行测试通过证据**。
- 遗留项：遵用户最新顺序，待全部代码修正及 1.9 容器更新后，在 1.9 隔离目录执行新契约测试与全量回归，再做专用命名空间零残留验收。旧导入标签引用和关联指标在单项删除时返回 409，需先清理其引用；项目删除按外键顺序清理项目归属图。不可删除非专用命名空间的现存仿真基线。
- 下次第一步：继续编排网关域的 C10 质量行级执行或回到 C7 运行后纠错；涉及节号：权威 §四、§10.7；待办 §三 C.7/C.10。
