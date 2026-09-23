# E2 · DWD→DWS 日聚合（fork 双分支 + merge 汇合）

## 1. 意图
验证汇总层加工与 DAG 编排组合：fork 并行分叉出两条 SQL 聚合分支（按天 / 按天+状态），各自带 C25 闸门，经 C7「合并（OR）」汇合收口（C5/C6/C7/C11/C25 组合）。

## 2. 业务意义与作用
DWS 聚合层通常同源多口径并行加工。本用例证明两条分支互不阻塞并行执行，且每条分支产物都能通过「各分组单数之和 = DWD 总数」的对账闸门；merge（OR）语义 = 任一上游完成即放行收口。

## 3. 业务逻辑（DAG）

```
                ┌─> [SQL 日聚合-按天]   ──> [C25 校验-按天]   ──┐
(开始) ─> [fork] ┤                                              ├─> [merge 合并（OR）] ─> (结束)
                └─> [SQL 日聚合-按状态] ──> [C25 校验-按状态] ──┘
```

## 4. 操作步骤
1. 前置：`datara_dw.dwd_order_clean` 就绪（E1 产物；批跑工具 prep 自动预建）。
2. 页面新建工作流 `i12_E2_dws_daily_agg`。
3. 画布拖入：开始 → 并行分叉(C5) → 两条分支（SQL(C11)+数据校验(C25)）→ 合并（OR）(C7) → 结束，连线。
4. 按 §5 配置；两个 SQL 节点分别登记结果表 `dws_order_stat_day` / `dws_order_stat_status`。
5. 保存 → 运行。

## 5. 逐节点配置参数与脚本

### SQL 日聚合-按天（C11，数据源=内置数仓-datara_dw）
```sql
DROP TABLE IF EXISTS dws_order_stat_day;
CREATE TABLE dws_order_stat_day AS
SELECT order_date, COUNT(*) AS order_cnt, SUM(amount) AS amt_sum
FROM dwd_order_clean GROUP BY order_date;
```
结果表注册表：k=v=`dws_order_stat_day`。

### SQL 日聚合-按状态（C11，同数据源）
```sql
DROP TABLE IF EXISTS dws_order_stat_status;
CREATE TABLE dws_order_stat_status AS
SELECT order_date, status, COUNT(*) AS order_cnt
FROM dwd_order_clean GROUP BY order_date, status;
```
结果表注册表：k=v=`dws_order_stat_status`。

### 两个 C25（校验对象=upstream，onFail=fail）
| 节点 | 规则集 |
|---|---|
| 校验-按天 | `rows`→`min=1`；`sql`→`SELECT IF((SELECT COALESCE(SUM(order_cnt),0) FROM dws_order_stat_day) = (SELECT COUNT(*) FROM dwd_order_clean), 1, 0)` |
| 校验-按状态 | `rows`→`min=1`；`sql`→`SELECT IF((SELECT COALESCE(SUM(order_cnt),0) FROM dws_order_stat_status) = (SELECT COUNT(*) FROM dwd_order_clean), 1, 0)` |

## 6. 注意事项
- merge 是「任一上游完成即放行」的 OR 语义（区别于 join 的 AND 全等待）；本用例把闸门放在各分支内部保证确定性，merge 仅做编排收口。
- 两条分支并行建表，表名不同无冲突；聚合粒度不同（按天 / 按天+状态），对账口径同为「分组计数求和 = DWD 行数」。

## 7. 验收标准
1. 实例终态 success，两分支 SQL 与两个 C25 均成功。
2. `SUM(order_cnt)`（两表分别）= `dwd_order_clean` 行数。
3. 任务列表可见两条分支节点，时间窗重叠（并行）。

## 8. 验收方法
① 查库 SQL（数仓容器）：

```sql
SELECT (SELECT COALESCE(SUM(order_cnt),0) FROM datara_dw.dws_order_stat_day),
       (SELECT COALESCE(SUM(order_cnt),0) FROM datara_dw.dws_order_stat_status),
       (SELECT COUNT(*) FROM datara_dw.dwd_order_clean);
-- 期望三值相等且 > 0
```

② API curl：`GET /instances/{instanceId}` → state=success；taskInstances 含两个 sql + 两个 assert 全 success，起止时间重叠。

③ 页面：实例详情 DAG 显示 fork 双路 + merge 汇合结构，任务列表两分支均「成功」。

## 9. 运行要求
- 数据源：内置数仓-datara_dw；prep：dwd_order_clean 就绪（工具自动保障）。

## 10. 日志查看
两个 SQL 节点日志均含 `[sql] 非查询语句 → 影响行数 …`；两个 C25 日志含「规则 2 项，不通过 0 项」。

## 11. 日志存放位置
`/mnt/lei/datara/logs/{instance_id}/{task_id}.log`。
