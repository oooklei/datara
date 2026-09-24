# F4 · HTTP 轮询源 + 阈值过滤触发（http→filter→window→api，C26 尾联）

## 1. 意图
验证流类「外部 HTTP 触发」链路：以 /stream-jobs 列表接口为 HTTP 数据源（内联 httpUrl 轮询模式），`filter` 前置过滤出「其他运行中流任务」行，`window` 按 status 分组计数产出阈值行（running_cnt），供下游消费判断「是否有流任务在跑」；尾联 C26「无论成败」用批处理画布（`i12_F4_notify`）双实例（成功/故意失败）触发 webhook 校验。

## 2. 业务意义与作用
调度治理中常需「阈值触发」：外部系统按固定间隔轮询某个服务状态，当指标越过阈值（如运行中任务数 >= 1）时触发通知。本用例把该逻辑做成流：HTTP 源周期拉取状态列表 → 过滤器只保留关心的行（排除任务自身，防止自环自触发）→ 窗口聚合出计数 → 下游消费阈值；同时用 C26 通知节点验证「上游成功或失败都触发 webhook」（always 触发语义），是告警类场景的零代码实现。

## 3. 业务逻辑（DAG）

```
(http 轮询 /stream-jobs) ──> [filter: status=running 且 wfName≠自身] ──> [window 10s 按 status 计数 cnt] ──> (api out)

【C26 尾联 - 批处理画布 i12_F4_notify】
(开始) ──> [SQL 成功实例] ──> [C26 notify(always)] ──> (结束)
       └─ [SQL 故意失败实例] ──> [C26 notify(always)] ──> (结束)
```

## 4. 操作步骤
1. 前置：登录获取 `$TOKEN`（供 http 内联源请求头与后续 API 取证）；确认至少存在 1 个其他流任务（F1/F2/F3/F5 任一）可被观察到 running。
2. 任务中心 →「流任务」页签 → 新建工作流 `i12_F4_http_threshold`。
3. 画布拖入：`stream_input`(http) → `stream_fuse`(filter) → `stream_fuse`(window) → `stream_output`(api)，连线。
   **filter 必须置于 window 之前**（window 透传原始行 + 聚合行：filter 若在 window 后引用 `cnt`，对透传原始行求值会抛 NameError 令任务失败——见 §6）。
4. 按 §5 配置；保存 → 启动；等待 ≥2 个窗口周期。
5. C26 尾联：批处理画布 `i12_F4_notify`（开始 → SQL 成功实例/故意失败实例 → notify → 结束），脚本自动跑两个实例断言通知均触发。

## 5. 逐节点配置参数与脚本

### 流输入 HTTP（srcType=http，内联模式）
> 1.9 未注册 http 资产 → 走「内联 httpUrl」直打模式（`resolve_ds_ref` 未命中注册资产即直接用参数 httpUrl）。

| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_input` | 流数据源 |
| 源类型 srcType | `http` | HTTP 轮询源 |
| 请求地址 httpUrl | `http://datara-api:8000/api/v1/stream-jobs` | 内联直打；worker 容器内按 compose 服务名可达（1.9 宿主侧兜底 `http://192.168.1.9:8000`） |
| 请求方法 httpMethod | `GET` | |
| 轮询间隔 intervalSec | `5` | 每 5s 拉一次 |
| 请求头 headers | `[{"key":"Authorization","value":"Bearer <登录TOKEN>"}]` | 列表页需 view_all 权限 → Bearer 鉴权 |
| 数据路径 dataPath | `data` | 响应 `ok([...])` 中数组字段名 |
| 游标参数 cursorParam / cursorPath | （空） | 本用例无需游标分页 |

### 阈值过滤（fuseType=filter，**前置**）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_fuse` | 流算子 |
| 融合类型 fuseType | `filter` | 行过滤（truthy 保留） |
| 过滤表达式 filterExpr | `status == 'running' and wfName != 'i12_F4_http_threshold'` | 只保留**其他**运行中任务行，排除自身防自触发 |

> 表达式基于 `simple_eval`，仅能引用当前行 data 内的字段：stream-jobs 列表行字段为 `{id, docId, wfName, name, status, lastError, startedAt, updatedAt, metrics}`，故 `status`/`wfName` 可直接引用。

### 窗口聚合（fuseType=window）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `stream_fuse` | 流算子 |
| 融合类型 fuseType | `window` | 滚动窗口 |
| 窗口大小 windowSizeSec | `10` | |
| 分组键 groupKeys | `status` | 按状态分组（过滤后仅 running 行，桶内全为 running） |
| 聚合 aggs | `[{"key":"status","value":"count:cnt"}]` | 桶内 running 任务数 |

### API 输出（outType=api）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 输出通道 outType | `api` | Last-N 订阅通道 |
| 保留条数 keepLast | `600` | 窗口行低速率 + 原始透传占缓冲，留足 |

### C26 尾联 — 批处理画布 `i12_F4_notify`
| 节点 | 配置要点 |
|---|---|
| 开始（C1） | 普通开始 |
| SQL 成功实例（C11） | `SELECT 1;`（必然成功） |
| SQL 故意失败实例（C11） | `SELECT * FROM not_exist_table_xyz;`（必然失败） |
| C26 通知 notify | `channel=webhook`、`url=http://192.168.1.9:8000/api/v1/echo`、`trigger=always`（无论上游成败都触发）、`failHard=true`（通知自身失败才断流） |
| 结束（C2） | 普通结束 |

```python
# 批跑工具 run() 内部语义：两个实例分别运行，断言两端
#   - 成功实例：运行终态 success
#   - 失败实例：上游 SQL 失败，但 notify 仍触发（trigger=always）→ webhook 命中 echo
```

## 6. 注意事项
- **filter 必须前置**：window（WindowAggOp.process）会把原始行透传下去；若 filter 位于 window 之后并引用聚合字段（如 `cnt`），引擎对透传原始行求值 `_safe_eval` 抛 NameError → `_fuse_loop` 捕获后 `rt.set_fail` → **整个流任务失败**（非坏行丢弃）。故阈值语义（cnt>=1）由脚本对窗口输出行（`win_start` 行）断言，filter 只引用原始行字段。
- **自环防护**：F4 自身也是 stream-jobs 列表里的 running 任务，filterExpr 必须排除 `wfName == 'i12_F4_http_threshold'`，否则窗口恒有 running 行、阈值恒命中。
- 动态性：启动 F4 前先启动另一个流任务（如 F1），列表才有「其他 running」行可过滤；停止其他任务后窗口不再产出 cnt>=1 行（脚本断言两相）。
- token 过期：内联 headers 里的 Bearer token 过期后 HTTP 源请求 401 → 拉不到列表（错误留痕但任务不 fail）；重部署时脚本重新取 token 注入。
- C26 的 `trigger=always` 是「无论上游成败都触发」；`failHard` 指通知节点自身失败才判失败——两者正交，双实例正好覆盖成功/失败两态。

## 7. 验收标准
1. 流任务 `running`，`lastError` 为空，日志无 ERROR / Traceback。
2. 窗口聚合行：存在 `win_start` 行且 `cnt >= 1`（此时有 F1 等其他任务 running）；停止其他任务后新窗口无 cnt>=1 行（脚本断言两相变化）。
3. filter 语义：API 通道无 `wfName == 'i12_F4_http_threshold'` 的行（自身被过滤，不产生自触发）。
4. C26 尾联：`i12_F4_notify` 成功实例终态 success、失败实例 notify 仍触发 webhook 命中 echo（2/2 断言）。

## 8. 验收方法
① 查库 SQL：HTTP 源数据本身在 API 通道（无落库）；C26 尾联仅走 notify webhook → echo 端点日志/响应码留痕（`docker logs datara-api --tail 50 | grep echo`）。

② API curl：
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
# 前置：确认有另一流任务 running
curl -s -H "Authorization: Bearer $TOKEN" localhost:8000/api/v1/stream-jobs | python3 -c '
import sys,json; rows=json.load(sys.stdin).get("data") or []
print("running others:", [r["wfName"] for r in rows if r.get("status")=="running"])'
JOB_ID=<F4的job_id>
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/stream-jobs/$JOB_ID/data?mode=poll&limit=800" | python3 -c '
import sys,json; rows=json.load(sys.stdin).get("rows") or []
win=[r for r in rows if r.get("win_start") is not None]
print("threshold win rows:", len(win), "latest cnt:", (win[-1].get("cnt") if win else None))
self_rows=[r for r in rows if r.get("wfName")=="i12_F4_http_threshold"]
print("self rows (should be 0):", len(self_rows))'
# 期望：win rows>=1 且 latest cnt>=1；self rows==0
# 停止其他流任务后再轮询：新窗口不再出现 cnt>=1 行
```

③ 页面：任务中心 → 流任务 → 实例详情运行中；日志无 ERROR；截图 `shots/F4-http阈值触发.png` 留档；C26 尾联在任务中心 → 批处理实例两个实例状态页留档。

## 9. 运行要求
- HTTP 源目标：`http://datara-api:8000/api/v1/stream-jobs`（worker 容器内 compose 网络；1.9 宿主兜底 `http://192.168.1.9:8000`），需 view_all 权限 Bearer。
- 前置状态：至少 1 个其他流任务（F1 等）处于 running 供阈值命中。
- C26 尾联：`http://192.168.1.9:8000/api/v1/echo` 免鉴权可达。

## 10. 日志查看
任务中心 → 流任务 → 运行日志；关键字 `[stream]` http 源轮询行数、`Traceback`；C26 尾联批处理日志关键字 `[notify]` webhook 触发/响应码。容器内 `/datara/logs/{job_id}/{task_id}.log`。

## 11. 日志存放位置
宿主机 `/mnt/lei/datara/logs/{job_id}/{task_id}.log`。排查顺序：F4 job 状态 → lastError（如 token 401 或 httpUrl 不可达）→ `docker logs datara-worker --tail 200` → task 日志。