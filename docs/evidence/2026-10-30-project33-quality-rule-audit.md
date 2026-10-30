# 项目 33 电商质量规则核对（2026-10-30）

## 只读核对结果

1. `rebuild_governance_asset` 只有三个资产：`ec_retail.ods_order`（16）、`datara_dw.dwd_trade_order`（17）、`datara_dw.dim_user`（18）。
2. 规则 8 的身份证表达式用 `id_card`，却绑定资产 17；规则 10 的统一社会信用代码表达式用 `usci`，也绑定资产 17。DBX 元数据查询中，`datara_dw.dwd_trade_order` 仅有 `order_no`、`user_id`、`order_amount`。
3. 规则 9 的手机号表达式用 `phone`，绑定资产 18；DBX 当前 `datara_dw` 元数据查询中未找到 `dim_user`。
4. 业务源库 `ec_retail.dim_user` 实际有 `phone`、`id_card`；`ec_retail.dim_supplier` 实际有 `credit_code`，没有 `usci`。后者应以真实列名重新定义表达式。
5. 三条规则尚无质量运行记录。现有 `run_quality_rule` 只做结构安全检查，四个行级计数恒为 0；因此不得把规则存在或 `succeeded` 状态作为业务数据质量通过的证据。

用 DBX 0.6.60 的 `/api/query/execute` 对源库做只读聚合，返回格式为 `columns` 加二维 `rows`，计数值是字符串：

| 真实表与字段 | 检查行数 | 不合规则行数 |
| --- | ---: | ---: |
| `ec_retail.dim_user.id_card` | 60,002 | 2 |
| `ec_retail.dim_user.phone` | 60,002 | 1,200 |
| `ec_retail.dim_supplier.credit_code` | 1,501 | 1 |

这里仅验证了长度与正则格式，未覆盖身份证校验位及企业代码校验位；因此这是格式规则的基线，不代表证件真实性或法定有效性。

## 修正顺序

1. 先把源库 `dim_user`、`dim_supplier` 采入项目 33 资产目录，核对 DBX 元数据和项目连接可见性。
2. 通过规则编辑接口将身份证与手机号规则绑定到 `ec_retail.dim_user`；把企业代码规则改为引用 `credit_code`，绑定 `ec_retail.dim_supplier`。保留原规则 ID 与审计记录。
3. 将行级检查接到 DBX 查询接口，并在运行记录中保存实查行数、失败数、连接 ID、查询时间与错误信息；不可用时明确失败，不回退为伪成功。
4. 最后部署到隔离验证入口，用正常与脏数据样本实测，再清理有命名空间的临时验证记录。

本轮没有改动 1.9 的共享业务数据或既有规则。

## 本地代码进度

已加入受限表达式编译器、资产到 DBX 连接的项目内授权绑定与解绑，以及有绑定时的 DBX 聚合检查路径。DBX 响应的字符串计数被校验后写入质量运行记录；不合规则行数大于 0 时运行状态为失败。规则页可选择资产与可见连接，规则页和任务页只对 `engine=dbx` 展示行级结果。相关后端测试、前端质量契约测试和前端构建通过。

管理员绑定未归属的既有 DBX 连接时，网关先向 DBX 核实连接存在，再在本项目建立 owner 归属；已归属其他项目的连接仍拒绝绑定。开发者只能绑定本项目本人拥有或被共享的连接。
临时验证身份 `user_id=0` 不允许认领未归属连接，避免把长期 owner 绑定给短时测试主体；项目 33 的正式连接认领须由持久管理员账号执行。

这些改动尚未部署到 1.9。项目 33 的源库资产采集、规则重绑和 DBX owner 归属仍未完成，因此上面的只读实查数字还不是 Datara 平台运行记录。

1.9 后端容器只读检查还确认：当前元数据库不存在 `rebuild_dbx_connection_ownership` 和 `rebuild_dbx_connection_share` 表；`DBX_INTERNAL_TOKEN` 未配置；项目 33 的资产 16、17、18 各有 0 个字段元数据。这三项均是行级路径的部署前置，不能用本地测试通过替代。
