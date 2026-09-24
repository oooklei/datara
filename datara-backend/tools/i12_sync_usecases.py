#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I12 同步类 S1~S5 批量编排：prep（1.9 本机 docker exec）+ 建工作流 + 跑批 + 三证取证。

在 1.9 宿主机执行（python3 标准库即可）：
  python3 i12_sync_usecases.py --cases s1,s2,s3,s4,s5            # prep+建流+跑批+验证
  python3 i12_sync_usecases.py --cases s3 --prep-only            # 仅 prep
  python3 i12_sync_usecases.py --cases s1 --base http://127.0.0.1:8000/api/v1

零接触约定：只创建/复用 i12_S1~S5 前缀工作流，不碰其他存量工作流（含另一 agent 的同步类）。
证据行格式：EVIDENCE|<case>|<key>|<value>；最终逐例打印 PASS/FAIL。
"""
import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

BASE = "http://127.0.0.1:8000/api/v1"
USER = ("admin", "Admin@123")
SRC_DS = "内置源库-ec_retail"      # id=9
DW_DS = "内置数仓-datara_dw"       # id=4
NODE_HOST = "1.9宿主机"            # 运行节点 id=2
TAGS = ["同步"]
TERMINAL = {"success", "failure", "kill"}
TIMEOUT = {"s1": 900, "s2": 600, "s3": 600, "s4": 300, "s5": 900}

TOKEN = ""
SRC_C = ""
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
    """本机 shell（docker exec 等），返回 (rc, stdout)。"""
    proc = subprocess.run(cmd, shell=isinstance(cmd, str), input=input_text,
                          capture_output=True, text=True, timeout=120)
    return proc.returncode, proc.stdout.strip()


# ---------- MySQL 容器探测与执行 ----------
def detect_mysql_containers():
    """按镜像找 mysql 容器，按库内容区分源库（含 ec_retail_east）与数仓（含 datara_dw）。"""
    global SRC_C, DW_C
    rc, out = sh("docker ps --format '{{.Names}}|{{.Image}}'")
    assert rc == 0, "docker ps 失败: %s" % out
    candidates = [line.split("|")[0] for line in out.splitlines()
                  if re.search(r"mysql|mariadb", line, re.I)]
    assert candidates, "未发现 mysql 容器"
    for name in candidates:
        dbs = mysql_dbs(name)
        if not dbs:
            continue
        if "ec_retail_east" in dbs:
            SRC_C = name
        if "datara_dw" in dbs:
            DW_C = name
    assert SRC_C and DW_C, "源库/数仓容器未识别齐: src=%r dw=%r" % (SRC_C, DW_C)
    print("EVIDENCE|common|src_container|%s" % SRC_C)
    print("EVIDENCE|common|dw_container|%s" % DW_C)


_PWD_CACHE = {}


def _mysql_env_names(container):
    if container in _PWD_CACHE:
        return _PWD_CACHE[container]
    _, out = sh("docker exec %s env" % container)
    for key in ("MYSQL_ROOT_PASSWORD", "MARIADB_ROOT_PASSWORD"):
        match = re.search(r"^%s=(.*)$" % key, out, re.M)
        if match:
            _PWD_CACHE[container] = match.group(1)
            return _PWD_CACHE[container]
    raise AssertionError("容器 %s 未找到 root 密码环境变量" % container)


def mysql_exec(container, sql, db=None, head_limit=None):
    """docker exec mysql 执行 SQL（argv 直跑，-N -B 制表符输出）；返回 stdout 行列表。"""
    pwd = _mysql_env_names(container)
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


def mysql_dbs(container):
    rc, out = sh("docker exec %s env" % container)
    if rc != 0:
        return set()
    pwd = ""
    for key in ("MYSQL_ROOT_PASSWORD", "MARIADB_ROOT_PASSWORD"):
        match = re.search(r"^%s=(.*)$" % key, out, re.M)
        if match:
            pwd = match.group(1)
            break
    if not pwd:
        return set()
    rc, out = sh("docker exec %s sh -c %s" % (
        container, json.dumps('MYSQL_PWD="%s" mysql -uroot -N -e "SHOW DATABASES"' % pwd)))
    return set(out.splitlines()) if rc == 0 else set()


def scalar(container, sql, db=None):
    rows = mysql_exec(container, sql, db)
    return rows[0] if rows else None


# ---------- 表结构克隆（S1/S3） ----------
def _pk_column(container, schema, table):
    rows = mysql_exec(container,
                      "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.STATISTICS "
                      "WHERE TABLE_SCHEMA='%s' AND TABLE_NAME='%s' AND INDEX_NAME='PRIMARY' "
                      "ORDER BY SEQ_IN_INDEX LIMIT 1" % (schema, table))
    return rows[0] if rows else None


def _columns(container, schema, table):
    rows = mysql_exec(container,
                      "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                      "WHERE TABLE_SCHEMA='%s' AND TABLE_NAME='%s' ORDER BY ORDINAL_POSITION"
                      % (schema, table))
    return rows


def clone_table(src_container, dst_container, src_schema, src_table, dst_schema, dst_table):
    """源表结构克隆到目标库：去 AUTO_INCREMENT=n 与 UNIQUE KEY（保留 PK），先删后建幂等。

    mysql -B 输出转义还原：首列为表名，正文 \\n/\\t 为字面转义。
    """
    rows = mysql_exec(src_container, "SHOW CREATE TABLE `%s`.`%s`" % (src_schema, src_table))
    parts = rows[0].split("\t", 1)
    create = parts[1] if len(parts) > 1 else rows[0]
    create = create.replace("\\n", "\n").replace("\\t", "  ")
    create = re.sub(r" AUTO_INCREMENT=\d+", "", create)
    lines = [ln for ln in create.splitlines() if "UNIQUE KEY" not in ln]
    create = re.sub(r",(\s*\))", r"\1", "\n".join(lines))
    create = create.replace("`%s`" % src_table, "`%s`" % dst_table, 1)
    mysql_exec(dst_container, "DROP TABLE IF EXISTS `%s`.`%s`" % (dst_schema, dst_table))
    mysql_exec(dst_container, create, db=dst_schema)
    print("EVIDENCE|prep|clone|%s.%s <- %s.%s" % (dst_schema, dst_table, src_schema, src_table))


def clone_rows(container, src_schema, src_table, dst_schema, dst_table, limit, offset, order):
    """整行克隆 limit 行；PK 列加 offset 防多批次主键冲突（UNIQUE 索引已在建表时剔除）。"""
    pk = _pk_column(container, src_schema, src_table)
    cols = _columns(container, src_schema, src_table)
    exprs = ["(`%s` + %d)" % (pk, offset) if pk and c == pk else "`%s`" % c for c in cols]
    col_list = ", ".join("`%s`" % c for c in cols)
    sel_list = ", ".join(exprs)
    mysql_exec(container,
               "INSERT INTO `%s`.`%s` (%s) SELECT %s FROM `%s`.`%s` ORDER BY %s %s LIMIT %d"
               % (dst_schema, dst_table, col_list, sel_list, src_schema, src_table, pk, order, limit))
    print("EVIDENCE|prep|rows|%s.%s +%d (pk_offset=%d, order=%s)" % (src_schema, dst_table, limit, offset, order))


# ---------- 各例 prep ----------
def prep_s1():
    """数仓预建 ods_order（结构克隆）。"""
    exists = scalar(DW_C, "SHOW TABLES FROM `datara_dw` LIKE 'ods_order'")
    if exists:
        print("EVIDENCE|prep|s1|dw.ods_order 已存在，跳过")
        return
    clone_table(SRC_C, DW_C, "ec_retail", "ods_order", "datara_dw", "ods_order")
    print("EVIDENCE|prep|s1|建表完成")


def prep_s2_phase1():
    """run1 基线：100 行历史单 pay_time 改为 NOW()-1h（进入当日窗口）。"""
    assert scalar(SRC_C, "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
                         "WHERE TABLE_SCHEMA='ec_retail' AND TABLE_NAME='ods_payment' "
                         "AND COLUMN_NAME='pay_time'") == "1", "ods_payment 缺 pay_time 列"
    pre = int(scalar(SRC_C, "SELECT COUNT(*) FROM ec_retail.ods_payment WHERE pay_time >= CURDATE()") or 0)
    mysql_exec(SRC_C, "UPDATE ec_retail.ods_payment SET pay_time = NOW() - INTERVAL 1 HOUR "
                      "WHERE pay_time < CURDATE() AND pay_time IS NOT NULL LIMIT 100")
    print("EVIDENCE|prep|s2|当日基线：先存当日行 %d + 基线注入 100" % pre)


def prep_s2_phase2():
    """run2 前注入差值：50 行历史单 pay_time 改为 NOW()。"""
    mysql_exec(SRC_C, "UPDATE ec_retail.ods_payment SET pay_time = NOW() "
                      "WHERE pay_time < CURDATE() AND pay_time IS NOT NULL LIMIT 50")
    print("EVIDENCE|prep|s2|差值注入 50 行 pay_time=NOW()")


def prep_s3(phase):
    """east/south/north 各建 ods_order_rev（结构克隆 ods_order，剔除 UNIQUE，PK 偏移防冲突）。"""
    plan = {"east": (100, 0, "ASC"), "south": (80, 200000, "DESC"), "north": (60, 400000, "ASC")}
    targets = ["east", "south"] if phase == 1 else ["north"]
    for suffix in targets:
        schema = "ec_retail_%s" % suffix
        limit, offset, order = plan[suffix]
        clone_table(SRC_C, SRC_C, "ec_retail", "ods_order", schema, "ods_order_rev")
        clone_rows(SRC_C, "ec_retail", "ods_order", schema, "ods_order_rev", limit, offset, order)
        count = scalar(SRC_C, "SELECT COUNT(*) FROM `%s`.ods_order_rev" % schema)
        print("EVIDENCE|prep|s3|%s.ods_order_rev=%s" % (schema, count))


def prep_s4():
    """宿主机生成 orders.csv（500 数据行 + 表头）。"""
    import os
    directory = "/mnt/lei/datara/i12files"
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "orders.csv")
    statuses = ["PAID", "NEW", "SHIPPED", "CLOSED"]
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("order_no,user_id,amount,status,create_time\n")
        for i in range(500):
            handle.write("i12NO%04d,%d,%.2f,%s,2026-09-%02d %02d:%02d:00\n"
                         % (i, 1000 + i % 97, 100.50 + i % 90, statuses[i % 4],
                            20 + i % 3, i % 24, i % 60))
    print("EVIDENCE|prep|s4|%s (501 行)" % path)


# ---------- 工作流文档构建 ----------
def node(uid, ntype, name, data, x=0, y=100):
    item = {"id": uid, "type": ntype, "position": {"x": x, "y": y}, "data": dict(data)}
    item["data"]["name"] = name
    return item


def edge(sid, tid, source_handle=None):
    e = {"id": "e_%s_%s" % (sid, tid), "source": sid, "target": tid, "kind": "flow"}
    if source_handle:
        e["sourceHandle"] = source_handle
    return e


def sync_data(**kw):
    base = {
        "readerType": "mysql", "readerDs": "", "readerTable": "",
        "readerFormat": "csv", "readerPath": "", "readerEncoding": "utf-8",
        "readerDelimiter": ",", "readerHeader": True, "readerSheet": "",
        "readerSchemasText": "", "autoSchema": True,
        "incrementalColumn": "", "incrementalExpr": "",
        "writerType": "mysql", "writerDs": "", "writerTable": "",
        "autoCreate": True, "truncate": False,
        "strategy": "union", "flagColumn": "src_schema",
        "fieldMap": [], "batchSize": 2000, "errorThreshold": 0,
    }
    base.update(kw)
    return base


def assert_data(rules, **kw):
    base = {"assertSrc": "upstream", "assertUpstream": "", "assertDs": "", "assertTable": "",
            "rules": rules, "ruleColumns": [], "onFail": "fail"}
    base.update(kw)
    return base


def file_sync_data(**kw):
    base = {
        "runtimeNode": "", "filePath": "", "fileName": "", "stagedPath": "",
        "fileType": "csv", "delimiter": ",", "encoding": "utf-8", "headerRows": 1,
        "targetDs": "", "targetSchema": "", "targetTable": "",
        "autoCreate": True, "ddl": "", "writeMode": "append",
        "flagColumn": "src_schema", "fieldMap": [],
    }
    base.update(kw)
    return base


def chain_doc(wf_id, name, middle):
    """开始 → middle 节点序列 → 结束 顺序连线。"""
    nodes = [node("nd_start", "start", "开始", {}, 100)]
    x = 300
    for item in middle:
        nodes.append(item)
        x += 220
    nodes.append(node("nd_end", "end", "结束", {}, x))
    ids = [n["id"] for n in nodes]
    # assert 节点出边带 sourceHandle='success'（否则 branch_match 不命中、下游被 skip）
    edges = []
    for i in range(len(ids) - 1):
        src_node = next(n for n in nodes if n["id"] == ids[i])
        sh = "success" if src_node.get("type") == "assert" else None
        edges.append(edge(ids[i], ids[i + 1], sh))
    return {"id": wf_id, "name": name, "version": 1, "meta": {"profile": "dag"},
            "nodes": nodes, "edges": edges}


def doc_s1(wf_id):
    return chain_doc(wf_id, "i12_S1_ods_order_load", [
        node("nd_sync", "sync", "数据同步", sync_data(
            readerDs=SRC_DS, readerTable="ods_order", readerSchemasText="ec_retail",
            autoSchema=False, writerDs=DW_DS, writerTable="ods_order",
            autoCreate=False, truncate=True)),
        node("nd_assert", "assert", "对账校验",
             assert_data([{"key": "rows", "value": "min=250000", "note": "行数下限"}])),
    ])


def doc_s2(wf_id):
    return chain_doc(wf_id, "i12_S2_ods_payment_incr", [
        node("nd_sync", "sync", "数据同步", sync_data(
            readerDs=SRC_DS, readerTable="ods_payment", readerSchemasText="ec_retail",
            autoSchema=False, incrementalColumn="pay_time", incrementalExpr="${last_sync_time}",
            writerDs=DW_DS, writerTable="ods_payment", autoCreate=True, truncate=False)),
    ])


def doc_s3(wf_id):
    return chain_doc(wf_id, "i12_S3_rev_source", [
        node("nd_sync", "sync", "数据同步", sync_data(
            writerDs=DW_DS, writerTable="ods_order_rev", autoCreate=True, truncate=True,
            readerDs=SRC_DS, readerTable="ods_order_rev",
            readerSchemasText="ec_retail_east,ec_retail_south", autoSchema=True,
            strategy="src_flag", flagColumn="src_schema", batchSize=1000)),
        node("nd_assert", "assert", "对账校验",
             assert_data([{"key": "rows", "value": "min=180", "note": "run1 精确值，run2=240 亦过"}])),
    ])


def doc_s4(wf_id):
    ddl = ("CREATE TABLE IF NOT EXISTS i12_ods_order_file ("
           "order_no VARCHAR(64), user_id BIGINT, amount DECIMAL(12,2), "
           "status VARCHAR(16), create_time DATETIME)")
    return chain_doc(wf_id, "i12_S4_file_to_db", [
        node("nd_fsync", "file_sync", "文件同步", file_sync_data(
            runtimeNode=NODE_HOST, filePath="/mnt/lei/datara/i12files/orders.csv",
            fileType="csv", delimiter=",", encoding="utf-8", headerRows=1,
            targetDs=DW_DS, targetTable={"schema": "datara_dw", "table": "i12_ods_order_file"},
            autoCreate=True, ddl=ddl, writeMode="overwrite")),
        node("nd_assert", "assert", "对账校验", assert_data([
            {"key": "rows", "value": "min=500,max=500", "note": "文件数据行精确值"},
            {"key": "unique", "value": "order_no", "note": "主键唯一"},
        ])),
    ])


def doc_s5(wf_id):
    tables = [("ods_cart", 9872), ("ods_coupon", 5000), ("ods_refund", 14750)]
    nodes = [node("nd_start", "start", "开始", {}, 80),
             node("nd_fork", "fork", "并行分叉", {"parallel": 3}, 260)]
    edges = [edge("nd_start", "nd_fork")]
    x = 460
    ends = []
    for table, rows_min in tables:
        sid = "nd_sync_%s" % table
        aid = "nd_assert_%s" % table
        nodes.append(node(sid, "sync", "数据同步-%s" % table, sync_data(
            readerDs=SRC_DS, readerTable=table, readerSchemasText="ec_retail",
            autoSchema=False, writerDs=DW_DS, writerTable=table,
            autoCreate=True, truncate=True), x, 40 if table == "ods_cart" else (180 if table == "ods_coupon" else 320)))
        nodes.append(node(aid, "assert", "对账校验-%s" % table,
                          assert_data([{"key": "rows", "value": "min=%d" % rows_min,
                                        "note": "源表行数下限"}]), x + 220,
                          nodes[-1]["position"]["y"]))
        edges.append(edge("nd_fork", sid))
        edges.append(edge(sid, aid))
        ends.append(aid)
        x += 480
    nodes.append(node("nd_join", "join", "汇合", {}, x, 180))
    nodes.append(node("nd_end", "end", "结束", {}, x + 160, 180))
    for aid in ends:
        edges.append(edge(aid, "nd_join", "success"))
    edges.append(edge("nd_join", "nd_end"))
    return {"id": wf_id, "name": "i12_S5_multi_fork", "version": 1, "meta": {"profile": "dag"},
            "nodes": nodes, "edges": edges}


# ---------- 工作流生命周期 ----------
def ensure_wf(name):
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


def save_doc(wf_id, doc):
    resp = http("PUT", "/workflow-definitions/%s/save" % wf_id,
                {"doc": doc, "remark": "I12 同步类用例", "tags": TAGS})
    assert resp.get("code") == 0, "保存失败 %s: %s" % (wf_id, resp)
    print("EVIDENCE|wf|save|%s version=%s" % (wf_id, resp["data"]))


def run_and_poll(wf_id, code, case):
    resp = http("POST", "/workflow-definitions/%s/run" % wf_id, {})
    assert resp.get("code") == 0, "运行失败: %s" % resp
    time.sleep(3)
    instance_id = None
    for _ in range(30):
        listing = http("GET", "/instances?wf_code=%s&page_no=1&page_size=5" % code)
        rows = (listing.get("data") or {}).get("list") or []
        if rows:
            instance_id = rows[0]["instanceId"]
            break
        time.sleep(3)
    assert instance_id, "未找到新实例"
    print("EVIDENCE|%s|instance|%s" % (case, instance_id))
    deadline = time.time() + TIMEOUT[case]
    while time.time() < deadline:
        detail = http("GET", "/instances/%s" % instance_id)
        assert detail.get("code") == 0, detail
        state = detail["data"]["state"]
        if state in TERMINAL:
            print("EVIDENCE|%s|final_state|%s" % (case, state))
            return detail["data"]
        time.sleep(5)
    raise AssertionError("%s 轮询超时" % case)


def tasks_of(detail, ntype):
    return [t for t in detail.get("taskInstances") or [] if t.get("nodeType") == ntype]


def outputs_of(task):
    outs = task.get("outputs")
    if isinstance(outs, str):
        try:
            outs = json.loads(outs)
        except ValueError:
            outs = {}
    return outs or {}


def tail_log(task, case, lines=100):
    resp = http("GET", "/logs/task/%s" % task["id"])
    content = (resp.get("data") or {}).get("content") or ""
    tail = "\n".join(content.splitlines()[-lines:])
    print("---- 日志尾 %d 行 (%s/%s) ----" % (lines, case, task.get("name")))
    print(tail if tail else "(空)")
    print("---- 日志尾结束 ----")
    return content


def check(case, name, ok_flag, detail):
    print("EVIDENCE|%s|%s|%s" % (case, name, detail if ok_flag else "FAIL: %s" % detail))
    return bool(ok_flag)


# ---------- 各例编排 ----------
def run_s1():
    prep_s1()
    wf_id, code = ensure_wf("i12_S1_ods_order_load")
    save_doc(wf_id, doc_s1(wf_id))
    detail = run_and_poll(wf_id, code, "s1")
    ok = detail["state"] == "success"
    src = int(scalar(SRC_C, "SELECT COUNT(*) FROM ec_retail.ods_order") or 0)
    dw = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.ods_order") or 0)
    sync_tasks = tasks_of(detail, "sync")
    written = int(outputs_of(sync_tasks[0]).get("write_rows", -1)) if sync_tasks else -1
    asserts_ok = all(t["state"] == "success" for t in tasks_of(detail, "assert"))
    ok &= check("s1", "src_count", src == 250000, src)
    ok &= check("s1", "dw_count", dw == src, "%d vs %d" % (dw, src))
    ok &= check("s1", "write_rows", written == src, written)
    ok &= check("s1", "assert_success", asserts_ok, asserts_ok)
    if sync_tasks:
        tail_log(sync_tasks[0], "s1")
    return ok


def run_s2():
    prep_s2_phase1()
    wf_id, code = ensure_wf("i12_S2_ods_payment_incr")
    save_doc(wf_id, doc_s2(wf_id))
    var_value_tpl = "$[yyyy-MM-dd 000000]"
    listing = http("GET", "/workflow-variables?wf=%s" % wf_id)
    rows = [v for v in (listing.get("data") or []) if v.get("name") == "last_sync_time"]
    if rows:
        http("PUT", "/workflow-variables/%s" % rows[0]["id"],
             {"wf": wf_id, "name": "last_sync_time", "value": var_value_tpl,
              "type": "文本", "encrypted": False, "options": [], "desc": "增量边界"})
        var_id = rows[0]["id"]
    else:
        created = http("POST", "/workflow-variables",
                       {"wf": wf_id, "name": "last_sync_time", "value": var_value_tpl,
                        "type": "文本", "encrypted": False, "options": [], "desc": "增量边界"})
        assert created.get("code") == 0, created
        var_id = created["data"]["id"]
    print("EVIDENCE|s2|variable|last_sync_time=%s (id=%s)" % (var_value_tpl, var_id))

    detail1 = run_and_poll(wf_id, code, "s2")
    ok = detail1["state"] == "success"
    sync1 = tasks_of(detail1, "sync")
    written1 = int(outputs_of(sync1[0]).get("write_rows", -1)) if sync1 else -1
    expect1 = int(scalar(SRC_C, "SELECT COUNT(*) FROM ec_retail.ods_payment WHERE pay_time >= CURDATE()") or 0)
    boundary = detail1.get("endTime") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    dw1 = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.ods_payment") or 0)
    ok &= check("s2", "run1_write_rows", written1 == expect1, "%d vs %d" % (written1, expect1))
    print("EVIDENCE|s2|boundary|%s" % boundary)

    prep_s2_phase2()
    body = {"wf": wf_id, "name": "last_sync_time", "value": boundary,
            "type": "文本", "encrypted": False, "options": [], "desc": "增量边界"}
    upd = http("PUT", "/workflow-variables/%s" % var_id, body)
    ok &= check("s2", "variable_updated", upd.get("code") == 0, boundary)

    detail2 = run_and_poll(wf_id, code, "s2")
    sync2 = tasks_of(detail2, "sync")
    written2 = int(outputs_of(sync2[0]).get("write_rows", -1)) if sync2 else -1
    dw2 = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.ods_payment") or 0)
    # 源表存量 2099-12-31 哨兵行恒被增量窗口重扫（他人 fixture，不可动数据）：断言动态三分一致
    sentinel = "2038-01-01"
    window = int(scalar(SRC_C, "SELECT COUNT(*) FROM ec_retail.ods_payment WHERE pay_time >= '%s'" % boundary) or 0)
    win_sentinel = int(scalar(SRC_C, "SELECT COUNT(*) FROM ec_retail.ods_payment "
                                     "WHERE pay_time >= '%s' AND pay_time >= '%s'" % (boundary, sentinel)) or 0)
    win_fresh = int(scalar(SRC_C, "SELECT COUNT(*) FROM ec_retail.ods_payment "
                                  "WHERE pay_time >= '%s' AND pay_time < '%s'" % (boundary, sentinel)) or 0)
    ok &= detail2["state"] == "success"
    ok &= check("s2", "window_fresh(注入精确50)", win_fresh == 50, win_fresh)
    ok &= check("s2", "window_sentinel", window == win_sentinel + win_fresh,
                "总%d=哨兵%d+新%d" % (window, win_sentinel, win_fresh))
    ok &= check("s2", "run2_write_rows", written2 == window, "%d vs 窗口%d" % (written2, window))
    ok &= check("s2", "dw_delta", dw2 - dw1 == window, "%d-%d vs 窗口%d" % (dw2, dw1, window))
    if sync2:
        tail_log(sync2[0], "s2")
    return ok


def run_s3():
    prep_s3(1)
    wf_id, code = ensure_wf("i12_S3_rev_source")
    save_doc(wf_id, doc_s3(wf_id))
    detail1 = run_and_poll(wf_id, code, "s3")
    ok = detail1["state"] == "success"
    sync1 = tasks_of(detail1, "sync")
    inc1 = outputs_of(sync1[0]).get("schemas_included") if sync1 else []
    total1 = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.ods_order_rev") or 0)
    groups1 = dict(line.split("\t") for line in mysql_exec(
        DW_C, "SELECT src_schema, COUNT(*) FROM datara_dw.ods_order_rev GROUP BY src_schema"))
    ok &= check("s3", "run1_total", total1 == 180, total1)
    ok &= check("s3", "run1_east", groups1.get("ec_retail_east") == "100", groups1.get("ec_retail_east"))
    ok &= check("s3", "run1_south", groups1.get("ec_retail_south") == "80", groups1.get("ec_retail_south"))
    print("EVIDENCE|s3|run1_schemas_included|%s" % inc1)

    prep_s3(2)
    detail2 = run_and_poll(wf_id, code, "s3")
    sync2 = tasks_of(detail2, "sync")
    inc2 = outputs_of(sync2[0]).get("schemas_included") if sync2 else []
    total2 = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.ods_order_rev") or 0)
    groups2 = dict(line.split("\t") for line in mysql_exec(
        DW_C, "SELECT src_schema, COUNT(*) FROM datara_dw.ods_order_rev GROUP BY src_schema"))
    content = tail_log(sync2[0], "s3") if sync2 else ""
    ok &= detail2["state"] == "success"
    ok &= check("s3", "run2_total", total2 == 240, total2)
    ok &= check("s3", "run2_north", groups2.get("ec_retail_north") == "60", groups2.get("ec_retail_north"))
    ok &= check("s3", "schemas_included_3",
                inc2 and len(inc2) == 3 and "ec_retail_north" in inc2, inc2)
    ok &= check("s3", "log_autoschema", "探测到新增 schema: ec_retail_north" in content,
                "关键字命中" if "探测到新增 schema: ec_retail_north" in content else "未命中")
    return ok


def run_s4():
    prep_s4()
    wf_id, code = ensure_wf("i12_S4_file_to_db")
    save_doc(wf_id, doc_s4(wf_id))
    detail = run_and_poll(wf_id, code, "s4")
    ok = detail["state"] == "success"
    fs = tasks_of(detail, "file_sync")
    outs = outputs_of(fs[0]) if fs else {}
    count = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.i12_ods_order_file") or 0)
    uniq = int(scalar(DW_C, "SELECT COUNT(DISTINCT order_no) FROM datara_dw.i12_ods_order_file") or 0)
    asserts_ok = all(t["state"] == "success" for t in tasks_of(detail, "assert"))
    content = tail_log(fs[0], "s4") if fs else ""
    ok &= check("s4", "rows_read", int(outs.get("rows_read", -1)) == 500, outs.get("rows_read"))
    ok &= check("s4", "rows_written", int(outs.get("rows_written", -1)) == 500, outs.get("rows_written"))
    ok &= check("s4", "rows_skipped", int(outs.get("rows_skipped", -1)) == 0, outs.get("rows_skipped"))
    ok &= check("s4", "dw_count", count == 500, count)
    ok &= check("s4", "unique_order_no", uniq == 500, uniq)
    ok &= check("s4", "assert_success", asserts_ok, asserts_ok)
    ok &= check("s4", "log_staging", "_filesync_" in content, "命中" if "_filesync_" in content else "未命中")
    return ok


def run_s5():
    wf_id, code = ensure_wf("i12_S5_multi_fork")
    save_doc(wf_id, doc_s5(wf_id))
    detail = run_and_poll(wf_id, code, "s5")
    ok = detail["state"] == "success"
    syncs = {t["name"]: t for t in tasks_of(detail, "sync")}
    spans = []
    for table in ("ods_cart", "ods_coupon", "ods_refund"):
        task = syncs.get("数据同步-%s" % table)
        if not task:
            ok &= check("s5", "task_%s" % table, False, "缺失")
            continue
        src = int(scalar(SRC_C, "SELECT COUNT(*) FROM ec_retail.%s" % table) or 0)
        dw = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.%s" % table) or 0)
        written = int(outputs_of(task).get("write_rows", -1))
        ok &= check("s5", "%s_rows" % table, written == src and dw == src,
                    "src=%d dw=%d written=%d" % (src, dw, written))
        spans.append((task.get("startTime"), task.get("endTime"), table))
    overlap = (max(s for s, _, _ in spans) <= min(e for _, e, _ in spans)) if len(spans) == 3 else False
    ok &= check("s5", "parallel_overlap", overlap, str(spans))
    for task in syncs.values():
        tail_log(task, "s5")
    return ok


CASES = {"s1": run_s1, "s2": run_s2, "s3": run_s3, "s4": run_s4, "s5": run_s5}
PREPS = {
    "s1": prep_s1, "s2": prep_s2_phase1, "s3": lambda: prep_s3(1),
    "s4": prep_s4, "s5": lambda: None,
}


def main():
    global BASE
    parser = argparse.ArgumentParser(description="I12 同步类 S1~S5 批量编排")
    parser.add_argument("--cases", default="s1,s2,s3,s4,s5")
    parser.add_argument("--base", default=BASE)
    parser.add_argument("--prep-only", action="store_true")
    parser.add_argument("--skip-detect", action="store_true", help="仅调 API 时跳过容器探测")
    args = parser.parse_args()
    BASE = args.base
    cases = [c.strip().lower() for c in args.cases.split(",") if c.strip()]
    for case in cases:
        assert case in CASES, "未知用例: %s" % case
    login()
    if not args.skip_detect or not args.prep_only:
        detect_mysql_containers()
    if args.prep_only:
        for case in cases:
            PREPS[case]()
        return 0
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
