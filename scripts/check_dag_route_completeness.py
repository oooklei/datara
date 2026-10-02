#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CI 断言 · 规则 2：组件路由完备性

目的：在不引入 Plan / CDL 的前提下，用当前源码静态校验
      "每个在前端注册的 nodeType，是否真的能被 Master 或 worker 执行"。

用法：
    python scripts/check_dag_route_completeness.py
    # 可选：--root <repo 根目录>

退出码：
    0 = 全部命中（或仅模板类豁免）
    1 = 存在"声明了但无路由"的 type（CI 应失败）
"""
from __future__ import annotations

import re
import sys
import json
import argparse
from pathlib import Path

# ---------------------------------------------------------------- 路径

DEFAULT_ROOT = Path(__file__).resolve().parent.parent

WEB_TYPES = "datara-web/src/graph/profiles/dag.ts"
WEB_TYPES_TS = "datara-web/src/graph/profiles/types.ts"
MASTER_ENGINE = "datara-backend/master/engine.py"
MASTER_DAG = "datara-backend/master/dag.py"
WORKER_EXEC = "datara-backend/worker/executor.py"
WORKER_EXEC_DIR = "datara-backend/worker/executors"
WEB_PALETTE = "datara-web/src/graph/workbench/GraphWorkbench.vue"

# 落图即展开的模板：没有运行期节点是设计使然，不算缺口
TEMPLATE_TYPES = {
    "src_base_orch",   # C29 -> buildSrcBaseChain
    "tgt_base_orch",   # C30 -> buildTgtBaseChain
    "file_sync_orch",  # C31 -> buildFileSyncChain
    "demo_pipeline",   # -> template.modes[0].build
}

# 声明为"非可执行宿主"的类型：运行期不产生任务实例（需在 nodeTypes 显式标注）
NON_EXECUTABLE_TYPES = {
    "page_board",      # 页面宿主，需后端 SSE/看板 API（G-15/G-17）
}


# ---------------------------------------------------------------- 解析

def read(path: Path) -> str:
    if not path.is_file():
        sys.exit(f"[FATAL] 文件不存在: {path}")
    return path.read_text(encoding="utf-8")


def parse_node_types(ts: str) -> dict[str, dict]:
    """从 dag.ts 的 nodeTypes 数组提取 type -> {code, runtimeOnly, category}。

    只做结构化正则解析，不求 AST —— 目的是零依赖、可在任意 CI 环境跑。
    匹配形如：
        { type: 'sql', code: 'C11', categories: ['etl','general','sync'],
          icon: SqlIcon, shape: 'device', summary: '...', form: [...] },
    """
    out: dict[str, dict] = {}
    # 以 `type: 'xxx'` 为锚点，向后取该条目内的关键字段
    for m in re.finditer(
        r"\{\s*type:\s*'(?P<type>[a-z0-9_]+)'"
        r"(?P<body>.{0,4000}?)(?=\n\s*\},|\n\s*\}\s*,\s*\n)",
        ts,
        re.S,
    ):
        t = m.group("type")
        body = m.group("body")
        code = re.search(r"\bcode:\s*'([^']*)'", body)
        cats = re.search(r"\bcategories:\s*\[([^\]]*)\]", body)
        out[t] = {
            "code": code.group(1) if code else None,
            "categories": (
                re.findall(r"'([a-z]+)'", cats.group(1)) if cats else []
            ),
            "runtimeOnly": "runtimeOnly: true" in body,
        }
    return out


def parse_master_handlers(py: str) -> set[str]:
    """engine.py 的 _execute_node 派发表键集。"""
    handlers: set[str] = set()
    m = re.search(r"handlers?\s*(?::[^=]+)?=\s*\{(.*?)\n\s*\}", py, re.S)
    if not m:
        return handlers
    for k in re.finditer(r"""['"]([a-z0-9_]+)['"]\s*:""", m.group(1)):
        handlers.add(k.group(1))
    return handlers


def parse_master_dictionary_keys(py: str) -> set[str]:
    """_execute_node 附近所有 "type": self._exec_xxx 字面量键（兜底解析）。"""
    keys: set[str] = set()
    idx = py.find("def _execute_node")
    if idx < 0:
        return keys
    window = py[idx : idx + 4000]
    for k in re.finditer(r"""['"]([a-z0-9_]+)['"]\s*:\s*self\._exec_""", window):
        keys.add(k.group(1))
    return keys


def parse_worker_types(py: str) -> set[str]:
    """WORKER_TYPES 键集（frozenset 字面量）。

    G-19 后 WORKER_TYPES 统一定义在 components/catalog.py（dag.py 改为 import）。
    本函数仍解析传入的 py 文本；调用方需传入 catalog.py 内容（见 export_dag_catalog.py）。
    """
    m = re.search(r"WORKER_TYPES\s*(?::[^=]+)?=\s*frozenset\(\s*\{(.*?)\}\s*\)", py, re.S)
    if not m:
        m = re.search(r"WORKER_TYPES\s*(?::[^=]+)?=\s*\{(.*?)\n\}", py, re.S)
        if not m:
            return set()
        return set(re.findall(r"""['"]([a-z0-9_]+)['"]\s*:""", m.group(1)))
    return set(re.findall(r"""['"]([a-z0-9_]+)['"]""", m.group(1)))


def parse_executors(exec_dir: Path) -> set[str]:
    """worker/executors/*.py 中 @register("<type>") 注册的执行器类型。"""
    found: set[str] = set()
    if not exec_dir.is_dir():
        return found
    for py in sorted(exec_dir.glob("*.py")):
        text = py.read_text(encoding="utf-8")
        for m in re.finditer(r"""@register\(\s*['"]([a-z0-9_]+)['"]\s*\)""", text):
            found.add(m.group(1))
    return found


# ---------------------------------------------------------------- 主流程

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(DEFAULT_ROOT))
    ap.add_argument("--json", action="store_true", help="输出 JSON 便于机器消费")
    args = ap.parse_args()
    root = Path(args.root)

    ts = read(root / WEB_TYPES)
    engine = read(root / MASTER_ENGINE)
    dag_py = read(root / MASTER_DAG)
    read(root / WORKER_EXEC)  # 存在性校验

    node_types = parse_node_types(ts)
    master = parse_master_handlers(engine) | parse_master_dictionary_keys(engine)
    workers = parse_worker_types(dag_py)
    executors = parse_executors(root / WORKER_EXEC_DIR)

    routed = master | workers

    # worker 已声明但 executor 未实现（反向缺口）
    missing_executor = sorted(workers - executors)

    # 核心断言：声明了但无路由
    gaps: list[dict] = []
    for t, meta in sorted(node_types.items()):
        if t in routed or t in TEMPLATE_TYPES or t in NON_EXECUTABLE_TYPES:
            continue
        gaps.append(
            {
                "type": t,
                "code": meta["code"],
                "categories": meta["categories"],
                "runtimeOnly": meta["runtimeOnly"],
            }
        )

    report = {
        "nodeTypes_count": len(node_types),
        "master_handlers": sorted(master),
        "worker_types": sorted(workers),
        "executors": sorted(executors),
        "templates_exempt": sorted(TEMPLATE_TYPES),
        "non_executable": sorted(NON_EXECUTABLE_TYPES),
        "routable_count": len(routed),
        "declared_but_unrouted": gaps,
        "worker_without_executor": missing_executor,
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("=" * 68)
        print("CI 规则 2 · 组件路由完备性")
        print("=" * 68)
        print(f"nodeTypes           : {len(node_types)}")
        print(f"master handler 键   : {len(master)}")
        print(f"WORKER_TYPES 键     : {len(workers)}")
        print(f"EXECUTORS 键        : {len(executors)}")
        print(f"模板豁免            : {len(TEMPLATE_TYPES)}  {sorted(TEMPLATE_TYPES)}")
        print(f"非可执行宿主豁免    : {len(NON_EXECUTABLE_TYPES)}  {sorted(NON_EXECUTABLE_TYPES)}")
        print()

        if gaps:
            print(f"[FAIL] 声明了但无路由 —— 可拖出、可保存、运行必失败：{len(gaps)} 项")
            for g in gaps:
                cats = ",".join(g["categories"]) or "-"
                print(
                    f"   - {g['type']:<20} code={str(g['code']):<6} "
                    f"categories={cats:<18} runtimeOnly={g['runtimeOnly']}"
                )
        else:
            print("[OK] 全部 nodeType 均命中路由 / 模板豁免 / 非可执行豁免")

        if missing_executor:
            print()
            print(f"[FAIL] WORKER_TYPES 已声明但无 executor 实现：{len(missing_executor)} 项")
            for t in missing_executor:
                print(f"   - {t}")
        else:
            print("[OK] WORKER_TYPES 与 EXECUTORS 一一对应")

    return 1 if (gaps or missing_executor) else 0


if __name__ == "__main__":
    raise SystemExit(main())
