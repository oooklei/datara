const { chromium } = require('../../datara-newweb/node_modules/@playwright/test')

const base = process.env.DATARA_E2E_BASE || 'http://localhost:18121'

async function loginAs(page, name) {
  await page.goto(`${base}/login`)
  await page.locator('[data-demo-account]').filter({ hasText: name }).first().click()
  await page.locator('button[type="submit"]').click()
  await page.waitForURL(`${base}/`, { timeout: 15000 })
  await page.locator('.state-loading').waitFor({ state: 'hidden', timeout: 15000 })
}

async function main() {
  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    const pageErrors = []
    page.on('pageerror', (error) => pageErrors.push(error.name))
    const idePageStatus = (await page.request.get(`${base}/ide/`)).status()
    const ideI18nStatus = (await page.request.get(`${base}/ide/assets/i18n-DvdMpN9C.js`)).status()
    const anonymousIdeApiStatus = (await page.request.get(`${base}/ide/api/connection/list`)).status()

    await loginAs(page, 'dev')
    const developerMonitorEntry = await page.locator('[data-quick-entry="/dep/monitor"]').count()
    await page.goto(`${base}/dep/monitor`)
    await page.waitForURL(`${base}/`, { timeout: 15000 })
    const developerMonitorDenied = new URL(page.url()).pathname === '/'
    await page.locator('[data-shell-logout]').click()
    await page.waitForURL(`${base}/login`, { timeout: 15000 })

    await loginAs(page, 'admin')
    const adminProjectCount = await page.locator('[data-project-id]').count()
    const adminMonitorEntry = await page.locator('[data-quick-entry="/dep/monitor"]').count()
    await page.goto(`${base}/dep/monitor`)
    await page.locator('main[aria-label="监控中心"]').waitFor({ timeout: 15000 })
    const adminMonitorVisible = new URL(page.url()).pathname === '/dep/monitor'
    const persistedToken = await page.evaluate(() => Boolean(
      localStorage.getItem('datara_token') || sessionStorage.getItem('datara_token'),
    ))

    const evidence = {
      idePageStatus,
      ideI18nStatus,
      anonymousIdeApiStatus,
      developerMonitorEntry,
      developerMonitorDenied,
      adminProjectCount,
      adminMonitorEntry,
      adminMonitorVisible,
      persistedToken,
      pageErrors,
    }
    await page.locator('[data-shell-logout]').click()
    await page.waitForURL(`${base}/login`, { timeout: 15000 })
    console.log(JSON.stringify(evidence))
    if (idePageStatus !== 200 || ideI18nStatus !== 200 || anonymousIdeApiStatus !== 401
      || developerMonitorEntry !== 0 || !developerMonitorDenied || adminProjectCount < 1
      || adminMonitorEntry !== 1 || !adminMonitorVisible || persistedToken || pageErrors.length) {
      process.exitCode = 1
    }
  } finally {
    await browser.close()
  }
}

main().catch((error) => {
  console.error(error.message)
  process.exitCode = 1
})
