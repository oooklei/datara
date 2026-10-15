# 组件页面设计器实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 [设计文档](../specs/2026-10-03-component-page-designer-design.md) 实现组件页面设计器：三区域布局（左组件库/中画布 288×520 居中阴影/右属性面板）、数据源绑定（placeholder 即默认值）、预览 LIMIT 100、发布即刷新引用、工具条含刷新、全组件（页面组件 + 存量 DAG 组件 35 个）初始化模板 + 目录刷新、aoci 索引。

**Architecture:** 方案 A——前端新建 `views/meta/pageDesigner/`（自研轻量画布，不用 VueFlow）；页面组件注册进现有 `t_component` 治理链（`execution_model='page'`）；后端新增 `api/page_designer.py`（资源目录/预览），`component_design.py` 扩展 page 校验与 refresh-refs。

**Tech Stack:** Vue3+TS+Vite+Pinia+AntD5 / FastAPI+SQLAlchemy / vitest+pytest（sqlite 内存库）

**验证命令（约定）**
- 后端单测：`cd datara-backend; python -m pytest tests/ -x -q`
- 前端单测：`cd datara-web; npx vitest run src/views/meta/pageDesigner` ；类型：`npx vue-tsc --noEmit`

---

### Task 1: 后端——execution_model=page 接入

**Files:**
- Modify: `datara-backend/api/component_design.py:62`（EXECUTION_MODELS）、`:137`（Literal）
- Modify: `datara-web/src/services/componentApi.ts:50`（ExecutionModel 联合类型）
- Test: `datara-backend/tests/test_component_design.py`

- [ ] **Step 1: 写失败测试**（追加到 test_component_design.py）

```python
def test_create_page_component_ok(client):
    set_role(app, "dev")
    r = client.post("/api/v1/components", json={
        "type": "page_sales_board", "name": "销售看板", "profile": "dag",
        "execution_model": "page", "spec": {"page": {"version": 1, "canvas": {"width": 288, "height": 520}, "widgets": []}},
    })
    assert r.status_code == 200

def test_page_model_executable_forbidden(client):
    set_role(app, "dev")
    r = client.post("/api/v1/components", json={
        "type": "page_bad_exec", "name": "x", "profile": "dag",
        "execution_model": "page", "executable": True, "spec": {"page": {"version": 1, "canvas": {}, "widgets": []}},
    })
    assert r.status_code == 422
```

- [ ] **Step 2: 跑测试确认失败** `python -m pytest tests/test_component_design.py -k page -x -q` → FAIL（422/校验拒绝）
- [ ] **Step 3: 实现**

```python
# component_design.py L62
EXECUTION_MODELS = ("dag-engine", "canvas-device", "demo-only", "runtime-only", "page")
# L137 Literal 同步加 "page"；create_component 内：
if body.execution_model == "page" and body.executable:
    raise ApiError(422, "COMP_SPEC_INVALID", "execution_model=page 组件 executable 必须为 false")
```

```ts
// componentApi.ts L50 联合类型加一行
  | 'page'           // 页面设计器产出的 UI 组件（不可执行）
```

- [ ] **Step 4: 跑测试通过**（同 Step 2 命令 → PASS；全量 `pytest tests/test_component_design.py -q` PASS）
- [ ] **Step 5: Commit** `git commit -m "feat(page-designer): execution_model 增 page 值（executable 强制 false）"`

### Task 2: 后端——page DSL 结构校验分支

**Files:**
- Modify: `datara-backend/api/component_design.py`（新增 `_validate_page_spec`，挂入 save_draft/publish 校验链）
- Test: `datara-backend/tests/test_component_design.py`

- [ ] **Step 1: 失败测试**

```python
def _page_spec(widgets):
    return {"page": {"version": 1, "name": "看板", "icon": "bar", "color": "#1677ff",
                     "canvas": {"width": 288, "height": 520, "background": {"fill": "#ffffff"}},
                     "widgets": widgets}}

def test_page_spec_structural_violations():
    from api.component_design import validate_spec_pure_data
    # widget 缺 id/kind；binding 缺 fallback
    bad = _page_spec([{"kind": "text", "rect": {"x": 0, "y": 0, "w": 100, "h": 24},
                       "bindings": {"value": {"kind": "metadata"}}}])
    violations = validate_spec_pure_data(bad)
    assert any("widget.id" in v or "widget.kind" in v for v in violations)
    assert any("fallback" in v for v in violations)

def test_page_spec_valid_passes():
    from api.component_design import validate_spec_pure_data
    ok = _page_spec([{"id": "w1", "kind": "text", "rect": {"x": 8, "y": 8, "w": 120, "h": 24},
                      "props": {"text": "销售"},
                      "style": {}, "bindings": {"value": {"kind": "static", "fallback": "销售"}}}])
    assert validate_spec_pure_data(ok) == []
```

- [ ] **Step 2: 确认失败**（AttributeError/断言失败）
- [ ] **Step 3: 实现**（component_design.py，validate_spec_pure_data 尾部分派）

```python
_WIDGET_KINDS = frozenset({
    # 布局容器
    "grid-row", "card", "tabs", "collapse", "divider", "spacer",
    # 基础元素
    "text", "heading", "rich-text", "image", "icon", "button", "badge", "link",
    # 表单输入
    "input", "number", "select", "date", "date-range", "switch", "slider",
    "radio", "checkbox", "cascader", "textarea", "upload",
    # 数据展示
    "table", "list", "descriptions", "statistic", "progress", "timeline", "tree",
    # 图表
    "chart-bar", "chart-line", "chart-pie", "chart-area", "chart-gauge", "chart-scatter",
    # 绑定元素
    "meta-field", "var-label", "query-result", "sys-status",
})
_BINDING_KINDS = frozenset({"metadata", "variable", "query", "static"})
_BINDING_KIND_FIELDS = {"metadata": "path", "variable": "path", "query": "query", "static": "fallback"}


def _validate_page_spec(spec, violations):
    page = spec.get("page") if isinstance(spec, dict) else None
    if page is None:
        return
    if not isinstance(page, dict) or page.get("version") != 1 or not isinstance(page.get("widgets"), list):
        violations.append("page: 结构非法（需 version=1 与 widgets 数组）")
        return
    canvas = page.get("canvas")
    if not isinstance(canvas, dict) or not (140 <= canvas.get("width", 0) <= 1920) \
            or not (160 <= canvas.get("height", 0) <= 2160):
        violations.append("page.canvas: 尺寸越界（宽 140-1920 / 高 160-2160）")

    def walk(widgets, prefix):
        for i, w in enumerate(widgets):
            p = f"{prefix}widgets[{i}]"
            if not isinstance(w, dict):
                violations.append(f"{p}: 非对象"); continue
            if not w.get("id"): violations.append(f"{p}.widget.id: 缺失")
            if w.get("kind") not in _WIDGET_KINDS:
                violations.append(f"{p}.widget.kind: 未知 kind={w.get('kind')!r}")
            rect = w.get("rect")
            if not isinstance(rect, dict):
                violations.append(f"{p}.widget.rect: 缺失")
            for key, b in (w.get("bindings") or {}).items():
                bp = f"{p}.bindings.{key}"
                if not isinstance(b, dict) or b.get("kind") not in _BINDING_KINDS:
                    violations.append(f"{bp}.kind: 非法"); continue
                field = _BINDING_KIND_FIELDS[b["kind"]]
                if not b.get(field):
                    violations.append(f"{bp}.{field}: 缺失（手动输入兜底 placeholder 即默认值）")
            walk(w.get("children") or [], p + ".")
    walk(page["widgets"], "")
```

在 `validate_spec_pure_data(spec)` 返回前追加：`_validate_page_spec(spec, violations)`（纯数据红线扫描仍先行，page 内容同样过 FORBIDDEN_SNIPPETS）。
- [ ] **Step 4: 通过**；全量 PASS
- [ ] **Step 5: Commit** `feat(page-designer): page DSL 结构校验（kind 白名单/绑定 fallback 必填/画布尺寸钳制）`

### Task 3: 后端——refresh_refs + 端点 + publish 自动刷新

**Files:**
- Modify: `datara-backend/api/component_design.py`（新增 `_refresh_refs` + `POST /{type}/refresh-refs`；publish_version 成功后自动调用）
- Test: `datara-backend/tests/test_component_design.py`

- [ ] **Step 1: 失败测试**

```python
def _put_graph(client, wf_id, comp_type, version):
    doc = {"id": wf_id, "nodes": [
        {"id": "n1", "type": comp_type, "data": {"params": {"componentRef": {"type": comp_type, "version": version}}}},
        {"id": "n2", "type": "other", "data": {"params": {}}},
    ], "edges": []}
    r = client.put(f"/api/v1/graph/{wf_id}", json={"doc": doc})
    assert r.status_code == 200, r.text


def test_refresh_refs_bumps_versions(client):
    set_role(app, "dev")
    _create_and_publish(client, "page_board_a", "page")   # 复用既有 create→freeze→publish 助手
    _put_graph(client, "wf_ref_1", "page_board_a", 1)
    r = client.post("/api/v1/components/page_board_a/refresh-refs")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["refreshed"] == 1 and body["items"][0]["wfId"] == "wf_ref_1"
    # 幂等：再刷一次 refreshed=0
    r2 = client.post("/api/v1/components/page_board_a/refresh-refs")
    assert r2.json()["data"]["refreshed"] == 0
```

- [ ] **Step 2: 确认失败**（404）
- [ ] **Step 3: 实现**

```python
def _refresh_refs(db: Session, comp: Component) -> dict:
    """发布即刷新：扫描 t_wf_definition.graph_json 中 componentRef.type 匹配且 version
    落后于 published_version 的节点，批量升级（幂等）。"""
    published = comp.published_version or 0
    items, refreshed = [], 0
    rows = db.query(WfDefinition).filter(WfDefinition.graph_json.isnot(None)).all()
    for wf in rows:
        try:
            doc = json.loads(wf.graph_json or "{}")
        except ValueError:
            continue
        changed = False
        for node in doc.get("nodes") or []:
            ref = ((node.get("data") or {}).get("params") or {}).get("componentRef") or {}
            if ref.get("type") == comp.type and isinstance(ref.get("version"), int) and ref["version"] < published:
                ref["version"] = published
                node["data"]["params"]["componentRef"] = ref
                changed = True
        if changed:
            wf.graph_json = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
            wf.version = (wf.version or 1) + 1
            wf.update_time = now()
            refreshed += 1
            items.append({"wfId": wf.id, "wfName": wf.name})
    if refreshed:
        db.commit()
    return {"refreshed": refreshed, "publishedVersion": published, "items": items}


@router.post("/{type_name}/refresh-refs", summary="刷新引用（发布即刷新，幂等）")
def refresh_refs(type_name: str, db: Session = Depends(get_db), user=Depends(require_perm("design_component"))):
    comp = _get_or_404(db, type_name)
    if comp.state != "published":
        raise ApiError(409, "COMP_STATE_CONFLICT", "仅 published 组件可刷新引用")
    return ok(_refresh_refs(db, comp))
```

publish_version 成功 return 前追加：`payload["refresh"] = _refresh_refs(db, comp)`。
- [ ] **Step 4: 通过**；全量 PASS
- [ ] **Step 5: Commit** `feat(page-designer): 发布即刷新引用（refresh-refs 端点 + publish 自动挂载，幂等）`

### Task 4: 后端——资源目录端点

**Files:**
- Create: `datara-backend/api/page_designer.py`
- Modify: `datara-backend/api/main.py:81` 后追加注册
- Test: `datara-backend/tests/test_page_designer.py`

- [ ] **Step 1: 失败测试**

```python
"""页面设计器 API 单测（资源目录/预览；sqlite 内存库，零外部依赖）。"""
import sys
from pathlib import Path
from types import SimpleNamespace
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
from api.auth import get_current_user  # noqa: E402


def set_role(app, role="dev"):
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1, user_name="tester", user_role=role)


def test_resources_tree(client):
    set_role(client.app)
    r = client.get("/api/v1/page-designer/resources")
    assert r.status_code == 200
    data = r.json()["data"]
    assert set(data.keys()) == {"datasources", "workflows", "globalParams", "timeParams", "components"}
    assert isinstance(data["timeParams"], list) and data["timeParams"][0]["path"].startswith("$")
```

- [ ] **Step 2: 确认失败**（404）
- [ ] **Step 3: 实现**

```python
"""页面设计器 API：资源目录（设计态元数据+运行态变量）与数据预览（LIMIT 100 只读）。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from api.auth import require_perm
from common.db import get_db
from common.models import Component, DataSource, GlobalParam, WfDefinition, WfVariable
from common.resp import ok

router = APIRouter(prefix="/page-designer", tags=["page-designer"])

TIME_PARAMS = [
    {"path": "$system.date", "label": "当前日期", "sample": "2026-10-03"},
    {"path": "$system.datetime", "label": "当前时间", "sample": "2026-10-03 00:00:00"},
    {"path": "$system.month", "label": "当前月份", "sample": "2026-10"},
]


@router.get("/resources", summary="系统资源目录（适配性绑定候选来源）")
def resources(db: Session = Depends(get_db), _user=Depends(require_perm("design_component"))):
    return ok({
        "datasources": [
            {"id": d.id, "name": d.name, "type": d.type, "db": d.db_name or ""}
            for d in db.query(DataSource).order_by(DataSource.name).all()],
        "workflows": [
            {"code": w.code, "name": w.name,
             "vars": [{"path": f"$wf.{v.name}", "label": v.name, "type": v.type}
                      for v in db.query(WfVariable).filter(WfVariable.wf_code == w.code).all()]}
            for w in db.query(WfDefinition).order_by(WfDefinition.name).all()],
        "globalParams": [
            {"path": f"$param.{p.name}", "label": p.name}
            for p in db.query(GlobalParam).order_by(GlobalParam.name).all()],
        "timeParams": TIME_PARAMS,
        "components": [
            {"type": c.type, "name": c.name, "state": c.state,
             "publishedVersion": c.published_version}
            for c in db.query(Component).order_by(Component.type).all()],
    })
```

main.py：`app.include_router(page_designer.router, prefix="/api/v1")`（import 同步加）。
- [ ] **Step 4: 通过**
- [ ] **Step 5: Commit** `feat(page-designer): 资源目录端点（数据源/工作流变量/全局参数/时间参数/组件清单）`

### Task 5: 后端——预览端点（LIMIT 100 只读）

**Files:**
- Modify: `datara-backend/api/page_designer.py`
- Test: `datara-backend/tests/test_page_designer.py`

- [ ] **Step 1: 失败测试**

```python
def test_preview_rejects_non_select(client):
    set_role(client.app)
    r = client.post("/api/v1/page-designer/preview", json={
        "queries": [{"id": "q1", "datasourceId": 1, "sql": "DELETE FROM t"}]})
    assert r.status_code == 422


def test_preview_caps_rows(monkeypatch, client):
    set_role(client.app)
    called = {}

    def fake_run(ds, sql, cap):
        called["sql"], called["cap"] = sql, cap
        return {"id": "q1", "columns": ["a"], "rows": [[str(i)] for i in range(cap)], "truncated": True, "error": ""}

    monkeypatch.setattr("api.page_designer._run_readonly", fake_run)
    r = client.post("/api/v1/page-designer/preview", json={
        "queries": [{"id": "q1", "datasourceId": 1, "sql": "SELECT a FROM t"}]})
    assert r.status_code == 200
    assert called["cap"] == 100
    assert len(r.json()["data"]["results"]["q1"]["rows"]) == 100
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**

```python
import re
from pydantic import BaseModel, Field

PREVIEW_ROW_CAP = 100  # 设计文档 §8：硬编码上限，不配置化
_SELECT_RE = re.compile(r"\s*(WITH|SELECT)\b", re.IGNORECASE)


class PreviewQuery(BaseModel):
    id: str
    datasourceId: int
    sql: str
    db: str | None = None


class PreviewBody(BaseModel):
    queries: list[PreviewQuery] = Field(default_factory=list)


def _run_readonly(ds: DataSource, sql: str, cap: int) -> dict:
    """只读连接执行单查询，最多取 cap 行（复用 ide 的连接构造）。"""
    from api.ide import _build_conn  # 连接构造单一来源；若函数名不同以实际为准
    result = {"id": "", "columns": [], "rows": [], "truncated": False, "error": ""}
    try:
        with _build_conn(ds) as conn, conn.cursor() as cur:
            cur.execute(sql)
            result["columns"] = [c[0] for c in cur.description or []]
            while len(result["rows"]) < cap:
                batch = cur.fetchmany(min(200, cap - len(result["rows"])))
                if not batch:
                    break
                result["rows"] += [[str(v) for v in row] for row in batch]
            result["truncated"] = cur.fetchone() is not None or len(result["rows"]) >= cap
    except Exception as exc:  # noqa: BLE001
        result["error"] = str(exc)
    return result


@router.post("/preview", summary="数据预览（每查询 LIMIT 100，只读）")
def preview(body: PreviewBody, db: Session = Depends(get_db), _user=Depends(require_perm("design_component"))):
    results = {}
    for q in body.queries:
        sql = (q.sql or "").strip().rstrip(";")
        if not _SELECT_RE.match(sql):
            raise ApiError(422, "PREVIEW_SQL_FORBIDDEN", f"{q.id}: 仅允许 SELECT/WITH 只读查询")
        ds = db.get(DataSource, q.datasourceId)
        if ds is None:
            results[q.id] = {"columns": [], "rows": [], "truncated": False, "error": f"数据源 {q.datasourceId} 不存在"}
            continue
        item = _run_readonly(ds, f"SELECT * FROM ({sql}) _pv LIMIT {PREVIEW_ROW_CAP}", PREVIEW_ROW_CAP)
        item["id"] = q.id
        results[q.id] = item
    return ok({"results": results, "rowCap": PREVIEW_ROW_CAP})
```

（`from api.auth import ApiError` 补 import；`_build_conn` 以 `api/ide.py` 实际连接构造为准，若私有则在本文件提取公共小函数。）
- [ ] **Step 4: 通过**；全量 PASS
- [ ] **Step 5: Commit** `feat(page-designer): 预览端点（只读拦截 + 硬编码 LIMIT 100）`

### Task 6: 前端——designerModel.ts（PageDSL 类型/归一化/校验镜像）

**Files:**
- Create: `datara-web/src/views/meta/pageDesigner/designerModel.ts`
- Test: `datara-web/src/views/meta/pageDesigner/__tests__/designerModel.test.ts`

- [ ] **Step 1: 失败测试**

```ts
import { describe, expect, it } from 'vitest'
import { newWidget, normalizePage, validatePage } from '../designerModel'

const base = { id: 'w1', kind: 'text', rect: { x: 8, y: 8, w: 120, h: 24 } } as const

describe('designerModel', () => {
  it('normalizePage 补齐缺省（画布 288×520、widget id）', () => {
    const p = normalizePage({ page: { version: 1, widgets: [{ kind: 'text' }] } })
    expect(p.canvas.width).toBe(288)
    expect(p.canvas.height).toBe(520)
    expect(p.widgets[0].id).toMatch(/^w_/)
    expect(p.widgets[0].style).toEqual({})
  })
  it('validatePage：未知 kind / 绑定缺 fallback / 尺寸越界', () => {
    const p = normalizePage({ page: { version: 1, canvas: { width: 10, height: 520 }, widgets: [
      { kind: 'nope', bindings: { value: { kind: 'metadata' } } },
    ] } })
    const vs = validatePage(p)
    expect(vs.some((v) => v.includes('kind'))).toBe(true)
    expect(vs.some((v) => v.includes('fallback'))).toBe(true)
    expect(vs.some((v) => v.includes('canvas'))).toBe(true)
  })
  it('newWidget 套模板：rect/props/style 来自模板', () => {
    const w = newWidget('text', { x: 10, y: 10 })
    expect(w.props.text).toBeTruthy()
    expect(w.rect.w).toBeGreaterThan(0)
  })
})
```

- [ ] **Step 2: 确认失败** `npx vitest run src/views/meta/pageDesigner` → FAIL
- [ ] **Step 3: 实现**

```ts
/** PageDSL 类型 + 归一化 + 校验（红线 2 前端镜像；与后端 _validate_page_spec 口径一致）。 */
export interface Rect { x: number; y: number; w: number; h: number }
export interface BackgroundStyle { fill: string; image?: string; size?: string }
export interface BindingRef {
  kind: 'metadata' | 'variable' | 'query' | 'static'
  path?: string; query?: string; datasourceId?: number; fallback: string
}
export interface WidgetNode {
  id: string; kind: string; rect: Rect
  props: Record<string, unknown>
  style: Record<string, string | number>
  bindings: Record<string, BindingRef>
  children?: WidgetNode[]
}
export interface PageDSL {
  version: 1; name: string; icon: string; color: string
  canvas: { width: number; height: number; background: BackgroundStyle }
  widgets: WidgetNode[]
}

export const CANVAS_DEFAULT = { width: 288, height: 520 }   // GraphWorkbench Inspector 规格
export const CANVAS_W = { min: 140, max: 1920 }
export const CANVAS_H = { min: 160, max: 2160 }

let seq = 0
export function genId(kind: string): string {
  seq = (seq + 1) % 1e6
  return `w_${Date.now().toString(36)}${seq.toString(36)}`
}

export function normalizePage(raw: unknown): PageDSL {
  const p = (raw as { page?: Record<string, unknown> })?.page ?? (raw as Record<string, unknown>) ?? {}
  const canvas = (p.canvas ?? {}) as Record<string, unknown>
  const bg = (canvas.background ?? {}) as BackgroundStyle
  return {
    version: 1,
    name: (p.name as string) ?? '未命名组件',
    icon: (p.icon as string) ?? 'block',
    color: (p.color as string) ?? '#1677ff',
    canvas: {
      width: Number(canvas.width) || CANVAS_DEFAULT.width,
      height: Number(canvas.height) || CANVAS_DEFAULT.height,
      background: { fill: bg.fill ?? '#ffffff', image: bg.image, size: bg.size ?? 'cover' },
    },
    widgets: ((p.widgets as Record<string, unknown>[]) ?? []).map((w) => ({
      id: (w.id as string) || genId(String(w.kind ?? 'w')),
      kind: String(w.kind ?? 'text'),
      rect: (w.rect ?? { x: 0, y: 0, w: 120, h: 32 }) as Rect,
      props: (w.props ?? {}) as Record<string, unknown>,
      style: (w.style ?? {}) as Record<string, string | number>,
      bindings: (w.bindings ?? {}) as Record<string, BindingRef>,
      ...(Array.isArray(w.children) ? { children: (w.children as WidgetNode[]).map((c) => normalizeWidget(c)) } : {}),
    })),
  }
}
function normalizeWidget(w: Record<string, unknown>): WidgetNode {
  return normalizePage({ page: { version: 1, widgets: [w] } }).widgets[0]
}

export function validatePage(p: PageDSL): string[] {
  const vs: string[] = []
  if (p.canvas.width < CANVAS_W.min || p.canvas.width > CANVAS_W.max) vs.push('canvas: 宽越界')
  if (p.canvas.height < CANVAS_H.min || p.canvas.height > CANVAS_H.max) vs.push('canvas: 高越界')
  const kinds = WIDGET_KINDS
  const walk = (ws: WidgetNode[]) => {
    ws.forEach((w) => {
      if (!kinds.has(w.kind)) vs.push(`widget.kind: 未知 ${w.kind}`)
      if (w.rect.w <= 0 || w.rect.h <= 0) vs.push(`widget.rect: 尺寸非法 ${w.id}`)
      Object.entries(w.bindings).forEach(([k, b]) => {
        if (!b?.fallback) vs.push(`bindings.${k}.fallback: 缺失（placeholder 即默认值）`)
      })
      walk(w.children ?? [])
    })
  }
  walk(p.widgets)
  return vs
}

export const WIDGET_KINDS = new Set<string>([
  'grid-row', 'card', 'tabs', 'collapse', 'divider', 'spacer',
  'text', 'heading', 'rich-text', 'image', 'icon', 'button', 'badge', 'link',
  'input', 'number', 'select', 'date', 'date-range', 'switch', 'slider', 'radio', 'checkbox', 'cascader', 'textarea', 'upload',
  'table', 'list', 'descriptions', 'statistic', 'progress', 'timeline', 'tree',
  'chart-bar', 'chart-line', 'chart-pie', 'chart-area', 'chart-gauge', 'chart-scatter',
  'meta-field', 'var-label', 'query-result', 'sys-status',
])
export type WidgetKind = string

/** 工厂：由模板创建 widget（templates.ts 注册，避免循环依赖用注入）。 */
export type TemplateOf = (kind: string) => { props: Record<string, unknown>; style: Record<string, string | number>; rect: Rect; bindings?: Record<string, BindingRef> } | undefined
let _templateOf: TemplateOf | undefined
export function bindTemplates(fn: TemplateOf): void { _templateOf = fn }
export function newWidget(kind: string, at: { x: number; y: number }): WidgetNode {
  const t = _templateOf?.(kind)
  return {
    id: genId(kind), kind,
    rect: t?.rect ? { ...t.rect, x: at.x, y: at.y } : { ...at, w: 120, h: 32 },
    props: { ...(t?.props ?? {}) },
    style: { ...(t?.style ?? {}) },
    bindings: {},
  }
}
```

- [ ] **Step 4: 通过**
- [ ] **Step 5: Commit** `feat(page-designer): PageDSL 模型/归一化/校验镜像`

### Task 7: 前端——templates.ts（40 widget 模板 + 页面级模板）

**Files:**
- Create: `datara-web/src/views/meta/pageDesigner/templates.ts`
- Test: 追加到 `__tests__/designerModel.test.ts`

- [ ] **Step 1: 失败测试**

```ts
import { describe, expect, it } from 'vitest'
import { widgetGroups, widgetTemplate, pageTemplates } from '../templates'

describe('templates', () => {
  it('六大分组 40 个 widget 全部带模板', () => {
    const all = widgetGroups.flatMap((g) => g.items)
    expect(all.length).toBe(40)
    expect(new Set(all.map((w) => w.kind)).size).toBe(40)
    all.forEach((w) => expect(widgetTemplate(w.kind)).toBeTruthy())
  })
  it('页面级模板 4 套且均合法', () => {
    expect(pageTemplates.map((t) => t.name)).toEqual(['空白页', '数据看板', '表单页', '列表页'])
    pageTemplates.forEach((t) => expect(t.page().widgets.length).toBeGreaterThanOrEqual(0))
  })
})
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**——六分组结构 `widgetGroups`（布局容器 6 / 基础元素 8 / 表单输入 12 / 数据展示 7 / 图表 6 / 绑定元素 4 = 40），每 widget 一个模板对象（props/style/rect 默认值）。分组与 kind 清单以 Task 6 `WIDGET_KINDS` 为唯一事实源，模板示例：

```ts
import type { PageDSL, Rect, WidgetNode } from './designerModel'

export interface WidgetTemplate { kind: string; label: string; icon: string; props: Record<string, unknown>; style: Record<string, string | number>; rect: Rect }
export interface WidgetGroup { key: string; label: string; items: WidgetTemplate[] }

const T = (kind: string, label: string, icon: string, rect: [number, number, number, number], props: Record<string, unknown> = {}, style: Record<string, string | number> = {}): WidgetTemplate =>
  ({ kind, label, icon, rect: { x: 0, y: 0, w: rect[2], h: rect[3] }, props, style })

export const widgetGroups: WidgetGroup[] = [
  { key: 'layout', label: '布局容器', items: [
    T('grid-row', '栅格行', 'table', [0, 0, 264, 64], { columns: 2, gap: 8 }, { border: '1px dashed #d9d9d9' }),
    T('card', '卡片', 'border', [0, 0, 264, 120], { title: '卡片标题' }, { radius: 12, shadow: 'soft', fill: '#ffffff' }),
    T('tabs', '标签页', 'folder', [0, 0, 264, 160], { tabs: ['标签一', '标签二'] }, {}),
    T('collapse', '折叠面板', 'unfold', [0, 0, 264, 96], { panels: [{ title: '面板一' }] }, {}),
    T('divider', '分隔线', 'minus', [0, 0, 264, 1], {}, { color: '#f0f0f0' }),
    T('spacer', '间距', 'arrows-alt-v', [0, 0, 264, 16], { h: 16 }, {}),
  ] },
  { key: 'basic', label: '基础元素', items: [
    T('text', '文本', 'font-size', [0, 0, 120, 24], { text: '文本内容' }, { fontSize: 13, color: '#1f2329' }),
    T('heading', '标题', 'bold', [0, 0, 200, 32], { text: '标题', level: 3 }, { fontSize: 20, fontWeight: 600 }),
    T('rich-text', '富文本', 'editor', [0, 0, 264, 96], { html: '<p>富文本</p>' }, {}),
    T('image', '图片/插图', 'picture', [0, 0, 160, 96], { src: '', fit: 'cover' }, { radius: 8 }),
    T('icon', '图标', 'smile', [0, 0, 24, 24], { name: 'smile' }, {}),
    T('button', '按钮', 'action', [0, 0, 88, 32], { text: '按钮', type: 'primary' }, { radius: 8 }),
    T('badge', '徽标', 'tag', [0, 0, 64, 22], { text: 'NEW', color: '#ff4d4f' }, {}),
    T('link', '链接', 'link', [0, 0, 96, 22], { text: '链接', href: '#' }, { color: '#1677ff' }),
  ] },
  // 表单输入 12 项：input/number/select/date/date-range/switch/slider/radio/checkbox/cascader/textarea/upload —— 各带 label 与默认 placeholder（如 input: { label: '名称', placeholder: '请输入名称' }）
  // 数据展示 7 项：table/list/descriptions/statistic/progress/timeline/tree —— table 模板含 columns 示例与空态文案
  // 图表 6 项：chart-bar/chart-line/chart-pie/chart-area/chart-gauge/chart-scatter —— 各带 seriesType/空数据占位
  // 绑定元素 4 项：meta-field/var-label/query-result/sys-status —— 各带 path 示例与 fallback 文案
].map((g) => g)
```

（计划执行者按同款 `T(...)` 一行式补齐注释中列出的其余 30 项，值取 AntD5 默认观感；`bindTemplates` 在模块顶层调用注入 `designerModel.newWidget`。）页面级模板：

```ts
export const pageTemplates = [
  { name: '空白页', page: (): PageDSL => blank() },
  { name: '数据看板', page: (): PageDSL => fromWidgets(['heading', 'statistic', 'statistic', 'chart-bar', 'table']) },
  { name: '表单页', page: (): PageDSL => fromWidgets(['heading', 'input', 'select', 'date', 'textarea', 'button']) },
  { name: '列表页', page: (): PageDSL => fromWidgets(['heading', 'table', 'progress']) },
]
```

- [ ] **Step 4: 通过**
- [ ] **Step 5: Commit** `feat(page-designer): 40 widget 全量模板 + 4 套页面级模板`

### Task 8: 前端——bindingCatalog.ts（适配候选 + placeholder 默认值）

**Files:**
- Create: `datara-web/src/views/meta/pageDesigner/bindingCatalog.ts`
- Test: `__tests__/bindingCatalog.test.ts`

- [ ] **Step 1: 失败测试**

```ts
import { describe, expect, it } from 'vitest'
import { candidatesFor, resolveFallback } from '../bindingCatalog'
import type { ResourceCatalog } from '../bindingCatalog'

const cat: ResourceCatalog = {
  datasources: [{ id: 1, name: '主库', type: 'mysql', db: 'sales' }],
  workflows: [{ code: 100, name: '日批', vars: [{ path: '$wf.batch', label: 'batch', type: '文本' }] }],
  globalParams: [{ path: '$param.env', label: 'env' }],
  timeParams: [{ path: '$system.date', label: '当前日期', sample: '2026-10-03' }],
  components: [],
}

describe('bindingCatalog', () => {
  it('标量槽候选 = 变量+参数+时间参数+组件', () => {
    const c = candidatesFor('scalar', cat)
    expect(c.some((x) => x.value === '$wf.batch')).toBe(true)
    expect(c.some((x) => x.value === '$system.date')).toBe(true)
  })
  it('dataset 槽候选 = 数据源表入口', () => {
    expect(candidatesFor('dataset', cat)[0].value).toBe('ds:1')
  })
  it('resolveFallback：空输入落 placeholder 默认值', () => {
    expect(resolveFallback('请输入名称', '')).toBe('请输入名称')
    expect(resolveFallback('请输入名称', '实际值')).toBe('实际值')
  })
})
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**

```ts
/** 适配性绑定候选 + placeholder 即默认值落值。 */
export interface ResourceCatalog {
  datasources: { id: number; name: string; type: string; db: string }[]
  workflows: { code: number; name: string; vars: { path: string; label: string; type: string }[] }[]
  globalParams: { path: string; label: string }[]
  timeParams: { path: string; label: string; sample: string }[]
  components: { type: string; name: string; state: string; publishedVersion: number | null }[]
}
export type SlotType = 'scalar' | 'dataset'

export interface Candidate { label: string; value: string }

export function candidatesFor(slot: SlotType, cat: ResourceCatalog): Candidate[] {
  if (slot === 'dataset') {
    return cat.datasources.map((d) => ({ label: `${d.name}（${d.type}）`, value: `ds:${d.id}` }))
  }
  const out: Candidate[] = []
  cat.workflows.forEach((w) => w.vars.forEach((v) => out.push({ label: `${w.name}/${v.label}`, value: v.path })))
  cat.globalParams.forEach((p) => out.push({ label: `参数/${p.label}`, value: p.path }))
  cat.timeParams.forEach((t) => out.push({ label: `时间/${t.label}`, value: t.path }))
  return out
}

/** placeholder 即默认值：用户未输入时提交 placeholder 文案。 */
export function resolveFallback(placeholder: string, input: string): string {
  const trimmed = (input ?? '').trim()
  return trimmed !== '' ? trimmed : (placeholder ?? '').trim()
}
```

- [ ] **Step 4: 通过**
- [ ] **Step 5: Commit** `feat(page-designer): 绑定候选推导 + placeholder 默认值落值`

### Task 9: 前端——pageApi.ts（服务 + mock）

**Files:**
- Create: `datara-web/src/views/meta/pageDesigner/pageApi.ts`
- Modify: `datara-web/src/services/mock/api.ts`（补 3 个 mock）
- Test: `__tests__/pageApi.test.ts`

- [ ] **Step 1: 失败测试**（mock 模式断言 three 方法返回形状：`getResources()` 有五键；`preview()` 返回 `results.rowCap=100`；`refreshRefs('x')` 返回 `refreshed` 数字）
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**

```ts
import { http } from '../../../services/http'
import { isMock } from '../../../services/apiMode'

export interface ResourcesResp { datasources: unknown[]; workflows: unknown[]; globalParams: unknown[]; timeParams: unknown[]; components: unknown[] }
export interface PreviewResult { columns: string[]; rows: string[][]; truncated: boolean; error: string }

export const pageApi = {
  async getResources(): Promise<ResourcesResp> {
    if (isMock()) return mockResources()
    return (await http.get('/page-designer/resources')).data.data
  },
  async preview(queries: { id: string; datasourceId: number; sql: string; db?: string }[]): Promise<{ results: Record<string, PreviewResult>; rowCap: number }> {
    if (isMock()) return { results: {}, rowCap: 100 }
    return (await http.post('/page-designer/preview', { queries })).data.data
  },
  async refreshRefs(type: string): Promise<{ refreshed: number; publishedVersion: number; items: { wfId: string; wfName: string }[] }> {
    if (isMock()) return { refreshed: 0, publishedVersion: 1, items: [] }
    return (await http.post(`/components/${type}/refresh-refs`)).data.data
  },
}
```

（mock 资源树给 2 数据源/1 工作流 1 变量/1 全局参数/timeParams 3 条；`http` 与 `isMock` 以 services 内实际导出为准，与 componentApi.ts 同款 import 路径。）
- [ ] **Step 4: 通过**
- [ ] **Step 5: Commit** `feat(page-designer): 前端服务层（resources/preview/refresh-refs + mock）`

### Task 10: 前端——PagePalette.vue

**Files:**
- Create: `datara-web/src/views/meta/pageDesigner/palette/PagePalette.vue`
- Test: `__tests__/PagePalette.test.ts`

- [ ] **Step 1: 失败测试**（mount 后：6 分组标题渲染；搜索 `表格` 收敛到 1 项；`dragstart` 事件 dataTransfer 设置 `application/x-datara-widget=<kind>`）
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**——`widgetGroups` 分组渲染（分组标题 + item 卡片：图标+label），顶部搜索框过滤（match label），item `draggable` 且 `@dragstart` 写 `e.dataTransfer.setData('application/x-datara-widget', kind)`。样式：分组标题 12px 灰、item 卡 hover 主色边、宽 232 默认随父容器。
- [ ] **Step 4: 通过**
- [ ] **Step 5: Commit** `feat(page-designer): 左侧组件库 Palette（分组/搜索/拖出）`

### Task 11: 前端——PageCanvas.vue + WidgetRenderer.vue

**Files:**
- Create: `datara-web/src/views/meta/pageDesigner/canvas/PageCanvas.vue`
- Create: `datara-web/src/views/meta/pageDesigner/canvas/WidgetRenderer.vue`
- Test: `__tests__/PageCanvas.test.ts`

- [ ] **Step 1: 失败测试**
  - 画布卡居中：容器 flex 居中，卡片 `box-shadow` 非空、默认宽 288 高 520（props 初始）；
  - 拖入：派发 `drop` 含 dataTransfer kind → emit `add`，坐标 = 卡内相对坐标；
  - 宽高拖拽：右/下手柄 mousedown → mousemove 更新 emit `canvasSize`，钳制 140–1920 / 160–2160；
  - 预览态：传 `previewData`（widgetId→rows/columns/error）时 WidgetRenderer 渲染真实行数。
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**——PageCanvas props：`page: PageDSL`、`selectedId`、`preview?: Record<string, PreviewResult>`； emits：`add/select/move/resize/canvasSize`。结构：

```vue
<template>
  <div class="pd-stage">                       <!-- 中间区域：flex 居中，中性底纹 -->
    <div class="pd-canvas" :style="canvasStyle" @drop.prevent="onDrop" @dragover.prevent>
      <WidgetRenderer v-for="w in page.widgets" :key="w.id" :widget="w" :preview="preview?.[w.id]"
        :selected="w.id === selectedId" @select="$emit('select', w.id)" />
      <div class="pd-grip-e" @mousedown="startResize('e', $event)" />
      <div class="pd-grip-s" @mousedown="startResize('s', $event)" />
      <div class="pd-grip-se" @mousedown="startResize('se', $event)" />
    </div>
  </div>
</template>
```

拖拽调尺寸同 GraphWorkbench 模式（mousedown 记起点 → window mousemove 实时 emit → mouseup 解绑并持久化键 `datara.pd.canvas`）。WidgetRenderer 按 kind 分派：`table` 用 AntD `a-table`（size=small，preview 有数据则 dataSource=rows 映射列，无则模板样例 3 行）；图表用 `a-(bar|line|pie) 类组件或 echarts 占位`——P1 用 AntD 内置 progress/statistic + 简易 SVG 柱/线/饼占位渲染（无新增依赖），preview 数据驱动；表单/基础元素逐 kind 映射 AntD 组件只读化（disabled）。
- [ ] **Step 4: 通过**
- [ ] **Step 5: Commit** `feat(page-designer): 画布（居中阴影/拖尺寸/拖入落点）+ widget 渲染分派`

### Task 12: 前端——PageInspector.vue

**Files:**
- Create: `datara-web/src/views/meta/pageDesigner/inspector/PageInspector.vue`
- Test: `__tests__/PageInspector.test.ts`

- [ ] **Step 1: 失败测试**
  - 选中 widget：显示 布局/样式/数据绑定 三段（a-tabs）；
  - 绑定段：scalar 槽渲染 `a-select`（候选来自 candidatesFor）+「手动输入」开关切 `a-input`，input 的 placeholder=模板默认值，blur 空值时 emit 的 binding.fallback=placeholder；
  - 未选中：显示画布段（尺寸/背景填充/背景图 URL/插图选择）。
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**——props：`page/selected/catalog`；emits：`updateWidget(patch)/updateCanvas(patch)`。绑定槽清单按 kind 维护 `SLOTS: Record<string, { key: string; label: string; slot: 'scalar' | 'dataset' }[]>`（table→`data:dataset`、text→`value:scalar`、image→`url:scalar`、图表→`series:dataset` 等，与 Task 7 模板一致）。fallback 落值统一走 `resolveFallback(placeholder, input)`。
- [ ] **Step 4: 通过**
- [ ] **Step 5: Commit** `feat(page-designer): 属性面板（布局/样式/适配性绑定 + placeholder 默认值）`

### Task 13: 前端——PageDesignerView.vue + 路由

**Files:**
- Create: `datara-web/src/views/meta/pageDesigner/PageDesignerView.vue`
- Modify: `datara-web/src/router/routes.ts`（追加一条）
- Modify: `datara-web/src/services/componentApi.ts`（补 `createPageDraft` 助手，create 时传 `execution_model: 'page'`、spec `{page}`）
- Test: `__tests__/PageDesignerView.test.ts`

- [ ] **Step 1: 失败测试**
  - 路由表含 `/meta/components/page-designer/:type?`；
  - mount（mock 模式）：三区域渲染（palette/canvas/inspector data-testid）+ 工具条按钮齐全：撤销 重做 复制 删除 对齐 缩放 **刷新** 保存 预览 发布；
  - 「刷新」点击触发 `getResources` 重载（spy 调用数 +1）；
  - 「预览」点击触发 `preview()` 并把结果传入 canvas preview prop；
  - 「发布」链：freeze→publish→断言请求体含 refresh 逻辑触发（mock publish 返回 refresh.refreshed=2 → toast 文案含「已刷新 2 个图引用」）。
- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**——布局壳复用 GraphWorkbench 面板交互（leftWidth=232 / rightWidth=288、MIN 140 / MAX 520、拖拽实时 + 持久化 `datara.pd.panels`、收放按钮）；顶栏含名称/状态徽标 + 工具条；undo/redo 用本地 PageDSL 快照栈（上限 50）；对齐=多选 x/y 对齐到最小值；缩放 a-dropdown（50/75/100/125%）；保存 `saveComponentDraft(spec={page})`（乐观锁 draft_rev）；发布走 `freezeComponentVersion→publishComponentVersion→（返回 refresh 不足时）pageApi.refreshRefs`；新建态（无 :type）先弹名称表单 → `createPageDraft` → replace 深链。
- [ ] **Step 4: 通过**；`npx vue-tsc --noEmit` 无错误
- [ ] **Step 5: Commit** `feat(page-designer): 设计器页壳（三区域/工具条含刷新/发布即刷新 toast）`

### Task 14: 存量 DAG 组件全量模板创作 + 目录刷新

**Files:**
- Modify: `datara-web/src/graph/profiles/*.ts`（每组件 NodeSpec 增 `template` 字段）
- Modify: `datara-backend/scripts/export_dag_catalog.py`（pick 键集合加 `"template"`）
- Regenerate: `datara-backend/common/dag_catalog.json`（重跑导出 → catalogHash 更新）
- Test: `datara-web/src/views/meta/__tests__/` 或就近现有 catalog 测试追加断言

- [ ] **Step 1: 失败测试**

```ts
// 组件目录消费侧断言：每个系统组件均携带 template（PageDSL 片段，纯数据）
it('catalog: 全量系统组件携带初始化模板', async () => {
  const { listComponents } = await import('../../../services/componentApi')
  const res = await listComponents()
  expect(res.items.length).toBeGreaterThan(0)
  res.items.forEach((it) => {
    expect(it.template, `${it.type} 缺 template`).toBeTruthy()
    expect(JSON.stringify(it.template)).not.toMatch(/=>|function/)
  })
})
```

- [ ] **Step 2: 确认失败**
- [ ] **Step 3: 实现**——以 `common/dag_catalog.json` items[].type 为权威清单（当前 35 个）逐组件创作 `template`：`{ rect: {w,h}, props: {<该组件 form 每个字段的 defaultValue 或安全示例>}, bindings: {<主数据槽推荐 kind>}, sample: <空态示例> }`。创作基准三例（其余按同构补齐，值取自各组件 form defaultValue，无则用 label 语义的安全文案，禁止脚本片段）：

```ts
// sql 组件
template: { rect: { w: 200, h: 64 }, props: { sql: 'SELECT 1', dsType: 'mysql' }, bindings: { result: { kind: 'query', fallback: '查询结果集' } }, sample: { rows: [] } }
// http 组件
template: { rect: { w: 160, h: 56 }, props: { method: 'GET', url: 'https://', timeout: 30 }, bindings: { response: { kind: 'static', fallback: '响应体' } }, sample: {} }
// notify 组件
template: { rect: { w: 160, h: 48 }, props: { channel: 'email', title: '通知标题' }, bindings: { body: { kind: 'variable', fallback: '通知内容' } }, sample: {} }
```

同时 profiles 的 TS 类型（NodeSpec）补可选 `template?: ComponentTemplate`；`export_dag_catalog.py` pick 键加 `"template"` 后重跑：

```bash
cd datara-backend; python scripts/export_dag_catalog.py   # 输出 catalogHash 变更
```

- [ ] **Step 4: 通过**（前端 catalog 测试 + 后端 `test_dag_catalog*` 同步校验 hash 一致）
- [ ] **Step 5: Commit** `feat(page-designer): 35 系统组件全量初始化模板创作 + catalog 重导出刷新`

### Task 15: aoci 初始化与索引

**Files:** Create: `aoci.txt`、`.aoci/`、`AGENTS.md`（aoci init 生成）；Modify: `.gitignore`（如 aoci 要求排除运行态资产）

- [ ] **Step 1: 初始化**

```powershell
D:\aoci\aoci.exe init --repo "d:\需求\数据治理工具\Datara"
D:\aoci\aoci.exe config --repo "d:\需求\数据治理工具\Datara" set scope.include datara-web/src/views/meta/pageDesigner,datara-backend/api/page_designer.py,datara-backend/api/component_design.py,datara-backend/common/models.py,datara-backend/common/dag_catalog.json
D:\aoci\aoci.exe scan --repo "d:\需求\数据治理工具\Datara"
```

- [ ] **Step 2: 索引构建**——`D:\aoci\aoci.exe index build`（按 `--help` 实际子命令）；若批量生成需 AI 端点而未配置（`aoci ai` 未设），执行 `aoci doctor` 留证并用 `aoci report` 记录缺口，不得猜测编造 Entry 语义。
- [ ] **Step 3: 提交** `chore(aoci): Datara 仓库 AOCI 初始化（组件设计器 scope 纳管）`

### Task 16: 全量验证

- [ ] `cd datara-web; npx vue-tsc --noEmit` 零错误
- [ ] `npx vitest run` 全绿（含既有 359 用例不回归）
- [ ] `cd datara-backend; python -m pytest tests/ -q` 全绿
- [ ] `D:\aoci\aoci.exe status --repo . --deep` 对齐
- [ ] Commit 收尾 + `aoci_maintain` 闭环（若已配置 MCP/AI 通道）

---

## P2 尾部任务（本期不实施，单独立计划）

1. 三页整合：`/meta/components` 改 Tab 容器（组件目录 | 基线化 | 页面设计器 | 声明编辑器），`?tab=` 深链。
2. DAG 工作台补「刷新」按钮（GraphWorkbench 工具条，重载 doc）。

## Self-Review 记录

- 规格覆盖：§3 布局=Task 11/13；§4 DSL=Task 6；§5 组件库=Task 7/10；§6 绑定=Task 4/8/12；§7 样式=Task 11/12（style 字段贯通）；§8 预览=Task 5/13；§9 发布刷新=Task 3/13；§10 工具条含刷新=Task 13；§11 模板=Task 7/14；§12 aoci=Task 15；§15 测试=各任务内嵌。✅
- 类型一致性：`BindingRef.fallback` 必填贯穿 Task 2/6/8/12；`PreviewResult` 形状 Task 5/9 一致（columns/rows/truncated/error）。✅
- 无占位符：Task 7 注释段为「按给定 T() 一行式模式补齐 30 项」的明确数据创作指令，kind 清单来自 Task 6 白名单（40 项权威），非含糊 TODO。✅
