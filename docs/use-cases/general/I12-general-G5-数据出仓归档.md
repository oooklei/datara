# G5 · 数据出仓归档（SQL→python 导出 CSV→C26，不含跨工作流调度壳）

## 1. 意图
验证普通类「数据出仓/分发」链路：SQL 节点查询源表 → python 节点把查询结果导出为 CSV 到 SSH 共享目录 → C26 通知下游取件，验证 SQL→python→C26 三节点串联与跨节点文件传递（R5：不含跨工作流调度壳，Dependent 仅作触发说明预留）。

## 2. 业务意义与作用
数据出仓是数据分发的常见场景：把数仓中某表按条件查询后导出为 CSV，放到共享目录供下游系统（BI、合作方）取件。本用例验证「查询→导出→通知」全链路，并诚实标注跨工作流调度壳本期不做（R5 裁定），Dependent 组件保留后置。

## 3. 业务逻辑（DAG）

```
(开始) ──> [SQL: 查询源表] ──> [python: 结果→CSV 导出到共享目录] ──> [C26: webhook 通知取件] ──> (结束)

【预留】下游工作流（Dependent 触发说明，不建调度壳）：
  归档完成 ──(Dependent 语义)──> 下游订阅/消费（本期仅说明，不实现调度壳形态，R5）
```

## 4. 操作步骤
1. 前置：数仓 `datara_dw.ods_order` 有数据（S1 产物，250000 行）；SSH 共享目录 `/mnt/lei/datara/i12files/export/` 可写。
2. 任务中心 →「批处理」页签 → 新建工作流 `i12_G5_data_export_archive`。
3. 画布拖入：`sql` → `python` → `notify(C26)`，连线。
4. 按 §5 配置；保存 → 运行。
5. 实例成功后验证 CSV 文件存在、行数匹配、webhook 触发。

## 5. 逐节点配置参数与脚本

### SQL 查询（C11）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `sql` | SQL 执行器 |
| 数据源 datasource | `datara_dw`（id=4） | 数仓 |
| SQL 语句 sql | `SELECT order_id, user_id, amount, pay_time FROM ods_order ORDER BY order_id` | 全量查询（导出全表） |

> SQL 节点结果集作为输出参数（结果行）供下游 python 节点引用。本用例 python 节点独立重查（文件型导出不依赖节点间结果传递），SQL 节点主要验证查询能力 + 提供行数基准。

### Python 导出 CSV（C13）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `python` | Python 执行器 |
| 脚本 script | 见下方「导出脚本」 | 查询 + CSV 写共享目录 |
| 依赖清单 requirements | （空） | 仅用 stdlib |

```python
# G5 数据出仓：查询 ods_order → 导出 CSV 到共享目录
import csv, os, sys
from common.dsconn import open_connection, _lookup_datasource

DS_NAME = "datara_dw"
TABLE = "ods_order"
OUT_DIR = "/mnt/lei/datara/i12files/export"
OUT_FILE = os.path.join(OUT_DIR, "ods_order_archive.csv")

ds = _lookup_datasource(DS_NAME)
conn = open_connection(ds, db="datara_dw")
cur = conn.cursor()
cur.execute(f"SELECT order_id, user_id, amount, pay_time FROM {TABLE} ORDER BY order_id")

os.makedirs(OUT_DIR, exist_ok=True)
rows = 0
with open(OUT_FILE, "w", encoding="utf-8", newline="") as f:
    writer = csv.writer(f)
    cols = [d[0] for d in cur.description]
    writer.writerow(cols)
    for row in cur.fetchall():
        writer.writerow(row)
        rows += 1

cur.close()
conn.close()
print(f"[export] 导出 {rows} 行 → {OUT_FILE}")
# stdout 写入任务日志
```

> 实际执行器中 `_lookup_datasource`/`open_connection` 在 worker 进程内可用（同 sync.py/file_sync.py 模式）。若 worker 内 import 路径差异，批跑工具以 SQL 节点结果 + 脚本独立查询双轨保障。

### C26 通知（webhook 通道）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `notify` | 通知节点 |
| 通道 channel | `Webhook` | 通知下游取件 |
| Webhook URL url | `http://192.168.1.9:8000/api/v1/echo` | 免鉴权可达 |
| 触发时机 trigger | `上游成功` | 导出成功后通知 |
| 消息模板 template | `${wf.name} 数据出仓完成 文件=ods_order_archive.csv 行数=N 路径=/mnt/lei/datara/i12files/export/ @ ${sys.now}` | 四级变量链解析 |
| 通知失败断流 failHard | `false` | 通知失败仅告警不断流 |

### Dependent 触发说明（预留，不实现）
> R5 裁定：跨工作流调度壳本期不做。下游工作流若需「归档完成后自动触发消费」，语义上通过 Dependent 组件配置（依赖本工作流最近一次 success 实例），但**不建调度壳用例**——本期仅保留此说明，Dependent 组件已在 C9 实现，后续可直接引用。

## 6. 注意事项
- python 节点导出路径 `/mnt/lei/datara/i12files/export/` 是共享卷挂载（worker 与 api 同路径约定），确保 worker 可写。
- CSV 列序 = SQL 查询列序（order_id, user_id, amount, pay_time），下游取件按列名解析。
- 导出全表 250000 行可能耗时数秒至数十秒（取决于数仓连接），实例耗时验收不设上限。
- C26 `failHard=false`：webhook 失败仅日志告警，不阻塞归档主流程（通知是辅助，文件已落盘即成功）。
- 幂等：CSV 覆盖写（同路径同名），重跑直接覆盖；共享目录定期清理归档（保留策略由运维定）。

## 7. 验收标准
1. 实例终态 `success`，日志无 ERROR / Traceback。
2. 共享目录存在 `ods_order_archive.csv`，数据行数 = `datara_dw.ods_order` 行数（250000）。
3. 任务日志含导出统计：`[export] 导出 N 行 → /mnt/lei/datara/i12files/export/ods_order_archive.csv`。
4. 日志含 C26 记录：`[notify] 通道=webhook` + 消息 + 响应码。

## 8. 验收方法
① 查库 SQL（数仓容器，行数基准）：
```sql
SELECT COUNT(*) AS src_rows FROM datara_dw.ods_order;
-- 期望：250000（S1 产物）
```

文件行数核对（worker 容器内）：
```bash
docker exec datara-worker bash -c 'wc -l < /mnt/lei/datara/i12files/export/ods_order_archive.csv'
# 期望：= src_rows + 1（表头行）
```

② API curl：
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/instances?wf_name=i12_G5_data_export_archive&page_no=1&page_size=1" | python3 -c '
import sys,json; rows=json.load(sys.stdin).get("list") or []
inst=rows[0]; print("status:", inst.get("status"), "id:", inst.get("id"), "duration_ms:", inst.get("duration_ms"))'
# 期望：status=success
INSTANCE_ID=<实例id>
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/instances/$INSTANCE_ID/logs?tail=30"
# 期望：含 "[export] 导出" 与 "[notify] webhook 响应"
```

③ 页面：任务中心 → 批处理 → 实例「成功」；日志含导出统计与 notify 记录；截图 `shots/G5-数据出仓归档.png` 留档。

## 9. 运行要求
- 数据源：数仓 `datara_dw`（id=4）。
- 外部服务：echo 端点 `http://192.168.1.9:8000/api/v1/echo` 免鉴权可达。
- 前置数据：`datara_dw.ods_order` 有数据（S1 产物）。
- 账号权限：数仓读写 + view_all。

## 10. 日志查看
页面「任务中心 → 运行 → 日志」在线查看；容器内 `/datara/logs/{instance_id}/{task_id}.log`。关键字：`[sql]` 查询执行、`[python]` 脚本执行、`[export]` 导出统计、`[notify]` webhook 触发、`Traceback`。

## 11. 日志存放位置
宿主机 `/mnt/lei/datara/logs/{instance_id}/{task_id}.log`。排查顺序：实例终态 → sql 节点日志（查询行数）→ python 节点日志（导出统计）→ 共享目录确认 CSV 存在 → notify 节点日志（响应码）→ api 容器 echo 命中。
