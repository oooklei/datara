import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import View from '../ApiKeyManagementView.vue'
import { openapiAdminKeyApi } from '../../services/rebuild/openapiAdminApi'

vi.mock('../../services/rebuild/openapiAdminApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/rebuild/openapiAdminApi')>('../../services/rebuild/openapiAdminApi')
  return { ...actual, openapiAdminKeyApi: { list: vi.fn(), issue: vi.fn(), rotate: vi.fn(), revoke: vi.fn() } }
})
const key = { id: 1, name: 'ci', keyPrefix: 'dk_live_abc', scopes: { permissions: ['security:read'], projectIds: [] }, status: 'active' as const, expiresAt: null, lastUsedAt: null, createdBy: 'admin', revokedAt: null, createdAt: '', updatedAt: '' }
afterEach(() => vi.clearAllMocks())
vi.stubGlobal('confirm', () => true)
describe('API-Key 管理页面', () => {
  it('列表不显示明文 key，并支持撤销', async () => {
    vi.mocked(openapiAdminKeyApi.list).mockResolvedValue([key]); vi.mocked(openapiAdminKeyApi.revoke).mockResolvedValue({ ...key, status: 'revoked' })
    const w = mount(View); await flushPromises(); expect(w.find('[data-key-list]').exists()).toBe(true); expect(w.find('[data-plain-key]').exists()).toBe(false)
    await w.find('[data-revoke]').trigger('click'); await flushPromises(); expect(openapiAdminKeyApi.revoke).toHaveBeenCalledWith(1)
  })
  it('签发后只展示一次性明文并可关闭', async () => {
    vi.mocked(openapiAdminKeyApi.list).mockResolvedValue([]); vi.mocked(openapiAdminKeyApi.issue).mockResolvedValue({ key, plainKey: 'dk_live_secret_once' })
    const w = mount(View); await w.find('[data-issue]').trigger('click'); await w.find('[data-name]').setValue('ci'); await w.find('[data-permissions]').setValue('security:read'); await w.find('form').trigger('submit'); await flushPromises()
    expect(openapiAdminKeyApi.issue).toHaveBeenCalledWith(expect.objectContaining({ name: 'ci', scopes: { permissions: ['security:read'], projectIds: [] } })); expect(w.find('[data-plain-key]').text()).toBe('dk_live_secret_once'); await w.find('[data-close-key]').trigger('click'); expect(w.find('[data-plain-key]').exists()).toBe(false)
  })
})
