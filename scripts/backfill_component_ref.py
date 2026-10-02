#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
存量工作流 componentRef 幂等回填（实施计划 20260926 Task D2，治理设计 §9.5）

背景：componentRef {type, version} 引入前，存量画布节点均无该字段；工作流发布闸门
（publish 走 require_component_ref=True 严格模式）会整体拒绝缺 ref 文档。
部署本版本时先跑一次本脚本，此后新画布由设计器自然携带。

口径（§9.5/§9.6）：
- 节点 id 带 sys_exec_ 前缀的运行态物化产物豁免（其 ref 由物化器 materialize_sync_exec
  按源组件 published 版本运行时注入，设计态文档不入库）
- 缺 ref 的设计节点注入 {type: 节点 type, version: 治理库 published 版本 or 1}；
  37 系统目录 type 不在 t_component → version=1（R6 对供给外类型仅做结构校验，不受影响）
- 幂等：已有 componentRef 的节点一律不动；无变化的文档不写库，重复执行零写放大
- doc 的 version/name 等其余字段原样保留

用法（仓库根执行）：
    python scripts/backfill_component_ref.py [--dry-run]

退出码：0 = 成功（含 dry-run）；1 = 异常
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "datara-backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from common.db import new_session  # noqa: E402
from common.log import get_logger  # noqa: E402
from common.models import Component, WfDefinition  # noqa: E402

logger = get_logger("datara.backfill_component_ref")

# 与 master.engine.SYS_EXEC_PREFIX 同口径（不 import engine：避免拉起重依赖链）
SYS_EXEC_PREFIX = "sys_exec_"


def backfill(session, comp_versions: dict = None) -> dict:
    """全表回填（不 commit，事务由调用方控制），返回统计（幂等可重复执行）：

    docs=定义行总数；scanned=含合法节点数组的文档数；patched=发生注入的文档数；
    nodes=注入的节点数。
    """
    if comp_versions is None:
        comp_versions = {c.type: c.published_version for c in session.query(Component).all()}
    stats = {"docs": 0, "scanned": 0, "patched": 0, "nodes": 0}
    for definition in session.query(WfDefinition).all():
        stats["docs"] += 1
        if not definition.graph_json:
            continue
        try:
            doc = json.loads(definition.graph_json)
        except (TypeError, ValueError):
            logger.warning("定义 %s graph_json 非法，跳过", definition.id)
            continue
        nodes = doc.get("nodes")
        if not isinstance(nodes, list):
            continue
        stats["scanned"] += 1
        changed = False
        for node in nodes:
            if not isinstance(node, dict) or str(node.get("id") or "").startswith(SYS_EXEC_PREFIX):
                continue  # §9.6：物化产物豁免，ref 由物化器运行时注入
            data = node.get("data")
            if not isinstance(data, dict):
                data = {}
                node["data"] = data
            if "componentRef" in data:
                continue  # 幂等：已有 ref 一律不动
            ntype = str(node.get("type") or "")
            data["componentRef"] = {"type": ntype, "version": comp_versions.get(ntype) or 1}
            stats["nodes"] += 1
            changed = True
        if changed:
            stats["patched"] += 1
            definition.graph_json = json.dumps(doc, ensure_ascii=False)
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description="存量工作流 componentRef 幂等回填（D2 §9.5）")
    parser.add_argument("--dry-run", action="store_true", help="只统计不写库")
    args = parser.parse_args()
    session = new_session()
    try:
        stats = backfill(session)
        if args.dry_run:
            session.rollback()
            logger.info("dry-run 完成（未写库）: %s", stats)
        else:
            session.commit()
            logger.info("回填完成: %s", stats)
        print(json.dumps(stats, ensure_ascii=False))
        return 0
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
