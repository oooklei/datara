"""清库归档（一次性脚本）：导出运行期五表 → archive/<时间戳>/*.json，可选清空。

背景：M-B0 基线化认可发版要求治理口径从「干净底稿」出发，历史运行数据
（工作流定义/实例/任务/日志/命令）先归档留证再清空，避免新旧口径混杂。

- 导出表：t_wf_definition、t_workflow_instance、t_task_instance、t_task_log、t_command
- 归档目录：datara-backend/archive/<YYYYMMDD_HHMMSS>/*.json（UTF-8，ensure_ascii=False）
- 首次建 archive/ 时自动向 datara-backend/.gitignore 追加 archive/（已存在不重复）
- 无 --confirm：只导出 + 打印统计，不动库；带 --confirm：导出成功后逐表 DELETE 清空
- 归档为纯 JSON 快照，**可复盘不可回库**（不提供回库功能）

用法（datara-backend 目录下）：
    python scripts/archive_and_purge.py             # 只导出 + 统计
    python scripts/archive_and_purge.py --confirm   # 导出成功后清空五表
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

ARCHIVE_ROOT = BACKEND / "archive"
GITIGNORE = BACKEND / ".gitignore"

# 导出 / 清空对象（顺序即执行顺序：定义 → 实例 → 任务 → 日志 → 命令）
from common.models import Command, TaskInstance, TaskLog, WfDefinition, WorkflowInstance  # noqa: E402

TABLES = (
    ("t_wf_definition", WfDefinition),
    ("t_workflow_instance", WorkflowInstance),
    ("t_task_instance", TaskInstance),
    ("t_task_log", TaskLog),
    ("t_command", Command),
)


def ensure_gitignore() -> None:
    """向 datara-backend/.gitignore 追加 archive/（文件或行已存在则不动）。"""
    line = "archive/"
    if GITIGNORE.is_file():
        text = GITIGNORE.read_text(encoding="utf-8")
        if line in text.splitlines():
            return
        GITIGNORE.write_text(text.rstrip("\n") + "\n" + line + "\n", encoding="utf-8")
    else:
        GITIGNORE.write_text(line + "\n", encoding="utf-8")


def rows_to_dicts(rows: list) -> list:
    """ORM 行 → 可 JSON 化的 dict（datetime 统一 'YYYY-MM-DD HH:mm:ss'，其余 default=str 兜底）。"""
    out: list = []
    for r in rows:
        item = {}
        for col in r.__table__.columns:
            v = getattr(r, col.name)
            if isinstance(v, datetime):
                v = v.strftime("%Y-%m-%d %H:%M:%S")
            item[col.name] = v
        out.append(item)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="清库归档（导出可复盘，不可回库）")
    parser.add_argument("--confirm", action="store_true", help="导出成功后 DELETE 清空五表（缺省只导出 + 打印统计）")
    args = parser.parse_args()

    from common.db import new_session

    session = new_session()
    try:
        # 1. 统计 + 导出（先全量取行，确认可序列化后再落盘）
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = ARCHIVE_ROOT / stamp
        stats: list = []
        for table, model in TABLES:
            rows = session.query(model).all()
            data = rows_to_dicts(rows)
            stats.append((table, len(rows), data))
        print("各表行数统计：")
        for table, count, _ in stats:
            print("  %-22s %d" % (table, count))
        if not any(count for _, count, _ in stats):
            print("五表均为空，无内容可归档。")
            if not args.confirm:
                return

        out_dir.mkdir(parents=True, exist_ok=True)
        ensure_gitignore()
        for table, _count, data in stats:
            path = out_dir / (table + ".json")
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            print("已归档: %s（%d 行）" % (path, len(data)))

        # 2. 清空（仅 --confirm；逐表 DELETE 打印行数，单事务原子生效）
        if args.confirm:
            deleted: list = []
            for table, model in TABLES:
                n = session.query(model).delete()
                deleted.append((table, n))
            session.commit()
            print("已清空：")
            for table, n in deleted:
                print("  %-22s -%d" % (table, n))
        else:
            print("\n[dry] 未清库；确认后加 --confirm 执行 DELETE（先归档后清空）。")
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
