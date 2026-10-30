# G1 · 定时 Shell 健康巡检 → 日志 + 通知（shell→delay→C26）

## 1. 意图
验证普通类「脚本巡检 + 延时 + 通知」链路：以 shell 节点执行容器/磁盘健康检查脚本（`df -h` + `docker ps`），delay 节点演示周期节流语义，尾联 C26「仅日志」通道将巡检结果写入任务日志，验证普通类工作流在批处理形态下跑通。

## 2. 业务意义与作用
数据平台日常运维需要周期性巡检：磁盘水位、容器存活、资源占用等。本用例把巡检做成可编排的工作流——shell 节点跑检查脚本、delay 控制触发频率、C26 把结果记入日志（后续可升级为 webhook 告警），是「脚本即任务」零代码运维的典型场景。

## 3. 业务逻辑（DAG）

```
(开始) ──> [shell: 健康巡检脚本] ──> [delay: 60s 演示节流] ──> [C26: 仅日志通知] ──> (结束)
```

## 4. 操作步骤
1. 任务中心 →「批处理」页签 → 新建工作流 `i12_G1_shell_health_check`。
2. 画布拖入：`shell` → `delay` → `notify(C26)`，连线。
3. 按 §5 配置三个节点参数；保存 → 运行。
4. 等待实例成功后按下章验收。

## 5. 逐节点配置参数与脚本

### Shell 巡检脚本（C12）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `shell` | Shell 执行器 |
| 脚本 script | 见下方「巡检脚本」 | bash 执行，stdout 逐行实时日志 |
| 环境变量 env | （空） | 使用默认环境 |

```bash
# 巡检脚本（G1）：磁盘 + 容器健康
echo "===== 磁盘水位 ====="
df -h | grep -E "/$|/mnt" | awk '{print $5, $6}'
echo "===== Datara 容器状态 ====="
docker ps --format '{{.Names}}\t{{.Status}}' 2>/dev/null | grep datara || echo "(docker 命令不可用，忽略)"
echo "===== 内存 ====="
free -m 2>/dev/null | head -2 || echo "(free 不可用)"
echo "巡检完成 @ $(date '+%Y-%m-%d %H:%M:%S')"
```

### 延时节点（C8 delay）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `delay` | 延时执行 |
| 延时时长 duration | `60` | 演示节流语义 |
| 单位 unit | `秒` | |

> delay 在批处理实例中表现为「暂停 60s 后继续下游」；生产场景以变量 `${cron_next}` 等到点延时（F49 时间变量），本用例用固定值演示机制。

### C26 通知（仅日志通道）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `notify` | 通知节点 |
| 通道 channel | `仅日志` | 结果写入任务日志，不发 webhook |
| 触发时机 trigger | `上游成功` | 巡检脚本成功后记录 |
| 消息模板 template | `G1 巡检完成 实例=${instance_id} 节点=${node.name} @ ${sys.now}` | 变量由四级链解析 |
| 通知失败断流 failHard | `false` | 仅日志，无断流风险 |

## 6. 注意事项
- shell 节点 stdout 逐行实时写入任务日志，`echo` 输出即为验收证据；exit 0 → success。
- 巡检脚本在 worker 容器内执行（`docker ps`/`df` 反映 worker 宿主视角），若 worker 容器内无 docker 命令则对应行输出不可用提示——非缺陷，脚本继续。
- delay 60s 会使实例总耗时 +60s，验收时注意实例终态判断需等待该时长。
- C26 通道=「仅日志」时 url 可不填，`failHard` 无效。
- 幂等：重跑前无需清表（无写库），可重复执行。

## 7. 验收标准
1. 实例终态 `success`，日志无 ERROR / Traceback。
2. 任务日志含 shell 输出关键字：`磁盘水位`、`Datara 容器状态`、`巡检完成`。
3. 日志含 C26 通知记录：`[notify]` + 消息模板渲染后的文本（含实例 ID）。
4. 实例耗时 ≥60s（delay 生效实证）。

## 8. 验收方法
① 查库 SQL：本用例无落库（纯日志输出），不适用。

② API curl：
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
# 取最新 i12_G1 实例
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/instances?wf_name=i12_G1_shell_health_check&page_no=1&page_size=1" | python3 -c '
import sys,json; rows=json.load(sys.stdin).get("list") or []
inst=rows[0]; print("status:", inst.get("status"), "id:", inst.get("id"), "duration_ms:", inst.get("duration_ms"))'
# 期望：status=success，duration_ms>=60000
# 拉日志尾 50 行
INSTANCE_ID=<实例id>
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/instances/$INSTANCE_ID/logs?tail=50"
# 期望：含 "巡检完成" 与 "[notify]" 关键字
```

③ 页面：任务中心 → 批处理 → 实例列表 → 最新实例「成功」；点日志查看含巡检输出与 notify 记录；截图 `shots/G1-shell健康巡检.png` 留档。

## 9. 运行要求
- 数据源：无（纯脚本 + 日志）。
- 外部服务：无。
- 账号权限：普通用户可创建/运行自身工作流。

## 10. 日志查看
页面「任务中心 → 运行 → 日志」在线查看；容器内 `/datara/logs/{instance_id}/{task_id}.log`（口径以 master 实配 log_dir 为准，1.9 挂载至 `/mnt/lei/datara/logs`）。关键字：`[shell]` 脚本执行、`巡检完成`、`[notify]` 通知记录、`Traceback`。

## 11. 日志存放位置
宿主机 `/mnt/lei/datara/logs/{instance_id}/{task_id}.log`。排查顺序：实例终态 → 日志尾 50 行（含 shell stdout）→ `[notify]` 节点日志 → worker 容器 `docker logs datara-worker --tail 200`。
