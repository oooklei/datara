/**
 * 探针：F2 创建同步工作流后 .vue-flow hidden 根因定位
 * 量测 .vue-flow 及其父链每层的 rect/computed style，定位高度断点（只读诊断，不改代码）
 */
import { chromium } from 'playwright'

const BASE = process.env.E2E_BASE ?? 'http://192.168.1.9:18091'
const USER = process.env.E2E_USER ?? 'e2e-runner'
const PASS = process.env.E2E_PASS ?? ''
if (!PASS) { console.error('E2E_PASS 未注入'); process.exit(2) }

const browser = await chromium.launch()
try {
  const resp = await fetch(`${BASE}/api/v1/rebuild/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  })
  const j = await resp.json()
  const token = j?.data?.token ?? ''
  if (!token) { console.error('login 失败'); process.exit(2) }

  const ctx = await browser.newContext({ viewport: { width: 1680, height: 950 } })
  await ctx.route('**/api/**', (route) => {
    const h = { ...route.request().headers(), authorization: `Bearer ${token}` }
    return route.continue({ headers: h })
  })
  await ctx.addInitScript(([t]) => localStorage.setItem('datara_token', t), [token])
  const page = await ctx.newPage()

  await page.goto(`${BASE}/p/23/dag`)
  await page.waitForSelector('[data-testid="new-workflow"]', { timeout: 20000 })
  const wfName = `E2E-PROBE-${Date.now()}`
  await page.click('[data-testid="new-workflow"]')
  await page.waitForSelector('[data-testid="tc-new-wf-dialog"]', { timeout: 10000 })
  await page.fill('[data-testid="tc-new-wf-name"]', wfName)
  await page.click('[data-testid="tc-new-wf-cat-sync"]')
  await page.click('[data-testid="tc-new-wf-confirm"]')
  await page.getByText('已创建工作流', { exact: false }).first().waitFor({ timeout: 15000 })
  // 等 .vue-flow attach（不要求 visible）
  await page.waitForSelector('.vue-flow', { state: 'attached', timeout: 20000 })
  await page.waitForTimeout(1500)

  const diag = await page.evaluate(() => {
    const el = document.querySelector('.vue-flow')
    if (!el) return { error: '.vue-flow not found' }
    const chain = []
    let n = el
    while (n && chain.length < 16) {
      const cs = getComputedStyle(n)
      const r = n.getBoundingClientRect()
      chain.push({
        tag: n.tagName.toLowerCase(),
        cls: String(n.className).slice(0, 70),
        w: Math.round(r.width * 10) / 10,
        h: Math.round(r.height * 10) / 10,
        cssH: cs.height, display: cs.display, vis: cs.visibility,
        overflow: cs.overflow, pos: cs.position, flex: cs.flex,
      })
      n = n.parentElement
    }
    return chain
  })
  console.log('=== .vue-flow 父链量测（自下而上） ===')
  console.log(JSON.stringify(diag, null, 1))

  // 顺带量画布 Tab 条与 tcd-type 状态
  const tabInfo = await page.evaluate(() => {
    const dag = document.querySelector('[data-tc-dagbar]')
    const tcd = document.querySelector('.tcd-type')
    const canvas = document.querySelector('[data-tc-canvas]')
    const wb = document.querySelector('[data-tc-canvas-workbench]')
    return {
      dagbar: !!dag, dagRect: dag ? JSON.stringify(dag.getBoundingClientRect()) : null,
      tcd: tcd ? tcd.textContent.trim() : null,
      canvas: !!canvas, canvasRect: canvas ? JSON.stringify(canvas.getBoundingClientRect()) : null,
      workbench: !!wb, wbRect: wb ? JSON.stringify(wb.getBoundingClientRect()) : null,
    }
  })
  console.log('=== Tab/画布容器 ===')
  console.log(JSON.stringify(tabInfo, null, 1))

  await page.screenshot({ path: 'probe-flow.png', fullPage: true })
} catch (e) {
  console.error('PROBE ERR', String(e).slice(0, 400))
} finally {
  await browser.close()
}
