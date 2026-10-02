# -*- coding: utf-8 -*-
"""工作流定义种子（B 方案：后端预置测试用例，喂画布/任务编排）。

往 t_wf_definition 插 3 条预置定义，tag 与调色板「工作流」分组对齐：
  - wf_wf_sync   : 月度数据同步        [同步]
  - wf_etl_incr  : 增量ETL同步          [ETL]
  - wf_stream_mon: 实时流监控            [流]

用法（容器内）：
  python tools/seed_wf_definition.py
  python tools/seed_wf_definition.py --owner 1
幂等：已存在的 code 跳过，不重复插入。
"""

import argparse
import json
import uuid

from sqlalchemy import func
from sqlalchemy.orm import Session

from common.db import new_session
from common.models import WfDefinition, WfDefinitionLog

PROFILES = [
    {"code": "wf_wf_sync", "name": "月度数据同步", "tags": ["同步"], "profile": "dag", "desc": "月度数据同步（画布测试用例）"},
    {"code": "wf_etl_incr", "name": "增量ETL同步", "tags": ["ETL"], "profile": "dag", "desc": "增量ETL同步（画布测试用例）"},
    {"code": "wf_stream_mon", "name": "实时流监控", "tags": ["流"], "profile": "dag", "desc": "实时流监控（画布测试用例）"},
]


def _next_code(db: Session) -> int:
    """雪花式数字编码：max(code)+1（对齐 api/wf_definition._next_code）。"""
    max_code = db.query(func.max(WfDefinition.code)).scalar()
    return (max_code or 0) + 1


def _empty_doc(wf_id: str, name: str) -> str:
    """最小空 GraphDocument（对齐 api/wf_definition._empty_doc 形状）。"""
    return json.dumps(
        {"id": wf_id, "name": name, "version": 1, "meta": {"profile": "dag"}, "nodes": [], "edges": []},
        ensure_ascii=False,
    )


def seed_wf_definition(db: Session, owner_id: int) -> int:
    """幂等落库：仅插入 code 不存在于 t_wf_definition 的定义。返回插入条数。"""
    inserted = 0
    existing = {code for (code,) in db.query(WfDefinition.code).all()}
    for p in PROFILES:
        if p["code"] in existing:
            print(f"[seed-wf-def] 跳过已存在: {p['code']}", flush=True)
            continue
        wf_id = "wf_" + uuid.uuid4().hex[:8]
        definition = WfDefinition(
            id=wf_id,
            code=_next_code(db),
            name=p["name"],
            version=1,
            release_state="offline",
            flag="yes",
            project_code="default",
            tags=p["tags"],
            graph_json=_empty_doc(wf_id, p["name"]),
            owner_id=owner_id,
        )
        db.add(definition)
        db.flush()
        db.add(
            WfDefinitionLog(
                wf_code=definition.code,
                version=definition.version,
                graph_json=definition.graph_json,
                operator="seed",
                remark="种子预置（画布测试用例，B 方案）",
            )
        )
        inserted += 1
        print(f"[seed-wf-def] 已插入: {p['code']} {p['name']} tags={p['tags']}", flush=True)
    db.commit()
    return inserted


def main():
    ap = argparse.ArgumentParser(description="工作流定义种子（画布测试用例）")
    ap.add_argument("--owner", type=int, default=1, help="owner_id（默认 1=admin）")
    args = ap.parse_args()
    db = new_session()
    try:
        n = seed_wf_definition(db, args.owner)
        total = db.query(WfDefinition).count()
        print(f"[seed-wf-def] 插入={n} 表内总数={total}", flush=True)
    finally:
        db.close()


if __name__ == "__main__":
    main()
