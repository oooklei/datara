# E5 · 带闸门分层链（校验闸门嵌入分层加工，不达标断流）

## 1. 意图
验证分层加工链中嵌入两道 C25 校验闸门的完整行为：正常数据全链通过；数据劣化时闸门断流（下游不执行、实例失败）；修复后恢复通过（C11×2 + C25×2 + 断流语义）。

## 2. 业务意义与作用
分层链路的隐患是「上游劣化静默传毒」：清洗层空转、聚合层照算。本用例用自有源表三段式验证——run1 全过建立基线；run2 清空源表使闸门一 0 行不达标 → 实例 failure、分层二未执行、DWS 表保持 run1 内容（断流实证）；run3 恢复源表后全链重建成功。

## 3. 业务逻辑（DAG）

```
(开始) ──> [SQL 分层一-清洗] ──> [C25 闸门一] ──> [SQL 分层二-聚合] ──> [C25 闸门二] ──> (结束)
```

## 4. 操作步骤
1. 前置：自有源表 `datara_dw.i12_o_order_src`（克隆 ods_order 结构、5000 行；工具 prep 自动建）。
2. 页面新建工作流 `i12_E5_gated_pipeline`，按 §5 配置四个节点（两个 SQL 均登记结果表），保存。
3. **run1**：直接运行 → 期望全链 success。
4. **run2**：数仓容器执行 `TRUNCATE TABLE datara_dw.i12_o_order_src;` 后再运行 → 期望闸门一断流 failure。
5. **run3**：恢复源表（`INSERT INTO i12_o_order_src SELECT * FROM ods_order LIMIT 5000;`）后运行 → 期望全链恢复 success。

## 5. 逐节点配置参数与脚本

### SQL 分层一-清洗（C11，数据源=内置数仓-datara_dw）
```sql
DROP TABLE IF EXISTS dwd_order_gate;
CREATE TABLE dwd_order_gate AS
SELECT t.* FROM i12_o_order_src t
JOIN (SELECT MIN(id) AS keep_id FROM i12_o_order_src
      WHERE amount >= 0 AND order_no IS NOT NULL AND order_no <> ''
      GROUP BY order_no) k ON t.id = k.keep_id
WHERE t.amount >= 0;
```
结果表注册表：k=v=`dwd_order_gate`。

### C25 闸门一（校验对象=upstream，onFail=fail）
| 规则 | 值 | 说明 |
|---|---|---|
| rows | min=1 | 清洗产物非空（**0 行即断流**） |
| unique | order_no | 单号唯一 |
| sql | `SELECT IF((SELECT COUNT(*) FROM dwd_order_gate) = (SELECT COUNT(*) FROM (SELECT order_no FROM i12_o_order_src WHERE amount >= 0 AND order_no IS NOT NULL AND order_no <> '' GROUP BY order_no) s), 1, 0)` | 与源去重口径一致 |

### SQL 分层二-聚合（C11，同数据源）
```sql
DROP TABLE IF EXISTS dws_gate_day;
CREATE TABLE dws_gate_day AS
SELECT order_date, COUNT(*) AS order_cnt, SUM(amount) AS amt_sum
FROM dwd_order_gate GROUP BY order_date;
```
结果表注册表：k=v=`dws_gate_day`。

### C25 闸门二（校验对象=upstream，onFail=fail）
| 规则 | 值 | 说明 |
|---|---|---|
| rows | min=1 | 聚合非空 |
| sql | `SELECT IF((SELECT COALESCE(SUM(order_cnt),0) FROM dws_gate_day) = (SELECT COUNT(*) FROM dwd_order_gate), 1, 0)` | 各天单数之和=DWD 总数 |

## 6. 注意事项
- 源表为本用例自有 `i12_o_order_src`，TRUNCATE 篡改只影响本用例，不碰共享 fixture（ods_order/ods_payment 零接触）。
- run2 断流点在闸门一：`rows min=1` 对 0 行表必然不通过；下游「分层二-聚合」不得出现 success 状态。
- DWS 表在 run2 中应保持 run1 内容（DROP/CREATE 未执行到）——这是「下游不执行」的库级实证。
- 幂等性：run1/run3 均 DROP+CREATE 重建，行数应一致。

## 7. 验收标准
1. run1：终态 success；`dwd_order_gate`>0、`dws_gate_day`>0；两闸门 assert_ok=true。
2. run2：终态 **failure**；「分层二-聚合」任务非 success（未执行/跳过）；`dws_gate_day` 行数与 run1 一致（未被重建）；闸门一 outputs.assert_ok=false、failed 含行数规则描述。
3. run3：终态 success；`dwd_order_gate`/`dws_gate_day` 行数与 run1 一致（恢复重建）。

## 8. 验收方法
① 查库 SQL（数仓容器，run1 后记 dws1，run2 后记 dws2，run3 后记 dws3）：

```sql
SELECT COUNT(*) FROM datara_dw.i12_o_order_src;   -- run2 前后分别期望 5000 / 0 / 5000
SELECT COUNT(*) FROM datara_dw.dwd_order_gate;    -- run1=run3，run2 后为 0（重建自空源）
SELECT COUNT(*) FROM datara_dw.dws_gate_day;      -- run1=run2=run3（run2 未被执行）
```

② API curl：三次 `GET /instances/{instanceId}` → state 分别 success / **failure** / success；run2 闸门一节点 outputs.failed 非空、分层二任务非 success。

③ 页面：任务中心三次实例「成功 / 失败 / 成功」；run2 实例详情闸门一节点红色失败、日志含「不通过: 行数 0 不在区间 [1, ∞)」。

## 9. 运行要求
- 数据源：内置数仓-datara_dw；需对 datara_dw 具备 TRUNCATE/INSERT 权限（仅限自有表）。

## 10. 日志查看
run2 闸门一日志：`[master] 校验目标: dwd_order_gate @ 内置数仓-datara_dw` + `规则 3 项，不通过 1 项` + `不通过: 行数 0 不在区间 [1, ∞)`；run1/run3 两 SQL 日志含影响行数、两闸门「不通过 0 项」。

## 11. 日志存放位置
`/mnt/lei/datara/logs/{instance_id}/{task_id}.log`。
