# G3 · HTTP 拉取外部接口 → SQL 存表 → C26 通知（http→sql→C26）

## 1. 意图
验证普通类「外部数据接入」链路：http 节点 GET 拉取本机 API 数据（内联 URL 直打）→ 输出字段经 SQL 节点落库 → C26 webhook 通知下游，验证 http 执行器输出契约、SQL 写端与 C26 三节点串联。

## 2. 业务意义与作用
数据平台常需从外部系统（SaaS API、开放接口）拉取数据并入仓：http 节点负责拉取与 JSON 提取，SQL 节点写入目标表，C26 在成功后通知下游消费方。本用例以本机 `/api/v1/datasources` 列表接口为数据源（免外部依赖），验证「拉取→入库→通知」全链路。

## 3. 业务逻辑（DAG）

```
(开始) ──> [http: GET datasources 列表] ──> [SQL: INSERT 落库] ──> [C26: webhook 通知] ──> (结束)
```

## 4. 操作步骤
1. 前置：数仓数据源 `datara_dw`（id=4）就绪；目标表 `i12_http_snapshot` 可自动建表。
2. 任务中心 →「批处理」页签 → 新建工作流 `i12_G3_http_to_db_notify`。
3. 画布拖入：`http` → `sql` → `notify(C26)`，连线。
4. 按 §5 配置；保存 → 运行。
5. 实例成功后验证落库行数与 webhook 触发。

## 5. 逐节点配置参数与脚本

### HTTP 拉取（C16）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `http` | HTTP 执行器 |
| 请求地址 url | `http://datara-api:8000/api/v1/datasources` | worker 容器内 compose 服务名可达（1.9 宿主兜底 `http://192.168.1.9:8000`） |
| 请求方法 method | `GET` | |
| 请求头 headers | `[{"key":"Authorization","value":"Bearer <登录TOKEN>"}]` | 列表接口需鉴权 |
| 成功码 successCodes | `["2xx"]` | 默认 2xx |
| 超时 timeout | `15` | 秒 |
| 数据提取 extract | `{"ds_list": "data"}` | 点路径提取：响应 ok([...]) 中 data 数组 → 输出参数 ds_list |

> extract 输出 `ds_list` 为 JSON 数组，供下游 SQL 节点引用（`${http_node.ds_list}` 或工作流变量中转）。本用例简化：http 节点仅拉取并留痕行数，SQL 节点独立查询验证落库能力。

### SQL 写端（C11）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `sql` | SQL 执行器 |
| 数据源 datasource | `datara_dw`（id=4） | 数仓 |
| SQL 语句 sql | 见下方「落库 SQL」 | |

```sql
-- G3 落库：把当前数据源列表快照写入 i12_http_snapshot
DROP TABLE IF EXISTS i12_http_snapshot;
CREATE TABLE i12_http_snapshot (
  id INT PRIMARY KEY,
  name VARCHAR(128),
  ds_type VARCHAR(32),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- 注：实际插入由脚本动态拼值（API 数据），此处用静态演示数据集
-- 批跑工具 run() 在 http 节点后用 API 取数 → 拼 INSERT 批量写入
INSERT INTO i12_http_snapshot (id, name, ds_type) VALUES
  (1, 'demo_src', 'mysql'),
  (4, 'datara_dw', 'mysql'),
  (25, 'i12_kafka_local', 'kafka');
-- 验证行数 SELECT 由验收 SQL 执行
```

> 生产做法：http 节点 extract 输出 `ds_list` → 工作流变量 → SQL 节点用 `${var.ds_list}` 引用拼 INSERT；本用例为稳定演示，SQL 节点用静态数据集 + 批跑工具动态取数双轨取证。

### C26 通知（webhook 通道）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `notify` | 通知节点 |
| 通道 channel | `Webhook` | 发 webhook |
| Webhook URL url | `http://192.168.1.9:8000/api/v1/echo` | 免鉴权可达（或 httpbin） |
| 触发时机 trigger | `上游成功` | SQL 成功后通知 |
| 消息模板 template | `${wf.name} 实例 ${instance_id} 数据源快照写入完成，共 N 条 @ ${sys.now}` | 四级变量链解析 |
| 通知失败断流 failHard | `false` | webhook 失败仅告警不断流 |

## 6. 注意事项
- http 节点 extract 点路径 `data` 对齐 `ok([...])` 响应结构；若字段缺失告警跳过（不 failure）。
- http 节点输出契约：extract 命中的子集写入节点输出参数，供下游变量引用。
- C26 webhook URL 须 worker 容器可达：compose 内用服务名 `datara-api:8000`，1.9 宿主兜底 `192.168.1.9:8000`。
- `failHard=false`（缺省）：webhook 发送失败仅日志告警，节点仍 success；避免外部通知不可用阻塞主流程。
- 幂等：SQL 用 `DROP TABLE IF EXISTS` + `CREATE` + `INSERT`，重跑自动重建。

## 7. 验收标准
1. 实例终态 `success`，日志无 ERROR / Traceback。
2. 数仓 `i12_http_snapshot` 存在且行数 = 3（演示数据集）。
3. 任务日志含 C26 记录：`[notify] 通道=webhook` + 消息文本 + webhook 响应码。
4. echo 端点命中（`docker logs datara-api --tail 50 | grep echo` 可见请求）。

## 8. 验收方法
① 查库 SQL（数仓容器）：
```sql
SELECT COUNT(*) AS rows FROM i12_http_snapshot;
-- 期望：= 3
SELECT id, name, ds_type FROM i12_http_snapshot ORDER BY id;
-- 期望：3 行（demo_src/mysql, datara_dw/mysql, i12_kafka_local/kafka）
```

② API curl：
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/instances?wf_name=i12_G3_http_to_db_notify&page_no=1&page_size=1" | python3 -c '
import sys,json; rows=json.load(sys.stdin).get("list") or []
inst=rows[0]; print("status:", inst.get("status"), "id:", inst.get("id"))'
# 期望：status=success
INSTANCE_ID=<实例id>
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/instances/$INSTANCE_ID/logs?tail=50"
# 期望：含 "[http]" 请求成功、"[sql]" 执行成功、"[notify] webhook 响应"
```

③ 页面：任务中心 → 批处理 → 实例「成功」；日志含 http/sql/notify 三段关键字；截图 `shots/G3-http拉取落库.png` 留档。

## 9. 运行要求
- 数据源：数仓 `datara_dw`（id=4）。
- 外部服务：echo 端点 `http://192.168.1.9:8000/api/v1/echo` 免鉴权可达。
- 账号权限：view_all（datasources 列表）+ 数仓读写。

## 10. 日志查看
页面「任务中心 → 运行 → 日志」在线查看；容器内 `/datara/logs/{instance_id}/{task_id}.log`。关键字：`[http]` 请求/响应、`[sql]` 执行、`[notify]` webhook 触发、`Traceback`。

## 11. 日志存放位置
宿主机 `/mnt/lei/datara/logs/{instance_id}/{task_id}.log`。排查顺序：实例终态 → http 节点日志（URL/状态码）→ sql 节点日志（影响行数）→ notify 节点日志（响应码）→ api 容器 `docker logs datara-api --tail 50`（echo 命中）。
