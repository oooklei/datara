# I12 数据治理工具 20 例验证汇总报告（P2.3 收官 · F 类+G 类）

日期：2026-09-24　环境：1.9 datara（api:8000 / web 隧道 18090）　方式：browser-use 页面级逐表单核对 + API 运行三证

## 一、结论总览

- S1~S5（离线批处理编排）、E1~E5（数据加工）、C 类数据集市资产链路：**P2.1/P2.2 已闭环**（见 i12_closeout.json 等前存档）
- **F1~F5 流类（实时流处理）**：画布节点配置与文档 §5 全量一致；F1 曾遇 Kafka broker 瞬时未就绪运行错误，重启后恢复，F1~F5 全部 running 无错误；F4 有真实窗口数据流。✅
- **G1~G5 普通类（批处理编排）**：由 tools/i12_general_usecases.py 在 1.9 建流+跑批（5 例 command 均 success、库/日志/文件三证齐备），并 browser-use 逐画布逐表单核对。✅
- **G1~G5 工具修正过程**：脚本原本存在 3 个与后端契约不一致的缺陷（`PUT /save` 端点、node 结构含 position、`file_read` 为未注册类型→改 `file`），逐一修复后全部 PASS；另确认 dw/adm 密码为 datara_2026、共享文件卷 worker 内路径为 /datara/files。

## 二、F 类流画布核对明细（browser-use + API）

| 用例 | wf | 流节点拓扑 | 核对结果 |
|---|---|---|---|
| F1 订单流(kafka)→聚合→api窗口 | wf_a48b0049 | s1 kafka(i12_kafka_local/order_pay/earliest/json) → w1 window(tumbling/10s/水位0) → o1 api(keepLast=600) | ✅ 3 节点全对 |
| F2 双流合并 | wf_32ff41fb | s1 order_pay + s2 user_click → w1/w2 10s 窗口 → u1 union(2上游) → o1 api + b1 page_board(ecommerce) | ✅ 7 节点全对 |
| F3 订单+商品 join | wf_aaec3124 | join(left/goods_id=goods_id/关联窗口60s) | ✅ 4 节点全对 |
| F4 HTTP 轮询告警 | wf_dc0c47f7 | s1 http GET /api/v1/stream-jobs(5s,dataPath=data) → f1 filterExpr(`status=='running' and wfName!='i12_F4_http_threshold'`) → w1 tumbling 5s groupKeys=status → o1 api(600) | ✅ 4 节点全对（运行有真实计数流量 rate 0.4/s） |
| F5 聚合落库 | wf_3fedba8b | s1 kafka(order_pay) → w1 window(10s, aggs amount:sum:amt_total + order_id:count:cnt) → o1 table→datara_dw.i12_stream_agg(uniqueKey=win_start, batch=500) | ✅ 3 节点全对 |
| F4_notify（批处理） | wf_5f700124 | start → fork(2) → nd_ok sql(SELECT 1;) / nd_bad sql(SELECT * FROM no_such_table) → merge(OR) → notify(webhook/always/echo) → end；实例 success | ✅ 7 节点全对 |

F 类运行状态：stream-job 25~29（F1~F5）全部 running；F1 修复记录：启动时 broker 未就绪 → `POST /stream-jobs/start`(doc_id) 重启后 lastError 清除。Kafka 系 tin/tout=0 属未灌数符合预期，F4 轮询 API 类有真实窗口行（cnt:3 等）。

## 三、G 类批处理核对明细（工具三证 + browser-use 逐表单）

| 用例 | wf( code ) | 画布拓扑 | 核对结果 |
|---|---|---|---|
| G1 定时 shell 巡检 | wf_dbe357ae(81) | start → shell(健康巡检/磁盘·容器·内存@date) → delay(60s) → notify(log/on_success) → end | ✅ 5 节点 |
| G2 python 文件清洗归档 | wf_de86dab5(82) | start → python(CSV清洗 strip去空行) → file(C22 读 cleaned_orders.csv 注册 tmp 表) → end | ✅ 4 节点 |
| G3 HTTP拉取落库通知 | wf_53beadd0(85) | start → http(GET datasources/2xx/15s) → sql(建 i12_http_snapshot 3 行) → notify(webhook/echo) → end | ✅ 5 节点 |
| G4 SSH 多节点 fork 批执行 | wf_4e55887a(83) | start → fork(parallel=2) → ssh×2(1.9宿主机 hostname;date,30s) → join(AND) → end | ✅ 6 节点 |
| G5 数据出仓归档 | wf_07a4e5cf(84) | start → sql(查 ods_order) → python(pymysql 导出 250000 行→export/ods_order_archive.csv)→ notify(webhook 完成) → end | ✅ 5 节点 |

G 类运行三证：G1/G2/G3/G4/G5 command(160/164/167/162/166) 全部 success；G3 落库 i12_http_snapshot=3 行；G2 csv=501 行、G5 csv=250001 行；G4 ssh 双节点≥2。

## 四、修复与发现（本轮）

1. `i12_general_usecases.py` 三处契约修正：save 用 `PUT /workflow-definitions/{id}/save`；node 用 `position:{x,y}` 结构；`file_read` 类型不存在→用注册的 `file`(C22)。
2. dw/src mysql root 密码 datara_2026（非 Datara@123），docker exec 探测以 t_data_source.pwd 为准。
3. worker 容器共享文件卷=宿主机 /mnt/lei/datara/files ↔ /datara/files；python/shell 节点运行目录 /datara/tmp/{instance_id}。
4. batch run 返回 {commandId}（master 异步建实例），实例主键在 /instances?wf_code= 列表的 instanceId 字段。
5. 画布打开：普通类 `/#/dag?tab=edit&type=wf&doc=<uuid>`；流类 type=stream。

## 五、证据落盘

- i12_general_g1g5.json（G1~G5 全量节点表单核对 + 运行三证）
- i12_board_cat_dom.json 等（P2.1/P2.2 归档）
- browser-use 原始输出（bu_g1~g5.py 的 G*_NODES/G*_INSP_* 行）