# 电商全域数据治理仿真：业务依据与可执行场景

日期：2026-10-30。范围：Datara 的变量、资源、数据治理、dbx 连接与 SQL、影响分析等非海豚能力。本文是**仿真方案的业务依据**，不是部署完成证明。外部事实只引一手资料；公式、阈值、规模和产品映射均为本项目的**仿真设计推导**，实施时以实际 API、字段和运行结果复核。

## 1. 客户核心业务闭环

主线是「获客活动 → 商品与可售库存 → 浏览/加购 → 下单 → 支付 → 履约 → 售后/退款 → 复购」。Google 的电商事件规范明确包含 `view_promotion`、`select_promotion`、`view_item`、`add_to_cart`、`begin_checkout`、`purchase` 和 `refund`；订单事件与商品行分别保存交易级和商品级参数，退款可按商品行记录。[Google 电商测量](https://developers.google.com/analytics/devguides/collection/ga4/ecommerce)、[事件参数](https://support.google.com/analytics/answer/12200568?hl=en-EN)

| 环节 | 仿真业务记录与关键关联 | 必须能被产品动作检验 |
|---|---|---|
| 获客与营销 | 活动、渠道、曝光、点击、券领取/使用；`promotion_id → cart/order/item`。Google 对活动曝光与点击使用 `view_promotion/select_promotion`，并要求后续事件沿用活动标识才能分析购买归因。[Google](https://developers.google.com/analytics/devguides/collection/ga4/ecommerce) | 活动效果指标、投放后购买漏斗、无效用券告警 |
| 商品主数据 | `category → product → SKU/variant`，可选 GTIN；GTIN 只在确有合法分配值时填写，不能随机造“真实条码”。GS1 将 GTIN 定义为可定价、订购、开票商品的唯一标识。[GS1](https://support.gs1.org/support/solutions/articles/43000734283-what-is-a-global-trade-item-number-gtin-) | 商品编码标准、重复 SKU/类目引用质量规则、商品标签 |
| 库存 | `SKU × location × snapshot_time`，区分 `available/on_hand/committed/reserved/damaged`。Shopify 的库存级按商品与地点记录这些状态，`on_hand` 是在库各状态之和，`incoming` 不是现货。[Shopify 库存](https://shopify.dev/docs/apps/build/inventory-management-apps) | 可售库存、缺货预警、库存守恒与超卖异常 |
| 浏览到下单 | 用户匿名/会员标识、商品浏览、加购、结算、订单、订单行；订单需保留金融与履约两个状态，而不能用一个状态替代。Shopify 订单提供交易金额、行项目、支付状态和履约状态。[Shopify 订单](https://shopify.dev/docs/api/admin-graphql/latest/queries/orders?example=retrieve-a-list-of-orders) | 漏斗转化、购物车放弃、订单行与订单总额核对 |
| 支付 | `order_id → payment_intent_id`；金额与币种、尝试时间、状态、实收金额。支付有需要支付方式、处理、成功、取消等不同状态；异步处理期间不能计作已付。[Stripe PaymentIntent](https://docs.stripe.com/payments/paymentintents/lifecycle)、[对象字段](https://docs.stripe.com/api/payment_intents/object) | 已支付订单与支付成功流水对账、重复支付异常 |
| 履约 | `order_item → fulfillment_item → shipment/tracking_event`，一单允许拆成多次履约；跟踪信息含承运商、运单号、状态。[Shopify Fulfillment](https://shopify.dev/docs/api/admin-graphql/latest/objects/fulfillment) | 已付未发、超时发货、部分发货、签收时效 |
| 售后 | `order_item → return_line → refund`，区分退货申请、退货状态与资金退款；部分退款必须保留商品与数量。Shopify Return 关联订单及多条退货行；Stripe Refund 记录支付引用、金额和 `pending/succeeded/failed` 等状态。[Shopify Return](https://shopify.dev/docs/api/admin-graphql/latest/objects/Return)、[Stripe Refund](https://docs.stripe.com/api/refunds/object) | 退款不超过实收、退货不超过购买数量、退款时效、净收入 |
| 复购 | 用同一合成会员标识串联多单；“复购用户”口径固定为观察窗内成功支付订单数 ≥2，不把失败支付算作复购。用户受众可由购买行为构造。[Google 受众](https://support.google.com/analytics/answer/12799087?hl=en) | 首购/复购标签、30 日复购率、会员分层 |

## 2. 对现有 infra 数据的核对

现有 [源库 DDL](../../infra/mysql/src/init/01_schema.sql) 有会员/地址、购物车、类目/供应商/商品、库存快照、订单/订单行、支付、退款、优惠券/用券、活动和敏感信息表；[目标库 DDL](../../infra/mysql/dw/init/01_schema.sql) 有订单明细。现有 [INFRA-DATA-01](../../infra/fixtures/business/README.md) 只有 2 用户、3 商品、3 订单、4 行、2 支付，足以做接口烟测，不足以检验跨日、分仓、部分履约、部分退款、复购、质量趋势和影响分析。

**需要补的业务事实**：商品 SKU/规格与合成商品编码、库存地点及状态变动、浏览/加购/结算事件、支付尝试及状态历史、履约单及轨迹、退货行与退款状态、活动曝光/点击和复购订单。既有 `ods_refund` 只有订单级退款金额，不能验证行级部分退款；`dim_inventory` 只有 `qty` 快照，不能验证可售/锁定/在途守恒。新增表或独立仿真 schema 应先与现有产品查询契约核对，不把外部平台字段机械搬入。

现有 fixture 的 `ensure_demo_identities` 会重置演示账号密码并写管理员密码文件；它不能直接作为共享验证环境的数据重建脚本。[源码](../../infra/fixtures/business/seed_product_fixture.py)

## 3. 每个治理模块承载的业务与验收信号

以下每行都是**建议的仿真检验**；不是声称产品已实现。质量规则可用 `not_null/unique/accepted_values/relationships` 四种基础约束做确定性正反样本；dbt 文档对这四种检验给出明确定义。[dbt 数据测试](https://docs.getdbt.com/reference/resource-properties/data-tests)

| 模块 | 业务场景和最小仿真对象 | 可执行验收 |
|---|---|---|
| 标签 | 商品：高毛利/临期缺货；会员：首购/30 日复购/高价值；订单：活动订单。行为标签应由事件与成功支付推导，不随机填写。[Google 受众](https://support.google.com/analytics/answer/12799087?hl=en) | 同一会员新增成功复购单后标签变更；失败支付不变更 |
| 标准 | 订单号、SKU、金额币种、时区、订单/支付/退款状态字典；术语“GMV/实收/净收入/可售库存”各有定义、owner 和适用口径。业务术语应能映射到表和列。[Apache Atlas Glossary](https://atlas.apache.org/2.0.0/Glossary.html) | 每个术语能定位字段；状态枚举外样本命中 |
| 指标目录 | 下单数、支付成功订单数、支付实收、退款成功额、净收入、客单价、购物车转化、复购率、可售库存、发货及时率。Google 区分事件次数和商品数量，退款事件不能直接并入“购买数”。[Google 指标](https://support.google.com/analytics/answer/13428834?hl=en) | 每项有粒度、分子/分母、过滤条件、币种与时区 |
| 指标看板 | 日/周、渠道、类目、仓库、会员层级切片，展示交易漏斗、支付、退款、履约和质量趋势。[Google 电商报告](https://support.google.com/analytics/answer/12924131?hl=en) | 改日期/渠道后数值按事实变化；汇总与明细可对账 |
| 一致性检查 | 订单金额 ↔ 行小计−优惠+运费/税；已付订单 ↔ 成功支付；退款成功额 ≤ 已收；库存状态合计 ↔ 在库。支付、退款及库存状态各有独立业务含义。[Stripe](https://docs.stripe.com/payments/paymentintents/lifecycle)、[Shopify 库存](https://shopify.dev/docs/apps/build/inventory-management-apps) | 正常样本通过，故意错账仅命中目标行 |
| 质量规则 | 唯一/非空/枚举/外键、金额非负、时间顺序、部分退货数量上界、活动券有效期。基础约束参考 dbt 内置测试。[dbt](https://docs.getdbt.com/reference/resource-properties/data-tests) | 每规则有通过样本与一条可定位失败样本 |
| 检查任务 | 对订单、支付、退款、库存等分区按业务日期执行规则组；重跑同日期应幂等。[OpenLineage Run 模型](https://openlineage.io/docs/spec/object-model/) | 展示运行 ID、范围、开始结束、通过/失败计数 |
| 异常数据核查 | 展示重复订单号、孤儿订单行、支付早于订单、退款超额、无库存发货等具体主键和原因。[dbt 关系测试](https://docs.getdbt.com/reference/resource-properties/data-tests) | 从报告下钻到命中行；修复/豁免后再次检查可对比 |
| 质量报告 | 按域/规则/日期聚合通过率、异常数、修复数、趋势，保留执行快照；OpenLineage 的数据质量 facet 区分指标与断言结果。[OpenLineage](https://openlineage.io/docs/spec/object-model/) | 报告统计等于任务与异常明细，不把未运行算通过 |
| 质量告警 | 支付对账差异、退款超额、库存负数、关键表延迟等触发；阈值、触发时间、恢复时间和接收者可核查。[OpenLineage 运行状态](https://openlineage.io/docs/spec/object-model/) | 故障样本触发一次，恢复后状态闭环；无重复风暴 |
| 变量参数 | `run.biz_date`、`project.currency`、`env.source_schema`、`global.quality_threshold`、`task.batch_size`；分别影响日期过滤、币种、源库、质量阈值和分页。Datara 七级作用域及敏感值规则见[目标设计 §九](../designs/2026-10-29-dbx-unified-target-design.md)。 | 改 `biz_date` 后仅目标分区结果变化；同名变量按优先级解析；敏感值不进日志 |
| 资源管理/脚本 | SQL 订单支付对账脚本绑定 dbx 连接与 schema；Python/shell 试运行绑定可用且授权的 SSH 节点，脚本版本/owner/共享可核查。见[目标设计 §八](../designs/2026-10-29-dbx-unified-target-design.md)。 | 改脚本版本/共享范围后，执行来源和可见集合变化；无权限者不能运行 |
| dbx IDE/连接 | 对电商源库、数仓、只读验证连接分别赋 owner；仅显式共享后给其他成员可见，数据库密码留在服务端。见[目标设计 §四](../designs/2026-10-29-dbx-unified-target-design.md)。 | admin 全见；无授权用户空集合；共享后只增加指定连接；撤销立即失效 |
| 历史/影响分析 | 对订单明细→日汇总→看板的 SQL 运行生成有输入、输出、运行 ID 和时间的记录；列级影响只在有真实解析证据时断言。OpenLineage 以 Dataset/Job/Run 建模。[OpenLineage](https://openlineage.io/docs/spec/object-model/) | 修改订单金额字段可找到下游支付/净收入指标；无关类目不误报 |
| 安全/审计 | 合成手机号/地址/身份字段标敏感；访问与拒绝记录可关联用户、资源、动作、时间；外部个人数据不进入仿真库。NIST Privacy Framework 用于识别与管理隐私风险。[NIST](https://www.nist.gov/privacy-framework) | 无权账号看不到明文及未共享资源；管理员能查拒绝事件 |

## 4. 统一口径与正反样本

建议所有事实携带 `fixture_namespace`、稳定业务键、`event_time`、`biz_date`、`source_system`、`run_id`；货币使用明确 `currency`，金额按最小货币单位或定点数存储并固定换算。订单、支付、履约、退款各自保留事件时间，不能用订单日期代替。此为从订单/支付/履约分离对象与事件级参数推导的仿真约束。[Shopify](https://shopify.dev/docs/api/admin-graphql/latest/queries/orders?example=retrieve-a-list-of-orders)、[Stripe](https://docs.stripe.com/api/payment_intents/object)、[Google](https://support.google.com/analytics/answer/12947610?hl=en)

最小可执行闭环包含：正常支付并发货、待支付取消、一次支付失败后重试成功、部分发货、部分退货并成功退款、退款处理中后失败、跨仓库存不足、同一会员复购、活动曝光点击但未购买、同一活动转化购买；另设可恢复的脏数据命名空间，覆盖重复键、缺失关联、枚举越界、金额不平、时间倒序和无权访问。期望结果由确定性生成器计算，不能把 UI 当前数值写成预期值。支付与退款状态区分依据 Stripe，部分履约与退货行依据 Shopify。[Stripe 支付](https://docs.stripe.com/payments/paymentintents/lifecycle)、[Stripe 退款](https://docs.stripe.com/api/refunds/object)、[Shopify 履约](https://shopify.dev/docs/api/admin-graphql/latest/objects/fulfillment)、[Shopify 退货](https://shopify.dev/docs/api/admin-graphql/latest/objects/Return)

**清理界限**：只清带专用验证命名空间/稳定 ID 范围的临时记录，先列清单并核对引用，再删除；保留经验证的电商仿真基线。现有 INFRA-DATA-01 的专用目标表与保留 ID 可作隔离参考，但不能据此删除其它项目数据。[现有 fixture 说明](../../infra/fixtures/business/README.md)

## 5. 待产品裁定的特殊项

1. 当前 `ec_retail` 缺少真实 GTIN、物流承运商与支付渠道官方回执。仿真可用明确标注的合成商品编码、物流事件、支付模拟状态；**不能冒称真实外部平台回执或合法分配的 GTIN**。GS1 要求 GTIN 在其体系内唯一。[GS1](https://support.gs1.org/support/solutions/articles/43000734120-what-is-a-gs1-gtin-)
2. “所有选项非空”应覆盖业务可配置项；确实无可用外部资源（如无已授权 SSH 节点、无真实支付渠道）时，应呈现说明性空态与补配入口，不伪造可运行资源。此项是产品决策，需结合当前部署事实确认。
3. 实收、GMV、净收入、退款率、复购率的日期归属、取消单/部分退款口径需要在平台标准与指标定义中冻结；本文只给出可检验候选场景，不替用户裁定财务口径。
