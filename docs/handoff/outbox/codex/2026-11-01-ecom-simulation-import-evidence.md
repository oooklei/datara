# C8 电商仿真样本导入证据卡

## 盘点

1.9 project 33（admin 只读）：8 个资产、7 个标签、3 条质量规则、4 个标准、4 个指标、0 个质量报告、0 个告警策略；导入前无 `ecom_sim_20261030_*` 项目变量。

## 导入

- 使用 WSL 隔离入口执行 `infra/fixtures/business/import_ecommerce_sim_variables.py --apply-variables --project-id 33 --target http://192.168.1.9:18091`。
- 首次结果：4 个变量全部 `saved`。
- 复跑结果：4 个变量全部 `unchanged`，证明导入幂等。
- 复核：4 个变量均带 `simulation-fixture:ECOM_SIM_20261030` 标记；未写入治理对象、未覆盖非仿真变量。

## 本地验证

- `python infra/fixtures/business/import_ecommerce_sim_variables.py`：输出受控 dry-run，命名空间与 4 个变量定义正确。
- `python -m pytest -q infra/fixtures/business/test_import_ecommerce_sim_variables.py infra/fixtures/business/test_ecommerce_core_simulation.py infra/fixtures/business/test_fixture_contract.py`：`14 passed`。

## 判定/遗留

C8 的变量样本导入已完成并可重复。完整业务事实样本（订单/履约/退款等）仍未导入；C9 矩阵逐项运行与 C10 行级质量执行裁定待继续。

## 涉及节号

收口计划 §三 C8；权威设计 §六、§10.7、§10.9。
