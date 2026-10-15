# 组件设计器与 DAG 工作流编排工作台优化 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按方案 `docs/superpowers/specs/2026-10-05-workbench-optimization-design.md` 渐进增强组件设计工作台、DAG 编排工作台、双工作台协同与执行管线四大方向，全部新增字段向后兼容、存量功能零回归。

**Architecture:** 声明式元数据驱动（方案 A）。后端成为组件规格唯一真源（GET /components/spec + ETag），前端 spec 驱动渲染 + profile 兜底降级；连线校验采用 DataType 集合交集矩阵（前后端同一规则表 + 共享测试用例 JSON）；执行可视化走 SSE node_event 事件族（Redis Pub/Sub 源，t_run_event 落库回放）；断点续传采用节点签名 + 产物指纹的保守策略（宁多勿漏）。

**Tech Stack:** datara-web（Vue3 + Vite + TS + Pinia + @vue-flow/core 1.48 + Element Plus）/ datara-backend（FastAPI + SQLAlchemy + MySQL + Redis）。**不引入任何新框架依赖**。

**权威依据:** 本计划所有设计与验收标准均引自方案文档 §2–§12，任务验收一列标注对应章节。实现中若与方案冲突，以方案文档为准并回报用户。

---

## 0. 全局约定

### 0.1 环境与验证命令（每任务完成必须执行）

| 命令 | 工作目录 | 通过标准 |
|---|---|---|
| `npx vue-tsc --noEmit` | `datara-web` | 0 错误 |
| `npx vitest run` | `datara-web` | 全绿 |
| `npx vite build` | `datara-web` | 构建成功 |
| `python -m pytest tests/ -q` | `datara-backend` | 全绿（新增测试须先失败后通过） |

> 后端 Python 解释器注意：沙箱外使用 `C:\Program Files\Python312\python.exe`（Windows 环境已知约束）。

### 0.2 分支与提交规范

- 工作分支：`feat/workbench-opt`（从 `main` 最新提交切出）；每任务一组提交，消息格式 `feat|fix|test|perf(scope): 中文描述`。
- 硬约束延续（project_memory）：组件 markRaw、graphService 深拷贝契约、EventBus emit try/catch、ID max+1 生成、updatedAt 用 localTime、`/echo` 免鉴权等既有约定不得破坏。
- AOCI 禁用：本仓库禁止调用 aoci 工具（rc16 与 Volumes v1 baseline 冲突）。

### 0.3 灰度开关登记表（方案 §11.5，实现时统一挂 `localStorage` 键 `datara.flags`，运行时可改）

| 开关 | 默认 | 作用 | 任务 |
|---|---|---|---|
| `specFallback` | on | spec 服务不可用/组件缺失时回退 profile 渲染 | Task 5 |
| `sseSource` | polling | `pubsub` \| `polling` SSE 推送源切换 | Task 18 |
| `undoCommandStack` | off | 命令栈 vs 快照栈 | Task 22 |
| `checkpointEnabled` | off | 断点续传启用（先仅幂等任务类型） | Task 26 |
| `canvasOnlyRenderVisible` | on | 视口裁剪（异常时可关） | Task 13 |

### 0.4 任务粒度说明

- P0 各任务为「写测试 → 跑失败 → 实现 → 跑通过 → 提交」的完整 TDD 循环；核心纯函数给出完整代码，UI 任务给出关键代码与精确交互规格。
- P1/P2 任务粒度稍粗（文件 + 改动要点 + 验证 + 验收），执行时按同样 TDD 纪律展开。

---

## 1. 文件结构总览

**新增（datara-web）**
```
src/graph/model/portTypes.ts              # DataType + 交集矩阵 + portTypesMatch（纯函数）
src/graph/model/__tests__/portTypes.spec.ts
src/graph/model/__tests__/portTypeCases.json   # 前后端共享测试用例表（唯一真源）
src/graph/model/align.ts                  # 对齐/分布纯函数
src/graph/model/clipboard.ts              # 多选复制粘贴（ID max+1 重生成）
src/graph/model/docErrors.ts              # 校验错误聚合模型（节点/边/闸门三类）
src/stores/componentStore.ts              # 组件规格缓存（specMap/ETag/失效广播）
src/composables/useCanvasState.ts         # 画布视口/选中/浮窗持久化
src/components/graph/ErrorPanel.vue       # 错误聚合抽屉
src/components/graph/EdgeLegend.vue       # 边类型图例浮窗（P1）
tests/perf/canvas-bench.ts                # 200节点/400边 性能基准
```

**新增（datara-backend）**
```
api/component_spec.py                     # GET /api/v1/components/spec（ETag）
api/workflow_templates.py                 # 模板 CRUD/instantiate/versions（P1）
master/retry_classifier.py                # 错误分类纯函数（P1）
master/signature.py                       # 节点签名 hash（P1）
migrations/或 models 内新增表：t_run_event、t_node_artifact、t_wf_template
```

**修改（关键）**
```
datara-web/src/services/componentSpec.ts        # ComponentSpecV2 扩展（全部 optional）
datara-web/src/graph/workbench/GraphWorkbench.vue  # onConnect 类型校验/批量操作/undo优化/keep-alive
datara-web/src/graph/model/index.ts             # SpecPort 消费、docErrors 接入
datara-web/src/components/graph/DataNode.vue    # ports memo、运行态染色 class
datara-backend/api/component_design.py          # publish 升级策略/破坏性闸门/upgrade-refs
datara-backend/api/graph_rules.py               # 类型交集复检（同规则）
datara-backend/api/instance.py                  # SSE node_event + last-event-id 补发
datara-backend/master/engine.py                 # 事件钩子→Redis Pub/Sub、重试分类、签名比对
```

---

## 2. 批次 P0-1（方向一：组件规格服务与 8 要素体系）

### Task 1: DataType 类型体系与 portTypes.ts 交集规则（前后端同规则的基石）

**Files:**
- Create: `datara-web/src/graph/model/portTypes.ts`
- Create: `datara-web/src/graph/model/__tests__/portTypes.spec.ts`
- Create: `datara-web/src/graph/model/__tests__/portTypeCases.json`

- [ ] **Step 1: 写共享测试用例表** `portTypeCases.json`（前后端 pytest 与 vitest 各自加载同一份，固化方案 §3.1 行为）：

```json
{
  "comment": "src/dst/expected 三元组；any 恒匹配，none 恒不匹配，其余查兼容矩阵",
  "cases": [
    { "src": "any",      "dst": "stream", "expected": true },
    { "src": "stream",   "dst": "any",    "expected": true },
    { "src": "none",     "dst": "table",  "expected": false },
    { "src": "table",    "dst": "none",   "expected": false },
    { "src": "table",    "dst": "table",  "expected": true },
    { "src": "dataset",  "dst": "table",  "expected": true },
    { "src": "dataset",  "dst": "dataset", "expected": true },
    { "src": "stream",   "dst": "dataset", "expected": false },
    { "src": "json",     "dst": "string", "expected": true },
    { "src": "string",   "dst": "json",   "expected": false },
    { "src": "number",   "dst": "string", "expected": true },
    { "src": "file",     "dst": "table",  "expected": false },
    { "src": "stream",   "dst": "stream", "expected": true },
    { "src": "boolean",  "dst": "number", "expected": false }
  ]
}
```

- [ ] **Step 2: 写失败测试** `portTypes.spec.ts`：

```ts
import { describe, it, expect } from 'vitest'
import { portTypesMatch, type DataType } from '../portTypes'
import cases from './portTypeCases.json'

describe('portTypesMatch（方案 §3.1 集合交集规则）', () => {
  it.each(cases.cases as { src: DataType; dst: DataType; expected: boolean }[])(
    '$src -> $dst = $expected', ({ src, dst, expected }) => {
      expect(portTypesMatch(src, dst)).toBe(expected)
    })
  it('未知类型按 any 处理（旧组件未声明向后兼容）', () => {
    expect(portTypesMatch(undefined as never, 'table')).toBe(true)
    expect(portTypesMatch('table', undefined as never)).toBe(true)
  })
})
```

- [ ] **Step 3: 跑测试确认失败**：`npx vitest run src/graph/model/__tests__/portTypes.spec.ts` → FAIL（模块不存在）。

- [ ] **Step 4: 实现** `portTypes.ts`：

```ts
/** DataType 体系与端口类型交集匹配（方案 §2.2/§3.1）。纯函数，禁止依赖任何 store/service。 */
export type DataType =
  | 'any' | 'string' | 'number' | 'boolean' | 'json'
  | 'table' | 'dataset' | 'file' | 'stream' | 'none'

/** 兼容矩阵：键=源类型，值=可流入的目标类型集合（dataset→table 可、stream→dataset 不可） */
export const TYPE_COMPAT: Record<Exclude<DataType, 'any' | 'none'>, DataType[]> = {
  string:  ['string', 'json'],
  number:  ['number', 'string'],
  boolean: ['boolean'],
  json:    ['json', 'string'],
  table:   ['table', 'dataset', 'json'],
  dataset: ['dataset', 'table', 'json'],
  file:    ['file', 'json'],
  stream:  ['stream'],
}

/** 交集匹配：任一端 any 恒真；任一端 none 恒假；未知类型视为 any（存量旧组件未声明 type） */
export function portTypesMatch(src?: string | null, dst?: string | null): boolean {
  if (!src || !dst || src === 'any' || dst === 'any') return true
  if (src === 'none' || dst === 'none') return false
  const row = (TYPE_COMPAT as Record<string, DataType[] | undefined>)[src]
  return row ? row.includes(dst) : true
}
```

- [ ] **Step 5: 跑测试通过**（同 Step 3 命令 → PASS）；提交：

```bash
git add src/graph/model/portTypes.ts src/graph/model/__tests__/
git commit -m "feat(graph): DataType 类型体系与端口交集匹配纯函数（方案§3.1）"
```

### Task 2: ComponentSpecV2 声明式 schema 扩展（全部 optional 向后兼容）

**Files:**
- Modify: `datara-web/src/services/componentSpec.ts:97-236`（SpecPort/SpecField/ComponentSpec/normalizeSpec 区域）
- Test: `datara-web/src/services/__tests__/componentSpec.v2.spec.ts`（新建）

- [ ] **Step 1: 写失败测试**——重点断言：旧 spec 数据进来字段齐全且新字段为 undefined；新字段能往返：

```ts
import { describe, it, expect } from 'vitest'
import { normalizeSpec } from '../componentSpec'

describe('ComponentSpecV2 normalizeSpec 向后兼容（方案§2.2）', () => {
  it('旧格式 spec：新字段可选不强制，原字段不变', () => {
    const s = normalizeSpec({ icon: 'db', color: '#333', summary: '旧组件', fields: [] })
    expect(s.icon).toBe('db')
    expect(s.outputs).toBeUndefined()
    expect(s.behaviors).toBeUndefined()
    expect(s.extensions).toBeUndefined()
    expect(s.specVersion).toBeUndefined()
  })
  it('新格式 spec：outputs/behaviors/extensions/aliases/category 往返保留', () => {
    const s = normalizeSpec({
      icon: 'sql', color: '#0891b2', summary: 'SQL 执行', category: '批处理与同步/数据源',
      aliases: ['sql', '脚本'], description: '**详细**说明',
      outputs: [{ name: 'result', type: 'table', desc: '结果表' }],
      fields: [{ key: 'sql', label: 'SQL', uiType: 'code', required: true, desc: '', layer: 'required' }],
      behaviors: { prefillFromUpstream: [{ field: 'table', from: 'input.table' }] },
      extensions: { hiddenInputs: ['tenantId', 'runId'], capabilities: { testable: true, previewLimit: 100 } },
      specVersion: '1.1',
      ports: { inputs: [{ name: 'in', type: 'dataset' }], outputs: [{ name: 'out', type: 'table' }] },
    })
    expect(s.category).toBe('批处理与同步/数据源')
    expect(s.aliases).toEqual(['sql', '脚本'])
    expect(s.outputs?.[0].type).toBe('table')
    expect(s.fields?.[0].layer).toBe('required')
    expect(s.behaviors?.prefillFromUpstream?.[0].from).toBe('input.table')
    expect(s.extensions?.hiddenInputs).toEqual(['tenantId', 'runId'])
  })
  it('outputs.type 非法值归一为 any（不炸渲染）', () => {
    const s = normalizeSpec({ outputs: [{ name: 'x', type: 'oops' }] })
    expect(s.outputs?.[0].type).toBe('any')
  })
})
```

- [ ] **Step 2: 跑失败**（`npx vitest run src/services/__tests__/componentSpec.v2.spec.ts` → FAIL）。

- [ ] **Step 3: 实现**——在 `componentSpec.ts` 现有接口上追加（不改既有字段语义）：

```ts
import type { DataType } from '../graph/model/portTypes'

export interface SpecField {
  key: string; label: string; uiType: SpecUiType; required: boolean
  default?: unknown; desc: string
  options?: { label: string; value: string | number }[]
  showIf?: unknown
  /** V2 新增：三层归属（缺省视为 required，向后兼容） */
  layer?: 'required' | 'optional' | 'hidden'
  /** V2 新增：声明式控件选项 */
  optionsEx?: { min?: number; max?: number; step?: number; placeholder?: string
               multiline?: boolean; remote?: string }
}

export interface ComponentSpec {
  icon: string; color: string; summary: string
  ports: { inputs: SpecPort[]; outputs: SpecPort[] }
  fields: SpecField[]; dropPolicy: SpecDropPolicy; paletteVisible: boolean
  /* ── V2（方案§2.2，全部 optional）── */
  displayName?: string; aliases?: string[]
  description?: string; category?: string; docUrl?: string
  outputs?: { name: string; type: DataType; desc?: string }[]
  badge?: { key: string; colorMap: Record<string, string> }
  behaviors?: {
    onChange?: { field: string; action: 'refreshOptions'|'resetFields'|'prefill'; target?: string[]; remote?: string }[]
    prefillFromUpstream?: { field: string; from: 'input.table'|'input.columns'|'input.datasource' }[]
    pick?: { field: string; picker: 'table'|'column'|'cron'|'sshHost' }[]
  }
  extensions?: {
    hiddenInputs?: ('tenantId'|'runId'|'nodeId'|'workflowId')[]
    capabilities?: { testable?: boolean; previewLimit?: number }
  }
  specVersion?: string
  initTemplate?: Record<string, unknown>
}
```

`normalizeSpec` 内为每个新字段写对应的 `norm*` 归一函数（模式照抄现有 `normField`：未知值兜底、非法枚举回落）。约束：`capabilities.previewLimit` 归一时 `Math.min(v, 100)`（方案硬约束 ≤100）。

- [ ] **Step 4: 跑通过**；提交 `feat(spec): ComponentSpecV2 声明式 schema 扩展（方案§2.2，全字段 optional）`。

### Task 3: 后端 GET /api/v1/components/spec 统一规格下发（ETag）

**Files:**
- Create: `datara-backend/api/component_spec.py`
- Modify: `datara-backend/api/__init__.py`（或主 router 注册处，参照 component_design.py 的注册方式）
- Test: `datara-backend/tests/test_component_spec.py`

- [ ] **Step 1: 写失败测试**（参照 `tests/test_component_design.py` 的 fixture 风格，走 conftest 的 app/client）：

```python
def test_spec_lists_published_components(client, seeded_published_component):
    r = client.get("/api/v1/components/spec")
    assert r.status_code == 200
    body = r.json()
    items = body["items"]
    assert any(i["type"] == seeded_published_component for i in items)
    one = next(i for i in items if i["type"] == seeded_published_component)
    # 8 要素骨架完整（缺失项显式 None 而非缺键，方案§2.1 可审计要求）
    for k in ("identity", "description", "inputs", "outputs", "visual", "behaviors", "dropPolicy", "extensions"):
        assert k in one

def test_spec_etag_304(client):
    r1 = client.get("/api/v1/components/spec")
    etag = r1.headers["ETag"]
    r2 = client.get("/api/v1/components/spec", headers={"If-None-Match": etag})
    assert r2.status_code == 304

def test_spec_offline_component_excluded(client, seeded_published_component):
    client.post(f"/api/v1/components/{seeded_published_component}/offline")
    r = client.get("/api/v1/components/spec")
    assert all(i["type"] != seeded_published_component for i in r.json()["items"])
```

- [ ] **Step 2: 跑失败**：`python -m pytest tests/test_component_spec.py -q` → FAIL。

- [ ] **Step 3: 实现** `component_spec.py`——聚合 `t_component`（published 且未删除）× `t_component_version` 最新发布版 `spec_json`，映射为 4 组结构后下发；ETag = `sha256(响应体)`：

```python
import hashlib, json
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from models import SessionLocal, Component, ComponentVersion   # 按现有 models 导入路径

router = APIRouter(prefix="/api/v1/components", tags=["component-spec"])

def _build_spec_payload(db) -> list[dict]:
    """published 组件 × 最新发布版本 spec_json → 8要素4组结构（方案§2.1/§6.1#1）"""
    rows = (db.query(Component, ComponentVersion)
              .join(ComponentVersion, ComponentVersion.component_id == Component.id)
              .filter(Component.status == "published")
              .order_by(ComponentVersion.version.desc()).all())
    seen, items = set(), []
    for comp, ver in rows:
        if comp.type_name in seen:
            continue
        seen.add(comp.type_name)
        spec = json.loads(ver.spec_json or "{}")
        items.append({
            "type": comp.type_name,
            "identity":  {"type": comp.type_name, "displayName": comp.name,
                          "aliases": spec.get("aliases", [])},
            "description": {"summary": spec.get("summary", ""), "description": spec.get("description"),
                            "category": spec.get("category"), "docUrl": spec.get("docUrl")},
            "inputs":    spec.get("fields", []),
            "outputs":   spec.get("outputs", []),
            "visual":    {"icon": spec.get("icon", ""), "color": spec.get("color"),
                          "shape": spec.get("shape", "default"), "badge": spec.get("badge")},
            "behaviors": spec.get("behaviors"),
            "dropPolicy": spec.get("dropPolicy"),
            "extensions": spec.get("extensions"),
            "specVersion": spec.get("specVersion"),
            "ports": spec.get("ports"),
        })
    return items

@router.get("/spec", summary="全量已发布组件规格（8要素；ETag 缓存）")
def get_components_spec(request: Request):
    db = SessionLocal()
    try:
        body = json.dumps({"items": _build_spec_payload(db)}, ensure_ascii=False, default=str)
        etag = '"' + hashlib.sha256(body.encode()).hexdigest()[:32] + '"'
        if request.headers.get("if-none-match") == etag:
            return JSONResponse(status_code=304, headers={"ETag": etag})
        return JSONResponse(content=json.loads(body), headers={"ETag": etag})
    finally:
        db.close()
```

主应用 `include_router` 注册（跟随 component_design.py 现有注册位置）。`SessionLocal`/模型类名以 `datara-backend/models` 实际导出为准，实现时先读现有文件再落笔。

- [ ] **Step 4: 跑通过**；提交 `feat(api): GET /components/spec 统一规格下发（ETag，方案§2.3）`。

### Task 4: componentStore（前端规格缓存与失效广播）

**Files:**
- Create: `datara-web/src/stores/componentStore.ts`
- Modify: `datara-web/src/services/componentApi.ts`（新增 `fetchComponentSpec(): Promise<{ items, etag }>`，GET 时带 `If-None-Match`，304 返回 null）
- Test: `datara-web/src/stores/__tests__/componentStore.spec.ts`

- [ ] **Step 1: 失败测试**（mock componentApi）：

```ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useComponentStore } from '../componentStore'
import * as api from '../../services/componentApi'

vi.mock('../../services/componentApi', () => ({
  fetchComponentSpec: vi.fn(),
}))

describe('componentStore（方案§2.3/§7.2）', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('ensureSpecs 拉取并构建 specMap', async () => {
    vi.mocked(api.fetchComponentSpec).mockResolvedValue({
      etag: 'W/"abc"', items: [{ type: 'sql_execute', /* …8要素结构… */ } as never],
    })
    const s = useComponentStore()
    await s.ensureSpecs()
    expect(s.specMap.get('sql_execute')).toBeTruthy()
    expect(s.loaded).toBe(true)
  })
  it('ETag 304：不重复解析，沿用缓存', async () => {
    const s = useComponentStore()
    vi.mocked(api.fetchComponentSpec).mockResolvedValueOnce({ etag: 'W/"abc"', items: [] as never[] })
    await s.ensureSpecs()
    vi.mocked(api.fetchComponentSpec).mockResolvedValueOnce(null as never)
    await s.invalidate()
    expect(vi.mocked(api.fetchComponentSpec)).toHaveBeenCalledTimes(2)
    expect(s.loaded).toBe(true)
  })
  it('服务异常进入降级态 degraded=true（触发 profile 兜底）', async () => {
    vi.mocked(api.fetchComponentSpec).mockRejectedValue(new Error('net'))
    const s = useComponentStore()
    await s.ensureSpecs()
    expect(s.degraded).toBe(true)
  })
})
```

- [ ] **Step 2: 跑失败**。

- [ ] **Step 3: 实现** `componentStore.ts`：

```ts
import { defineStore } from 'pinia'
import { fetchComponentSpec } from '../services/componentApi'
import { normalizeSpec, type ComponentSpec } from '../services/componentSpec'
import { bus } from '../services/eventBus'

export const useComponentStore = defineStore('component', {
  state: () => ({
    specMap: new Map<string, ComponentSpec>(),   // type → 归一化 spec
    etag: '',
    loaded: false,
    loading: false,
    degraded: false,                             // true = 走 profile 兜底（方案§1.4 渐进可回退）
  }),
  actions: {
    async ensureSpecs(force = false) {
      if (this.loaded && !force) return
      if (this.loading) return
      this.loading = true
      try {
        const res = await fetchComponentSpec(this.etag || undefined)
        if (res) {
          this.specMap = new Map(res.items.map((it) => {
            const spec = normalizeSpec(it)
            return [spec.type ?? (it as { type: string }).type, spec]
          }) as [string, ComponentSpec][])
          this.etag = res.etag
          this.degraded = false
        }
        this.loaded = true
      } catch { this.degraded = true }   // 方案§R1：服务不可用必须能整体降级
      finally { this.loading = false }
    },
    /** 发布/回滚/离线事件触发失效（方案§4.4 失效闭环） */
    async invalidate() { await this.ensureSpecs(true) },
    getSpec(type: string): ComponentSpec | undefined { return this.specMap.get(type) },
  },
})
// 失效广播接线（app 入口处调用一次 setupComponentStoreBus()）：
export function setupComponentStoreBus() {
  const s = useComponentStore()
  bus.on('component:published', () => { void s.invalidate() })
  bus.on('component:rolled-back', () => { void s.invalidate() })
  bus.on('component:offline', () => { void s.invalidate() })
}
```

`componentApi.ts` 新增：

```ts
export async function fetchComponentSpec(ifNoneMatch?: string):
  Promise<{ etag: string; items: Record<string, unknown>[] } | null> {
  const headers: Record<string, string> = {}
  if (ifNoneMatch) headers['If-None-Match'] = ifNoneMatch
  const r = await http.get('/api/v1/components/spec', { headers })
  if (r.status === 304) return null
  return { etag: (r.headers.etag as string) ?? '', items: r.data.items }
}
```

（`http` 为 componentApi.ts 现有请求封装，保持一致。）

- [ ] **Step 4: 跑通过**；提交 `feat(store): componentStore 规格缓存 + ETag + 失效广播（方案§2.3）`。

### Task 5: spec 驱动渲染 + profile 兜底降级（双源归一切换期）

**Files:**
- Modify: `datara-web/src/graph/workbench/GraphWorkbench.vue`（palette 分类树、nodeTypes 解析入口）
- Modify: `datara-web/src/graph/model/index.ts`（新增 `resolveNodeSchema(type, profile, specMap)` 纯函数）
- Modify: `datara-web/src/views/DagDesignerView.vue`（或各视角视图初始化处，调用 `ensureSpecs`）
- Test: `datara-web/src/graph/model/__tests__/resolveNodeSchema.spec.ts`

- [ ] **Step 1: 失败测试**（核心：spec 优先、缺失回退 profile、开关可控）：

```ts
import { describe, it, expect } from 'vitest'
import { resolveNodeSchema } from '../index'

const profileSchema = { label: 'profile 版', fields: [], outputs: [{ name: 'o', type: 'any' }] }
const profile = { nodeTypes: { sql: profileSchema } }

describe('resolveNodeSchema（方案§2.3 spec 驱动 + profile 兜底）', () => {
  const spec = { label: 'spec 版', fields: [{ key: 'a', label: 'A', uiType: 'text', required: true, desc: '' }],
                 outputs: [{ name: 'o', type: 'table' }] }
  it('spec 存在 → spec 驱动', () => {
    expect(resolveNodeSchema('sql', profile, new Map([['sql', spec]]), true)).toBe(spec)
  })
  it('spec 缺失 → profile 兜底', () => {
    expect(resolveNodeSchema('sql', profile, new Map(), true)).toBe(profileSchema)
  })
  it('degraded=true → 强制 profile', () => {
    expect(resolveNodeSchema('sql', profile, new Map([['sql', spec]]), false)).toBe(profileSchema)
  })
  it('profile 也无该类型 → undefined（不抛错）', () => {
    expect(resolveNodeSchema('ghost', profile, new Map(), true)).toBeUndefined()
  })
})
```

- [ ] **Step 2: 跑失败**。

- [ ] **Step 3: 实现** `graph/model/index.ts` 追加：

```ts
import type { ComponentSpec } from '../../services/componentSpec'

/** spec 驱动渲染入口（方案§2.3）：spec 优先，缺失或降级态回退 profile（渐进切换，R1 风险对策） */
export function resolveNodeSchema(
  type: string,
  profile: { nodeTypes: Record<string, unknown> },
  specMap: Map<string, ComponentSpec> | undefined,
  specEnabled: boolean,
): unknown {
  if (specEnabled && specMap) {
    const s = specMap.get(type)
    if (s) return s
  }
  return (profile.nodeTypes as Record<string, unknown>)[type]
}
```

GraphWorkbench 侧：`props.profile.nodeTypes[...]` 的读取点收敛为经过 `resolveNodeSchema`（palette 构建、DataNode schema 查找、Inspector 表单源三处）；`specEnabled = componentStore.loaded && !componentStore.degraded`。**不做一次性替换**：保持两源并存，`ComponentStats.consistencyErrors` 继续对账（方案§2.3），归零前不删 profile。

- [ ] **Step 4: 跑通过 + 全量验证**（vue-tsc / vitest run / vite build）；浏览器冒烟：5174 打开 DAG 工作台，正常/降级（DevTools Network 把 `/components/spec` block 掉刷新）两态均无白屏、palette 完整。提交 `feat(graph): spec 驱动渲染 + profile 兜底降级（方案§2.3，R1 对策）`。

### Task 6: 设计器 8 要素 4 组页签表单 + 完整度徽标

**Files:**
- Modify: `datara-web/src/views/ComponentDesignerView.vue`（fields/page 双模式表单区，改造为页签结构）
- Create: `datara-web/src/components/designer/SpecFormIdentity.vue` / `SpecFormContract.vue` / `SpecFormVisual.vue` / `SpecFormExtension.vue`（4 组页签子组件）
- Create: `datara-web/src/components/designer/SpecCompletenessBadge.vue`
- Test: `datara-web/src/components/designer/__tests__/specCompleteness.spec.ts`

- [ ] **Step 1: 完整度纯函数失败测试**（方案§2.1 裁剪规则）：

```ts
import { describe, it, expect } from 'vitest'
import { specCompleteness } from '../specCompleteness'

describe('specCompleteness（按裁剪规则判定应填项）', () => {
  it('拖入组件最小集：身份+契约required+视觉 = 3/4 组齐即视为可落库', () => {
    const r = specCompleteness({ icon: 'x', color: '#000', summary: 's', fields: [{ key: 'a', required: true }] })
    expect(r.canDrop).toBe(true)
    expect(r.missing).toContain('outputs')   // 有下游产出的组件必填，此处标记缺失但不阻断
  })
  it('逻辑组件（start/end/conditions）outputs 可省略 → missing 不含 outputs', () => {
    const r = specCompleteness({ icon: 'x', summary: 's', fields: [], logical: true })
    expect(r.missing).not.toContain('outputs')
  })
  it('身份组缺失 → canDrop=false', () => {
    expect(specCompleteness({ fields: [] }).canDrop).toBe(false)
  })
})
```

- [ ] **Step 2: 跑失败**。

- [ ] **Step 3: 实现** `src/components/designer/specCompleteness.ts`：

```ts
export interface CompletenessResult {
  groups: { id: 'identity'|'contract'|'visual'|'extension'; done: boolean; missing: string[] }[]
  missing: string[]
  canDrop: boolean   // 身份组 + 契约组 required + 视觉 = 拖入落库最低门槛（方案§2.1）
}
export function specCompleteness(spec: {
  type?: string; summary?: string; icon?: string; color?: string
  fields?: { required?: boolean; layer?: string }[]
  outputs?: unknown[]; logical?: boolean
}): CompletenessResult {
  const identityMissing = [!spec.type && 'type', !spec.summary && 'summary'].filter(Boolean) as string[]
  const reqFields = (spec.fields ?? []).filter((f) => f.required || f.layer === 'required')
  const contractMissing = [
    reqFields.length === 0 && 'fields.required',
    !spec.logical && !(spec.outputs && spec.outputs.length) && 'outputs',
  ].filter(Boolean) as string[]
  const visualMissing = [!spec.icon && 'icon'].filter(Boolean) as string[]
  const groups = [
    { id: 'identity' as const, done: identityMissing.length === 0, missing: identityMissing },
    { id: 'contract' as const, done: contractMissing.length === 0, missing: contractMissing },
    { id: 'visual' as const, done: visualMissing.length === 0, missing: visualMissing },
    { id: 'extension' as const, done: true, missing: [] },   // 扩展组全 optional，默认完成
  ]
  const missing = groups.flatMap((g) => g.missing)
  return { groups, missing, canDrop: identityMissing.length === 0 && visualMissing.length === 0 }
}
```

- [ ] **Step 4: 设计器表单改造**——现有表单区改为 `el-tabs` 四页签（身份/契约/表现/扩展），每页签底部固定徽标 `SpecCompletenessBadge`（显示 `8/8` 或缺项黄色，点击缺项直达对应页签，方案§8.3）。**输出定义编辑器**（契约页签内）：`outputs` 行编辑（name/type 下拉=DataType 九值/desc），type 下拉直接消费 `portTypes.ts` 导出的 `TYPE_COMPAT` 键集合。交互行为编辑器（表现页签）：`behaviors.prefillFromUpstream/pick/onChange` 行编辑，from/picker 枚举与方案§2.2 一致。**约束**：拖入弹窗与 Inspector 共用此表单渲染组件（project_memory 既有约束），表单数据源唯一为 ComponentSpecV2。

- [ ] **Step 5: 跑通过 + 浏览器实测**（新建组件走完 4 页签保存→冻结→发布全链路，截图留档）；提交 `feat(designer): 8要素4组页签表单+完整度徽标+输出定义编辑（方案§2.1/§2.6）`。

### Task 7: 破坏性变更闸门 + fieldMapping（发布扩展）

**Files:**
- Modify: `datara-backend/api/component_design.py:757`（publish_version 请求体与闸门检查）
- Modify: `datara-web/src/views/ComponentHubView.vue`（或发布弹窗所在组件，发布请求体新增 upgradeStrategy）
- Test: `datara-backend/tests/test_publish_breaking_change.py`

- [ ] **Step 1: 失败测试**：

```python
def test_major_change_requires_field_mapping(client, published_component_with_v1):
    """删字段=major（方案§2.4），未带 fieldMapping 且未确认不迁移 → 422 拦截"""
    r = client.post(f"/api/v1/components/{published_component_with_v1}/publish",
                    json={"draft_rev": 1, "upgrade_strategy": "auto"})
    assert r.status_code == 422
    assert "breaking" in r.json()["detail"]

def test_major_change_with_confirm_passes(client, published_component_with_v1):
    r = client.post(f"/api/v1/components/{published_component_with_v1}/publish",
                    json={"draft_rev": 1, "upgrade_strategy": "auto",
                          "field_mapping": None, "breaking_confirmed": True})
    assert r.status_code == 200

def test_minor_change_no_gate(client, published_component_minor_change):
    assert client.post(f"/api/v1/components/{published_component_minor_change}/publish",
                       json={"draft_rev": 1, "upgrade_strategy": "auto"}).status_code == 200
```

- [ ] **Step 2: 跑失败**。

- [ ] **Step 3: 实现**——`component_design.py` 新增纯函数并挂入 publish 闸门（在现有八项闸门之后追加第 9 项）：

```python
def _classify_spec_change(old: dict, new: dict) -> dict:
    """specVersion 语义化判定（方案§2.4）：minor=新增/可选层/desc；major=删除字段/改 uiType/删输出/required 收紧"""
    old_f = {f["key"]: f for f in old.get("fields", []) if isinstance(f, dict)}
    new_f = {f["key"]: f for f in new.get("fields", []) if isinstance(f, dict)}
    removed = sorted(set(old_f) - set(new_f))
    ui_changed = [k for k in set(old_f) & set(new_f) if old_f[k].get("uiType") != new_f[k].get("uiType")]
    tightened = [k for k in set(old_f) & set(new_f)
                 if old_f[k].get("required") and not new_f[k].get("required")]
    old_out = {o.get("name") for o in old.get("outputs", []) if isinstance(o, dict)}
    new_out = {o.get("name") for o in new.get("outputs", []) if isinstance(o, dict)}
    removed_out = sorted(old_out - new_out)
    breaking = bool(removed or ui_changed or tightened or removed_out)
    return {"major": breaking,
            "changes": {"removed": removed, "uiChanged": ui_changed,
                        "requiredTightened": tightened, "outputsRemoved": removed_out}}

# publish_version 内、闸门链追加：
cls_ = _classify_spec_change(old_spec_json, new_spec_json)
if cls_["major"] and not body.breaking_confirmed:
    raise HTTPException(422, detail={"code": "breaking_change",
                                     "changes": cls_["changes"],
                                     "hint": "需 breaking_confirmed=true 或提供 field_mapping"})
```

请求体模型扩展（现有 PublishBody 类）：`upgrade_strategy: str = 'auto'`（`auto|manual|pin`）、`field_mapping: dict | None = None`、`breaking_confirmed: bool = False`。升级动作本身在 Task 16 实现，本任务只落闸门与数据结构。所有 major 决策写 `t_component_log`（复用现有 log 写入函数）。

- [ ] **Step 4: 跑通过 + 全量验证**；前端发布弹窗补 `breaking_confirmed` 确认框（检测到 422 `breaking_change` 时弹出变更清单 + 「确认发布 / 取消」）；提交 `feat(publish): 破坏性变更闸门+fieldMapping 数据结构（方案§2.4，P0-1c）`。

---

## 3. 批次 P0-2（方向二：类型化连线、错误定位、批量操作、性能）

### Task 8: isValidConnection 实时校验 + onConnect 类型检查

**Files:**
- Modify: `datara-web/src/graph/workbench/GraphWorkbench.vue:786-820`（onConnect）及 `<VueFlow>` 绑定处（:1384 附近加 `:is-valid-connection`）
- Test: `datara-web/src/graph/workbench/__tests__/onConnectGuard.spec.ts`（抽出可测的守卫纯函数）

- [ ] **Step 1: 抽守卫纯函数并写失败测试**（放 `graph/model/connectionGuard.ts`）：

```ts
import { describe, it, expect } from 'vitest'
import { connectionRejectReason } from '../connectionGuard'
import type { GraphDocument } from '../index'

const doc = (edges: [string, string][] = []): GraphDocument => ({
  nodes: [ { id: 'a', type: 'sql', position: { x: 0, y: 0 }, data: {} },
           { id: 'b', type: 'sink', position: { x: 0, y: 0 }, data: {} } ],
  edges: edges.map(([s, t]) => ({ id: `e_${s}_${t}`, source: s, target: t, kind: 'dependency' })),
} as unknown as GraphDocument)

describe('connectionRejectReason（方案§3.1 四道闸）', () => {
  it('自连拒绝', () => expect(connectionRejectReason(doc(), { source: 'a', target: 'a' })).toContain('自连'))
  it('重复边拒绝', () => {
    const d = doc([['a', 'b']])
    expect(connectionRejectReason(d, { source: 'a', target: 'b' })).toContain('已存在')
  })
  it('成环拒绝', () => {
    const d = doc([['b', 'a']])
    expect(connectionRejectReason(d, { source: 'a', target: 'b' })).toContain('环')
  })
  it('类型不匹配拒绝（src=stream dst=file）', () => {
    const d = doc() as never as GraphDocument & { portTypes?: unknown }
    expect(connectionRejectReason(d, { source: 'a', target: 'b' },
      { a: 'stream', b: 'file' })).toContain('类型')
  })
  it('全部通过返回 null', () => {
    expect(connectionRejectReason(doc(), { source: 'a', target: 'b' },
      { a: 'table', b: 'dataset' })).toBeNull()
  })
})
```

- [ ] **Step 2: 跑失败**。

- [ ] **Step 3: 实现** `graph/model/connectionGuard.ts`：

```ts
import { detectCycle, type GraphDocument } from './index'
import { portTypesMatch } from './portTypes'

export interface ConnLike { source: string; target: string; sourceHandle?: string | null; targetHandle?: string | null }

/** 连线四道闸（方案§3.1）：自连→重复→环→类型交集。返回 null=放行，否则返回中文原因。 */
export function connectionRejectReason(
  doc: GraphDocument,
  conn: ConnLike,
  portTypes?: Record<string, string>,   // nodeId → 源/目标端口 DataType（由调用方解析 ports 得出）
): string | null {
  if (conn.source === conn.target) return '不允许自连'
  const dup = doc.edges.some((e) => e.source === conn.source && e.target === conn.target
    && (e.sourceHandle ?? '') === (conn.sourceHandle ?? ''))
  if (dup) return '依赖边已存在'
  const next: GraphDocument = { ...doc, edges: [...doc.edges, {
    id: 'tmp', source: conn.source, target: conn.target,
  } as never] }
  if (detectCycle(next).length) return '该连接将形成环（DAG 不允许成环）'
  if (portTypes) {
    const st = portTypes[conn.source], dt = portTypes[conn.target]
    if (!portTypesMatch(st, dt)) return `类型不匹配：源 ${st ?? 'any'} → 目标 ${dt ?? 'any'}`
  }
  return null
}
```

- [ ] **Step 4: GraphWorkbench 接线**——onConnect 现有四段内联判断（786-813 行：自连/dup/detectCycle）收敛为调用 `connectionRejectReason`（行为不变、追加类型道）；端口类型解析：`srcSchema?.ports?.(node.data)?.outputs` 与 `dstSchema.ports.inputs` 按 handle 匹配 `SpecPort.type`（**SpecPort.type 首次接入消费链路**，方案§1.2 差距②）；`<VueFlow>` 增加 `:is-valid-connection="onIsValidConnection"`（内部调 `portTypesMatch`，拖线实时预判）+ 被拒时 `ElMessage.warning(reason)` + 源/目标 DOM 端口加 `.port-flash-red` class 1s（CSS keyframes，方案§8.2）。保存闸门处（现有 validateDoc 调用点）追加全图边类型复检，错误进入 Task 10 的错误聚合模型。

- [ ] **Step 5: 跑通过 + 浏览器实测**（拖线不匹配被实时拦截 + toast；截图）；提交 `feat(dag): 类型化连线四道闸 + isValidConnection 实时校验（方案§3.1）`。

### Task 9: 后端 graph_rules 同规则复检 + 共享用例表

**Files:**
- Modify: `datara-backend/api/graph_rules.py`（新增类型交集检查，加载共享用例 JSON）
- Modify: `datara-backend/tests/test_graph_rules.py`（追加用例表驱动测试）
- 读取: `datara-web/src/graph/model/__tests__/portTypeCases.json`（Task 1 产物，唯一真源）

- [ ] **Step 1: 失败测试**（追加到现有 test_graph_rules.py）：

```python
import json, pathlib
from api.graph_rules import port_types_match_py

_CASES = json.loads((pathlib.Path(__file__).parents[2]
    / "datara-web/src/graph/model/__tests__/portTypeCases.json").read_text(encoding="utf-8"))["cases"]

def test_port_types_match_shared_case_table():
    """与前端 vitest 跑同一份用例表（方案§11.2 校验规则一致性）"""
    for c in _CASES:
        assert port_types_match_py(c["src"], c["dst"]) is c["expected"], c
```

- [ ] **Step 2: 跑失败**。

- [ ] **Step 3: 实现**——`graph_rules.py` 追加（逻辑与前端 portTypes.ts 逐行同构）：

```python
TYPE_COMPAT = {
    "string": ["string", "json"], "number": ["number", "string"], "boolean": ["boolean"],
    "json": ["json", "string"], "table": ["table", "dataset", "json"],
    "dataset": ["dataset", "table", "json"], "file": ["file", "json"], "stream": ["stream"],
}

def port_types_match_py(src: str | None, dst: str | None) -> bool:
    if not src or not dst or src == "any" or dst == "any":
        return True
    if src == "none" or dst == "none":
        return False
    row = TYPE_COMPAT.get(src)
    return row is None or dst in row   # 未知类型视为 any（与前端一致）
```

并挂入现有保存/发布校验流：遍历 `graph_json.edges`，取两端组件 spec 的 ports type（缺省 any），任一边不匹配 → 校验失败，错误消息含 `源 X → 目标 Y`（与前端文案一致，方案§3.1「前后端同一份规则」）。

- [ ] **Step 4: 跑通过**；提交 `feat(rules): 后端类型交集复检 + 前后端共享用例表（方案§3.1/§11.2）`。

### Task 10: 错误聚合面板 + 一键定位

**Files:**
- Create: `datara-web/src/graph/model/docErrors.ts` + `__tests__/docErrors.spec.ts`
- Create: `datara-web/src/components/graph/ErrorPanel.vue`
- Modify: `datara-web/src/graph/workbench/GraphWorkbench.vue`（底部抽屉挂载 + 定位函数）

- [ ] **Step 1: 失败测试**（docErrors 聚合三类错误源 → 统一列表）：

```ts
import { describe, it, expect } from 'vitest'
import { collectDocErrors } from '../docErrors'

describe('collectDocErrors（方案§3.3 三类分页签）', () => {
  it('聚合节点/边/闸门错误并携带定位锚点', () => {
    const doc = { nodes: [{ id: 'n1', type: 'sql', position: { x: 0, y: 0 }, data: {} }],
                  edges: [] } as never
    const errs = collectDocErrors(doc, {
      nodeErrors: { n1: ['参数 sql 不能为空'] },
      edgeErrors: [],
      gateErrors: [{ code: 'CYCLE', message: '存在环: n1' }],
    })
    expect(errs).toHaveLength(2)
    expect(errs[0]).toMatchObject({ kind: 'node', nodeId: 'n1', message: '参数 sql 不能为空' })
    expect(errs[1]).toMatchObject({ kind: 'gate', message: '存在环: n1' })
  })
  it('空文档零错误', () => {
    expect(collectDocErrors({ nodes: [], edges: [] } as never, { nodeErrors: {}, edgeErrors: [], gateErrors: [] })).toHaveLength(0)
  })
})
```

- [ ] **Step 2: 跑失败**。

- [ ] **Step 3: 实现** `docErrors.ts`：

```ts
export interface DocError {
  kind: 'node' | 'edge' | 'gate'
  nodeId?: string; edgeId?: string
  code: string; message: string
}
export function collectDocErrors(
  doc: { nodes: { id: string }[]; edges: unknown[] },
  src: { nodeErrors: Record<string, string[]>; edgeErrors: { edgeId: string; message: string }[]; gateErrors: { code: string; message: string }[] },
): DocError[] {
  const out: DocError[] = []
  for (const [nodeId, msgs] of Object.entries(src.nodeErrors)) {
    for (const m of msgs) out.push({ kind: 'node', nodeId, code: 'NODE_INVALID', message: m })
  }
  for (const e of src.edgeErrors) out.push({ kind: 'edge', edgeId: e.edgeId, code: 'EDGE_INVALID', message: e.message })
  for (const g of src.gateErrors) out.push({ kind: 'gate', code: g.code, message: g.message })
  return out
}
```

- [ ] **Step 4: ErrorPanel 组件 + 定位**——底部可收起抽屉（`el-drawer` direction=btt，尺寸 30%），三页签 node/edge/gate 列表，每条右侧「定位」按钮 → `fitView({ nodes: [id], duration: 300 })` + 该节点 class `error-focus` 2s（CSS outline + 感叹角标，方案§3.3）。GraphWorkbench：校验（onConnect 拒绝、保存闸门、Task 8 类型道）结果全部写入错误模型；节点红描边 class `st-error`（沿用 DataNode 现有状态 class 机制）；Inspector 顶部错误卡片（选中节点有 node 错误时显示 message 列表）。验收：任意错误 ≤2 次点击定位（方案§12-二③）。

- [ ] **Step 5: 跑通过 + 浏览器实测**；提交 `feat(dag): 错误聚合面板+一键定位+Inspector错误卡片（方案§3.3）`。

### Task 11: 批量操作（对齐/分布/多选复制粘贴/新快捷键）

**Files:**
- Create: `datara-web/src/graph/model/align.ts` + `__tests__/align.spec.ts`
- Create: `datara-web/src/graph/model/clipboard.ts` + `__tests__/clipboard.spec.ts`
- Modify: `datara-web/src/graph/workbench/GraphWorkbench.vue`（键盘 handler、工具条、右键菜单）

- [ ] **Step 1: align 失败测试**：

```ts
import { describe, it, expect } from 'vitest'
import { alignNodes, distributeNodes } from '../align'

const mk = (xs: number[], y = 0) => xs.map((x, i) => ({ id: `n${i}`, position: { x, y } }))

describe('alignNodes（方案§3.5 以选集边界为基准）', () => {
  it('左对齐', () => {
    const r = alignNodes(mk([100, 50, 75]), 'left')
    expect(r.map((n) => n.position.x)).toEqual([50, 50, 50])
  })
  it('右对齐（含节点宽度）', () => {
    const r = alignNodes(mk([100, 50]), 'right', () => 40)
    expect(r.map((n) => n.position.x)).toEqual([60, 50])   // 右边界对齐 90：100+40-80, 50
  })
  it('水平居中', () => {
    const r = alignNodes(mk([100, 50]), 'hcenter', () => 40)
    expect(r.map((n) => n.position.x)).toEqual([80, 50])
  })
})

describe('distributeNodes（≥3 有效）', () => {
  it('水平等距', () => {
    const r = distributeNodes(mk([0, 10, 60]), 'h', () => 10)
    expect(r.map((n) => n.position.x)).toEqual([0, 25, 50])
  })
  it('少于 3 个原样返回', () => {
    const arr = mk([0, 30])
    expect(distributeNodes(arr, 'h', () => 10)).toEqual(arr)
  })
})
```

- [ ] **Step 2: 跑失败**。**Step 3: 实现** `align.ts`（纯函数：left/right/top/bottom/hcenter/vcenter/distributeH/distributeV，宽度取自 `nodeWidthOf` 回调）与 `clipboard.ts`：

```ts
/** 多选复制粘贴（方案§3.5）：新 ID 按 max-existing-sequence+1（硬约束），内部边随行复制，跨组件连线不复制 */
export function pasteSelection(
  doc: { nodes: { id: string; type: string; position: { x: number; y: number }; data: Record<string, unknown> }[]
           ; edges: { id: string; source: string; target: string; kind: string; label?: string; sourceHandle?: string; targetHandle?: string }[] },
  copied: { nodes: { id: string; type: string; position: { x: number; y: number }; data: Record<string, unknown> }[]
           ; edges: { source: string; target: string; kind: string; label?: string; sourceHandle?: string; targetHandle?: string }[] },
  nextId: (type: string) => string,   // 由调用方注入 max+1 生成器（GraphWorkbench 现有 uid 序列逻辑）
  offset = 24,
) {
  const idMap = new Map(copied.nodes.map((n) => [n.id, nextId(n.type)]))
  const nodes = copied.nodes.map((n) => ({
    ...n, id: idMap.get(n.id)!, position: { x: n.position.x + offset, y: n.position.y + offset },
    data: structuredClone(n.data),
  }))
  const internal = new Set(copied.nodes.map((n) => n.id))
  const edges = copied.edges
    .filter((e) => internal.has(e.source) && internal.has(e.target))
    .map((e, i) => ({ ...e, id: `e_paste_${Date.now().toString(36)}_${i}`,
                      source: idMap.get(e.source)!, target: idMap.get(e.target)! }))
  return { nodes, edges }
}
```

- [ ] **Step 4: GraphWorkbench 接线**——Ctrl+C（快照 `copied = {nodes: 选集深拷贝, edges: 选集内部边}`）、Ctrl+V（pasteSelection → doc 追加 → markDirty）、Ctrl+D（原位复制，offset=0）、Ctrl+A（selectedIds = 全节点）、方向键（选中节点微移 1px，Shift=网格步长）、F2（重命名聚焦）、`?`（快捷键帮助浮窗——走 FloatDef 注册，方案§4.1）。多选态工具条：对齐六按钮 + 分布两按钮（选集 ≥3 才可用）。**注意**：与现有快捷键 Ctrl+Z/Y/C/V/Del/F/Esc 合并进同一 keydown handler，避免重复绑定；粘贴后 ID 用现有 uid/max+1 序列。

- [ ] **Step 5: 跑通过 + 浏览器实测**（框选→对齐/分布/复制粘贴/ID 连续性）；提交 `feat(dag): 批量对齐/分布/多选复制粘贴/新快捷键（方案§3.5）`。

### Task 12: undo structuredClone + 渲染性能三件套

**Files:**
- Modify: `datara-web/src/graph/workbench/GraphWorkbench.vue`（undo 快照栈 ~L354 区域）
- Modify: `datara-web/src/components/graph/DataNode.vue`（ports memo）
- Modify: `datara-web/src/graph/workbench/GraphWorkbench.vue`（`<VueFlow>` prop `only-render-visible-elements`，受开关 `canvasOnlyRenderVisible` 控制）

- [ ] **Step 1: ports memo 失败测试**（`datara-web/src/components/graph/__tests__/portsMemo.spec.ts`）：

```ts
import { describe, it, expect, vi } from 'vitest'
import { memoPorts } from '../portsMemo'

describe('memoPorts（方案§3.6 惰性求值）', () => {
  it('相同 schemaId+data 摘要不重算', () => {
    const factory = vi.fn(() => [{ id: 'out', label: 'O' }])
    const m = memoPorts(factory)
    const data = { name: 'a' }
    m('s1', data); m('s1', data)
    expect(factory).toHaveBeenCalledTimes(1)
    m('s1', { name: 'b' })
    expect(factory).toHaveBeenCalledTimes(2)
  })
})
```

- [ ] **Step 2: 跑失败**。**Step 3: 实现**：

`portsMemo.ts`：
```ts
/** ports 结果按 schemaId+data 摘要 memo（方案§3.6：杜绝拖拽帧每帧重算） */
export function memoPorts<T>(factory: (schemaId: string, data: Record<string, unknown>) => T) {
  const cache = new Map<string, T>()
  return (schemaId: string, data: Record<string, unknown>): T => {
    const key = `${schemaId}:${JSON.stringify(data)}`
    let v = cache.get(key)
    if (v === undefined) { v = factory(schemaId, data); cache.set(key, v) }
    return v
  }
}
```

DataNode：`schema?.ports?.(props.node.data)` 调用点包 memoPorts（组件实例级 cache，卸载随组件回收，无全局泄漏）。

undo 栈：快照序列化从 `JSON.stringify(doc)` 改 `structuredClone(doc)`（浏览器原生，node 侧 vitest 需 Node ≥17 可用）；快照栈上限 50 与 800ms 拖拽合并窗口**保持不变**（方案§3.5 P0 范围，命令栈留 P1 Task 22）。

VueFlow prop：`<VueFlow :only-render-visible-elements="flag" ...>`，`flag = flags.canvasOnlyRenderVisible !== false`（默认 on）。

- [ ] **Step 4: 跑通过**；提交 `perf(dag): undo structuredClone + ports memo + 视口裁剪（方案§3.6）`。

### Task 13: 性能基准脚本 canvas-bench

**Files:**
- Create: `datara-web/tests/perf/canvas-bench.ts`
- Modify: `datara-web/package.json`（scripts 加 `"bench:canvas": "vitest run tests/perf/canvas-bench.ts"`）

- [ ] **Step 1: 实现基准**（vitest 环境跑纯前端指标：构建 200 节点/400 边标准图 → cloneDoc×100 计时、toFlowNode 全量转换计时、undo 快照 50 次计时；FPS 类指标留浏览器手动脚本输出到 console，报告写 `tests/perf/last-bench.json`）：

```ts
import { describe, it, expect } from 'vitest'
import { cloneDoc, type GraphDocument } from '../../src/graph/model'
import { buildBenchDoc } from './buildBenchDoc'

describe('canvas-bench（方案§3.6 基准，200 节点/400 边）', () => {
  const doc: GraphDocument = buildBenchDoc(200, 400)

  it('cloneDoc×100 < 1500ms', () => {
    const t0 = performance.now()
    for (let i = 0; i < 100; i++) cloneDoc(doc)
    expect(performance.now() - t0).toBeLessThan(1500)
  })
  it('undo 快照（structuredClone）×50 < 1000ms', () => {
    const t0 = performance.now()
    for (let i = 0; i < 50; i++) structuredClone(doc)
    expect(performance.now() - t0).toBeLessThan(1000)
  })
})
```

`buildBenchDoc.ts`：生成 `bench_n{i}` 节点（i<160 为 sql 型，其余 sink）+ 保证 400 条边（链式 + 每第 5 个节点额外一条汇聚边）。

- [ ] **Step 2: 跑基准通过并记录基线值**到 `tests/perf/last-bench.json`（后续批次改动对比用，方案§11.3）；提交 `test(perf): 200节点画布基准脚本（方案§3.6/§11.3）`。

---

## 4. 批次 P0-3（方向三：状态持久化与升级策略）

### Task 14: 画布状态持久化 + Tab keep-alive

**Files:**
- Create: `datara-web/src/composables/useCanvasState.ts` + `__tests__/useCanvasState.spec.ts`
- Modify: `datara-web/src/graph/workbench/GraphWorkbench.vue`（onMoveEnd/onSelectionChange 挂钩 + 恢复）
- Modify: `datara-web/src/views/DagDesignerView.vue`（dagTabs 渲染改 keep-alive）

- [ ] **Step 1: 失败测试**：

```ts
import { describe, it, expect } from 'vitest'
import { loadCanvasState, saveCanvasState } from '../useCanvasState'

describe('useCanvasState（方案§3.7 localStorage canvas-state:{docId}）', () => {
  it('保存后可恢复视口/选中/Tab/浮窗', () => {
    saveCanvasState('doc1', { viewport: { x: 1, y: 2, zoom: 0.8 }, selectedIds: ['n1'], activeTab: '依赖', floats: { legend: true } })
    expect(loadCanvasState('doc1')).toMatchObject({ viewport: { zoom: 0.8 }, selectedIds: ['n1'] })
  })
  it('隐私模式写失败不抛错', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    expect(() => saveCanvasState('doc2', { viewport: { x: 0, y: 0, zoom: 1 }, selectedIds: [], activeTab: '', floats: {} })).not.toThrow()
  })
})
```

- [ ] **Step 2: 跑失败**。**Step 3: 实现**（`localStorage` 键 `canvas-state:${docId}`，写侧 500ms 防抖，方案§4.5；try/catch 吞隐私模式异常——GraphWorkbench L327 已有同模式）：

```ts
export interface CanvasState {
  viewport: { x: number; y: number; zoom: number }
  selectedIds: string[]
  activeTab: string
  floats: Record<string, boolean>
}
const KEY = (docId: string) => `canvas-state:${docId}`
let timer: ReturnType<typeof setTimeout> | undefined
let pending: CanvasState | undefined
export function saveCanvasState(docId: string, st: CanvasState) {
  pending = st
  clearTimeout(timer)
  timer = setTimeout(() => { try { localStorage.setItem(KEY(docId), JSON.stringify(pending)) } catch { /* 隐私模式 */ } }, 500)
}
export function loadCanvasState(docId: string): CanvasState | null {
  try { const raw = localStorage.getItem(KEY(docId)); return raw ? JSON.parse(raw) as CanvasState : null }
  catch { return null }
}
```

GraphWorkbench：`onMoveEnd`/`onSelectionChange`/Tab 切换/FloatDef 开合时 `saveCanvasState`；挂载恢复 `loadCanvasState` → `setViewport` + selectedIds + 浮窗开合。DagDesignerView：dagTabs 循环外包 `<KeepAlive>`，Tab 内容组件 `activated` 钩子里恢复视口（消除切换闪白与重复初始化，方案§3.7）。

- [ ] **Step 4: 跑通过 + 浏览器实测**（切 Tab 再切回视口/选中不丢；刷新恢复）；提交 `feat(dag): 画布状态持久化+Tab keep-alive（方案§3.7/§4.5）`。

### Task 15: 发布升级策略三档 + upgrade-refs 批量端点（自动档）+ 引用角标实时刷新

**Files:**
- Modify: `datara-backend/api/component_design.py`（publish 落 `_apply_upgrade_strategy`；新增 `POST /{type_name}/upgrade-refs`）
- Modify: `datara-web/src/views/…`（发布弹窗加策略单选：自动/手动/钉住，方案§4.3）
- Modify: `datara-web/src/components/graph/DataNode.vue` 或引用角标渲染处（specVersion 高于引用版本 → 黄色角标）
- Test: `datara-backend/tests/test_upgrade_refs.py`

- [ ] **Step 1: 失败测试**：

```python
def test_publish_auto_strategy_bumps_refs(client, wf_referencing_v1):
    """auto（patch/minor）：发布即扫 graph_json 注入新版本（扩展现有 _refresh_refs）"""
    r = client.post(f"/api/v1/components/{COMP}/publish", json={"draft_rev": 1, "upgrade_strategy": "auto"})
    assert r.status_code == 200
    assert r.json()["refs_refreshed"] >= 1

def test_publish_pin_strategy_pins_refs(client, wf_referencing_v1):
    r = client.post(f"/api/v1/components/{COMP}/publish", json={"draft_rev": 1, "upgrade_strategy": "pin"})
    body = r.json()
    assert body["pinned"] >= 1          # 引用处写入 pinned=true，版本不自动升
    # 该工作流 graph_json 中 componentRef.version 保持 v1

def test_upgrade_refs_batch(client, two_wfs_referencing_v1):
    r = client.post(f"/api/v1/components/{COMP}/upgrade-refs",
                    json={"targets": [{"wf_id": "wf_a", "strategy": "auto"},
                                      {"wf_id": "wf_b", "strategy": "auto"}]})
    body = r.json()
    assert {x["wfId"] for x in body["results"]} == {"wf_a", "wf_b"}
    assert all(x["ok"] for x in body["results"])
```

- [ ] **Step 2: 跑失败**。**Step 3: 实现**——

后端：publish 末尾按 `upgrade_strategy` 分派：`auto` → 现有 `_refresh_refs`（L1036）；`pin` → 扫引用处写 `pinned: true` 且**不改 version**；`manual` → 只记录待升级清单（供 P1 向导 Task 21 消费）。新增 `upgrade-refs`：逐 wf 读 graph_json → 注入新 version → base_version 乐观锁保存 → 失败项 `{"ok": false, "reason": ...}` 不中断（方案§4.3）。全部决策写 `t_component_log`。

前端：引用角标渲染读取 `componentStore.getSpec(type)?.specVersion`，> 当前引用 version → 黄色角标（方案§4.1 角标语义）；`component:published` EventBus（Task 4 已接线 invalidate）→ 角标随 specMap 刷新自动更新。

- [ ] **Step 4: 跑通过 + 浏览器实测**（patch 发布后角标变绿/消失、pin 发布后保持旧版可运行）；提交 `feat(publish): 升级策略三档+upgrade-refs+引用角标实时刷新（方案§4.3/§4.4）`。

---

## 5. 批次 P0-4（方向四：SSE 节点事件与画布染色）

### Task 16: t_run_event 表 + master 事件钩子 → Redis Pub/Sub

**Files:**
- Modify: `datara-backend/models.py`（或现有模型定义文件，新增 TRunEvent）
- Modify: `datara-backend/master/engine.py`（任务推进/重试/完成各状态点挂事件钩子）
- Create: `datara-backend/master/event_bus.py`（发布封装）
- Test: `datara-backend/tests/test_run_event_publish.py`

- [ ] **Step 1: 失败测试**：

```python
def test_engine_publishes_node_events(fake_redis, engine_fixture_with_two_nodes):
    """事件钩子按方案§5.1 协议发布到 Redis channel datara:run_events:{run_id}"""
    engine_fixture_with_two_nodes.run()
    msgs = fake_redis.published("datara:run_events:*")
    types = [m["type"] for m in msgs]
    assert "node_executing" in types and "node_executed" in types
    assert "execution_start" in types and "execution_success" in types
    for m in msgs:
        assert {"runId", "nodeId", "type", "ts"} <= set(m)

def test_run_event_persisted(engine_fixture_with_two_nodes, db):
    rows = db.query(TRunEvent).all()
    assert {r.event_type for r in rows} >= {"node_executing", "node_executed"}
```

- [ ] **Step 2: 跑失败**。**Step 3: 实现**：

表（追加到现有建表处，对齐现有迁移方式）：
```sql
CREATE TABLE IF NOT EXISTS t_run_event (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  run_id VARCHAR(64) NOT NULL, node_id VARCHAR(128) NOT NULL DEFAULT '',
  event_type VARCHAR(32) NOT NULL, payload_json TEXT,
  ts DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
  KEY idx_run (run_id, id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

`master/event_bus.py`：
```python
import json, time
import redis
from models import SessionLocal, TRunEvent

_channel_tpl = "datara:run_events:{run_id}"

def publish_run_event(rds: redis.Redis, run_id: str, node_id: str, ev_type: str, payload: dict | None = None) -> None:
    msg = {"runId": run_id, "nodeId": node_id, "type": ev_type, "ts": int(time.time() * 1000)}
    if payload: msg["payload"] = payload
    rds.publish(_channel_tpl.format(run_id=run_id), json.dumps(msg, ensure_ascii=False, default=str))
    db = SessionLocal()
    try:
        db.add(TRunEvent(run_id=run_id, node_id=node_id, event_type=ev_type,
                         payload_json=json.dumps(payload, ensure_ascii=False) if payload else None))
        db.commit()
    finally:
        db.close()
```

engine.py 钩子位（现有状态推进函数内追加一行调用）：节点开始执行 → `node_executing`；成功 → `node_executed`；命中缓存 → `node_cached`；失败 → `node_error`（payload 含 exceptionType/message）；进入重试 → `node_retry`（payload 含 attempt/max）；运行级 start/success/interrupted。**progress 事件节流 200ms 合帧**（方案 R6）。现有行为零改动（纯追加钩子调用）。

- [ ] **Step 4: 跑通过**；提交 `feat(engine): 节点级事件钩子→Redis Pub/Sub + t_run_event 落库（方案§5.1/§5.6）`。

### Task 17: SSE node_event 协议 + last-event-id 补发（灰度开关 sseSource）

**Files:**
- Modify: `datara-backend/api/instance.py:205`（stream_instance 扩展）
- Modify: `datara-backend/api/instance.py`（新增 `GET /{id}/events` 分页回放）
- Test: `datara-backend/tests/test_instance_stream.py`（追加）

- [ ] **Step 1: 失败测试**（追加）：

```python
def test_stream_emits_node_events(client, running_instance_with_events):
    """实例级事件保留 + node_event 新族（方案§5.1 additive）"""
    with client.stream("GET", f"/api/v1/instances/{running_instance_with_events}/stream") as r:
        body = b"".join(r.iter_bytes()).decode()
    assert "event: status" in body            # 现有实例级事件不动
    assert "event: node_event" in body
    assert "node_executing" in body

def test_stream_last_event_id_replays_missed(client, running_instance_with_events):
    r = client.get(f"/api/v1/instances/{running_instance_with_events}/events?page=1&page_size=10")
    assert r.status_code == 200
    assert r.json()["items"], "events 回放接口返回 t_run_event 分页"
```

- [ ] **Step 2: 跑失败**。**Step 3: 实现**——`stream_instance` 的 gen（L220）内追加一条分支：读 `datara.flags.sseSource`（服务端配置等价开关，默认 polling 保持现状）；`pubsub` 模式下 `redis.pubsub(subscribe=channel)` 收到消息 → `yield f"event: node_event\ndata: {msg}\n\n"`（复用 L265 现有 yield 模式）；`polling` 模式维持现 1s diff 逻辑但**额外**从 `t_run_event` 增量拉新事件合成 node_event（两种模式都出 node_event，区别仅延迟与实现）。断线重连：请求头 `Last-Event-ID`（或 query `lastEventId`）→ 先从 `t_run_event` 补发该 id 之后的事件再进入实时流（方案§6.2 事件不丢）。新增 `GET /{id}/events`：t_run_event 按 run 分页（page/page_size）。

- [ ] **Step 4: 跑通过**；提交 `feat(api): SSE node_event 协议+last-event-id 补发+events 回放（方案§5.1/§6.1#9）`。

### Task 18: runStore 扩展 + 画布四态染色 + 边流动动画 + 日志 SSE 化

**Files:**
- Modify: `datara-web/src/stores/run.ts`（新增 SSE 订阅生命周期 nodeStateMap；保留现有 mock bus 通道）
- Create: `datara-web/src/services/runEventSource.ts`（EventSource 封装：重连/lastEventId）
- Modify: `datara-web/src/components/graph/DataNode.vue`（四态染色 class）
- Modify: `datara-web/src/graph/workbench/GraphWorkbench.vue`（运行中边流动 class）
- Modify: `datara-web/src/components/graph/LogPanel.vue`（SSE 增量追加，保留 3s 轮询降级）
- Test: `datara-web/src/stores/__tests__/run.nodeEvents.spec.ts`

- [ ] **Step 1: 失败测试**（store 纯逻辑，EventSource mock 掉）：

```ts
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useRunStore } from '../run'

describe('runStore node_event 消费（方案§5.1 四态染色）', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('四态映射：executing→amber executed→green cached→gray error→red', () => {
    const s = useRunStore()
    s.applyNodeEvent({ runId: 'r1', nodeId: 'n1', type: 'node_executing', ts: 1 })
    s.applyNodeEvent({ runId: 'r1', nodeId: 'n2', type: 'node_executed', ts: 2 })
    s.applyNodeEvent({ runId: 'r1', nodeId: 'n3', type: 'node_cached', ts: 3 })
    s.applyNodeEvent({ runId: 'r1', nodeId: 'n4', type: 'node_error', ts: 4, payload: { message: 'x' } })
    expect(s.nodeStateMap.n1).toMatchObject({ state: 'executing', color: 'amber' })
    expect(s.nodeStateMap.n2).toMatchObject({ state: 'executed', color: 'green' })
    expect(s.nodeStateMap.n3).toMatchObject({ state: 'cached', color: 'gray' })
    expect(s.nodeStateMap.n4).toMatchObject({ state: 'error', color: 'red' })
  })
  it('他 run 事件丢弃', () => {
    const s = useRunStore()
    s.runId = 'r1'
    s.applyNodeEvent({ runId: 'r2', nodeId: 'n1', type: 'node_executing', ts: 1 })
    expect(s.nodeStateMap.n1).toBeUndefined()
  })
})
```

- [ ] **Step 2: 跑失败**。**Step 3: 实现**：

run.ts 追加 state：`nodeStateMap: {} as Record<string, { state: string; color: string; attempt?: number; message?: string; ts: number }>`；action：

```ts
applyNodeEvent(ev: { runId: string; nodeId: string; type: string; ts: number; payload?: Record<string, unknown> }) {
  if (this.runId && ev.runId !== this.runId) return
  const m: Record<string, { state: string; color: string }> = {
    node_executing: { state: 'executing', color: 'amber' },
    node_executed: { state: 'executed', color: 'green' },
    node_cached: { state: 'cached', color: 'gray' },
    node_error: { state: 'error', color: 'red' },
    node_retry: { state: 'retrying', color: 'amber' },
  }
  const hit = m[ev.type]
  if (!hit) return
  this.nodeStatus[ev.nodeId] = hit.state          // 复用现有 DataNode st- 染色通道
  this.nodeStateMap[ev.nodeId] = { ...hit, attempt: (ev.payload?.attempt as number), message: (ev.payload?.message as string), ts: ev.ts }
  if (ev.type === 'node_error') this.log(`[error] ${ev.nodeId} · ${ev.payload?.message ?? ''}`, 'fail')
}
```

`runEventSource.ts`：`new EventSource(`/api/v1/instances/${id}/stream`)`，`addEventListener('node_event', ...)` → store.applyNodeEvent；onerror 自动重连（<3s）并带 lastEventId。**禁止组件各自开连接**——仅 runStore 持有（方案§7.2）。GraphWorkbench 运行监控态：`nodeStateMap` 驱动 DataNode class（amber/green/gray/red 四态 CSS，与 §4.1 色彩语义一致）；两端节点皆 executing/executed 的边加 `.edge-flowing`（CSS `stroke-dashoffset` 关键帧动画）。LogPanel：优先消费 runStore.logs（SSE 已入），失败回退现有 3s 轮询。

- [ ] **Step 4: 跑通过 + 全量验证 + 1.9 实测**（真实运行实例四态染色与执行一致、截图留档）；提交 `feat(run): SSE 节点事件消费+画布四态染色+边流动+日志SSE化（方案§5.1）`。

---

## 6. 批次 P1（方向 1d/2e/2f/3c/3d/4b/4c/4d，按依赖顺序）

> P1 任务粒度：文件 + 改动要点 + 验证 + 验收。执行时按 P0 同样 TDD 纪律展开（每任务先写测试）。P1 内部顺序：4c（重试分类，独立）→ 4b（断点续传，依赖 4c 无但依赖 Task 16 事件）→ 2e（命令栈）→ 3c（升级向导）→ 3d（自动保存）→ 1d（behaviors）→ 2f（边浮窗）→ 4d（模板库）。

### Task 19 (4c): 智能重试分类策略
**Files:** Create `datara-backend/master/retry_classifier.py` + `tests/test_retry_classifier.py`；Modify `master/engine.py` `_schedule_retry`。
要点：纯函数 `classify_error(exception_type, message, exit_code) -> 'transient'|'congestion'|'deterministic'|'external'`，规则表可配置（dict 常量）；瞬时=指数退避 1s→5s→25s 上限 3；拥塞=30s 起退避；确定性=不重试直接失败；外部=组件 retryTimes 兜底默认 2。engine 集成：现有固定 retryTimes 保留为无分类时的默认；`node_retry` 事件 payload 带 `{attempt, max, strategy}`（前端角标「第 n/3 次（指数退避）」，方案§5.3/§8.2）。
验证：`pytest tests/test_retry_classifier.py -q`（用例覆盖四类各 ≥2 条）+ engine 集成测试；vue-tsc/vitest。
验收：§12-四③ 瞬时错误自动指数退避且 node_retry 可见。

### Task 20 (4b): 断点续传（t_node_artifact + resume-from + cached 染色）
**Files:** Modify `models.py`（TRunNodeArtifact）、`master/engine.py`（成功后写产物指纹；重跑前签名比对）；Create `master/signature.py` + `tests/test_node_signature.py`；Modify `api/instance.py`（`POST /workflow-definitions/{wf}/runs/{runId}/resume-from` body `{fromNodeIds: string[]}`，方案§6.1#5，响应 <200ms 异步）。前端：Modify 运行监控「从失败节点续跑」按钮 + cached 灰色染色（Task 18 已有 color 映射）。
要点：`node_signature = sha256(class_type + spec_version + sorted(params json) + 上游签名递归)`（`signature.py` 纯函数，测试覆盖：参数变化/上游变化/无关变化三种失效场景）；产物登记 `t_node_artifact(run_id, node_id, node_signature, artifact_fingerprint, refs)`；重跑逐节点比对：命中跳过执行发 `node_cached`、不命中正常执行（宁多勿漏，R3）；受开关 `checkpointEnabled` 控制（默认 off，先仅幂等任务类型启用，方案§11.5）；清理任务对齐「定期清理远期日志脚本」按 run 保留期清 t_node_artifact。
验证：pytest（签名纯函数 + 引擎命中跳过集成）+ vue-tsc/vitest + 1.9 实测。
验收：§12-四②（命中灰、耗时 0；未命中正常重跑）。

### Task 21 (3c): 批量升级向导（diff + fieldMapping UI）
**Files:** Create `datara-web/src/components/designer/UpgradeWizard.vue`；Modify ComponentHubView（发布弹窗 manual 档入口）；消费 Task 15 的 upgrade-refs 端点（逐个乐观锁保存，冲突项跳过进失败清单）。
要点：向导三步 = 选工作流（impacted 清单多选）→ 逐个 diff（旧 spec vs 新 spec 字段级对照，复用 Task 7 `_classify_spec_change` 的 changes 结构，前端同构 TS 函数 `classifySpecChange` 放 `services/componentSpec.ts` 并配套 vitest）→ fieldMapping 行编辑（旧字段→新字段映射）或「不迁移」确认 → 结果报告（成功/失败/跳过三列表，方案§4.3 流程图）。
验证：vitest（classifySpecChange + 向导状态机）+ vue-tsc + 1.9 实测截图。
验收：§12-三③（major 发布走向导完成迁移并出报告）。

### Task 22 (2e): undo 命令栈（灰度开关）+ syncFromDoc 增量化 + dagre Worker
**Files:** Create `datara-web/src/graph/history/commands.ts` + `__tests__/commands.spec.ts`；Modify GraphWorkbench（六类命令 AddNode/DeleteNode/MoveNodes/Connect/Disconnect/UpdateProps 各自 apply/undo，开关 `undoCommandStack`，>150 节点自动切命令栈，快照栈保留兜底）；Modify `graph/workbench/syncFromDoc`（nodes/edges 增删改三类 patch diff——先 diff 再写入 flowNodes/flowEdges，P0 全量路径保留为回退）；Create `datara-web/src/graph/workbench/layoutWorker.ts`（dagre 计算移入 Web Worker，>200 节点触发，主线程显示进度）。
验证：vitest（命令对偶性：任意操作序列 apply 后 undo 等价原状态——property-based 10 组）+ vue-tsc + canvas-bench 对比 last-bench.json。
验收：方案§3.5 P1 + R5（随时可退回快照栈）。

### Task 23 (3d): 草稿 30s 自动保存 + 冲突 diff 视图
**Files:** Modify 组件设计器保存逻辑（30s 防抖 + beforeunload 强制保存 + 「已自动保存」轻提示）；Modify 保存 409 处理（拉远端 draftRev，弹三方 diff 视图「我的/远端/基准」逐项选择，方案§2.4/§8.2）。
验证：vitest（防抖保存 + 409 流程）+ vue-tsc + 实测双开冲突场景。
验收：方案§2.4 冲突解决 + §4.5 持久化表。

### Task 24 (1d): behaviors 序列化消费 + hiddenInputs + 组件开发规范文档
**Files:** Modify Inspector/拖入弹窗表单渲染（消费 `behaviors.prefillFromUpstream/pick/onChange`——现散落 profile 硬编码迁入 spec 驱动，逐组件迁移，profile 行为保留兜底）；Modify 执行侧（`extensions.hiddenInputs` 运行时向算子注入 tenantId/runId/nodeId/workflowId 上下文，engine 传参扩展）；Create `docs/组件开发规范.md`（8 要素填写标准与反例、DataType 选用表、FieldSpec 控件选型表、behaviors 表达式语法、命名与分类树约定、测试验证要求 testable+≤100、发布闸门自查清单——方案§2.5 全要点）。
验证：vitest（behaviors 判定纯函数）+ pytest（hiddenInputs 注入）+ 1.9 实测。
验收：§2.5 文档产出 + 交互行为从 profile 到 spec 的迁移完成度（对账 consistencyErrors 归零推进）。

### Task 25 (2f): 边类型着色 + 边数据浮窗 + Reroute 转接节点
**Files:** Modify GraphWorkbench（toFlowEdge 追加 color class：table=蓝 dataset=青 stream=紫 file=橙 any=灰；图例浮窗 EdgeLegend.vue 走 FloatDef 注册）；Create `EdgeDataFloat.vue`（点击边显示上游 outputs schema + 最近运行样例 ≤100 行——复用组件设计器预览上限约束，无运行记录仅显示 schema）；Create `RerouteNode.vue`（纯编辑图节点，执行编译时展开消除——在 doc→run 编译处过滤 `type==='reroute'` 并直连前后边，配套 pytest/vitest 各一条）。
验证：vitest + vue-tsc + 实测截图。
验收：方案§3.2 全三项。

### Task 26 (4d): 工作流模板库
**Files:** Create `datara-backend/api/workflow_templates.py`（CRUD + `POST /{id}/instantiate` body `{name?}` → 新工作流草稿 id（ID/变量全量重生成，走现有 max+1 序列）+ `GET /{id}/versions` 版本链，方案§6.1#6-8）；Modify `models.py`（`t_wf_template(id, name, category, description, template_json, version, created_by, updated_at)` + `t_wf_template_version`）；Modify 任务编排列表（「另存为模板」）+ 新增模板中心页签（「从模板新建」）；Create `datara-web/src/stores/templateStore.ts`。
要点：模板升级仅提示不强制（基于旧版实例化的工作流列表显示「可选升级」+ diff 预览 + 确认，R7）。
验证：pytest（CRUD/instantiate/versions 全链路）+ vitest + vue-tsc + 1.9 实测。
验收：§12-四④ 模板创建→实例化→升级提示全链路。

---

## 7. 批次 P2（按需启动，单独立项验收）

### Task 27 (2g): 跨工作流依赖环检测
dependent 组件引用外部工作流节点后，保存时构建「工作流引用图」DFS 检测引用环，含环给出路径展示；错误聚合面板（Task 10）新增「依赖配置不完整」检查项。**验证**：pytest（环路径构造用例）+ vitest。**验收**：方案§3.4。

### Task 28 (4e): 全图签名缓存（ComfyUI 完整形态）
任意节点重跑：Task 20 的节点签名推广到全图（祖先签名缓存键），运行前逐节点比对支持任意节点粒度重跑。**验证**：pytest + 实测。**验收**：方案§9.1 P2。

### Task 29 (4f): 关键路径高亮 + 并行度配置
Inspector 工作流属性页 `parallelism` 配置（默认不限）；运行监控按节点耗时计算最长路径琥珀描边。**验证**：pytest（最长路径纯函数）+ vitest + 实测。**验收**：方案§5.4。

### Task 30 (3e): 子图/流程片段复用（blueprints 模式）
画布选集另存为可复用片段（GraphDocument 子集），拖入展开；执行编译时平铺展开。**验证**：vitest（子图序列化/展开）+ 实测。**验收**：方案§1.3 演进项。

---

## 8. 每批次合并门槛（DoD，方案§11）

1. `npx vue-tsc --noEmit` 0 错误（datara-web）；
2. `npx vitest run` 全绿、`python -m pytest tests/ -q` 全绿（datara-backend）；
3. `npx vite build` 成功；
4. canvas-bench 对比 last-bench.json 无退化（画布相关改动批次）；
5. 1.9 环境 UI 实测 + 截图留档（涉及可见交互的任务）;
6. 本文档对应任务 checkbox 勾选 + 验收标准核对（§9 总表）；
7. 提交推送 `feat/workbench-opt`，用户确认后合并 main。

## 9. 验收对照总表（方案§12 → 任务映射）

| 方向 | 验收点 | 任务 |
|---|---|---|
| 一① | /components/spec 全量已发布 + 8 要素结构 | Task 3 |
| 一② | 设计器可编辑输出/行为/接口并走通发布闸门 | Task 6、7、24 |
| 一③ | 破坏性变更 impacted+fieldMapping 拦截 | Task 7、21 |
| 一④ | spec 断连 profile 兜底无白屏 | Task 4、5 |
| 二① | 拖线实时拦截 + toast 准确 | Task 8 |
| 二② | 保存闸门/后端同一批非法图全拒（用例表 100%） | Task 1、8、9 |
| 二③ | 错误 ≤2 次点击定位 | Task 10 |
| 二④ | 对齐/分布/复制粘贴 + ID max+1 | Task 11 |
| 二⑤ | 200 节点基准 ≥30FPS / 布局 P95<1.5s | Task 12、13（FPS 项 1.9 实测） |
| 三① | 双工作台互跳状态恢复 | Task 14 |
| 三② | patch 发布引用角标/版本自动刷新 | Task 15 |
| 三③ | major 发布向导迁移+报告 | Task 21 |
| 三④ | 三层乐观锁拒绝并发写 | Task 15（upgrade-refs 逐个校验）+ 现有 draftRev/base_version |
| 四① | 画布四态染色与执行一致 | Task 18 |
| 四② | 断点续跑命中灰/耗时 0 | Task 20 |
| 四③ | 瞬时错误指数退避 + node_retry 可见 | Task 19 |
| 四④ | 模板全链路 | Task 26 |
| 四⑤ | SSE P95<1s + 断线不丢 | Task 17、18（延迟实测留档） |

## 10. Self-Review 记录

- **Spec 覆盖**：方案 §2.1→Task 6、§2.2→Task 2、§2.3→Task 3/4/5、§2.4→Task 7/23、§2.5→Task 24、§2.6→Task 6、§2.7→Task 6、§3.1→Task 1/8/9、§3.2→Task 25、§3.3→Task 10、§3.4→Task 27、§3.5→Task 11/22、§3.6→Task 12/13、§3.7→Task 14、§4.1→Task 8/15/25（FloatDef/色彩语义贯穿）、§4.2→Task 14（互跳路由 query focus 参数随 Task 14 恢复机制一并实现）、§4.3→Task 15/21、§4.4→Task 4/15、§4.5→Task 14/23、§5.1→Task 16/17/18、§5.2→Task 20、§5.3→Task 19、§5.4→Task 29、§5.5→Task 26、§5.6→Task 16/26、§6.1 全 9 接口→Task 3/7/15/17/20/26 对应覆盖、§8 全部交互反馈分散于对应任务。
- **占位符扫描**：无 TBD/TODO；P1 任务按用户约定的粗粒度给出完整改动要点与验收（非「实现细节后补」）。
- **类型一致性**：`portTypesMatch(src?, dst?)` 签名在 Task 1/8/9 三处一致（src/dst 可空按 any）；`DocError` 字段在 Task 10 定义与消费一致；`nodeStateMap` 结构在 Task 18 测试与实现一致；共享用例表 JSON 路径唯一（datara-web 侧），后端 pytest 跨目录读取。
