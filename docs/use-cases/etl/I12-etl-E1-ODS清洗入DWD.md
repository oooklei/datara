# E1 · ODS→DWD 清洗（去重 / 脏行过滤 + 校验闸门）

## 1. 意图
验证 C11「SQL」节点承担分层加工主链路：对 ODS 明细按业务主键去重、过滤脏行，产出 DWD 清洗层表；并用 C25「数据校验」上游模式对 SQL 产物做闸门校验（C11/C25 + 数仓分层语义）。

## 2. 业务意义与作用
ODS 落地表通常存在重复推送、金额为负等脏数据，直接入 DWD 会污染下游聚合。本用例用可复核口径（`MIN(id)` 保首条 + `amount>=0` + 非空单号）清洗，并由校验闸门证明「清洗产物行数 = 源表去重口径行数」，防止静默丢数。

## 3. 业务逻辑（DAG）

```
(开始) ──> [SQL ODS清洗] ──> [C25 对账校验（上游模式）] ──> (结束)
```

## 4. 操作步骤
1. 前置：数仓 `ods_order` 就绪（S1 产物或批跑工具 prep 自动克隆灌入，25 万行）。
2. 页面新建工作流 `i12_E1_ods_to_dwd_clean`。
3. 画布拖入：开始(C1) → SQL(C11) → 数据校验(C25) → 结束(C2)，连线。
4. 按 §5 配置 SQL 与 C25；**SQL 节点须在 Inspector「输出 → 结果表注册表」登记 `dwd_order_clean`**（C25 上游模式据此解析校验对象）。
5. 保存 → 运行。

## 5. 逐节点配置参数与脚本

### SQL ODS清洗（C11）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 数据源 datasource | 内置数仓-datara_dw | 默认库 datara_dw |
| SQL 语句 sql | 见下 | 多语句分号拆分顺序执行 |
| 结果表注册表 outputs.tables | k=v=`dwd_order_clean` | C25 上游模式解析目标表 |

```sql
DROP TABLE IF EXISTS dwd_order_clean;
CREATE TABLE dwd_order_clean AS
SELECT t.* FROM ods_order t
JOIN (SELECT MIN(id) AS keep_id FROM ods_order
      WHERE amount >= 0 AND order_no IS NOT NULL AND order_no <> ''
      GROUP BY order_no) k ON t.id = k.keep_id
WHERE t.amount >= 0;
```

### 对账校验（C25）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 校验对象 assertSrc | upstream | 自动取上游 SQL 声明的结果表 |
| 规则集 rules | `rows`→`min=1`（清洗产物非空）；`unique`→`order_no`（去重后单号唯一）；`sql`→见下（行数与源去重口径一致） | |
| 不达标动作 onFail | fail（断流失败） | |

```sql
SELECT IF((SELECT COUNT(*) FROM dwd_order_clean) =
          (SELECT COUNT(*) FROM (SELECT order_no FROM ods_order
           WHERE amount >= 0 AND order_no IS NOT NULL AND order_no <> ''
           GROUP BY order_no) s), 1, 0)
```

## 6. 注意事项
- SQL 节点未登记结果表注册表时，C25 上游模式解析不到对象会留痕不通过——登记是本用例关键步骤。
- 清洗口径幂等：`DROP + CREATE AS`，可重复运行；产物表结构继承 ODS。
- 源表 25 万行，自连接去重 <1s；如源表结构变更（缺 id/order_no/amount 列）prep 会显式报错。

## 7. 验收标准
1. 实例终态 success，两个节点均成功。
2. `datara_dw.dwd_order_clean` 行数 = 源表去重口径行数（>0）；`order_no` 无重复组；`amount < 0` 行数 = 0。
3. C25 三条规则全通过（日志「规则 3 项，不通过 0 项」）。

## 8. 验收方法
① 查库 SQL（数仓容器）：

```sql
SELECT COUNT(*) FROM datara_dw.dwd_order_clean;                         -- 期望 = 去重口径行数
SELECT COUNT(*) FROM (SELECT order_no FROM datara_dw.dwd_order_clean
                      GROUP BY order_no HAVING COUNT(*) > 1) t;          -- 期望 0
SELECT COUNT(*) FROM datara_dw.dwd_order_clean WHERE amount < 0;        -- 期望 0
```

② API curl：

```bash
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/instances/{instanceId} | python3 -m json.tool
# 期望 state=success；assert 节点 outputs.assert_ok=true、failed=[]
```

③ 页面：实例详情 SQL/校验节点均「成功」；SQL 节点可打开「SQL 结果预览」浮窗。

## 9. 运行要求
- 数据源：内置数仓-datara_dw（id=4，默认库 datara_dw）。
- prep：dw.ods_order 就绪（批跑工具自动保障）。

## 10. 日志查看
实例详情 → SQL 节点「日志」：`[sql] 非查询语句 → 影响行数 …`（DROP/CREATE）+ `[lineage] 同步血缘`计数；C25 节点日志：`[master] 校验目标: dwd_order_clean @ 内置数仓-datara_dw` + 「规则 3 项，不通过 0 项」。

## 11. 日志存放位置
`/mnt/lei/datara/logs/{instance_id}/{task_id}.log`（宿主 docker 卷 datara_datara-logs）。
