/**
 * R7 契约测试（node 环境，纯契约层无组件挂载）。
 * RED describe：方法清单冻结、工厂实现统一抛 R7_METRICS_NOT_WIRED（即后端接入前不存在半连通状态）。
 * GREEN describe：R7 批次接线断言（接线计划 Task 5；包络 {code,msg,data} 沿 R2 固化）。
 * 组件可编译性由 `pnpm build` 门禁保证。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  R7_CONTRACT_METHODS,
  createMetricsContract,
} from '../../../../services/rebuild/metricsApi'

const window = { from: '2026-01-01T00:00:00Z', to: '2026-01-02T00:00:00Z', offset: 0, limit: 50 }
const projectId = 1

describe('R7 metricsApi contract (RED)', () => {
  it('contract method list is frozen to the metrics/quality/lineage subset', () => {
    expect(R7_CONTRACT_METHODS).toHaveLength(6)
    expect(R7_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'queryWorkflowResultStats',
        'queryTaskInstanceDataStats',
        'queryTaskDataStatSegments',
        'queryTaskDataErrorSamples',
        'listQualityRuleLinks',
        'listLineageWritebacks',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createMetricsContract()
    for (const method of R7_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })
})

/* ---------- GREEN 接线断言（R7 批次，接线计划 Task 5；包络沿 R2 固化） ---------- */

/** 后端成功包络形态（rebuild 域全域实证：{code:0,msg:'success',data}） */
function stubFetchWithEnvelope(data: unknown): ReturnType<typeof vi.fn> {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status: 200 }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('R7 metricsApi contract (GREEN wired)', () => {
  it('queryWorkflowResultStats POSTs /workflow-result-stats and maps stat rows snake-to-camel', async () => {
    const fetchMock = stubFetchWithEnvelope([
      { workflow_id: 7, run_date: '2026-01-01', success_count: 5, failure_count: 1, skipped_count: 2, retry_count: 3 },
    ])
    vi.stubGlobal('fetch', fetchMock)
    const rows = await createMetricsContract().queryWorkflowResultStats(projectId, window)
    expect(rows).toEqual([
      { workflowId: 7, runDate: '2026-01-01', successCount: 5, failureCount: 1, skippedCount: 2, retryCount: 3 },
    ])
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/metrics/workflow-result-stats')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ ...window, project_id: projectId })
  })

  it('queryTaskInstanceDataStats passes MetricValue through unprocessed (unknown/estimated untouched)', async () => {
    const fetchMock = stubFetchWithEnvelope([
      {
        instance_id: 11,
        task_id: 't-1',
        rows_in: { value: 100, known: false, estimated: true },
        rows_out: { value: 90, known: true, estimated: false },
        error_rows: { value: 0, known: true, estimated: false },
        elapsed_ms: { value: 1234, known: true, estimated: false },
      },
    ])
    vi.stubGlobal('fetch', fetchMock)
    const rows = await createMetricsContract().queryTaskInstanceDataStats(projectId, window)
    expect(rows).toEqual([
      {
        instanceId: 11,
        taskId: 't-1',
        rowsIn: { value: 100, known: false, estimated: true },
        rowsOut: { value: 90, known: true, estimated: false },
        errorRows: { value: 0, known: true, estimated: false },
        elapsedMs: { value: 1234, known: true, estimated: false },
      },
    ])
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/v1/rebuild/metrics/task-instance-data-stats')
  })

  it('queryTaskDataStatSegments maps segment_key to segmentKey', async () => {
    const fetchMock = stubFetchWithEnvelope([
      { instance_id: 11, task_id: 't-1', segment_key: 'hour-00', row_count: { value: 60, known: true, estimated: false } },
    ])
    vi.stubGlobal('fetch', fetchMock)
    const rows = await createMetricsContract().queryTaskDataStatSegments(projectId, window)
    expect(rows).toEqual([
      { instanceId: 11, taskId: 't-1', segmentKey: 'hour-00', rowCount: { value: 60, known: true, estimated: false } },
    ])
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/v1/rebuild/metrics/task-data-stat-segments')
  })

  it('queryTaskDataErrorSamples maps sample_data and captured_at', async () => {
    const fetchMock = stubFetchWithEnvelope([
      { instance_id: 11, task_id: 't-1', error_type: 'NOT_NULL', sample_data: 'row#8', captured_at: '2026-01-01 10:00:00' },
    ])
    vi.stubGlobal('fetch', fetchMock)
    const rows = await createMetricsContract().queryTaskDataErrorSamples(projectId, window)
    expect(rows).toEqual([
      { instanceId: 11, taskId: 't-1', errorType: 'NOT_NULL', sampleData: 'row#8', capturedAt: '2026-01-01 10:00:00' },
    ])
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/v1/rebuild/metrics/task-data-error-samples')
  })

  it('listQualityRuleLinks maps rule fields and stat_ref (table+pk reference passthrough)', async () => {
    const fetchMock = stubFetchWithEnvelope([
      { rule_id: 3, rule_name: '非空校验', stat_ref: 'task_instance_data_stat:11', alert_sent: true, result_at: '2026-01-01 10:00:00' },
    ])
    vi.stubGlobal('fetch', fetchMock)
    const rows = await createMetricsContract().listQualityRuleLinks(projectId, window)
    expect(rows).toEqual([
      { ruleId: 3, ruleName: '非空校验', statRef: 'task_instance_data_stat:11', alertSent: true, resultAt: '2026-01-01 10:00:00' },
    ])
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/v1/rebuild/metrics/quality-rule-links')
  })

  it('listLineageWritebacks sends kind filter and normalizes numeric run_id to string', async () => {
    const fetchMock = stubFetchWithEnvelope([
      { run_id: 42, run_kind: 'sql', source_entity: 'dwh.a', target_entity: 'dwh.b', writeback_at: '2026-01-01 10:00:00' },
    ])
    vi.stubGlobal('fetch', fetchMock)
    const rows = await createMetricsContract().listLineageWritebacks(projectId, window, 'sql')
    expect(rows).toEqual([
      { runId: '42', runKind: 'sql', sourceEntity: 'dwh.a', targetEntity: 'dwh.b', writebackAt: '2026-01-01 10:00:00' },
    ])
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/metrics/lineage-writebacks')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ ...window, project_id: projectId, kind: 'sql' })
  })

  it("listLineageWritebacks passes kind 'all' through as-is", async () => {
    const fetchMock = stubFetchWithEnvelope([])
    vi.stubGlobal('fetch', fetchMock)
    await expect(createMetricsContract().listLineageWritebacks(projectId, window, 'all')).resolves.toEqual([])
    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({ ...window, project_id: projectId, kind: 'all' })
  })

  /* FE-12 骨架（LineageWritebackPanel）kind 四态筛选面：sql/sync/workflow/all 全量透传 */
  it.each(['sql', 'sync', 'workflow', 'all'] as const)(
    "listLineageWritebacks passes runKind '%s' through as-is",
    async (kind) => {
      const fetchMock = stubFetchWithEnvelope([])
      vi.stubGlobal('fetch', fetchMock)
      await expect(createMetricsContract().listLineageWritebacks(projectId, window, kind)).resolves.toEqual([])
      const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
      expect(JSON.parse(init.body as string)).toEqual({ ...window, project_id: projectId, kind })
    },
  )

  it('non-2xx maps to ContractApiError with httpStatus preserved', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 500 })))
    await expect(createMetricsContract().queryWorkflowResultStats(projectId, window)).rejects.toMatchObject({
      httpStatus: 500,
      name: 'ContractApiError',
    })
  })

  it('envelope business error (code !== 0) maps to ContractApiError with the backend code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 4001, msg: '查询失败', data: null }), { status: 200 })),
    )
    await expect(createMetricsContract().queryWorkflowResultStats(projectId, window)).rejects.toMatchObject({
      httpStatus: 200,
      code: 4001,
      name: 'ContractApiError',
    })
  })
})
