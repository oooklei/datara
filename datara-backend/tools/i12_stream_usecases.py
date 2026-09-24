#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I12 流类 F1~F5 批量编排：建流任务 + 灌数 + 三证 + 断流恢复（Task 16）。

在 1.9 宿主机执行（python3 标准库即可，无第三方依赖）：
  python3 i12_stream_usecases.py --cases f1,f2,f3,f4,f5       # 全量
  python3 i12_stream_usecases.py --cases f1                   # 单例
  python3 i12_stream_usecases.py --cases f4 --stop-jobs       # 跑完停掉本次启动的 job
  python3 i12_stream_usecases.py --cases f1 --wait 25 --kafka-stop 8

用例形态（I12 实施计划 Task 16 / 设计文档 §7.2 F 表）：
  F1 kafka 单源 → 10s 滚动窗口（sum amt_total / count ord_cnt / count_distinct uv）→ API
     + kafka 容器停 10s 断流恢复（位点续跑，窗口桶不重放）
  F2 kafka 双源（order_pay/user_click）各自 10s 窗口 → union → API → 电商看板
  F3 kafka 订单流 LEFT JOIN 维表流（kafka i12_dim_goods）→ API
  F4 http 源轮询 /stream-jobs 列表 → filter(排除自身, status=='running') → 5s 窗口计数 → API
     （两相验证：有他任务 running → cnt>=1；停他任务 → cnt 不再 >=1）
     + C26 尾联：i12_F4_notify 批处理 DAG（成功/故意失败双实例 → notify webhook failHard）
  F5 kafka → 10s 窗口 → TableSink（outDs=内置数仓，upsert uniqueKey=win_start 幂等）
     + 下游 SQL 手动跑批 i12_stream_agg_daily（演示 R5 Dependent，不建调度壳）

零接触约定：只创建/复用 i12_F1~F5 前缀工作流，自建表均 i12_ 新表，不碰他人资产。
证据行格式：EVIDENCE|<case>|<key>|<value>；最终逐例打印 PASS/FAIL。
页面证（playwright DOM+截图）脚本外执行，本脚本输出的 job id 供页面证定位。
"""
import argparse
import json
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"
USER = ("admin", "Admin@123")
DW_DS = "内置数仓-datara_dw"     # id=4（默认库 datara_dw，F5 落库目标）
TAGS = ["流"]
TERMINAL = {"success", "failure", "kill"}
TIMEOUT = {"f1": 240, "f2": 120, "f3": 180, "f4": 240, "f5": 240}

KAFKA_DS = "i12_kafka_local"     # 注册 kafka 源（id=25，brokers=datara-kafka:9092）
KAFKA_BROKER = "datara-kafka:9092"
TOPIC_ORDER = "order_pay"
TOPIC_CLICK = "user_click"
TOPIC_DIM = "i12_dim_goods"
WF_F4 = "i12_F4_http_threshold"

TOKEN = ""
SRC_C = ""
DW_C = ""
API_C = ""      # api 容器名（F4 http 源 from worker 视角的 service 名）
KAFKA_C = ""    # kafka 容器名（断流抽测 docker stop/start 对象）

GOODS = ["SKU_1001", "SKU_1002", "SKU_1003", "SKU_1004", "SKU_1005"]
USERS = ["u_%04d" % i for i in range(50)]
DIM_ROWS = [
    {"goods_id": "SKU_1001", "name": "数码·蓝牙耳机", "category": "数码"},
    {"goods_id": "SKU_1002", "name": "服饰·纯棉T恤", "category": "服饰"},
    {"goods_id": "SKU_1003", "name": "家清·洗衣液", "category": "家清"},
    {"goods_id": "SKU_1004", "name": "食品·咖啡豆", "category": "食品"},
    {"goods_id": "SKU_1005", "name": "运动·瑜伽垫", "category": "运动"},
]

# ---------- 基础工具（与 i12_etl_usecases.py 同构） ----------

def http(method, path, body=None):
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + TOKEN},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        return {"code": exc.code, "msg": exc.read().decode()[:500], "data": None}


def login():
    global TOKEN
    resp = http("POST", "/login", {"user_name": USER[0], "user_pwd": USER[1]})
    assert resp.get("code") == 0, "登录失败: %s" % resp
    TOKEN = resp["data"]["token"]
    print("EVIDENCE|common|login|ok")


def sh(cmd, input_text=None, timeout=120):
    proc = subprocess.run(cmd, shell=isinstance(cmd, str), input=input_text,
                          capture_output=True, text=True, timeout=timeout)
    return proc.returncode, proc.stdout.strip()


# ---------- 容器探测 ----------
def detect_containers():
    """识别 源库/数仓/api/kafka/worker 容器；kafka 断流抽测依赖 KAFKA_C。"""
    global SRC_C, DW_C, API_C, KAFKA_C
    rc, out = sh("docker ps --format '{{.Names}}|{{.Image}}'")
    assert rc == 0, "docker ps 失败: %s" % out
    lines = out.splitlines()
    names = [line.split("|")[0] for line in lines]
    for name in names:
        low = name.lower()
        if re.search(r"mysql|mariadb", low) and "datara_dw" in _mysql_dbs(name):
            DW_C = name
        for kw in ("api", "server", "gateway"):
            if kw in low and API_C == "":
                API_C = name
    mysql_candidates = [n for n in names if re.search(r"mysql|mariadb", n.lower())]
    assert DW_C, "数仓容器未识别齐（找 datara_dw 库）"
    for name in mysql_candidates:
        if _mysql_dbs(name) and "datara_dw" not in _mysql_dbs(name):
            SRC_C = name
            break
    for name in names:
        if re.search(r"kafka", name.lower()):
            KAFKA_C = name
    assert KAFKA_C, "kafka 容器未识别（断流抽测需要）"
    if not API_C:
        API_C = "datara-api"
    print("EVIDENCE|common|containers|dw=%s kafka=%s api=%s src=%s" % (DW_C, KAFKA_C, API_C, SRC_C or "-"))


_PWD_CACHE = {}


def _mysql_pwd(container):
    if container in _PWD_CACHE:
        return _PWD_CACHE[container]
    _, out = sh("docker exec %s env" % container)
    for key in ("MYSQL_ROOT_PASSWORD", "MARIADB_ROOT_PASSWORD"):
        m = re.search(r"^%s=(.*)$" % key, out, re.M)
        if m:
            _PWD_CACHE[container] = m.group(1)
            return _PWD_CACHE[container]
    raise AssertionError("容器 %s 未找到 root 密码环境变量" % container)


def _mysql_dbs(container):
    rc, out = sh("docker exec %s env" % container)
    if rc != 0:
        return set()
    pwd = ""
    for key in ("MYSQL_ROOT_PASSWORD", "MARIADB_ROOT_PASSWORD"):
        m = re.search(r"^%s=(.*)$" % key, out, re.M)
        if m:
            pwd = m.group(1)
            break
    if not pwd:
        return set()
    rc, out = sh("docker exec %s sh -c %s" % (
        container, json.dumps('MYSQL_PWD="%s" mysql -uroot -N -e "SHOW DATABASES"' % pwd)))
    return set(out.splitlines()) if rc == 0 else set()


def mysql_exec(container, sql, db=None, head_limit=None):
    pwd = _mysql_pwd(container)
    argv = ["docker", "exec", "-e", "MYSQL_PWD=%s" % pwd, container,
            "mysql", "-uroot", "-N", "-B"]
    if db:
        argv += ["-D", db]
    argv += ["-e", sql]
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError("SQL 失败(%s): %s\n%s" % (container, sql[:200], proc.stderr.strip()[:500]))
    lines = [line for line in proc.stdout.splitlines() if line != ""]
    return lines[:head_limit] if head_limit else lines


def scalar(container, sql, db=None):
    rows = mysql_exec(container, sql, db)
    return rows[0] if rows else None


def check(case, name, ok_flag, detail):
    print("EVIDENCE|%s|%s|%s" % (case, name, detail if ok_flag else "FAIL: %s" % detail))
    return bool(ok_flag)


# ---------- 流任务画布构造（smoke_stream_i11 同款） ----------

def _n(nid, ntype, name, x, data):
    return {"id": nid, "type": ntype, "position": {"x": x, "y": 0},
            "data": dict(data, name=name)}


def _e(s, t):
    return {"id": "e_%s_%s" % (s, t), "source": s, "target": t, "kind": "flow"}


def _doc(name, nodes, edges):
    return {"id": name, "name": name, "version": 1, "meta": {"profile": "stream"},
            "nodes": nodes, "edges": edges}


def _kafka_src(nid, name, x, topic, group, start_from="earliest"):
    return _n(nid, "stream_input", name, x, {
        "srcType": "kafka", "dsRef": KAFKA_DS, "topic": topic,
        "group": group, "startFrom": start_from, "format": "json", "delimiter": ",",
    })


def _http_src(nid, name, x, url, interval_sec, headers, data_path="data"):
    return _n(nid, "stream_input", name, x, {
        "srcType": "http", "httpUrl": url, "httpMethod": "GET",
        "intervalSec": interval_sec, "headers": headers, "dataPath": data_path,
        "cursorParam": "", "cursorPath": "",
    })


def _filter(nid, name, x, expr):
    return _n(nid, "stream_fuse", name, x, {"fuseType": "filter", "filterExpr": expr})


def _win(nid, name, x, group_keys, aggs, size):
    return _n(nid, "stream_fuse", name, x, {
        "fuseType": "window", "groupKeys": group_keys, "aggs": aggs,
        "windowType": "tumbling", "windowSizeSec": size, "slideSec": size, "watermarkSec": 0,
    })


def _join(nid, name, x, key_left, key_right, win_sec, jtype):
    return _n(nid, "stream_fuse", name, x, {
        "fuseType": "join", "joinKeyLeft": key_left, "joinKeyRight": key_right,
        "joinWindowSec": win_sec, "joinType": jtype,
    })


def _union(nid, name, x):
    return _n(nid, "stream_fuse", name, x, {"fuseType": "union", "alignMap": []})


def _api_out(nid, name, x):
    return _n(nid, "stream_output", name, x, {"outType": "api", "keepLast": 600, "schemaText": ""})


def _table_out(nid, name, x, out_table, field_map, unique_key, batch=500):
    return _n(nid, "stream_output", name, x, {
        "outType": "table", "outDs": DW_DS, "outTable": out_table,
        "outFieldMap": [{"key": k, "value": v} for k, v in field_map],
        "uniqueKey": unique_key, "outBatchSize": batch,
    })


def _board(nid, name, x, preset):
    return _n(nid, "page_board", name, x, {"preset": preset})


# ---------- 工作流生命周期 ----------
def ensure_wf(name):
    """复用或新建工作流定义，返回 (id, code)。"""
    resp = http("GET", "/workflow-definitions?page_no=1&page_size=50&search=%s" % name)
    assert resp.get("code") == 0, resp
    for row in resp["data"].get("list") or []:
        if row.get("name") == name:
            print("EVIDENCE|wf|reuse|%s id=%s code=%s" % (name, row["id"], row["code"]))
            return row["id"], row["code"]
    resp = http("POST", "/workflow-definitions", {"name": name})
    assert resp.get("code") == 0, "创建失败 %s: %s" % (name, resp)
    data = resp["data"]
    print("EVIDENCE|wf|create|%s id=%s code=%s" % (name, data["id"], data["code"]))
    return data["id"], data["code"]


def save_stream_doc(wf_id, doc):
    doc["id"] = wf_id
    doc["name"] = doc["name"]
    resp = http("PUT", "/workflow-definitions/%s/save" % wf_id,
                {"doc": doc, "remark": "I12 流类用例", "tags": TAGS})
    assert resp.get("code") == 0, "保存失败 %s: %s" % (wf_id, resp)
    print("EVIDENCE|stream|save|%s version=%s" % (wf_id, resp["data"]))


def start_stream_job(wf_id, case):
    resp = http("POST", "/stream-jobs/start", {"doc_id": wf_id})
    assert resp.get("code") == 0, "流任务启动失败: %s" % resp
    job = resp["data"]
    print("EVIDENCE|%s|job|%s restarted=%s" % (case, job["id"], job.get("restarted")))
    return int(job["id"])


def wait_running(job_id, case, timeout=90):
    deadline = time.time() + timeout
    status = ""
    while time.time() < deadline:
        row = http("GET", "/stream-jobs/%s" % job_id).get("data") or {}
        status = str(row.get("status") or "")
        if status in ("running", "failed", "stopped"):
            break
        time.sleep(2)
    if status != "running":
        print("EVIDENCE|%s|job_status|%s lastError=%s" % (case, status, (row or {}).get("lastError")))
    else:
        print("EVIDENCE|%s|job_status|running" % case)
    return status


def poll_rows(job_id, limit=800):
    resp = http("GET", "/stream-jobs/%s/data?mode=poll&limit=%s" % (job_id, limit))
    data = resp.get("data") or {}
    return (data.get("rows") or []), (data.get("metrics") or {})


def stop_job(job_id):
    resp = http("POST", "/stream-jobs/%s/stop" % job_id, {})
    return resp.get("code") == 0


def find_running_job(wf_name):
    """找指定工作流名的 running 流任务 job id（F4 需确认他人任务在跑）。"""
    resp = http("GET", "/stream-jobs?page_no=1&page_size=100")
    assert resp.get("code") == 0, resp
    for row in resp["data"] if isinstance(resp.get("data"), list) else []:
        if row.get("wfName") == wf_name and row.get("status") == "running":
            return row.get("id")
    return None


# ---------- kafka 灌数（console-producer stdin 管道，不依赖 kafka-python） ----------

class KafkaFeeder(threading.Thread):
    """kafka-console-producer 管道灌数：容器内 localhost:9092；断线自动重建（断流后续灌）。"""

    def __init__(self, topic, rows_iter, eps, conn="localhost:9092"):
        super().__init__(daemon=True)
        self.topic = topic
        self.rows_iter = rows_iter
        self.eps = eps
        self.conn = conn
        self._proc = None
        self._stop = threading.Event()

    def _ensure_proc(self):
        if self._proc is not None and self._proc.poll() is None:
            return self._proc
        self._proc = subprocess.Popen(
            ["docker", "exec", "-i", KAFKA_C, "kafka-console-producer",
             "--broker-list", self.conn, "--topic", self.topic],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return self._proc

    def run(self):
        while not self._stop.is_set():
            try:
                proc = self._ensure_proc()
                row = next(self.rows_iter, None)
                if row is None:
                    break
                proc.stdin.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))
                proc.stdin.flush()
                time.sleep(1.0 / self.eps)
            except (BrokenPipeError, OSError, ValueError):
                time.sleep(2.0)
            except Exception:  # noqa: BLE001 任何异常都重连续灌
                time.sleep(2.0)

    def stop(self):
        self._stop.set()
        if self._proc is not None and self._proc.poll() is None:
            try:
                self._proc.terminate()
            except Exception:  # noqa: BLE001
                pass


_order_iter = None


def _order_rows():
    """与 seed_stream.gen_ecommerce 相同 schema（order_pay 20%/user_click 60%/cart_event 20%）。"""
    import random
    while True:
        r = random.random()
        if r < 0.2:
            yield {"event": "order_pay", "order_id": "ord_%08d" % random.randrange(10**8),
                   "user_id": random.choice(USERS), "goods_id": random.choice(GOODS),
                   "amount": round(random.uniform(9.9, 999.0), 2), "ts": time.time()}
        elif r < 0.8:
            yield {"event": "user_click", "user_id": random.choice(USERS),
                   "goods_id": random.choice(GOODS), "ts": time.time()}
        else:
            yield {"event": "cart_event", "user_id": random.choice(USERS),
                   "goods_id": random.choice(GOODS),
                   "action": random.choice(["add", "add", "remove"]), "ts": time.time()}


def _dim_rows():
    while True:
        for row in DIM_ROWS:
            yield row


def start_feeders(need_dim=False):
    """返回 (order_feeder, dim_feeder or None)。kafka 断流期间自动续灌，无需重启。"""
    order_feed = KafkaFeeder(TOPIC_ORDER, _order_rows(), eps=5.0)
    order_feed.start()
    dim_feed = None
    if need_dim:
        dim_feed = KafkaFeeder(TOPIC_DIM, _dim_rows(), eps=1.0)
        dim_feed.start()
    print("EVIDENCE|seed|kafka_feeder|topic=%s running; dim=%s" %
          (TOPIC_ORDER, TOPIC_DIM if need_dim else "-"))
    return order_feed, dim_feed


def stop_feeders(*feeds):
    for feed in feeds:
        if feed:
            feed.stop()


def kafka_stop_start(seconds, case):
    """docker stop kafka 容器 seconds 秒后复启，等待 broker 就绪；断流抽测专用。"""
    rc, out = sh("docker stop %s" % KAFKA_C, timeout=60)
    print("EVIDENCE|%s|kafka_stop|rc=%s %s" % (case, rc, out))
    time.sleep(seconds)
    rc, out = sh("docker start %s" % KAFKA_C, timeout=60)
    print("EVIDENCE|%s|kafka_start|rc=%s %s" % (case, rc, out))
    deadline = time.time() + 90
    ready = False
    while time.time() < deadline:
        rc, out = sh("docker exec %s kafka-topics --bootstrap-server localhost:9092 --list" % KAFKA_C)
        if rc == 0 and TOPIC_ORDER in out:
            ready = True
            break
        time.sleep(3)
    assert ready, "kafka 未就绪（90s 超时）"
    print("EVIDENCE|%s|kafka_ready|%s" % (case, TOPIC_ORDER))


# ---------- 画布定义 ----------

def doc_f1():
    nodes = [
        _kafka_src("s1", "订单流(kafka)", 0, TOPIC_ORDER, "i12_f1"),
        _win("w1", "10s全局窗口", 180, "", [
            {"key": "amount", "value": "sum:amt_total"},
            {"key": "order_id", "value": "count:ord_cnt"},
            {"key": "user_id", "value": "count_distinct:uv"},
        ], 10),
        _api_out("o1", "API通道", 360),
    ]
    return "i12_F1_kafka_window_api", _doc("i12_F1_kafka_window_api", nodes,
                                           [_e("s1", "w1"), _e("w1", "o1")])


def doc_f2():
    nodes = [
        _kafka_src("s1", "订单流(kafka)", 0, TOPIC_ORDER, "i12_f2a"),
        _kafka_src("s2", "点击流(kafka)", 0, TOPIC_CLICK, "i12_f2b"),
        _win("w1", "订单10s窗口", 180, "", [
            {"key": "amount", "value": "sum:amt_total"},
            {"key": "order_id", "value": "count:ord_cnt"},
        ], 10),
        _win("w2", "点击10s窗口", 180, "goods_id", [{"key": "user_id", "value": "count:click_cnt"}], 10),
        _union("u1", "双流合并", 360),
        _api_out("o1", "API通道", 520),
        _board("b1", "电商实时大盘", 680, "ecommerce"),
    ]
    return "i12_F2_kafka2_union_board", _doc("i12_F2_kafka2_union_board", nodes,
                                            [_e("s1", "w1"), _e("s2", "w2"),
                                             _e("w1", "u1"), _e("w2", "u1"),
                                             _e("u1", "o1"), _e("o1", "b1")])


def doc_f3():
    nodes = [
        _kafka_src("s1", "订单流(kafka)", 0, TOPIC_ORDER, "i12_f3"),
        _kafka_src("s2", "维表流(kafka)", 0, TOPIC_DIM, "i12_f3_dim", start_from="latest"),
        _join("j1", "订单⋈维表", 180, "goods_id", "goods_id", 60, "left"),
        _api_out("o1", "API通道", 360),
    ]
    return "i12_F3_kafka_join_dim", _doc("i12_F3_kafka_join_dim", nodes,
                                         [_e("s1", "j1"), _e("s2", "j1"), _e("j1", "o1")])


def doc_f4(f4_url, f4_token):
    filter_expr = "status == 'running' and wfName != '%s'" % WF_F4
    nodes = [
        _http_src("s1", "任务列表(http)", 0, f4_url, 5,
                  [{"key": "Authorization", "value": "Bearer " + f4_token}], "data"),
        _filter("f1", "前置过滤", 180, filter_expr),
        _win("w1", "5s状态窗口", 320, "status", [{"key": "status", "value": "count:cnt"}], 5),
        _api_out("o1", "API通道", 460),
    ]
    return WF_F4, _doc(WF_F4, nodes, [_e("s1", "f1"), _e("f1", "w1"), _e("w1", "o1")])


def doc_f5():
    nodes = [
        _kafka_src("s1", "订单流(kafka)", 0, TOPIC_ORDER, "i12_f5"),
        _win("w1", "10s窗口", 180, "", [
            {"key": "amount", "value": "sum:amt_total"},
            {"key": "order_id", "value": "count:cnt"},
        ], 10),
        _table_out("o1", "落库(upsert)", 360, "i12_stream_agg",
                   [("win_start", "win_start"), ("amt_total", "amt_total"), ("cnt", "cnt")],
                   "win_start"),
    ]
    return "i12_F5_kafka_table_agg", _doc("i12_F5_kafka_table_agg", nodes,
                                          [_e("s1", "w1"), _e("w1", "o1")])


# ---------- C26 尾联：F4 通知批处理 DAG（i12_F4_notify） ----------

def _sql_node(nid, name, x, sql, ds=DW_DS, constraints=None):
    data = {"name": name, "datasource": ds, "pre": "", "sql": sql, "post": ""}
    if constraints:
        data["constraints"] = constraints
    return {"id": nid, "type": "sql", "position": {"x": x, "y": 0}, "data": data}


def _notify_node(nid, name, x, url):
    return {"id": nid, "type": "notify", "position": {"x": x, "y": 0},
            "data": {"name": name, "channel": "webhook", "url": url,
                     "trigger": "always", "failHard": True}}


def ensure_and_run_notify_dag(case):
    """i12_F4_notify：start→fork→(SQL成功 / SQL故意失败 双实例)→merge(OR)→notify(failHard)→end。

    C26 语义（F4 文档 §7-4）：成功实例终态 success；失败实例上游 SQL 失败（failPolicy=continue
    不阻断出边）→ notify trigger=always 仍触发 → webhook 命中 echo（2/2 断言）。
    返回 (ok, detail)。
    """
    wf_id, code = ensure_wf("i12_F4_notify")
    ok_sql = "SELECT 1;"
    bad_sql = "SELECT * FROM datara_dw.no_such_table_%s" % int(time.time())
    doc = {"id": wf_id, "name": "i12_F4_notify", "version": 1, "meta": {"profile": "dag"},
           "nodes": [
               {"id": "nd_start", "type": "start", "position": {"x": 80, "y": 0}, "data": {"name": "开始"}},
               {"id": "nd_fork", "type": "fork", "position": {"x": 220, "y": 0},
                "data": {"name": "双实例分叉", "parallel": 2}},
               _sql_node("nd_ok", "成功实例", 400, ok_sql),
               _sql_node("nd_bad", "故意失败实例", 400, bad_sql,
                         constraints={"failPolicy": "continue"}),
               {"id": "nd_merge", "type": "merge", "position": {"x": 580, "y": 0}, "data": {"name": "合并(OR)"}},
               _notify_node("nd_notify", "通知(webhook)", 720, "http://%s:8000/api/v1/echo" % API_C),
               {"id": "nd_end", "type": "end", "position": {"x": 880, "y": 0}, "data": {"name": "结束"}},
           ],
           "edges": [_e("nd_start", "nd_fork"), _e("nd_fork", "nd_ok"), _e("nd_fork", "nd_bad"),
                     _e("nd_ok", "nd_merge"), _e("nd_bad", "nd_merge"),
                     _e("nd_merge", "nd_notify"), _e("nd_notify", "nd_end")]}
    save_stream_doc(wf_id, doc)
    resp = http("POST", "/workflow-definitions/%s/run" % wf_id, {})
    assert resp.get("code") == 0, "DAG 运行失败: %s" % resp
    time.sleep(3)
    instance_id = None
    for _ in range(40):
        listing = http("GET", "/instances?wf_code=%s&page_no=1&page_size=5" % code)
        rows = (listing.get("data") or {}).get("list") or []
        if rows:
            instance_id = rows[0]["instanceId"]
            break
        time.sleep(3)
    assert instance_id, "未找到 i12_F4_notify 新实例"
    detail = None
    deadline = time.time() + TIMEOUT[case]
    while time.time() < deadline:
        detail = http("GET", "/instances/%s" % instance_id).get("data") or {}
        state = detail.get("state") or ""
        if state in TERMINAL:
            break
        time.sleep(5)
    tasks = detail.get("taskInstances") or []
    # 引擎 _finalize：FAILURE 节点仅当 failPolicy != "continue" 才判实例失败；
    # nd_bad 为 continue → 实例终态 success（F4 文档 §7-4「成功实例终态 success」）。
    ok = full_ok = bool(detail) and detail.get("state") == "success"
    ok &= check(case, "notify_dag_final", full_ok, detail.get("state") if detail else "no-data")
    ok &= check(case, "notify_dag_failBranch", any(
        t.get("state") == "failure" and "失败" in (t.get("name") or "") for t in tasks), "见任务清单")
    notify_tasks = [t for t in tasks if t.get("nodeType") == "notify"]
    ok &= check(case, "notify_dag_notifyRan", bool(notify_tasks), len(notify_tasks))
    if notify_tasks:
        for nt in notify_tasks:
            print("EVIDENCE|%s|notify_task|%s state=%s" % (case, nt.get("name"), nt.get("state")))
    ok &= check(case, "notify_dag_end", any(t.get("nodeType") == "end" for t in tasks), "end 节点存在")
    return ok, detail


# ---------- 用例编排 ----------

def run_f1():
    """kafka 单源→窗口→API + kafka 断流 10s 恢复（位点续跑、窗口桶不重放）。"""
    case = "f1"
    feed, _ = start_feeders(need_dim=False)
    time.sleep(3)  # 预灌数
    wf_id, _ = ensure_wf("i12_F1_kafka_window_api")
    save_stream_doc(wf_id, doc_f1()[1])
    job_id = start_stream_job(wf_id, case)
    ok = wait_running(job_id, case) == "running"
    time.sleep(ARGS.wait)
    rows, metrics = poll_rows(job_id)
    win_rows = [r for r in rows if r.get("win_start") is not None]
    ok &= check(case, "win_rows", len(win_rows) > 0, "%d 行" % len(win_rows))
    latest = max((r.get("win_start") or 0) for r in win_rows) if win_rows else 0
    cur = next((r for r in win_rows if (r.get("win_start") or 0) == latest), {})
    ok &= check(case, "sum_amount", float(cur.get("amt_total") or 0) > 0, cur.get("amt_total"))
    ok &= check(case, "count_orders", int(cur.get("ord_cnt") or 0) >= 1, cur.get("ord_cnt"))
    ok &= check(case, "count_distinct_uv", int(cur.get("uv") or 0) >= 1, cur.get("uv"))
    print("EVIDENCE|%s|latest_win|start=%s amt=%s ord=%s uv=%s" %
          (case, latest, cur.get("amt_total"), cur.get("ord_cnt"), cur.get("uv")))

    # 断流恢复：停 kafka → 复启 → 位点续跑（新桶单调增，无重复）
    before_max = latest
    ok &= check(case, "reconnect_anchor", before_max > 0, before_max)
    kafka_stop_start(ARGS.kafka_stop, case)
    time.sleep(25)  # 观察 2~3 个窗口
    rows2, _ = poll_rows(job_id)
    win2 = [r for r in rows2 if r.get("win_start") is not None]
    ok &= check(case, "reconnect_job_alive", wait_running(job_id, case, timeout=30) == "running", "")
    after_max = max((r.get("win_start") or 0) for r in win2) if win2 else 0
    ok &= check(case, "reconnect_offset_resume", after_max > before_max,
                "before=%s after=%s" % (before_max, after_max))
    all_starts = [r.get("win_start") for r in win2]
    ok &= check(case, "reconnect_no_replay", len(all_starts) == len(set(all_starts)), "win_start 无重复桶")
    print("EVIDENCE|%s|reconnect_windows|%d 个窗口桶" % (case, len(win2)))
    return ok


def run_f2():
    """kafka 双源各自窗口→union→API→电商看板。"""
    case = "f2"
    feed, _ = start_feeders(need_dim=False)
    time.sleep(3)
    wf_id, _ = ensure_wf("i12_F2_kafka2_union_board")
    save_stream_doc(wf_id, doc_f2()[1])
    job_id = start_stream_job(wf_id, case)
    ok = wait_running(job_id, case) == "running"
    time.sleep(ARGS.wait)
    rows, metrics = poll_rows(job_id)
    win_rows = [r for r in rows if r.get("win_start") is not None]
    amt_rows = [r for r in win_rows if (r.get("amt_total") or 0) > 0]
    click_rows = [r for r in win_rows if (r.get("click_cnt") or 0) > 0]
    ok &= check(case, "both_streams", len(amt_rows) > 0 and len(click_rows) > 0,
                "amt=%d click=%d" % (len(amt_rows), len(click_rows)))
    latest = max((r.get("win_start") or 0) for r in win_rows) if win_rows else 0
    cur_amt = next((r for r in amt_rows if (r.get("win_start") or 0) == latest), {})
    print("EVIDENCE|%s|latest_win|start=%s amt=%s ord=%s" %
          (case, latest, cur_amt.get("amt_total"), cur_amt.get("ord_cnt")))
    return ok


def run_f3():
    """订单流 LEFT JOIN 维表流（kafka i12_dim_goods）→ API；命中行带 dim 字段。"""
    case = "f3"
    feed, dim_feed = start_feeders(need_dim=True)
    time.sleep(5)  # 维表预灌（join 60s 缓存先有数据）
    wf_id, _ = ensure_wf("i12_F3_kafka_join_dim")
    save_stream_doc(wf_id, doc_f3()[1])
    job_id = start_stream_job(wf_id, case)
    ok = wait_running(job_id, case) == "running"
    time.sleep(ARGS.wait)
    rows, metrics = poll_rows(job_id)
    joined = [r for r in rows if r.get("event") == "order_pay"]
    ok &= check(case, "order_rows", len(joined) > 0, "%d 行" % len(joined))
    matched = [r for r in joined if (r.get("name") or "") != "" and (r.get("category") or "") != ""]
    rate = (len(matched) / float(len(joined))) if joined else 0.0
    ok &= check(case, "join_matched", len(matched) > 0 and rate >= 0.8,
                "%d/%d (%.0f%%)" % (len(matched), len(joined), rate * 100))
    sample = matched[0] if matched else (joined[0] if joined else {})
    print("EVIDENCE|%s|join_sample|goods=%s name=%s cat=%s" %
          (case, sample.get("goods_id"), sample.get("name"), sample.get("category")))
    return ok


def run_f4():
    """F4 阈值触发（两相）+ C26 尾联 i12_F4_notify 双实例。"""
    case = "f4"
    f1_wf_id, f1_code = ensure_wf("i12_F1_kafka_window_api")
    other_job = find_running_job("i12_F1_kafka_window_api")
    if other_job is None:
        print("EVIDENCE|%s|control_start|重启 i12_F1 作为对照任务" % case)
        other_job = start_stream_job(f1_wf_id, case)
    status = wait_running(other_job, case)
    ok = status == "running"
    ok &= check(case, "control_running", status == "running", status)

    f4_url = "http://%s:8000/api/v1/stream-jobs" % API_C
    wf_name, doc = doc_f4(f4_url, TOKEN)
    wf_id, _ = ensure_wf(wf_name)
    save_stream_doc(wf_id, doc)
    job_id = start_stream_job(wf_id, case)
    ok &= wait_running(job_id, case) == "running"
    time.sleep(20)  # ≥4 个 5s 窗口
    rows, metrics = poll_rows(job_id)
    win_rows = [r for r in rows if r.get("win_start") is not None]
    fired = [r for r in win_rows if int(r.get("cnt") or 0) >= 1 and (r.get("status") or "") == "running"]
    ok &= check(case, "threshold_fired", len(fired) > 0,
                "%d 个 cnt>=1 窗口（对照任务 running）" % len(fired))
    before_max = max((r.get("win_start") or 0) for r in win_rows) if win_rows else 0

    # 两相之二：停对照任务 → 新增窗口不得再出现 cnt>=1
    stop_job(other_job)
    print("EVIDENCE|%s|control_stop|对照任务已停" % case)
    time.sleep(15)  # ≥3 窗口
    rows2, _ = poll_rows(job_id)
    win2 = [r for r in rows2 if r.get("win_start") is not None]
    new_fired = [r for r in win2 if (r.get("win_start") or 0) > before_max
                 and int(r.get("cnt") or 0) >= 1]
    ok &= check(case, "threshold_quiet", len(new_fired) == 0,
                "stop 后新增 cnt>=1 窗口=%d 个" % len(new_fired))

    # C26 尾联：notify 批处理双实例（成功实例终态 success + 失败实例 notify 仍触发 → echo 命中）
    ok_notify, _ = ensure_and_run_notify_dag(case)
    ok &= ok_notify
    return ok


def run_f5():
    """kafka→窗口→TableSink upsert（uniqueKey=win_start 幂等）+ 下游 SQL 跑批（R5 演示）。"""
    case = "f5"
    feed, _ = start_feeders(need_dim=False)
    time.sleep(3)
    mysql_exec(DW_C, "DROP TABLE IF EXISTS datara_dw.i12_stream_agg")
    wf_id, _ = ensure_wf("i12_F5_kafka_table_agg")
    save_stream_doc(wf_id, doc_f5()[1])
    job_id = start_stream_job(wf_id, case)
    ok = wait_running(job_id, case) == "running"
    time.sleep(ARGS.wait)
    exists = scalar(DW_C, "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
                          "WHERE TABLE_SCHEMA='datara_dw' AND TABLE_NAME='i12_stream_agg'")
    ok &= check(case, "table_created", exists == "1", exists)
    total = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.i12_stream_agg") or 0)
    ok &= check(case, "rows_written", total > 0, total)
    dup = int(scalar(DW_C, "SELECT COUNT(*) - COUNT(DISTINCT win_start) "
                           "FROM datara_dw.i12_stream_agg") or 0)
    ok &= check(case, "upsert_unique", dup == 0, "重复 win_start=%d" % dup)
    amt = float(scalar(DW_C, "SELECT COALESCE(SUM(CAST(amt_total AS DECIMAL(12,2))),0) "
                             "FROM datara_dw.i12_stream_agg") or 0)
    ok &= check(case, "amt_positive", amt > 0, amt)

    # 断流恢复（job 级）：重启流任务（restarted=true）→ upsert 幂等（无重复桶、不重放）
    job2 = start_stream_job(wf_id, case)
    ok &= wait_running(job2, case) == "running"
    time.sleep(20)
    dup2 = int(scalar(DW_C, "SELECT COUNT(*) - COUNT(DISTINCT win_start) "
                            "FROM datara_dw.i12_stream_agg") or 0)
    total2 = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.i12_stream_agg") or 0)
    ok &= check(case, "restart_idempotent", dup2 == 0 and total2 >= total,
                "dup=%d total %d→%d" % (dup2, total, total2))

    # 下游 SQL 手动跑批（R5 Dependent 演示，不建调度壳）
    mysql_exec(DW_C, "DROP TABLE IF EXISTS datara_dw.i12_stream_agg_daily;"
                     "CREATE TABLE datara_dw.i12_stream_agg_daily AS"
                     " SELECT DATE(FROM_UNIXTIME(win_start)) AS d,"
                     " COUNT(*) AS bucket_cnt,"
                     " SUM(CAST(amt_total AS DECIMAL(12,2))) AS amt_sum,"
                     " SUM(CAST(cnt AS UNSIGNED)) AS ord_cnt"
                     " FROM datara_dw.i12_stream_agg GROUP BY DATE(FROM_UNIXTIME(win_start))")
    daily = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.i12_stream_agg_daily") or 0)
    ok &= check(case, "daily_buckets", daily >= 1, daily)
    daily_amt = float(scalar(DW_C, "SELECT COALESCE(SUM(amt_sum),0) "
                                   "FROM datara_dw.i12_stream_agg_daily") or 0)
    ok &= check(case, "daily_amt_match", abs(daily_amt - amt) < 0.01, "%s vs %s" % (daily_amt, amt))
    return ok


CASES = {"f1": run_f1, "f2": run_f2, "f3": run_f3, "f4": run_f4, "f5": run_f5}


def main():
    global ARGS, BASE
    parser = argparse.ArgumentParser(description="I12 流类 F1~F5 批量编排")
    parser.add_argument("--cases", default="f1,f2,f3,f4,f5")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--wait", type=int, default=30, help="窗口数据观察秒数")
    parser.add_argument("--kafka-stop", type=int, default=10, help="F1 断流抽测 kafka 停摆秒数")
    parser.add_argument("--stop-jobs", action="store_true", help="套件结束后停掉本次启动的流任务")
    ARGS = parser.parse_args()
    BASE = ARGS.base
    cases = [c.strip().lower() for c in ARGS.cases.split(",") if c.strip()]
    for case in cases:
        assert case in CASES, "未知用例: %s" % case
    login()
    detect_containers()
    print("EVIDENCE|common|api_base|%s" % BASE)
    results = {}
    for case in cases:
        print("\n========== 用例 %s ==========" % case.upper())
        try:
            results[case] = CASES[case]()
        except Exception as exc:  # noqa: BLE001 单例失败不阻断其余用例
            print("EVIDENCE|%s|exception|%s" % (case, exc))
            results[case] = False
    print("\n========== 结果汇总 ==========")
    for case, ok_flag in results.items():
        print("%s: %s" % (case.upper(), "PASS" if ok_flag else "FAIL"))
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
