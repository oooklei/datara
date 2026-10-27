import playwright from '/lei/datara/datara-web/node_modules/playwright-core/index.js'
const { chromium } = playwright

const base = 'http://127.0.0.1:18091'
const accounts = [
  ['admin', 'Admin@123', 'admin', '管理员'],
  ['dev', 'Dev@123', 'developer', '开发者'],
  ['analyst', 'Analyst@123', 'operator', '分析师'],
  ['viewer', 'Viewer@123', 'viewer', '观察者'],
]
const browser = await chromium.launch({
  executablePath: '/root/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',
  headless: true,
  args: ['--no-sandbox'],
})
const result = { accounts: [], critical: {}, consoleErrors: [] }

for (const [username, password, expectedRole, expectedRoleLabel] of accounts) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  page.on('console', (message) => { if (message.type() === 'error') result.consoleErrors.push(`${username}:${message.text()}`) })
  await page.goto(`${base}/login`, { waitUntil: 'networkidle' })
  await page.locator('[data-login-username]').fill(username)
  await page.locator('[data-login-password]').fill(password)
  await Promise.all([
    page.waitForURL((url) => !url.pathname.endsWith('/login'), { timeout: 15_000 }),
    page.locator('button[type="submit"]').click(),
  ])
  const userChip = page.locator('[data-current-user]')
  await userChip.waitFor()
  const userText = await userChip.textContent()
  if (!userText?.includes(username) || !userText.includes(expectedRoleLabel)) throw new Error(`${username} session mismatch`)
  result.accounts.push({ username, role: expectedRole, login: 'ok' })

  if (username === 'admin') {
    await page.locator('[data-project-id="33"]').click()
    await page.waitForURL('**/p/33')
    await page.locator('[data-project-nav]').waitFor()
    await page.locator('[data-dashboard-chart]').first().waitFor()
    result.critical.dashboard = {
      navItems: await page.locator('[data-project-nav] a').count(),
      pipelineKpis: await page.locator('[data-pipeline-kpi]').count(),
      governanceKpis: await page.locator('[data-governance-kpi]').count(),
      charts: await page.locator('[data-dashboard-chart]').count(),
    }
    await page.screenshot({ path: '/lei/datara/evidence/F-UX-V3-P5-dashboard.png', fullPage: true })

    await page.locator('a[href="/p/33/dag"]').click()
    await page.waitForURL('**/p/33/dag')
    await page.locator('[data-tc-tabs]').waitFor()
    result.critical.dag = {
      tabs: await page.locator('[data-tc-tabs] button').count(),
      body: await page.locator('[data-tc-body]').count(),
    }

    await page.locator('a[href="/p/33/ide"]').click()
    await page.waitForURL('**/p/33/ide')
    await page.locator('[data-ds-select]').selectOption({ index: 1 })
    await page.locator('[data-codemirror-editor]').waitFor()
    result.critical.ide = {
      datasources: await page.locator('[data-ds-select] option').count() - 1,
      codeMirror: await page.locator('[data-codemirror-editor]').count(),
      workspace: await page.locator('[data-ide-workspace]').count(),
    }

    await page.locator('a[href="/sys"]').first().click()
    await page.waitForURL('**/sys')
    await page.locator('[data-user-management]').waitFor()
    result.critical.system = { users: await page.locator('[data-user-row]').count() }

    await page.locator('a[href="/open/llm"]').first().click()
    await page.waitForURL('**/open/llm')
    const row = page.locator('[data-test="llm-row"]').filter({ hasText: 'LongCat-2.0' }).first()
    await row.waitFor()
    await row.locator('[data-test="llm-test"]').click()
    const rowId = await row.getAttribute('data-llm-id')
    const testResult = page.locator(`[data-test="llm-test-result-${rowId}"]`)
    await testResult.waitFor({ timeout: 105_000 })
    const testText = await testResult.textContent()
    if (!testText?.includes('连通性测试通过')) throw new Error('LongCat connectivity failed')
    result.critical.longcat = { models: await page.locator('[data-test="llm-row"]').count(), probe: 'ok' }
  }
  if (username === 'viewer') {
    await page.locator('[data-global-system]').click()
    await page.waitForURL('**/sys')
    result.critical.viewerSystem = {
      adminNotice: await page.locator('[data-admin-required]').count(),
      userManagement: await page.locator('[data-user-management]').count(),
    }
    if (result.critical.viewerSystem.adminNotice !== 1 || result.critical.viewerSystem.userManagement !== 0) {
      throw new Error('viewer system visibility mismatch')
    }
  }
  await context.close()
}

await browser.close()
if (result.critical.dashboard?.navItems !== 19) throw new Error('project navigation count mismatch')
if (result.consoleErrors.length) throw new Error(`console errors: ${result.consoleErrors.join(' | ')}`)
console.log(JSON.stringify(result))
