import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { createStreamContractSpy, queryStreamObservation, listStreamCheckpoints, listStreamRecoveryEvents, produceStreamEvents, fuseStreamEvents, provisionStreamJob, listStreamJobs } = vi.hoisted(() => ({ createStreamContractSpy: vi.fn(), queryStreamObservation: vi.fn(), listStreamCheckpoints: vi.fn(), listStreamRecoveryEvents: vi.fn(), produceStreamEvents: vi.fn(), fuseStreamEvents: vi.fn(), provisionStreamJob: vi.fn(), listStreamJobs: vi.fn() }))
vi.mock('../../services/rebuild/streamApi', () => ({
  createStreamContract: (projectId?: number) => {
    createStreamContractSpy(projectId)
    return { queryStreamObservation, listStreamCheckpoints, listStreamRecoveryEvents, produceStreamEvents, fuseStreamEvents, provisionStreamJob, listStreamJobs }
  },
}))
import StreamObservationPanel from '../StreamObservationPanel.vue'

const observation = {
  produceRate: { value: 12 }, consumeRate: { value: 11 }, processRate: { value: 10 },
  inputCount: { value: 20 }, outputCount: { value: 18 }, duplicateCount: { value: 1 },
  lag: { value: 2 }, offset: { current: { value: 21 }, committed: { value: 19 } },
  windowResults: [{ windowKey: 'w-1', windowStart: '10:00', windowEnd: '10:01', status: 'success', recordsIn: { value: 20 }, recordsOut: { value: 18 } }],
  counters: { success: { value: 18 }, failure: { value: 1 }, skipped: { value: 1 } },
  errorSamples: [{ jobId: '7', sample: '{"id":9}', flow: 'failed', capturedAt: '10:00:30' }],
}

describe('stream observation panel', () => {
  /** B3 自动轮询（5s interval）依赖 unmount 清理；统一收集防泄漏 */
  const wrappers: VueWrapper[] = []
  function mountPanel(props: Record<string, unknown>): VueWrapper {
    const w = mount(StreamObservationPanel, { props })
    wrappers.push(w)
    return w
  }

  beforeEach(() => {
    vi.clearAllMocks()
    queryStreamObservation.mockResolvedValue(observation)
    produceStreamEvents.mockResolvedValue({ produced: 2 })
    fuseStreamEvents.mockResolvedValue({ fused: 1, result: [] })
    provisionStreamJob.mockResolvedValue({ jobId: '17', state: 'RUNNING' })
    listStreamJobs.mockResolvedValue([])
    listStreamCheckpoints.mockResolvedValue([{ jobId: '7', partition: 'p0', committedOffset: { value: 19 }, currentOffset: { value: 21 }, checkpointedAt: '10:01' }])
    listStreamRecoveryEvents.mockResolvedValue([{ eventId: 'r1', jobId: '7', kind: 'recovery', detail: 'offset restored', occurredAt: '10:02' }])
  })

  afterEach(() => {
    while (wrappers.length) wrappers.pop()?.unmount()
  })

  it('refresh exposes backend errors instead of creating an unhandled rejection', async () => {
    queryStreamObservation.mockRejectedValueOnce(new Error('job not found'))
    const wrapper = mountPanel({ jobId: '7' })
    await wrapper.find('header button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-stream-error]').text()).toContain('job not found')
  })

  it('changing the parent job scope clears stale metrics and uses the new id', async () => {
    const wrapper = mountPanel({ jobId: '7' })
    await wrapper.find('header button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-stream-metrics]').exists()).toBe(true)
    await wrapper.setProps({ jobId: '8' })
    expect(wrapper.find('[data-stream-metrics]').exists()).toBe(false)
    await wrapper.find('header button').trigger('click')
    await flushPromises()
    expect(queryStreamObservation).toHaveBeenLastCalledWith(expect.anything(), '8')
  })

  it('does not let an old job refresh overwrite the new job scope', async () => {
    let resolveOld!: (value: typeof observation) => void
    queryStreamObservation.mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
    const wrapper = mountPanel({ jobId: '7' })
    await wrapper.find('header button').trigger('click')
    await wrapper.setProps({ jobId: '8' })
    resolveOld(observation)
    await flushPromises()
    expect(wrapper.find('[data-stream-metrics]').exists()).toBe(false)
  })

  it('renders the required four observation panels and thirteen metric items', async () => {
    const wrapper = mountPanel({ jobId: '7' })
    await wrapper.find('header button').trigger('click')
    await flushPromises()

    const panels = wrapper.findAll('[data-stream-metric-panel]')
    expect(panels).toHaveLength(4)
    expect(wrapper.findAll('[data-stream-metric]')).toHaveLength(13)
    expect(wrapper.text()).toContain('生产速率 12')
    expect(wrapper.text()).toContain('当前偏移 21')
    expect(wrapper.text()).toContain('跳过 1')
  })

  it('shows traceable window, checkpoint, error and recovery details', async () => {
    const wrapper = mountPanel({ projectId: 7, jobId: '7' })
    await wrapper.find('header button').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-stream-window-results]').text()).toContain('w-1')
    expect(wrapper.get('[data-stream-window-results]').text()).toContain('20 → 18')
    expect(wrapper.get('[data-stream-checkpoints]').text()).toContain('p0')
    expect(wrapper.get('[data-stream-error-samples]').text()).toContain('{"id":9}')
    expect(wrapper.get('[data-stream-recovery-events]').text()).toContain('offset restored')
    expect(listStreamCheckpoints).toHaveBeenCalledWith(expect.anything(), '7')
    expect(listStreamRecoveryEvents).toHaveBeenCalledWith(expect.anything(), '7')
  })

  it('keeps core metrics visible when auxiliary checkpoint history is unavailable', async () => {
    listStreamCheckpoints.mockRejectedValueOnce(new Error('checkpoint offline'))
    const wrapper = mountPanel({ projectId: 7, jobId: '7' })
    await wrapper.find('header button').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-stream-metrics]').exists()).toBe(true)
    expect(wrapper.get('[data-stream-detail-warning]').text()).toContain('checkpoint offline')
  })

  it('creates, activates and produces a live stream for the current workflow', async () => {
    const wrapper = mountPanel({ projectId: 7, workflowId: 9, workflowName: 'orders' })
    await wrapper.get('[data-stream-provision]').trigger('click')
    await flushPromises()
    expect(provisionStreamJob).toHaveBeenCalledWith(expect.objectContaining({ projectId: 7, workflowId: 9, name: 'orders-live' }))
    expect(produceStreamEvents).toHaveBeenCalledWith('17', expect.objectContaining({ count: 10 }))
    expect(wrapper.get('[data-stream-job-id]').element).toHaveProperty('value', '17')
  })

  it('rebinds the stream API client after navigating to another project', async () => {
    const wrapper = mountPanel({ projectId: 7, workflowId: 9, workflowName: 'orders' })
    await wrapper.setProps({ projectId: 8, workflowId: 10, workflowName: 'invoices' })
    await wrapper.get('[data-stream-provision]').trigger('click')
    await flushPromises()

    expect(createStreamContractSpy).toHaveBeenLastCalledWith(8)
    expect(provisionStreamJob).toHaveBeenCalledWith(expect.objectContaining({ projectId: 8, workflowId: 10 }))
  })

  it('submits valid stream JSON to the fusion endpoint and reports the result', async () => {
    const wrapper = mountPanel({ jobId: '7' })
    await wrapper.find('[data-stream-fuse-submit]').trigger('click')
    await flushPromises()
    expect(fuseStreamEvents).toHaveBeenCalledWith('7', 'id', {
      orders: [{ id: 1, amount: 10 }],
      customers: [{ id: 1, name: 'Ada' }],
    })
    expect(wrapper.find('[data-stream-fuse]').text()).toContain('最近融合 1')
  })

  it('B3：jobId 为空时按 workflow 自动绑定 running job 并立即观摩', async () => {
    listStreamJobs.mockResolvedValue([
      { jobId: '31', kind: 'stream', state: 'stopped', startedAt: null, workflowId: 9 },
      { jobId: '33', kind: 'stream', state: 'running', startedAt: '10:00', workflowId: 9 },
    ])
    const wrapper = mountPanel({ projectId: 7, workflowId: 9 })
    await flushPromises()
    expect(listStreamJobs).toHaveBeenCalledTimes(1)
    expect((wrapper.get('[data-stream-job-id]').element as HTMLInputElement).value).toBe('33')
    expect(queryStreamObservation).toHaveBeenCalledWith(expect.anything(), '33')
    expect(wrapper.find('[data-stream-live]').exists()).toBe(true)
  })

  it('B3：jobId 就绪后 5s 自动轮询观摩，卸载停止', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] })
    try {
      queryStreamObservation.mockClear()
      const wrapper = mountPanel({ jobId: '7' })
      await flushPromises()
      expect(queryStreamObservation).not.toHaveBeenCalled() // 挂载仅注册轮询，不立即拉取

      vi.advanceTimersByTime(5000)
      expect(queryStreamObservation).toHaveBeenCalledTimes(1) // 首个轮询周期触发
      const afterPoll = queryStreamObservation.mock.calls.length
      wrapper.unmount()
      vi.advanceTimersByTime(15000)
      expect(queryStreamObservation.mock.calls.length).toBe(afterPoll) // 卸载后不再轮询
    } finally {
      vi.useRealTimers()
    }
  })

  it('B3：融合结果行渲染（result 数组逐行呈现，非仅计数）', async () => {
    fuseStreamEvents.mockResolvedValue({
      fused: 2,
      result: [{ id: 1, name: 'Ada' }, { id: 2, name: 'Bob' }],
    })
    const wrapper = mountPanel({ jobId: '7' })
    expect(wrapper.find('[data-stream-fuse-result]').exists()).toBe(false)
    await wrapper.find('[data-stream-fuse-submit]').trigger('click')
    await flushPromises()
    const result = wrapper.get('[data-stream-fuse-result]')
    expect(result.text()).toContain('融合结果行（2）')
    expect(result.text()).toContain('Ada')
    expect(result.text()).toContain('Bob')
  })
})
