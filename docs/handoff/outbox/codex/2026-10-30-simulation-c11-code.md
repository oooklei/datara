# C.11 电商仿真事实补齐

- 涉及节号：待办 §三 C.11；research `2026-10-30-ecommerce-governance-simulation.md` §2、§4。
- 改动文件：`infra/fixtures/business/ecommerce_core_simulation.py`、`ECOM_SIM_20261030.json`、`test_ecommerce_core_simulation.py`。
- 内容：补 SKU/规格及合成商品编码、跨仓库存与状态变动、支付尝试状态史、履约轨迹、退货行与退款状态史、活动曝光/点击；所有有效事实带 `fixture_namespace`、`source_system`、`run_id`、独立 `event_time`、`biz_date`。保留原 6 单独立样本与原金额预期，新增派生对账预期。
- 本机产物生成：`python -c '... sim.build_fixture() ... ECOM_SIM_20261030.json ...'`，退出码 0；语法检查 `python -m compileall -q`，退出码 0；`git diff --check`，退出码 0。
- 遗留项：尚未在 1.9 核对 25 万订单基线可复用字段，尚未导入样本或运行测试。按用户顺序，全部代码修正完成后再更新容器并验证。
- 下次第一步：完成 C.8 专用命名空间数据导入路径代码，并只读核对 1.9 基线映射。
