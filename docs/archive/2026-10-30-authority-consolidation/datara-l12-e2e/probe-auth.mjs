/** 401 探针：header 词形 × 注入方式 定位 */
import { chromium } from 'playwright'

const BASE = 'http://192.168.1.9:18091'

const login = await fetch(`${BASE}/api/v1/rebuild/login`, {
  method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ username: 'e2e-runner', password: process.env.E2E_PASS }),
}).then((r) => r.json())
const token = login?.data?.token ?? ''
console.log('login token_len=', token.length)

for (const [label, headers] of [
  ['header token', { token }],
  ['Bearer', { Authorization: `Bearer ${token}` }],
]) {
  const r = await fetch(`${BASE}/api/v1/rebuild/projects`, { headers })
  console.log(`projects via ${label}:`, r.status, (await r.text()).slice(0, 120))
}

/* 页内注入复测：addInitScript 在每轮导航 document-start 注入 */
const browser = await chromium.launch()
const ctx = await browser.newContext()
await ctx.addInitScript(([t]) => localStorage.setItem('datara_token', t), [token])
const page = await ctx.newPage()
page.on('request', (r) => {
  if (r.url().includes('/api/')) console.log('REQ', r.method(), r.url().slice(BASE.length), 'token_hdr=', r.headers()['token'] ? `len${r.headers()['token'].length}` : 'NONE')
})
page.on('response', (r) => {
  if (r.status() >= 400) console.log('RESP', r.status(), r.url().slice(BASE.length))
})
await page.goto(`${BASE}/p/23/dag`, { waitUntil: 'domcontentloaded' })
await page.waitForTimeout(9000)
console.log('final_url=', page.url())
console.log('has data-tc-tabs=', await page.locator('[data-tc-tabs]').count())
console.log('body_head=', (await page.locator('body').innerText()).slice(0, 200).replace(/\n/g, ' | '))
await browser.close()
