/**
 * INC4-FE-6 workflowGraph store 契约测试（draft 权威态 + R-25 差量保存）。
 *
 * 覆盖（真源 workflowApi 十方法 + workflowSaveQueue R-25 协调器 + 4-O4-04 证据件）：
 *  1. load：GET 回读 draft snake→camel 落地 + baseline 深拷贝锚定 + doc getter 形状；
 *     load 失败：lastError 记录、状态不落地、loading 复位；
 *  2. loadSeq 时序守卫：双 load 竞态仅最新响应落地，过期响应与过期错误一并丢弃；
 *  3. addNode：nodeCode 生成（空图 n1/n2 递增、断档取 max+1、删后号段复用）；
 *  4. removeNode：本地级联删触边（服务端 nodes/delete 同语义）+ 不存在 no-op；
 *  5. updateNode/moveNode：逐字段 patch（undefined 不覆盖）→ isDirty=true；
 *  6. addEdge：自环拒绝 + (from,to) 身份幂等；removeEdge；
 *  7. save 守卫与幂等：未加载 → null；无差异 → 零请求 complete 收口；
 *  8. save diff 派发：安全序 删边→删节点→upsert 节点→upsert 边（URL+body 对拍）
 *     → complete 收口（baseline 更新、isDirty=false）；
 *  9. save 部分失败：失败项 retryable-failed 保持 dirty、成功项 saved、baseline 不动
 *     → 重存收口（重存时删边 write 404 噪音由读回裁定吸收：read null=next → saved）；
 * 10. R-25 读回裁定：write 抛错但服务端已落地（超时隐藏已提交写）→ 读回=next → saved；
 * 11. R-25 补偿：读回失败 → compensate 恢复（previous=null → 删除）→ compensated 保持
 *     dirty 可重试；补偿失败 → recovery-failed 不自动重试（manualRecoveryKeys）；
 * 12. close：docId 匹配才清态（不匹配不动）；关后 doc=null、save=null。
 *
 * 范式：pinia（沿 dagTabs.contract）+ 模拟服务端（draft 可变状态：写端点应用变更、
 * 读端点回读全量——R-25 read 每次 write 后权威读回的镜像）+ 一次性故障注入
 * （failPostOnce/failReadOnce 前置失败、thenFailPostOnce 应用后断连）。
 * 多调用 fetch mock 必须 mockImplementation 每次新建 Response（happy-dom body 一次性）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useWorkflowGraphStore } from '../workflowGraph'

afterEach(() => vi.unstubAllGlobals())

/** 包络 2xx 响应（code=0 成功态）；每次调用新建 Response（body 一次性） */
const ENV = (data: unknown, status = 200) =>
  new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status })

interface WireNode {
  node_code: string
  node_type: string
  name: string | null
  params: Record<string, unknown> | null
  position_x: number | null
  position_y: number | null
}

interface WireEdge {
  from_node: string
  to_node: string
  name: string | null
}

/** wire 节点快捷构造（缺省 null 直传——对拍 upsert body 六键显式携带语义） */
const WN = (node_code: string, node_type: string, extra: Partial<WireNode> = {}): WireNode => ({
  node_code,
  node_type,
  name: null,
  params: null,
  position_x: null,
  position_y: null,
  ...extra,
})

const WE = (from_node: string, to_node: string, name: string | null = null): WireEdge => ({
  from_node,
  to_node,
  name,
})

/** GET /{id}?project_id 回读包络（definition_id=42 / project_id=7 固定锚） */
const GET_DEF = (name: string, nodes: WireNode[], edges: WireEdge[]) => ({
  definition_id: 42,
  project_id: 7,
  name,
  description: null,
  current_version: null,
  draft: { nodes, edges },
})

/**
 * 模拟服务端：draft 可变状态镜像 repository 语义——
 *  - POST /nodes、/edges：按身份 upsert（body 六键/四键直映）；
 *  - POST /nodes/delete、/edges/delete：按身份删除（节点级联删触边）；目标不存在 → 404
 *    （WF_NODE_NOT_FOUND / WF_EDGE_NOT_FOUND——供读回裁定吸收 404 噪音用例）；
 *  - GET /{id}?project_id：回读当前全量 draft（read 每次 write 后权威读回的镜像）。
 */
function makeServer(initialNodes: WireNode[], initialEdges: WireEdge[]) {
  const draft = { nodes: structuredClone(initialNodes), edges: structuredClone(initialEdges) }
  const calls: Array<{ method: string; url: string; body: Record<string, unknown> }> = []
  const failOnce: Array<(url: string, method: string) => boolean> = []
  const thenFailOnce: string[] = []
  const CONNECTION_LOST = () => ENV({ code: 500, msg: 'connection lost after commit' }, 500)
  const fetchMock = vi.fn().mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input instanceof Request ? input.url : input)
    const method = init?.method ?? 'GET'
    const body = typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : {}
    calls.push({ method, url, body })
    const fi = failOnce.findIndex((match) => match(url, method))
    if (fi !== -1) {
      failOnce.splice(fi, 1)
      return ENV({ code: 500, msg: 'injected failure' }, 500)
    }
    const tfIdx = thenFailOnce.findIndex((suffix) => method === 'POST' && url.endsWith(suffix))
    const applyThenFail = tfIdx !== -1
    if (applyThenFail) thenFailOnce.splice(tfIdx, 1)
    if (method === 'GET' && url.includes('/workflows/42?')) {
      return ENV(GET_DEF('客户画像', draft.nodes, draft.edges))
    }
    if (method === 'POST' && url.endsWith('/nodes')) {
      const wire: WireNode = {
        node_code: body.node_code as string,
        node_type: body.node_type as string,
        name: (body.name as string | null) ?? null,
        params: (body.params as Record<string, unknown> | null) ?? null,
        position_x: (body.position_x as number | null) ?? null,
        position_y: (body.position_y as number | null) ?? null,
      }
      const i = draft.nodes.findIndex((n) => n.node_code === wire.node_code)
      if (i === -1) draft.nodes.push(wire)
      else draft.nodes[i] = wire
      return applyThenFail ? CONNECTION_LOST() : ENV(wire)
    }
    if (method === 'POST' && url.endsWith('/nodes/delete')) {
      const exists = draft.nodes.some((n) => n.node_code === body.node_code)
      draft.nodes = draft.nodes.filter((n) => n.node_code !== body.node_code)
      draft.edges = draft.edges.filter((e) => e.from_node !== body.node_code && e.to_node !== body.node_code)
      if (!exists) return ENV({ code: 404, msg: 'WF_NODE_NOT_FOUND' }, 404)
      return applyThenFail ? CONNECTION_LOST() : ENV({ deleted: true })
    }
    if (method === 'POST' && url.endsWith('/edges')) {
      const wire: WireEdge = {
        from_node: body.from_node as string,
        to_node: body.to_node as string,
        name: (body.name as string | null) ?? null,
      }
      const i = draft.edges.findIndex((e) => e.from_node === wire.from_node && e.to_node === wire.to_node)
      if (i === -1) draft.edges.push(wire)
      else draft.edges[i] = wire
      return applyThenFail ? CONNECTION_LOST() : ENV(wire)
    }
    if (method === 'POST' && url.endsWith('/edges/delete')) {
      const exists = draft.edges.some((e) => e.from_node === body.from_node && e.to_node === body.to_node)
      draft.edges = draft.edges.filter((e) => !(e.from_node === body.from_node && e.to_node === body.to_node))
      if (!exists) return ENV({ code: 404, msg: 'WF_EDGE_NOT_FOUND' }, 404)
      return applyThenFail ? CONNECTION_LOST() : ENV({ deleted: true })
    }
    throw new Error(`unexpected ${method} ${url}`)
  })
  return {
    draft,
    calls,
    fetchMock,
    /** 一次性前置失败（write/read 任意段注入：不应用变更直接 500） */
    failPostOnce: (suffix: string) => {
      failOnce.push((url, method) => method === 'POST' && url.endsWith(suffix))
    },
    failReadOnce: () => {
      failOnce.push((url, method) => method === 'GET' && url.includes('/workflows/42?'))
    },
    /** 一次性应用后断连（变更已落库但响应丢失——超时隐藏已提交写） */
    thenFailPostOnce: (suffix: string) => {
      thenFailOnce.push(suffix)
    },
  }
}

type Server = ReturnType<typeof makeServer>

/** stub fetch + 加载定义 42（project_id 7 固定锚） */
async function loadVia(server: Server) {
  vi.stubGlobal('fetch', server.fetchMock)
  const store = useWorkflowGraphStore()
  await store.load(7, 42)
  return store
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('INC4-FE-6 workflowGraph：load 与本地编辑', () => {
  it('load：GET 回读 draft snake→camel 落地 + baseline 深拷贝锚定（isDirty=false）+ doc getter 形状', async () => {
    const server = makeServer(
      [WN('n1', 'SQL', { params: { sql: 'select 1' }, position_x: 100, position_y: 200 }), WN('n2', 'SYNC', { name: '同步' })],
      [WE('n1', 'n2')],
    )
    vi.stubGlobal('fetch', server.fetchMock)
    const store = useWorkflowGraphStore()
    await store.load(7, 42)
    expect(server.calls[0]).toMatchObject({ method: 'GET', url: '/api/v1/rebuild/workflows/42?project_id=7' })
    expect(store.docId).toBe(42)
    expect(store.projectId).toBe(7)
    expect(store.name).toBe('客户画像')
    expect(store.nodes[0]).toEqual({ nodeCode: 'n1', nodeType: 'SQL', name: null, params: { sql: 'select 1' }, positionX: 100, positionY: 200 })
    expect(store.nodes[1]).toEqual({ nodeCode: 'n2', nodeType: 'SYNC', name: '同步', params: null, positionX: null, positionY: null })
    expect(store.edges).toEqual([{ fromNode: 'n1', toNode: 'n2', name: null }])
    expect(store.loading).toBe(false)
    expect(store.lastError).toBe(null)
    // baseline 深拷贝：非同引用 → 本地编辑不串写基线
    expect(store.baseline).not.toBeNull()
    expect(store.baseline!.nodes[0]).not.toBe(store.nodes[0])
    expect(store.isDirty).toBe(false)
    // 宿主接驳面：TaskCenterView onCloseTab → graphStore.doc?.id === t.docId
    expect(store.doc).toEqual({ id: 42, projectId: 7, name: '客户画像' })
  })

  it('load 失败：lastError 记录、状态不落地、loading 复位', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ENV({ code: 404, msg: 'WF_NOT_FOUND' }, 404)))
    const store = useWorkflowGraphStore()
    await store.load(7, 42)
    expect(store.lastError).toBeTruthy()
    expect(store.docId).toBe(null)
    expect(store.nodes).toEqual([])
    expect(store.loading).toBe(false)
    expect(store.doc).toBe(null)
  })

  it('loadSeq 时序守卫：双 load 竞态仅最新响应落地，过期响应与过期错误一并丢弃', async () => {
    const pending: Array<{ res: (r: Response) => void; rej: (e: unknown) => void }> = []
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => new Promise<Response>((res, rej) => { pending.push({ res, rej }) })),
    )
    const store = useWorkflowGraphStore()
    const p1 = store.load(7, 42)
    const p2 = store.load(7, 42)
    expect(pending).toHaveLength(2)
    expect(store.loading).toBe(true)
    // 新响应（第二次）先落地
    pending[1].res(ENV(GET_DEF('新名', [WN('n9', 'SQL')], [])))
    await p2
    expect(store.name).toBe('新名')
    expect(store.nodes).toHaveLength(1)
    // 旧响应（第一次）迟到 → 丢弃
    pending[0].res(ENV(GET_DEF('旧名', [], [])))
    await p1
    expect(store.name).toBe('新名')
    expect(store.nodes).toHaveLength(1)
    expect(store.loading).toBe(false)
    expect(store.lastError).toBe(null)
    // 过期错误同样丢弃：p3 旧 / p4 新，p4 先落地、p3 后拒绝
    const p3 = store.load(7, 42)
    const p4 = store.load(7, 42)
    pending[3].res(ENV(GET_DEF('再新', [], [])))
    await p4
    pending[2].rej(new Error('过期请求失败'))
    await p3
    expect(store.name).toBe('再新')
    expect(store.lastError).toBe(null)
    expect(store.loading).toBe(false)
  })

  it('addNode：nodeCode 生成——空图 n1/n2 递增；断档取 max+1；删后号段复用', async () => {
    // 空图起步：n1、n2
    vi.stubGlobal('fetch', makeServer([], []).fetchMock)
    let store = useWorkflowGraphStore()
    await store.load(7, 42)
    expect(store.addNode({ nodeType: 'SQL' }).nodeCode).toBe('n1')
    expect(store.addNode({ nodeType: 'SQL' }).nodeCode).toBe('n2')
    // 断档 n1/n3 → n4
    vi.stubGlobal('fetch', makeServer([WN('n1', 'SQL'), WN('n3', 'SQL')], []).fetchMock)
    store = useWorkflowGraphStore()
    await store.load(7, 42)
    expect(store.addNode({ nodeType: 'SQL' }).nodeCode).toBe('n4')
    // 删后复用：n1/n2 删 n2 → 再加得 n2
    vi.stubGlobal('fetch', makeServer([WN('n1', 'SQL'), WN('n2', 'SQL')], []).fetchMock)
    store = useWorkflowGraphStore()
    await store.load(7, 42)
    store.removeNode('n2')
    expect(store.addNode({ nodeType: 'SQL' }).nodeCode).toBe('n2')
  })

  it('removeNode：本地级联删触边（与服务端 nodes/delete 同语义）；不存在 no-op', async () => {
    const server = makeServer(
      [WN('n1', 'SQL'), WN('n2', 'SQL'), WN('n3', 'SQL')],
      [WE('n1', 'n2'), WE('n2', 'n3'), WE('n1', 'n3')],
    )
    const store = await loadVia(server)
    store.removeNode('n2')
    expect(store.nodes.map((n) => n.nodeCode)).toEqual(['n1', 'n3'])
    expect(store.edges.map((e) => `${e.fromNode}->${e.toNode}`)).toEqual(['n1->n3'])
    expect(store.isDirty).toBe(true)
    store.removeNode('nX')
    expect(store.nodes).toHaveLength(2)
  })

  it('updateNode/moveNode：逐字段 patch（undefined 不覆盖）→ isDirty=true', async () => {
    const server = makeServer([WN('n1', 'SQL', { name: '原始', params: { sql: 'select 1' } })], [])
    const store = await loadVia(server)
    expect(store.isDirty).toBe(false)
    store.updateNode('n1', { name: '改名' })
    expect(store.nodes[0].name).toBe('改名')
    expect(store.nodes[0].params).toEqual({ sql: 'select 1' })
    expect(store.isDirty).toBe(true)
    store.updateNode('n1', {})
    expect(store.nodes[0].name).toBe('改名')
    store.moveNode('n1', 30, 40)
    expect(store.nodes[0].positionX).toBe(30)
    expect(store.nodes[0].positionY).toBe(40)
    store.updateNode('nX', { name: '幽灵' })
    expect(store.nodes).toHaveLength(1)
  })

  it('addEdge：自环拒绝 + (from,to) 身份幂等；removeEdge 删除', async () => {
    const server = makeServer([WN('n1', 'SQL'), WN('n2', 'SQL')], [])
    const store = await loadVia(server)
    expect(store.addEdge('n1', 'n1')).toBe(null)
    const e = store.addEdge('n1', 'n2', '串行')
    expect(e).toEqual({ fromNode: 'n1', toNode: 'n2', name: '串行' })
    expect(store.addEdge('n1', 'n2')).toBe(null)
    expect(store.edges).toHaveLength(1)
    expect(store.isDirty).toBe(true)
    store.removeEdge('n1', 'n2')
    expect(store.edges).toEqual([])
    store.removeEdge('n1', 'n2')
  })
})

describe('INC4-FE-6 workflowGraph：save diff 派发与 R-25 语义', () => {
  it('save 守卫与幂等：未加载 → null；无差异 → 零请求 complete 收口', async () => {
    const store = useWorkflowGraphStore()
    await expect(store.save()).resolves.toBeNull()
    const server = makeServer([], [])
    vi.stubGlobal('fetch', server.fetchMock)
    await store.load(7, 42)
    const before = server.calls.length
    const r = await store.save()
    expect(r?.complete).toBe(true)
    expect(r?.outcomes).toEqual([])
    expect(server.calls.length).toBe(before)
    expect(store.isDirty).toBe(false)
  })

  it('save diff 派发：安全序 删边→upsert 节点→upsert 边（URL+body 对拍、写读交替）→ complete 收口', async () => {
    const server = makeServer([WN('n1', 'SQL'), WN('n2', 'SYNC')], [WE('n1', 'n2')])
    const store = await loadVia(server)
    store.removeEdge('n1', 'n2')
    store.moveNode('n1', 10, 20)
    store.addNode({ nodeType: 'SQL', name: '新节点' })
    store.addEdge('n2', 'n3', '串行')
    const r = await store.save()
    expect(r?.complete).toBe(true)
    expect(r?.savedKeys).toEqual(['edge-del:n1->n2', 'node:n1', 'node:n3', 'edge:n2->n3'])
    expect(r?.dirtyKeys).toEqual([])
    // 派发序列：load 一次 + 每 delta 写+读回交替（4 delta → 8 次）
    expect(server.calls.map((c) => `${c.method} ${c.url}`)).toEqual([
      'GET /api/v1/rebuild/workflows/42?project_id=7',
      'POST /api/v1/rebuild/workflows/42/edges/delete',
      'GET /api/v1/rebuild/workflows/42?project_id=7',
      'POST /api/v1/rebuild/workflows/42/nodes',
      'GET /api/v1/rebuild/workflows/42?project_id=7',
      'POST /api/v1/rebuild/workflows/42/nodes',
      'GET /api/v1/rebuild/workflows/42?project_id=7',
      'POST /api/v1/rebuild/workflows/42/edges',
      'GET /api/v1/rebuild/workflows/42?project_id=7',
    ])
    expect(server.calls[1].body).toEqual({ project_id: 7, from_node: 'n1', to_node: 'n2' })
    expect(server.calls[3].body).toEqual({ project_id: 7, node_code: 'n1', node_type: 'SQL', name: null, params: null, position_x: 10, position_y: 20 })
    expect(server.calls[5].body).toEqual({ project_id: 7, node_code: 'n3', node_type: 'SQL', name: '新节点', params: null, position_x: null, position_y: null })
    expect(server.calls[7].body).toEqual({ project_id: 7, from_node: 'n2', to_node: 'n3', name: '串行' })
    // complete 收口：baseline 更新、lastError 清、isDirty=false、lastSaveResult 记录
    expect(store.isDirty).toBe(false)
    expect(store.lastError).toBe(null)
    expect(store.lastSaveResult?.complete).toBe(true)
    expect(store.baseline?.nodes.map((n) => n.nodeCode)).toEqual(['n1', 'n2', 'n3'])
    expect(store.baseline?.edges.map((e) => `${e.fromNode}->${e.toNode}`)).toEqual(['n2->n3'])
  })

  it('save 部分失败：失败项 retryable-failed 保持 dirty、成功项 saved、baseline 不动 → 重存收口（404 噪音读回吸收）', async () => {
    const server = makeServer([WN('n1', 'SQL'), WN('n2', 'SYNC')], [WE('n1', 'n2')])
    const store = await loadVia(server)
    store.removeNode('n1')
    server.failPostOnce('/edges/delete')
    const r1 = await store.save()
    expect(r1?.complete).toBe(false)
    expect(r1?.savedKeys).toEqual(['node-del:n1'])
    expect(r1?.dirtyKeys).toEqual(['edge-del:n1->n2'])
    expect(r1?.outcomes[0]).toMatchObject({ key: 'edge-del:n1->n2', status: 'retryable-failed', dirty: true, retryable: true })
    expect(store.lastError).toContain('edge-del:n1->n2')
    // baseline 不动：isDirty 仍 true（本地编辑保留，未回滚）
    expect(store.isDirty).toBe(true)
    expect(store.baseline?.nodes.map((n) => n.nodeCode)).toEqual(['n1', 'n2'])
    // 重存：服务端边已被节点删除级联清掉 → 删边 write 404 → 读回 null=next → saved（幂等吸收）
    const r2 = await store.save()
    expect(r2?.complete).toBe(true)
    expect(r2?.savedKeys).toEqual(['edge-del:n1->n2', 'node-del:n1'])
    expect(store.isDirty).toBe(false)
    expect(store.lastError).toBe(null)
  })

  it('R-25 读回裁定：write 抛错但服务端已落地（超时隐藏已提交写）→ 读回=next → saved', async () => {
    const server = makeServer([WN('n1', 'SQL')], [])
    const store = await loadVia(server)
    store.moveNode('n1', 5, 6)
    server.thenFailPostOnce('/nodes')
    const r = await store.save()
    expect(r?.complete).toBe(true)
    expect(r?.savedKeys).toEqual(['node:n1'])
    expect(r?.dirtyKeys).toEqual([])
    expect(store.isDirty).toBe(false)
    expect(store.lastError).toBe(null)
    expect(server.draft.nodes[0].position_x).toBe(5)
  })

  it('R-25 补偿：write 落地后断连 + 读回失败 → compensate 恢复（previous=null → 删除）→ compensated 保持 dirty 可重试', async () => {
    const server = makeServer([], [])
    const store = await loadVia(server)
    store.addNode({ nodeType: 'SQL', name: '新节点' })
    server.thenFailPostOnce('/nodes')
    server.failReadOnce()
    const r = await store.save()
    expect(r?.complete).toBe(false)
    expect(r?.outcomes[0]).toMatchObject({ key: 'node:n1', status: 'compensated', dirty: true, retryable: true })
    expect(r?.manualRecoveryKeys).toEqual([])
    expect(store.isDirty).toBe(true)
    // 补偿动作真实发生：服务端节点被删除回滚
    expect(server.draft.nodes).toHaveLength(0)
    // 重存（store.save 重新 diff）→ 成功收口
    const r2 = await store.save()
    expect(r2?.complete).toBe(true)
    expect(server.draft.nodes.map((n) => n.node_code)).toEqual(['n1'])
    expect(store.isDirty).toBe(false)
  })

  it('R-25 补偿失败 → recovery-failed 不自动重试（manualRecoveryKeys 记录、baseline 不动）', async () => {
    const server = makeServer([], [])
    const store = await loadVia(server)
    store.addNode({ nodeType: 'SQL', name: '新节点' })
    // write 成功落地 → 读回注入失败 → compensate（previous=null → 删除）→ 删除注入失败 → recovery-failed
    server.failReadOnce()
    server.failPostOnce('/nodes/delete')
    const r = await store.save()
    expect(r?.complete).toBe(false)
    expect(r?.outcomes[0]).toMatchObject({ key: 'node:n1', status: 'recovery-failed', dirty: true, retryable: false })
    expect(r?.manualRecoveryKeys).toEqual(['node:n1'])
    expect(r?.dirtyKeys).toEqual(['node:n1'])
    expect(store.isDirty).toBe(true)
    expect(store.lastError).toContain('node:n1')
    // write 已落地且补偿删除失败：服务端节点仍在（未被误删）；baseline 不动
    expect(server.draft.nodes.map((n) => n.node_code)).toEqual(['n1'])
    expect(store.baseline!.nodes).toHaveLength(0)
  })
})

describe('INC4-FE-6 workflowGraph：close', () => {
  it('close：docId 匹配才清态（不匹配不动）；关后 doc=null、save=null', async () => {
    const server = makeServer([WN('n1', 'SQL')], [])
    const store = await loadVia(server)
    store.addNode({ nodeType: 'SQL' })
    store.close(999)
    expect(store.docId).toBe(42)
    expect(store.nodes).toHaveLength(2)
    store.close(42)
    expect(store.docId).toBe(null)
    expect(store.projectId).toBe(null)
    expect(store.name).toBe('')
    expect(store.nodes).toEqual([])
    expect(store.edges).toEqual([])
    expect(store.baseline).toBe(null)
    expect(store.doc).toBe(null)
    expect(store.isDirty).toBe(false)
    await expect(store.save()).resolves.toBeNull()
  })
})
