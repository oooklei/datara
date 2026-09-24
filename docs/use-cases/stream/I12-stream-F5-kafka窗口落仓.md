# F5 · Kafka 窗口聚合落库（kafka→window→TableSink→dw，下游手动汇总）

## 1. 意图
验证流类「结果落库」：Kafka 订单流按 10s 窗口聚合后经 **TableSink 库表通道**写入数仓 `datara_dw.i12_stream_agg`（批量 INSERT / upsert），并演示下游手动 SQL 汇总（R5「Dependent 不建调度壳」约束下，下游依赖手工/外部触发，不自动级联）。

## 2. 业务意义与作用
流处理结果需要沉淀到数仓供离线分析/报表复用：窗口聚合是高频小批写入。TableSink 支持 `uniqueKey` 命中即 `ON DUPLICATE KEY UPDATE`（窗口桶去重幂等），且按条数/1s 定时双触发批量 flush，兼顾吞吐与时效。落库后下游再做任意的批次化汇总（按天/按类目），形成「实时加工入仓 + 离线宽表消费」的混合架构。

## 3. 业务逻辑（DAG）

```
(kafka: order_pay) ──> [window 10s: sum(amount)→amt_total, count→cnt] ──> (TableSink → datara_dw.i12_stream_agg)
                                                                                  │
                                                                                  v
                                                         [手动] 下游 SQL 汇总（i12_stream_agg_daily 或直接 GROUP BY）
```

## 4. 操作步骤
1. 前置：数仓数据源 `datara_dw`（id=4）就绪；`order_pay` 灌数运行。
2. 任务中心 →「流任务」页签 → 新建工作流 `i12_F5_kafka_table_agg`。
3. 画布拖入：`stream_input`(kafka) → `stream_fuse`(window) → `stream_output`(table)，连线。
4. 按 §5 配置（TableSink 指定 outDs/outTable/outFieldMap/uniqueKey/outBatchSize）；保存 → 启动。
5. 等 ≥2 个窗口周期，验证落库行数与幂等性；随后在数仓执行下游汇总 SQL（Dependent 手动触发）。

## 5. 逐节点配置参数与脚本

### 流输入 Kafka（srcType=kafka）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_input` | 流数据源 |
| 源类型 srcType | `kafka` | 消息源 |
| 数据源 dsRef | `i12_kafka_local` | id=25，brokers=`datara-kafka:9092` |
| topic | `order_pay` | |
| group | `datara-flink` | 位点持久化 |

### 窗口聚合（fuseType=window）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_fuse` | 流算子 |
| 融合类型 fuseType | `window` | 滚动窗口 |
| 窗口大小 windowSizeSec | `10` | |
| 分组键 groupKeys | （空） | 全局汇总 |
| 聚合 aggs | `[{"key":"amount","value":"sum:amt_total"}, {"key":"order_id","value":"count:cnt"}]` | GMV + 订单数 |

### 库表输出（outType=table，TableSink）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_output` | 流输出 |
| 输出通道 outType | `table` | 库表通道 |
| 输出数据源 outDs | `datara_dw`（「内置数仓-datara_dw」，id=4） | lookup_datasource 按注册名解析连接 |
| 输出表 outTable | `i12_stream_agg` | 不存在自动建表（id BIGINT PK + 目标列 TEXT） |
| 字段映射 outFieldMap | `[{"key":"win_start","value":"win_start"}, {"key":"amt_total","value":"amt_total"}, {"key":"cnt","value":"cnt"}]` | 目标列 ← 流字段 |
| 唯一键 uniqueKey | `win_start` | 桶幂等：同桶重写（ON DUPLICATE KEY UPDATE） |
| 批量大小 outBatchSize | `500` | 条数或 1s 定时双触发 flush |

### 下游汇总 SQL（Dependent 手动触发，不建调度壳）
```sql
-- 手动跑批：按窗口桶日维度汇总（演示下游消费流落库产物）
DROP TABLE IF EXISTS i12_stream_agg_daily;
CREATE TABLE i12_stream_agg_daily AS
SELECT DATE(FROM_UNIXTIME(win_start)) AS biz_date,
       SUM(amt_total) AS gmv, SUM(cnt) AS orders
FROM i12_stream_agg
GROUP BY DATE(FROM_UNIXTIME(win_start));
```

## 6. 注意事项
- **TableSink 建表语义**：`outTable` 不存在时自动 `CREATE TABLE (id BIGINT AUTO_INCREMENT PRIMARY KEY, {cols} TEXT)`——列全部 TEXT；仅当 outFieldMap 未给定时才按行数据键自动推导列。target 列是 `win_start`（int 时间戳）时会以 TEXT 存储，下游汇总注意 `FROM_UNIXTIME(CAST(win_start AS UNSIGNED))` 或 CAST。
- **幂等**：`uniqueKey=win_start` 使同一窗口桶重复写入走 upsert；断流恢复后同桶行重写不产生重复行——验收以「win_start 唯一」为断。
- 与 F1 相比差异：F1 走 api 通道（内存 Last-N），F5 走库表通道（持久化），两者窗口/算子相同，验证「同一加工逻辑多出口」。
- 下游汇总为手动批次（R5：Dependent 不建调度壳），故第 4 步手工执行 SQL，不自动级联。
- 断流恢复：kafka 源位点续跑；恢复后新桶正常落库（同 F1 机制），旧桶因 upsert 不重复。
- 灌数持续期间表持续增长；验收断言取「某窗口桶存在且唯一」。

## 7. 验收标准
1. 流任务 `running`，`lastError` 为空，日志无 ERROR / Traceback。
2. 库内 `datara_dw.i12_stream_agg` 存在且 >0 行；`win_start` 列唯一（uniqueKey 幂等生效）；最近桶 `amt_total>0` 且 `cnt>0`。
3. 下游手动汇总 SQL 执行成功：`i12_stream_agg_daily` 生成且 `SUM(amt_total)=i12_stream_agg 全量 SUM`（行数按天聚合 ≤ 窗口桶数）。
4. 断流恢复：stop kafka 10s 复启后，新窗口桶继续落库且无重复 `win_start`。

## 8. 验收方法
① 查库 SQL（数仓容器，`MYSQL_PWD=... mysql -h 127.0.0.1 datara_dw`）：
```sql
SELECT COUNT(*) AS rows_total, COUNT(DISTINCT win_start) AS uniq_buckets,
       SUM(amt_total) AS gmv_total, SUM(cnt) AS order_total FROM i12_stream_agg;
-- 期望：rows_total>0 且 rows_total=uniq_buckets（upsert 幂等）；gmv_total>0
SELECT win_start, amt_total, cnt FROM i12_stream_agg ORDER BY win_start DESC LIMIT 3;  -- 最近桶
SELECT COUNT(*) FROM i12_stream_agg_daily;                                          -- 下游汇总产物>0
-- 汇总对账：
SELECT IF((SELECT SUM(amt_total) FROM i12_stream_agg_daily) =
          (SELECT SUM(amt_total) FROM i12_stream_agg), 1, 0);
```

② API curl：
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/stream-jobs | python3 -c '
import sys,json; rows=json.load(sys.stdin).get("data") or []
j=[r for r in rows if r.get("wfName")=="i12_F5_kafka_table_agg"][0]
print("status:", j.get("status"), "lastError:", j.get("lastError"))'
# 期望：status=running 且 lastError 空
```

③ 页面：任务中心 → 流任务 → 实例详情运行中；日志无 ERROR；截图 `shots/F5-kafka窗口落仓.png` 留档；数仓表 `i12_stream_agg` 在数据源浏览/查询页可见。

## 9. 运行要求
- 数据源：kafka `i12_kafka_local`（id=25，源）+ 数仓 `datara_dw`（id=4，落库）。
- 外部服务：kafka + seed_stream 灌数（order_pay eps=5）。
- 账号权限：view_all + 数仓读写（datara_dw 连接账号）。

## 10. 日志查看
任务中心 → 流任务 → 运行日志；关键字 `[stream]` TableSink `流输出建表: i12_stream_agg`、`flush` 成功/失败（SinkError 重连）、`Traceback`。容器内 `/datara/logs/{job_id}/{task_id}.log`。

## 11. 日志存放位置
宿主机 `/mnt/lei/datara/logs/{job_id}/{task_id}.log`。排查顺序：job 状态 → lastError → `docker logs datara-worker --tail 200` → task 日志；落库失败重点看 SinkError（数仓连接/权限/建表冲突）。