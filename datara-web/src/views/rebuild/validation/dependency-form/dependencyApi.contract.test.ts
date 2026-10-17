/**
 * R4-DEPENDENCY 契约测试（node 环境，纯契约层无组件挂载）。
 * RED describe：方法清单冻结、表达式草稿拼装行为（组内 join / 组间 AND）。
 * GREEN describe：R4 批次接线断言（接线计划 Task 4；包络 {code,msg,data} 沿 R2/R7 固化；
 * upstreamTaskCode string→int 哨兵转换；非 2xx 保码透出 DEP_*）。
 * 语义源：客户要求 #5 + 纠偏设计 §5.3（DolphinScheduler 式依赖表单）+ A2 v2.1 冻结契约。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  R4_DEPENDENCY_CONTRACT_METHODS,
  composeExpressionDraft,
  createDependencyContract,
  type DependencyGroup,
} from '../../../../services/rebuild/dependencyApi'

const groups: DependencyGroup[] = [
  {
    join: 'OR',
    conditions: [
      { upstreamWorkflowId: 1, dateRange: { periodType: 'day', beginOffset: -1, endOffset: -1 } },
      { upstreamWorkflowId: 2, upstreamTaskCode: '7', dateRange: { periodType: 'hour', beginOffset: -2, endOffset: -1 } },
    ],
  },
  {
    join: 'AND',
    conditions: [{ upstreamWorkflowId: 3, dateRange: { periodType: 'week', beginOffset: -1, endOffset: 0 } }],
  },
]

describe('R4 dependencyApi contract (RED)', () => {
  it('contract method list is frozen to the dependency form subset', () => {
    expect(R4_DEPENDENCY_CONTRACT_METHODS).toHaveLength(5)
    expect(R4_DEPENDENCY_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'listCandidateWorkflows',
        'listWorkflowTasks',
        'previewExpression',
        'saveDependency',
        'evaluateDependency',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createDependencyContract()
    for (const method of R4_DEPENDENCY_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('composeExpressionDraft joins conditions in-group and groups with AND', () => {
    const draft = composeExpressionDraft(groups)
    expect(draft).toBe(
      '(wf(1) day[-1..-1] OR wf(2) task(7) hour[-2..-1]) AND wf(3) week[-1..0]',
    )
  })

  it('composeExpressionDraft keeps single-condition groups unparenthesized', () => {
    const single: DependencyGroup[] = [{ join: 'AND', conditions: [{ upstreamWorkflowId: 7, dateRange: { periodType: 'month', beginOffset: 0, endOffset: 0 } }] }]
    expect(composeExpressionDraft(single)).toBe('wf(7) month[0..0]')
  })
})

/* ---------- GREEN 接线断言（R4 批次，接线计划 Task 4；包络沿 R2/R7 固化） ---------- */

function stubFetchWithEnvelope(data: unknown, status = 200): ReturnType<typeof vi.fn> {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('R4 dependencyApi contract (GREEN wired)', () => {
  it('listCandidateWorkflows GETs /workflows?project_id= (honest empty list on main)', async () => {
    const fetchMock = stubFetchWithEnvelope([])
    vi.stubGlobal('fetch', fetchMock)
    await expect(createDependencyContract().listCandidateWorkflows(1)).resolves.toEqual([])
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/dependency/workflows?project_id=1')
    expect(init.method).toBe('GET')
  })

  it('listWorkflowTasks GETs /workflows/{id}/tasks with project_id and optional workflow_version', async () => {
    const fetchMock = stubFetchWithEnvelope([])
    vi.stubGlobal('fetch', fetchMock)
    await expect(createDependencyContract().listWorkflowTasks(1, 7, 2)).resolves.toEqual([])
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/v1/rebuild/dependency/workflows/7/tasks?project_id=1&workflow_version=2')
  })

  it('previewExpression POSTs /preview with snake body and string→int task-code sentinel', async () => {
    const fetchMock = stubFetchWithEnvelope({
      expression: 'wf(1) day[-1..-1]',
      resolved: [{ upstream_workflow_id: 1, window_start: '2026-10-16T00:00:00Z', window_end: '2026-10-17T00:00:00Z', verdict: 'pending' }],
      verdict: 'pending',
    })
    vi.stubGlobal('fetch', fetchMock)
    const preview = await createDependencyContract().previewExpression(1, 10, 3, 'clean', [
      { join: 'AND', conditions: [{ upstreamWorkflowId: 1, upstreamTaskCode: '0', dateRange: { periodType: 'day', beginOffset: -1, endOffset: -1 } }] },
    ])
    expect(preview).toEqual({
      expression: 'wf(1) day[-1..-1]',
      resolved: [{ upstreamWorkflowId: 1, windowStart: '2026-10-16T00:00:00Z', windowEnd: '2026-10-17T00:00:00Z', verdict: 'pending' }],
      verdict: 'pending',
    })
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      project_id: 1,
      workflow_id: 10,
      workflow_version: 3,
      task_id: 'clean',
      groups: [{ join: 'AND', conditions: [{ upstream_workflow_id: 1, upstream_task_code: 0, date_range: { period_type: 'day', begin_offset: -1, end_offset: -1 } }] }],
    })
  })

  it('previewExpression maps resolved upstream_task_code through as string (selector=task)', async () => {
    const fetchMock = stubFetchWithEnvelope({
      expression: 'wf(2) task(7) hour[-2..-1]',
      resolved: [{ upstream_workflow_id: 2, upstream_task_code: '7', window_start: 'a', window_end: 'b', verdict: 'satisfied' }],
      verdict: 'satisfied',
    })
    vi.stubGlobal('fetch', fetchMock)
    const preview = await createDependencyContract().previewExpression(1, 10, 3, 'clean', [
      { join: 'AND', conditions: [{ upstreamWorkflowId: 2, upstreamTaskCode: '7', dateRange: { periodType: 'hour', beginOffset: -2, endOffset: -1 } }] },
    ])
    expect(preview.resolved[0]?.upstreamTaskCode).toBe('7')
  })

  it('non-decimal upstreamTaskCode fails fast with ID_NORMALIZATION_FAILED (no request sent)', async () => {
    const fetchMock = stubFetchWithEnvelope([])
    vi.stubGlobal('fetch', fetchMock)
    await expect(
      createDependencyContract().previewExpression(1, 10, 3, 'clean', [
        { join: 'AND', conditions: [{ upstreamWorkflowId: 2, upstreamTaskCode: 't_load', dateRange: { periodType: 'day', beginOffset: -1, endOffset: -1 } }] },
      ]),
    ).rejects.toMatchObject({ code: 'ID_NORMALIZATION_FAILED', name: 'ContractApiError' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('saveDependency POSTs /saves and returns saved/version', async () => {
    const fetchMock = stubFetchWithEnvelope({ saved: true, version: 3 })
    vi.stubGlobal('fetch', fetchMock)
    await expect(createDependencyContract().saveDependency({ projectId: 1, workflowId: 10, workflowVersion: 3, taskId: 'clean', groups })).resolves.toEqual({
      saved: true,
      version: 3,
    })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/dependency/saves')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      project_id: 1,
      workflow_id: 10,
      workflow_version: 3,
      task_id: 'clean',
      groups: [
        {
          join: 'OR',
          conditions: [
            { upstream_workflow_id: 1, date_range: { period_type: 'day', begin_offset: -1, end_offset: -1 } },
            { upstream_workflow_id: 2, upstream_task_code: 7, date_range: { period_type: 'hour', begin_offset: -2, end_offset: -1 } },
          ],
        },
        { join: 'AND', conditions: [{ upstream_workflow_id: 3, date_range: { period_type: 'week', begin_offset: -1, end_offset: 0 } }] },
      ],
    })
  })

  it('evaluateDependency maps evaluated_at to evaluatedAt and passes asOf through', async () => {
    const fetchMock = stubFetchWithEnvelope({
      expression: 'wf(1) day[-1..-1]',
      resolved: [],
      verdict: 'pending',
      evaluated_at: '2026-10-17T12:00:00Z',
    })
    vi.stubGlobal('fetch', fetchMock)
    const result = await createDependencyContract().evaluateDependency({
      projectId: 1,
      workflowId: 10,
      workflowVersion: 3,
      taskId: 'clean',
      groups: [{ join: 'AND', conditions: [{ upstreamWorkflowId: 1, dateRange: { periodType: 'day', beginOffset: -1, endOffset: -1 } }] }],
      asOf: '2026-10-17T12:00:00Z',
    })
    expect(result.evaluatedAt).toBe('2026-10-17T12:00:00Z')
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(JSON.parse(init.body as string).as_of).toBe('2026-10-17T12:00:00Z')
  })

  it('DEP_* business error on HTTP 400 keeps both httpStatus and the backend code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: 'DEP_INVALID_WINDOW', msg: 'condition validation failed', data: { diagnostics: [] } }), { status: 400 }),
      ),
    )
    await expect(
      createDependencyContract().previewExpression(1, 10, 3, 'clean', groups),
    ).rejects.toMatchObject({ httpStatus: 400, code: 'DEP_INVALID_WINDOW', name: 'ContractApiError' })
  })
})
