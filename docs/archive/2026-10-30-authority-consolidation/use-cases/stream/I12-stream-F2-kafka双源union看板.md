# F2 · Kafka 双源 Union 合并 → API + 实时看板（kafka→union→api/board）

## 1. 意图
验证流类「多源汇流」能力：两个独立 Kafka 主题（订单流 + 点击流）经 Union 合并为一路，同时投向 API 订阅通道与页面实时看板（C20 看板通道 preset=ecommerce），验证双源行混合透传、看板实时刷新与断流单路自恢复。

## 2. 业务意义与作用
实时大屏往往需要把多个业务流（交易、流量、用户行为）合并后统一展示或消费。Union 保持行级原样透传、不做关联，是分流治理（解析→规范化→多路复用）的聚流层；本用例同时验证页面看板的实时刷新链路（源→window→union→board 的零代码可视化）。

## 3. 业务逻辑（DAG）

```
(kafka: order_pay) ──┐
                     ├──> [union] ──> (api out)
(kafka: user_click) ─┘                    └──> (page_board ecommerce)
```

## 4. 操作步骤
1. 前置：Kafka 数据源 `i12_kafka_local`（id=25）就绪；`order_pay`/`user_click` 两 topic 持续灌数。
2. 任务中心 →「流任务」页签 → 新建工作流 `i12_F2_kafka2_union_board`。
3. 画布拖入：2×`stream_input`(kafka) → `stream_fuse`(union) → `stream_output`(api) + `page_board`(ecommerce)，连线（union→api→board 串联）。
4. 按 §5 配置；保存 → 启动流任务。
5. 等 1~2 个窗口周期，按下章取证（API + 页面看板截图）。

## 5. 逐节点配置参数与脚本

### 流输入 Kafka ×2（srcType=kafka）
| 字段（表单键） | 值（左/右） | 说明 |
|---|---|---|
| 节点类型 type | `stream_input` | 流数据源 |
| 源类型 srcType | `kafka` | 消息源 |
| 数据源 dsRef | `i12_kafka_local` | 共用注册 kafka 资产（id=25） |
| topic | `order_pay` / `user_click` | 双主题分别入两源节点 |
| group | `datara-flink` | 消费组，位点持久化 |

### Union 合并（fuseType=union）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_fuse` | 流算子 |
| 融合类型 fuseType | `union` | 多路汇流 |
| 对齐映射 alignMap | `[]` | 空=同名透传，不重命名不裁剪 |

### API 输出（outType=api）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_output` | 流输出 |
| 输出通道 outType | `api` | Last-N 订阅通道 |
| 保留条数 keepLast | `600` | 双源混合行速率高，留足缓冲 |
| schemaText | （空） | 原样透出 |

### 实时看板（page_board）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `page_board` | 可视化看板节点 |
| 预设 preset | `ecommerce` | 电商实时大盘预设（示例化 chart） |

## 6. 注意事项
- Union 不做 key 对齐与去重：同一条消息只透传一次（不复制），双源行按到达顺序混合。
- 看板节点挂在 api 输出下游，属同一链路端点；看板聚合基于窗口行的 `win_start` 分桶刷新。
- 断流恢复：两路独立 kafka 源各自维护位点；停 kafka 期间两路同时断，复启后按位点续跑（与 F1 同机制）。抽测时先停其他 kafka 源任务。
- 页面证看板须等数据到达（面板有数字）后再截图，避免空面板。

## 7. 验收标准
1. 流任务 `running`，`lastError` 为空，日志无 ERROR / Traceback。
2. API 通道行混合两路事件：`event` 集合含 `order_pay` 与 `user_click`；窗口聚合行（`win_start` 非空）存在。
3. 页面看板（ecommerce preset）显示实时数据，无报错面板。
4. 断流恢复：stop kafka 10s 复启后任务保持 running，恢复后两路事件继续混合到达。

## 8. 验收方法
① 查库 SQL：不适用落库（同 F1，本用例 API+看板为数据出口）。

② API curl：
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/stream-jobs | python3 -m json.tool   # 目标 job running
JOB_ID=<job_id>
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/stream-jobs/$JOB_ID/data?mode=poll&limit=800" | python3 -c '
import sys,json; rows=json.load(sys.stdin).get("rows") or []
print("events:", sorted({r.get("event") for r in rows if r.get("event")}))
print("win rows:", len([r for r in rows if r.get("win_start") is not None]))'
# 期望：events 含 order_pay 与 user_click；win rows >= 1
```

③ 页面：任务中心 → 流任务 → 实例详情运行中；进入对应工作流画布 → 看板/预览面板显示实时数字；截图 `shots/F2-kafka双源union看板.png` 留档。

## 9. 运行要求
- 数据源：`i12_kafka_local`（id=25）。
- 外部服务：kafka + seed_stream 灌数（order_pay eps=5、user_click eps=3，可双路运行）。
- 账号权限：view_all。

## 10. 日志查看
任务中心 → 流任务 → 运行日志；关键字 `[stream]` 双源连接、`Traceback`、`窗口触发投递失败`。容器内 `/datara/logs/{job_id}/{task_id}.log`。

## 11. 日志存放位置
宿主机 `/mnt/lei/datara/logs/{job_id}/{task_id}.log`。排查顺序：job 状态 → lastError → `docker logs datara-worker --tail 200` → task 日志。