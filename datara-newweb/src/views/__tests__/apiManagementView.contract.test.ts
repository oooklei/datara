import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  list: vi.fn().mockResolvedValue([]),
  callLogs: vi.fn().mockResolvedValue({ list: [] }),
  create: vi.fn(), update: vi.fn(), publish: vi.fn(), disable: vi.fn(), enable: vi.fn(), remove: vi.fn(),
}))
vi.mock('../../services/rebuild/openapiAdminApi', () => ({ openapiAdminApi: api }))
import ApiManagementView from '../ApiManagementView.vue'

describe('API 管理弹窗契约', () => {
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
})
