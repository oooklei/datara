"""I5 实测门 #2/#3/#4 解析器探针（1.9 worker/api 容器内直连运行）。

用法：docker exec datara-worker python tools/parse_probe.py
十形态断言（与 I5-设计文档 §8/§9 对齐），全部通过打印 PROBE_OK。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from common.sqlparser import parse_sql_lineage

FAILS = []


def check(name, cond, detail=""):
    if cond:
        print("  ok  %s" % name)
    else:
        FAILS.append(name)
        print("  FAIL %s %s" % (name, detail))


# ---- 门#2/#4 基准：INSERT..SELECT JOIN（实测基准语句，default_db=ec_retail） ----
base_sql = (
    "INSERT INTO dwd_i5_order_wide\n"
    "SELECT o.id, o.order_no, u.username, o.amount * 0.9 AS net_amount, o.create_time\n"
    "FROM ods_order o JOIN dim_user u ON u.id = o.user_id\n"
    "WHERE o.status = 'DONE'"
)
rs = parse_sql_lineage(base_sql, "ec_retail")
check("基准单边", len(rs) == 1, str(len(rs)))
s = rs[0]
check("基准 froms", s.from_tables == ["ec_retail.ods_order", "ec_retail.dim_user"], str(s.from_tables))
check("基准 tos", s.to_tables == ["ec_retail.dwd_i5_order_wide"], str(s.to_tables))
fm = {(f.to_field, f.from_table, f.from_field): f for f in s.fields}
check("net_amount 映射", ("net_amount", "ec_retail.ods_order", "amount") in fm, str(list(fm)))
check("net_amount transform", fm.get(("net_amount", "ec_retail.ods_order", "amount")) is not None
      and "o.amount * 0.9" in fm[("net_amount", "ec_retail.ods_order", "amount")].transform)
check("username 来源 dim_user", ("username", "ec_retail.dim_user", "username") in fm, str(list(fm)))
check("id 映射 ods_order", ("id", "ec_retail.ods_order", "id") in fm, str(list(fm)))
check("create_time 映射", ("create_time", "ec_retail.ods_order", "create_time") in fm, str(list(fm)))

# ---- 门#3 多形态 ----
# CTE（挂 Insert 层；已限定 db 前缀的表不补 default_db）
rs = parse_sql_lineage(
    "INSERT INTO t_agg WITH x AS (SELECT uid, SUM(amt) s FROM o.pay GROUP BY uid) "
    "SELECT uid, s FROM x", "ec_retail")
check("CTE froms", len(rs) == 1 and rs[0].from_tables == ["o.pay"], str(rs and rs[0].from_tables))
check("CTE tos", rs and rs[0].to_tables == ["ec_retail.t_agg"])

# 子查询
rs = parse_sql_lineage(
    "INSERT INTO t_sub SELECT a.uid FROM (SELECT uid FROM o.orders) a", "ec_retail")
check("子查询 froms", len(rs) == 1 and rs[0].from_tables == ["o.orders"], str(rs and rs[0].from_tables))

# UNION
rs = parse_sql_lineage(
    "INSERT INTO t_un SELECT id FROM o.a UNION SELECT id FROM o.b", "ec_retail")
check("UNION froms", len(rs) == 1 and rs[0].from_tables == ["o.a", "o.b"],
      str(rs and rs[0].from_tables))

# UPDATE（MySQL 多表语法）
rs = parse_sql_lineage(
    "UPDATE d.t1 JOIN d.b ON b.id = t1.bid SET t1.amt = b.amt * 1.1, t1.flag = 'Y'")
check("UPDATE tos", len(rs) == 1 and rs[0].to_tables == ["d.t1"], str(rs and rs[0].to_tables))
check("UPDATE froms", rs and rs[0].from_tables == ["d.b"], str(rs and rs[0].from_tables))
ufm = {(f.to_field, f.from_table, f.from_field) for f in rs[0].fields} if rs else set()
check("UPDATE 字段", ("amt", "d.b", "amt") in ufm, str(ufm))

# INSERT..VALUES（常量来源 → from='' 单边；无 SELECT 主体 → 字段级为空，worker 侧落 from='' 表级边）
rs = parse_sql_lineage("INSERT INTO d.t2 (a, b) VALUES (1, 'x')")
check("VALUES 单边", len(rs) == 1 and rs[0].to_tables == ["d.t2"] and rs[0].from_tables == [],
      str(rs and (rs[0].to_tables, rs[0].from_tables)))
check("VALUES 无字段级", rs and rs[0].fields == [], str(rs and rs[0].fields))

# CTAS
rs = parse_sql_lineage("CREATE TABLE d.t3 AS SELECT id, nm FROM d.src")
check("CTAS", len(rs) == 1 and rs[0].to_tables == ["d.t3"]
      and rs[0].from_tables == ["d.src"], str(rs and (rs[0].to_tables, rs[0].from_tables)))

# 显式列清单（Identifier 形态）
rs = parse_sql_lineage(
    "INSERT INTO d.t4 (uid, uname) SELECT u.id, u.name FROM d.users u")
check("显式列清单", rs and {(f.to_field) for f in rs[0].fields} == {"uid", "uname"},
      str(rs and [f.to_field for f in rs[0].fields]))

# 纯 SELECT（无目标 → 空）
check("纯 SELECT 不产血缘", parse_sql_lineage("SELECT COUNT(*) FROM d.t1") == [])

# 语法错误（整段容错 → 空）
check("语法错误容错", parse_sql_lineage("INSERT INT0 bad sql ###") == [])
check("空语句容错", parse_sql_lineage("   ") == [])

print()
if FAILS:
    print("PROBE_FAILED: %d 项未过 -> %s" % (len(FAILS), FAILS))
    raise SystemExit(1)
print("PROBE_OK")
