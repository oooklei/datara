import fs from 'node:fs/promises'
import { chromium } from 'playwright-core'

const base = 'http://127.0.0.1:18091'
const key = (await fs.readFile('/lei/datara/runtime-secrets/rebuild-validation.key', 'utf8')).trim()
const tokenResponse = await fetch(`${base}/api/v1/rebuild/validation-token`, {
  method: 'POST',
  headers: {
    'content-type': 'application/json',
    'x-backend-validation-key': key,
    'x-backend-validation-scope': 'high-priority-e2e',
  },
  body: '{}',
})
const token = (await tokenResponse.json()).data.token
const expected = ['电商订单离线加工样例', '电商订单同步入仓样例', '电商实时订单流观摩样例']
const consoleErrors = []
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] })
const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
page.on('console', message => { if (message.type() === 'error') consoleErrors.push(message.text()) })
page.on('pageerror', error => consoleErrors.push(error.message))
await page.addInitScript(value => { globalThis.__DATARA_TEST_TOKEN__ = value }, token)

let result
try {
  await page.goto(`${base}/#/`, { waitUntil: 'networkidle', timeout: 30_000 })
  await page.locator('[data-project-id="33"]').click({ timeout: 15_000 })
  await page.locator('[data-nav="dag"]').click({ timeout: 15_000 })
  await page.locator('.wb-palette:visible .pal-tab').nth(1).click({ timeout: 15_000 })
  for (const name of expected) {
    await page.locator(`.wb-palette:visible .pt-name[title="${name}"]`).first().waitFor({ state: 'attached', timeout: 15_000 })
  }
  const folded = page.locator('.wb-palette:visible .pal-cat.fold > .pal-cat-head')
  while (await folded.count()) await folded.first().click()
  const visible = []
  for (const name of expected) {
    if (await page.locator(`.wb-palette:visible .pt-name[title="${name}"]:visible`).count()) visible.push(name)
  }
  await page.screenshot({ path: '/lei/datara/evidence/HANDOFF-DATARA-20261027/workflows.png', fullPage: true })
  result = { url: page.url(), visibleWorkflows: visible, consoleErrors, verdict: visible.length === expected.length && !consoleErrors.length ? 'PASS' : 'FAIL' }
} catch (error) {
  result = { url: page.url(), error: String(error), consoleErrors, verdict: 'FAIL' }
} finally {
  await browser.close()
}
await fs.writeFile('/lei/datara/evidence/HANDOFF-DATARA-20261027/browser-smoke.json', JSON.stringify(result, null, 2))
console.log(`BROWSER_VERDICT=${result.verdict} visible=${result.visibleWorkflows?.length ?? 0} consoleErrors=${consoleErrors.length}`)
if (result.verdict !== 'PASS') process.exitCode = 1
