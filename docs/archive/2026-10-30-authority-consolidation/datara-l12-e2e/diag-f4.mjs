/**
 * 诊断脚本（临时件，用后删）：F4 fatal 根因实证 + position 避让可行性验证
 * 非验收件，不产 PASS 证据；输出 DIAG JSON 至 stdout
 */
import { chromium } from 'playwright'
import { writeFileSync } from 'node:fs'

const BASE = process.env.E2E_BASE ?? 'http://192.168.1.9:18091'
const USER = process.env.E2E_USER ?? 'e2e-runner'
const PASS = process.env.E2E_PASS ?? ''
const PROJECT_ID = Number(process.env.E2E_PROJECT_ID ?? '23')

if (!PASS) {
  console.error('E2E_PASS 未注入')
  process.exit(2)
}

const browser = await chromium.launch()
const entries = []
const log = (k, v) => {
  const line = `${k} | ${typeof v === 'string' ? v.slice(0, 300) : JSON.stringify(v)}`
  entries.push(line)
  console.log(line)
}

try {
  const resp = await fetch(`${BASE}/api/v1/rebuild/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  })
  const j = await resp.json()
  const token = j?.data?.token ?? ''
  log('login', `ok=${resp.ok} token_len=${token.length}`)
  if (!token) throw new Error('login 失败')

  const ctx = await browser.newContext({ viewport: { width: 1680, height: 950 } })
  await ctx.route('**/api/**', (route) => {
    const h = { ...route.request().headers(), authorization: `Bearer ${token}` }
    return route.continue({ headers: h })
  })
  await ctx.addInitScript(([t]) => localStorage.setItem('datara_token', t), [token])
  const page = await ctx.newPage()
  const pageErrors = []
  page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)))

  await page.goto(`${BASE}/p/${PROJECT_ID}/dag`)
  await page.waitForSelector('[data-testid="new-workflow"]', { timeout: 20000 })
  const wfName = `DIAG-F4-${Date.now()}`
  await page.click('[data-testid="new-workflow"]')
  await page.waitForSelector('[data-testid="tc-new-wf-dialog"]', { timeout: 10000 })
  await page.fill('[data-testid="tc-new-wf-name"]', wfName)
  await page.click('[data-testid="tc-new-wf-cat-sync"]')
  await page.click('[data-testid="tc-new-wf-confirm"]')
  await page.waitForSelector('.vue-flow', { timeout: 20000 })
  await page.waitForTimeout(800)

  await page.click('[data-testid="wf-spec-endpoint_select"]')
  await page.waitForFunction((n) => document.querySelectorAll('.vue-flow__node').length > n, 0, { timeout: 10000 })
  await page.click('[data-testid="wf-spec-field_map"]')
  await page.waitForFunction((n) => document.querySelectorAll('.vue-flow__node').length > n + 1, 0, { timeout: 10000 })
  await page.waitForTimeout(500)

  /* 核心诊断：节点几何 + 中心点 elementFromPoint 命中链 */
  const diag = await page.evaluate(() => {
    const nodes = [...document.querySelectorAll('.vue-flow__node')]
    const pick = (el) => {
      const r = el.getBoundingClientRect()
      const cx = r.left + r.width / 2
      const cy = r.top + r.height / 2
      const top = document.elementFromPoint(cx, cy)
      const chain = []
      let cur = top
      for (let i = 0; cur && i < 4; i++) {
        chain.push(`${cur.tagName}.${String(cur.className).split(' ').slice(0, 2).join('.')}`)
        cur = cur.parentElement
      }
      return {
        id: el.dataset.id,
        rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
        center: [Math.round(cx), Math.round(cy)],
        centerHitIsSelfOrChild: !!(top && (top === el || el.contains(top))),
        hitChain: chain,
        pointerEvents: getComputedStyle(el).pointerEvents,
      }
    }
    const flow = document.querySelector('.vue-flow')
    const fr = flow.getBoundingClientRect()
    return { viewport: [innerWidth, innerHeight], flowRect: [Math.round(fr.x), Math.round(fr.y), Math.round(fr.width), Math.round(fr.height)], nodes: nodes.map(pick) }
  })
  log('DIAG', diag)

  /* 验证 A：默认中心点 click（预期失败，重现 fatal） */
  try {
    await page.click('.vue-flow__node >> nth=0', { timeout: 4000 })
    log('click.center', 'OK（未重现重叠遮挡）')
  } catch (e) {
    log('click.center', `FAIL: ${String(e).split('\n')[0]}`)
  }

  /* 验证 B：position 避让（节点内左上区，避开 n2 覆盖区 x<48px） */
  try {
    await page.click('.vue-flow__node >> nth=0', { position: { x: 20, y: 15 }, timeout: 5000 })
    await page.waitForSelector('[data-testid="node-config-panel"]', { timeout: 5000 })
    const structured = await page.locator('[data-field="srcDs"]').isVisible()
    log('click.offset', `OK node-config-panel 出现, srcDs 可见=${structured}`)
  } catch (e) {
    log('click.offset', `FAIL: ${String(e).split('\n')[0]}`)
  }

  log('pageErrors', pageErrors)
} catch (e) {
  log('fatal', String(e).slice(0, 300))
} finally {
  await browser.close()
}
writeFileSync('d:/diag_f4_result.json', entries.join('\n'))
console.log('DIAG_DONE')
