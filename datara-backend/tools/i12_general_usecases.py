#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I12 普通类 G1~G5 批量编排：建工作流 + 跑批 + 三证取证（Task 17）。

在 1.9 宿主机执行（python3 标准库即可）：
  python3 i12_general_usecases.py --cases g1,g2,g3,g4,g5      # 建流+跑批+验证
  python3 i12_general_usecases.py --cases g3 --base http://127.0.0.1:8000/api/v1

零接触约定：只创建/复用 i12_G1~G5 前缀工作流，自建表/文件均 i12_ 前缀，不碰他人资产。
证据行格式：EVIDENCE|<case>|<key>|<value>；最终逐例打印 PASS/FAIL。
"""
import argparse
import json
import re
import subprocess
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"
USER = ("admin", "Admin@123")
DW_DS = "内置数仓-datara_dw"       # id=4
NODE_HOST = "1.9宿主机"            # 运行节点 id=2（G4 SSH 节点，按实读调整）
TAGS = []                          # 普通类无标签
TERMINAL = {"success", "failure", "kill"}
TIMEOUT = {"g1": 300, "g2": 300, "g3": 300, "g4": 300, "g5": 900}

TOKEN = ""
DW_C = ""


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


def sh(cmd, input_text=None):
    proc = subprocess.run(cmd, shell=isinstance(cmd, str), input=input_text,
                          capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout.strip()


# ---------- MySQL 容器探测与执行 ----------
def detect_mysql_containers():
    global DW_C
    rc, out = sh("docker ps --format '{{.Names}}|{{.Image}}'")
    assert rc == 0, "docker ps 失败: %s" % out
    candidates = [line.split("|")[0] for line in out.splitlines()
                  if re.search(r"mysql|mariadb", line, re.I)]
    assert candidates, "未发现 mysql 容器"
    for name in candidates:
        dbs = mysql_dbs(name)
        if not dbs:
            continue
        if "datara_dw" in dbs:
            DW_C = name
            break
    print("EVIDENCE|common|dw_container|%s" % DW_C)


def mysql_dbs(container):
    rc, out = sh("docker exec %s mysql -uroot -pdatara_2026 -e 'SHOW DATABASES' -N 2>/dev/null" % container)
    if rc != 0:
        return []
    skip = ("information_schema", "mysql", "performance_schema", "sys")
    return [ln.strip() for ln in out.splitlines() if ln.strip() not in skip]


def mysql_exec(container, sql, db=None):
    cmd = "docker exec %s mysql -uroot -pdatara_2026 %s -e %s -N 2>/dev/null" % (
        container, ("-D " + db) if db else "", _sql_quote(sql))
    rc, out = sh(cmd)
    return rc, out


def _sql_quote(sql):
    return "'" + sql.replace("'", "'\\''") + "'"


def scalar(container, sql, db=None):
    rc, out = mysql_exec(container, sql, db=db)
    if rc != 0 or not out:
        return None
    return out.splitlines()[0].strip()


# ---------- 工作流 CRUD ----------
def ensure_wf(name):
    """按名称查找工作流定义，不存在则创建。返回 (wf_id, code)。"""
    resp = http("GET", "/workflow-definitions?page_no=1&page_size=50&search=%s" % name)
    for row in (resp.get("data") or {}).get("list") or []:
        if row.get("name") == name:
            print("EVIDENCE|wf|reuse|%s id=%s code=%s" % (name, row["id"], row["code"]))
            return row["id"], row["code"]
    resp = http("POST", "/workflow-definitions", {"name": name, "tags": TAGS})
    assert resp.get("code") == 0, "创建工作流失败: %s" % resp
    wf_id, code = resp["data"]["id"], resp["data"]["code"]
    print("EVIDENCE|wf|create|%s id=%s code=%s" % (name, wf_id, code))
    return wf_id, code


def save_wf(wf_id, doc):
    doc = dict(doc)
    doc["id"] = wf_id
    resp = http("PUT", "/workflow-definitions/%s/save" % wf_id, {"doc": doc, "remark": "i12 general batch"})
    assert resp.get("code") == 0, "保存工作流失败: %s" % resp
    print("EVIDENCE|wf|save|%s version=%s" % (wf_id, resp["data"]))
    return resp["data"]


def run_instance(wf_id, case, wf_code, timeout=60):
    resp = http("POST", "/workflow-definitions/%s/run" % wf_id, {})
    assert resp.get("code") == 0, "运行命令提交失败: %s" % resp
    print("EVIDENCE|%s|command|%s" % (case, resp["data"]))
    # 命令异步消费：master 建实例后按 wf_code 过滤取出（批处理模式无直接实例 id）
    time.sleep(3)
    t0 = time.time()
    while time.time() - t0 < timeout:
        path = "/instances?wf_code=%s&page_no=1&page_size=5" % wf_code
        lst = http("GET", path)
        rows = ((lst.get("data") or {}).get("list")) or []
        if rows:
            return rows[0]["instanceId"]
        time.sleep(3)
    raise AssertionError("等待实例超时 %ds" % timeout)


def wait_terminal(inst_id, case, timeout=300):
    t0 = time.time()
    while time.time() - t0 < timeout:
        resp = http("GET", "/instances/%s" % inst_id)
        row = resp.get("data") or {}
        status = row.get("state")
        if status in TERMINAL:
            print("EVIDENCE|%s|instance_status|%s duration_ms=%s" % (
                case, status, row.get("duration")))
            return status, row
        time.sleep(5)
    print("EVIDENCE|%s|instance_timeout|%d" % (case, timeout))
    return "timeout", {}


def instance_logs(inst_id, tail=80):
    """实例 t_task_log 索引 → task 级日志合并（logger 服务 /logs/task/{id}）。"""
    resp = http("GET", "/instances/%s" % inst_id)
    detail = resp.get("data") or {}
    chunks = []
    for task in detail.get("taskInstances") or []:
        lr = http("GET", "/logs/task/%s" % task["id"])
        content = ((lr.get("data") or {}).get("content")) or ""
        if content:
            chunks.append(content)
    return "\n".join(chunks)[-tail * 200:]


# ---------- 节点构建 helpers ----------
def _n(nid, ntype, name, x, y, data=None):
    return {"id": nid, "type": ntype, "position": {"x": x, "y": y},
            "data": dict(data or {}, name=name)}


def _e(s, t):
    return {"source": s, "target": t}


def _doc(name, nodes, edges):
    return {"name": name, "nodes": nodes, "edges": edges, "meta": {}}


# ---------- G1 shell 巡检 ----------
_G1_SCRIPT = (
    'echo "===== 磁盘水位 ====="\n'
    'df -h | grep -E "/$|/mnt" | awk \'{print $5, $6}\'\n'
    'echo "===== Datara 容器状态 ====="\n'
    'docker ps --format "{{.Names}}\t{{.Status}}" 2>/dev/null | grep datara || echo "(docker 不可用)"\n'
    'echo "===== 内存 ====="\n'
    'free -m 2>/dev/null | head -2 || echo "(free 不可用)"\n'
    'echo "巡检完成 @ $(date \'+%Y-%m-%d %H:%M:%S\')"'
)


def build_g1():
    nodes = [
        _n("s", "start", "开始", 80, 120),
        _n("k1", "shell", "健康巡检", 260, 120, {"script": _G1_SCRIPT}),
        _n("k2", "delay", "延时60s", 440, 120, {"duration": 60, "unit": "秒"}),
        _n("k3", "notify", "仅日志通知", 620, 120, {
            "channel": "log", "trigger": "on_success",
            "template": "G1 巡检完成 实例=${instance_id} 节点=${node.name} @ ${sys.now}",
            "failHard": False,
        }),
        _n("e", "end", "结束", 800, 120),
    ]
    edges = [_e("s", "k1"), _e("k1", "k2"), _e("k2", "k3"), _e("k3", "e")]
    return "i12_G1_shell_health_check", _doc("i12_G1_shell_health_check", nodes, edges)


def check_g1(inst_id, case, status):
    ok = status == "success"
    check(case, "terminal", ok, "status=%s" % status)
    if ok:
        logs = instance_logs(inst_id, tail=60)
        has_check = "巡检完成" in logs
        has_notify = "[notify]" in logs
        check(case, "shell_output", has_check, "巡检完成关键字")
        check(case, "notify_log", has_notify, "[notify]关键字")


# ---------- G2 python 清洗 ----------
_G2_SCRIPT = (
    'import csv, os\n'
    'SRC="/datara/files/i12_raw_orders.csv"\n'
    'DST="/datara/files/i12_cleaned_orders.csv"\n'
    'read=written=skipped=0\n'
    'with open(SRC,"r",encoding="utf-8-sig",newline="") as f:\n'
    '    reader=csv.reader(f)\n'
    '    with open(DST,"w",encoding="utf-8",newline="") as out:\n'
    '        writer=csv.writer(out)\n'
    '        for row in reader:\n'
    '            read+=1\n'
    '            row=[c.strip() for c in row]\n'
    '            if not any(row):\n'
    '                skipped+=1\n'
    '                continue\n'
    '            writer.writerow(row)\n'
    '            written+=1\n'
    'print(f"[clean] 读={read} 写={written} 跳过空行={skipped}")\n'
)


def build_g2():
    nodes = [
        _n("s", "start", "开始", 80, 120),
        _n("k1", "python", "CSV清洗", 260, 120, {"script": _G2_SCRIPT}),
        _n("k2", "file", "注册预览", 460, 120, {
            "mode": "manual", "path": "/datara/files/i12_cleaned_orders.csv",
            "format": "csv", "encoding": "utf-8", "delimiter": ",", "header": True, "sheet": "",
            "register": True, "tmpName": "cleaned_orders", "kind": "table",
            "targetDs": DW_DS, "retention": "immediate", "keepDays": 7,
        }),
        _n("e", "end", "结束", 660, 120),
    ]
    edges = [_e("s", "k1"), _e("k1", "k2"), _e("k2", "e")]
    return "i12_G2_python_clean_file", _doc("i12_G2_python_clean_file", nodes, edges)


def check_g2(inst_id, case, status):
    ok = status == "success"
    check(case, "terminal", ok, "status=%s" % status)
    if ok:
        logs = instance_logs(inst_id, tail=40)
        has_clean = "[clean]" in logs
        check(case, "clean_output", has_clean, "[clean]关键字")
        # 文件行数核对
        _f = "/datara/files/i12_cleaned_orders.csv"
        rc, out = sh("docker exec datara-worker bash -c 'wc -l < %s 2>/dev/null'" % _f)
        file_rows = int(out) if out and out.strip().isdigit() else 0
        check(case, "file_exists", file_rows > 0, "csv rows=%d" % file_rows)


# ---------- G3 http→sql→notify ----------
_G3_SQL = (
    "DROP TABLE IF EXISTS i12_http_snapshot;"
    " CREATE TABLE i12_http_snapshot (id INT PRIMARY KEY,"
    " name VARCHAR(128), ds_type VARCHAR(32),"
    " created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
    " INSERT INTO i12_http_snapshot (id,name,ds_type)"
    " VALUES (1,'demo_src','mysql'),(4,'datara_dw','mysql'),"
    "(25,'i12_kafka_local','kafka');"
)


def build_g3():
    nodes = [
        _n("s", "start", "开始", 80, 120),
        _n("k1", "http", "GET datasources", 250, 120, {
            "url": "http://datara-api:8000/api/v1/datasources",
            "method": "GET",
            "headers": [{"key": "Authorization", "value": "Bearer " + TOKEN}],
            "successCodes": ["2xx"], "timeout": 15, "extract": {"ds_list": "data"},
        }),
        _n("k2", "sql", "落库", 440, 120, {"datasource": DW_DS, "sql": _G3_SQL}),
        _n("k3", "notify", "webhook通知", 630, 120, {
            "channel": "webhook", "url": "http://192.168.1.9:8000/api/v1/echo",
            "trigger": "on_success",
            "template": "${wf.name} 数据源快照写入完成 @ ${sys.now}", "failHard": False,
        }),
        _n("e", "end", "结束", 820, 120),
    ]
    edges = [_e("s", "k1"), _e("k1", "k2"), _e("k2", "k3"), _e("k3", "e")]
    return "i12_G3_http_to_db_notify", _doc("i12_G3_http_to_db_notify", nodes, edges)


def check_g3(inst_id, case, status):
    ok = status == "success"
    check(case, "terminal", ok, "status=%s" % status)
    if ok:
        # 库证
        rows = scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.i12_http_snapshot", db="")
        check(case, "db_rows", rows == "3", "rows=%s" % rows)
        # API 证
        logs = instance_logs(inst_id, tail=50)
        has_http = "[http]" in logs
        has_notify = "[notify]" in logs
        check(case, "http_log", has_http, "[http]关键字")
        check(case, "notify_log", has_notify, "[notify]关键字")


# ---------- G4 ssh fork/join ----------
def build_g4():
    nodes = [
        _n("s", "start", "开始", 80, 160),
        _n("k1", "fork", "并行分叉", 240, 160, {"parallel": 2}),
        _n("k2a", "ssh", "节点A", 420, 100, {
            "runtimeNode": NODE_HOST, "script": "hostname; date '+%Y-%m-%d %H:%M:%S'", "timeout": 30,
        }),
        _n("k2b", "ssh", "节点B", 420, 220, {
            "runtimeNode": NODE_HOST, "script": "hostname; date '+%Y-%m-%d %H:%M:%S'", "timeout": 30,
        }),
        _n("k3", "join", "汇合", 600, 160, {}),
        _n("e", "end", "结束", 760, 160),
    ]
    edges = [_e("s", "k1"), _e("k1", "k2a"), _e("k1", "k2b"), _e("k2a", "k3"), _e("k2b", "k3"), _e("k3", "e")]
    return "i12_G4_ssh_fork_parallel", _doc("i12_G4_ssh_fork_parallel", nodes, edges)


def check_g4(inst_id, case, status):
    ok = status == "success"
    check(case, "terminal", ok, "status=%s" % status)
    if ok:
        logs = instance_logs(inst_id, tail=60)
        has_ssh = logs.count("[ssh]") >= 2
        check(case, "dual_ssh", has_ssh, "ssh节点数>=2")


# ---------- G5 数据出仓 ----------
_G5_SCRIPT = (
    'import csv, os\n'
    'import pymysql\n'
    'conn=pymysql.connect(host="datara-mysql-dw",port=3306,user="root",'
    'password="datara_2026",db="datara_dw",charset="utf8mb4")\n'
    'cur=conn.cursor()\n'
    'cur.execute("SELECT order_no,user_id,amount,create_time FROM ods_order ORDER BY id")\n'
    'os.makedirs("/datara/files/export",exist_ok=True)\n'
    'rows=0\n'
    'with open("/datara/files/export/ods_order_archive.csv",'
    '"w",encoding="utf-8",newline="") as f:\n'
    '    w=csv.writer(f)\n'
    '    w.writerow([d[0] for d in cur.description])\n'
    '    for r in cur.fetchall():\n'
    '        w.writerow(r); rows+=1\n'
    'cur.close(); conn.close()\n'
    'print(f"[export] 导出 {rows} 行")\n'
)


def build_g5():
    nodes = [
        _n("s", "start", "开始", 80, 120),
        _n("k1", "sql", "查询源表", 250, 120, {
            "datasource": DW_DS,
            "sql": "SELECT order_no, user_id, amount, create_time "
                   "FROM datara_dw.ods_order ORDER BY id",
        }),
        _n("k2", "python", "导出CSV", 440, 120, {"script": _G5_SCRIPT}),
        _n("k3", "notify", "webhook通知", 630, 120, {
            "channel": "webhook", "url": "http://192.168.1.9:8000/api/v1/echo",
            "trigger": "on_success",
            "template": "${wf.name} 数据出仓完成 文件=ods_order_archive.csv @ ${sys.now}", "failHard": False,
        }),
        _n("e", "end", "结束", 820, 120),
    ]
    edges = [_e("s", "k1"), _e("k1", "k2"), _e("k2", "k3"), _e("k3", "e")]
    return "i12_G5_data_export_archive", _doc("i12_G5_data_export_archive", nodes, edges)


def check_g5(inst_id, case, status):
    ok = status == "success"
    check(case, "terminal", ok, "status=%s" % status)
    if ok:
        logs = instance_logs(inst_id, tail=40)
        has_export = "[export]" in logs
        has_notify = "[notify]" in logs
        check(case, "export_output", has_export, "[export]关键字")
        check(case, "notify_log", has_notify, "[notify]关键字")
        # 文件行数
        _f = "/datara/files/export/ods_order_archive.csv"
        rc, out = sh("docker exec datara-worker bash -c 'wc -l < %s 2>/dev/null'" % _f)
        file_rows = int(out) if out and out.strip().isdigit() else 0
        check(case, "file_exists", file_rows > 0, "csv rows=%d" % file_rows)


# ---------- 通用检查与主流程 ----------
def check(case, name, ok_flag, detail):
    print("EVIDENCE|%s|%s|%s" % (case, name, detail if ok_flag else "FAIL: %s" % detail))


def run_one(case):
    builders = {"g1": build_g1, "g2": build_g2, "g3": build_g3, "g4": build_g4, "g5": build_g5}
    checkers = {"g1": check_g1, "g2": check_g2, "g3": check_g3, "g4": check_g4, "g5": check_g5}
    build = builders[case]
    check_fn = checkers[case]
    wf_name, doc = build()
    wf_id, code = ensure_wf(wf_name)
    save_wf(wf_id, doc)
    inst_id = run_instance(wf_id, case, code)
    status, row = wait_terminal(inst_id, case, timeout=TIMEOUT.get(case, 300))
    check_fn(inst_id, case, status)


def main():
    global BASE
    parser = argparse.ArgumentParser(description="I12 普通类 G1~G5 批跑取证")
    parser.add_argument("--cases", default="g1,g2,g3,g4,g5", help="逗号分隔用例编号")
    parser.add_argument("--base", default=None, help="API base URL")
    args = parser.parse_args()
    if args.base:
        BASE = args.base.rstrip("/")
    login()
    detect_mysql_containers()
    cases = [c.strip() for c in args.cases.split(",") if c.strip()]
    for case in cases:
        print("===== %s =====" % case)
        try:
            run_one(case)
        except Exception as exc:
            print("EVIDENCE|%s|exception|%r" % (case, exc))


if __name__ == "__main__":
    main()
