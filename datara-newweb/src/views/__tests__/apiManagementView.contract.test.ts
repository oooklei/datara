import { flushPromises, mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  list: vi.fn().mockResolvedValue([]),
  callLogs: vi.fn().mockResolvedValue({ list: [] }),
  create: vi.fn(), update: vi.fn(), publish: vi.fn(), disable: vi.fn(), enable: vi.fn(), remove: vi.fn(),
}))
vi.mock('../../services/rebuild/openapiAdminApi', () => ({ openapiAdminApi: api }))
import ApiManagementView from '../ApiManagementView.vue'

describe('API 管理弹窗契约', () => {
  beforeEach(() => {
    for (const fn of Object.values(api)) fn.mockReset()
    api.list.mockResolvedValue([])
    api.callLogs.mockResolvedValue({ list: [] })
  })

  it('编辑遮罩具备对话框语义，并支持点击遮罩关闭', async () => {
    const w = mount(ApiManagementView)
    await nextTick()
    await w.find('[data-create]').trigger('click')
    const mask = w.find('[data-editor-mask]')
    expect(mask.exists()).toBe(true)
    expect(mask.find('[role="dialog"]').attributes('aria-modal')).toBe('true')
    await mask.trigger('click')
    expect(w.find('[data-editor-mask]').exists()).toBe(false)
  })

  it('发布请求在途时禁用写按钮并阻止重复提交', async () => {
    api.list.mockResolvedValueOnce([{ id: 7, name: '订单查询', method: 'GET', path: '/orders', version: 'v1', requiredPermission: 'data:read', status: 'draft' }])
      .mockResolvedValueOnce([{ id: 7, name: '订单查询', method: 'GET', path: '/orders', version: 'v1', requiredPermission: 'data:read', status: 'published' }])
    let resolvePublish!: () => void
    api.publish.mockReturnValue(new Promise<void>((resolve) => { resolvePublish = resolve }))
    const w = mount(ApiManagementView)
    await flushPromises()
    const publish = w.get('[data-publish]')

    void publish.trigger('click')
    void publish.trigger('click')
    await nextTick()
    expect(api.publish).toHaveBeenCalledTimes(1)
    expect(publish.attributes('disabled')).toBeDefined()

    resolvePublish()
    await flushPromises()
    expect(w.find('[data-publish]').exists()).toBe(false)
  })
})
