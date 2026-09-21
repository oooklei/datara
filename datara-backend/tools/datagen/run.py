"""I2 测试数据基座 · 生成器 CLI（I2 设计文档 §6.2 四模式）。

  python -m tools.datagen.run plan      # dry-run：只算计划不连库（本机验证门 #3）
  python -m tools.datagen.run gen       # 灌 src 17 表 → dw 种子 → 自动对账
  python -m tools.datagen.run verify    # 独立对账重跑
  python -m tools.datagen.run samples [--out DIR] [--rows N]   # 文件样例（不连库）

退出码：0 成功；1 配置/参数错误；2 对账 FAIL（gen/verify）。
"""

import argparse
import sys
from pathlib import Path

DATAGEN_DIR = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.datagen.run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gen", help="灌数 + dw 种子 + 自动对账")
    sub.add_parser("verify", help="独立对账")
    sub.add_parser("plan", help="dry-run 生成计划（不连库）")
    sp = sub.add_parser("samples", help="产出 CSV/TXT/XLSX 样例文件（不连库）")
    sp.add_argument("--out", default="", help="输出目录（缺省 <repo>/infra/files/samples）")
    sp.add_argument("--rows", type=int, default=5000,
                    help="样例行数（缺省 5000；下限 5000，需各规则期望 ≥ 锚定量）")
    args = ap.parse_args()

    if args.cmd == "plan":
        from tools.datagen.config import compute_plan, load_config
        plan = compute_plan(load_config(DATAGEN_DIR))
        print(f"[plan] 运行日 {plan['today']} seed={plan['seed']} 窗口 {plan['window_days']} 天")
        for sname, s in plan["schemas"].items():
            print(f"[plan] schema {sname} (db={s['db']}) 业务行数 {s['rows_total']:,}")
            for te in s["tables"]:
                tag = f" [{te['sec_level']}]" if te["sec_level"] else (" [dw派生]" if te["derived"] else "")
                print(f"  - {te['table']}: {te['rows']:,} 行"
                      f" 分区 {te['partitions'] or '-'} 规则 {len(te['rules'])}{tag}")
                for r in te["rules"]:
                    print(f"      · {r['rule']} [{r['kind']}] {r['column']}"
                          f" expected={r['expected']}（锚定 {r['anchor']} + 随机 {r['random']}）")
        print(f"[plan] relations {plan['relations']} 条")
        print(f"[plan] 业务表合计 {plan['business_total']:,} / 目标 {plan['target_rows_total']:,}"
              f" → {'OK' if plan['ok'] else 'MISMATCH'}")
        return 0 if plan["ok"] else 1

    from tools.datagen.config import load_config
    cfg = load_config(DATAGEN_DIR)
    if args.cmd == "gen":
        from tools.datagen.gen import run_gen
        report = run_gen(cfg)
        return 0 if report["summary"]["status"] == "PASS" else 2
    if args.cmd == "verify":
        from tools.datagen.reconcile import run_verify
        report = run_verify(cfg)
        return 0 if report["summary"]["status"] == "PASS" else 2
    if args.cmd == "samples":
        from tools.datagen.samples import run_samples
        run_samples(cfg, out=args.out or None, rows=args.rows)
        return 0
    return 1  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
