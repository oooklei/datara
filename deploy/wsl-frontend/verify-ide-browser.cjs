const { chromium, request } = require('../../datara-newweb/node_modules/@playwright/test')

async function main() {
  const token = process.env.DATARA_IDE_VERIFY_TOKEN
  if (!token) throw new Error('short-lived token unavailable')
  const base = process.env.DATARA_IDE_VERIFY_BASE || 'http://192.168.1.9:8090'
  const api = await request.newContext({ baseURL: base, extraHTTPHeaders: { token } })
  const projectsResponse = await api.get('/api/v1/rebuild/projects')
  if (!projectsResponse.ok()) throw new Error(`project list ${projectsResponse.status()}`)
  const body = await projectsResponse.json()
  const projects = body.data?.list ?? body.data?.items ?? body.data ?? []
  const projectId = Array.isArray(projects) ? projects[0]?.id : undefined
  if (!Number.isInteger(projectId)) throw new Error('no project available to verify IDE')

  const browser = await chromium.launch({ headless: true })
  try {
    const page = await browser.newPage()
    const pageErrors = []
    const dbxApiPaths = new Set()
    const dbxApiStatuses = []
    page.on('pageerror', (error) => pageErrors.push(error.name))
    page.on('request', (request) => {
      const path = new URL(request.url()).pathname
      if (path.startsWith('/ide/api/')) dbxApiPaths.add(`${request.method()} ${path}`)
    })
    page.on('response', (response) => {
      const path = new URL(response.url()).pathname
      if (path.startsWith('/ide/api/')) dbxApiStatuses.push(`${response.status()} ${path}`)
    })
    await page.addInitScript((shortLivedToken) => {
      if (window.top === window) window.__DATARA_TEST_TOKEN__ = shortLivedToken
    }, token)
    const connectionListReady = page.waitForResponse(
      (response) => new URL(response.url()).pathname === '/ide/api/connection/list' && response.status() === 200,
      { timeout: 30000 },
    )
    await page.goto(`${base}/p/${projectId}/ide`)
    await page.locator('[data-dbx-frame]').waitFor({ timeout: 15000 })
    const frame = page.frameLocator('[data-dbx-frame]')
    await frame.locator('body').waitFor({ timeout: 15000 })
    await frame.locator('body').filter({ hasNotText: 'Loading…' }).waitFor({ timeout: 15000 })
    await frame.getByRole('button', { name: '新建连接' }).first().waitFor({ timeout: 20000 })
    await connectionListReady
    const ideWorkbenchReady = dbxApiStatuses.includes('200 /ide/api/connection/list')
    const state = await page.evaluate(() => ({
      pathname: location.pathname,
      projectVisible: !!document.querySelector('[data-dbx-project]'),
      variablePanel: !!document.querySelector('[data-variable-panel]'),
      persistedToken: !!localStorage.getItem('datara_token') || !!sessionStorage.getItem('datara_token'),
    }))
    await page.goto(`${base}/dep/monitor`)
    await page.locator('main[aria-label="监控中心"]').waitFor({ timeout: 15000 })
    const adminMonitorVisible = new URL(page.url()).pathname === '/dep/monitor'

    const developerPage = await browser.newPage()
    await developerPage.addInitScript((shortLivedToken) => {
      if (window.top === window) window.__DATARA_TEST_TOKEN__ = shortLivedToken
    }, token)
    await developerPage.route('**/api/v1/rebuild/session', (route) => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({ code: 0, data: { id: 7, username: 'zhangsan', role: 'developer' } }),
    }))
    await developerPage.goto(`${base}/dep/monitor`)
    await developerPage.waitForURL(`${base}/`)
    const developerMonitorDenied = new URL(developerPage.url()).pathname === '/'
    await developerPage.close()

    console.log(JSON.stringify({ ...state, ideWorkbenchReady, adminMonitorVisible, developerMonitorDenied, dbxApiPaths: [...dbxApiPaths].sort(), dbxApiStatuses, pageErrors }))
    if (!state.projectVisible || !state.variablePanel || !ideWorkbenchReady || !adminMonitorVisible || !developerMonitorDenied || state.persistedToken || pageErrors.length) {
      process.exitCode = 1
    }
  } finally {
    await browser.close()
    await api.dispose()
  }
}

main().catch((error) => {
  console.error(error.message)
  process.exitCode = 1
})
