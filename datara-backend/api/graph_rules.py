"""服务端图校验规则引擎（实施计划 20260926 Task A1，大文档 §3.3 graph_rules 最小集）。

口径对齐：
- 环检测与前端 GraphWorkbench 前置检测同语义（Kahn 拓扑排序）
- 必填与前端 W1（formLinkage.requiredMissing）同口径，但仅覆盖**无条件必填**：
  showIf 依赖函数语义无法 JSON 化，catalog 导出只留 hasWhen 布尔，条件必填留前端
  弹窗/Inspector/保存闸门（W1）——边界明确，不做函数语义复制
- upstreamMax 引用数校验暂缓：导出器未含 pick 结构，Task F3 扩展导出后补

规则集（validate_graph 返回违规清单，空=通过）：
- R0 结构基础：nodes/edges 为 list、节点 id/type 非空、边 source/target 非空
- R1 环检测：存在环即失败（列环节点）
- R2 节点类型合法性：type ∈ 组件目录 ∪ backendOnlyTypes（src_select/tgt_select/smoke
  为旧画布兼容路径）∪ sys_exec_* 物化产物豁免
- R3 无条件必填：catalog formFields 中 required=true 且 hasWhen=false 且 type≠hint
  的字段，data 值为空（None/''/空数组）即缺失
- R4 悬挂边：边端点必须指向画布内存在的节点
- R5 引用有效性（Task F4）：data 中 ${var} 引用必须可解析——变量链口径与引擎
  master/variables.VarResolver 同源：run.instanceId/run.loopIter 白名单、同节点
  params key、工作流变量(t_wf_variable)、全局参数(t_global_param)、内置时间参数
  14 项、date(N) 函数式、日期命名模式；${tmp.*} 实例级/C21 注入层运行时才可知，
  保存时跳过；$[...] 时间模板恒可求值（仅 $[wf.x] 混用语法按变量链校验）。
  列/表引用：upstreamSchemas 无后端供给，暂不校验（L2 schema 登记后补）。
- R6 componentRef（Task D2，治理设计 §9）：节点 data.componentRef {type, version}
  结构校验（type 与节点 type 一致 §9.1；version 为 ≥1 整数，禁 latest/null/缺省
  §9.2）；版本存在性按 comp_versions 供给（type→published_version，save/publish
  查 t_component 组装，None 跳过——纯函数兼容）；缺 ref 仅在
  require_component_ref=True（工作流发布路径）拒绝，save 宽松兼容存量未回填文档
  （部署时先跑 scripts/backfill_component_ref.py，§9.5）；sys_exec_* 物化产物豁免
  （§9.6，其 componentRef 由物化器按源组件 published 版本注入）。
- R12 组件版本存在性（Task D2 §9 + G-21 收口）：节点的 type 若在 comp_versions
  供给中对应值为 None（t_component 查无 published_version），即该组件当前无生效版本
  ——保存时 warning 留痕（§8/§18.3：无 published 版本的组件其工作流不可发布），
  发布时 R6 已升级为 error 拒绝。
- R14 边端口类型交集（工作台优化 Task 9，方案 §3.1/§11.2 前后端同规则）：port_types
  供给存在时逐边判 port_types_match_py——矩阵镜像前端 portTypes.ts（唯一真源在原侧，
  本侧禁止单独演进，portTypeCases.json 22 条用例表做行为等价证明）；端口类型解析不到
  （供给外 type/handle 未命中/缺省 handle/端口无 type）视为 any 不误拦；任一边不匹配
  → 「类型不匹配：源 X → 目标 Y」（与前端连线四道闸同一文案）。

降级策略：catalog 快照缺失/损坏时 R2/R3 跳过并 error 日志（部署事故另查），
R0/R1/R4 不依赖目录照常执行——校验引擎不可用不卡死保存主链路。
vars_supply 缺省（None）时 R5 整体跳过（纯函数兼容：既有测试/A2 publish 无 db 上下文
亦可调用；save/publish 端点负责查库组装传入）。
"""

import json
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from common.vars_render import (
    BUILTIN_VAR_NAMES,
    DATE_FUNC_RE,
    TIME_RE,
    VAR_RE,
    render_pattern,
)
from components.catalog import NON_EXECUTABLE_TYPES, PASSTHROUGH_TYPES, TEMPLATE_TYPES

logger = logging.getLogger("datara.graph_rules")

CATALOG_FILE = Path(__file__).resolve().parent.parent / "common" / "dag_catalog.json"

# 引擎运行时变量白名单（master/variables.VarResolver.runtime_scope 同口径）
RUN_VARS = frozenset({"run.instanceId", "run.loopIter"})
# 日期命名模式判定的求值基准（纯格式判定，任意时刻结果一致）
_PATTERN_PROBE = datetime(2000, 1, 1)

# ---- R14 端口类型兼容矩阵（工作台优化 Task 9，方案 §3.1/§11.2）----
# 唯一真源：datara-web/src/graph/model/portTypes.ts 的 TYPE_COMPAT——本字典为其逐行
# 镜像（键=源类型，值=可流入的目标类型集合），两侧由共享用例表 portTypeCases.json
# （22 条，两侧测试各跑同一份）做行为等价锁定；§11.2 一致性契约：禁止单侧单独演进，
# 改矩阵必须先改 portTypes.ts 并同步用例表。
TYPE_COMPAT = {
    "string": ["string"],
    "number": ["number", "string"],
    "boolean": ["boolean"],
    "json": ["json", "string"],
    "table": ["table", "dataset", "json"],
    "dataset": ["dataset", "table", "json"],
    "file": ["file", "json"],
    "stream": ["stream"],
}


def port_types_match_py(src, dst) -> bool:
    """端口类型交集匹配（R14 纯函数，前端 portTypesMatch 逐行同构）：

    任一端为 any（或空值/未知类型）恒真，优先于 none 判定；无 any 时任一端为 none
    恒假；其余查兼容矩阵（未知源类型视为 any——存量旧组件未声明 type 不误拦）。
    """
    if not src or not dst or src == "any" or dst == "any":
        return True
    if src == "none" or dst == "none":
        return False
    row = TYPE_COMPAT.get(src)
    return True if row is None else dst in row


def _port_type(port_types: dict, node_map: dict, node_id, handle, side: str):
    """单端端口类型解析（R14，前端 GraphWorkbench.connPortType 逐行同构）：

    供给按组件 type → {inputs:[{name,type}], outputs:[{name,type}]}（spec ports 形态）。
    节点/组件 type 不在供给、side 端口清单缺失、handle 缺省或未命中端口名、命中但未
    声明 type——任一情形返回 None（=any），与前端宽进口径一致不误拦。
    """
    n = node_map.get(node_id)
    if not isinstance(n, dict):
        return None
    spec = port_types.get(str(n.get("type") or ""))
    if not isinstance(spec, dict):
        return None
    ports = spec.get(side)
    if not isinstance(ports, list) or not handle:
        return None
    for p in ports:
        if isinstance(p, dict) and p.get("name") == handle:
            t = p.get("type")
            return str(t) if t else None
    return None


@lru_cache(maxsize=1)
def _catalog() -> dict:
    """读目录快照（进程内缓存，随代码发布不变，与 api/component._load 同假设）。

    不可用返回 {} 并 error 日志：调用方据此降级 R2/R3，而非 503 拦保存。
    """
    try:
        return json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("组件目录快照不可用，图校验降级（仅结构/环/悬边规则）: %s", exc)
        return {}


def _legal_types(cat: dict) -> set:
    """合法节点类型全集：目录组件 ∪ 后端保留类型（旧画布兼容）。"""
    types = {str(c.get("type") or "") for c in cat.get("components", [])}
    types.discard("")
    types.update(cat.get("stats", {}).get("backendOnlyTypes") or [])
    return types


def _is_blank(v) -> bool:
    """空值判定（与前端 requiredMissing 同口径）：None/''/空数组。"""
    if isinstance(v, list):
        return len(v) == 0
    return v is None or v == ""


def _extract_refs(obj, out: list, branches_key: str = "branches") -> None:
    """深遍历收集 ${var} 与 $[wf.*] 引用名（R5 扫描范围 = 节点 data 全树）。

    branches 键跳过：引擎 resolve_tree skip_keys 同口径，分支表达式不参与占位渲染。
    $[...] 时间模板恒可求值；仅 $[wf.x] 混用语法（引擎 _time 有 wf. 转发变量链）按完整名校验。
    """
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == branches_key:
                continue
            _extract_refs(v, out, branches_key)
    elif isinstance(obj, list):
        for v in obj:
            _extract_refs(v, out, branches_key)
    elif isinstance(obj, str):
        for m in VAR_RE.finditer(obj):
            name = m.group(1).strip()
            if name:
                out.append(name)
        for m in TIME_RE.finditer(obj):
            inner = m.group(1).strip()
            if inner.startswith("wf.") and inner[3:].strip():
                out.append(inner)


def _ref_resolvable(name: str, vars_supply: dict, node_param_keys: set) -> bool:
    """单引用存在性判定（引擎四级链 + IDE 渲染链并集；顺序无关，命中即合法）。"""
    if name in RUN_VARS:
        return True
    if name.startswith("tmp."):
        return True  # 实例级临时数据，保存时不可校验（引擎运行时同实例查表）
    if name in node_param_keys:
        return True  # 同节点参数（引擎 node_params 优先级最高）
    for key in ("workflow", "global"):
        if name in (vars_supply.get(key) or ()):
            return True
    if name in BUILTIN_VAR_NAMES:
        return True
    if DATE_FUNC_RE.match(name):
        return True
    return render_pattern(name, _PATTERN_PROBE) is not None


def validate_graph(doc: dict, vars_supply: dict = None, comp_versions: dict = None,
                   port_types: dict = None, require_component_ref: bool = False) -> list:
    """校验 GraphDocument，返回违规清单 [{rule, nodeId, message}]（空=通过）。

    vars_supply（Task F4 R5）：{"workflow": set[str], "global": set[str]}，调用方
    （save/publish）按 wf_code 查 t_wf_variable + t_global_param 组装；None 时 R5
    跳过。纯函数（除目录缓存），可测试注入：测试直接 monkeypatch _catalog / 传 supply。
    comp_versions / require_component_ref（Task D2 R6）：t_component type→published_version
    供给与严格模式开关（发布路径传 True；save 宽松兼容存量），None 跳过版本存在性。
    port_types（Task 9 R14，方案 §3.1/§11.2）：组件 type→{"inputs"/"outputs":
    [{name, type}]}（spec ports 形态），调用方查治理库 spec_json 组装（机制同
    vars_supply/comp_versions）；None 时 R14 整体跳过（纯函数兼容），端口类型解析
    不到的边视为 any 不误拦。
    """
    violations: list = []

    def bad(rule, message, node_id=None):
        item = {"rule": rule, "message": message}
        if node_id:
            item["nodeId"] = node_id
        violations.append(item)

    # ---- R0 结构基础 ----
    if not isinstance(doc, dict):
        bad("R0", "doc 不是对象")
        return violations
    nodes = doc.get("nodes")
    edges = doc.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        bad("R0", "nodes/edges 必须为数组")
        return violations

    cat = _catalog()
    legal_types = _legal_types(cat) if cat else None
    fields_by_type = {
        str(c.get("type") or ""): [
            f for f in (c.get("formFields") or [])
            if f.get("required") and not f.get("hasWhen")
            and str(f.get("type") or "") != "hint"
        ]
        for c in cat.get("components", [])
    } if cat else {}

    node_ids: set = set()
    for n in nodes:
        if not isinstance(n, dict):
            bad("R0", "存在非对象节点")
            continue
        nid = str(n.get("id") or "")
        ntype = str(n.get("type") or "")
        if not nid or not ntype:
            bad("R0", "节点缺少 id 或 type", nid or None)
            continue
        node_ids.add(nid)

        # ---- R2 类型合法性 ----
        if legal_types is not None:
            materialized = nid.startswith("sys_exec_") and ntype in ("sync", "file_sync")
            if ntype not in legal_types and not materialized:
                bad("R2", "未知组件类型: %s" % ntype, nid)

        # ---- R3 无条件必填 ----
        data = n.get("data")
        if cat and isinstance(data, dict):
            for f in fields_by_type.get(ntype, []):
                if _is_blank(data.get(f["key"])):
                    bad("R3", "必填项未填: %s" % (f.get("label") or f["key"]), nid)

        # ---- R5 引用有效性（Task F4；vars_supply=None 时跳过） ----
        if vars_supply is not None and isinstance(data, dict):
            param_keys = {
                str(row.get("key"))
                for row in (data.get("params") or [])
                if isinstance(row, dict) and row.get("key")
            }
            refs: list = []
            _extract_refs(data, refs)
            seen: set = set()
            for name in refs:
                if name in seen:
                    continue  # 同节点同名引用去重（避免刷屏）
                seen.add(name)
                if not _ref_resolvable(name, vars_supply, param_keys):
                    if name.startswith("run."):
                        bad("R5", "运行时变量不存在: ${%s}（仅支持 run.instanceId/run.loopIter）" % name, nid)
                    else:
                        bad("R5", "引用的变量未定义: ${%s}" % name, nid)

        # ---- R7 分支边匹配：出边 sourceHandle 必须命中已声明分支 ----
        branches = data.get("branches") if isinstance(data, dict) else None
        if isinstance(branches, list) and ntype in ("conditions", "switch", "assert"):
            branch_ids = {str(b.get("id") or "") for b in branches if isinstance(b, dict)}
            branch_ids.discard("")
            out_edges = [e for e in edges if isinstance(e, dict) and e.get("source") == nid]
            for e in out_edges:
                handle = str(e.get("sourceHandle") or "")
                if handle and handle not in branch_ids:
                    bad("R7", "出边 sourceHandle「%s」未命中已声明分支 %s" % (handle, sorted(branch_ids)), nid)
            # ---- R8 分支全覆盖：每个分支至少一条出边 ----
            for b in branches:
                if not isinstance(b, dict):
                    continue
                bid = str(b.get("id") or "")
                if not bid:
                    continue
                has_out = any(
                    isinstance(e, dict) and e.get("source") == nid
                    and str(e.get("sourceHandle") or "") == bid
                    for e in edges
                )
                if not has_out:
                    bad("R8", "分支「%s」未连接下游" % (b.get("name") or bid), nid)

        # ---- R9 直通节点被消费：passthrough 节点必须至少有一条下游出边 ----
        # 排除：① 后端兼容旧画布节点（src_select/tgt_select/smoke）——无前端 palette 入口；
        # ② 展示型节点（page_board）——渲染宿主，无需出边。
        _backend_only = frozenset(cat.get("stats", {}).get("backendOnlyTypes") or [])
        if (ntype in PASSTHROUGH_TYPES
                and ntype not in TEMPLATE_TYPES
                and ntype not in _backend_only
                and ntype not in NON_EXECUTABLE_TYPES):
            has_out = any(
                isinstance(e, dict) and e.get("source") == nid
                for e in edges
            )
            if not has_out:
                bad("R9", "直通节点无下游消费边（配置无处落地）", nid)

        # ---- R6 componentRef（Task D2，§9）：物化产物豁免（§9.6） ----
        # ---- R12 组件版本存在性（G-21 收口）：无 published 版本的组件登记留痕 ----
        if not nid.startswith("sys_exec_"):
            ref = data.get("componentRef") if isinstance(data, dict) else None
            if ref is None:
                if require_component_ref:
                    bad("R6", "节点缺少 componentRef（禁止缺省语义 §9.2；存量画布请先跑 "
                              "scripts/backfill_component_ref.py 回填）", nid)
                # R12：缺 ref 的节点，若该 type 在 comp_versions 中无 published 版本 → 警告
                # （save 宽松路径：兼容存量未回填文档；但无 published 版本的组件不可发布）
                if comp_versions is not None and ntype in comp_versions \
                        and comp_versions[ntype] is None and ntype not in TEMPLATE_TYPES:
                    bad("R12", "组件「%s」当前无 published 版本（§8/§18.3：该节点所在工作流"
                              "不可发布，请先发布该组件）" % ntype, nid)
            elif not isinstance(ref, dict):
                bad("R6", "componentRef 必须为对象 {type, version}", nid)
            else:
                if ref.get("type") != ntype:
                    bad("R6", "componentRef.type「%s」与节点 type「%s」不一致（§9.1）"
                        % (ref.get("type"), ntype), nid)
                ver = ref.get("version")
                if isinstance(ver, bool) or not isinstance(ver, int) or ver < 1:
                    bad("R6", "componentRef.version 必须为 ≥1 整数（禁止 latest/null，§9.2）", nid)
                elif comp_versions is not None and ntype in comp_versions:
                    published = comp_versions.get(ntype)
                    if published is None:
                        # R6 + R12 联合：有 ref 但组件无 published 版本 → 拒绝发布
                        bad("R6", "组件「%s」当前无 published 版本，工作流不可发布（§8/§18.3）"
                            % ntype, nid)
                    elif ver != published:
                        bad("R6", "组件「%s」引用 v%s，当前 published 为 v%s（升级走显式升级 §9.3）"
                            % (ntype, ver, published), nid)

    # ---- R1 环检测（Kahn） + R4 悬挂边 + R14 边端口类型交集 ----
    node_map = {str(n.get("id") or ""): n for n in nodes if isinstance(n, dict)}
    indeg = {nid: 0 for nid in node_ids}
    adj: dict = {nid: [] for nid in node_ids}
    for e in edges:
        if not isinstance(e, dict):
            bad("R0", "存在非对象边")
            continue
        src, tgt = e.get("source"), e.get("target")
        if not src or not tgt:
            bad("R4", "边缺少 source 或 target")
            continue
        if src not in node_ids:
            bad("R4", "边起点节点不存在: %s" % src)
            continue
        if tgt not in node_ids:
            bad("R4", "边终点节点不存在: %s" % tgt)
            continue
        # ---- R14 边端口类型交集（Task 9，§3.1/§11.2 前后端同规则）----
        # 仅校验两端点均在画布内的边（悬挂边归 R4，前端 edgeTypeIssues 同口径跳过）；
        # 端口类型解析不到视为 any（_port_type 宽进口径），不匹配即拒绝。
        if port_types is not None:
            src_t = _port_type(port_types, node_map, src, e.get("sourceHandle"), "outputs")
            dst_t = _port_type(port_types, node_map, tgt, e.get("targetHandle"), "inputs")
            if not port_types_match_py(src_t, dst_t):
                bad("R14", "类型不匹配：源 %s → 目标 %s" % (src_t, dst_t), src)
        adj[src].append(tgt)
        indeg[tgt] += 1

    queue = [nid for nid, d in indeg.items() if d == 0]
    seen = 0
    while queue:
        cur = queue.pop()
        seen += 1
        for nxt in adj[cur]:
            indeg[nxt] -= 1
            if indeg[nxt] == 0:
                queue.append(nxt)
    if seen != len(node_ids):
        cycle_nodes = sorted(nid for nid, d in indeg.items() if d > 0)
        bad("R1", "存在环，环节点: %s" % ", ".join(cycle_nodes[:10]))

    # ---- R13 物化锚点：含 endpoint_select 的同步链必须挂 assert（G-10 服务端收口）----
    # 对齐 engine.py materialize_sync_exec：无 assert 的同步链不会被物化 → sync 配置无处落地。
    # 保存闸门直接报 error，避免用户画完链才发现运行不了。
    ep_ids = [nid for nid, n in node_map.items()
              if isinstance(n, dict) and n.get("type") == "endpoint_select"]
    if ep_ids:
        has_assert = any(
            isinstance(n, dict) and n.get("type") == "assert"
            for n in nodes if isinstance(n, dict)
        )
        if not has_assert:
            for eid in ep_ids:
                bad("R13", "同步链含 endpoint_select 但无 assert 对账节点（链无法物化，"
                          "请用 src_base_orch/tgt_base_orch/file_sync_orch 模板建链）", eid)

    return violations
