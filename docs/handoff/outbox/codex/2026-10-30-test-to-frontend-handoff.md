# 测试域转前端域交接

- 涉及节号：待办 §三 C.8、C.9、C.11、C.12；下域 A.3；权威 §10.7。
- 已落地文件：`infra/fixtures/business/ecommerce_core_simulation.py`、`ECOM_SIM_20261030.json`、`test_ecommerce_core_simulation.py`（`7fc551d3`）；`render_ecommerce_sim_sql.py`、`test_render_ecommerce_sim_sql.py`（`0e155450`）；`docs/research/2026-10-30-customer-meeting-simulation-matrix.md`（`b0c513ce`）。各票细节见同日 C.11、C.8、C.9 outbox 卡。
- 未完事项：C.8 1.9 隔离目录实际导入和变量导入、C.9 12 行真实运行及 §10.7 十五项、C.12 SSH E2E；以上均按用户顺序留到全部代码修正和容器更新后。
- 当前验证：本机语法检查通过，1.9 只读确认原基线订单 250003、支付 200002、退款 15000、库存 5 仓；未执行写入或运行测试。
- 下次第一步：前端域仅取待办 §三 A.3 与权威 §四、§九/§10.10 相关片段，定位告警/SLA 空态与变量投影残项，完成代码修正。
