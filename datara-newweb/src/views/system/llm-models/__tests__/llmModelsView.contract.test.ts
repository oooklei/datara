import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  remove: vi.fn(),
  confirm: vi.fn(),
}))

vi.mock('../../../../services/rebuild/llmApi', async (original) => {
  const actual = await original<typeof import('../../../../services/rebuild/llmApi')>()
  return {
    ...actual,
    llmApi: {
      list: mocks.list,
      remove: mocks.remove,
      update: vi.fn(),
      setDefault: vi.fn(),
      testModel: vi.fn(),
    },
  }
})

vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  ElMessageBox: { confirm: mocks.confirm },
}))

import LlmModelsView from '../LlmModelsView.vue'

const model = (id: number, isDefault: boolean) => ({
  id,
  name: `model-${id}`,
  displayName: `模型 ${id}`,
  provider: 'volcengine' as const,
  apiBase: 'https://example.invalid/v1',
  modelId: `endpoint-${id}`,
  apiKey: '****1234',
  maxTokens: 1000,
  temperature: 0.2,
  isActive: true,
  isDefault,
  sortOrder: id,
})

describe('LLM 模型正式管理页删除保护', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.list.mockResolvedValue({ items: [model(1, true), model(2, false)] })
    mocks.confirm.mockResolvedValue('confirm')
    mocks.remove.mockResolvedValue({ deleted: true, id: 2 })
  })

  it('默认模型禁删，非默认模型确认后才调用删除 API', async () => {
    const wrapper = mount(LlmModelsView, {
      global: { stubs: { LlmModelFormDialog: true } },
    })
    await flushPromises()

    const buttons = wrapper.findAll('[data-test="llm-delete"]')
    expect(buttons).toHaveLength(2)
    expect(buttons[0].attributes('disabled')).toBeDefined()
    expect(buttons[0].attributes('title')).toBe('默认模型不可删除')
    await buttons[0].trigger('click')
    expect(mocks.confirm).not.toHaveBeenCalled()
    expect(mocks.remove).not.toHaveBeenCalled()

    await buttons[1].trigger('click')
    await flushPromises()
    expect(mocks.confirm).toHaveBeenCalledOnce()
    expect(mocks.remove).toHaveBeenCalledWith(2)
  })

  it('D13 列表搜索：关键字前端过滤模型行，不触发后端', async () => {
    const wrapper = mount(LlmModelsView, {
      global: { stubs: { LlmModelFormDialog: true } },
    })
    await flushPromises()

    expect(wrapper.findAll('[data-test="llm-row"]')).toHaveLength(2)
    expect(mocks.list).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-filter-keyword]').setValue('model-2')
    const rows = wrapper.findAll('[data-test="llm-row"]')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.attributes('data-llm-id')).toBe('2')
    expect(mocks.list).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-filter-keyword]').setValue('不存在')
    expect(wrapper.get('[data-test="llm-list"] tbody').text()).toContain('无匹配模型')
  })
})
