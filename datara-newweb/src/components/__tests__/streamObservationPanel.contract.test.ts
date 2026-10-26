import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { queryStreamObservation, listStreamCheckpoints, listStreamRecoveryEvents, produceStreamEvents, fuseStreamEvents, provisionStreamJob } = vi.hoisted(() => ({ queryStreamObservation: vi.fn(), listStreamCheckpoints: vi.fn(), listStreamRecoveryEvents: vi.fn(), produceStreamEvents: vi.fn(), fuseStreamEvents: vi.fn(), provisionStreamJob: vi.fn() }))
vi.mock('../../services/rebuild/streamApi', () => ({
  createStreamContract: () => ({ queryStreamObservation, listStreamCheckpoints, listStreamRecoveryEvents, produceStreamEvents, fuseStreamEvents, provisionStreamJob }),
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
  beforeEach(() => {
    vi.clearAllMocks()
    queryStreamObservation.mockResolvedValue(observation)
    produceStreamEvents.mockResolvedValue({ produced: 2 })
    fuseStreamEvents.mockResolvedValue({ fused: 1 })
    provisionStreamJob.mockResolvedValue({ jobId: '17', state: 'RUNNING' })
    listStreamCheckpoints.mockResolvedValue([{ jobId: '7', partition: 'p0', committedOffset: { value: 19 }, currentOffset: { value: 21 }, checkpointedAt: '10:01' }])
    listStreamRecoveryEvents.mockResolvedValue([{ eventId: 'r1', jobId: '7', kind: 'recovery', detail: 'offset restored', occurredAt: '10:02' }])
  })

  it('refresh exposes backend errors instead of creating an unhandled rejection', async () => {
    queryStreamObservation.mockRejectedValueOnce(new Error('job not found'))
    const wrapper = mount(StreamObservationPanel, { props: { jobId: '7' } })
    await wrapper.find('header button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-stream-error]').text()).toContain('job not found')
  })

  it('changing the parent job scope clears stale metrics and uses the new id', async () => {
    const wrapper = mount(StreamObservationPanel, { props: { jobId: '7' } })
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
    const wrapper = mount(StreamObservationPanel, { props: { jobId: '7' } })
    await wrapper.find('header button').trigger('click')
    await wrapper.setProps({ jobId: '8' })
    resolveOld(observation)
    await flushPromises()
    expect(wrapper.find('[data-stream-metrics]').exists()).toBe(false)
  })

  it('renders the required four observation panels and thirteen metric items', async () => {
    const wrapper = mount(StreamObservationPanel, { props: { jobId: '7' } })
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
    const wrapper = mount(StreamObservationPanel, { props: { projectId: 7, jobId: '7' } })
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
    const wrapper = mount(StreamObservationPanel, { props: { projectId: 7, jobId: '7' } })
    await wrapper.find('header button').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-stream-metrics]').exists()).toBe(true)
    expect(wrapper.get('[data-stream-detail-warning]').text()).toContain('checkpoint offline')
  })

  it('creates, activates and produces a live stream for the current workflow', async () => {
    const wrapper = mount(StreamObservationPanel, { props: { projectId: 7, workflowId: 9, workflowName: 'orders' } })
    await wrapper.get('[data-stream-provision]').trigger('click')
    await flushPromises()
    expect(provisionStreamJob).toHaveBeenCalledWith(expect.objectContaining({ projectId: 7, workflowId: 9, name: 'orders-live' }))
    expect(produceStreamEvents).toHaveBeenCalledWith('17', expect.objectContaining({ count: 10 }))
    expect(wrapper.get('[data-stream-job-id]').element).toHaveProperty('value', '17')
  })

  it('submits valid stream JSON to the fusion endpoint and reports the result', async () => {
    const wrapper = mount(StreamObservationPanel, { props: { jobId: '7' } })
    await wrapper.find('[data-stream-fuse-submit]').trigger('click')
    await flushPromises()
    expect(fuseStreamEvents).toHaveBeenCalledWith('7', 'id', {
      orders: [{ id: 1, amount: 10 }],
      customers: [{ id: 1, name: 'Ada' }],
    })
    expect(wrapper.find('[data-stream-fuse]').text()).toContain('最近融合 1')
  })
})
