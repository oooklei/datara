#!/usr/bin/env bash
# =====================================================================
# I12 Task 4：1.9（192.168.1.9）存量工作流清理脚本
#
# 目标：清理测试期遗留工作流，只保留「同步类」定义（tags 含「同步」）
#       与 name=demo_pipeline，为 I12 乐观锁/删除级联验证留干净基线。
#
# 逻辑（对齐实施计划 Task 4）：
#   ① t_stream_job 全表 → 逐 job 调 stop API → DELETE API 全删
#      （必须 with_def=false：该端点默认 true 会连带删定义且绕过 409 校验，
#        绝不可经此路径触碰「同步」类定义）
#   ② 删除「tags 不含 '同步' 且 name != 'demo_pipeline'」的定义（走 DELETE
#      /workflow-definitions API，D3 级联删 schedule/停止态流任务/位点/版本快照；
#      存在活跃实例或活跃流任务时返回 409，故先清实例）
#   ③ 待删定义残留活跃实例：submitted/running → POST /instances/{id}/stop
#      （waiting_dependency/retry/fault_tolerance 会被 stop API 400 拒绝）；
#      其余活跃态或 STOP 后到期未终态的 → 兜底直改库
#      UPDATE t_workflow_instance 置 state='kill'（终态枚举值）+ end_time，
#      并删除日志目录 {LOG_DIR}/{instance_id}（容器内 /datara/logs）
#   ④ 同步类保护（铁律）：tags 含「同步」或 name=demo_pipeline 的定义及
#      其任何实例/定时/日志 零接触；直改库 SQL 亦带 wf_code 白名单条件
#   ⑤ 输出基线快照 JSON：保留定义清单(id/code/name/tags)、各状态实例数、
#      流任务数；stdout 打印并保存 tools/i12_cleanup_snapshot_{before,after}.json
#
# 用法（在 1.9 上执行；依赖仅 docker + bash）：
#   bash i12_cleanup.sh all        # 快照before → 清理 → 快照after（默认）
#   bash i12_cleanup.sh snapshot   # 只输出当前基线快照 JSON（只读）
#   bash i12_cleanup.sh cleanup    # 只执行清理
#
# 实现说明：HTTP/DB/日志目录操作统一在 datara-api 容器内经 python3 执行
# （urllib 全部带超时、串行低频，避免干扰同宿主机其他验证；DB 复用应用自身
# SQLAlchemy 会话与凭据，日志目录直接操作容器内 LOG_DIR，免猜宿主卷路径）。
# 幂等可重跑：已删资源自动跳过；不重启/rebuild 任何容器，不改任何业务代码。
# =====================================================================
set -u

API_CONTAINER="datara-api"
OUT_DIR="/mnt/lei/datara/datara-backend/tools"
BEFORE_JSON="$OUT_DIR/i12_cleanup_snapshot_before.json"
AFTER_JSON="$OUT_DIR/i12_cleanup_snapshot_after.json"
MODE="${1:-all}"

# 定位本栈权威 API 的容器桥接 IP（绕开宿主机 127.0.0.1:8000 上可能存在的
# 转发/隧道占用——09-23 实测该地址曾被指向另一套环境的进程间歇性抢占，
# 导致 localhost 请求读到另一套库的数据；直连容器 IP 对其免疫）。
API_IP="$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}} {{end}}' "$API_CONTAINER" | awk '{print $1}')"
if [ -z "${API_IP:-}" ]; then
  echo "[FATAL] 无法解析 $API_CONTAINER 的容器 IP，拒绝在错误后端上执行清理" >&2
  exit 3
fi
echo "目标 API: http://$API_IP:8000/api/v1 (container=$API_CONTAINER)"

run_py() {
  docker exec -i -e API_IP="$API_IP" "$API_CONTAINER" python3 - "$1" <<'PYEOF'
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

MODE = sys.argv[1] if len(sys.argv) > 1 else "cleanup"
# BASE 由 bash 侧注入本容器桥接 IP（API_IP），理由见脚本头注释：
# 宿主机 127.0.0.1:8000 可能被指向其他环境的转发/隧道进程间歇性占用。
_base_ip = os.environ.get("API_IP") or ""
if not _base_ip:
    raise RuntimeError("缺少 API_IP 环境变量（bash 侧未注入容器 IP），拒绝误打其他后端")
BASE = "http://%s:8000/api/v1" % _base_ip
ADMIN_USER = "admin"
ADMIN_PWD = os.environ.get("DATARA_ADMIN_PWD") or "Admin@123"  # 容器 env（compose DATARA_ADMIN_PWD）可覆盖，默认不变
SYNC_TAG = "同步"
PROTECT_NAME = "demo_pipeline"
PAGE_SIZE = 200
# master/state.py ACTIVE_STATES（实例级活跃态：删除定义会被 409 拒绝的集合）
ACTIVE_STATES = {"submitted", "waiting_dependency", "running", "retry", "fault_tolerance"}
# master/state.py INSTANCE_RUNNING_STATES（stop API 唯一接受的实例态）
API_STOPPABLE = {"submitted", "running"}
# 流任务活跃态（出处：api/wf_definition.py STREAM_ACTIVE_STATUS / worker/stream/engine.py ACTIVE_STATUSES）
STREAM_ACTIVE = {"starting", "running", "reconnecting"}


def log(msg):
    print(msg, flush=True)


def http(method, path, token="", body=None, timeout=30):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("token", token)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except Exception:
            payload = {}
        return exc.code, payload
    except (urllib.error.URLError, TimeoutError) as exc:
        # 网络异常（连接拒绝/socket 超时，URLError 为 OSError 子类一并覆盖）：
        # 降级为可记录的错误响应（st=0 会被调用方归入 errors），不让进程崩退
        return 0, {"msg": "网络异常: %s" % getattr(exc, "reason", exc)}


def login():
    st, body = http("POST", "/login", body={"user_name": ADMIN_USER, "user_pwd": ADMIN_PWD})
    token = ((body or {}).get("data") or {}).get("token")
    if st != 200 or not token:
        raise RuntimeError("login failed: %s %s" % (st, body))
    return token


def list_definitions(token):
    rows, page, seen = [], 1, set()
    while True:
        # 分页参数双兼容：仓库 common/resp.py PageQuery 认 page_no，旧版认 page（多余参数彼此忽略）
        st, body = http("GET", "/workflow-definitions?page=%d&page_no=%d&page_size=%d" % (page, page, PAGE_SIZE), token)
        if st != 200:
            raise RuntimeError("definitions list failed: %s %s" % (st, body))
        data = body.get("data") or {}
        items = data.get("items") or data.get("list") or []  # 分页 data 键双兼容：仓库 resp.py 与 1.9 部署版实测均返回 list，items 键仅为更早版本兜底
        new = [it for it in items if it.get("id") not in seen]  # 按 id 去重，防新旧翻页参数口径差异下重复行污染
        seen.update(it.get("id") for it in new)
        rows.extend(new)
        if not items or not new or len(items) < PAGE_SIZE or len(rows) >= int(data.get("total") or 0):
            break
        page += 1
    return rows


def list_instances(token):
    rows, page, seen = [], 1, set()
    while True:
        # 分页参数双兼容：仓库 common/resp.py PageQuery 认 page_no，旧版认 page（多余参数彼此忽略）
        st, body = http("GET", "/instances?page=%d&page_no=%d&page_size=%d" % (page, page, PAGE_SIZE), token)
        if st != 200:
            raise RuntimeError("instances list failed: %s %s" % (st, body))
        data = body.get("data") or {}
        items = data.get("items") or data.get("list") or []  # 分页 data 键双兼容：仓库 resp.py 与 1.9 部署版实测均返回 list，items 键仅为更早版本兜底
        new = [it for it in items if it.get("instanceId") not in seen]  # 按 instanceId 去重，防新旧翻页参数口径差异下重复行污染
        seen.update(it.get("instanceId") for it in new)
        rows.extend(new)
        if not items or not new or len(items) < PAGE_SIZE or len(rows) >= int(data.get("total") or 0):
            break
        page += 1
    return rows


def list_stream_jobs(token):
    st, body = http("GET", "/stream-jobs?page_size=%d" % PAGE_SIZE, token)
    if st != 200:
        raise RuntimeError("stream-jobs list failed: %s %s" % (st, body))
    return body.get("data") or []


def is_kept(item):
    """同步类保护判定：tags 含「同步」或 name=demo_pipeline → 保留。"""
    tags = item.get("tags") or []
    return (SYNC_TAG in tags) or (item.get("name") == PROTECT_NAME)


def count_by(rows, key):
    out = {}
    for row in rows:
        state = str(row.get(key) or "unknown")
        out[state] = out.get(state, 0) + 1
    return out


def build_snapshot(token):
    defs = list_definitions(token)
    insts = list_instances(token)
    jobs = list_stream_jobs(token)
    kept = [d for d in defs if is_kept(d)]
    dele = [d for d in defs if not is_kept(d)]
    del_codes = {d.get("code") for d in dele}
    known_codes = {d.get("code") for d in defs}
    scope = [i for i in insts if i.get("wfCode") in del_codes]
    orphan = [i for i in insts if i.get("wfCode") not in known_codes and i.get("state") in ACTIVE_STATES]

    def brief(d):
        return {"id": d.get("id"), "code": d.get("code"), "name": d.get("name"), "tags": d.get("tags") or []}

    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "definition_total": len(defs),
        "kept_definitions": [brief(d) for d in kept],
        "delete_definitions": [brief(d) for d in dele],
        "instance_state_counts": count_by(insts, "state"),
        "delete_scope_instance_state_counts": count_by(scope, "state"),
        "orphan_active_instances": [
            {"instanceId": i.get("instanceId"), "wfCode": i.get("wfCode"), "state": i.get("state")}
            for i in orphan
        ],
        "stream_job_count": len(jobs),
        "stream_job_status_counts": count_by(jobs, "status"),
    }


def db_kill_instances(instance_ids, del_codes, stats):
    """兜底直改库：UPDATE t_workflow_instance 置 state='kill'+end_time，并删日志目录。

    SQL 带 state∈ACTIVE 且 wf_code∈待删集合 双重条件（幂等 + 防竞态 + 同步类零接触）。
    """
    ids = list(dict.fromkeys(instance_ids))
    if not ids:
        return
    from common.config import get_settings
    from common.db import new_session
    from common.models import WorkflowInstance, now

    session = new_session()
    try:
        for iid in ids:
            matched = (
                session.query(WorkflowInstance)
                .filter(
                    WorkflowInstance.instance_id == iid,
                    WorkflowInstance.state.in_(ACTIVE_STATES),
                    WorkflowInstance.wf_code.in_(del_codes),
                )
                .update({"state": "kill", "end_time": now()}, synchronize_session=False)
            )
            session.commit()
            if matched:
                stats["instances_db_killed"] += 1
                log_dir = os.path.join(get_settings().log_dir, iid)
                if os.path.isdir(log_dir):
                    shutil.rmtree(log_dir, ignore_errors=True)
                    stats["log_dirs_removed"] += 1
                log("  直改库 kill + 清日志目录: %s" % iid)
    finally:
        session.close()


def sweep_instances(token, del_codes, stats):
    """终止待删定义（wf_code ∈ del_codes）名下全部活跃实例。"""
    if not del_codes:
        return
    targets = [
        i for i in list_instances(token)
        if i.get("wfCode") in del_codes and i.get("state") in ACTIVE_STATES
    ]
    if not targets:
        return
    log("  活跃实例 %d 个待终止（wf_code: %s）"
        % (len(targets), ",".join(str(c) for c in sorted(del_codes, key=str))))
    api_stopped, db_pending = [], []
    for row in targets:
        iid, state = row.get("instanceId"), row.get("state")
        if state in API_STOPPABLE:
            st, body = http("POST", "/instances/%s/stop" % iid, token)
            if st == 200:
                stats["instances_api_stopped"] += 1
                api_stopped.append(iid)
                log("    STOP 命令已提交: %s (%s)" % (iid, state))
            else:
                db_pending.append(iid)
                log("    stop API 拒绝 %s (%s) -> %s %s，转直改库"
                    % (iid, state, st, (body or {}).get("msg")))
        else:
            db_pending.append(iid)
            log("    非 API 可停态走直改库: %s (%s)" % (iid, state))
        time.sleep(0.2)
    # STOP 命令为异步（master 2s 内消费），限时等待终态；到期未终态转直改库兜底
    pending = set(api_stopped)
    deadline = time.time() + 36
    while pending and time.time() < deadline:
        time.sleep(3)
        current = {i.get("instanceId"): i.get("state") for i in list_instances(token)}
        pending = {iid for iid in pending if current.get(iid) in ACTIVE_STATES}
    if pending:
        log("    STOP 后仍未终态 %d 个，转直改库: %s" % (len(pending), ",".join(sorted(pending))))
    db_kill_instances(db_pending + sorted(pending), del_codes, stats)


def cleanup():
    token = login()
    stats = {
        "stream_jobs_stopped": 0,
        "stream_jobs_deleted": 0,
        "instances_api_stopped": 0,
        "instances_db_killed": 0,
        "log_dirs_removed": 0,
        "definitions_deleted": 0,
        "definitions_kept": 0,
        "errors": [],
    }
    defs = list_definitions(token)
    kept = [d for d in defs if is_kept(d)]
    dele = [d for d in defs if not is_kept(d)]
    del_codes = {d.get("code") for d in dele}
    stats["definitions_kept"] = len(kept)
    log("== 定义判定：待删 %d / 保留 %d（同步类 + demo_pipeline）==" % (len(dele), len(kept)))
    for d in kept:
        log("  [保留] id=%s code=%s name=%s tags=%s"
            % (d.get("id"), d.get("code"), d.get("name"), d.get("tags") or []))

    # ① 流任务全删：stop → delete（with_def=false，绝不经此路径触碰任何定义）
    log("== ① 流任务清理（全删，with_def=false）==")
    for attempt in range(10):
        jobs = list_stream_jobs(token)
        if not jobs:
            break
        if attempt:
            log("  第 %d 轮剩余 %d 个" % (attempt + 1, len(jobs)))
        for job in jobs:
            jid = job.get("id")
            if (job.get("status") or "") in STREAM_ACTIVE:
                st, body = http("POST", "/stream-jobs/%s/stop" % jid, token)
                if st == 200:
                    stats["stream_jobs_stopped"] += 1
                else:
                    stats["errors"].append("stream-job stop %s -> %s %s" % (jid, st, (body or {}).get("msg")))
            st, body = http("DELETE", "/stream-jobs/%s?with_def=false" % jid, token)
            if st == 200:
                stats["stream_jobs_deleted"] += 1
                log("  已删流任务 #%s %s" % (jid, job.get("name") or job.get("wfName") or ""))
            else:
                stats["errors"].append("stream-job delete %s -> %s %s" % (jid, st, (body or {}).get("msg")))
            time.sleep(0.2)
    else:
        stats["errors"].append("流任务清理 10 轮后仍有残留")

    # ③ 活跃实例清扫（仅待删定义 wf_code 范围；同步类实例零接触）
    log("== ③ 活跃实例清扫（仅待删定义范围）==")
    sweep_instances(token, del_codes, stats)

    # ④ 定义删除（D3 级联 schedule/停止态流任务/位点/版本快照；409 则补清扫后重试一次）
    log("== ④ 定义删除 ==")
    for d in dele:
        wid = d.get("id")
        st, body = http("DELETE", "/workflow-definitions/%s" % wid, token)
        if st == 409:
            log("  定义 %s 删除被拒(409)，补清活跃实例后重试" % wid)
            sweep_instances(token, {d.get("code")}, stats)
            st, body = http("DELETE", "/workflow-definitions/%s" % wid, token)
        if st == 200:
            stats["definitions_deleted"] += 1
            log("  已删定义: %s (id=%s code=%s)" % (d.get("name"), wid, d.get("code")))
        else:
            stats["errors"].append("definition delete %s -> %s %s" % (wid, st, (body or {}).get("msg")))
        time.sleep(0.2)

    log("== 清理完成 ==")
    log("STATS " + json.dumps(stats, ensure_ascii=False))


def main():
    if MODE == "snapshot":
        print(json.dumps(build_snapshot(login()), ensure_ascii=False, indent=2))
    elif MODE == "cleanup":
        cleanup()
    else:
        raise RuntimeError("unknown mode: %s" % MODE)


main()
PYEOF
}

case "$MODE" in
  snapshot)
    run_py snapshot
    ;;
  cleanup)
    run_py cleanup
    ;;
  all)
    mkdir -p "$OUT_DIR"
    echo "== [1/3] before 基线快照 =="
    run_py snapshot | tee "$BEFORE_JSON"
    if [ "${PIPESTATUS[0]}" -ne 0 ]; then echo "[WARN] before 快照执行异常，请检查上方输出"; fi
    echo "== [2/3] 执行清理 =="
    if ! run_py cleanup; then
      echo "[FATAL] 清理执行失败（run_py cleanup 返回非 0），中止后续 after 快照" >&2
      exit 4
    fi
    echo "== [3/3] after 基线快照 =="
    run_py snapshot | tee "$AFTER_JSON"
    if [ "${PIPESTATUS[0]}" -ne 0 ]; then echo "[WARN] after 快照执行异常，请检查上方输出"; fi
    echo "== 完成：快照已保存 $BEFORE_JSON 与 $AFTER_JSON =="
    ;;
  *)
    echo "用法: bash i12_cleanup.sh [all|snapshot|cleanup]" >&2
    exit 2
    ;;
esac
