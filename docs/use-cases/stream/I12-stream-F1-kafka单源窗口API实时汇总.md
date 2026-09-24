# F1 · Kafka 单源窗口聚合 → API 通道实时汇总（kafka→window→api）

## 1. 意图
验证流类主链路「消息源 → 窗口聚合 → API 订阅通道」在 /stream-jobs 形态下可跑通：Kafka 订单流按 10s 滚动窗口聚合金额/订单数/UV，聚合行经 API 通道供外部订阅，并验证窗口定时触发语义（`win_start/win_end` 时间桶）与断流恢复（kafka 短暂停摆后位点续跑）。

## 2. 业务意义与作用
实时订单大盘是流处理的典型场景：源端 Kafka 持续产生订单事件，下游需要按固定时间窗（如 10s）滚动输出 GMV/订单数/UV，供大屏或报表实时刷新。本用例同时覆盖流任务的健壮性要求——消息中间件短暂不可用后，任务恢复时从已提交位点续跑，不丢数据、不重复窗口。

## 3. 业务逻辑（DAG）

```
(kafka: order_pay) ──> [window 10s: sum(amount)→amt_total, count→ord_cnt, count_distinct(user_id)→uv] ──> (api out)
```

## 4. 操作步骤
1. 前置：Kafka 数据源 `i12_kafka_local`（数据源 id=25，brokers=`datara-kafka:9092`）就绪；`order_pay` topic 由批跑工具持续灌数。
2. 任务中心 →「流任务」页签 → 新建工作流 `i12_F1_kafka_window_api`。
3. 画布拖入：`stream_input`(kafka) → `stream_fuse`(window) → `stream_output`(api)，连线。
4. 按 §5 配置三个节点参数；保存 → 启动流任务（POST /stream-jobs/start）。
5. 等待 ≥2 个窗口周期后按下章验收方法取证。

## 5. 逐节点配置参数与脚本

### 流输入 Kafka（srcType=kafka）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_input` | 流数据源 |
| 源类型 srcType | `kafka` | 消息源 |
| 数据源 dsRef | `i12_kafka_local` | 注册 kafka 资产（id=25），brokers 取注册值 `datara-kafka:9092` |
| topic | `order_pay` | 订阅主题 |
| group | `datara-flink` | 消费组（默认），位点经 t_stream_offset 持久化 |
| startFrom | `earliest` | 无位点时从头消费 |

### 窗口聚合（fuseType=window）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_fuse` | 流算子 |
| 融合类型 fuseType | `window` | 滚动窗口 |
| 窗口类型 windowType | `tumbling` | 滚动窗口 |
| 窗口大小 windowSizeSec | `10` | 10s 一个桶 |
| 水位线 watermarkSec | `0` | 不延迟触发（演示精度） |
| 分组键 groupKeys | （空） | 全局汇总不分组 |
| 聚合 aggs | `[{key:amount, value:sum:amt_total}, {key:order_id, value:count:ord_cnt}, {key:user_id, value:count_distinct:uv}]` | 三聚合：GMV/订单数/UV |

### API 输出（outType=api）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_output` | 流输出 |
| 输出通道 outType | `api` | API 订阅通道（Redis List Last-N） |
| 保留条数 keepLast | `600` | 窗口行速率低，原始行透传占缓冲，须留足 |
| schemaText | （空） | 未声明列序则原样透出 |

## 6. 注意事项
- 窗口节点**原始行继续透传**（明细不阻断），API 通道同时含原始行与聚合行；按 `win_start` 字段区分聚合行（原始行无该键）。
- 窗口行由**定时线程**在水位线满足后触发投递（`now >= win_end + watermark`），故最多滞后一个桶周期；观察窗口须 ≥2 个窗口周期。
- 断流恢复：本用例已实现位点恢复（engine 以 t_stream_offset 持久化，source open 注入 `_saved` 并 seek）；抽测时 `docker stop datara-kafka` 会导致同一时刻所有 kafka 源任务一起断流，抽测前先停止其他 kafka 源任务、仅保留被测任务。
- 聚合行 `cnt` 语义：`count` 聚合 = 桶内行数；`count_distinct` 对任意类型值去重（user_id 为字符串也可用）。

## 7. 验收标准
1. 流任务状态 `running`，`lastError` 为空，日志无 ERROR / Traceback。
2. API 通道出现聚合行：`win_start` 时间桶递增，最近桶 `amt_total` 与订单量正相关（灌数 eps=5 时 10s 桶约 50 单、GMV>0、UV>1）。
3. 断流恢复：stop kafka 10s→复启后，任务保持 running，恢复后继续产出**新** `win_start` 桶行（位点续跑未丢窗）。

## 8. 验收方法
① 查库 SQL（数仓容器）：不适用落库，本用例以 API 通道为唯一数据出口（F5 覆盖落库路径）。

② API curl：
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/stream-jobs | python3 -m json.tool   # 目标任务 status=running
JOB_ID=<job_id>
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/stream-jobs/$JOB_ID/data?mode=poll&limit=800" | python3 -c '
import sys,json; d=json.load(sys.stdin); rows=d.get("data") or d.get("rows") or []
win=[r for r in rows if r.get("win_start") is not None]
print("win rows:", len(win), "latest:", max((r["win_start"] for r in win), default=None))
cur=[r for r in win if r["win_start"]==max(r["win_start"] for r in win)][0]
print("latest bucket:", cur.get("amt_total"), cur.get("ord_cnt"), cur.get("uv"))'
# 期望：win rows >= 2；latest bucket amt_total>0 且 ord_cnt>0 且 uv>1
```

③ 页面：任务中心 → 流任务 → 实例详情，运行状态「运行中」；日志无 ERROR；截图 `shots/F1-kafka单源窗口聚合.png` 留档。

## 9. 运行要求
- 数据源：`i12_kafka_local`（kafka，id=25，brokers=`datara-kafka:9092`）。
- 外部服务：kafka 容器 `datara-kafka`；灌数工具 seed_stream.py `--target kafka --brokers datara-kafka:9092 --duration 1800 --eps 5`（worker 容器内或 1.9 可达处执行）。
- 账号权限：view_all（流任务列表/启动均需）。

## 10. 日志查看
页面「任务中心 → 流任务 → 运行日志」在线查看；容器内 `/datara/logs/{job_id}/{task_id}.log`（口径以 master 实配 log_dir 为准，1.9 挂载至 `/mnt/lei/datara/logs`）。关键字：`[stream]` 源连接/消费位点、`窗口触发投递失败`（异常信号）、`Traceback`。

## 11. 日志存放位置
宿主机 `/mnt/lei/datara/logs/{job_id}/{task_id}.log`。失败排查顺序：job 状态 → lastError → worker 容器 `docker logs datara-worker --tail 200` → 对应 task_id 日志文件。