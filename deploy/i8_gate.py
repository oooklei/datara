#!/usr/bin/env python
"""I8 七项实测门驱动（设计文档 §11）：在 datara-worker 容器内运行（复用 kafka-python/pymysql/redis/requests 与 datara 网络拓扑）。

用法：python /tmp/i8_gate.py <子命令> [参数]
子命令：
  prep                          注册 I8-源库 数据源 + 建 CDC 测试表
  mkwf <tag> <kind>             创建工作流定义并保存流画布（kind: g1|g2|g3）
  run <wf>                      启动流任务 → 打印 jobId
  stop <jobId>                  停止流任务（POST /stream-jobs/{id}/stop）
  status <jobId>                打印 DB 状态 + Redis 指标
  wait <jobId> <status> <sec>   轮询等待状态
  produce <topic> <n>           模拟订单生产者（JSON，含 ts）
  dml <n>                       src 库 i8_cdc_test INSERT n 条 + UPDATE 1 条
  poll <jobId> <limit>          轮询 API 输出（fields/rows/metrics 摘要）
  sse <jobId> <frames>          SSE 订阅 N 帧摘要
  offsets <jobId>               打印 t_stream_offset
  windowemits <jobId>           打印窗口触发计数
"""
import json
import sys
import time

import pymysql
import requests

API = "http://datara-api:8000/api/v1"
KAFKA = "datara-kafka:9092"
SRC = dict(host="datara-mysql-src", port=3306, user="root", password="datara_2026", charset="utf8mb4")
TOKEN = ""


def _hdr():
    return {"token": TOKEN}


def _api(method, path, body=None):
    r = requests.request(method, API + path, json=body, headers=_hdr(), timeout=15)
    data = r.json()
    if data.get("code") != 0:
        raise SystemExit(f"API {method} {path} 失败: {data}")
    return data["data"]


def _login():
    global TOKEN
    data = _api("POST", "/login", {"user_name": "admin", "user_pwd": "Admin@123"})
    TOKEN = data["token"]


def _redis():
    from common.queue import get_client
    return get_client()


def _metrics(job_id):
    return _redis().hgetall(f"datara:flink:metrics:{job_id}") or {}


def _print_job(job_id):
    m = _metrics(job_id)
    print(f"[status] metrics={json.dumps(m, ensure_ascii=False)}")


# ---------- 子命令 ----------

def cmd_prep():
    _login()
    rows = _api("GET", "/datasources?page_no=1&page_size=100")
    if not any(r["name"] == "I8-源库" for r in rows):
        _api("POST", "/datasources", {
            "name": "I8-源库", "type": "mysql", "host": "datara-mysql-src", "port": 3306,
            "db": "ec_retail", "user": "root", "pwd": "datara_2026"})
        print("[prep] 数据源 I8-源库 已创建")
    else:
        print("[prep] 数据源 I8-源库 已存在")
    conn = pymysql.connect(**SRC, database="ec_retail")
    try:
        with conn.cursor() as cur:
            cur.execute("""CREATE TABLE IF NOT EXISTS i8_cdc_test (
                id INT PRIMARY KEY AUTO_INCREMENT, name VARCHAR(64),
                amount DECIMAL(10,2), updated_at DATETIME)""")
        conn.commit()
        print("[prep] 表 ec_retail.i8_cdc_test 就绪")
    finally:
        conn.close()


def _mk_doc(kind):
    def n(nid, typ, x, data):
        return {"id": nid, "type": typ, "position": {"x": x, "y": 0}, "data": {"name": nid, **data}}
    kafka_src = {"srcType": "kafka", "brokers": KAFKA, "topic": "datara-demo-orders",
                 "group": f"i8-{kind}-{int(time.time())}", "startFrom": "earliest", "format": "json"}
    cdc_src = {"srcType": "cdc", "cdcDs": "I8-源库", "schemasText": "ec_retail",
               "tablesText": "i8_cdc_test", "posMode": "latest"}
    api_out = {"outType": "api", "keepLast": 200, "schemaText": ""}
    if kind == "g1":
        nodes = [n("src1", "stream_input", 0, kafka_src),
                 n("out1", "stream_output", 260, {**api_out, "schemaText": "order_id,category,amount"})]
        edges = [{"id": "e1", "source": "src1", "target": "out1"}]
    elif kind == "g2":
        nodes = [n("src1", "stream_input", 0, cdc_src),
                 n("out1", "stream_output", 260, {**api_out, "schemaText": "op,schema,table"})]
        edges = [{"id": "e1", "source": "src1", "target": "out1"}]
    else:  # g3：订单流窗口聚合 + CDC 流 union → 融合输出
        nodes = [n("src1", "stream_input", 0, kafka_src),
                 n("src2", "stream_input", 0, cdc_src),
                 n("op1", "stream_fuse", 260, {"name": "窗口聚合", "fuseType": "window", "groupKeys": "category",
                    "aggs": [{"key": "amount", "value": "sum:amount_sum"}, {"key": "amount", "value": "count:cnt"}],
                    "windowType": "tumbling", "windowSizeSec": 10, "watermarkSec": 2}),
                 n("op2", "stream_fuse", 520, {"name": "融合", "fuseType": "union"}),
                 n("out1", "stream_output", 780, api_out)]
        nodes[1]["position"] = {"x": 0, "y": 160}
        edges = [{"id": "e1", "source": "src1", "target": "op1"},
                 {"id": "e2", "source": "op1", "target": "op2"},
                 {"id": "e3", "source": "src2", "target": "op2"},
                 {"id": "e4", "source": "op2", "target": "out1"}]
    return {"nodes": nodes, "edges": edges}


def cmd_mkwf(tag, kind):
    _login()
    name = f"I8-{tag}-{kind}"
    wf = _api("POST", "/workflow-definitions", {"name": name})
    wf_id = wf["id"]
    doc = {**_mk_doc(kind), "id": wf_id, "name": name, "version": 1, "meta": {"profile": "dag"}}
    _api("PUT", f"/workflow-definitions/{wf_id}/save", {"doc": doc, "remark": f"I8 实测门 {kind}"})
    print(f"[mkwf] wf_id={wf_id}")


def cmd_run(wf):
    _login()
    r = _api("POST", f"/workflow-definitions/{wf}/run", {"priority": 3})
    print(f"[run] {json.dumps(r, ensure_ascii=False)}")


def cmd_stop(job_id):
    _login()
    r = _api("POST", f"/stream-jobs/{job_id}/stop")
    print(f"[stop] {json.dumps(r, ensure_ascii=False)}")


def cmd_status(job_id):
    _login()
    rows = _api("GET", f"/stream-jobs?page_size=50") if job_id == "all" else []
    if job_id == "all":
        for r in rows:
            print(f"[status] id={r['id']} doc={r['docId']} status={r['status']} metrics={json.dumps(r['metrics'], ensure_ascii=False)}")
    else:
        _print_job(int(job_id))


def cmd_wait(job_id, status, sec):
    _login()
    deadline = time.time() + int(sec)
    while time.time() < deadline:
        m = _metrics(int(job_id))
        cur = m.get("status") or ""
        print(f"[wait] status={cur or '(no-metrics)'}")
        if cur == status:
            return
        time.sleep(2)
    raise SystemExit(f"[wait] 超时未到 {status}")


def cmd_produce(topic, n):
    from kafka import KafkaProducer
    producer = KafkaProducer(bootstrap_servers=KAFKA, value_serializer=lambda v: json.dumps(v).encode())
    cats = ["手机", "电脑", "家电"]
    for i in range(int(n)):
        msg = {"order_id": f"O{int(time.time() * 1000)}{i}", "category": cats[i % 3],
               "amount": round(100 + (i % 7) * 33.5, 2), "ts": int(time.time() * 1000)}
        producer.send(topic, msg)
        time.sleep(0.15)
    producer.flush()
    producer.close()
    print(f"[produce] 已投递 {n} 条 → {topic}")


def cmd_dml(n):
    conn = pymysql.connect(**SRC, database="ec_retail")
    try:
        with conn.cursor() as cur:
            for i in range(int(n)):
                cur.execute("INSERT INTO i8_cdc_test (name, amount, updated_at) VALUES (%s, %s, NOW())",
                            (f"cdc-{int(time.time())}-{i}", round(10.5 + i, 2)))
            cur.execute("UPDATE i8_cdc_test SET amount = amount + 1 WHERE id = (SELECT id FROM (SELECT MAX(id) id FROM i8_cdc_test) t)")
        conn.commit()
        print(f"[dml] INSERT {n} + UPDATE 1 完成")
    finally:
        conn.close()


def cmd_poll(job_id, limit):
    _login()
    d = _api("GET", f"/stream-jobs/{job_id}/data?mode=poll&limit={limit}")
    print(f"[poll] fields={d['fields']} rows={len(d['rows'])}")
    for row in d["rows"][:5]:
        print(f"[poll]   {json.dumps(row, ensure_ascii=False, default=str)[:200]}")
    m = d.get("metrics") or {}
    print(f"[poll] metrics.status={m.get('status')} totalIn={m.get('totalIn')} totalOut={m.get('totalOut')}")


def cmd_sse(job_id, frames):
    _login()
    n, last = 0, None
    with requests.get(f"{API}/stream-jobs/{job_id}/data?mode=sse&token={TOKEN}", stream=True, timeout=30) as r:
        for line in r.iter_lines(decode_unicode=True):
            if line and line.startswith("data: "):
                last = json.loads(line[6:])
                n += 1
                if n >= int(frames):
                    break
    if last:
        m = last.get("metrics") or {}
        print(f"[sse] frames={n} fields={last['fields']} rows={len(last['rows'])} status={m.get('status')} totalOut={m.get('totalOut')}")
        for row in last["rows"][:3]:
            print(f"[sse]   {json.dumps(row, ensure_ascii=False, default=str)[:200]}")
    else:
        raise SystemExit("[sse] 未收到帧")


def cmd_offsets(job_id):
    from common.db import new_session
    from common.models import StreamOffset
    session = new_session()
    try:
        rows = session.query(StreamOffset).filter(StreamOffset.job_id == int(job_id)).all()
        for r in rows:
            print(f"[offsets] {r.source_key} → {json.dumps(r.offset_json, ensure_ascii=False)}")
        if not rows:
            print("[offsets] (空)")
    finally:
        session.close()


def cmd_windowemits(job_id):
    m = _metrics(int(job_id))
    print(f"[windowemits] {m.get('windowEmits')}")


CMDS = {
    "prep": cmd_prep, "mkwf": cmd_mkwf, "run": cmd_run, "stop": cmd_stop, "status": cmd_status,
    "wait": cmd_wait, "produce": cmd_produce, "dml": cmd_dml, "poll": cmd_poll,
    "sse": cmd_sse, "offsets": cmd_offsets, "windowemits": cmd_windowemits,
}

if __name__ == "__main__":
    fn = CMDS[sys.argv[1]]
    fn(*sys.argv[2:])
