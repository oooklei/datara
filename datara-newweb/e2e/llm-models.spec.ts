import { expect, test as base, type Page } from '@playwright/test'
import { authenticatedContext, login } from './support/auth'

const test = base.extend<{ authPage: Page }>({
  authPage: async ({ browser, request }, use) => {
    const context = await authenticatedContext(browser, await login(request))
    await use(await context.newPage())
    await context.close()
  },
})

const t = (name: string): string => `[data-test="${name}"]`

test.describe.serial('LLM 模型配置闭环', () => {
  const suffix = `${Date.now()}`
  const modelName = `e2e-llm-${suffix}`
  const runtimeKey = process.env.E2E_LLM_TEST_KEY ?? `runtime-probe-${suffix}`
  const apiBase = process.env.E2E_LLM_TEST_BASE ?? 'https://127.0.0.1:9/v1'

  test('路由、新建、掩码与连通性结果', async ({ authPage: page }) => {
    await page.goto('/open/llm')
    await expect(page.locator(t('llm-page'))).toBeVisible()
    await page.locator(t('llm-create')).click()
    await page.fill(t('llm-form-name'), modelName)
    await page.fill(t('llm-form-display-name'), 'E2E 临时模型')
    await page.selectOption(t('llm-form-provider'), 'siliconflow')
    await page.fill(t('llm-form-api-base'), apiBase)
    await page.fill(t('llm-form-model-id'), 'e2e-probe-model')
    await page.fill(t('llm-form-api-key'), runtimeKey)
    await page.locator(t('llm-form-save')).click()

    const row = page.locator(`[data-test="llm-row"][data-llm-name="${modelName}"]`)
    await expect(row).toBeVisible()
    const keyCellText = await row.locator(t('llm-api-key')).innerText()
    const keyLeaked = keyCellText.includes(runtimeKey)
    expect(keyLeaked).toBe(false)
    await row.locator(t('llm-test')).click()
    const id = await row.getAttribute('data-llm-id')
    await expect(page.locator(t(`llm-test-result-${id}`))).toBeVisible({ timeout: 40_000 })
  })

  test('非默认模型经确认删除', async ({ authPage: page }) => {
    await page.goto('/open/llm')
    const row = page.locator(`[data-test="llm-row"][data-llm-name="${modelName}"]`)
    await row.locator(t('llm-delete')).click()
    const box = page.locator('.el-message-box')
    await box.getByRole('button', { name: '删除', exact: true }).click()
    await expect(row).toBeHidden()
  })
})
