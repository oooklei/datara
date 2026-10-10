"""基线底稿初始化导出（M-B0 · 一次性脚本）。

把目录快照（common/dag_catalog.json，profile=dag 的 35 type）机械迁移为八段 DSL
初始底稿，写入 t_baseline_progress（status=pending, draft_spec=底稿 JSON）：

- 缺省 dry-run：只打印将初始化的 35 type 清单与统计，不连库不写任何文件；
- --apply：连库（复用 common.db），对每个 type 幂等插入——进度行已存在则跳过；
- 底稿仅做**机械迁移**（formFields→params 字段平移 + render 元数据平移），
  inputs/outputs/conditions/constraints/exclusions/refs/exports/lineage 留空，
  待逐组件语义分析补全（迁移原则见 meta.note）。

用法（datara-backend 目录下）：
    python scripts/export_baseline_drafts.py           # dry-run
    python scripts/export_baseline_drafts.py --apply   # 实际写库
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

CATALOG_FILE = BACKEND / "common" / "dag_catalog.json"


def build_params(form_fields: list) -> tuple:
    """formFields → params 段机械映射；返回 (params, 含 showIf 的字段 key 清单)。

    映射：{key, label, uiType:原type, required:原required, hint:desc 或 placeholder,
    options:原options, cap:原pick}（缺省键不写）。快照 formFields 无 desc/placeholder/
    options/pick 时对应键自然缺省；showIf 函数不可序列化，迁移时丢弃并记录 key。
    """
    params: list = []
    showif_keys: list = []
    for f in form_fields:
        if not isinstance(f, dict) or not f.get("key"):
            continue
        if "showIf" in f:
            showif_keys.append(f["key"])
        p: dict = {"key": f["key"], "label": f.get("label"), "uiType": f.get("type")}
        if "required" in f:
            p["required"] = f["required"]
        for src_key, dst_key in (("desc", "hint"), ("placeholder", "hint"), ("options", "options"), ("pick", "cap")):
            if f.get(src_key) is not None and dst_key not in p:
                p[dst_key] = f[src_key]
        params.append(p)
    return params, showif_keys


def build_draft(c: dict) -> dict:
    """目录条目 → 初始底稿（八段 DSL；快照有则平移，无则留空）。"""
    params, showif_keys = build_params(c.get("formFields") or [])
    showif_note = "、".join(showif_keys) if showif_keys else "无"
    draft: dict = {
        "form": {
            "inputs": [],
            "outputs": [],
            "params": params,
            "conditions": [],
            "constraints": [],
            "exclusions": [],
            "refs": [],
            "exports": [],
        },
        "lineage": {"assets": []},
        "render": {
            "icon": c.get("icon"),
            "color": c.get("color"),
            "shape": c.get("shape"),
            "summary": c.get("desc"),
            "ports": [],  # 快照无 ports 字段 → 空（端口拓扑属前端运行态）
        },
        "paletteVisible": c.get("paletteVisible"),
        "meta": {
            "migratedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source": "dag_catalog",
            "note": "params 段由旧 formFields 机械迁移（showIf 函数不可序列化已丢弃：%s）；"
            "inputs/outputs/conditions/constraints/exclusions/refs/exports/lineage "
            "待逐组件语义分析补全" % showif_note,
        },
    }
    if c.get("dropPolicy"):
        draft["dropPolicy"] = c["dropPolicy"]  # 快照有则平移（当前快照无此字段）
    return draft


def main() -> None:
    parser = argparse.ArgumentParser(description="基线底稿初始化导出（M-B0，幂等可重复跑）")
    parser.add_argument("--apply", action="store_true", help="实际写库（缺省 dry-run 只打印清单与统计）")
    args = parser.parse_args()

    data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    dag_items = [c for c in data.get("components", []) if c.get("profile") == "dag"]
    dag_items.sort(key=lambda c: str(c.get("code") or c.get("type")))

    drafts = {c["type"]: build_draft(c) for c in dag_items}
    total_params = sum(len(d["form"]["params"]) for d in drafts.values())

    print("目录快照: %s" % CATALOG_FILE)
    print("基线化对象: %d type（profile=dag），机械迁移 params 字段共 %d 个" % (len(drafts), total_params))
    for c in dag_items:
        d = drafts[c["type"]]
        print(
            "  %-16s %-14s params=%-3d executor=%s"
            % (c["type"], str(c.get("code") or ""), len(d["form"]["params"]), c.get("executor") or "-")
        )

    if not args.apply:
        print("\n[dry-run] 未写库；确认后加 --apply 执行（已存在进度行的 type 将跳过）")
        return

    # --apply：连库幂等插入（进度行已存在则跳过，不覆盖既有底稿/状态）
    from common.db import new_session
    from common.models import BaselineProgress

    session = new_session()
    created = skipped = 0
    try:
        for type_name, draft in drafts.items():
            exists = session.query(BaselineProgress).filter(BaselineProgress.type == type_name).first()
            if exists is not None:
                skipped += 1
                continue
            session.add(
                BaselineProgress(
                    type=type_name,
                    status="pending",
                    draft_spec=json.dumps(draft, ensure_ascii=False),
                )
            )
            created += 1
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
    print("\n[apply] 新建进度行 %d，跳过已存在 %d（共 %d）" % (created, skipped, len(drafts)))


if __name__ == "__main__":
    main()
