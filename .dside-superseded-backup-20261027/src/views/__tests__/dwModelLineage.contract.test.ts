/**
 * 模型血缘页契约测试：血缘图（节点/边）与下游影响清单。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ lineage: vi.fn(), impact: vi.fn() }))
vi.mock('../../services/rebuild/modelApi', () => ({ modelApi: api }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))

import View from '../dwmodel/ModelLineageView.vue'

const graph = {
  nodes: [
    { id: 'ext:orders', kind: 'ext', label: 'orders' },
    { id: '8', kind: 'model', label: 'dwd_orders' },
  ],
  edges: [{ from: 'ext:orders', to: '8', kind: 'declared', relType: '1:N' }],
  sources: { declared: 1, runtime: 0 },
}

describe('model lineage view', () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset()
    api.lineage.mockResolvedValue(graph)
    api.impact.mockResolvedValue({ list: [{ modelId: 9, code: 'dws_trade', name: '交易汇总', path: 'dwd_orders → dws_trade' }] })
  })

  it('renders the lineage graph and the downstream impact list', async () => {
    const wrapper = mount(View, { props: { modelId: 8 } })
    await flushPromises()
    expect(api.lineage).toHaveBeenCalledWith(8)
    expect(api.impact).toHaveBeenCalledWith(8)
    expect(wrapper.find('[data-lineage]').exists()).toBe(true)
    expect(wrapper.find('[data-lineage-canvas]').exists()).toBe(true)
    expect(wrapper.findAll('[data-lineage-node]').length).toBe(2)
    expect(wrapper.findAll('[data-lineage-edge]').length).toBe(1)
    expect(wrapper.find('[data-impact-list]').exists()).toBe(true)
    expect(wrapper.find('[data-impact-id="9"]').text()).toContain('dws_trade')
  })
})
