/** Capture the real DolphinScheduler save response for workflow `tt`. */
let playwright
try { playwright = require('../../datara-newweb/node_modules/@playwright/test') } catch { playwright = require('playwright-core') }
const { chromium, request } = playwright

const BASE = process.argv[2] || 'http://192.168.1.9:18091'
const PROJECT_ID = Number(process.argv[3] || 33)

async function main() {
  const token = process.env.DATARA_DS_VERIFY_TOKEN
  if (!token) throw new Error('DATARA_DS_VERIFY_TOKEN unavailable')
  const browser = await chromium.launch({ headless: true, executablePath: process.env.DATARA_CHROMIUM_PATH || undefined })
  const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
  page.setDefaultTimeout(20000)
  const responses = []
  const requestBodies = new Map()
  page.on('request', (request) => {
    const method = request.method()
    if (!['POST', 'PUT', 'PATCH'].includes(method) || !request.url().includes('workflow-definition')) return
    const raw = request.postData() || ''
    let summary = { type: 'text', length: raw.length }
    try {
      const parsed = JSON.parse(raw)
      summary = { type: 'json', keys: Object.keys(parsed).sort(), lengths: Object.fromEntries(Object.entries(parsed).map(([key, value]) => [key, typeof value === 'string' ? value.length : Array.isArray(value) ? value.length : typeof value])) }
    } catch {}
    requestBodies.set(request, summary)
  })
  page.on('response', async (response) => {
    const method = response.request().method()
    if (!['POST', 'PUT', 'PATCH'].includes(method) || !response.url().includes('workflow-definition')) return
    let body = ''
    try { body = (await response.text()).slice(0, 1200) } catch { body = '<body unavailable>' }
    responses.push({ method, url: response.url(), status: response.status(), request: requestBodies.get(response.request()) || null, body })
  })
  try {
    await page.addInitScript((shortLivedToken) => { window.__DATARA_TEST_TOKEN__ = shortLivedToken }, token)
    await page.goto(`${BASE}/p/${PROJECT_ID}/dag`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-tc-wf-list]').waitFor()
    const rows = page.locator('[data-wf-row]')
    const rowTexts = await rows.allInnerTexts()
    const row = rows.filter({ hasText: /tt/i }).first()
    if (await row.count() === 0) throw new Error(`workflow tt not found; rows=${JSON.stringify(rowTexts)}`)
    await row.locator('[data-wf-open]').click()
    await page.locator('[data-tc-ds-frame]').waitFor()
    const frame = await (await page.locator('[data-tc-ds-frame]').elementHandle()).contentFrame()
    if (!frame) throw new Error('ds iframe has no content frame')
    await frame.locator('.dag-container').waitFor({ timeout: 45000 })
    const save = frame.locator('.btn-save')
    await save.click()
    const modal = frame.locator('.n-modal').last()
    await modal.locator('.input-name input').waitFor()
    const name = await modal.locator('.input-name input').inputValue()
    await modal.locator('.btn-submit').click()
    await frame.waitForTimeout(3500)
    const last = responses.at(-1) || null
    console.log(JSON.stringify({ workflow: 'tt', name, response: last, responses }))
    if (!last) process.exitCode = 2
  } finally {
    await browser.close()
  }
}

main().catch((error) => { console.error(error.stack || error); process.exitCode = 1 })
