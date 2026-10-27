/**
 * 模型设计页契约测试：详情加载、字段全量保存（乐观锁 rev）、发布/重新起草、DDL 预览、物理化。
 * `services/rebuild/modelApi` 被整体 mock，断言落在视图的锚点与调用参数上。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  detail: vi.fn(), updateFields: vi.fn(), publish: vi.fn(), redraft: vi.fn(), ddl: vi.fn(), physicalize: vi.fn(),
}))
vi.mock('../../services/rebuild/modelApi', () => ({ modelApi: api }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))

import View from '../dwmodel/ModelDesignView.vue'

const detail = {
  id: 8, code: 'dwd_orders', name: '订单', layer: 'DWD', type: '明细表', bizDomain: '交易域',
  engine: 'mysql', engineXc: false, dsId: null, dbName: null, securityLevel: '内部',
  status: 'draft', version: 1, owner: 'admin', builtAt: null, updatedAt: null, remark: '',
  fields: [{ name: 'id', dataType: 'bigint', length: null, precision: null, nullable: false, defaultValue: null, comment: '主键', isPk: true, isPartition: false, dictRef: null }],
}

describe('model design view', () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset()
    api.detail.mockResolvedValue(detail)
    api.updateFields.mockResolvedValue(2)
    api.publish.mockResolvedValue({ status: 'published' })
    api.ddl.mockResolvedValue({ engine: 'mysql', ddl: 'CREATE TABLE dwd_orders()', notes: [] })
    api.physicalize.mockResolvedValue({ script: 'CREATE TABLE dwd_orders();', notes: [] })
  })

  it('loads the model detail and exposes the design surface', async () => {
    const wrapper = mount(View, { props: { modelId: 8 } })
    await flushPromises()
    expect(api.detail).toHaveBeenCalledWith(8)
    expect(wrapper.find('[data-model-design]').exists()).toBe(true)
    expect(wrapper.find('[data-model-meta]').text()).toContain('dwd_orders')
    expect(wrapper.find('[data-field-table]').exists()).toBe(true)
  })

  it('saves the full field set with the optimistic-lock rev', async () => {
    const wrapper = mount(View, { props: { modelId: 8 } })
    await flushPromises()
    await wrapper.find('[data-save-fields]').trigger('click')
    await flushPromises()
    expect(api.updateFields).toHaveBeenCalledWith(8, expect.objectContaining({ rev: 1, fields: expect.any(Array) }))
  })

  it('publishes, previews DDL, and physicalizes the model', async () => {
    const wrapper = mount(View, { props: { modelId: 8 } })
    await flushPromises()

    await wrapper.find('[data-publish]').trigger('click')
    await flushPromises()
    expect(api.publish).toHaveBeenCalledWith(8)

    await wrapper.find('[data-ddl]').trigger('click')
    await flushPromises()
    expect(api.ddl).toHaveBeenCalledWith(8, 'mysql')
    expect(wrapper.find('[data-ddl-preview]').text()).toContain('CREATE TABLE')

    await wrapper.find('[data-physicalize]').trigger('click')
    await wrapper.find('[data-physicalize-confirm]').trigger('click')
    await flushPromises()
    expect(api.physicalize).toHaveBeenCalledWith(8, expect.objectContaining({ engine: 'mysql', mode: 'script' }))
  })
})
