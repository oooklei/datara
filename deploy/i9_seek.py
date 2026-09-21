#!/usr/bin/env python
"""I9 实测门：open() seek 修复验证（I8 验证单·遗留观察项1 → F56d 修复）。

场景：流任务重启后按已提交位点续跑（只消费新消息），而非 earliest 整题重放。
流程：
  1) 独立画布（kafka→api，独立 topic + 独立 consumer group）
  2) run → 投 10 条 → totalIn==10、offset==10
  3) stop → 再投 5 条 → run 重启（幂等先停再起，同一 job、同一 group）
  4) 断言：重启后「新消费增量」==5（修复态）；>5 即整题重放（未修复态，earliest 回放）
  5) offset 终值==15；收尾 stop

说明：totalIn 在同一 job 的重启间可能累计也可能重置（按代际实现而异），
统一用 consumed_after_restart = max(in2 - in1, in2) 归一判定。
在 datara-worker 容器内运行：python /tmp/i9_seek.py
"""
import json
import time

import requests

API = "http://datara-api:8000/api/v1"
KAFKA = "datara-kafka:9092"
TOKEN = ""


def _api(method, path, body=None):
    r = requests.request(method, API + path, json=body, headers={"token": TOKEN}, timeout=15)
    d = r.json()
    if d.get("code") != 0:
        raise SystemExit(f"API {method} {path} 失败: {d}")
    return d["data"]


def _login():
    global TOKEN
    TOKEN = _api("POST", "/login", {"user_name": "admin", "user_pwd": "Admin@123"})["token"]


def _metrics(jid):
    from common.queue import get_client
    return get_client().hgetall(f"datara:flink:metrics:{jid}") or {}


def _total_in(jid):
    m = _metrics(jid)
    try:
        return int(float(m.get("totalIn") or 0))
    except (TypeError, ValueError):
        return 0


def _db_status(jid):
    """DB 权威状态（metrics hash 停止后残留 running 至 TTL 过期，不可作停止判据）。"""
    from common.db import new_session
    from common.models import StreamJob
    s = new_session()
    try:
        row = s.query(StreamJob).filter(StreamJob.id == jid).first()
        return row.status if row else "(missing)"
    finally:
        s.close()


def _wait_status(jid, want, sec):
    dl, last = time.time() + sec, ""
    while time.time() < dl:
        last = _db_status(jid)
        if last == want:
            return
        time.sleep(2)
    raise SystemExit(f"[seek] 超时未到 {want}，最后状态={last}")


def _cleanup_leftovers():
    """收编历史失败轮次遗留的 I9-seek 活跃任务（幂等重跑）。"""
    rows = _api("GET", "/stream-jobs?page_size=50")
    for r in rows:
        if str(r.get("name", "")).startswith("I9-seek") and r.get("status") in ("running", "starting", "reconnecting"):
            try:
                _api("POST", f"/stream-jobs/{r['id']}/stop")
                print(f"[seek] 遗留任务已停 job={r['id']}")
            except SystemExit:
                pass


def _offsets(jid):
    from common.db import new_session
    from common.models import StreamOffset
    s = new_session()
    try:
        rows = s.query(StreamOffset).filter(StreamOffset.job_id == jid).all()
        return {r.source_key: r.offset_json for r in rows}
    finally:
        s.close()


def _mk_topic(topic):
    from kafka.admin import KafkaAdminClient, NewTopic
    try:
        admin = KafkaAdminClient(bootstrap_servers=KAFKA)
        admin.create_topics([NewTopic(name=topic, num_partitions=1, replication_factor=1)])
        admin.close()
        print(f"[seek] topic 已创建 {topic}")
    except Exception as e:  # 已存在等场景放行
        print(f"[seek] topic 创建跳过: {str(e)[:120]}")


def _produce(topic, n):
    from kafka import KafkaProducer
    p = KafkaProducer(bootstrap_servers=KAFKA, value_serializer=lambda v: json.dumps(v).encode())
    cats = ["手机", "电脑", "家电"]
    for i in range(n):
        p.send(topic, {"order_id": f"I9{int(time.time() * 1000)}{i}", "category": cats[i % 3],
                       "amount": round(100 + i * 1.5, 2), "ts": int(time.time() * 1000)})
        time.sleep(0.1)
    p.flush()
    p.close()
    print(f"[seek] 已投递 {n} 条 → {topic}")


def _wait_total_in(jid, target, sec):
    dl = time.time() + sec
    cur = _total_in(jid)
    while time.time() < dl:
        cur = _total_in(jid)
        if cur >= target:
            return cur
        time.sleep(1)
    return cur


def _flat_ints(offsets):
    """递归展开位点 JSON（形如 {src: {partitions: {topic:0: 15}}}）收集全部 int。"""
    out = []

    def walk(v):
        if isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)
        else:
            try:
                out.append(int(v))
            except (TypeError, ValueError):
                pass

    walk(offsets)
    return out


def main():
    _login()
    _cleanup_leftovers()
    ts = int(time.time())
    topic, group, name = f"datara-i9seek-{ts}", f"i9-seek-{ts}", f"I9-seek-{ts}"
    _mk_topic(topic)

    wf = _api("POST", "/workflow-definitions", {"name": name})
    wf_id = wf["id"]

    def n(nid, typ, x, data):
        return {"id": nid, "type": typ, "position": {"x": x, "y": 0}, "data": {"name": nid, **data}}

    doc = {"nodes": [
        n("src1", "stream_input", 0, {"srcType": "kafka", "brokers": KAFKA, "topic": topic,
                                      "group": group, "startFrom": "earliest", "format": "json"}),
        n("out1", "stream_output", 260, {"outType": "api", "keepLast": 200,
                                         "schemaText": "order_id,category,amount", "name": "out1"}),
    ], "edges": [{"id": "e1", "source": "src1", "target": "out1"}],
        "id": wf_id, "name": name, "version": 1, "meta": {"profile": "dag"}}
    _api("PUT", f"/workflow-definitions/{wf_id}/save", {"doc": doc, "remark": "I9 seek 门"})

    r1 = _api("POST", f"/workflow-definitions/{wf_id}/run", {"priority": 3})
    jid = r1["streamJobId"]
    print(f"[seek] job={jid} wf={wf_id} topic={topic} group={group}")
    _wait_status(jid, "running", 90)

    # 阶段1：首跑消费 10 条
    _produce(topic, 10)
    in1 = _wait_total_in(jid, 10, 45)
    ok1 = in1 == 10
    print(f"[seek] 阶段1 totalIn={in1}（期望10）")
    if not ok1:
        print("[seek] FAIL 阶段1")

    # 停止 → 追投 5 条 → 重启
    _api("POST", f"/stream-jobs/{jid}/stop")
    _wait_status(jid, "stopped", 60)
    off1 = _offsets(jid)
    print(f"[seek] 已停止，位点={json.dumps(off1, ensure_ascii=False)}")
    _produce(topic, 5)
    r2 = _api("POST", f"/workflow-definitions/{wf_id}/run", {"priority": 3})
    print(f"[seek] 重启 job={r2['streamJobId']} restarted={r2.get('restarted')}")
    _wait_status(r2["streamJobId"], "running", 90)

    # 阶段2：等新代际消费稳定（代际计数器每代从 0 起：修复态==5，earliest 重放态==15）
    time.sleep(8)
    prev, stable, dl = _total_in(jid), 0, time.time() + 40
    while time.time() < dl:
        time.sleep(2)
        cur = _total_in(jid)
        if cur == prev:
            stable += 1
        else:
            stable, prev = 0, cur
        if stable >= 3:
            break
    in2 = prev
    ok2 = in2 == 5
    print(f"[seek] 阶段2 代际 totalIn={in2}（期望5；=15 即整题重放）")
    if not ok2:
        print("[seek] FAIL 阶段2")

    _api("POST", f"/stream-jobs/{jid}/stop")
    _wait_status(jid, "stopped", 60)
    off2 = _offsets(jid)
    flat = _flat_ints(off2)
    ok3 = 15 in flat
    print(f"[seek] offsets 终值={json.dumps(off2, ensure_ascii=False)}（含15: {ok3}）")
    if not ok3:
        print("[seek] FAIL offsets 终值")
    verdict = {"pass": bool(ok1 and ok2 and ok3), "j1_totalIn": in1, "restart_generation_totalIn": in2,
               "offsets_final": off2, "topic": topic, "wf_id": wf_id, "job_id": jid}
    print("[seek] VERDICT " + json.dumps(verdict, ensure_ascii=False))
    raise SystemExit(0 if verdict["pass"] else 1)


if __name__ == "__main__":
    main()
