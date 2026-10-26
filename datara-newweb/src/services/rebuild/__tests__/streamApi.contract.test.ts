import { afterEach, describe, expect, it, vi } from 'vitest'
import { I8_CONTRACT_METHODS, I8_PERMISSION_MATRIX, createStreamContract } from '../streamApi'

const response = (data: unknown, status = 200) => ({
  ok: status >= 200 && status < 300,
  status,
  json: async () => ({ code: 0, msg: 'success', data }),
  text: async () => JSON.stringify({ code: 0, msg: 'success', data }),
})

describe('stream API contract', () => {
  afterEach(() => vi.restoreAllMocks())

  it('wires the stream observation methods to the router and normalizes responses', async () => {
    expect(Object.keys(I8_PERMISSION_MATRIX)).toEqual(I8_CONTRACT_METHODS)
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = String(input)
      if (url.endsWith('/jobs?project_id=7')) return response([{ id: 7, name: 'demo', workflow_id: 1, mq_topic: 'topic', runtime_config: { mode: 'fixed_rate' }, state: 'RUNNING', attempt_no: 1, started_at: null, finished_at: null }]) as Response
      if (url.endsWith('/attempts')) return response([{ job_id: 7, attempt_id: 1, started_at: '2026-10-19T00:00:00', ended_at: null, exit_reason: null }]) as Response
      if (url.endsWith('/checkpoints')) return response([{ job_id: 7, partition_id: 'p0', offset_value: 9, event_time: '2026-10-19T00:00:00' }]) as Response
      if (url.includes('/metrics?')) return response([{ job_id: 7, metric: 'produce_rate', value: 4, captured_at: '2026-10-19T00:00:00' }]) as Response
      if (url.endsWith('/observe')) return response({ produce_rate: 4, consume_rate: 3, process_rate: 3, input_count: 8, output_count: 6, success_count: 6, failure_count: 0, skipped_count: 0, duplicate_count: 1, backlog: 2, offset_value: 9, window_result: {}, error_samples: [] }) as Response
      if (url.includes('/recovery-events?')) return response([{ event_id: '2', job_id: 7, kind: 'recovery-started', detail: 'x', occurred_at: '2026-10-19T00:00:00' }]) as Response
      throw new Error(`unexpected request ${url} ${String(init?.method)}`)
    })
    const api = createStreamContract(7)
    const window = { from: '2026-10-19T00:00:00Z', to: '2026-10-19T23:59:59Z', offset: 0, limit: 10 }
    expect((await api.listStreamJobs(window))[0].jobId).toBe('7')
    expect((await api.listStreamAttempts(window))[0].attemptId).toBe(1)
    expect((await api.listStreamCheckpoints(window))[0].partition).toBe('p0')
    expect((await api.listStreamMetrics(window))[0].value.value).toBe(4)
    expect((await api.queryStreamObservation(window)).processRate.value).toBe(3)
    expect((await api.listStreamRecoveryEvents(window))[0].kind).toBe('recovery-started')
    expect(fetchMock).toHaveBeenCalledTimes(11)
  })

  it('registers and starts a workflow-bound stream job through the real lifecycle routes', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => response({
      id: 17, name: 'orders-live', workflow_id: 9, mq_topic: 'datara.workflow.9',
      runtime_config: { mode: 'fixed_rate' }, state: String(input).endsWith('/jobs') ? 'CREATED' : 'RUNNING',
      attempt_no: 1, started_at: null, finished_at: null,
    }) as Response)
    const api = createStreamContract(7)
    await expect(api.provisionStreamJob({
      projectId: 7,
      workflowId: 9, name: 'orders-live', mqTopic: 'datara.workflow.9',
      runtimeConfig: { mode: 'fixed_rate', rows_per_sec: 5, columns: ['id', 'value'] },
    })).resolves.toMatchObject({ jobId: '17', state: 'RUNNING' })
    expect(fetchMock.mock.calls.map(([url, init]) => [String(url), init?.method, init?.body])).toEqual([
      ['/api/v1/rebuild/stream/jobs', 'POST', JSON.stringify({ project_id: 7, name: 'orders-live', workflow_id: 9, mq_topic: 'datara.workflow.9', runtime_config: { mode: 'fixed_rate', rows_per_sec: 5, columns: ['id', 'value'] } })],
      ['/api/v1/rebuild/stream/jobs/17/transitions', 'POST', JSON.stringify({ action: 'start' })],
      ['/api/v1/rebuild/stream/jobs/17/transitions', 'POST', JSON.stringify({ action: 'activate' })],
    ])
  })
})
