/**
 * INC4-FE-7 trialApi 契约测试（/api/v1/rebuild/trial 真实端点接线）。
 *
 * 覆盖（真源 datara-backend/rebuild/trial/api.py + http.ts 单 BASE 底座）：
 *  1. createTrialSnapshot：POST /definitions/{id}/snapshot + body {project_id}
 *     → 快照 payload snake→camel 对拍（node_snapshot_json→nodes / edge_snapshot_json→edges）；
 *  2. getTrialSnapshot：GET /snapshots/{id}?project_id=（camel→snake 查询串）；
 *  3. runTrial：POST /definitions/{id}/run body {project_id, snapshot_id, options?}
 *     —— 八能力 options 全量键对拍（nodeCodes→node_codes 等 snake 词形）；
 *  4. runTrial options 缺省 → body 不含 options 键（条件键展开）；
 *     runTrial 部分键 → options 仅携带所传键；dry_run 映射；
 *  5. promoteTrialRun：POST /definitions/{id}/promote body {project_id, instance_id, remark?}
 *     （remark 缺省不携带）→ TrialPromoteResult（idempotent 幂等位）；
 *  6. createTrialRun（WF-26）：POST /runs body {project_id, definition_id, snapshot_id, options?}；
 *  7. getTrialRunOutput（WF-26）：GET /runs/{id}?project_id= → 输出面映射
 *     （logs/variables/stats camel 化 + stats 空对象/instance_type 缺省容错）；
 *  8. promoteRunById（WF-26）：POST /runs/{id}/promote body {project_id, remark?}；
 *  9. DryRun 语义：plan 拓扑序数组直存、tasks 空、instance_id=0；
 * 10. 域错误：WF_SNAPSHOT_NOT_FOUND 404 / WF_PROMOTE_DIGEST_MISMATCH 409
 *     —— 默认丢包络码保 HTTP 状态码（preserveEnvelopeCode 未开，与底座默认一致）。
 *
 * 范式：vi.stubGlobal('fetch') 直测 http 底座真实调用形状（沿 workflowApi.contract 先例）；
 * 多次调用处 mockImplementation 每次新建 Response（happy-dom body 一次性不可复用）。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'

import {
  createTrialRun,
  createTrialSnapshot,
  getTrialRunOutput,
  getTrialSnapshot,
  promoteRunById,
  promoteTrialRun,
  runTrial,
  type TrialRunOptions,
} from '../trialApi'

afterEach(() => vi.unstubAllGlobals())

/** 包络 2xx 响应（code=0 成功态） */
const ENV = (data: unknown, status = 200) =>
  new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status })

/** 快照 wire 样例（repository._snapshot_payload 形状） */
const SNAPSHOT_WIRE = {
  snapshot_id: 9,
  definition_id: 42,
  snapshot_digest: 'sha256:snap1',
  node_snapshot_json: [
    { node_code: 'n1', node_type: 'SQL', name: '清洗', params: { sql: 'select 1' }, position_x: 10, position_y: 20 },
    { node_code: 'n2', node_type: 'SYNC', name: null, params: {}, position_x: null, position_y: null },
  ],
  edge_snapshot_json: [{ from_node: 'n1', to_node: 'n2', name: null }],
  status: 'ACTIVE',
  created_by: 3,
  created_at: '2026-10-21T00:00:00Z',
}

const SNAPSHOT_DOMAIN = {
  snapshotId: 9,
  definitionId: 42,
  snapshotDigest: 'sha256:snap1',
  nodes: [
    { nodeCode: 'n1', nodeType: 'SQL', name: '清洗', params: { sql: 'select 1' }, positionX: 10, positionY: 20 },
    { nodeCode: 'n2', nodeType: 'SYNC', name: null, params: {}, positionX: null, positionY: null },
  ],
  edges: [{ fromNode: 'n1', toNode: 'n2', name: null }],
  status: 'ACTIVE',
  createdBy: 3,
  createdAt: '2026-10-21T00:00:00Z',
}

describe('INC4-FE-7 trialApi 契约（/api/v1/rebuild/trial）', () => {
  it('createTrialSnapshot：POST /definitions/{id}/snapshot + body {project_id} + token 头 → 快照映射', async () => {
    localStorage.setItem('datara_token', 'trial-token')
    const fetchMock = vi.fn().mockResolvedValue(ENV(SNAPSHOT_WIRE))
    vi.stubGlobal('fetch', fetchMock)
    const snap = await createTrialSnapshot(7, 42)
    expect(snap).toEqual(SNAPSHOT_DOMAIN)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/trial/definitions/42/snapshot')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ project_id: 7 }))
    expect(new Headers(init.headers).get('token')).toBe('trial-token')
    expect(new Headers(init.headers).get('Content-Type')).toBe('application/json')
  })

  it('getTrialSnapshot：GET /snapshots/{id}?project_id=（camel→snake 查询串）→ 快照映射', async () => {
    const fetchMock = vi.fn().mockResolvedValue(ENV(SNAPSHOT_WIRE))
    vi.stubGlobal('fetch', fetchMock)
    const snap = await getTrialSnapshot(7, 9)
    expect(snap).toEqual(SNAPSHOT_DOMAIN)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/trial/snapshots/9?project_id=7')
    expect(init.method).toBe('GET')
  })

  it('runTrial：POST /definitions/{id}/run —— 八能力 options 全量键对拍（camel→snake）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ENV({ instance_id: 55, status: 'SUCCEEDED', task_count: 2, tasks: [], plan: null }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const options: TrialRunOptions = {
      nodeCodes: ['n1', 'n2'],
      startNode: 'n1',
      testVariables: { row_count: 42 },
      dependencyMock: { dep_1: 'SUCCEEDED', dep_2: 'FAILED' },
      dryRun: true,
      sqlPrecheck: true,
    }
    await runTrial(7, 42, 9, options)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/trial/definitions/42/run')
    expect(init.method).toBe('POST')
    expect(init.body).toBe(
      JSON.stringify({
        project_id: 7,
        snapshot_id: 9,
        options: {
          node_codes: ['n1', 'n2'],
          start_node: 'n1',
          test_variables: { row_count: 42 },
          dependency_mock: { dep_1: 'SUCCEEDED', dep_2: 'FAILED' },
          dry_run: true,
          sql_precheck: true,
        },
      }),
    )
  })

  it('runTrial：options 缺省 → body 不含 options 键；部分键仅携带所传（条件键展开）', async () => {
    // 多次调用须每次新建 Response（happy-dom body 一次性，不可复用实例）
    const fetchMock = vi.fn().mockImplementation(() =>
      ENV({ instance_id: 55, status: 'SUCCEEDED', task_count: 0, tasks: [], plan: null }),
    )
    vi.stubGlobal('fetch', fetchMock)

    await runTrial(7, 42, 9)
    const [, init1] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(init1.body).toBe(JSON.stringify({ project_id: 7, snapshot_id: 9 }))

    await runTrial(7, 42, 9, { dryRun: true })
    const [, init2] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(init2.body).toBe(JSON.stringify({ project_id: 7, snapshot_id: 9, options: { dry_run: true } }))

    await runTrial(7, 42, 9, { startNode: 'n1', dependencyMock: { dep_1: 'FAILED' } })
    const [, init3] = fetchMock.mock.calls[2] as [string, RequestInit]
    expect(init3.body).toBe(
      JSON.stringify({
        project_id: 7,
        snapshot_id: 9,
        options: { start_node: 'n1', dependency_mock: { dep_1: 'FAILED' } },
      }),
    )
  })

  it('runTrial：运行结果映射（tasks snake→camel；plan null 直存）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ENV({
        instance_id: 55,
        status: 'SUCCEEDED',
        task_count: 2,
        tasks: [
          { task_instance_id: 101, task_id: 'n1', node_code: 'n1', status: 'SUCCEEDED' },
          { task_instance_id: 102, task_id: 'n2', node_code: 'n2', status: 'SKIPPED' },
        ],
        plan: null,
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const result = await runTrial(7, 42, 9)
    expect(result).toEqual({
      instanceId: 55,
      status: 'SUCCEEDED',
      taskCount: 2,
      tasks: [
        { taskInstanceId: 101, taskId: 'n1', nodeCode: 'n1', status: 'SUCCEEDED' },
        { taskInstanceId: 102, taskId: 'n2', nodeCode: 'n2', status: 'SKIPPED' },
      ],
      plan: null,
    })
  })

  it('runTrial DryRun 语义：status=DRY_RUN、instance_id=0、plan 拓扑序直存、tasks 空', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ENV({ instance_id: 0, status: 'DRY_RUN', task_count: 2, tasks: [], plan: ['n1', 'n2'] }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const result = await runTrial(7, 42, 9, { dryRun: true })
    expect(result).toEqual({
      instanceId: 0,
      status: 'DRY_RUN',
      taskCount: 2,
      tasks: [],
      plan: ['n1', 'n2'],
    })
  })

  it('promoteTrialRun：POST /definitions/{id}/promote body {project_id, instance_id, remark}；remark 缺省不携带', async () => {
    // 多次调用须每次新建 Response（happy-dom body 一次性，不可复用实例）
    const fetchMock = vi.fn().mockImplementation(() =>
      ENV({ version: 3, status: 'PUBLISHED', snapshot_digest: 'sha256:snap1', idempotent: false }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const promoted = await promoteTrialRun(7, 42, 55, '试运行通过转正式')
    expect(promoted).toEqual({ version: 3, status: 'PUBLISHED', snapshotDigest: 'sha256:snap1', idempotent: false })
    const [url, init1] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/trial/definitions/42/promote')
    expect(init1.body).toBe(JSON.stringify({ project_id: 7, instance_id: 55, remark: '试运行通过转正式' }))

    await promoteTrialRun(7, 42, 55)
    const [, init2] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(init2.body).toBe(JSON.stringify({ project_id: 7, instance_id: 55 }))
  })

  it('createTrialRun（WF-26）：POST /runs body {project_id, definition_id, snapshot_id, options?}', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ENV({ instance_id: 56, status: 'FAILED', task_count: 1, tasks: [], plan: null }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const result = await createTrialRun(7, 42, 9, { nodeCodes: ['n1'] })
    expect(result).toEqual({ instanceId: 56, status: 'FAILED', taskCount: 1, tasks: [], plan: null })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/trial/runs')
    expect(init.body).toBe(
      JSON.stringify({ project_id: 7, definition_id: 42, snapshot_id: 9, options: { node_codes: ['n1'] } }),
    )
  })

  it('getTrialRunOutput（WF-26）：GET /runs/{id}?project_id= → 输出面映射（logs/variables/stats camel 化）', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      ENV({
        logs: [{ task_id: 101, task_code: 'n1', logs: [{ attempt_no: 1, level: 'INFO', message: 'done' }] }],
        variables: [
          { name: 'row_count', expression: '{{out.n1.count}}', scope: 'INSTANCE', resolved_value: 42, value_type: 'int', source: 'task', attempt_no: 1 },
        ],
        stats: { success_count: 2, failed_count: 0, skipped_count: 1 },
        found: true,
        instance_type: 'TRIAL',
        status: 'SUCCEEDED',
      }),
    )
    vi.stubGlobal('fetch', fetchMock)
    const output = await getTrialRunOutput(7, 55)
    expect(output).toEqual({
      logs: [{ taskId: 101, taskCode: 'n1', logs: [{ attemptNo: 1, level: 'INFO', message: 'done' }] }],
      variables: [
        { name: 'row_count', expression: '{{out.n1.count}}', scope: 'INSTANCE', resolvedValue: 42, valueType: 'int', source: 'task', attemptNo: 1 },
      ],
      stats: { successCount: 2, failedCount: 0, skippedCount: 1 },
      found: true,
      instanceType: 'TRIAL',
      status: 'SUCCEEDED',
    })
    const [url] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/trial/runs/55?project_id=7')
  })

  it('getTrialRunOutput 容错：stats 空对象/instance_type 缺省 → 0 兜底与 null（空运行分支）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ENV({ logs: [], variables: [], stats: {}, found: false })))
    const output = await getTrialRunOutput(7, 55)
    expect(output.logs).toEqual([])
    expect(output.variables).toEqual([])
    expect(output.stats).toEqual({ successCount: 0, failedCount: 0, skippedCount: 0 })
    expect(output.found).toBe(false)
    expect(output.instanceType).toBeNull()
    expect(output.status).toBeNull()
  })

  it('promoteRunById（WF-26）：POST /runs/{id}/promote body {project_id, remark?}；幂等 idempotent=true 直返', async () => {
    // 多次调用须每次新建 Response（happy-dom body 一次性，不可复用实例）
    const fetchMock = vi.fn().mockImplementation(() =>
      ENV({ version: 2, status: 'PUBLISHED', snapshot_digest: 'sha256:snap1', idempotent: true }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const first = await promoteRunById(7, 55, '二次转正式（幂等）')
    expect(first).toEqual({ version: 2, status: 'PUBLISHED', snapshotDigest: 'sha256:snap1', idempotent: true })
    const [url, init1] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/trial/runs/55/promote')
    expect(init1.body).toBe(JSON.stringify({ project_id: 7, remark: '二次转正式（幂等）' }))

    await promoteRunById(7, 55)
    const [, init2] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(init2.body).toBe(JSON.stringify({ project_id: 7 }))
  })

  it('域错误：WF_SNAPSHOT_NOT_FOUND 404 → 默认保 HTTP 状态码（包络码不透出）', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ENV({ code: 'WF_SNAPSHOT_NOT_FOUND', msg: 'not found' }, 404)))
    await expect(getTrialSnapshot(7, 999)).rejects.toMatchObject({
      name: 'ContractApiError',
      httpStatus: 404,
      code: 404,
    })
  })

  it('域错误：WF_PROMOTE_DIGEST_MISMATCH 409 → 默认保 HTTP 状态码', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(ENV({ code: 'WF_PROMOTE_DIGEST_MISMATCH', msg: 'digest mismatch' }, 409)))
    await expect(promoteTrialRun(7, 42, 55)).rejects.toMatchObject({
      name: 'ContractApiError',
      httpStatus: 409,
      code: 409,
    })
  })
})
