# E3 · ELT 先入仓后加工（raw 原样落地 → SQL 类型规整）

## 1. 意图
验证 ELT 语义：C24「文件同步」把 CSV **原样**落地为 raw 表（全 TEXT 列），再由 C11「SQL」在库内做类型规整（CAST/STR_TO_DATE）产出结构化 DWD 表，C25 收口对账（C24 + C11 + C25）。

## 2. 业务意义与作用
ELT 与 ETL 的差异在于「先入仓、后加工」：raw 层保留文件原始字符串形态可回溯，加工失败不丢原始数据。本用例用 500 行订单 CSV 验证 raw→typed 两层行数一致、类型规整后无解析失败行。

## 3. 业务逻辑（DAG）

```
(开始) ──> [C24 文件原样入仓 i12_ods_order_raw] ──> [SQL ELT类型规整 dwd_order_file] ──> [C25 对账校验] ──> (结束)
```

## 4. 操作步骤
1. 前置：宿主机 `/mnt/lei/datara/i12files/orders.csv`（500 数据行 + 表头；S4 同源文件，工具 prep 保障存在）。
2. 页面新建工作流 `i12_E3_elt_file_raw`。
3. 画布拖入：开始 → 文件同步(C24) → SQL(C11) → 数据校验(C25) → 结束，连线。
4. 按 §5 配置；SQL 节点登记结果表 `dwd_order_file`。
5. 保存 → 运行。

## 5. 逐节点配置参数与脚本

### 文件原样入仓（C24）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 运行节点 runtimeNode | 1.9宿主机 | 文件在宿主机路径，非共享卷走节点读取 |
| 文件路径 filePath | /mnt/lei/datara/i12files/orders.csv | |
| 文件类型 fileType / 分隔符 / 编码 / 表头行数 | csv / , / utf-8 / 1 | |
| 写端数据源 targetDs | 内置数仓-datara_dw | |
| 目标表 targetTable | datara_dw.i12_ods_order_raw | raw 层专用表（i12_ 前缀） |
| 自动建表 autoCreate + DDL | 开 + 见下 | raw 全 TEXT 原样承载 |
| 写入模式 writeMode | overwrite | 幂等重演 |

```sql
CREATE TABLE IF NOT EXISTS i12_ods_order_raw (
  order_no TEXT, user_id TEXT, amount TEXT, status TEXT, create_time TEXT)
```

### ELT类型规整（C11，数据源=内置数仓-datara_dw）
```sql
DROP TABLE IF EXISTS dwd_order_file;
CREATE TABLE dwd_order_file AS
SELECT order_no, CAST(user_id AS UNSIGNED) AS user_id,
       CAST(amount AS DECIMAL(12,2)) AS amount, status,
       STR_TO_DATE(create_time, '%Y-%m-%d %H:%i:%s') AS create_time
FROM i12_ods_order_raw WHERE order_no <> '';
```
结果表注册表：k=v=`dwd_order_file`。

### 对账校验（C25，校验对象=upstream，onFail=fail）
| 规则 | 值 | 说明 |
|---|---|---|
| rows | min=500,max=500 | 文件数据行精确值 |
| unique | order_no | 单号唯一 |
| sql | `SELECT IF((SELECT COUNT(*) FROM dwd_order_file) = (SELECT COUNT(*) FROM i12_ods_order_raw WHERE order_no <> ''), 1, 0)` | 规整前后行数一致 |

## 6. 注意事项
- raw 表与 S4 的 `i12_ods_order_file` 是两张表：本例 raw 全 TEXT（ELT 原样语义），S4 是直接建结构化表（ETL 语义）。
- `STR_TO_DATE` 解析失败返回 NULL，验收以 `create_time IS NULL` 计数=0 证明格式匹配。
- writeMode=overwrite 保证重跑幂等；raw 表可留档回溯。

## 7. 验收标准
1. 实例终态 success，三个节点均成功。
2. `i12_ods_order_raw` = 500 行；`dwd_order_file` = 500 行且 order_no 去重 = 500。
3. `create_time IS NULL OR amount IS NULL` 行数 = 0（类型规整无失败）。
4. C24 outputs：rows_read/rows_written=500、rows_skipped=0。

## 8. 验收方法
① 查库 SQL（数仓容器）：

```sql
SELECT COUNT(*) FROM datara_dw.i12_ods_order_raw;   -- 期望 500
SELECT COUNT(*), COUNT(DISTINCT order_no) FROM datara_dw.dwd_order_file;  -- 期望 500 / 500
SELECT COUNT(*) FROM datara_dw.dwd_order_file WHERE create_time IS NULL OR amount IS NULL;  -- 期望 0
```

② API curl：`GET /instances/{instanceId}` → file_sync 节点 outputs.rows_written=500；assert outputs.assert_ok=true。

③ 页面：实例详情三节点「成功」；C24「同步运行详情」读/写行数=500。

## 9. 运行要求
- 数据源：内置数仓-datara_dw；运行节点 1.9宿主机；prep：orders.csv 存在（工具自动保障）。

## 10. 日志查看
C24 日志含 `_filesync_` 暂存/读取与写行数；SQL 日志含影响行数；C25 日志「规则 3 项，不通过 0 项」。

## 11. 日志存放位置
`/mnt/lei/datara/logs/{instance_id}/{task_id}.log`。
