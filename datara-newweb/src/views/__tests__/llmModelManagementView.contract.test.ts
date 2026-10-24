import { describe, expect, it } from 'vitest'
import source from '../LlmModelManagementView.vue?raw'
import { routes } from '../../router/routes'

describe('15.6 LLM model management view', () => {
  it('registers a direct route and essential operations', () => {
    const route = routes.find((item) => item.path === '/open/llm')
    expect(route?.name).toBe('open-llm')
    expect(route?.component).toBeTruthy()
    for (const marker of ['data-create', 'data-edit', 'data-toggle', 'data-default', 'data-test', 'data-api-key']) {
      expect(source).toContain(marker)
    }
  })

  it('does not persist or place credentials in a URL', () => {
    expect(source).not.toMatch(/localStorage|sessionStorage|location\.(href|search)|router\.push\([^)]*apiKey/)
    expect(source).toContain('autocomplete="new-password"')
  })
})
