const { chromium } = require('/lei/datara/datara-web/node_modules/playwright-core')

const base = process.env.DATARA_BASE || 'http://127.0.0.1:18091'
const evidenceDir = process.env.EVIDENCE_DIR || '/lei/datara/deployments/F-UX-V4-P1-20261028'
const failures = []

function observe(page, scope) {
  page.on('console', (message) => {
    if (message.type() === 'error') failures.push(`${scope}:console:${message.text()}`)
  })
  page.on('pageerror', (error) => failures.push(`${scope}:page:${error.message}`))
  page.on('response', (response) => {
    if (response.status() >= 400 && !response.url().includes('/favicon')) {
      failures.push(`${scope}:http:${response.status()}:${response.url()}`)
    }
  })
}

async function login(page) {
  await page.goto(`${base}/login`, { waitUntil: 'networkidle', timeout: 30_000 })
  await page.locator('[data-login-username]').fill('admin')
  await page.locator('[data-login-password]').fill('Admin@123')
  await page.locator('button[type=submit]').click()
  await page.waitForURL(`${base}/`, { timeout: 15_000 })
}

async function enterOnlyProject(page) {
  const projects = page.locator('[data-project-id]')
  await projects.first().waitFor({ state: 'visible', timeout: 20_000 })
  const count = await projects.count()
  const names = await projects.allTextContents()
  if (count !== 1) throw new Error(`expected one project, got ${count}: ${names.join('|')}`)
  if (!names[0].includes('电商数据全域治理项目')) throw new Error(`unexpected project: ${names[0]}`)
  await projects.first().click()
  await page.waitForURL(/\/p\/33$/, { timeout: 15_000 })
  return { count, names }
}

async function main() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || '/root/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome',
    args: ['--no-sandbox'],
  })
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, acceptDownloads: true })
    observe(page, 'desktop')
    await login(page)
    const project = await enterOnlyProject(page)
    await page.waitForSelector('[data-project-switcher]', { timeout: 15_000 })

    const result = {
      project,
      desktop: {
        path: new URL(page.url()).pathname,
        globalProjectEntry: await page.locator('[data-project-exit]').count(),
        localProjectSelectors: await page.locator('[data-project-select]').count(),
      },
    }

    await page.goto(`${base}/p/33/ds/list`, { waitUntil: 'networkidle', timeout: 30_000 })
    await page.waitForSelector('[data-filter-keyword]', { timeout: 15_000 })
    const datasourceRows = page.locator('[data-ds-id]')
    result.datasource = {
      filters: await page.locator('[data-filter-keyword], [data-filter-kind], [data-filter-status]').count(),
      rows: await datasourceRows.count(),
      localProjectSelectors: await page.locator('[data-project-select]').count(),
      detailOpened: false,
    }
    if (result.datasource.rows > 0) {
      await page.locator('[data-detail-action]').first().click()
      await page.locator('[data-detail]').waitFor({ state: 'visible' })
      result.datasource.detailOpened = true
    }

    await page.goto(`${base}/p/33/ide`, { waitUntil: 'networkidle', timeout: 30_000 })
    await page.waitForSelector('[data-ds-select]', { timeout: 15_000 })
    const options = await page.locator('[data-ds-select] option').evaluateAll((items) => items.map((item) => ({ value: item.value, text: item.textContent || '' })))
    const firstDatasource = options.find((item) => item.value)
    result.ide = {
      datasources: options.length - 1,
      executeVisible: await page.locator('[data-execute]').isVisible(),
      cancelVisible: await page.locator('[data-cancel]').isVisible(),
      exportCount: 0,
      exportVisible: false,
      localProjectSelectors: await page.locator('[data-project-select]').count(),
      executed: false,
      resultGrid: false,
    }
    if (firstDatasource) {
      await page.locator('[data-ds-select]').selectOption(firstDatasource.value)
      await page.waitForSelector('[data-codemirror-editor] .cm-content', { timeout: 15_000 })
      await page.locator('[data-codemirror-editor] .cm-content').fill('SELECT 1 AS value')
      await page.locator('[data-execute]').click()
      await page.waitForSelector('[data-result-grid], [data-error], [data-contract-error]', { timeout: 30_000 })
      result.ide.executed = true
      result.ide.resultGrid = await page.locator('[data-result-grid]').isVisible().catch(() => false)
      result.ide.exportCount = await page.locator('[data-export]').count()
      result.ide.exportVisible = await page.locator('[data-export]:visible').count() > 0
      result.ide.exportEnabled = await page.locator('[data-export]').isEnabled()
    }
    await page.screenshot({ path: `${evidenceDir}/p1-desktop.png`, fullPage: true })

    await page.goto(`${base}/p/33/dag`, { waitUntil: 'networkidle', timeout: 30_000 })
    result.dag = {
      path: new URL(page.url()).pathname,
      localProjectSelectors: await page.locator('[data-project-select]').count(),
      horizontalOverflow: await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth),
    }

    const mobile = await browser.newPage({ viewport: { width: 375, height: 812 } })
    observe(mobile, 'mobile')
    await login(mobile)
    await enterOnlyProject(mobile)
    const logout = mobile.locator('[data-shell-logout]')
    await logout.waitFor({ state: 'visible', timeout: 15_000 })
    await mobile.locator('[data-sidebar-toggle]').click()
    await mobile.waitForTimeout(250)
    result.mobile = {
      logoutVisible: await logout.isVisible(),
      logoutBox: await logout.boundingBox(),
      drawerExpanded: await mobile.locator('[data-sidebar-toggle]').getAttribute('aria-expanded'),
      navVisible: await mobile.locator('[data-project-nav]').isVisible(),
      localProjectSelectors: await mobile.locator('[data-project-select]').count(),
      horizontalOverflow: await mobile.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth),
    }
    await mobile.screenshot({ path: `${evidenceDir}/p1-mobile.png`, fullPage: true })

    result.failures = [...new Set(failures)]
    result.ok = result.project.count === 1
      && result.desktop.globalProjectEntry === 1
      && result.desktop.localProjectSelectors === 0
      && result.datasource.filters === 3
      && result.datasource.localProjectSelectors === 0
      && result.ide.executeVisible && result.ide.cancelVisible && result.ide.exportVisible
      && result.ide.localProjectSelectors === 0
      && (!firstDatasource || (result.ide.executed && result.ide.resultGrid && result.ide.exportEnabled))
      && result.dag.localProjectSelectors === 0
      && result.mobile.logoutVisible && result.mobile.logoutBox
      && result.mobile.logoutBox.x >= 0
      && result.mobile.logoutBox.x + result.mobile.logoutBox.width <= 375
      && result.mobile.drawerExpanded === 'true'
      && result.mobile.localProjectSelectors === 0
      && result.mobile.horizontalOverflow <= 1
      && result.failures.length === 0
    console.log(JSON.stringify(result))
    if (!result.ok) process.exitCode = 1
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error.stack || error.message)
  process.exit(1)
})
