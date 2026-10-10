"""组件目录（M0）单测：API 契约 + 注册表漂移守卫。

背景：系统组件注册表此前只存在于 `datara-web/src/graph/profiles/*.ts`，被编译进
Vue bundle —— 后端无法校验、无法版本化、无法服务给其他客户端。M0 由
`scripts/export_dag_catalog.py` 从 profile 源码导出 `common/dag_catalog.json`，
经 `GET /api/v1/components` 只读下发。

覆盖：
1. 目录自洽：各 profile 的 route 分布合计 == nodeTypes；dag 36 + backendOnly 2 == 38
   （2026-09-29 基线化目录对账更新：op_script 经 shared.ts 去重后仍属前端组件，
   不再误报 backend-only）；
2. 无派发缺口与 CI 脚本一致：dag 画布 UNROUTED 恰为 stream_input/fuse/output；
3. 只读 API 契约：清单/统计/详情/原始快照/过滤；backendOnly 类型返回 409，未知 404；
4. 漂移守卫：篡改快照内容（**不动自述 hash**）必须被 --check 检出。
   旧实现只比对 old['catalogHash']，而该字段自指，实测可被绕过，故此处专门回归。

不依赖任何外部服务：仅需 fastapi TestClient + 仓库内已生成的快照。
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND = Path(__file__).resolve().parent.parent
REPO = BACKEND.parent
SNAPSHOT = BACKEND / "common" / "dag_catalog.json"
EXPORTER = REPO / "scripts" / "export_dag_catalog.py"

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# `tests/test_stream_i11.py` 在**模块导入期**用 stub 覆盖 sys.modules['common'] 与
# ['common.db']（只给 new_session，无 init_db）且从不恢复。这会污染任何随后需要
# 真实 common.* / api.main 的用例。本模块两者都需要，故：
#   1) 先清掉可能被 stub 污染的 common.*；
#   2) 在**模块导入期**（而非 fixture 内）急切导入 api.main，使其在任何 stub
#      安装之前就完成解析并留在 sys.modules 中。
# 这样无论 pytest 的收集顺序如何，本用例都能拿到真实 app。
for _n in [n for n in sys.modules if n == "common" or n.startswith("common.")]:
    sys.modules.pop(_n, None)

from api.main import create_app  # noqa: E402


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture(scope="module")
def catalog() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 目录自洽

def test_snapshot_exists_and_has_basics(catalog):
    assert SNAPSHOT.is_file(), "快照缺失，请运行 python scripts/export_dag_catalog.py"
    assert catalog["schemaVersion"] == 1
    assert catalog["catalogHash"]
    assert catalog["components"], "组件列表为空"


def test_route_breakdown_sums_to_nodetypes(catalog):
    """每个 profile 的 route 分布合计必须等于其 nodeTypes 数（防解析器漏收/多收）。"""
    errs = catalog["stats"]["consistencyErrors"]
    assert errs == [], f"目录自洽校验失败: {errs}"
    rbp = catalog["stats"]["routeByProfile"]
    for p in catalog["profiles"]:
        assert sum(rbp.get(p["profile"], {}).values()) == p["nodeTypes"], p["profile"]


def test_dag_totals_match_documented_baseline(catalog):
    """DAG 基线：36 个前端 NodeSchema（含编辑态 reroute）+ 2 个仅后端类型 = 38 需建档 type。"""
    s = catalog["stats"]
    # G-12：smoke 已补前端 NodeSchema → 不再是 backend-only
    assert s["backendOnlyTypes"] == ["src_select", "tgt_select"]
    assert s["dagTotal"] + s["backendOnlyCount"] == 38
    # 31 个 dag 前端组件有派发实现（20 master = 16 编排 + 1 页面 + 3 流编排接线 G1，11 worker 含 smoke）；
    # 另 2 个仅后端类型也可路由
    assert s["dagRoutable"] == 31
    assert s["dagRoutable"] + s["backendOnlyCount"] == 33


def test_dag_unrouted_closed_by_g1(catalog):
    """G1 收口回归（实施计划 20260926 Task C1）：stream_input/fuse/output 已接线
    master 批引擎分派表（_exec_stream 编排面占位，数据面由 worker 常驻流任务承载），
    dag 引擎口径 UNROUTED 必须为空。若此断言失败说明分派表又出现缺口。"""
    s = catalog["stats"]
    assert s["unrouted"] == 0
    assert s["unroutedTypes"] == []


def test_unrouted_total_does_not_hide_etl_and_stream(catalog):
    """回归：全系统口径必须如实上报各 profile 的执行缺口，防止「dag 已清零」掩盖其它 profile。

    2026-09-29 基线化目录对账更新：M-B2 已为 etl 17 + stream 10 个演示组件注册
    worker 执行器（components/catalog.py WORKER_TYPES + worker/executors/*），
    全系统 UNROUTED 清零；「凡派发必有执行器」的缺口守卫由 test_catalog_consistency.py
    的 WORKER_TYPES ⊆ EXECUTORS 门禁承接，本用例保留「全系统口径如实上报」语义。
    """
    s = catalog["stats"]
    assert s["unroutedTotal"] == 0
    assert s["unroutedByProfile"] == {}
    assert s["unrouted"] == 0


def test_execution_model_is_declared_per_profile(catalog):
    """executionModel 是 M1「发布必须绑定执行契约」的依据。

    dag profile 内按 type 细化：dag-engine（默认）/ passthrough（直通配置节点）/
    template（编排模板）。2026-09-29 executionModel 口径修正：M-B2 为 etl/stream
    演示组件注册 worker 执行器后，导出器按 route=worker 且 executor 已落盘推导为
    dag-engine，etl/stream 全量 dag-engine（旧口径 demo-only 已失效）；topo 全
    canvas-device。"""
    by_prof: dict[str, set[str]] = {}
    for c in catalog["components"]:
        by_prof.setdefault(c["profile"], set()).add(c["executionModel"])
    # dag profile 包含三种执行模型（按 type 细化，覆盖 profile 级粗分类）
    assert by_prof["dag"] == {"dag-engine", "passthrough", "template", "nonExecutable"}
    # 2026-09-29 executionModel 口径修正：M-B2 执行器注册后 etl/stream 全量
    # route=worker → dag-engine
    assert by_prof["etl"] == {"dag-engine"}
    assert by_prof["stream"] == {"dag-engine"}
    assert by_prof["topo"] == {"canvas-device"}

    # 逐 type 校验：passthrough 集 = 直通配置节点（自身不执行，配置被下游拍平消费）
    passthrough_types = {c["type"] for c in catalog["components"]
                         if c["executionModel"] == "passthrough"}
    assert passthrough_types == {
        "endpoint_select", "field_map", "field_map_union", "condition_set", "page_board",
    }, "passthrough 集应与 PASSTHROUGH_TYPES 一致（page_board 归 passthrough 不归入 nonExecutable）"

    # template 集 = 编排模板（落图即展开为节点链，无独立运行时路由）
    template_types = {c["type"] for c in catalog["components"]
                      if c["executionModel"] == "template"}
    assert template_types == {"src_base_orch", "tgt_base_orch", "file_sync_orch", "demo_pipeline"}, \
        "template 集 = 3 个 dag 编排模板 + etl 的 demo_pipeline"

    # dag-engine 组件分两类：master 路由（控制流节点，无 worker executor）/
    # worker 路由（执行节点，必须绑定 executor）。
    dag_engine_worker = [c for c in catalog["components"]
                         if c["profile"] == "dag" and c["executionModel"] == "dag-engine"
                         and c["route"] == "worker"]
    for c in dag_engine_worker:
        assert c["executor"], "dag-engine worker 路由组件 %s 必须绑定 executor" % c["type"]
    # master 路由的 dag-engine 组件（start/end/conditions/switch/fork/join/merge/delay/
    # dependent/loop/assert/stream_*/variable）由 master 引擎直接处理，无 worker executor。
    dag_engine_master = [c for c in catalog["components"]
                         if c["profile"] == "dag" and c["executionModel"] == "dag-engine"
                         and c["route"] == "master"]
    assert len(dag_engine_master) > 0, "应由 master 路由的控制流节点"


def test_topo_devices_are_non_executable_not_unrouted(catalog):
    """topo 的 13 个是 shape=device/form=[] 的画布元件，归 nonExecutable 而非 UNROUTED，
    否则会虚增「缺执行实现」的数量。"""
    topo = [c for c in catalog["components"] if c["profile"] == "topo"]
    assert len(topo) == 13
    assert all(c["route"] == "nonExecutable" for c in topo)
    assert all(c["executionModel"] == "canvas-device" for c in topo)
    assert all(c["formFieldCount"] == 0 for c in topo)


def test_worker_routed_components_bind_executor(catalog):
    """凡 worker 路由组件必须绑定 executor，防止发布闸门被无实现组件绕过。

    2026-09-29 基线化目录对账更新：M-B2 为 etl/stream 演示组件注册执行器后，
    旧断言「demo-only 组件不得绑定 executor」的前提已失效（目录中不再有
    route=UNROUTED 的前端组件），守卫反转为同目的的新不变量：worker 路由 ⇔ executor。
    """
    for c in catalog["components"]:
        if c["route"] == "worker":
            assert c["executor"], c["type"]


def test_cross_profile_duplicate_is_surfaced(catalog):
    """op_script 在 etl 与 stream 各定义一份。

    复核结论：两份定义当前**内容完全一致**（label/icon/color/desc/defaults/form 相同），
    属复制粘贴而非语义冲突 —— 真实风险是「改一处忘另一处」的静默漂移，
    而非同名不同义。故断言只锁定「重复存在」这一事实本身。
    """
    assert "op_script" in catalog["stats"]["crossProfileDuplicateTypes"]
    hits = [c for c in catalog["components"] if c["type"] == "op_script"]
    assert {c["profile"] for c in hits} == {"etl", "stream"}
    a, b = hits
    assert a["label"] == b["label"] and a["desc"] == b["desc"]
    assert a["formFieldCount"] == b["formFieldCount"]


def test_runtime_only_flag(catalog):
    """sync/file_sync 在 dag nodeTypes 内但不在 Palette —— runtimeOnly。"""
    by = {c["type"]: c for c in catalog["components"] if c["profile"] == "dag"}
    for t in ("sync", "file_sync"):
        assert by[t]["runtimeOnly"] is True
        assert by[t]["paletteVisible"] is False


# ---------------------------------------------------------------- 只读 API

def test_list_components(client):
    r = client.get("/api/v1/components")
    assert r.status_code == 200
    d = r.json()["data"]
    assert d["total"] == 76
    assert d["catalogHash"]
    assert d["items"]


def test_list_filters(client):
    assert client.get("/api/v1/components?profile=dag").json()["data"]["total"] == 36
    assert client.get("/api/v1/components?profile=topo").json()["data"]["total"] == 13
    assert client.get("/api/v1/components?route=master").json()["data"]["total"] == 20
    # 2026-09-29 基线化目录对账更新：M-B2 执行器注册后 etl/stream 全量 worker 路由
    # （11 dag + 17 etl + 10 stream），旧基线 11 仅为 dag 口径。
    assert client.get("/api/v1/components?route=worker").json()["data"]["total"] == 38
    # paletteVisible=true 跨 profile 合计
    vis = client.get("/api/v1/components?paletteVisible=true").json()["data"]["total"]
    assert vis == 51
    assert client.get("/api/v1/components?q=join").json()["data"]["total"] > 0
    assert client.get("/api/v1/components?q=__no_such__").json()["data"]["total"] == 0


def test_stats_exposes_drift_signals(client):
    d = client.get("/api/v1/components/stats").json()["data"]
    st = d["stats"]
    assert st["unrouted"] == 0
    # 2026-09-29 基线化目录对账更新：M-B2 执行器注册后全系统 UNROUTED 清零（旧基线 27）。
    assert st["unroutedTotal"] == 0
    assert st["consistencyErrors"] == []
    assert st["crossProfileDuplicateTypes"] == ["op_script"]
    assert d["profiles"] and len(d["profiles"]) == 7, "应覆盖全部 7 个 ViewProfile"
    formats = {p["profile"]: p["paletteFormat"] for p in d["profiles"]}
    assert formats["dag"] == "items"
    assert formats["etl"] == "types", "etl palette 容器格式与 dag 不同，需保留该事实"
    etl = next(p for p in d["profiles"] if p["profile"] == "etl")
    assert etl["paletteSpreads"] == ["dagProfile.palette"]


def test_list_exposes_execution_model(client):
    """列表必须带 executionModel/executionNote —— 发布闸门据此裁定执行契约。"""
    items = client.get("/api/v1/components?profile=etl").json()["data"]["items"]
    # 2026-09-29 executionModel 口径修正：M-B2 执行器注册后 etl 全量 route=worker
    # 且 executor 已落盘 → 导出器推导为 dag-engine（旧口径 demo-only 已失效）。
    assert items and all(i["executionModel"] == "dag-engine" for i in items)
    assert all(i["executionNote"] for i in items)
    topo = client.get("/api/v1/components?profile=topo").json()["data"]["items"]
    assert all(i["executionModel"] == "canvas-device" for i in topo)


def test_component_detail(client):
    d = client.get("/api/v1/components/sql").json()["data"]
    assert d["type"] == "sql"
    assert d["route"] == "worker"
    assert d["executor"] == "sql"
    assert d["formFields"] and d["formFieldCount"] == len(d["formFields"])


def test_backend_only_type_returns_409(client):
    """G-24：src_select/tgt_select 有后端路由但无前端 schema —— 409 而非 404。

    smoke 经 G-12 已补前端 NodeSchema（name/delaySec + palette 入口），故返回 200（非 backend-only）。
    """
    # smoke 已有前端 schema（G-12 落地）→ 200（正常返回）
    assert client.get("/api/v1/components/smoke").status_code == 200
    # src_select / tgt_select 仍无前端 schema → 409
    for t in ("src_select", "tgt_select"):
        r = client.get(f"/api/v1/components/{t}")
        assert r.status_code == 409, t
        assert "无前端 NodeSchema" in r.json()["detail"]


def test_unknown_component_returns_404(client):
    assert client.get("/api/v1/components/__nope__").status_code == 404


def test_raw_catalog(client):
    d = client.get("/api/v1/components/catalog").json()["data"]
    assert d["schemaVersion"] == 1
    assert d["stats"]["total"] == 76


def test_api_is_read_only(client):
    """M0 目录端点保持只读；M1 起草稿端点挂同前缀（api/component_design.py）。

    POST /components 自 M1 起为合法端点（创建草稿，design_component 权限）——
    未带 token 时被鉴权依赖拦截 401；其余写方法仍无路由。
    """
    assert client.post("/api/v1/components").status_code == 401, "M1 草稿创建端点应要求登录"
    for m in ("put", "patch", "delete"):
        r = getattr(client, m)("/api/v1/components")
        assert r.status_code in (404, 405), f"{m} 不应被目录端点支持"


# ---------------------------------------------------------------- 漂移守卫

def _run_check(tmp_out: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(EXPORTER), "--check", "--quiet", "--out", str(tmp_out)],
        capture_output=True, text=True, cwd=str(REPO), encoding="utf-8",
    )


def test_check_passes_on_fresh_snapshot(tmp_path):
    assert _run_check(SNAPSHOT).returncode == 0


def test_check_detects_tampered_content_even_when_hash_kept(tmp_path):
    """回归：只改内容、不动自述 catalogHash，也必须检出（旧实现会漏过）。"""
    bad = tmp_path / "dag_catalog.json"
    doc = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    doc["schemaVersion"] = 999          # hash 字段原样保留
    bad.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    r = _run_check(bad)
    assert r.returncode == 1
    assert "内容" in r.stdout or "过期" in r.stdout


def test_check_detects_label_tamper(tmp_path):
    bad = tmp_path / "dag_catalog.json"
    text = SNAPSHOT.read_text(encoding="utf-8").replace('"label": "SQL"', '"label": "X"', 1)
    bad.write_text(text, encoding="utf-8")
    assert _run_check(bad).returncode == 1


def test_check_detects_broken_json(tmp_path):
    bad = tmp_path / "dag_catalog.json"
    bad.write_text("{ broken", encoding="utf-8")
    r = _run_check(bad)
    assert r.returncode == 1
    assert "JSON" in r.stdout


def test_check_detects_missing_snapshot(tmp_path):
    assert _run_check(tmp_path / "absent.json").returncode == 1
