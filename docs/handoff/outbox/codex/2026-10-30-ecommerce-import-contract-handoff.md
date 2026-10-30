# 电商仿真变量导入/清理交接

- 任务包：权威设计 §二、§四、§五；当前后端变量、治理、DBX owner 和项目路由。未碰海豚、共享部署或现有测试数据。
- 已落地：`infra/fixtures/business/import_ecommerce_sim_variables.py`、`test_import_ecommerce_sim_variables.py`；API 核对表 `docs/research/2026-10-30-codex-ecommerce-import-contract-audit.md`。
- 验证：`rtk pytest -q infra/fixtures/business/test_import_ecommerce_sim_variables.py infra/fixtures/business/test_ecommerce_core_simulation.py` 7/7；`rtk proxy python -m py_compile` 通过；dry-run 输出 4 项计划且无网络；`rtk git diff --check` 通过。
- 关键限制：治理资产/标签/规则/标准/指标/报告/告警缺匹配删除 API；项目删除不能保证清理治理 FK。因此本票仅对变量提供可清理导入，治理对象尚未写入。
- 下次第一步：在 WSL 隔离部署只读核对 project 33 的变量与治理对象；若需要临时治理数据，先补删除/级联契约；若做长期仿真基线，明确命名和保留范围，再逐模块导入并实际验证。
