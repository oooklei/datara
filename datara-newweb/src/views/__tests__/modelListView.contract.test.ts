import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import View from '../dwmodel/ModelListView.vue'

const routerPush = vi.hoisted(() => vi.fn())
vi.mock('vue-router', () => ({ useRouter: () => ({ push: routerPush }) }))

const api = vi.hoisted(() => ({
  list: vi.fn(), create: vi.fn(), update: vi.fn(), remove: vi.fn(),
  publish: vi.fn(), redraft: vi.fn(), ddl: vi.fn(),
}))
vi.mock('../../services/rebuild/modelApi', () => ({ modelApi: api }))

describe('model list view', () => {
  beforeEach(() => {
    routerPush.mockReset()
    for (const fn of Object.values(api)) fn.mockReset()
    api.list.mockResolvedValue({ total: 1, layers: [], domains: [], list: [{
      id: 8, code: 'dwd_orders', name: '订单', layer: 'DWD', type: '明细表', bizDomain: '交易域',
      engine: 'mysql', engineXc: false, dsId: null, dbName: null, securityLevel: '内部',
      status: 'draft', version: 1, owner: 'admin', builtAt: null, updatedAt: null, remark: '',
    }] })
    api.create.mockResolvedValue({ id: 9 })
    api.publish.mockResolvedValue({ status: 'published' })
    api.ddl.mockResolvedValue({ engine: 'mysql', ddl: 'CREATE TABLE dwd_orders()', notes: [] })
  })

  it('loads models and wires create, publish, and DDL actions', async () => {
    const wrapper = mount(View)
    await flushPromises()
    expect(wrapper.find('[data-model-id="8"]').text()).toContain('dwd_orders')

    await wrapper.find('[data-create]').trigger('click')
    await wrapper.find('[data-field-name]').setValue('客户')
    await wrapper.find('[data-field-code]').setValue('dim_customer')
    await wrapper.find('[data-save]').trigger('click')
    await flushPromises()
    expect(api.create).toHaveBeenCalledWith(expect.objectContaining({ code: 'dim_customer' }))

    const buttons = wrapper.find('[data-model-id="8"]').findAll('button')
    await buttons.find((button) => button.text() === '发布')!.trigger('click')
    await buttons.find((button) => button.text() === 'DDL')!.trigger('click')
    await flushPromises()
    expect(api.publish).toHaveBeenCalledWith(8)
    expect(wrapper.find('[data-ddl-dialog]').text()).toContain('CREATE TABLE')
  })

  it('opens design, version, lineage, and ER workspaces from the model list', async () => {
    const wrapper = mount(View)
    await flushPromises()

    const row = wrapper.find('[data-model-id="8"]')
    await row.find('[data-open-design]').trigger('click')
    await row.find('[data-open-version]').trigger('click')
    await row.find('[data-open-lineage]').trigger('click')
    await wrapper.find('[data-open-er]').trigger('click')

    expect(routerPush).toHaveBeenNthCalledWith(1, { path: '/model/design', query: { modelId: 8 } })
    expect(routerPush).toHaveBeenNthCalledWith(2, { path: '/model/version', query: { modelId: 8 } })
    expect(routerPush).toHaveBeenNthCalledWith(3, { path: '/model/lineage', query: { modelId: 8 } })
    expect(routerPush).toHaveBeenNthCalledWith(4, { path: '/model/er' })
  })
})
