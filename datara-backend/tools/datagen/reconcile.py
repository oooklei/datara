"""I2 测试数据基座 · reconcile 对账（I2 设计文档 §7）。

产出（落 LOG_DIR/datagen/，时间戳报告保留最近 3 份）：
  - reconcile.json        最新报告（gen 末步自动产出 / verify 独立重跑 / import 后更新）
  - reconcile_{ts}.json   历史快照
  - verify_queries.sql    核对 SQL 清单（1.9 实测门 #4/#5/#7 直接执行比对；
                          含锚定段断言与三规则实证位格式率）

对账口径（计数驱动 → expected/actual 严格相等，无容差）：
  - 行数总账：src 17 表 + dw 派生表；业务行数合计 = target_rows_total
  - 分区数：3 张分区表各 91（90 日 + pmax）
  - 脏规则：每条规则按 kind 生成 actual 计数 SQL；锚定段另行断言（PK 区间 + 谓词）
  - 时间类规则不使用 NOW() 判定：order_ctime 当日行的时间可晚于运行时刻
    （上午灌数时当日订单约半数 create_time > NOW()），NOW() 口径会把自然行
    误计为"未来时间"，对账随运行时刻漂移 → time_future/time_invalid 按注入值精确命中
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from tools.datagen.config import DatagenConfig, RuleSpec, TableSpec, anchor_blocks, run_today
from tools.datagen.gen import connect

REPORT_DIR = Path(os.environ.get("LOG_DIR", "/datara/logs")) / "datagen"
_KEEP = 3


def _lit(v) -> str:
    """SQL 字面量（配置来源可信，仅做引号转义）。"""
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(v)
    return "'" + str(v).replace("\\", "\\\\").replace("'", "''") + "'"


def _like(s: str) -> str:
    """LIKE 模式转义（MySQL 默认转义符为反斜杠）。"""
    return (s.replace("\\", "\\\\").replace("%", "\\%")
             .replace("_", "\\_").replace("'", "''"))


def _fk_col(cfg: DatagenConfig, table_name: str, parent: str) -> str:
    """从 tables.yaml relations 找 table_name 指向 parent 的外键列。"""
    for rel in cfg.relations:
        if rel.get("from", "").split(".")[0] == parent and rel.get("to", "").startswith(table_name + "."):
            return rel["to"].split(".")[1]
    raise RuntimeError(f"tables.yaml relations 缺少 {parent} → {table_name} 外键声明")


def rule_sql(cfg: DatagenConfig, t: TableSpec, r: RuleSpec, blocks: dict) -> dict:
    """kind → actual 计数 SQL（+ 锚定段断言 SQL）。返回 {actual, anchor, note}。"""
    col, p, pk = r.column, r.params, t.pk
    note = ""
    if r.kind == "duplicate_row":
        eq = " AND ".join(f"a.{c} <=> b.{c}" for c in t.col_names if c != pk)
        sql = f"SELECT COUNT(*) FROM {t.name} a JOIN {t.name} b ON b.{pk} = a.{pk} + 1 WHERE {eq}"
        anchor_sql = None
        if r.anchor:  # 锚定重复对 = (PK2, PK3)，恰 1 对
            anchor_sql = (f"SELECT COUNT(*) FROM {t.name} a JOIN {t.name} b ON b.{pk} = a.{pk} + 1 "
                          f"WHERE a.{pk} = 2 AND {eq}")
    elif r.kind == "phone_pair":
        sql = (f"SELECT COUNT(*) FROM (SELECT {col} FROM {t.name} "
               f"GROUP BY {col} HAVING COUNT(*) > 1) g")
        anchor_sql = None  # 结构型规则不占锚定块
    else:
        join, where = "", ""
        if r.kind == "null_value":
            where = f"x.{col} IS NULL"
        elif r.kind == "format_phone":
            where = f"x.{col} REGEXP '[^0-9]' OR CHAR_LENGTH(x.{col}) <> 11"
        elif r.kind == "format_idcard":
            where = f"x.{col} NOT REGEXP '^[0-9]{{17}}[0-9X]$'"
        elif r.kind == "format_credit":
            where = f"x.{col} NOT REGEXP '^91[0-9]{{16}}$'"
            note = "三规则实证位：企业信用代码"
        elif r.kind == "out_of_range":
            lo, hi = p["bounds"]
            where = f"x.{col} NOT BETWEEN {_lit(lo)} AND {_lit(hi)}"
        elif r.kind == "enum_out":
            where = f"x.{col} NOT IN ({','.join(_lit(a) for a in p['allowed'])})"
        elif r.kind == "orphan":
            parent_rows = cfg.table(str(p["parent"]).split(".")[0]).rows
            where = f"x.{col} < 1 OR x.{col} > {parent_rows}"
        elif r.kind == "time_future":
            where = f"x.{col} = {_lit(p['value'])}"
            note = "按注入值精确命中（NOW() 判定受运行时刻影响，当日未来自然行会误计）"
        elif r.kind == "time_invalid":
            where = f"x.{col} IN ({','.join(_lit(v) for v in p['values'])})"
            note = "按注入值精确命中（同 time_future）"
        elif r.kind == "time_before_order":
            fk = _fk_col(cfg, t.name, "ods_order")
            join = f" JOIN ods_order o ON x.{fk} = o.id"
            where = f"x.{col} < o.create_time"
        elif r.kind == "time_before_coupon":
            fk = _fk_col(cfg, t.name, "ods_coupon")
            join = f" JOIN ods_coupon o ON x.{fk} = o.id"
            where = f"x.{col} < o.valid_from"
        elif r.kind == "dirty_chars":
            where = f"x.{col} LIKE '%{_like(p['marker'])}%'"
        else:
            raise RuntimeError(f"规则 {r.id} 未知 kind：{r.kind}")
        sql = f"SELECT COUNT(*) FROM {t.name} x{join} WHERE {where}"
        anchor_sql = None
        if r.anchor:
            s, e = blocks[r.id]
            rng = f"x.{pk} BETWEEN {s + 1} AND {e + 1}"
            if r.kind == "orphan":  # 锚定段断言用 anchor_from 精确 ID 段（设计文档 §5.2）
                afrom = int(p["anchor_from"])
                pred = f"x.{col} >= {afrom} AND x.{col} < {afrom + r.anchor}"
            else:
                pred = where
            anchor_sql = f"SELECT COUNT(*) FROM {t.name} x{join} WHERE {rng} AND ({pred})"
    return {"actual": sql, "anchor": anchor_sql, "note": note}


def _check(cur, sql: str) -> int:
    cur.execute(sql)
    return cur.fetchone()[0]


def run_verify(cfg: DatagenConfig, log=print) -> dict:
    """对账主流程：行数总账 + 分区数 + 逐规则 expected/actual + 锚定段。"""
    today = run_today()
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "gen", "seed": cfg.seed, "run_date": today.isoformat(),
        "window": {"from": (today - timedelta(days=cfg.window_days - 1)).isoformat(),
                   "to": today.isoformat()},
        "databases": {},
    }
    conns = {"src": connect(cfg.dsn("src")), "dw": connect(cfg.dsn("dw"))}
    mismatch = []
    try:
        for db_key in ("src", "dw"):
            cur = conns[db_key].cursor()
            db_name = cfg.dsn(db_key)["db"]
            for schema_name in sorted({t.schema_name for t in cfg.tables if t.db == db_key}):
                tables_of = [t for t in cfg.tables if t.schema_name == schema_name]
                entry = {"dsn": {"host": cfg.dsn(db_key)["host"], "db": db_name},
                         "tables": [], "partitions": [], "rules": []}
                for t in tables_of:
                    actual = _check(cur, f"SELECT COUNT(*) FROM {t.name}")
                    entry["tables"].append({"table": t.name, "expected": t.rows,
                                            "actual": actual, "pass": actual == t.rows})
                    if actual != t.rows:
                        mismatch.append(f"{schema_name}.{t.name} 行数 {actual} != {t.rows}")
                    if t.is_partitioned:
                        cur.execute(
                            "SELECT COUNT(*) FROM information_schema.PARTITIONS "
                            "WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s AND PARTITION_NAME IS NOT NULL",
                            (db_name, t.name))
                        pactual = cur.fetchone()[0]
                        entry["partitions"].append({"table": t.name, "expected": t.partition_count,
                                                    "actual": pactual, "pass": pactual == t.partition_count})
                        if pactual != t.partition_count:
                            mismatch.append(f"{schema_name}.{t.name} 分区数 {pactual} != {t.partition_count}")
                for t in tables_of:
                    rules = cfg.rules_of(t.name)
                    blocks = anchor_blocks(t, rules)
                    for r in rules:
                        sqls = rule_sql(cfg, t, r, blocks)
                        expected = r.expected_total(t)
                        actual = _check(cur, sqls["actual"])
                        item = {"rule": r.id, "kind": r.kind, "table": t.name, "column": r.column,
                                "expected": expected, "actual": actual, "pass": actual == expected}
                        if sqls["note"]:
                            item["note"] = sqls["note"]
                        if actual != expected:
                            mismatch.append(f"{r.id} actual {actual} != expected {expected}")
                        if sqls["anchor"]:
                            a = _check(cur, sqls["anchor"])
                            item["anchor_expected"], item["anchor_actual"] = r.anchor, a
                            item["pass"] = item["pass"] and a == r.anchor
                            if a != r.anchor:
                                mismatch.append(f"{r.id} 锚定段 {a} != {r.anchor}")
                        entry["rules"].append(item)
                entry["summary"] = {
                    "tables": len(tables_of),
                    "rows": sum(x["actual"] for x in entry["tables"]),
                    "partitions": len(entry["partitions"]),
                    "rules": len(entry["rules"]),
                    "mismatch": sum(1 for x in entry["tables"] + entry["partitions"] + entry["rules"]
                                    if not x["pass"]),
                }
                if db_key == "src":
                    biz = sum(x["actual"] for x, t in zip(entry["tables"], tables_of) if t.is_business)
                    entry["summary"]["business_rows"] = biz
                    entry["summary"]["business_expected"] = cfg.target_rows_total
                    if biz != cfg.target_rows_total:
                        mismatch.append(f"业务行数合计 {biz} != {cfg.target_rows_total}")
                report["databases"][schema_name] = entry
    finally:
        for c in conns.values():
            c.close()

    report["summary"] = {"mismatch": len(mismatch), "mismatch_detail": mismatch[:20],
                         "status": "PASS" if not mismatch else "FAIL"}
    write_report(report, log)
    _write_verify_sql(cfg)
    for schema_name, entry in report["databases"].items():
        s = entry["summary"]
        log(f"[verify] {schema_name}: 表 {s['tables']} 行 {s['rows']:,} "
            f"分区 {s['partitions']} 规则 {s['rules']} 失配 {s['mismatch']}")
    log(f"[verify] 对账结论：{report['summary']['status']}"
        + (f"（{len(mismatch)} 项失配）" if mismatch else "（expected = actual 全部严格相等）"))
    log(f"[verify] 报告：{REPORT_DIR / 'reconcile.json'}")
    return report


def write_report(report: dict, log=print) -> Path:
    """写最新报告 + 时间戳快照（保留最近 3 份）。"""
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    text = json.dumps(report, ensure_ascii=False, indent=2)
    (REPORT_DIR / f"reconcile_{ts}.json").write_text(text, encoding="utf-8")
    (REPORT_DIR / "reconcile.json").write_text(text, encoding="utf-8")
    for old in sorted(REPORT_DIR.glob("reconcile_*.json"))[:-_KEEP]:
        old.unlink(missing_ok=True)
    return REPORT_DIR / "reconcile.json"


def _write_verify_sql(cfg: DatagenConfig) -> None:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "verify_queries.sql").write_text(build_verify_sql(cfg), encoding="utf-8")


def build_verify_sql(cfg: DatagenConfig) -> str:
    """核对 SQL 清单（分 SRC/DW 段，expect 注释即对账期望）。"""
    today = run_today()
    L = [
        "-- ============================================================",
        "-- I2 reconcile 核对 SQL 清单（1.9 实测门 #4/#5/#7 比对依据）",
        f"-- 生成时间 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  seed={cfg.seed}",
        f"-- 窗口 T-89~T = {(today - timedelta(days=cfg.window_days - 1)).isoformat()}"
        f" ~ {today.isoformat()}",
        "-- 用法：SRC 段在容器 datara-mysql-src 执行；DW 段在容器 datara-mysql-dw 执行",
        "-- ============================================================",
        "",
        "-- ############ SRC（容器 datara-mysql-src / 库 ec_retail） ############",
        "USE ec_retail;",
        "",
        "-- A. 行数总账",
    ]
    src_tables = [t for t in cfg.tables if t.db == "src"]
    for t in src_tables:
        L.append(f"SELECT '{t.name}' AS tbl, COUNT(*) AS rows_cnt FROM {t.name};"
                 f"  -- expect {t.rows:,}")
    L += ["", "-- B. 分区数（90 日 + pmax = 91）"]
    for t in src_tables:
        if t.is_partitioned:
            L.append("SELECT COUNT(*) AS part_cnt FROM information_schema.PARTITIONS "
                     f"WHERE TABLE_SCHEMA = '{t.schema_name}' AND TABLE_NAME = '{t.name}' "
                     "AND PARTITION_NAME IS NOT NULL;  -- expect 91")
    L += ["", "-- C. 锚定段断言（PK 区间 + 谓词，不受 seed 漂移影响）"]
    for t in src_tables:
        rules = cfg.rules_of(t.name)
        blocks = anchor_blocks(t, rules)
        for r in rules:
            sqls = rule_sql(cfg, t, r, blocks)
            if sqls["anchor"]:
                L.append(f"{sqls['anchor']};  -- {r.id} expect {r.anchor}")
    L += ["", "-- D. 脏规则计数核对（与 dirty_rules.yaml 一一对应）"]
    for t in src_tables:
        rules = cfg.rules_of(t.name)
        blocks = anchor_blocks(t, rules)
        for r in rules:
            sqls = rule_sql(cfg, t, r, blocks)
            exp = r.expected_total(t)
            note = f"（{sqls['note']}）" if sqls["note"] else ""
            L.append(f"{sqls['actual']};  -- {r.id} expect {exp:,}{note}")
    L += ["", "-- E. 三规则实证位（身份证 / 手机号 / 企业信用代码）"]
    sui = cfg.table("sec_user_identity")
    fmt_id = next(r for r in cfg.rules_of("sec_user_identity") if r.kind == "format_idcard")
    fmt_ph = next(r for r in cfg.rules_of("dim_user") if r.kind == "format_phone")
    L += [
        f"SELECT COUNT(*) AS total, SUM(id_card REGEXP '^[0-9]{{17}}[0-9X]$') AS ok "
        f"FROM {sui.name};  -- expect total={sui.rows:,} ok={sui.rows - fmt_id.expected_total(sui):,}"
        f"（2% 校验位错）",
        f"SELECT COUNT(*) AS total, SUM(phone REGEXP '^1[0-9]{{10}}$') AS ok FROM dim_user;"
        f"  -- expect total=60000 ok={60000 - fmt_ph.expected_total(cfg.table('dim_user')):,}"
        f"（2% 格式错；同号对为合法格式不扣减）",
        "SELECT COUNT(*) AS total, SUM(credit_code REGEXP '^91[0-9]{16}$') AS ok FROM dim_supplier;"
        "  -- expect total=1,500 ok=1,500（100% 合规）",
        "SELECT COUNT(*) AS total, SUM(credit_code REGEXP '^91[0-9]{16}$') AS ok "
        "FROM sec_supplier_contract;  -- expect total=3,000 ok=3,000（100% 合规）",
        "SELECT COUNT(*) AS dw_base FROM ods_order_item;"
        "  -- F 基准：dw 明细宽表行数应等于此值（400,000）",
        "",
        "-- ############ DW（容器 datara-mysql-dw / 库 datara_dw） ############",
        "USE datara_dw;",
        "",
        "-- F. dw 对账：dwd_order_detail 行数 = src.ods_order_item 行数",
        "SELECT COUNT(*) AS dw_rows FROM dwd_order_detail;  -- expect = SRC 段 dw_base（400,000）",
        "",
    ]
    return "\n".join(L)
