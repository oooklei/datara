# 电商需求归并与隔离仿真样本交接

- 任务包：权威设计 §二、§五与 §10.7 中非海豚能力；四份客户原始材料；电商核心业务仿真。未读取归档区。
- 已产出：`docs/research/2026-10-30-codex-ecommerce-requirements-reconciliation.md`（11 条去重需求及权威优先级/冲突处理）；`infra/fixtures/business/ecommerce_core_simulation.py`、`ECOM_SIM_20261030.json`、`test_ecommerce_core_simulation.py`（独立命名空间、正常事实与异常预期分离）。`docs/research/` 另四份未跟踪文档归属未知，未修改或提交。
- 外部业务依据：Google 官方电商事件、Stripe 官方 PaymentIntent 生命周期、Shopify 官方 Fulfillment 对象；链接已嵌入需求归并文档。指标金额/样本规模为仿真设定，非外部事实。
- 验证：`rtk pytest -q infra/fixtures/business/test_ecommerce_core_simulation.py` 3/3 通过；生成 JSON 5917 字节，6 订单/7 支付/4 履约/2 退款/4 库存/7 事件/4 隔离异常；实收 36000 分、成功退款 6000 分、净额 30000 分、复购 U001、部分履约 O002。`rtk git diff --check` 通过。
- 未完：样本尚未导入 DBX/Datara，平台 10 项治理、变量、资源、权限、影响分析尚需逐项实际运行和清理临时验证数据。导入前先核对现有 project 33/infra 数据、当前 API 与连接授权。
- 下次第一步：在本机 WSL 隔离环境只读盘点项目 33 的已授权连接和治理对象，再以专用命名空间导入少量样本，按“业务主键→入口→实际结果→清理”逐项验证；不碰海豚并行线。
