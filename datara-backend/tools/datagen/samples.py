"""I2 测试数据基座 · 文件源样例产出（I2 设计文档 §9，I4 文件源 / C22 实证位）。

三格式（同 seed 派生，与 ec_retail.ods_order 同构，缺省 5000 行）：
  orders_part.csv   UTF-8 逗号分隔（csv 模块标准转义，含引号/脏样本行）
  orders_part.txt   自定义分隔符 |.（用户"双杠加点"口径样例）
  orders_part.xlsx  openpyxl 双 sheet（数据 + 说明页）

无 DB 依赖（纯文件产出），本机与容器均可执行：
  python -m tools.datagen.run samples [--out DIR] [--rows N]
  行数下限 5000：各规则期望 ≥ 锚定量（r_order_status_enum 0.002×N ≥ 10）
"""

import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from tools.datagen.config import ConfigError, DatagenConfig, run_today
from tools.datagen.gen import GenCtx, iter_rows, plan_table_copy

REPO = Path(__file__).resolve().parents[3]
DEFAULT_OUT = REPO / "infra" / "files" / "samples"
MIN_ROWS = 5000


def _cell(v):
    """openpyxl 不收 Decimal → float；其余原样（datetime/date/None 原生支持）。"""
    return float(v) if isinstance(v, Decimal) else v


def run_samples(cfg: DatagenConfig, out: Path = None, rows: int = 5000, log=print) -> list:
    if rows < MIN_ROWS:
        raise ConfigError(f"样例行数须 ≥ {MIN_ROWS}（r_order_status_enum 0.002×N ≥ 锚定 10）")
    out = Path(out) if out else DEFAULT_OUT
    out.mkdir(parents=True, exist_ok=True)
    t = plan_table_copy(cfg.table("ods_order"), rows)
    ctx = GenCtx(cfg, run_today())
    data = [[_cell(row[c.name]) for c in t.columns]
            for row, _content in iter_rows(t, cfg.rules_of("ods_order"), ctx)]
    header = t.col_names

    csv_path = out / "orders_part.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(data)

    txt_path = out / "orders_part.txt"
    sep = "|."
    with open(txt_path, "w", encoding="utf-8", newline="") as f:
        f.write(sep.join(header) + "\n")
        for r in data:
            f.write(sep.join("" if v is None else str(v) for v in r) + "\n")

    xlsx_path = out / "orders_part.xlsx"
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "数据"
    ws.append(header)
    for r in data:
        ws.append(r)
    info = wb.create_sheet("说明")
    info.append(["Datara I2 文件源样例"])
    info.append(["生成时间", datetime.now().strftime("%Y-%m-%d %H:%M")])
    info.append(["seed", cfg.seed])
    info.append(["行数", len(data)])
    info.append(["同构表", "ec_retail.ods_order（含脏样本：空值/越界/枚举外/孤儿/格式错）"])
    info.append(["CSV", "UTF-8 逗号分隔，首行列名"])
    info.append(["TXT", "自定义分隔符 |.（竖线+点）"])
    info.append(["列说明", "；".join(f"{c.name}({c.ctype})" for c in t.columns)])
    wb.save(xlsx_path)

    log(f"[samples] 产出 {len(data):,} 行 × 3 格式 → {out}")
    for p in (csv_path, txt_path, xlsx_path):
        log(f"  - {p.name} ({p.stat().st_size:,} B)")
    return [csv_path, txt_path, xlsx_path]
