"""I2 测试数据基座 · CSV 目录导入（import.sh csv-dir 通道的容器内执行体，设计文档 §8.3）。

用法（docker compose exec datara-api）：
  python -m tools.datagen.import_csv --dir /tmp/import --schema ec_retail [--truncate]

规则：
  - 目录内文件名 = 表名（<table>.csv），首行 = 列名；列集合必须与 tables.yaml
    该表列定义一致（失配列出差异并退出码 1，任何表都不落库）
  - 列序无关（按列名映射）；空字段 → NULL；流式分批写入（内存约束）
  - 仅允许 tables.yaml 声明的 src/dw 业务 schema（meta 库不在其列，天然拒绝）
  - 导入后按表核对 CSV 行数 vs 落库行数，写 reconcile.json（mode=import）
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

from tools.datagen.config import ConfigError, DatagenConfig, load_config
from tools.datagen.gen import connect
from tools.datagen.reconcile import REPORT_DIR, write_report


def import_dir(cfg: DatagenConfig, csv_dir: Path, schema_name: str,
               truncate: bool, log=print) -> dict:
    tables = {t.name: t for t in cfg.tables if t.schema_name == schema_name}
    if not tables:
        raise ConfigError(f"tables.yaml 无 schema：{schema_name}")
    csv_dir = Path(csv_dir)
    files = sorted(csv_dir.glob("*.csv"))
    if not files:
        raise ConfigError(f"{csv_dir} 下无 *.csv 文件")
    unknown = [f.stem for f in files if f.stem not in tables]
    if unknown:
        raise ConfigError(f"未知目标表：{unknown}（schema {schema_name} 可用表：{sorted(tables)}）")

    # 第一遍：全量列校验（fail-fast，任何失配都不落库）
    plans = []
    for f in files:
        t = tables[f.stem]
        with open(f, encoding="utf-8-sig", newline="") as fh:
            reader = csv.reader(fh)
            header = next(reader, None)
            if not header:
                raise ConfigError(f"{f.name} 无表头")
            expect, got = set(t.col_names), set(header)
            if got != expect:
                raise ConfigError(f"{f.name} 列失配：缺失 {sorted(expect - got)}，多余 {sorted(got - expect)}")
            dup_cols = {c for c in header if header.count(c) > 1}
            if dup_cols:
                raise ConfigError(f"{f.name} 表头重复列：{sorted(dup_cols)}")
            idx = [header.index(c) for c in t.col_names]
        plans.append((f, t, idx))

    db = next(iter(tables.values())).db
    conn = connect(cfg.dsn(db))
    results = []
    try:
        cur = conn.cursor()
        for f, t, idx in plans:
            sql = (f"INSERT INTO {t.name} ({','.join(t.col_names)}) "
                   f"VALUES ({','.join(['%s'] * len(t.col_names))})")
            if truncate:
                cur.execute(f"TRUNCATE TABLE {t.name}")
            n, buf = 0, []
            with open(f, encoding="utf-8-sig", newline="") as fh:
                reader = csv.reader(fh)
                next(reader)  # 表头
                for row in reader:
                    buf.append([None if row[i] == "" else row[i] for i in idx])
                    if len(buf) >= cfg.batch_size:
                        cur.executemany(sql, buf)
                        n += len(buf)
                        buf = []
            if buf:
                cur.executemany(sql, buf)
                n += len(buf)
            cur.execute(f"SELECT COUNT(*) FROM {t.name}")
            db_rows = cur.fetchone()[0]
            conn.commit()
            ok = db_rows == n if truncate else db_rows >= n
            results.append({"table": t.name, "file": f.name, "csv_rows": n,
                            "db_rows": db_rows, "pass": ok})
            log(f"[import] {t.name}: CSV {n:,} 行 → 库 {db_rows:,} 行 {'✓' if ok else '✗'}")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    mismatch = [r for r in results if not r["pass"]]
    report = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": "import", "schema": schema_name, "db": db,
        "source_dir": str(csv_dir), "truncate": truncate,
        "tables": results,
        "summary": {"tables": len(results), "mismatch": len(mismatch)},
        "status": "PASS" if not mismatch else "FAIL",
    }
    write_report(report, log)
    log(f"[import] 对账报告已更新：{REPORT_DIR / 'reconcile.json'}（mode=import）")
    return report


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.datagen.import_csv")
    ap.add_argument("--dir", required=True, help="CSV 目录（<table>.csv，首行列名）")
    ap.add_argument("--schema", default="ec_retail", help="目标 schema（tables.yaml 声明）")
    ap.add_argument("--truncate", action="store_true", help="导入前清空目标表")
    args = ap.parse_args()
    cfg = load_config(Path(__file__).resolve().parent)
    try:
        report = import_dir(cfg, Path(args.dir), args.schema, args.truncate)
    except ConfigError as e:
        print(f"[import] 拒绝导入：{e}", file=sys.stderr)
        return 1
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
