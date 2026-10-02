#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
M0 · 组件清单导出器

把前端 `dag.ts` 的 `nodeTypes` + `palette` 导出为**可 diff 的 JSON 快照**，
供后端 `GET /api/v1/components` 下发，并作为组件管理（M1+）的只读基线。

设计取舍（重要）：
  M0 **不落库**。系统组件目录的唯一真源应是 git 里的这份 JSON——
  它可 diff、可评审、能作为 CI 基线。若落库会产生"生成物与代码不同步"的漂移陷阱。
  数据库表（`t_component`）在 M1 引入，且只用于**用户自建组件**（需版本/属主/状态机）。

用法：
    python scripts/export_dag_catalog.py                # 写入 JSON + 打印摘要
    python scripts/export_dag_catalog.py --check        # CI 模式：快照过期则退出 1
    python scripts/export_dag_catalog.py --out <path>

输出结构见文件末尾 SCHEMA 注释。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

# 复用路由完备性脚本的解析器，避免两份正则实现漂移
from check_dag_route_completeness import (  # noqa: E402
    NON_EXECUTABLE_TYPES,
    TEMPLATE_TYPES,
    parse_executors,
    parse_master_dictionary_keys,
    parse_master_handlers,
    parse_node_types,
    parse_worker_types,
)

# G-19 单一真源：PASSTHROUGH_TYPES 从 components/catalog.py 导入
_CATALOG_PY = ROOT / "datara-backend" / "components" / "catalog.py"
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location("_catalog_types", _CATALOG_PY)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_PASSTHROUGH_TYPES = _mod.PASSTHROUGH_TYPES

DAG_TS = "datara-web/src/graph/profiles/dag.ts"
# op_script 的 NodeSchema 已去重到 shared.ts（etl/stream 经 `...opScriptSchema` 展开复用）。
# 本导出器按字面量提取、不追踪跨文件 spread，扫描引用它的 profile 时必须把 shared 源码
# 并入扫描文本，否则 op_script 会从目录消失——表现为 backendOnlyTypes 误报 +
# 发布闸门「同名一致」碰撞漏检（M-B1 期间实测，2026-09-29 修复）。
SHARED_TS = "datara-web/src/graph/profiles/shared.ts"
MASTER_ENGINE = "datara-backend/master/engine.py"
MASTER_DAG = "datara-backend/master/dag.py"
WORKER_EXEC_DIR = "datara-backend/worker/executors"
DEFAULT_OUT = "datara-backend/common/dag_catalog.json"


# --------------------------------------------------------------- 通用提取

TYPE_LIT = re.compile(r"\btype:\s*'([a-z0-9_]+)'")


def extract_entries(ts: str) -> dict[str, str]:
    """提取文件内所有形如 `key: { ... type: 'x', ... }` 的对象字面量。

    做法（不依赖缩进/声明形式，对 4 个 profile 文件均适用）：
      1. 找每个 `type: 'x'` 的位置；
      2. 开括号 = 该位置**之前最近的** `{`（因 `type` 均为条目首属性）；
      3. 从开括号做花括号深度扫描到配平，得到条目原文。
    返回 { type: 条目原文 }；同名后者覆盖前者并记入 _dupes。
    """
    out: dict[str, str] = {}
    dupes: list[str] = []
    for m in TYPE_LIT.finditer(ts):
        t = m.group(1)
        open_at = ts.rfind("{", 0, m.start())
        if open_at < 0:
            continue
        depth = 0
        i = open_at
        end = -1
        while i < len(ts):
            c = ts[i]
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
            i += 1
        if end < 0:
            continue
        text = ts[open_at + 1:end]
        # 合理性校验：NodeSchema.form 为必填（types.ts:182），故条目必含 `form:`
        # —— 这一条同时排除掉 FieldSchema.type 字面量（bool/select/...）与
        #    dsTypes 里的数据源类型码（mysql/kafka/flink/...）被误当组件。
        if "form:" not in text:
            continue
        if t in out:
            dupes.append(t)
        out[t] = text
    return out, dupes


def parse_palette(ts: str) -> tuple[dict[str, dict], dict]:
    """解析 palette。**注意：各 profile 的 palette 结构并不一致**（见返回的 meta）：

      - dag / stream / er : { name, items: [{ type: 'x' }, ...] }
      - etl               : { name, types: ['x', ...] }  且末组为 `...dagProfile.palette` 展开
      - topo / lineage / relation : []

    这是组件注册表碎片化的又一表现：Palette 容器格式本身就有两种。
    组件管理（M1+）必须收敛为单一格式。

    返回 ({type: {group, orderInGroup, paletteIndex}}, meta)。
    """
    pm = re.search(r"\bpalette:\s*\[", ts)
    if not pm:
        return {}, {"format": None, "groups": 0, "spreads": []}
    i = pm.end()
    depth = 1
    while i < len(ts) and depth:
        if ts[i] == "[":
            depth += 1
        elif ts[i] == "]":
            depth -= 1
        i += 1
    block = ts[pm.end():i - 1]

    spreads = re.findall(r"\.\.\.(\w+(?:\.\w+)*)\s*,?", block)
    out: dict[str, dict] = {}
    idx = 0
    fmt = None
    # 形式 A: items: [{ type: 'x' }]
    for gm in re.finditer(r"name:\s*'([^']+)'\s*,\s*items:\s*\[(.*?)\]\s*\}", block, re.S):
        fmt = fmt or "items"
        group, items = gm.group(1), gm.group(2)
        c = 0
        for it in re.finditer(r"\{\s*type:\s*'([a-z0-9_]+)'", items):
            out[it.group(1)] = {"group": group, "orderInGroup": c, "paletteIndex": idx}
            c += 1
            idx += 1
    # 形式 B: types: ['x', 'y']
    for gm in re.finditer(r"name:\s*'([^']+)'\s*,\s*types:\s*\[([^\]]*)\]", block, re.S):
        fmt = fmt or "types"
        group, items = gm.group(1), gm.group(2)
        c = 0
        for t in re.findall(r"'([a-z0-9_]+)'", items):
            out[t] = {"group": group, "orderInGroup": c, "paletteIndex": idx}
            c += 1
            idx += 1
    return out, {
        "format": fmt,
        "groups": len(re.findall(r"name:\s*'", block)),
        "spreads": spreads,
    }


# --------------------------------------------------------------- initTemplate（§11 初始化模板，Task 14）

class _TsLiteralError(ValueError):
    """initTemplate 字面量解析失败（含函数/展开等非数据记号时抛出）。"""


def _strip_ts_comments(text: str) -> str:
    """字符串感知地剥离 // 与 /* */ 注释（保留字符串字面量内的 /，如 'https://'）。"""
    out: list[str] = []
    i, n = 0, len(text)
    in_str: str | None = None
    while i < n:
        c = text[i]
        if in_str:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if c == in_str:
                in_str = None
            i += 1
            continue
        if c in ("'", '"', "`"):
            in_str = c
            out.append(c)
            i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
            continue
        if c == "/" and i + 1 < n and text[i + 1] == "*":
            j = text.find("*/", i + 2)
            i = (j + 2) if j >= 0 else n
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _split_top_level(s: str) -> list[str]:
    """按顶层逗号切分（字符串/嵌套深度感知）。"""
    parts: list[str] = []
    depth = 0
    in_str: str | None = None
    cur: list[str] = []
    i, n = 0, len(s)
    while i < n:
        c = s[i]
        if in_str:
            cur.append(c)
            if c == "\\" and i + 1 < n:
                cur.append(s[i + 1])
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in ("'", '"', "`"):
            in_str = c
            cur.append(c)
        elif c in "{[":
            depth += 1
            cur.append(c)
        elif c in "}]":
            depth -= 1
            cur.append(c)
        elif c == "," and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    tail = "".join(cur)
    if tail.strip():
        parts.append(tail)
    return parts


_KEY_RE = re.compile(
    r"^(?:'([^']*)'|\"([^\"]*)\"|([A-Za-z_$][\w$]*))\s*:\s*(.+)$", re.S)


def _parse_ts_literal(text: str):
    """TS 字面量 → python 值（纯数据子集：对象/数组/字符串/数字/布尔/null）。

    仅服务于 initTemplate（§11 纯数据红线）：遇函数/展开/无法识别的记号即抛
    _TsLiteralError，由调用方降级为 None（不导出），保证 catalog 不出现函数文本。
    """
    s = text.strip()
    if not s:
        raise _TsLiteralError("空字面量")
    if s[0] == "{":
        if not s.endswith("}"):
            raise _TsLiteralError("对象不配平")
        obj: dict = {}
        for part in _split_top_level(_strip_ts_comments(s[1:-1])):
            part = part.strip()
            if not part:
                continue
            m = _KEY_RE.match(part)
            if not m:
                raise _TsLiteralError(f"无法解析键值对: {part[:60]}")
            key = next(g for g in m.groups()[:3] if g is not None)
            obj[key] = _parse_ts_literal(m.group(4))
        return obj
    if s[0] == "[":
        if not s.endswith("]"):
            raise _TsLiteralError("数组不配平")
        return [_parse_ts_literal(p) for p in _split_top_level(_strip_ts_comments(s[1:-1]))
                if p.strip()]
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ("'", '"', "`"):
        return s[1:-1]
    if s == "true":
        return True
    if s == "false":
        return False
    if s == "null":
        return None
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        raise _TsLiteralError(f"不支持的字面量: {s[:40]}")


def parse_init_template(entry: str) -> dict | None:
    """提取条目内 `initTemplate: { ... }`（§11 组件初始化模板，Task 14）。

    - 花括号配平采用字符串感知扫描（'https://' 等字符串内容不参与深度计数）；
    - 结构校验：rect.w/h 为数值 + props 为对象，否则视为无效返回 None
      （防 F63 聚合模板等其他形态误入 —— F63 的 template 是函数性质，本函数不碰）。
    """
    m = re.search(r"\binitTemplate:\s*\{", entry)
    if not m:
        return None
    open_at = entry.index("{", m.start())
    depth = 0
    in_str: str | None = None
    i, n = open_at, len(entry)
    end = -1
    while i < n:
        c = entry[i]
        if in_str:
            if c == "\\":
                i += 2
                continue
            if c == in_str:
                in_str = None
        elif c in ("'", '"', "`"):
            in_str = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
        i += 1
    if end < 0:
        return None
    try:
        parsed = _parse_ts_literal(entry[open_at:end + 1])
    except _TsLiteralError:
        return None
    if not isinstance(parsed, dict):
        return None
    rect = parsed.get("rect")
    if not (isinstance(rect, dict)
            and isinstance(rect.get("w"), (int, float))
            and isinstance(rect.get("h"), (int, float))
            and isinstance(parsed.get("props"), dict)):
        return None
    return parsed


# --------------------------------------------------------------- nodeTypes 详情

def parse_form_fields(entry: str) -> list[dict]:
    """解析条目内 form: [ {...}, ... ] 的字段元信息（只取可序列化的部分）。"""
    m = re.search(r"\bform:\s*\[", entry)
    if not m:
        return []
    i = m.end()
    depth = 1
    while i < len(entry) and depth:
        c = entry[i]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
        i += 1
    body = entry[m.end():i - 1]
    fields: list[dict] = []
    j = 0
    while j < len(body):
        b = body.find("{", j)
        if b < 0:
            break
        d = 1
        k = b + 1
        while k < len(body) and d:
            if body[k] == "{":
                d += 1
            elif body[k] == "}":
                d -= 1
            k += 1
        chunk = body[b:k]
        j = k
        key = re.search(r"\bkey:\s*'([^']*)'", chunk)
        if not key:
            continue
        ftype = re.search(r"\btype:\s*'([^']*)'", chunk)
        label = re.search(r"\blabel:\s*'([^']*)'", chunk)
        dts = re.search(r"\bdsTypes:\s*\[([^\]]*)\]", chunk)
        fields.append({
            "key": key.group(1),
            "label": label.group(1) if label else None,
            "type": ftype.group(1) if ftype else None,
            "required": bool(re.search(r"\brequired:\s*true", chunk)),
            "dsTypes": re.findall(r"'([^']*)'", dts.group(1)) if dts else [],
            # 以下为"不可序列化"标记，服务于 CDL 迁移度量
            "hasWhen": "showIf:" in chunk,
            "hasOnChange": "onChange:" in chunk,
            "hasPick": "pick:" in chunk or "cap:" in chunk,
        })
    return fields


def parse_entry_detail(entry: str) -> dict:
    """条目内的标量字段 + 函数存在性标记。"""
    def s(key: str) -> str | None:
        m = re.search(rf"\b{key}:\s*'((?:[^'\\]|\\.)*)'", entry)
        return m.group(1) if m else None

    cats = re.search(r"\bcategories:\s*\[([^\]]*)\]", entry)
    defaults = re.search(r"\bdefaults:\s*\{(.*?)\}", entry, re.S)
    return {
        "label": s("label"),
        "icon": s("icon"),
        "color": s("color"),
        "code": s("code"),
        "desc": s("desc"),
        "shape": s("shape"),
        "phase": s("phase"),
        "categories": re.findall(r"'([^']*)'", cats.group(1)) if cats else [],
        "defaultKeys": (
            re.findall(r"(?:^|[,{\s])([A-Za-z0-9_]+)\s*:", defaults.group(1))
            if defaults else []
        ),
        "runtimeOnly": bool(re.search(r"\bruntimeOnly:\s*true", entry)),
        "hasSummaryFn": bool(re.search(r"\bsummary:\s*\(", entry)),
        "hasPage": bool(re.search(r"\bpage:\s*\{", entry)),
        "hasTemplate": bool(re.search(r"\btemplate:\s*\{", entry)),
        "hasPortsFn": bool(re.search(r"\bports:\s*\(", entry)),
    }


# --------------------------------------------------------------- 主流程

# executionModel：声明该 profile 的组件**由谁执行**。这是 M1「发布必须绑定执行契约」
# 的前置事实，不能靠 route 猜测。
#   dag-engine   → 由 Master 派发点 / Worker executor 执行（master.py + worker/executor.py）
#   demo-only    → **无任何执行实现**（后端全文检索无该 type）；routes.ts 标注 F56a 演示态
#   canvas-device→ 画布装饰元件（shape=device, form=[]），设计上就不执行
EXECUTION_MODEL = {
    "dag":    ("dag-engine",    "Master 派发点 / Worker executor"),
    "etl":    ("demo-only",     "无执行实现；F56a 演示态（未接 DAG 引擎）"),
    "stream": ("demo-only",     "无执行实现；F56a 演示态（未接 stream 引擎）"),
    "topo":   ("canvas-device", "画布拓扑元件（shape=device, form=[]），设计上不执行"),
}
# 2026-09-29 executionModel 口径修正：M-B2 已为 etl/stream 演示组件注册 worker
# 执行器（WORKER_TYPES + worker/executors/*），故 etl/stream 的 profile 级 demo-only
# 仅是 route=UNROUTED 时的兜底口径——route=worker 且 executor 已落盘的组件在
# 下方按 route/executor 推导为 dag-engine（见 build_catalog 内细化分支）。

PROFILE_FILES = [
    ("dag", DAG_TS),
    ("etl", "datara-web/src/graph/profiles/etl.ts"),
    ("stream", "datara-web/src/graph/profiles/stream.ts"),
    ("topo", "datara-web/src/graph/profiles/topo.ts"),
]
# 有 palette 但无 nodeTypes 的 profile（仅画布元件，无组件定义）
PALETTE_ONLY_FILES = [
    ("er", "datara-web/src/graph/profiles/er.ts"),
    ("lineage", "datara-web/src/graph/profiles/lineage.ts"),
    ("relation", "datara-web/src/graph/profiles/relation.ts"),
]


def build_catalog(root: Path) -> dict:
    engine = (root / MASTER_ENGINE).read_text(encoding="utf-8")
    dag_py = (root / MASTER_DAG).read_text(encoding="utf-8")
    # G-19：WORKER_TYPES 统一定义在 datara-backend/components/catalog.py（dag.py 改为 import）
    catalog_py = (root / "datara-backend" / "components" / "catalog.py").read_text(encoding="utf-8")

    master = parse_master_handlers(engine) | parse_master_dictionary_keys(engine)
    workers = parse_worker_types(catalog_py)
    executors = parse_executors(root / WORKER_EXEC_DIR)

    shared_path = root / SHARED_TS
    shared_ts = shared_path.read_text(encoding="utf-8") if shared_path.is_file() else ""

    components: list[dict] = []
    profiles: list[dict] = []
    all_dupes: dict[str, list[str]] = {}

    for prof, rel in PROFILE_FILES:
        ts = (root / rel).read_text(encoding="utf-8")
        if shared_ts and "opScriptSchema" in ts:
            ts += "\n" + shared_ts
        entries, dupes = extract_entries(ts)
        if dupes:
            all_dupes[prof] = sorted(set(dupes))
        pal, pmeta = parse_palette(ts)
        visible = sum(1 for c in entries if c in pal)
        profiles.append({
            "profile": prof,
            "source": rel,
            "nodeTypes": len(entries),
            "dagRelevant": prof == "dag",
            "paletteFormat": pmeta["format"],
            "paletteGroups": pmeta["groups"],
            "paletteItems": len(pal),
            "paletteSpreads": pmeta["spreads"],
            "hidden": len(entries) - visible,
        })

        emodel_profile, ereason_profile = EXECUTION_MODEL[prof]
        for t, entry in entries.items():
            d = parse_entry_detail(entry)
            p = pal.get(t)
            if t in master:
                route = "master"
            elif t in workers:
                route = "worker"
            elif t in TEMPLATE_TYPES:
                route = "template"
            elif t in NON_EXECUTABLE_TYPES:
                route = "nonExecutable"
            elif emodel_profile == "canvas-device":
                # 画布元件（topo 的 lb/gateway/app/... ）设计上就不该派发，
                # 归为 nonExecutable 而非 UNROUTED，否则会虚增"缺实现"数量。
                route = "nonExecutable"
            else:
                route = "UNROUTED"
            # 按 type 分类细化 executionModel（覆盖 profile 级粗分类）。
            # 必须使用**局部变量**，绝不可复用/emodel_profile——否则前一个组件的
            # 分类会泄漏到后续组件（Python 循环变量跨迭代持久化，曾导致 file_sync/
            # notify/stream_input 等继承到 passthrough/template 的错误分类）。
            # passthrough = 直通配置节点（自身不执行，配置被下游拍平消费）；
            # template = 编排模板（落图即展开为节点链，无独立运行时路由）；
            # nonExecutable = 展示型节点（不产生任务实例）。
            if t in _PASSTHROUGH_TYPES:
                emodel, ereason = "passthrough", "直通配置节点（自身不执行，配置被下游拍平消费）"
            elif t in TEMPLATE_TYPES:
                emodel, ereason = "template", "编排模板（落图即展开为节点链，无独立运行时路由）"
            elif t in NON_EXECUTABLE_TYPES:
                emodel, ereason = "nonExecutable", "展示型节点（不产生任务实例）"
            elif route == "worker" and t in executors:
                # 2026-09-29 executionModel 口径修正：M-B2 执行器注册后，凡
                # route=worker 且 executor 已落盘即真实执行（Master 派发点派发到
                # Worker executor），推导为 dag-engine；仅仍 UNROUTED（无任何实现）
                # 的组件才落 profile 级 demo-only 兜底口径。
                emodel, ereason = "dag-engine", "Master 派发点 / Worker executor"
            else:
                emodel, ereason = emodel_profile, ereason_profile
            fields = parse_form_fields(entry)
            components.append({
                "type": t,
                "profile": prof,
                "dagRelevant": prof == "dag",
                "executionModel": emodel,
                "executionNote": ereason,
                "code": d["code"],
                "label": d["label"],
                "icon": d["icon"],
                "color": d["color"],
                "desc": d["desc"],
                "phase": d["phase"],
                "categories": d["categories"],
                "shape": d["shape"],
                "runtimeOnly": d["runtimeOnly"],
                "route": route,
                "executor": t if t in executors else None,
                "paletteVisible": p is not None,
                "paletteGroup": p["group"] if p else None,
                "paletteIndex": p["paletteIndex"] if p else None,
                "initTemplate": parse_init_template(entry),
                "formFieldCount": len(fields),
                "formFields": fields,
                "defaultKeys": d["defaultKeys"],
                "flags": {
                    "hasSummaryFn": d["hasSummaryFn"],
                    "hasPage": d["hasPage"],
                    "hasTemplate": d["hasTemplate"],
                    "hasPortsFn": d["hasPortsFn"],
                },
            })

    for prof, rel in PALETTE_ONLY_FILES:
        ts = (root / rel).read_text(encoding="utf-8")
        pal, pmeta = parse_palette(ts)
        profiles.append({
            "profile": prof, "source": rel, "nodeTypes": 0, "dagRelevant": False,
            "paletteFormat": pmeta["format"], "paletteGroups": pmeta["groups"],
            "paletteItems": len(pal), "paletteSpreads": pmeta["spreads"], "hidden": 0,
        })

    # 跨 profile 重名 type（严重：同一 type 在两个 profile 各定义一次）
    seen: dict[str, list[str]] = {}
    for c in components:
        seen.setdefault(c["type"], []).append(c["profile"])
    cross_profile_dupes = {t: ps for t, ps in seen.items() if len(ps) > 1}

    components.sort(key=lambda c: (
        c["profile"], c["paletteIndex"] is None, c["paletteIndex"] or 0, c["type"]))

    fn_counts = {
        "summary": sum(1 for c in components if c["flags"]["hasSummaryFn"]),
        "ports": sum(1 for c in components if c["flags"]["hasPortsFn"]),
        "form.showIf": sum(1 for c in components for f in c["formFields"] if f["hasWhen"]),
        "form.onChange": sum(1 for c in components for f in c["formFields"] if f["hasOnChange"]),
        "form.pick": sum(1 for c in components for f in c["formFields"] if f["hasPick"]),
    }
    field_types = sorted({f["type"] for c in components for f in c["formFields"] if f["type"]})

    # route 分布（按 profile），并做自洽校验
    route_by_profile: dict[str, dict[str, int]] = {}
    for c in components:
        route_by_profile.setdefault(c["profile"], {}).setdefault(c["route"], 0)
        route_by_profile[c["profile"]][c["route"]] += 1
    consistency: list[str] = []
    for p in profiles:
        rb = route_by_profile.get(p["profile"], {})
        s = sum(rb.values())
        if s != p["nodeTypes"]:
            consistency.append(
                f"profile {p['profile']}: route 合计 {s} != nodeTypes {p['nodeTypes']}")
    # 跨 profile 重名 type
    seen_rt: dict[tuple, list[str]] = {}
    for c in components:
        seen_rt.setdefault((c["profile"], c["type"]), []).append(c["type"])
    dup_in_profile = sorted({k[1] for k, v in seen_rt.items() if len(v) > 1})

    # 后端有路由、但**任何 profile 都没有 NodeSchema** 的类型（前端不可见）
    declared_types = {c["type"] for c in components}
    backend_only = sorted((master | workers) - declared_types)

    # ---- 执行实现缺口：必须同时报两个口径，缺一即误导 ----
    #   dagUnrouted   ：DAG 引擎内的硬缺口（3 个 stream_*），C17/I6 的收口对象
    #   unroutedTotal ：全系统口径（etl 17 + stream 10 亦无任何执行实现）
    # 早期版本只报 dagUnrouted，把 etl/stream 的 27 个"声明了但没有任何后端实现"
    # 藏了起来 —— 那才是更大的问题。
    dag_unrouted = sorted(c["type"] for c in components
                          if c["dagRelevant"] and c["route"] == "UNROUTED")
    all_unrouted = sorted(c["type"] for c in components if c["route"] == "UNROUTED")
    unrouted_by_profile: dict[str, list[str]] = {}
    for c in components:
        if c["route"] == "UNROUTED":
            unrouted_by_profile.setdefault(c["profile"], []).append(c["type"])
    unrouted_by_profile = {k: sorted(v) for k, v in sorted(unrouted_by_profile.items())}

    catalog = {
        "schemaVersion": 1,
        "generatedAt": None,
        "source": [rel for _, rel in PROFILE_FILES],
        "scope": "system",
        "note": (
            "M0 只读系统组件目录，覆盖全部 7 个 ViewProfile。"
            "用户自建组件（M1+）以 scope='user' 另行下发，不在本文件内。"
        ),
        "stats": {
            "profiles": len(profiles),
            "profilesWithNodeTypes": sum(1 for p in profiles if p["nodeTypes"]),
            "total": len(components),
            "paletteVisible": sum(1 for c in components if c["paletteVisible"]),
            "hidden": sum(1 for c in components if not c["paletteVisible"]),
            "routable": sum(1 for c in components if c["route"] in ("master", "worker")),
            "dagTotal": sum(1 for c in components if c["dagRelevant"]),
            "dagRoutable": sum(1 for c in components if c["dagRelevant"] and c["route"] in ("master", "worker")),
            "backendOnlyTypes": backend_only,
            "backendOnlyCount": len(backend_only),
            "template": sum(1 for c in components if c["route"] == "template"),
            "nonExecutable": sum(1 for c in components if c["route"] == "nonExecutable"),
            # DAG 引擎口径（M1 之前的历史基线，保持 3）
            "unrouted": len(dag_unrouted),
            "unroutedTypes": dag_unrouted,
            # 全系统口径（更真实：etl 17 + stream 10 亦无任何执行实现）
            "unroutedTotal": len(all_unrouted),
            "unroutedByProfile": unrouted_by_profile,
            "runtimeOnly": sum(1 for c in components if c["runtimeOnly"]),
            "formFieldCount": sum(c["formFieldCount"] for c in components),
            "formFieldTypeCount": len(field_types),
            "formFieldTypes": field_types,
            "nonSerializable": fn_counts,
            "routeByProfile": route_by_profile,
            "consistencyErrors": consistency,
            "duplicateTypeInProfile": dup_in_profile,
            "crossProfileDuplicateTypes": sorted(cross_profile_dupes),
        },
        "profiles": profiles,
        "components": components,
    }
    body = json.dumps(catalog, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    catalog["catalogHash"] = hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]
    return catalog


def _canon(obj: dict) -> str:
    """确定性序列化：用于 --check 的内容比对（键序固定）。"""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)


def _first_diff(a: list[str], b: list[str]) -> tuple | None:
    """返回首个差异 (行号, 旧行, 新行)，用于 --check 失败时定位。"""
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else "<EOF>"
        y = b[i] if i < len(b) else "<EOF>"
        if x != y:
            return (i + 1, x.strip()[:120], y.strip()[:120])
    return None


def main() -> int:
    # Windows 控制台默认 codepage（cp936/GBK）会把中文输出成乱码，且子进程捕获时
    # 无法按 UTF-8 解码。强制 stdout/stderr 为 UTF-8，保证输出在任何环境下可读可测。
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # pragma: no cover
            pass

    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--out", default=None)
    ap.add_argument("--check", action="store_true", help="CI：快照过期则退出 1")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    out = Path(args.out) if args.out else root / DEFAULT_OUT
    catalog = build_catalog(root)
    catalog["generatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    payload = json.dumps(catalog, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not out.is_file():
            print(f"[FAIL] 快照不存在: {out}（请运行 export_dag_catalog.py）")
            return 1
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(f"[FAIL] 快照不是合法 JSON: {out}  ({exc})")
            return 1

        # 比对**内容**而非仅比对自述 hash。
        # 旧实现只比 old['catalogHash']，而该字段是自指的：任何手工改动/损坏只要
        # 没碰这个字段就能蒙混过关（已实测可绕过）。
        # generatedAt 是时间戳，比对时剔除，避免每次运行都判为漂移。
        old_body = {k: v for k, v in old.items() if k != "generatedAt"}
        new_body = {k: v for k, v in catalog.items() if k != "generatedAt"}

        if old.get("catalogHash") != catalog["catalogHash"]:
            print(f"[FAIL] 快照已过期: {out.name}")
            print(f"       期望 hash={catalog['catalogHash']}  实际 hash={old.get('catalogHash')}")
            print(f"       请运行 python scripts/export_dag_catalog.py 并提交")
            return 1
        if _canon(old_body) != _canon(new_body):
            diff = _first_diff(_canon(old_body).splitlines(), _canon(new_body).splitlines())
            print(f"[FAIL] 快照内容与源码不一致: {out.name}")
            print(f"       hash 未变但内容已改（手工编辑或文件损坏）")
            if diff:
                print(f"       首个差异 行{diff[0]}:\n         - {diff[1]}\n         + {diff[2]}")
            print(f"       请运行 python scripts/export_dag_catalog.py 重新生成")
            return 1
        if not args.quiet:
            print(f"[OK] 快照与源码一致 (hash={catalog['catalogHash']})")
        return 0

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(payload, encoding="utf-8")

    if not args.quiet:
        s = catalog["stats"]
        print("=" * 68)
        print("M0 · 组件清单导出")
        print("=" * 68)
        print(f"输出      : {out.relative_to(root) if out.is_relative_to(root) else out}")
        print(f"hash      : {catalog['catalogHash']}")
        print(f"总组件    : {s['total']}  (palette 可见 {s['paletteVisible']} / 隐藏 {s['hidden']})")
        print(f"可路由    : {s['routable']}  (master+worker)")
        print(f"模板      : {s['template']}   非可执行: {s['nonExecutable']}   runtimeOnly: {s['runtimeOnly']}")
        print(f"DAG 无路由: {s['unrouted']}  {s['unroutedTypes']}   (DAG 引擎口径·C17/I6 收口对象)")
        print(f"全系统无路由: {s['unroutedTotal']}  按 profile: "
              f"{ {k: len(v) for k, v in s['unroutedByProfile'].items()} }")
        print(f"            etl/stream 组件在后端全文检索不到任何执行实现（演示态），一并计入")
        print(f"仅后端    : {s['backendOnlyCount']}  {s['backendOnlyTypes']}   (有路由但无前端 NodeSchema)")
        print(f"表单字段  : {s['formFieldCount']} 个，控件类型 {s['formFieldTypeCount']} 种")
        print(f"            {s['formFieldTypes']}")
        print(f"不可序列化: {s['nonSerializable']}")
        print("-" * 68)
        print("profile 分布 / palette 格式：")
        for p in catalog["profiles"]:
            print(
                f"  {p['profile']:<9} nodeTypes={p['nodeTypes']:<3} "
                f"dag={str(p['dagRelevant']):<5} paletteFmt={str(p['paletteFormat']):<6} "
                f"groups={p['paletteGroups']:<2} items={p['paletteItems']:<3} "
                f"spreads={p['paletteSpreads']}"
            )
        print("-" * 68)
        print("route 分布：")
        for prof, rb in s["routeByProfile"].items():
            print(f"  {prof:<9} {rb}")
        if s["consistencyErrors"]:
            print("[WARN] 自洽校验未通过：")
            for e in s["consistencyErrors"]:
                print(f"   - {e}")
        if s["duplicateTypeInProfile"]:
            print(f"[WARN] 同 profile 内 type 重复: {s['duplicateTypeInProfile']}")
        if s["crossProfileDuplicateTypes"]:
            print(f"[WARN] 跨 profile 重名 type: {s['crossProfileDuplicateTypes']}")
    return 0


# SCHEMA
# {
#   schemaVersion, generatedAt, catalogHash, source, scope, note,
#   stats: { total, paletteVisible, hidden, routable, template, nonExecutable,
#            unrouted, unroutedTypes, runtimeOnly, formFieldCount,
#            formFieldTypeCount, formFieldTypes[], nonSerializable{} },
#   components: [ { type, code, label, icon, color, desc, phase, categories[],
#                   shape, runtimeOnly, route, executor, paletteVisible,
#                   paletteGroup, paletteIndex, initTemplate|null (§11 纯数据
#                               { rect{w,h}, props, bindings?, sample? }),
#                   formFieldCount,
#                   formFields[{key,label,type,required,dsTypes[],
#                               hasWhen,hasOnChange,hasPick}],
#                   defaultKeys[], flags{...} } ]
# }

if __name__ == "__main__":
    raise SystemExit(main())
