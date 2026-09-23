#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I12 ETL 类 E1~E5 批量编排：prep（1.9 本机 docker exec）+ 建工作流 + 跑批 + 三证取证。

在 1.9 宿主机执行（python3 标准库即可）：
  python3 i12_etl_usecases.py --cases e1,e2,e3,e4,e5            # prep+建流+跑批+验证
  python3 i12_etl_usecases.py --cases e5 --prep-only            # 仅 prep
  python3 i12_etl_usecases.py --cases e1 --base http://127.0.0.1:8000/api/v1

用例形态（设计文档 §7.2 E 表）：
  E1 ODS→DWD 清洗：SQL 链（去重/脏行过滤）+ C25 上游闸门
  E2 DWD→DWS 日聚合：fork 双 SQL 分支各自建 DWS 表 → merge（OR）汇合
  E3 ELT 先入仓后加工：C24 文件原样入 raw（全 TEXT）→ SQL 类型规整 → C25
  E4 文件+库表混合加工：C22 读 CSV 注册临时表 → SQL ${tmp.*} JOIN 事实表 → C25
  E5 带闸门分层链：SQL→C25→SQL→C25；run1 过 → run2 篡改源断流（下游不执行）→ run3 恢复

零接触约定：只创建/复用 i12_E1~E5 前缀工作流，自建表均 i12_ / dwd_ / dws_ 新表，不碰他人资产。
证据行格式：EVIDENCE|<case>|<key>|<value>；最终逐例打印 PASS/FAIL。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

BASE = "http://127.0.0.1:8000/api/v1"
USER = ("admin", "Admin@123")
DW_DS = "内置数仓-datara_dw"       # id=4（默认库 datara_dw）
NODE_HOST = "1.9宿主机"            # 运行节点 id=2
TAGS = ["ETL"]
TERMINAL = {"success", "failure", "kill"}
TIMEOUT = {"e1": 300, "e2": 300, "e3": 300, "e4": 600, "e5": 900}

TOKEN = ""
SRC_C = ""
DW_C = ""

# E1/E2/E5 共用清洗 SQL 模板（按 order_no 去重保 MIN(id)，过滤 amount<0 / 空单号）
CLEAN_SQL_TMPL = (
    "DROP TABLE IF EXISTS {dwd};"
    "CREATE TABLE {dwd} AS"
    " SELECT t.* FROM {src} t"
    " JOIN (SELECT MIN(id) AS keep_id FROM {src}"
    "   WHERE amount >= 0 AND order_no IS NOT NULL AND order_no <> ''"
    "   GROUP BY order_no) k ON t.id = k.keep_id"
    " WHERE t.amount >= 0"
)


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


def _mysql_pwd(container):
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


def _pk_column(container, schema, table):
    rows = mysql_exec(container,
                      "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.STATISTICS "
                      "WHERE TABLE_SCHEMA='%s' AND TABLE_NAME='%s' AND INDEX_NAME='PRIMARY' "
                      "ORDER BY SEQ_IN_INDEX LIMIT 1" % (schema, table))
    return rows[0] if rows else None


def _columns(container, schema, table):
    return mysql_exec(container,
                      "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                      "WHERE TABLE_SCHEMA='%s' AND TABLE_NAME='%s' ORDER BY ORDINAL_POSITION"
                      % (schema, table))


def clone_table(src_container, dst_container, src_schema, src_table, dst_schema, dst_table):
    """源表结构克隆：去 AUTO_INCREMENT=n 与 UNIQUE KEY（保留 PK），先删后建幂等。"""
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


# ---------- 各例 prep ----------
def _ensure_ods_order():
    """E 系事实表底座：dw.ods_order 缺失则结构克隆 + 整表灌入。"""
    if not scalar(DW_C, "SHOW TABLES FROM `datara_dw` LIKE 'ods_order'"):
        clone_table(SRC_C, DW_C, "ec_retail", "ods_order", "datara_dw", "ods_order")
    count = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.ods_order") or 0)
    if count == 0:
        mysql_exec(DW_C, "INSERT INTO datara_dw.ods_order SELECT * FROM ec_retail.ods_order")
        count = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.ods_order") or 0)
    print("EVIDENCE|prep|ods_order|%d 行" % count)
    cols = set(_columns(DW_C, "datara_dw", "ods_order"))
    missing = {"id", "order_no", "amount", "order_date", "status", "user_id"} - cols
    assert not missing, "ods_order 缺列: %s" % missing
    return count


def _build_dwd_clean():
    """确保 E1 清洗产物存在（E2/E4 依赖底座时直接 SQL 预建）。"""
    count = int(scalar(DW_C, "SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES "
                             "WHERE TABLE_SCHEMA='datara_dw' AND TABLE_NAME='dwd_order_clean'") or 0)
    if count:
        return int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_clean") or 0)
    mysql_exec(DW_C, CLEAN_SQL_TMPL.format(dwd="dwd_order_clean", src="ods_order"))
    n = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_clean") or 0)
    print("EVIDENCE|prep|dwd_order_clean|预建 %d 行" % n)
    return n


def prep_e1():
    _ensure_ods_order()


def prep_e2():
    _ensure_ods_order()
    _build_dwd_clean()


def prep_e3():
    """复用 S4 的 orders.csv（500 数据行 + 表头）。"""
    directory = "/mnt/lei/datara/i12files"
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "orders.csv")
    if not os.path.exists(path):
        statuses = ["PAID", "NEW", "SHIPPED", "CLOSED"]
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("order_no,user_id,amount,status,create_time\n")
            for i in range(500):
                handle.write("i12NO%04d,%d,%.2f,%s,2026-09-%02d %02d:%02d:00\n"
                             % (i, 1000 + i % 97, 100.50 + i % 90, statuses[i % 4],
                                20 + i % 3, i % 24, i % 60))
    with open(path, encoding="utf-8") as handle:
        total = sum(1 for _ in handle)
    print("EVIDENCE|prep|e3|%s (%d 行)" % (path, total))


def prep_e4():
    """C22 共享卷维表 CSV：region 映射按 dw.ods_order 实际 user_id 全覆盖生成。"""
    _ensure_ods_order()
    directory = "/mnt/lei/datara/files"
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "i12_etl_user_region.csv")
    regions = ["华东", "华南", "华北", "西南", "东北"]
    user_ids = mysql_exec(DW_C, "SELECT DISTINCT user_id FROM datara_dw.ods_order ORDER BY user_id")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("user_id,region\n")
        for i, uid in enumerate(user_ids):
            handle.write("%s,%s\n" % (uid, regions[i % len(regions)]))
    print("EVIDENCE|prep|e4|%s (%d 维表行)" % (path, len(user_ids)))
    rc, out = sh(["docker", "exec", "datara-worker", "sh", "-c",
                  "wc -l < /datara/files/i12_etl_user_region.csv"])
    print("EVIDENCE|prep|e4|worker_container_view|%s" % (out if rc == 0 else "不可见(仅告警)"))


def prep_e5():
    """E5 自有源表 i12_o_order_src（克隆 ods_order 结构，灌 5000 行）+ 清空下游。"""
    _ensure_ods_order()
    if not scalar(DW_C, "SHOW TABLES FROM `datara_dw` LIKE 'i12_o_order_src'"):
        clone_table(DW_C, DW_C, "datara_dw", "ods_order", "datara_dw", "i12_o_order_src")
    count = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.i12_o_order_src") or 0)
    if count != 5000:
        mysql_exec(DW_C, "TRUNCATE TABLE datara_dw.i12_o_order_src")
        mysql_exec(DW_C, "INSERT INTO datara_dw.i12_o_order_src "
                         "SELECT * FROM datara_dw.ods_order LIMIT 5000")
        count = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.i12_o_order_src") or 0)
    mysql_exec(DW_C, "DROP TABLE IF EXISTS datara_dw.dwd_order_gate")
    mysql_exec(DW_C, "DROP TABLE IF EXISTS datara_dw.dws_gate_day")
    print("EVIDENCE|prep|e5|i12_o_order_src=%d 行，下游已清" % count)


def restore_e5():
    """run3 前恢复源表 5000 行。"""
    mysql_exec(DW_C, "TRUNCATE TABLE datara_dw.i12_o_order_src")
    mysql_exec(DW_C, "INSERT INTO datara_dw.i12_o_order_src "
                     "SELECT * FROM datara_dw.ods_order LIMIT 5000")
    count = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.i12_o_order_src") or 0)
    print("EVIDENCE|e5|restore|src=%d 行" % count)


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


def sql_data(sql, result_table=None, **kw):
    base = {"datasource": DW_DS, "pre": "", "sql": sql, "post": ""}
    if result_table:  # C25 上游模式解析 SQL 目标表所需（engine._assert_upstream_target）
        base["outputs"] = {"params": [], "tables": [{"k": result_table, "v": result_table}]}
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


def file22_data(**kw):
    """C22 文件读取（临时数据注册）。表单键 tmpName（避免与节点显示名 name 冲突）。"""
    base = {
        "mode": "manual", "datasource": "",
        "path": "", "format": "csv", "encoding": "utf-8", "delimiter": ",", "header": True, "sheet": "",
        "register": True, "tmpName": "", "kind": "table", "targetDs": DW_DS,
        "retention": "immediate", "keepDays": 7,
    }
    base.update(kw)
    return base


def chain_doc(wf_id, name, middle):
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


def doc_e1(wf_id):
    clean_sql = CLEAN_SQL_TMPL.format(dwd="dwd_order_clean", src="ods_order")
    match_sql = ("SELECT IF((SELECT COUNT(*) FROM dwd_order_clean) = "
                 "(SELECT COUNT(*) FROM (SELECT order_no FROM ods_order "
                 "WHERE amount >= 0 AND order_no IS NOT NULL AND order_no <> '' "
                 "GROUP BY order_no) s), 1, 0)")
    return chain_doc(wf_id, "i12_E1_ods_to_dwd_clean", [
        node("nd_sql", "sql", "ODS清洗", sql_data(clean_sql, "dwd_order_clean"), 300),
        node("nd_assert", "assert", "对账校验", assert_data([
            {"key": "rows", "value": "min=1", "note": "清洗产物非空"},
            {"key": "unique", "value": "order_no", "note": "去重后单号唯一"},
            {"key": "sql", "value": match_sql, "note": "行数与源去重口径一致"},
        ]), 520),
    ])


def doc_e2(wf_id):
    day_sql = ("DROP TABLE IF EXISTS dws_order_stat_day;"
               "CREATE TABLE dws_order_stat_day AS"
               " SELECT order_date, COUNT(*) AS order_cnt, SUM(amount) AS amt_sum"
               " FROM dwd_order_clean GROUP BY order_date")
    day_match = ("SELECT IF((SELECT COALESCE(SUM(order_cnt),0) FROM dws_order_stat_day) = "
                 "(SELECT COUNT(*) FROM dwd_order_clean), 1, 0)")
    st_sql = ("DROP TABLE IF EXISTS dws_order_stat_status;"
              "CREATE TABLE dws_order_stat_status AS"
              " SELECT order_date, status, COUNT(*) AS order_cnt"
              " FROM dwd_order_clean GROUP BY order_date, status")
    st_match = ("SELECT IF((SELECT COALESCE(SUM(order_cnt),0) FROM dws_order_stat_status) = "
                "(SELECT COUNT(*) FROM dwd_order_clean), 1, 0)")
    nodes = [
        node("nd_start", "start", "开始", {}, 80),
        node("nd_fork", "fork", "并行分叉", {"parallel": 2}, 240),
        node("nd_sql_day", "sql", "日聚合-按天", sql_data(day_sql, "dws_order_stat_day"), 440, 40),
        node("nd_as_day", "assert", "校验-按天", assert_data([
            {"key": "rows", "value": "min=1", "note": "聚合非空"},
            {"key": "sql", "value": day_match, "note": "各天单数之和=DWD 总数"},
        ]), 660, 40),
        node("nd_sql_st", "sql", "日聚合-按状态", sql_data(st_sql, "dws_order_stat_status"), 440, 220),
        node("nd_as_st", "assert", "校验-按状态", assert_data([
            {"key": "rows", "value": "min=1", "note": "聚合非空"},
            {"key": "sql", "value": st_match, "note": "各状态单数之和=DWD 总数"},
        ]), 660, 220),
        node("nd_merge", "merge", "合并（OR）", {}, 900, 130),
        node("nd_end", "end", "结束", {}, 1060, 130),
    ]
    edges = [edge("nd_start", "nd_fork"), edge("nd_fork", "nd_sql_day"),
             edge("nd_sql_day", "nd_as_day"), edge("nd_fork", "nd_sql_st"),
             edge("nd_sql_st", "nd_as_st"),
             edge("nd_as_day", "nd_merge", "success"),
             edge("nd_as_st", "nd_merge", "success"),
             edge("nd_merge", "nd_end")]
    return {"id": wf_id, "name": "i12_E2_dws_daily_agg", "version": 1, "meta": {"profile": "dag"},
            "nodes": nodes, "edges": edges}


def doc_e3(wf_id):
    raw_ddl = ("CREATE TABLE IF NOT EXISTS i12_ods_order_raw ("
               "order_no TEXT, user_id TEXT, amount TEXT, status TEXT, create_time TEXT)")
    typed_sql = ("DROP TABLE IF EXISTS dwd_order_file;"
                 "CREATE TABLE dwd_order_file AS"
                 " SELECT order_no, CAST(user_id AS UNSIGNED) AS user_id,"
                 " CAST(amount AS DECIMAL(12,2)) AS amount, status,"
                 " STR_TO_DATE(create_time, '%Y-%m-%d %H:%i:%s') AS create_time"
                 " FROM i12_ods_order_raw WHERE order_no <> ''")
    count_match = ("SELECT IF((SELECT COUNT(*) FROM dwd_order_file) = "
                   "(SELECT COUNT(*) FROM i12_ods_order_raw WHERE order_no <> ''), 1, 0)")
    return chain_doc(wf_id, "i12_E3_elt_file_raw", [
        node("nd_fsync", "file_sync", "文件原样入仓", file_sync_data(
            runtimeNode=NODE_HOST, filePath="/mnt/lei/datara/i12files/orders.csv",
            fileType="csv", delimiter=",", encoding="utf-8", headerRows=1,
            targetDs=DW_DS, targetTable={"schema": "datara_dw", "table": "i12_ods_order_raw"},
            autoCreate=True, ddl=raw_ddl, writeMode="overwrite"), 300),
        node("nd_sql", "sql", "ELT类型规整", sql_data(typed_sql, "dwd_order_file"), 520),
        node("nd_assert", "assert", "对账校验", assert_data([
            {"key": "rows", "value": "min=500,max=500", "note": "文件数据行精确值"},
            {"key": "unique", "value": "order_no", "note": "单号唯一"},
            {"key": "sql", "value": count_match, "note": "规整前后行数一致"},
        ]), 740),
    ])


def doc_e4(wf_id):
    join_sql = ("DROP TABLE IF EXISTS dwd_order_region;"
                "CREATE TABLE dwd_order_region AS"
                " SELECT o.order_no, o.user_id, r.region, o.amount, o.status"
                " FROM ods_order o LEFT JOIN ${tmp.user_region} r ON o.user_id = r.user_id")
    count_match = ("SELECT IF((SELECT COUNT(*) FROM dwd_order_region) = "
                   "(SELECT COUNT(*) FROM ods_order), 1, 0)")
    region_match = ("SELECT IF((SELECT COUNT(*) FROM dwd_order_region WHERE region IS NOT NULL) = "
                    "(SELECT COUNT(*) FROM dwd_order_region), 1, 0)")
    return chain_doc(wf_id, "i12_E4_file_join_dim", [
        node("nd_file", "file", "读取维表CSV", file22_data(
            mode="manual", path="i12_etl_user_region.csv", format="csv",
            encoding="utf-8", delimiter=",", header=True,
            register=True, tmpName="user_region", kind="table",
            targetDs=DW_DS, retention="immediate"), 300),
        node("nd_sql", "sql", "维表JOIN加工", sql_data(join_sql, "dwd_order_region"), 520),
        node("nd_assert", "assert", "对账校验", assert_data([
            {"key": "rows", "value": "min=1", "note": "加工产物非空"},
            {"key": "sql", "value": count_match, "note": "LEFT JOIN 行数=事实表"},
            {"key": "sql", "value": region_match, "note": "维表全覆盖 region 非空"},
        ]), 740),
    ])


def doc_e5(wf_id):
    l1_sql = CLEAN_SQL_TMPL.format(dwd="dwd_order_gate", src="i12_o_order_src")
    l1_match = ("SELECT IF((SELECT COUNT(*) FROM dwd_order_gate) = "
                "(SELECT COUNT(*) FROM (SELECT order_no FROM i12_o_order_src "
                "WHERE amount >= 0 AND order_no IS NOT NULL AND order_no <> '' "
                "GROUP BY order_no) s), 1, 0)")
    l2_sql = ("DROP TABLE IF EXISTS dws_gate_day;"
              "CREATE TABLE dws_gate_day AS"
              " SELECT order_date, COUNT(*) AS order_cnt, SUM(amount) AS amt_sum"
              " FROM dwd_order_gate GROUP BY order_date")
    l2_match = ("SELECT IF((SELECT COALESCE(SUM(order_cnt),0) FROM dws_gate_day) = "
                "(SELECT COUNT(*) FROM dwd_order_gate), 1, 0)")
    return chain_doc(wf_id, "i12_E5_gated_pipeline", [
        node("nd_sql1", "sql", "分层一-清洗", sql_data(l1_sql, "dwd_order_gate"), 300),
        node("nd_g1", "assert", "闸门一", assert_data([
            {"key": "rows", "value": "min=1", "note": "清洗产物非空（0 行即断流）"},
            {"key": "unique", "value": "order_no", "note": "单号唯一"},
            {"key": "sql", "value": l1_match, "note": "与源去重口径一致"},
        ]), 520),
        node("nd_sql2", "sql", "分层二-聚合", sql_data(l2_sql, "dws_gate_day"), 740),
        node("nd_g2", "assert", "闸门二", assert_data([
            {"key": "rows", "value": "min=1", "note": "聚合非空"},
            {"key": "sql", "value": l2_match, "note": "各天单数之和=DWD 总数"},
        ]), 960),
    ])


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
                {"doc": doc, "remark": "I12 ETL 类用例", "tags": TAGS})
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


def task_by_name(detail, name):
    for t in detail.get("taskInstances") or []:
        if t.get("name") == name:
            return t
    return None


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
def run_e1():
    prep_e1()
    wf_id, code = ensure_wf("i12_E1_ods_to_dwd_clean")
    save_doc(wf_id, doc_e1(wf_id))
    detail = run_and_poll(wf_id, code, "e1")
    ok = detail["state"] == "success"
    expect = int(scalar(DW_C, "SELECT COUNT(*) FROM (SELECT order_no FROM datara_dw.ods_order "
                              "WHERE amount >= 0 AND order_no IS NOT NULL AND order_no <> '' "
                              "GROUP BY order_no) s") or 0)
    actual = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_clean") or 0)
    dup = int(scalar(DW_C, "SELECT COUNT(*) FROM (SELECT order_no FROM datara_dw.dwd_order_clean "
                           "GROUP BY order_no HAVING COUNT(*) > 1) t") or 0)
    neg = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_clean WHERE amount < 0") or 0)
    asserts_ok = all(t["state"] == "success" for t in tasks_of(detail, "assert"))
    sql_tasks = tasks_of(detail, "sql")
    ok &= check("e1", "rows_match", actual == expect and expect > 0, "%d vs %d" % (actual, expect))
    ok &= check("e1", "unique_order_no", dup == 0, dup)
    ok &= check("e1", "no_negative_amount", neg == 0, neg)
    ok &= check("e1", "assert_success", asserts_ok, asserts_ok)
    if sql_tasks:
        tail_log(sql_tasks[0], "e1")
    return ok


def run_e2():
    prep_e2()
    wf_id, code = ensure_wf("i12_E2_dws_daily_agg")
    save_doc(wf_id, doc_e2(wf_id))
    detail = run_and_poll(wf_id, code, "e2")
    ok = detail["state"] == "success"
    dwd = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_clean") or 0)
    day_sum = int(scalar(DW_C, "SELECT COALESCE(SUM(order_cnt),0) FROM datara_dw.dws_order_stat_day") or 0)
    st_sum = int(scalar(DW_C, "SELECT COALESCE(SUM(order_cnt),0) FROM datara_dw.dws_order_stat_status") or 0)
    asserts_ok = all(t["state"] == "success" for t in tasks_of(detail, "assert"))
    sqls = {t["name"]: t for t in tasks_of(detail, "sql")}
    ok &= check("e2", "day_sum_match", day_sum == dwd, "%d vs %d" % (day_sum, dwd))
    ok &= check("e2", "status_sum_match", st_sum == dwd, "%d vs %d" % (st_sum, dwd))
    ok &= check("e2", "assert_success", asserts_ok, asserts_ok)
    ok &= check("e2", "both_branches_ran", len(sqls) == 2, sorted(sqls))
    for task in sqls.values():
        tail_log(task, "e2")
    return ok


def run_e3():
    prep_e3()
    wf_id, code = ensure_wf("i12_E3_elt_file_raw")
    save_doc(wf_id, doc_e3(wf_id))
    detail = run_and_poll(wf_id, code, "e3")
    ok = detail["state"] == "success"
    raw = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.i12_ods_order_raw") or 0)
    typed = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_file") or 0)
    uniq = int(scalar(DW_C, "SELECT COUNT(DISTINCT order_no) FROM datara_dw.dwd_order_file") or 0)
    bad_time = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_file "
                                "WHERE create_time IS NULL OR amount IS NULL") or 0)
    fs = tasks_of(detail, "file_sync")
    outs = outputs_of(fs[0]) if fs else {}
    asserts_ok = all(t["state"] == "success" for t in tasks_of(detail, "assert"))
    ok &= check("e3", "raw_rows", raw == 500, raw)
    ok &= check("e3", "typed_rows", typed == 500 and uniq == 500, "%d/%d" % (typed, uniq))
    ok &= check("e3", "typed_parse_ok", bad_time == 0, bad_time)
    ok &= check("e3", "fs_rows_written", int(outs.get("rows_written", -1)) == 500, outs.get("rows_written"))
    ok &= check("e3", "assert_success", asserts_ok, asserts_ok)
    if fs:
        tail_log(fs[0], "e3")
    sqls = tasks_of(detail, "sql")
    if sqls:
        tail_log(sqls[0], "e3")
    return ok


def run_e4():
    prep_e4()
    wf_id, code = ensure_wf("i12_E4_file_join_dim")
    save_doc(wf_id, doc_e4(wf_id))
    detail = run_and_poll(wf_id, code, "e4")
    ok = detail["state"] == "success"
    ods = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.ods_order") or 0)
    joined = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_region") or 0)
    no_region = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_region "
                                 "WHERE region IS NULL OR region = ''") or 0)
    fnodes = tasks_of(detail, "file")
    fouts = outputs_of(fnodes[0]) if fnodes else {}
    asserts_ok = all(t["state"] == "success" for t in tasks_of(detail, "assert"))
    ok &= check("e4", "file_rows_count", int(fouts.get("rows_count", -1)) > 0, fouts.get("rows_count"))
    ok &= check("e4", "file_tmp_name", fouts.get("tmp_name") == "user_region", fouts.get("tmp_name"))
    ok &= check("e4", "join_rows_match", joined == ods and ods > 0, "%d vs %d" % (joined, ods))
    ok &= check("e4", "region_full_cover", no_region == 0, no_region)
    ok &= check("e4", "assert_success", asserts_ok, asserts_ok)
    if fnodes:
        tail_log(fnodes[0], "e4")
    sqls = tasks_of(detail, "sql")
    if sqls:
        tail_log(sqls[0], "e4")
    return ok


def run_e5():
    prep_e5()
    wf_id, code = ensure_wf("i12_E5_gated_pipeline")
    save_doc(wf_id, doc_e5(wf_id))

    # run1：正常通过
    detail1 = run_and_poll(wf_id, code, "e5")
    ok = detail1["state"] == "success"
    dwd1 = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_gate") or 0)
    dws1 = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dws_gate_day") or 0)
    asserts1 = all(t["state"] == "success" for t in tasks_of(detail1, "assert"))
    ok &= check("e5", "run1_dwd_rows", dwd1 > 0, dwd1)
    ok &= check("e5", "run1_dws_rows", dws1 > 0, dws1)
    ok &= check("e5", "run1_asserts", asserts1, asserts1)

    # run2：篡改源（清空）→ 闸门一 0 行断流，下游分层二不得执行
    mysql_exec(DW_C, "TRUNCATE TABLE datara_dw.i12_o_order_src")
    print("EVIDENCE|e5|tamper|i12_o_order_src 清空")
    detail2 = run_and_poll(wf_id, code, "e5")
    ok &= check("e5", "run2_failure", detail2["state"] == "failure", detail2["state"])
    l2 = task_by_name(detail2, "分层二-聚合")
    l2_state = (l2 or {}).get("state") or "absent"
    ok &= check("e5", "run2_downstream_not_run", l2_state != "success", l2_state)
    dws2 = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dws_gate_day") or 0)
    ok &= check("e5", "run2_dws_untouched", dws2 == dws1, "%d vs run1 %d" % (dws2, dws1))
    g1 = task_by_name(detail2, "闸门一")
    g1_outs = outputs_of(g1) if g1 else {}
    # onFail=fail（默认）时闸门节点 FAILURE，outputs={"error":"assert_failed","failed":[...]}（engine.py L790），无 assert_ok 键
    ok &= check("e5", "run2_g1_assert_failed",
                bool(g1) and g1.get("state") == "failure"
                and g1_outs.get("error") == "assert_failed"
                and bool(g1_outs.get("failed")),
                {"state": (g1 or {}).get("state"), "error": g1_outs.get("error"),
                 "failed": g1_outs.get("failed")})
    if g1:
        tail_log(g1, "e5")

    # run3：恢复源 → 全链恢复通过
    restore_e5()
    detail3 = run_and_poll(wf_id, code, "e5")
    ok &= detail3["state"] == "success"
    dwd3 = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dwd_order_gate") or 0)
    dws3 = int(scalar(DW_C, "SELECT COUNT(*) FROM datara_dw.dws_gate_day") or 0)
    asserts3 = all(t["state"] == "success" for t in tasks_of(detail3, "assert"))
    ok &= check("e5", "run3_recovered", dwd3 == dwd1 and dws3 == dws1,
                "dwd %d vs %d, dws %d vs %d" % (dwd3, dwd1, dws3, dws1))
    ok &= check("e5", "run3_asserts", asserts3, asserts3)
    sqls = tasks_of(detail3, "sql")
    for task in sqls:
        tail_log(task, "e5")
    return ok


CASES = {"e1": run_e1, "e2": run_e2, "e3": run_e3, "e4": run_e4, "e5": run_e5}
PREPS = {"e1": prep_e1, "e2": prep_e2, "e3": prep_e3, "e4": prep_e4, "e5": prep_e5}


def main():
    global BASE
    parser = argparse.ArgumentParser(description="I12 ETL 类 E1~E5 批量编排")
    parser.add_argument("--cases", default="e1,e2,e3,e4,e5")
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
