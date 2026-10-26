import { expect, test as base, type Page } from '@playwright/test'
import { authenticatedContext, login } from './support/auth'

const test = base.extend<{ authPage: Page }>({
  authPage: async ({ browser, request }, use) => {
    const context = await authenticatedContext(browser, await login(request))
    await use(await context.newPage())
    await context.close()
  },
})

test.describe.serial('质量规则 structural 闭环', () => {
  let projectId = 0
  let assetId = 0
  const ruleName = `e2e-quality-${Date.now()}`

  test.beforeAll(() => {
    projectId = requiredPositiveInt('E2E_PROJECT_ID')
    assetId = requiredPositiveInt('E2E_ASSET_ID')
  })

  test('路由、新建规则与 structural 运行结果', async ({ authPage: page }) => {
    await page.goto(`/qc/rule?projectId=${projectId}`)
    await expect(page.getByRole('heading', { name: '质量规则' })).toBeVisible()
    await expect(page.locator('[data-structural-note]')).toContainText('structural')
    await page.locator('[data-create]').click()
    await page.fill('[data-name]', ruleName)
    await page.fill('[data-asset-input]', String(assetId))
    await page.fill('[data-expr-input]', 'not_null(id)')
    await page.selectOption('[data-severity-select]', 'warning')
    await page.locator('[data-save]').click()

    const row = page.locator('tr[data-rule-id]', { hasText: ruleName })
    await expect(row).toBeVisible()
    await row.locator('[data-run]').click()
    await expect(page.locator('[data-run-result]')).toContainText('structural', { timeout: 40_000 })
    await expect(page.locator('[data-run-result]')).toContainText('行级四字段恒 0')
  })

  test('运行记录跳转保留项目上下文', async ({ authPage: page }) => {
    await page.goto(`/qc/rule?projectId=${projectId}`)
    await page.locator('[data-goto-runs]').click()
    await expect(page).toHaveURL(new RegExp(`/qc/task\\?projectId=${projectId}`))
  })
})

function requiredPositiveInt(name: 'E2E_PROJECT_ID' | 'E2E_ASSET_ID'): number {
  const raw = process.env[name] ?? ''
  if (!/^[1-9]\d*$/.test(raw)) throw new Error(`${name} 必须显式注入正整数`)
  return Number(raw)
}
