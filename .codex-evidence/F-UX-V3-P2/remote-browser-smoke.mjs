import { chromium } from 'playwright-core'

const base = process.env.DATARA_BASE || 'http://127.0.0.1:18103'
const errors = []
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] })
const page = await browser.newPage({ viewport: { width: 1440, height: 960 } })
page.on('console', message => { if (message.type() === 'error') errors.push(message.text()) })
page.on('pageerror', error => errors.push(error.message))

await page.goto(`${base}/login`, { waitUntil: 'networkidle', timeout: 30_000 })
await page.locator('[data-login-username]').fill('admin')
await page.locator('[data-login-password]').fill('Admin@123')
await page.locator('button[type=submit]').click()
await page.waitForURL(`${base}/`, { timeout: 15_000 })
await page.locator('[data-project-id="33"]').click()
await page.waitForURL(/\/p\/33$/, { timeout: 15_000 })
await page.waitForSelector('[data-pipeline-kpi]', { timeout: 20_000 })
await page.waitForTimeout(800)

const result = {
  path: new URL(page.url()).pathname,
  groups: await page.locator('[data-project-group]').count(),
  navItems: await page.locator('[data-project-nav] .project-nav-link').count(),
  pipelineKpis: await page.locator('[data-pipeline-kpi]').count(),
  governanceKpis: await page.locator('[data-governance-kpi]').count(),
  charts: await page.locator('[data-dashboard-chart] canvas').count(),
  recentRuns: await page.locator('[data-recent-run]').count(),
  partialWarning: await page.locator('[data-partial-warning]').count(),
  errors,
}
await page.screenshot({ path: '/lei/datara/evidence/F-UX-V3-P2-dashboard.png', fullPage: true })

const mobile = await browser.newPage({ viewport: { width: 375, height: 812 } })
await mobile.goto(`${base}/login`, { waitUntil: 'networkidle' })
await mobile.locator('[data-login-username]').fill('admin')
await mobile.locator('[data-login-password]').fill('Admin@123')
await mobile.locator('button[type=submit]').click()
await mobile.waitForURL(`${base}/`)
await mobile.locator('[data-project-id="33"]').click()
await mobile.waitForURL(/\/p\/33$/)
await mobile.locator('[data-sidebar-toggle]').click()
await mobile.waitForTimeout(350)
result.mobile = {
  drawerExpanded: await mobile.locator('[data-sidebar-toggle]').getAttribute('aria-expanded'),
  navVisible: await mobile.locator('[data-project-nav]').isVisible(),
  sidebarBox: await mobile.locator('.app-sidebar').boundingBox(),
  sidebarTransform: await mobile.locator('.app-sidebar').evaluate(element => getComputedStyle(element).transform),
  overflowX: await mobile.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth),
}
await mobile.screenshot({ path: '/lei/datara/evidence/F-UX-V3-P2-mobile.png', fullPage: true })
console.log(JSON.stringify(result))
await browser.close()
