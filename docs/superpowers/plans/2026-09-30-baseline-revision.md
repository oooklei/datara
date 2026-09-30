# 基线化组件「修订轮次」+ 三项缺陷修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让已认可发版的基线化组件支持「复制上版开修订 → 手动认可发 vN」完整轮次，并修复保存 422、M1 设计器 builtin 死路、published 底稿可静默改写三个缺陷。

**Architecture:** 第一批修前端保存契约字段名（camelCase→snake_case）、http 兜底文案、后端 save 状态拦截、M1 设计器 builtin 引导；第二批在基线化链上增量扩展 redraft / discard_draft 端点与 publish vN 改造（复用 t_component_version 多版本），状态机不新增枚举（修订中 = designing + publishedVersion>0）。

**Tech Stack:** FastAPI + SQLAlchemy（sqlite 内存库测试）、Vue3 + vitest、1.9 实测（API 冒烟 + 浏览器回归）。

**Spec:** `docs/superpowers/specs/2026-09-30-baseline-revision-design.md`

**项目惯例:** 部署 1.9 用脚本文件 scp 过 bash 执行（PowerShell 远端引号会坏）；`docker restart datara-web` 在替换挂载 inode 后必须执行；commit 步骤执行前与用户确认（本会话未见用户明确授权过 git commit）。

---

## 第一批：缺陷修复

### Task 1: R1 前端保存字段名 + http 兜底文案

**Files:**
- Create: `datara-web/src/services/__tests__/baselineApi.save.test.ts`
- Modify: `datara-web/src/services/baselineApi.ts:125-129`
- Modify: `datara-web/src/services/http.ts:57`

- [ ] **Step 1: 写失败测试（请求体契约）**

```ts
// datara-web/src/services/__tests__/baselineApi.save.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'

const putSpy = vi.hoisted(() => vi.fn())
vi.mock('../http', () => ({
  http: { get: vi.fn(), put: putSpy, post: vi.fn() },
}))
vi.mock('../apiMode', () => ({ isMock: false }))

import { saveDraft } from '../baselineApi'

describe('saveDraft 请求体契约（后端 BaselineDraftBody 要求 snake_case）', () => {
  beforeEach(() => {
    putSpy.mockReset().mockResolvedValue({ draftRev: 2, specHash: 'abc', status: 'designing' })
  })

  it('发送 draft_rev（下划线）而非 draftRev', async () => {
    await saveDraft('sql', { draftRev: 1, spec: { fields: [] } })
    expect(putSpy).toHaveBeenCalledTimes(1)
    const body = putSpy.mock.calls[0][1] as Record<string, unknown>
    expect(body).toHaveProperty('draft_rev', 1)
    expect(body).not.toHaveProperty('draftRev')
    expect(body).toHaveProperty('spec')
  })

  it('remark 传入时透传', async () => {
    await saveDraft('sql', { draftRev: 1, spec: {}, remark: 'r1' })
    const body = putSpy.mock.calls[0][1] as Record<string, unknown>
    expect(body).toHaveProperty('remark', 'r1')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd datara-web && npx vitest run src/services/__tests__/baselineApi.save.test.ts`
Expected: FAIL（`body` 无 `draft_rev`，实际是 `draftRev`）

- [ ] **Step 3: 修 baselineApi.ts 请求体**

`baselineApi.ts` L125-129 改为：

```ts
  return http.put<BaselineSaveResult>(`/components/baseline/${encodeURIComponent(type)}/draft`, {
    draft_rev: body.draftRev,
    spec: body.spec,
    ...(body.remark !== undefined ? { remark: body.remark } : {}),
  })
```

- [ ] **Step 4: 跑测试确认通过**

Run: `npx vitest run src/services/__tests__/baselineApi.save.test.ts`
Expected: PASS（2/2）

- [ ] **Step 5: http.ts 兜底文案**

`http.ts` L57 改为（杜绝 code=undefined 文案再现）：

```ts
      const err = new Error(json.msg || `响应格式异常（HTTP ${res.status}）`) as Error & { code?: number; data?: unknown }
```

- [ ] **Step 6: 全量回归**

Run: `npx vitest run && npx vue-tsc -b`
Expected: 全绿、0 类型错

- [ ] **Step 7: Commit（先与用户确认）**

```bash
git add datara-web/src/services/baselineApi.ts datara-web/src/services/http.ts datara-web/src/services/__tests__/baselineApi.save.test.ts
git commit -m "fix(baseline): saveDraft 请求体 draftRev→draft_rev（pydantic 422 根因），http 兜底文案去 code=undefined"
```

### Task 2: R3 后端 published 底稿保存拦截

**Files:**
- Modify: `datara-backend/api/baseline.py:429-432`（save_baseline_draft）
- Test: `datara-backend/tests/test_baseline.py`（追加用例；fixture=`client`，角色切换用 `set_role`，造底稿用 `_legal_spec()`——文件内既有模式）

- [ ] **Step 1: 写失败测试（追加到 tests/test_baseline.py 末尾）**

```python
# ---------------- 修订前置：published 底稿不可直接改（R3） ----------------


def test_save_draft_rejected_on_published(client):
    """已认可发版的 type：PUT draft 必须 409/6002，底稿不被改写。"""
    set_role(client, "admin")
    # 造已发版：保存底稿 → 认可发 v1（既有用例同款两步）
    r = client.put("/api/v1/components/baseline/sql/draft",
                   json={"draft_rev": 0, "spec": _legal_spec()})
    assert r.status_code == 200, r.text
    r = client.post("/api/v1/components/sql/baseline/publish", json={})
    assert r.status_code == 200, r.text
    # 发版后再保存 → 409
    r = client.put("/api/v1/components/baseline/sql/draft",
                   json={"draft_rev": 1, "spec": _legal_spec()})
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == 6002
    # 且底稿未被改写：draft_rev 仍为 1、status 仍 published
    r = client.get("/api/v1/components/baseline/sql/draft")
    assert r.json()["data"]["status"] == "published"
    assert r.json()["data"]["draftRev"] == 1
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd datara-backend && python -m pytest tests/test_baseline.py::test_save_draft_rejected_on_published -v`
Expected: FAIL（当前实现 rev 匹配时返回 200）

- [ ] **Step 3: 实现——save_baseline_draft 加 status 检查**

`baseline.py` save_baseline_draft 中，`current_rev = row.draft_rev if row else 0` 之后、乐观锁检查之前插入：

```python
    if row is not None and row.status == "published":
        # 基线一次性：已发版底稿不可直接改写（修订走 redraft 端点，第二批上线）
        raise ApiError(COMP_STATE_CONFLICT, status=409,
                       msg="type「%s」已发版，底稿不可直接修改（修订能力即将上线）" % type_name)
```

- [ ] **Step 4: 跑测试确认通过 + 文件回归**

Run: `python -m pytest tests/test_baseline.py -v`
Expected: 全过（新用例 + 既有用例无回归）

- [ ] **Step 5: Commit（先与用户确认）**

```bash
git add datara-backend/api/baseline.py datara-backend/tests/test_baseline.py
git commit -m "fix(baseline): published 底稿保存 409 拦截（防静默改写，治理 R3）"
```

### Task 3: R2 M1 设计器 builtin 引导

**Files:**
- Modify: `datara-web/src/views/meta/ComponentDesignView.vue`（loadDraft L93-110 + 模板 L591 附近 + script 顶部 state）
- Test: Create `datara-web/src/views/meta/__tests__/ComponentDesignView.builtin.test.ts`

- [ ] **Step 1: 写失败测试**

```ts
// datara-web/src/views/meta/__tests__/ComponentDesignView.builtin.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const getDraftSpy = vi.hoisted(() => vi.fn())
const versionsSpy = vi.hoisted(() => vi.fn())
const getCompSpy = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { type: 'sql' }, query: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))
vi.mock('../../../services/componentApi', () => ({
  getComponentDraft: getDraftSpy,
  listComponentVersions: versionsSpy,
  getComponent: getCompSpy,
}))
vi.mock('../../../services/componentDesignApi', () => ({ validateSpecPureData: () => [] }))

import ComponentDesignView from '../ComponentDesignView.vue'

describe('M1 设计器对 builtin 组件引导（R2）', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // 无草稿行：draft 409（6002）；详情返回 builtin
    getDraftSpy.mockRejectedValue(Object.assign(new Error('无进行中的草稿，请新建草稿版本'), { code: 6002 }))
    versionsSpy.mockResolvedValue({ items: [{ version: 1, state: 'published', specHash: 'h', remark: '' }] })
    getCompSpy.mockResolvedValue({ type: 'sql', scope: 'builtin' })
  })

  it('409(6002) + scope=builtin → 显示引导而非报错', async () => {
    const w = mount(ComponentDesignView)
    await flushPromises()
    expect(w.text()).toContain('内置组件')
    expect(w.text()).toContain('基线化工作台')
    expect(w.text()).not.toContain('草稿加载失败')
  })
})
```

- [ ] **Step 2: 跑测试确认失败**

Run: `cd datara-web && npx vitest run src/views/meta/__tests__/ComponentDesignView.builtin.test.ts`
Expected: FAIL（当前显示「草稿加载失败」）

- [ ] **Step 3: 实现**

ComponentDesignView.vue script（loadDraft 附近）加 state 与判断：

```ts
/** R2：409(6002) 且该 type 为 builtin → 引导至基线化工作台（内置组件无 M1 草稿链） */
const builtinGuide = ref<{ type: string } | null>(null)
```

`loadDraft` 的 catch 改为：

```ts
  } catch (e) {
    const code = (e as { code?: number }).code
    loadErr.value = e instanceof Error ? e.message : String(e)
    draft.value = null
    versions.value = []
    if (code === 6002) {
      try {
        const d = await getComponent(t)
        if (d.scope === 'builtin') builtinGuide.value = { type: t }
      } catch { /* 详情失败则维持原报错展示 */ }
    }
  } finally {
```

（`getComponent` 加入文件顶部既有 `from '../../../services/componentApi'` import 列表；`builtinGuide` 在 loadDraft 成功路径开头重置为 `null`。）

模板 L591 alert 前加引导块：

```vue
    <el-alert v-if="builtinGuide" type="warning" :closable="false" show-icon class="err-alert"
      title="内置组件请到基线化工作台修订">
      <template #default>
        「{{ builtinGuide.type }}」为基线化内置组件（已发版留档，无用户草稿链）。
        <el-button link type="primary"
          @click="router.push({ path: '/meta/baseline', query: { type: builtinGuide.type } })">
          前往基线化工作台</el-button>
      </template>
    </el-alert>
    <el-alert v-if="loadErr && !builtinGuide" type="error" :closable="false" :title="`草稿加载失败：${loadErr}`" show-icon class="err-alert" />
```

- [ ] **Step 4: 跑测试确认通过 + 全量回归**

Run: `npx vitest run src/views/meta/__tests__/ComponentDesignView.builtin.test.ts && npx vitest run && npx vue-tsc -b`
Expected: 新用例 PASS、全量无回归、0 类型错

- [ ] **Step 5: Commit（先与用户确认）**

```bash
git add datara-web/src/views/meta/ComponentDesignView.vue datara-web/src/views/meta/__tests__/ComponentDesignView.builtin.test.ts
git commit -m "fix(meta): M1 设计器 builtin 组件 409 引导至基线化工作台（R2）"
```

### Task 4: 第一批 1.9 部署与验证

- [ ] **Step 1: 后端测试全量**

Run: `cd datara-backend && python -m pytest -q`
Expected: 全过（基线 260+ 新增）

- [ ] **Step 2: 前端构建 + 打包传输**

```bash
cd datara-web && npm run build
tar -czf "$env:TEMP\dist_fix1.tgz" -C dist .
scp "$env:TEMP\dist_fix1.tgz" root@192.168.1.9:/tmp/dist_fix1.tgz
```

- [ ] **Step 3: 后端代码同步 1.9（api/baseline.py 单文件，容器内直换）**

写脚本 scp 执行（铁律：不裸写远端引号命令）：

```bash
#!/bin/bash
scp 本地先传: scp datara-backend/api/baseline.py root@192.168.1.9:/tmp/baseline_new.py
# 1.9 上（脚本内）：
docker cp /tmp/baseline_new.py datara-api:/app/api/baseline.py
docker restart datara-api datara-master datara-worker datara-logger datara-alert
sleep 5
docker ps --format '{{.Names}}\t{{.Status}}'
```

- [ ] **Step 4: dist 双写 + 重启 web（挂载 inode 惯例）**

```bash
#!/bin/bash
rm -rf /mnt/lei/datara/datara-web/dist-new /mnt/lei/datara/datara-web/dist
mkdir -p /mnt/lei/datara/datara-web/dist-new /mnt/lei/datara/datara-web/dist
tar -xzf /tmp/dist_fix1.tgz -C /mnt/lei/datara/datara-web/dist-new
tar -xzf /tmp/dist_fix1.tgz -C /mnt/lei/datara/datara-web/dist
docker restart datara-web && sleep 2
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8090/
```

- [ ] **Step 5: API 冒烟（登录 → published 保存 409 → designing 保存 200）**

```bash
#!/bin/bash
TOK=$(curl -s -X POST http://127.0.0.1:8000/api/v1/login -H 'Content-Type: application/json' -d '{"user_name":"admin","user_pwd":"Admin@123"}' | grep -o '"token":"[^"]*' | cut -d'"' -f4)
# published（sql）→ 409/6002
curl -s -o /dev/null -w 'published save: %{http_code}\n' -X PUT http://127.0.0.1:8000/api/v1/components/baseline/sql/draft -H "Authorization: Bearer $TOK" -H 'Content-Type: application/json' -d '{"draft_rev":1,"spec":{}}'
```
Expected: `published save: 409`；首页 200；五后端 healthy。

---

## 第二批：修订轮次功能

### Task 5: progress 响应增加 publishedVersion

**Files:**
- Modify: `datara-backend/api/baseline.py`（baseline_progress，L356-387）
- Test: `datara-backend/tests/test_baseline.py`

- [ ] **Step 1: 失败测试（追加）**

```python
def test_progress_contains_published_version(client):
    """published 类型进度行带 publishedVersion；未发为 0。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    client.post("/api/v1/components/sql/baseline/publish", json={})
    r = client.get("/api/v1/components/baseline/progress")
    items = {i["type"]: i for i in r.json()["data"]["items"]}
    assert items["sql"]["publishedVersion"] == 1
    assert items["start"]["publishedVersion"] == 0
```

- [ ] **Step 2: 跑失败** — `pytest tests/test_baseline.py::test_progress_contains_published_version -v` → FAIL（无字段）

- [ ] **Step 3: 实现** — baseline_progress 的 items.append 里 `r` 查询后左联组件表，加字段：

```python
    comp_rows = {c.type: c for c in db.query(Component).filter(Component.scope == "builtin").all()}
```
items.append 字典内加：
```python
            "publishedVersion": (comp_rows[c["type"]].published_version or 0) if c.get("type") in comp_rows else 0,
```

- [ ] **Step 4: 跑过** → PASS。 **Step 5: Commit（确认后）**

### Task 6: redraft 端点（复制上版开修订）

**Files:**
- Modify: `datara-backend/api/baseline.py`（save_baseline_draft 之后新增端点）
- Test: `tests/test_baseline.py`

- [ ] **Step 1: 失败测试**

```python
def test_redraft_copies_published_spec(client):
    """published → redraft：复制最新 published spec 为底稿，rev+1，status=designing，log 记 redraft。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    r = client.post("/api/v1/components/sql/baseline/publish", json={})
    published_spec = client.get("/api/v1/components/baseline/sql/draft").json()["data"]["spec"]
    # 开修订
    r = client.post("/api/v1/components/sql/baseline/redraft", json={"remark": "修订第一轮"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["status"] == "designing"
    assert d["fromVersion"] == 1
    assert d["draftRev"] == 2  # published 时 rev=1，redraft +1
    # 底稿 = 上版内容
    cur = client.get("/api/v1/components/baseline/sql/draft").json()["data"]
    assert cur["spec"] == published_spec
    # 修订中可正常保存（rev=2 → 3）
    r = client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 2, "spec": _legal_spec()})
    assert r.status_code == 200


def test_redraft_requires_published(client):
    """designing（未发版）redraft → 409；published 后修订中再 redraft → 409。"""
    set_role(client, "admin")
    r = client.post("/api/v1/components/start/baseline/redraft", json={})
    assert r.status_code == 404  # 无进度行
    client.put("/api/v1/components/baseline/notify/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    r = client.post("/api/v1/components/notify/baseline/redraft", json={})
    assert r.status_code == 409  # designing 且未发版
```

- [ ] **Step 2: 跑失败**（404 路由不存在）

- [ ] **Step 3: 实现（save 端点后新增）**

```python
@router.post("/baseline/{type_name}/redraft", summary="复制最新已发版 spec 开修订轮（published→designing）")
def redraft_baseline(
    type_name: str,
    body: BaselineRedraftBody,
    user: User = Depends(require_perm("design_component")),
    db: Session = Depends(get_db),
):
    """修订开轮：取最新 published 版 spec 写回底稿（复制上版），rev+1，status 回 designing；log 记 redraft。"""
    if type_name not in _dag_types():
        raise ApiError(COMP_NOT_FOUND, status=404, msg="type「%s」不在基线化目录内" % type_name)
    row = db.query(BaselineProgress).filter(BaselineProgress.type == type_name).first()
    if row is None:
        raise ApiError(COMP_NOT_FOUND, status=404, msg="type「%s」无基线化进度行" % type_name)
    if row.status != "published":
        raise ApiError(COMP_STATE_CONFLICT, status=409,
                       msg="type「%s」当前状态 %s，仅已发版可开修订" % (type_name, row.status))
    comp = db.query(Component).filter(Component.type == type_name).first()
    if comp is None:
        raise ApiError(COMP_STATE_CONFLICT, status=409, msg="type「%s」无已发版组件行" % type_name)
    ver = (db.query(ComponentVersion)
           .filter(ComponentVersion.component_id == comp.id, ComponentVersion.state == "published")
           .order_by(ComponentVersion.version.desc()).first())
    if ver is None:
        raise ApiError(COMP_STATE_CONFLICT, status=409, msg="type「%s」无已发布版本可复制" % type_name)
    row.draft_spec = ver.spec_json
    row.draft_rev = (row.draft_rev or 0) + 1
    row.status = "designing"
    db.add(ComponentLog(
        component_id=comp.id, type=type_name, version=ver.version, action="redraft",
        spec_hash=ver.spec_hash, operator=user.user_name,
        remark=body.remark or "复制 v%d 开修订轮" % ver.version,
    ))
    db.commit()
    logger.info("开修订轮: %s（复制 v%d，rev=%d，操作人 %s）",
                type_name, ver.version, row.draft_rev, user.user_name)
    return ok({"draftRev": row.draft_rev, "status": row.status, "fromVersion": ver.version,
               "specHash": ver.spec_hash})


class BaselineRedraftBody(BaseModel):
    remark: Optional[str] = None
```

（`BaselineRedraftBody` 与其他 Body 类同区放置；`Component`/`ComponentVersion`/`ComponentLog` 文件内已 import。）

- [ ] **Step 4: 跑过** `pytest tests/test_baseline.py -v` 全过。 **Step 5: Commit（确认后）**

### Task 7: publish 端点支持 vN（修订发布）

**Files:**
- Modify: `datara-backend/api/baseline.py`（publish_baseline L506-547）
- Test: `tests/test_baseline.py`

- [ ] **Step 1: 失败测试**

```python
def test_publish_revision_creates_v2(client):
    """修订中（designing + 已发 v1）认可 → v2：新版本行 + published_version 更新 + v1 留档。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    client.post("/api/v1/components/sql/baseline/publish", json={})
    client.post("/api/v1/components/sql/baseline/redraft", json={})
    # 改底稿（rev=2 → 3）再发布
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 2, "spec": _legal_spec()})
    r = client.post("/api/v1/components/sql/baseline/publish", json={"remark": "修订发布"})
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["publishedVersion"] == 2
    # 版本行两枚且均 published（v1 留档）
    r = client.get("/api/v1/components/sql/versions")
    vers = r.json()["data"]["items"]
    assert [v["version"] for v in vers] == [2, 1]
    assert all(v["state"] == "published" for v in vers)
    # 进度行回 published；重复认可仍 409
    assert client.get("/api/v1/components/baseline/sql/draft").json()["data"]["status"] == "published"
    assert client.post("/api/v1/components/sql/baseline/publish", json={}).status_code == 409


def test_publish_still_rejected_when_published_no_revision(client):
    """status=published（未开修订）直接再认可 → 409 不变。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    client.post("/api/v1/components/sql/baseline/publish", json={})
    assert client.post("/api/v1/components/sql/baseline/publish", json={}).status_code == 409
```

- [ ] **Step 2: 跑失败**（当前 designing+已有组件行 → 409「已被占用」或 v1 硬编码）

- [ ] **Step 3: 实现** — publish_baseline 中，L509-512 的组件行占用检查改为分型：

```python
    comp = db.query(Component).filter(Component.type == type_name).first()
    if comp is not None and row.status != "designing":
        # published 态重复认可（未开修订）→ 治理一次性
        raise ApiError(COMP_STATE_CONFLICT, status=409,
                       msg="type「%s」已认可发过 v%d（修订请先开修订轮）" % (type_name, comp.published_version))
```

L524-532 的写入段改为按首发/修订分型（体检、spec_hash、check_report 逻辑全部复用不变）：

```python
    is_revision = comp is not None
    next_version = (comp.published_version + 1) if is_revision else 1
    if not is_revision:
        comp = Component(
            type=type_name, name=meta.get("label") or type_name,
            category=(meta.get("categories") or [None])[0],
            profile="dag", scope="builtin", execution_model=meta.get("executionModel") or "dag-engine",
            executor=meta.get("executor"), executable=True, state="published",
            published_version=1, draft_rev=0, description=meta.get("desc"),
        )
        db.add(comp)
        db.flush()  # 取 comp.id
    else:
        comp.published_version = next_version
        db.flush()
    db.add(ComponentVersion(
        component_id=comp.id, type=type_name, version=next_version, state="published",
        spec_json=json.dumps(spec, ensure_ascii=False), spec_hash=spec_hash,
        remark=body.remark, published_by=user.user_name, published_time=now(),
    ))
    db.add(ComponentLog(
        component_id=comp.id, type=type_name, version=next_version, action="publish",
        spec_hash=spec_hash, operator=user.user_name,
        remark=body.remark or ("基线化认可，发 v%d" % next_version),
    ))
```

返回体 `"publishedVersion": 1` → `"publishedVersion": next_version`；日志文案同步。

- [ ] **Step 4: 跑过** 全量 `pytest tests/test_baseline.py -v`（含首发型回归用例）。 **Step 5: Commit（确认后）**

### Task 8: discard_draft 端点（放弃修订）

**Files:**
- Modify: `datara-backend/api/baseline.py`（redraft 之后）
- Test: `tests/test_baseline.py`

- [ ] **Step 1: 失败测试**

```python
def test_discard_revision_restores_published(client):
    """修订中放弃：底稿重置为最新 published 版，status 回 published，log 记 discard。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    client.post("/api/v1/components/sql/baseline/publish", json={})
    published_spec = client.get("/api/v1/components/baseline/sql/draft").json()["data"]["spec"]
    client.post("/api/v1/components/sql/baseline/redraft", json={})
    client.put("/api/v1/components/baseline/sql/draft", json={"draft_rev": 2, "spec": _legal_spec()})
    r = client.post("/api/v1/components/sql/baseline/discard_draft", json={})
    assert r.status_code == 200
    d = client.get("/api/v1/components/baseline/sql/draft").json()["data"]
    assert d["status"] == "published"
    assert d["spec"] == published_spec  # 重置为上版内容
    assert d["draftRev"] == 4  # redraft 2 → 保存 3 → discard 4（连续递增）


def test_discard_rejected_when_not_revision(client):
    """首发型 designing / 未发版 discard → 409。"""
    set_role(client, "admin")
    client.put("/api/v1/components/baseline/notify/draft", json={"draft_rev": 0, "spec": _legal_spec()})
    assert client.post("/api/v1/components/notify/baseline/discard_draft", json={}).status_code == 409
```

- [ ] **Step 2: 跑失败**（404）

- [ ] **Step 3: 实现（redraft 端点后新增）**

```python
@router.post("/baseline/{type_name}/discard_draft", summary="放弃修订（底稿重置为最新已发版，status 回 published）")
def discard_baseline_revision(
    type_name: str,
    user: User = Depends(require_perm("design_component")),
    db: Session = Depends(get_db),
):
    """仅修订中（designing + 已有 published 组件行）可放弃；draft_rev 连续递增，log 记 discard。"""
    if type_name not in _dag_types():
        raise ApiError(COMP_NOT_FOUND, status=404, msg="type「%s」不在基线化目录内" % type_name)
    row = db.query(BaselineProgress).filter(BaselineProgress.type == type_name).first()
    comp = db.query(Component).filter(Component.type == type_name).first()
    if row is None or comp is None or row.status != "designing":
        raise ApiError(COMP_STATE_CONFLICT, status=409,
                       msg="type「%s」不在修订中，无可放弃草稿" % type_name)
    ver = (db.query(ComponentVersion)
           .filter(ComponentVersion.component_id == comp.id, ComponentVersion.state == "published")
           .order_by(ComponentVersion.version.desc()).first())
    if ver is None:
        raise ApiError(COMP_STATE_CONFLICT, status=409, msg="type「%s」无已发布版本" % type_name)
    row.draft_spec = ver.spec_json
    row.draft_rev = (row.draft_rev or 0) + 1
    row.status = "published"
    db.add(ComponentLog(
        component_id=comp.id, type=type_name, version=ver.version, action="discard",
        spec_hash=ver.spec_hash, operator=user.user_name, remark="放弃修订，回滚底稿至 v%d" % ver.version,
    ))
    db.commit()
    logger.info("放弃修订: %s（底稿重置至 v%d，操作人 %s）", type_name, ver.version, user.user_name)
    return ok({"status": row.status, "draftRev": row.draft_rev})
```

- [ ] **Step 4: 跑过** 全量。 **Step 5: Commit（确认后）**

### Task 9: 前端 API + 工作台三态交互

**Files:**
- Modify: `datara-web/src/services/baselineApi.ts`（新增 redraft/discardDraft + BaselineProgressRow.publishedVersion）
- Modify: `datara-web/src/views/meta/BaselineWorkbenchView.vue`（三态按钮）
- Test: `datara-web/src/services/__tests__/baselineApi.save.test.ts`（追加）+ 工作台既有测试文件

- [ ] **Step 1: API 层（类型 + 两函数，追加至 baselineApi.ts）**

```ts
/** 进度行扩展：已发版本号（0=未发）；修订中 = status==='designing' && publishedVersion>0 */
export interface BaselineProgressRow { /* 既有字段不变，追加 */ publishedVersion: number }

/** 复制最新已发版 spec 开修订轮（published→designing） */
export async function redraftBaseline(type: string, remark?: string): Promise<{ draftRev: number; status: BaselineStatus; fromVersion: number; specHash: string }> {
  return http.post(`/components/baseline/${encodeURIComponent(type)}/redraft`, remark ? { remark } : {})
}

/** 放弃修订（底稿重置为最新已发版） */
export async function discardBaselineRevision(type: string): Promise<{ status: BaselineStatus; draftRev: number }> {
  return http.post(`/components/baseline/${encodeURIComponent(type)}/discard_draft`, {})
}
```

（BaselineProgressRow 接口在既有定义处追加 `publishedVersion: number` 字段，不新建接口。）

- [ ] **Step 2: save.test.ts 追加 API 契约用例**

```ts
import { saveDraft, redraftBaseline, discardBaselineRevision } from '../baselineApi'
// putSpy 同 Task1；新增 postSpy mock（vi.hoisted）

it('redraftBaseline POST /baseline/{t}/redraft', async () => {
  await redraftBaseline('sql', '轮一')
  expect(postSpy).toHaveBeenCalledWith('/components/baseline/sql/redraft', { remark: '轮一' })
})

it('discardBaselineRevision POST /baseline/{t}/discard_draft 空 body', async () => {
  await discardBaselineRevision('sql')
  expect(postSpy).toHaveBeenCalledWith('/components/baseline/sql/discard_draft', {})
})
```

- [ ] **Step 3: 工作台三态**（BaselineWorkbenchView.vue）

新增 state 与动作（onSave/onPublish 同区）：

```ts
/** 修订中 = 已发版 + designing；publishedVersion 来自 progress 行 */
const publishedVersion = computed(() => curRow.value?.publishedVersion ?? 0)
const isRevising = computed(() => d.value?.status === 'designing' && publishedVersion.value > 0)

/** 复制最新已发版开修订轮 */
async function onRedraft(): Promise<void> {
  if (!selectedType.value || publishing.value) return
  try {
    await ElMessageBox.confirm(
      `复制已发 v${publishedVersion.value} 底稿开修订轮：底稿转为可编辑，registry 继续供给 v${publishedVersion.value}。确认开修订？`,
      '开修订轮', { type: 'info', confirmButtonText: '复制 v' + publishedVersion.value + ' 开修订', cancelButtonText: '取消' })
  } catch { return }
  const r = await redraftBaseline(selectedType.value)
  ElMessage.success(`已复制 v${r.fromVersion} 开修订（rev=${r.draftRev}）`)
  await loadDraft(selectedType.value)
}

/** 放弃修订：底稿重置回最新已发版 */
async function onDiscard(): Promise<void> {
  if (!selectedType.value) return
  try {
    await ElMessageBox.confirm('放弃修订：底稿将重置为最新已发版内容（修订改动丢弃）。确认放弃？',
      '放弃修订', { type: 'warning', confirmButtonText: '放弃修订', cancelButtonText: '继续编辑' })
  } catch { return }
  await discardBaselineRevision(selectedType.value)
  ElMessage.success('已放弃修订，底稿回到已发版')
  await loadDraft(selectedType.value)
}
```

保存栏（L346-349）与发布区按钮按三态切换：

```vue
          <div class="save-bar">
            <!-- published：只读 + 开修订入口；修订中/未发：可编辑保存 -->
            <el-button v-if="d?.status === 'published'" type="primary" @click="onRedraft">复制 v{{ publishedVersion }} 开修订</el-button>
            <template v-else>
              <el-button type="primary" :loading="saving" @click="onSave">保存底稿</el-button>
              <el-button v-if="isRevising" @click="onDiscard">放弃修订</el-button>
              <span class="muted">乐观锁保护：rev 冲突（409）时自动重拉最新底稿，请合并后重试</span>
            </template>
          </div>
```

发布按钮文案：`认可发 v1` → `认可发 v{{ publishedVersion + 1 }}`（确认框文案同步：`以当前底稿发布 v{{ publishedVersion + 1 }}，v{{ publishedVersion }} 留档，registry 供给切换至新版`）；发布成功消息 `已发 v${r.publishedVersion}`。修订中发布入口保持可见（isRevising 时亦可发布）。

- [ ] **Step 4: 工作台测试更新**（既有 BaselineWorkbenchView.test.ts 追加）

```ts
it('published 态：编辑器只读 + 「复制 v1 开修订」按钮可见', async () => {
  const w = mountView()
  await flushPromises()
  await w.vm.select?.('sql') // 或按既有测试的选中方式
  await flushPromises()
  expect(w.text()).toContain('复制 v1 开修订')
})
```

（选中方式对齐该文件既有用例；mock 的 getDraftSpy 返回 status:'published'、progress 行 sql.publishedVersion=1——PROGRESS 快照补 `publishedVersion` 字段。）

- [ ] **Step 5: 全量回归** `npx vitest run && npx vue-tsc -b` 全绿。 **Step 6: Commit（确认后）**

### Task 10: 目录页分型回归 + M1 引导文案更新

**Files:**
- Modify: `datara-web/src/views/meta/ComponentCatalogView.vue`（按钮分型 + 空态引导）

- [ ] **Step 1: 按钮分型扩展**——「修改/查看」判断加修订中（修订中显示「修改」）：

```vue
          <el-button link type="primary" size="small" @click="router.push({ path: '/meta/baseline', query: { type: row.type } })">{{ baselineMap[row.type] === 'published' ? '查看' : '修改' }}</el-button>
```

（逻辑不变——修订中 status=designing 自然落入「修改」；仅需确认 baselineMap 数据源 progress 带 publishedVersion 后徽标区追加「修订中(vN 已发)」徽标：`v-else-if="row.publishedVersion > 0 && baselineMap[row.type] === 'designing'"`。）

- [ ] **Step 2: M1 设计器空态引导文案更新**（ComponentDesignView builtinGuide 文案第二批升级）：

```vue
      title="内置组件请到基线化工作台修订（支持复制上版开修订轮）"
```

- [ ] **Step 3: 全量回归 + Commit（确认后）**

### Task 11: 第二批 1.9 部署 + sql 全链实测 + 文档回写

- [ ] **Step 1: 后端全量 pytest + 前端 vitest/vue-tsc/build**
- [ ] **Step 2: 部署**（同 Task 4 步骤：baseline.py 容器直换 + 五后端重启 + dist 双写 + restart datara-web）
- [ ] **Step 3: 1.9 全链实测（写探针脚本容器内执行）**

```python
# mb_revision_e2e.py（datara-api 容器内）：sql 组件全链
# 1 redraft → 200 {fromVersion:1, draftRev:2}
# 2 PUT draft {draft_rev:2, spec:改 timeout 默认值} → 200 rev=3
# 3 POST check → 200 全项落库
# 4 POST baseline/publish {remark:"修订 v2 实测"} → 200 publishedVersion=2
# 5 GET versions → [v2, v1] 双 published
# 6 GET registry → sql publishedVersion=2
# 7 POST redraft → discard → status=published（丢弃轮验证）
# 其余 17 组件：GET progress 全量 publishedVersion 不变（sql=2 其余=1）
```

- [ ] **Step 4: 浏览器回归（Playwright/Edge，复用 hash 路由入口）**：工作台 sql「查看」→ 显示「复制 v1 开修订」→ 点击转可编辑 → 保存 → 发布文案「认可发 v2」
- [ ] **Step 5: 文档回写**：实施计划 §11 追加两批收口记录；组件基线化 README 台账追加「修订轮次能力上线」说明；spec 状态行更新为「已实施」
- [ ] **Step 6: 清理**：探针脚本自清（1.9 /tmp + 容器 /tmp + 本地 Temp）
