import { describe, expect, it } from 'vitest'
import source from '../LlmModelManagementView.vue?raw'
import { routes } from '../../router/routes'

describe('15.6 LLM model management view', () => {
  it('registers a direct route and essential operations', () => {
    const route = routes.find((item) => item.path === '/open/llm')
    expect(route?.name).toBe('open-llm')
    expect(route?.component).toBeTruthy()
    for (const marker of ['data-create', 'data-edit', 'data-toggle', 'data-default', 'data-test', 'data-api-key', 'data-delete']) {
      expect(source).toContain(marker)
    }
  })

  it('guards the default model against deletion (§5E.2#6 front-end half of the dual guard)', () => {
    // T3（D-04）：默认模型行删除按钮禁用；后端 409/4092 兜底在 llmApi 契约测试冻结。
    expect(source).toContain('data-delete :disabled="item.isDefault"')
    // 非默认删除仍须二次确认
    expect(source).toContain('globalThis.confirm')
  })

  it('does not persist or place credentials in a URL', () => {
    expect(source).not.toMatch(/localStorage|sessionStorage|location\.(href|search)|router\.push\([^)]*apiKey/)
    expect(source).toContain('autocomplete="new-password"')
  })
})
