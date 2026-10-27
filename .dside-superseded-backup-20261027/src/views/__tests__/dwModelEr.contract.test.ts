/**
 * ER 画布页契约测试：读取 ER 图（GET /models/er）与保存布局（PUT /models/er，positions + relations 三键增量）。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ getEr: vi.fn(), putEr: vi.fn() }))
vi.mock('../../services/rebuild/modelApi', () => ({ modelApi: api }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))

import View from '../dwmodel/ErCanvasView.vue'

const graph = {
  nodes: [
    { id: '8', model: { id: 8, code: 'dwd_orders', name: '订单', layer: 'DWD', type: '明细表', bizDomain: '', engine: 'mysql', engineXc: false, dsId: null, dbName: null, securityLevel: '内部', status: 'draft', version: 1, owner: 'admin', builtAt: null, updatedAt: null, remark: '' }, erPos: { x: 200, y: 160 } },
    { id: '9', model: { id: 9, code: 'dws_trade', name: '交易汇总', layer: 'DWS', type: '汇总表', bizDomain: '', engine: 'mysql', engineXc: false, dsId: null, dbName: null, securityLevel: '内部', status: 'draft', version: 1, owner: 'admin', builtAt: null, updatedAt: null, remark: '' }, erPos: { x: 600, y: 160 } },
  ],
  edges: [{ id: 'e1', source: '8', target: '9', relType: '1:N', srcFields: 'id', tgtFields: 'order_id', joinDesc: '' }],
}

describe('er canvas view', () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset()
    api.getEr.mockResolvedValue(graph)
    api.putEr.mockResolvedValue(true)
  })

  it('loads the ER graph and renders nodes and edges', async () => {
    const wrapper = mount(View, { props: { layer: 'DWD' } })
    await flushPromises()
    expect(api.getEr).toHaveBeenCalledWith({ layer: 'DWD', domain: '' })
    expect(wrapper.find('[data-er-canvas]').exists()).toBe(true)
    expect(wrapper.findAll('[data-er-node]').length).toBe(2)
    expect(wrapper.findAll('[data-er-edge]').length).toBe(1)
  })

  it('saves positions and an empty relation diff to PUT /models/er', async () => {
    const wrapper = mount(View, { props: { layer: 'DWD' } })
    await flushPromises()
    await wrapper.find('[data-er-save]').trigger('click')
    await flushPromises()
    expect(api.putEr).toHaveBeenCalledWith(expect.objectContaining({
      positions: { '8': { x: 200, y: 160 }, '9': { x: 600, y: 160 } },
      relations: { removed: [], added: [], updated: [] },
    }))
  })
})
