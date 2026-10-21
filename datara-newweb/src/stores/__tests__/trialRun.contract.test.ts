/**
 * INC4-FE-7 trialRun store 契约测试（options 表单态 + 运行结果 + 输出面）。
 *
 * 覆盖（真源 trialApi 七端点 + runner.TrialRunOptions WF-15~WF-20 + promote WF-21/WF-26）：
 *  1. 守卫：未 open（projectId null）四动作全 null 零请求；无 snapshot → run null；
 *     无 runResult → refreshOutput/promote null；
 *  2. open：绑定上下文 + 全量清态；二次进入换 definition 清旧态；
 *  3. createSnapshot：POST body {project_id} → 快照 snake→camel 落地（含 SKIPPED 形状无关，
 *     深拷贝锚定）；
 *  4. options 归一化：空表单 run body 无 options 键；部分键（仅 dryRun）→ options 单键；
 *  5. 八能力全量 run：options 六键 snake 对拍（node_codes/start_node/test_variables/
 *     dependency_mock/dry_run/sql_precheck）→ runResult 落地（含 SKIPPED 任务）；
 *  6. run 失败：lastError 记录、running 复位、runResult 不落地；
 *  7. loadSeq 时序守卫：双 run 竞态仅最新响应落地，过期响应与过期错误一并丢弃；
 *  8. refreshOutput：GET /runs/{id}?project_id= → output 落地；容错分支 stats {} → 0、
 *     缺 instance_type/status → null；
 *  9. promote：remark 带与不带 body 对拍（不带 → 无 remark 键）；幂等 idempotent 映射；
 * 10. open 在飞失效：run 在飞时二次 open → 响应过期丢弃、running 复位、全态清空。
 *
 * 范式：pinia + ENV 包络 + vi.stubGlobal('fetch')（多调用 mockImplementation 每次新建
 * Response——happy-dom body 一次性）；竞态用 pending promise 手工放行。
 * 固定锚：project_id=7 / definition_id=42 / snapshot_id=501 / instance_id=9001。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

import { useTrialRunStore } from '../trialRun'

afterEach(() => vi.unstubAllGlobals())

/** 包络 2xx 响应（code=0 成功态）；每次调用新建 Response（body 一次性） */
const ENV = (data: unknown, status = 200) =>
  new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status })

/* ---------- wire 夹具（repository/runner/promote/output 形状直映） ---------- */

const SNAPSHOT_WIRE = {
  snapshot_id: 501,
  definition_id: 42,
  snapshot_digest: 'dg-abc123',
  node_snapshot_json: [
    { node_code: 'n1', node_type: 'SQL', name: '取数', params: { sql: 'select 1' }, position_x: 10, position_y: 20 },
    { node_code: 'n2', node_type: 'SYNC', name: null, params: {}, position_x: null, position_y: null },
  ],
  edge_snapshot_json: [{ from_node: 'n1', to_node: 'n2', name: null }],
  status: 'ACTIVE',
  created_by: 3,
  created_at: '2026-10-21T10:00:00',
}

const RUN_WIRE = {
  instance_id: 9001,
  status: 'SUCCEEDED',
  task_count: 2,
  tasks: [
    { task_instance_id: 11, task_id: 'n1', node_code: 'n1', status: 'SUCCEEDED' },
    { task_instance_id: 12, task_id: 'n2', node_code: 'n2', status: 'SKIPPED' },
  ],
  plan: null,
}

const RUN_WIRE_B = { ...RUN_WIRE, instance_id: 9002, status: 'FAILED' }

const DRY_RUN_WIRE = {
  instance_id: 0,
  status: 'DRY_RUN',
  task_count: 0,
  tasks: [],
  plan: ['n1', 'n2'],
}

const OUTPUT_WIRE = {
  logs: [{ task_id: 11, task_code: 'n1', logs: [{ attempt_no: 1, level: 'INFO', message: 'ok' }] }],
  variables: [
    { name: 'cnt', expression: '1', scope: 'node', resolved_value: 1, value_type: 'int', source: 'literal', attempt_no: 1 },
  ],
  stats: { success_count: 1, failed_count: 0, skipped_count: 0 },
  found: true,
  instance_type: 'TRIAL',
  status: 'SUCCEEDED',
}

/** 容错分支：实例缺属聚合面（无 instance_type/status 键、stats 空对象） */
const OUTPUT_EMPTY_WIRE = { logs: [], variables: [], stats: {}, found: false }

const PROMOTE_WIRE = { version: 5, status: 'PUBLISHED', snapshot_digest: 'dg-abc123', idempotent: false }
const PROMOTE_IDEM_WIRE = { ...PROMOTE_WIRE, idempotent: true }

/* ---------- 模拟服务端（trial 四端点；calls 记录 method/url/body 供对拍） ---------- */

function makeTrialServer(opts: { runWire?: unknown; outputWire?: unknown; promoteWire?: unknown } = {}) {
  const calls: Array<{ method: string; url: string; body: Record<string, unknown> }> = []
  const fetchMock = vi.fn().mockImplementation(async (input: string | URL | Request, init?: RequestInit) => {
    const url = String(input instanceof Request ? input.url : input)
    const method = init?.method ?? 'GET'
    const body = typeof init?.body === 'string' ? (JSON.parse(init.body) as Record<string, unknown>) : {}
    calls.push({ method, url, body })
    if (method === 'POST' && url.endsWith('/trial/definitions/42/snapshot')) return ENV(SNAPSHOT_WIRE)
    if (method === 'POST' && url.endsWith('/trial/definitions/42/run')) return ENV(opts.runWire ?? RUN_WIRE)
    if (method === 'GET' && url.includes('/trial/runs/9001?')) return ENV(opts.outputWire ?? OUTPUT_WIRE)
    if (method === 'POST' && url.endsWith('/trial/runs/9001/promote')) return ENV(opts.promoteWire ?? PROMOTE_WIRE)
    throw new Error(`unexpected ${method} ${url}`)
  })
  return { calls, fetchMock }
}

type Server = ReturnType<typeof makeTrialServer>

/** stub fetch + open 会话（固定锚 7/42） */
function openVia(server: Server) {
  vi.stubGlobal('fetch', server.fetchMock)
  const store = useTrialRunStore()
  store.open(7, 42)
  return store
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('INC4-FE-7 trialRun：守卫与 open', () => {
  it('守卫：未 open 四动作全 null 零请求；无 snapshot → run null；无 runResult → output/promote null', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    const store = useTrialRunStore()
    await expect(store.createSnapshot()).resolves.toBeNull()
    await expect(store.run()).resolves.toBeNull()
    await expect(store.refreshOutput()).resolves.toBeNull()
    await expect(store.promote('x')).resolves.toBeNull()
    expect(fetchMock).not.toHaveBeenCalled()
    // open 后仅 snapshot/run 守卫仍生效（无 snapshot / 无 runResult）
    const server = makeTrialServer()
    vi.stubGlobal('fetch', server.fetchMock)
    store.open(7, 42)
    await expect(store.run()).resolves.toBeNull()
    await expect(store.refreshOutput()).resolves.toBeNull()
    await expect(store.promote()).resolves.toBeNull()
    expect(server.calls).toHaveLength(0)
  })

  it('open：绑定上下文 + 全量清态；二次进入换 definition 清旧态', async () => {
    const server = makeTrialServer()
    const store = openVia(server)
    await store.createSnapshot()
    await store.run()
    await store.refreshOutput()
    expect(store.snapshot?.snapshotId).toBe(501)
    expect(store.runResult?.instanceId).toBe(9001)
    expect(store.output?.found).toBe(true)
    store.open(7, 43)
    expect(store.projectId).toBe(7)
    expect(store.definitionId).toBe(43)
    expect(store.snapshot).toBe(null)
    expect(store.runResult).toBe(null)
    expect(store.output).toBe(null)
    expect(store.promoteResult).toBe(null)
    expect(store.lastError).toBe(null)
    expect(store.running).toBe(false)
  })
})

describe('INC4-FE-7 trialRun：快照与 options 归一化 run', () => {
  it('createSnapshot：POST body {project_id} → 快照 snake→camel 落地', async () => {
    const server = makeTrialServer()
    const store = openVia(server)
    const snap = await store.createSnapshot()
    expect(server.calls[0]).toMatchObject({ method: 'POST', url: '/api/v1/rebuild/trial/definitions/42/snapshot' })
    expect(server.calls[0].body).toEqual({ project_id: 7 })
    expect(snap).not.toBe(null)
    expect(store.snapshot).toEqual({
      snapshotId: 501,
      definitionId: 42,
      snapshotDigest: 'dg-abc123',
      nodes: [
        { nodeCode: 'n1', nodeType: 'SQL', name: '取数', params: { sql: 'select 1' }, positionX: 10, positionY: 20 },
        { nodeCode: 'n2', nodeType: 'SYNC', name: null, params: {}, positionX: null, positionY: null },
      ],
      edges: [{ fromNode: 'n1', toNode: 'n2', name: null }],
      status: 'ACTIVE',
      createdBy: 3,
      createdAt: '2026-10-21T10:00:00',
    })
    expect(store.snapshot).toBe(snap)
    expect(store.lastError).toBe(null)
  })

  it('options 归一化：空表单 run body 无 options 键；部分键（仅 dryRun）→ options 单键', async () => {
    const server = makeTrialServer()
    const store = openVia(server)
    await store.createSnapshot()
    await store.run()
    expect(server.calls[1].body).toEqual({ project_id: 7, snapshot_id: 501 })
    // 部分键：startNode 空串不携带；nodeCodes 空数组不携带
    store.options.dryRun = true
    await store.run()
    expect(server.calls[2].body).toEqual({ project_id: 7, snapshot_id: 501, options: { dry_run: true } })
    expect(store.runResult?.instanceId).toBe(9001)
  })

  it('八能力全量 run：options 六键 snake 对拍 → runResult 落地（含 SKIPPED 任务）', async () => {
    const server = makeTrialServer()
    const store = openVia(server)
    await store.createSnapshot()
    store.options.nodeCodes = ['n1', 'n3']
    store.options.startNode = 'n2'
    store.options.testVariables = { k: 'v' }
    store.options.dependencyMock = { dep1: 'FAILED' }
    store.options.dryRun = true
    store.options.sqlPrecheck = true
    const result = await store.run()
    expect(server.calls[1]).toMatchObject({ method: 'POST', url: '/api/v1/rebuild/trial/definitions/42/run' })
    expect(server.calls[1].body).toEqual({
      project_id: 7,
      snapshot_id: 501,
      options: {
        node_codes: ['n1', 'n3'],
        start_node: 'n2',
        test_variables: { k: 'v' },
        dependency_mock: { dep1: 'FAILED' },
        dry_run: true,
        sql_precheck: true,
      },
    })
    expect(result).toEqual({
      instanceId: 9001,
      status: 'SUCCEEDED',
      taskCount: 2,
      tasks: [
        { taskInstanceId: 11, taskId: 'n1', nodeCode: 'n1', status: 'SUCCEEDED' },
        { taskInstanceId: 12, taskId: 'n2', nodeCode: 'n2', status: 'SKIPPED' },
      ],
      plan: null,
    })
    expect(store.runResult).toEqual(result)
    expect(store.running).toBe(false)
    expect(store.lastError).toBe(null)
  })

  it('DryRun 结果落地：instance_id=0 / plan 拓扑序直存', async () => {
    const server = makeTrialServer({ runWire: DRY_RUN_WIRE })
    const store = openVia(server)
    await store.createSnapshot()
    store.options.dryRun = true
    await store.run()
    expect(store.runResult).toEqual({
      instanceId: 0,
      status: 'DRY_RUN',
      taskCount: 0,
      tasks: [],
      plan: ['n1', 'n2'],
    })
  })

  it('run 失败：lastError 记录、running 复位、runResult 不落地', async () => {
    const server = makeTrialServer()
    const store = openVia(server)
    await store.createSnapshot()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ENV({ code: 500, msg: 'WF_TRIAL_INVALID' }, 500)))
    await store.run()
    expect(store.lastError).toBeTruthy()
    expect(store.runResult).toBe(null)
    expect(store.running).toBe(false)
  })

  it('loadSeq 时序守卫：双 run 竞态仅最新响应落地，过期响应与过期错误一并丢弃', async () => {
    const server = makeTrialServer()
    const store = openVia(server)
    await store.createSnapshot()
    // 换 pending fetch 手工放行
    const pending: Array<{ res: (r: Response) => void; rej: (e: unknown) => void }> = []
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => new Promise<Response>((res, rej) => { pending.push({ res, rej }) })),
    )
    const p1 = store.run()
    const p2 = store.run()
    expect(pending).toHaveLength(2)
    expect(store.running).toBe(true)
    // 新响应（第二次）先落地
    pending[1].res(ENV(RUN_WIRE_B))
    await p2
    expect(store.runResult?.instanceId).toBe(9002)
    expect(store.runResult?.status).toBe('FAILED')
    // 旧响应（第一次）迟到 → 丢弃
    pending[0].res(ENV(RUN_WIRE))
    await p1
    expect(store.runResult?.instanceId).toBe(9002)
    expect(store.running).toBe(false)
    expect(store.lastError).toBe(null)
    // 过期错误同样丢弃：p3 旧 / p4 新，p4 先落地、p3 后拒绝
    const p3 = store.run()
    const p4 = store.run()
    pending[3].res(ENV(RUN_WIRE))
    await p4
    pending[2].rej(new Error('过期请求失败'))
    await p3
    expect(store.runResult?.instanceId).toBe(9001)
    expect(store.lastError).toBe(null)
    expect(store.running).toBe(false)
  })
})

describe('INC4-FE-7 trialRun：output 与 promote', () => {
  it('refreshOutput：GET /runs/{id}?project_id= → output 落地（映射对拍）', async () => {
    const server = makeTrialServer()
    const store = openVia(server)
    await store.createSnapshot()
    await store.run()
    const out = await store.refreshOutput()
    expect(server.calls[2]).toMatchObject({ method: 'GET', url: '/api/v1/rebuild/trial/runs/9001?project_id=7' })
    expect(out).toEqual({
      logs: [{ taskId: 11, taskCode: 'n1', logs: [{ attemptNo: 1, level: 'INFO', message: 'ok' }] }],
      variables: [
        { name: 'cnt', expression: '1', scope: 'node', resolvedValue: 1, valueType: 'int', source: 'literal', attemptNo: 1 },
      ],
      stats: { successCount: 1, failedCount: 0, skippedCount: 0 },
      found: true,
      instanceType: 'TRIAL',
      status: 'SUCCEEDED',
    })
    expect(store.output).toEqual(out)
  })

  it('refreshOutput 容错：stats {} → 0 兜底、缺 instance_type/status → null（found=false）', async () => {
    const server = makeTrialServer({ outputWire: OUTPUT_EMPTY_WIRE })
    const store = openVia(server)
    await store.createSnapshot()
    await store.run()
    await store.refreshOutput()
    expect(store.output).toEqual({
      logs: [],
      variables: [],
      stats: { successCount: 0, failedCount: 0, skippedCount: 0 },
      found: false,
      instanceType: null,
      status: null,
    })
  })

  it('promote：remark 带与不带 body 对拍（不带 → 无 remark 键）；幂等 idempotent 映射', async () => {
    const server = makeTrialServer()
    const store = openVia(server)
    await store.createSnapshot()
    await store.run()
    const r1 = await store.promote('首发转正')
    expect(server.calls[2]).toMatchObject({ method: 'POST', url: '/api/v1/rebuild/trial/runs/9001/promote' })
    expect(server.calls[2].body).toEqual({ project_id: 7, remark: '首发转正' })
    expect(r1).toEqual({ version: 5, status: 'PUBLISHED', snapshotDigest: 'dg-abc123', idempotent: false })
    // 不带 remark：body 无 remark 键
    const server2 = makeTrialServer({ promoteWire: PROMOTE_IDEM_WIRE })
    vi.stubGlobal('fetch', server2.fetchMock)
    const store2 = useTrialRunStore()
    store2.open(7, 42)
    await store2.createSnapshot()
    await store2.run()
    const r2 = await store2.promote()
    expect(server2.calls[2].body).toEqual({ project_id: 7 })
    expect(r2?.idempotent).toBe(true)
    expect(store2.promoteResult?.idempotent).toBe(true)
  })

  it('open 在飞失效：run 在飞时二次 open → 响应过期丢弃、running 复位、全态清空', async () => {
    const server = makeTrialServer()
    const store = openVia(server)
    await store.createSnapshot()
    await store.run()
    expect(store.runResult?.instanceId).toBe(9001)
    // 换 pending fetch：run 在飞 → 二次 open 换 definition
    const pending: Array<{ res: (r: Response) => void }> = []
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(() => new Promise<Response>((res) => { pending.push({ res }) })),
    )
    const p = store.run()
    expect(store.running).toBe(true)
    store.open(7, 43)
    expect(store.running).toBe(false)
    expect(store.snapshot).toBe(null)
    pending[0].res(ENV(RUN_WIRE))
    await p
    // 过期响应丢弃：不落地
    expect(store.runResult).toBe(null)
    expect(store.definitionId).toBe(43)
  })
})
