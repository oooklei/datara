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

  it('D13 列表搜索：关键字前端过滤 API 定义与调用日志，不触发后端', async () => {
    api.list.mockResolvedValue([
      { id: 1, name: '订单查询', method: 'GET', path: '/orders', version: 'v1', requiredPermission: 'data:read', status: 'draft' },
      { id: 2, name: '用户同步', method: 'POST', path: '/users/sync', version: 'v1', requiredPermission: 'data:write', status: 'published' },
    ])
    api.callLogs.mockResolvedValue({ list: [
      { requestId: 'req-aaa', apiId: 1, principal: 'alice', statusCode: 200, latencyMs: 12, result: 'ok', requestedAt: '2026-10-28T10:00:00' },
      { requestId: 'req-bbb', apiId: 2, principal: 'bob', statusCode: 500, latencyMs: 30, result: 'err', requestedAt: '2026-10-28T10:05:00' },
    ] })
    const w = mount(ApiManagementView)
    await flushPromises()

    // API 定义：按名称过滤，计数徽标同步，且不触发后端重查
    expect(w.findAll('[data-api-list] tbody tr')).toHaveLength(2)
    await w.get('[data-filter-keyword]').setValue('订单')
    const defRows = w.findAll('[data-api-list] tbody tr')
    expect(defRows).toHaveLength(1)
    expect(defRows[0]!.text()).toContain('订单查询')
    expect(w.get('[data-api-count]').text()).toContain('1 条')
    expect(api.list).toHaveBeenCalledTimes(1)

    // 调用日志：切 tab 后按 requestId 过滤；无匹配时呈现兜底行
    await w.get('[data-tab="log"]').trigger('click')
    await flushPromises()
    await w.get('[data-filter-keyword]').setValue('req-bbb')
    const logRows = w.findAll('[data-log-list] tbody tr')
    expect(logRows).toHaveLength(1)
    expect(logRows[0]!.text()).toContain('req-bbb')
    expect(w.get('[data-logs-count]').text()).toContain('1 条')
    await w.get('[data-filter-keyword]').setValue('不存在')
    expect(w.findAll('[data-log-list] tbody tr')[0]!.text()).toContain('无匹配日志')
  })
})
