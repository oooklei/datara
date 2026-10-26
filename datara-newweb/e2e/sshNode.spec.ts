import { expect, test as base, type Page } from '@playwright/test'
import { authenticatedContext, login } from './support/auth'

const test = base.extend<{ authPage: Page }>({
  authPage: async ({ browser, request }, use) => {
    const context = await authenticatedContext(browser, await login(request))
    await use(await context.newPage())
    await context.close()
  },
})

test.describe.serial('SSH 节点管理闭环', () => {
  const suffix = `${Date.now()}`
  const nodeName = `e2e-ssh-${suffix}`
  const runtimeCredential = `runtime-credential-${suffix}`

  test('新建、凭据遮罩与探测', async ({ authPage: page }) => {
    await page.goto('/dep/ssh')
    await expect(page.getByRole('heading', { name: 'SSH 节点' })).toBeVisible()
    await page.locator('[data-create]').click()
    await page.fill('[data-name]', nodeName)
    await page.fill('[data-host]', process.env.E2E_SSH_PROBE_HOST ?? '192.0.2.1')
    await page.fill('[data-port]', '22')
    await page.fill('[data-user]', 'root')
    await page.fill('[data-cred-input]', runtimeCredential)
    await page.locator('[data-save]').click()

    const row = page.locator('tr[data-node-id]', { hasText: nodeName })
    await expect(row.locator('[aria-label="凭据已遮罩"]')).toBeVisible()
    const maskedBody = await page.locator('body').innerText()
    const maskedCredentialLeaked = maskedBody.includes(runtimeCredential)
    expect(maskedCredentialLeaked).toBe(false)
    await row.locator('[data-probe]').click()
    await expect(page.locator('[data-probe-result]')).toContainText('连接', { timeout: 40_000 })
  })

  test('显示后可重新遮罩并删除', async ({ authPage: page }) => {
    await page.goto('/dep/ssh')
    const row = page.locator('tr[data-node-id]', { hasText: nodeName })
    const toggle = row.locator('[data-cred-toggle]')
    await toggle.click()
    const revealedText = await row.locator('[data-cred]').innerText()
    const credentialRevealed = revealedText.includes(runtimeCredential)
    expect(credentialRevealed).toBe(true)
    await toggle.click()
    const remaskedBody = await page.locator('body').innerText()
    const remaskedCredentialLeaked = remaskedBody.includes(runtimeCredential)
    expect(remaskedCredentialLeaked).toBe(false)
    page.once('dialog', (dialog) => dialog.accept())
    await row.locator('[data-delete]').click()
    await expect(row).toBeHidden()
  })
})
