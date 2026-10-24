import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { queryStreamObservation, produceStreamEvents, fuseStreamEvents } = vi.hoisted(() => ({ queryStreamObservation: vi.fn(), produceStreamEvents: vi.fn(), fuseStreamEvents: vi.fn() }))
vi.mock('../../services/rebuild/streamApi', () => ({
  createStreamContract: () => ({ queryStreamObservation, produceStreamEvents, fuseStreamEvents }),
}))
import StreamObservationPanel from '../StreamObservationPanel.vue'

const observation = { inputCount: { value: 2 }, outputCount: { value: 1 }, counters: { success: { value: 1 }, failure: { value: 0 }, skipped: { value: 0 } }, lag: { value: 0 } }

describe('stream observation panel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryStreamObservation.mockResolvedValue(observation)
    produceStreamEvents.mockResolvedValue({ produced: 2 })
    fuseStreamEvents.mockResolvedValue({ fused: 1 })
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
