# E4 · 文件+库表混合加工（C22 临时表 → SQL ${tmp.*} JOIN 维表）

## 1. 意图
验证 C22「文件读取」注册临时数据的加工链路：CSV 维表经 C22 物化为临时表，SQL 以 `${tmp.<名>}` 引用并与库内事实表 JOIN 产出带维度的 DWD 表（C22 + C11 + C25 + 临时数据语义）。

## 2. 业务意义与作用
外部维表（地区映射等）常以文件交付。本用例证明：文件 → 临时表注册（table 形态、实例终态即清扫）→ `${tmp.*}` 引用 JOIN 事实表 → 行数不放大（LEFT JOIN 一对一）→ 维表全覆盖（region 无 NULL）。

## 3. 业务逻辑（DAG）

```
(开始) ──> [C22 读取维表CSV → 注册临时表 user_region] ──> [SQL 维表JOIN加工 dwd_order_region] ──> [C25 对账校验] ──> (结束)
```

## 4. 操作步骤
1. 前置：共享卷 `/datara/files`（宿主机 /mnt/lei/datara/files）存在 `i12_etl_user_region.csv`（user_id,region 两列，按 dw.ods_order 实际 user_id 全覆盖生成；工具 prep 自动生成）。
2. 页面新建工作流 `i12_E4_file_join_dim`。
3. 画布拖入：开始 → 文件读取(C22) → SQL(C11) → 数据校验(C25) → 结束，连线。
4. 按 §5 配置；SQL 节点登记结果表 `dwd_order_region`。
5. 保存 → 运行。

## 5. 逐节点配置参数与脚本

### 读取维表CSV（C22）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 来源模式 mode | manual（手动参数） | 或选文件源数据源（数据源中心 file 型） |
| 文件路径 path | i12_etl_user_region.csv | /datara/files 相对路径 |
| 格式 format / 编码 / 分隔符 / 首行表头 | csv / utf-8 / , / 开 | |
| 注册临时数据 register | 开 | |
| 临时数据名 tmpName | user_region | 小写字母开头 3~32 位 |
| 临时数据形态 kind | table（临时表全量物化） | |
| 物化目标数据源 targetDs | 内置数仓-datara_dw | |
| 保留策略 retention | immediate（实例终态清扫） | |

### 维表JOIN加工（C11，数据源=内置数仓-datara_dw）
```sql
DROP TABLE IF EXISTS dwd_order_region;
CREATE TABLE dwd_order_region AS
SELECT o.order_no, o.user_id, r.region, o.amount, o.status
FROM ods_order o LEFT JOIN ${tmp.user_region} r ON o.user_id = r.user_id;
```
- `${tmp.user_region}` 运行时渲染为物理临时表名（`{instance_id}_{node_id}_{name}`）。
- 结果表注册表：k=v=`dwd_order_region`。

### 对账校验（C25，校验对象=upstream，onFail=fail）
| 规则 | 值 | 说明 |
|---|---|---|
| rows | min=1 | 加工产物非空 |
| sql | `SELECT IF((SELECT COUNT(*) FROM dwd_order_region) = (SELECT COUNT(*) FROM ods_order), 1, 0)` | LEFT JOIN 行数=事实表（无 fanout） |
| sql | `SELECT IF((SELECT COUNT(*) FROM dwd_order_region WHERE region IS NOT NULL) = (SELECT COUNT(*) FROM dwd_order_region), 1, 0)` | 维表全覆盖 region 非空 |

## 6. 注意事项
- CSV 的 user_id 必须覆盖事实表全部 user_id（prep 按实际 distinct user_id 生成），否则 LEFT JOIN 产生 NULL region 触发闸门失败——这本身是维表质量闸门的正确行为。
- 维表 user_id 在 CSV 内唯一，JOIN 一对一不放大行数。
- retention=immediate：实例终态临时表被清扫；如需留档改 keep（转正式表）。

## 7. 验收标准
1. 实例终态 success，三个节点均成功。
2. C22 outputs：rows_count>0、tmp_name=user_region。
3. `dwd_order_region` 行数 = `ods_order` 行数；region 非空行数 = 总行数。

## 8. 验收方法
① 查库 SQL（数仓容器，运行中执行可见临时表；终态后已清扫）：

```sql
SELECT COUNT(*) FROM datara_dw.dwd_order_region;                                  -- 期望 = ods_order 行数
SELECT COUNT(*) FROM datara_dw.dwd_order_region WHERE region IS NULL OR region=''; -- 期望 0
SELECT COUNT(*) FROM information_schema.tables
 WHERE table_schema='datara_dw' AND table_name LIKE '%user_region%';               -- 终态后期望 0（清扫）
```

② API curl：`GET /instances/{instanceId}` → file 节点 outputs.tmp_name=user_region；assert outputs.assert_ok=true。

③ 页面：实例详情三节点「成功」；C22 节点可打开「数据预览检验」浮窗看抽样网格。

## 9. 运行要求
- 数据源：内置数仓-datara_dw；共享卷 /datara/files 可读（api/worker 双侧）。
- prep：维表 CSV 按 ods_order distinct user_id 生成（工具自动）。

## 10. 日志查看
C22 日志：`[file] 来源: … 列数=2 … [file] 物化临时表: datara_dw.{tmp 表名} … 已注册临时数据: user_region（table，ref=…，N 行，保留=immediate）`；SQL 日志含影响行数。

## 11. 日志存放位置
`/mnt/lei/datara/logs/{instance_id}/{task_id}.log`。
