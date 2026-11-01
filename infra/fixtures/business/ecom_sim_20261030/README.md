# 项目 33 电商核心业务仿真基线

此目录是可复核的业务 SQL 资源源文件。2026-10-30 通过 Datara 资源上传 API 写入 1.9 项目 33；2026-11-01 三条核查脚本改为读取隔离夹具 schema `ecom_sim_20261030`，并随 `infra/seed_ecommerce_demo.py` 一起投影进海豚工作流定义。资源库中的副本仍是 2026-10-30 上传的版本，**不是**这三条 DAG 的运行时来源；DAG 的 SQL 来自本目录当前文件。

| 资源 | 业务检验 | 运行时读取 | 只读执行结果 |
| --- | --- | --- | --- |
| `ecom_order_payment_reconciliation.sql` | 订单到支付的逐单对账 | `ecom_sim_20261030.orders` / `.payments` | 海豚实例 18（任务 54）：6 单，O001/O002/O004/O006 `MATCH`，O003/O005 `UNPAID` |
| `ecom_refund_overpayment_check.sql` | 退款总额超过已付金额的异常订单 | `ecom_sim_20261030.payments` / `.refunds` | 海豚实例 19（任务 55）：0 行（R001 6000 ≤ P005 12000），无超额退款 |
| `ecom_inventory_safety_check.sql` | 仓库低于安全库存与缺货 | `ecom_sim_20261030.inventory` | 海豚实例 20（任务 56）：SKU-A@WH-EAST `OK`、SKU-B@WH-EAST `STOCKOUT`、SKU-B@WH-WEST / SKU-C@WH-EAST / SKU-D@WH-WEST `BELOW_SAFETY` |
| `ecom_sim_expected_reconciliation.sql` | 隔离仿真事实与 fixture 预期指标对账 | `ecom_sim_20261030` 隔离 schema | 资源 id=20 版本 2；只读实跑 `verdict=MATCH`（4/4、30000/30000、异常 8 条） |

## 变量绑定规则（2026-11-01 实测，勿再违反）

海豚把 SQL 里的 `${...}` 替换成 JDBC `?` 占位符再参数绑定（`ds-worker` 日志：`after replace sql , preparing : ...`、`prepare statement replace sql : ... sql parameters : {1=Property(...)}`）。因此：

- **schema / 表名必须是字面量**，写成 `${schema}.payments` 会变成 `?.payments` 而无法执行。
- 变量只能承载**值**：日期上界、阈值、预期计数。三条脚本分别使用 `${project.ecom_sim_20261030_biz_date}` 与 `${project.ecom_sim_20261030_safety_stock}`。
- `${prop}` 按名字精确匹配工作流定义里的 `globalParams`，`project.` 只是名字的一部分，不是作用域解析。

`infra/seed_ecommerce_demo.py` 的 `fixture_global_params()` 把 `import_ecommerce_sim_variables.variable_definitions()` 的 8 个变量以 `<scope>.<name>` 全名投影进工作流的 `globalParams`（`direct=IN`、`type=VARCHAR`），保证 DAG 与变量清单同源。

`ecom_sim_expected_reconciliation.sql` 的预期值取自 `${project.ecom_sim_20261030_paid_orders}`、`${project.ecom_sim_20261030_net_paid_cents}`。注意项目 33 里另有一个**无前缀**的 `project.source_schema=ec_retail`，它不属于本夹具，本夹具变量一律带 `ecom_sim_20261030_` 前缀以免指向错库。

## 1.9 实测（2026-11-01，隔离验证主机）

- 隔离 schema `ecom_sim_20261030`：14 张事实表（含 `quality_anomalies`），异常行 8 条（X001–X008）。
- 对账 SQL 只读实跑结果：`observed_paid_orders=4 / expected=4`、`observed_net_paid_cents=30000 / expected=30000`、`quality_anomalies=8`、`verdict=MATCH`。
- 夹具变量：项目 33 现有 8 个 `ecom_sim_20261030_` 变量（1 个 `global` + 7 个 `project`）；本轮新增 `safety_stock=10`，其余 7 个为 `unchanged`（幂等）。
- 三条 DAG 于 2026-11-01 11:25 重建：旧定义 `188478422402080` / `188478422568992` / `188478422787104` 先 OFFLINE 再删除，新定义 `188490901197856` / `188490901942304` / `188490902082592` 均 release ONLINE 并运行，实例 18/19/20 全部 `SUCCESS`，任务 54/55/56 全部 `SUCCESS`。
- 变量工具在非 WSL 主机上需显式 `DATARA_SIM_ALLOW_HOST=192.168.1.9` 且本机地址确含该地址，否则拒绝变更。
- 浏览器级验收（`http://192.168.1.9:8090/`，项目 33）：工作流定义列表可见三条夹具 DAG 且均为「已上线」；打开画布 iframe 落在 `/dolphinscheduler/ui/projects/188273928846848/workflow/definitions/<code>?embed=1` 并渲染出 ECOM-SIM 节点；运行历史中实例 18/19/20 状态均为「成功」；展开实例可见 8 个夹具变量与 1 个任务实例。证据截图 `ecom-dag-canvas.png`、`ecom-run-detail.png` 存于 1.9 `/lei/datara/deployments/F-DS-EMBED-20261030/e2e/`。

同批次（2026-10-30）通过 Datara 变量 API 写入项目级 `biz_date`、`source_schema`、`warehouse_schema`、`settlement_currency`、`quality_max_failure_rate`、`order_batch_size`、`refund_sla_hours`、`inventory_safety_stock`，描述均带 `[ECOM-SIM-20261030]`。业务日期初设 2026-10-22；发现该日仅 1 条订单后，修正为最近的完整日批 2026-10-14（2,777 条订单、2,271 条支付、166 条退款）。既有 `${global.biz_date}=2026-10-28` 保持原值；源库和质量阈值的项目作用域解析也已确认。数据由同一仿真标记识别，后续清理临时验证数据时应保留。

项目中既有的 `_clean_cross.py`、`test-upload.sql`、`smoke_check.sh` 等资源未删除：当前没有足够的归属证据证明它们属于本轮临时验证数据。

治理目录同批次新增 5 个项目标签（订单、支付、退款、库存、个人信息），其中订单与个人信息标签挂载到现有 `ec_retail.ods_order` 资产 #16；新增 4 项标准和 4 项指标定义，均保留 `draft` 状态。支付金额与退款金额分列，不把二者相减后直接称为确认收入；金额精度与业务日期标准在财务口径确认前同样保留草稿。这些定义使目录可用于业务讨论，但没有执行引擎结果，不能视为指标验收通过。

随后从 `ec_retail` 元数据与实际行数建立 5 个项目资产：`dim_user`（11 字段、60,002 行）、`dim_supplier`（7 字段、1,501 行）、`ods_payment`（6 字段、200,002 行）、`ods_refund`（5 字段、15,000 行）、`dim_inventory`（5 字段、20,000 行）。另增会员、供应商两个标签，并将对应业务与敏感度标签挂到上述资产。原有 `ods_order` 资产 #16 仍缺字段元数据，这是既有目录缺口，尚待通过可审计的资产更新接口修正。

截至本轮只读核对，项目 33 为 8 个资产、7 个标签、4 项标准草稿、4 项指标草稿、3 条旧质量规则、0 条质量运行、10 个资源、11 个项目变量。质量运行保持空白，因为现网规则绑定错误且仍只执行结构校验；不能为填充界面制造 0 行的伪运行。新增资源、变量、资产及目录定义均经正式 API 写入；原有测试资源未删。
