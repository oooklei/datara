/** 诊断：draft.save 段——保存按钮点击后 toast/网络/状态全录 */
import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const BASE = process.env.E2E_BASE ?? 'http://192.168.1.9:18091'
const USER = process.env.E2E_USER ?? 'e2e-runner'
const PASS = process.env.E2E_PASS ?? ''
const PROJECT_ID = Number(process.env.E2E_PROJECT_ID ?? '23')
const EV = path.resolve('evidence')
mkdirSync(EV, { recursive: true })

const entries = []
const log = (s) => { entries.push(s); console.log(s) }
const apiCalls = []
const pageErrors = []

if (!PASS) { console.error('E2E_PASS 未注入'); process.exit(2) }

const browser = await chromium.launch()
try {
  const resp = await fetch(`${BASE}/api/v1/rebuild/login`, {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  })
  const j = await resp.json()
  const token = j?.data?.token ?? ''
  log(`LOGIN code=${j?.code} token_len=${token.length}`)
  if (!token) throw new Error('login 失败')

  const ctx = await browser.newContext({ viewport: { width: 1680, height: 950 } })
  await ctx.route('**/api/**', (route) => {
    const h = { ...route.request().headers(), authorization: `Bearer ${token}` }
    return route.continue({ headers: h })
  })
  await ctx.addInitScript(([t]) => localStorage.setItem('datara_token', t), [token])
  const page = await ctx.newPage()
  page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)))
  page.on('response', (r) => {
    const u = r.url()
    if (u.includes('/api/')) apiCalls.push(`${r.request().method()} ${u.slice(BASE.length)} -> ${r.status()}`)
  })

  /* 前段复刻：新建同步工作流 + 加 2 节点 + F4 配置 */
  await page.goto(`${BASE}/p/${PROJECT_ID}/dag`)
  await page.waitForSelector('[data-testid="new-workflow"]', { timeout: 20000 })
  const wfName = `E2E-DIAG-SAVE-${Date.now()}`
  await page.click('[data-testid="new-workflow"]')
  await page.waitForSelector('[data-testid="tc-new-wf-dialog"]', { timeout: 10000 })
  await page.fill('[data-testid="tc-new-wf-name"]', wfName)
  await page.click('[data-testid="tc-new-wf-cat-sync"]')
  await page.click('[data-testid="tc-new-wf-confirm"]')
  await page.getByText('已创建工作流', { exact: false }).first().waitFor({ timeout: 15000 })
  await page.waitForSelector('.vue-flow', { timeout: 20000 })
  await page.waitForTimeout(800)
  const before = await page.locator('.vue-flow__node').count()
  await page.click('[data-testid="wf-spec-endpoint_select"]')
  await page.waitForFunction((n) => document.querySelectorAll('.vue-flow__node').length > n, before, { timeout: 10000 })
  await page.click('[data-testid="wf-spec-field_map"]')
  await page.waitForFunction((n) => document.querySelectorAll('.vue-flow__node').length > n + 1, before, { timeout: 10000 })
  await page.click('.vue-flow__node >> nth=1')
  await page.waitForSelector('[data-testid="ncp-json"]', { timeout: 10000 })
  await page.fill('[data-testid="ncp-json"]', JSON.stringify({ mapping: 'e2e-smoke' }))
  await page.click('[data-testid="ncp-save"]')
  await page.getByText('节点配置已保存', { exact: false }).first().waitFor({ timeout: 10000 })
  log('PRE_SAVE_OK（前段复刻完成，apiCalls=' + apiCalls.length + '）')

  /* 保存点诊断 */
  const saveBtns = page.locator('.wf-btn', { hasText: '保存' })
  const btnCount = await saveBtns.count()
  const btnTexts = []
  for (let i = 0; i < btnCount; i++) btnTexts.push((await saveBtns.nth(i).innerText()).trim())
  log(`SAVE_BTNS count=${btnCount} texts=${JSON.stringify(btnTexts)}`)

  apiCalls.length = 0
  await saveBtns.first().click()
  log('SAVE_CLICKED')

  for (let i = 0; i < 12; i++) {
    await page.waitForTimeout(1000)
    const toasts = await page.evaluate(() =>
      Array.from(document.querySelectorAll('[class*="toast" i],[class*="message" i],[class*="notif" i],[role="alert"],[class*="msg" i]'))
        .map((e) => e.textContent?.trim()).filter((t) => t && t.length < 80)
    )
    const saveToasts = await page.evaluate(() =>
      Array.from(document.querySelectorAll('*'))
        .filter((e) => e.children.length === 0 && /保存/.test(e.textContent || ''))
        .map((e) => e.textContent?.trim())
    )
    if (i === 2 || i === 5 || i === 11) log(`T+${i + 1}s toasts=${JSON.stringify(toasts.slice(0, 5))} saveTexts=${JSON.stringify([...new Set(saveToasts)].slice(0, 8))}`)
    if (saveToasts.some((t) => /保存成功/.test(t))) { log(`SAVE_SUCCESS_TOAST at T+${i + 1}s`); break }
  }

  await page.screenshot({ path: path.join(EV, 'diag_save_after.png'), fullPage: true })
  log('API_CALLS_AFTER_SAVE=' + JSON.stringify(apiCalls, null, 1))
  log('PAGE_ERRORS=' + JSON.stringify(pageErrors))
  writeFileSync('d:/diag_save_result.json', entries.join('\n'), 'utf-8')
  console.log('DIAG_DONE')
} catch (e) {
  log('FATAL ' + String(e).slice(0, 400))
  writeFileSync('d:/diag_save_result.json', entries.join('\n'), 'utf-8')
  console.log('DIAG_DONE_FAIL')
} finally {
  await browser.close()
}
