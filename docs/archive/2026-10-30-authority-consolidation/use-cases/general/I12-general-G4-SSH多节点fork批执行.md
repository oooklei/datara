# G4 · SSH 多节点 Fork/Join 并行批执行（ssh×N→fork→join）

## 1. 意图
验证普通类「多主机并行批处理」链路：fork 节点把单输入分发到 N 路 ssh 节点（每节点 `hostname; date` 脚本），join 汇合后结束，验证 fork/join 并行编排、ssh 执行器节点寻址与并行时间戳重叠实证。

## 2. 业务意义与作用
运维批执行（批量打补丁、批量采集、批量重启）需要在多台主机上并行跑同一脚本。fork/join 把「N 次串行」变成「1 次并行」，join 等待全部完成后继续下游。本用例验证 fork 并行度、ssh 节点标签/runtimeNode 寻址与并行时间戳重叠（实证并行非串行）。

## 3. 业务逻辑（DAG）

```
(开始) ──> [fork 并行度=2] ─┬─> [ssh: 节点A hostname;date] ─┐
                            └─> [ssh: 节点B hostname;date] ─┴─> [join] ──> (结束)
```

## 4. 操作步骤
1. 前置：≥2 个 SSH 节点注册（t_runtime_node + t_ssh_node），host/port/凭证可达。
2. 任务中心 →「批处理」页签 → 新建工作流 `i12_G4_ssh_fork_parallel`。
3. 画布拖入：`fork` → `ssh` × 2 → `join`，连线（fork 两出口分别接两 ssh，两 ssh 接 join 两入口）。
4. 按 §5 配置（fork 并行度=2、两 ssh 节点各指定目标主机）；保存 → 运行。
5. 实例成功后验证两节点并行时间戳重叠。

## 5. 逐节点配置参数与脚本

### Fork 并行分叉（C5）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `fork` | 并行分叉 |
| 并行度 parallel | `2` | 分发到 2 路下游 |

### SSH 节点 A（C14，runtimeNode 寻址）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `ssh` | SSH 执行器 |
| 执行节点 runtimeNode | `<节点A名称或id>` | 按名称查 t_runtime_node，纯数字兜底按 id |
| 脚本 script | `hostname; date '+%Y-%m-%d %H:%M:%S'` | 输出主机名与当前时间 |
| 超时 timeout | `30` | 秒 |

### SSH 节点 B（C14，runtimeNode 寻址）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `ssh` | SSH 执行器 |
| 执行节点 runtimeNode | `<节点B名称或id>` | 第二台主机 |
| 脚本 script | `hostname; date '+%Y-%m-%d %H:%M:%S'` | 同上 |
| 超时 timeout | `30` | 秒 |

> 也可用 execNodeTag（I7 标签路由）替代 runtimeNode：任务参数带节点标签 → 在线且含该标签的节点轮转尝试。本用例用 runtimeNode 精确指定。

### Join 汇合（C6）
| 字段（表单键） | 值 | 说明 |
|---|---|---|
| 节点类型 type | `join` | 汇合（AND） |
| （无额外参数） | — | 等待全部上游分支完成后触发 |

## 6. 注意事项
- fork 并行度须与实际下游分支数一致（=2），否则多余分支无输入不触发、不足分支少一路。
- join 是 AND 语义：两路 ssh 都 success 才触发下游；任一路 failure 则 join 等待直至超时/失败。
- ssh 节点 stdout（`hostname` 输出 + `date` 时间戳）逐行写入任务日志，是并行重叠的实证依据。
- **并行实证**：两 ssh 节点日志的 `date` 时间戳应在同一秒窗口内（非先后差 30s 以上），证明 fork 是真并行。
- ssh 凭证：cred "-----BEGIN" 开头按私钥内容（RSA/Ed25519/ECDSA 依次尝试），否则按密码明文。
- 幂等：重跑无需清理（无写库），但须确保两节点持续在线可达。

## 7. 验收标准
1. 实例终态 `success`，日志无 ERROR / Traceback。
2. 两 ssh 节点日志各含 `hostname` 输出（不同主机名）+ `date` 时间戳。
3. 并行实证：两节点 `date` 时间戳差 < 5s（证明同时执行，非串行）。
4. join 节点日志显示「全部上游完成」后触发结束。

## 8. 验收方法
① 查库 SQL：本用例无落库（纯远程脚本），不适用。

② API curl：
```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["data"]["token"])')
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/instances?wf_name=i12_G4_ssh_fork_parallel&page_no=1&page_size=1" | python3 -c '
import sys,json; rows=json.load(sys.stdin).get("list") or []
inst=rows[0]; print("status:", inst.get("status"), "id:", inst.get("id"), "duration_ms:", inst.get("duration_ms"))'
# 期望：status=success
INSTANCE_ID=<实例id>
# 拉两 ssh 节点日志（task_id 在实例任务列表中）
curl -s -H "Authorization: Bearer $TOKEN" "localhost:8000/api/v1/instances/$INSTANCE_ID/tasks" | python3 -c '
import sys,json; tasks=json.load(sys.stdin).get("list") or []
for t in tasks:
    if t.get("node_type")=="ssh":
        print(t.get("name"), "status:", t.get("status"), "duration_ms:", t.get("duration_ms"))'
# 期望：两 ssh 节点均 success，duration_ms 相近（并行）
```

③ 页面：任务中心 → 批处理 → 实例「成功」；DAG 染色两 ssh 节点同色（并行）；日志含两主机名 + 时间戳；截图 `shots/G4-ssh多节点并行.png` 留档。

## 9. 运行要求
- 数据源：无（远程节点直连）。
- 外部服务：≥2 台 SSH 主机在线可达（注册于 t_runtime_node + t_ssh_node）。
- 账号权限：SSH 连接账号（root 或具 bash 权限用户）。

## 10. 日志查看
页面「任务中心 → 运行 → 日志」在线查看；容器内 `/datara/logs/{instance_id}/{task_id}.log`。关键字：`[ssh]` 连接/执行、`hostname` 主机名输出、`date` 时间戳、`Traceback`。

## 11. 日志存放位置
宿主机 `/mnt/lei/datara/logs/{instance_id}/{task_id}.log`。排查顺序：实例终态 → 两 ssh 节点日志（连接成功？执行退出码？）→ 时间戳对比（并行实证）→ worker 容器 `docker logs datara-worker --tail 200`。
