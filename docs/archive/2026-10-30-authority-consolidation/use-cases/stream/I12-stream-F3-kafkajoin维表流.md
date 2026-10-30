# F3 · Kafka 流 LEFT JOIN 维表流（order_pay ⋈ i12_dim_goods）

## 1. 意图
验证流类「双流 Join」能力：订单流（左表）与商品维表流（右表）按 `goods_id` 关联，JOIN 窗口内命中时把维表字段（商品名/类目）并入订单行，经 API 通道输出；同时验证 left join 未命中行保留（null 维表字段）与维表流断流恢复。

## 2. 业务意义与作用
实时流上的维度补齐是流式数仓的常见需求：交易明细流只有外键（goods_id），下游报表需要商品名称、类目等维度。与批处理 lookup 不同，流上维表以「维表流」形态存在（维表变更也走消息），Join 在时间窗口内做缓存匹配，避免每次外键命中都回查库。

## 3. 业务逻辑（DAG）

```
(kafka: order_pay) ─────────┐
                            ├──> [join goods_id, left, 60s] ──> (api out)
(kafka: i12_dim_goods) ─────┘    （命中：订单字段+维表字段合并）
```

## 4. 操作步骤
1. 前置：Kafka 数据源 `i12_kafka_local`（id=25）；`order_pay` 灌数；维表 topic `i12_dim_goods` 由维表灌数脚本（见 §5）持续投递 `{goods_id, name, category}`。
2. 任务中心 →「流任务」页签 → 新建工作流 `i12_F3_kafka_join_dim`。
3. 画布拖入：2×`stream_input`(kafka) → `stream_fuse`(join) → `stream_output`(api)，连线。
4. 按 §5 配置（join 键 goods_id、左连接、窗口 60s）；保存 → 启动。
5. 观察窗口后按下章取证。

## 5. 逐节点配置参数与脚本

### 流输入 Kafka ×2（srcType=kafka）
| 字段（表单键） | 值（流/维表） | 说明 |
|---|---|---|
| 节点类型 type | `stream_input` | 流数据源 |
| 源类型 srcType | `kafka` | 消息源 |
| 数据源 dsRef | `i12_kafka_local` | 共用注册 kafka 资产（id=25） |
| topic | `order_pay` / `i12_dim_goods` | 左流 + 右维表流 |
| group | `datara-flink` | 各自消费组（join 两侧独立源，位点各自持久化） |

### Join 算子（fuseType=join）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_fuse` | 流算子 |
| 融合类型 fuseType | `join` | 双流关联 |
| 左关联键 joinKeyLeft | `goods_id` | 订单流关联字段 |
| 右关联键 joinKeyRight | `goods_id` | 维表流关联字段 |
| 关联窗口 joinWindowSec | `60` | 缓存窗口秒数（行按 ts 修剪） |
| 关联类型 joinType | `left` | left：未命中保留左行，维表字段缺省 |

### API 输出（outType=api）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_output` | 流输出 |
| 输出通道 outType | `api` | Last-N 订阅通道 |
| 保留条数 keepLast | `600` | 留足缓冲 |
| schemaText | （空） | 原样透出 |

### 维表灌数脚本（批跑工具内置 `_kafka_send`，等价命令）
```bash
# 商品维表 3 条，持续循环重投（模拟维表流），与 order_pay 的 GOODS 集合对齐
for i in $(seq 1 100); do
  echo '{"goods_id":"g_1001","name":"无线鼠标","category":"数码"}'
  echo '{"goods_id":"g_1002","name":"机械键盘","category":"数码"}'
  echo '{"goods_id":"g_1003","name":"电竞椅","category":"家具"}'
done | docker exec -i datara-kafka kafka-console-producer --topic i12_dim_goods \
  --bootstrap-server localhost:9092
```
（批跑脚本内用 kafka-python 发送，效果一致；变量写法仅为文档可读。）

## 6. 注意事项
- **join 输出是原始行透出（不是窗口行）**：命中行 `{**左侧数据, **维表数据}`（同名键维表覆盖），未命中 left 行直接透出且无维表字段——API 通道据此区分命中/未命中。
- 关联窗口 60s 是**缓存修剪窗口**不是事件窗口：行只与窗口内已到达的对侧行匹配；两侧行须在 60s 内先后到达。
- JoinOp 未配置关联键会抛 `OpError`（配置期即失败）；两侧键名必须与行内真实字段一致（order_pay 事件 schema 含 `goods_id`）。
- 断流恢复：两侧独立源各自位点续跑；抽测前先停其他 kafka 源任务。
- 维表流必须**持续投递**（单次投递后 60s 缓存过期，后续订单将无命中）。

## 7. 验收标准
1. 流任务 `running`，`lastError` 为空，日志无 ERROR / Traceback。
2. API 通道出现命中行：行内同时含订单字段与维表字段（`name`/`category` 非空且非 None），`goods_id` 与维表一致。
3. left join 语义：存在未命中行（仅订单字段、无 `name` 键或为 null）不丢数据。
4. 断流恢复：stop kafka 10s 复启后，命中行继续产出（维表流恢复重投后命中恢复）。

## 8. 验收方法
① 查库 SQL：本用例无落库（API 通道为出口），join 正确性以 API 通道抽样核对（goods_id ↔ name/category 映射与灌数维表一致）。

② API curl：
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/stream-jobs | python3 -m json.tool   # 目标 job running
JOB_ID=<job_id>
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/stream-jobs/$JOB_ID/data?mode=poll&limit=800" | python3 -c '
import sys,json; rows=json.load(sys.stdin).get("rows") or []
hits=[r for r in rows if r.get("name")]
miss=[r for r in rows if r.get("goods_id") and not r.get("name")]
print("join hits:", len(hits), "sample:", (hits[-1] if hits else None))
print("left-miss rows:", len(miss))'
# 期望：hits >= 1 且 sample 含 name/category；miss >= 0（left 语义不丢）
```

③ 页面：任务中心 → 流任务 → 实例详情运行中；日志无 ERROR；截图 `shots/F3-kafkajoin维表流.png` 留档。

## 9. 运行要求
- 数据源：`i12_kafka_local`（id=25）。
- 外部服务：kafka；order_pay 灌数（eps=5）+ 维表流灌数（3 条循环）。
- 账号权限：view_all。

## 10. 日志查看
任务中心 → 流任务 → 运行日志；关键字 `[stream]` join 两侧源连接、`Traceback`。容器内 `/datara/logs/{job_id}/{task_id}.log`。

## 11. 日志存放位置
宿主机 `/mnt/lei/datara/logs/{job_id}/{task_id}.log`。排查顺序：job 状态 → lastError → `docker logs datara-worker --tail 200` → task 日志；重点核对两侧源 `consumed` 指标是否都在增长（任一侧为 0 说明消费组位点或 topic 未对齐）。