import { chromium } from 'playwright'

const baseURL = process.env.DATARA_BASE_URL || 'http://127.0.0.1:8090'
const user = process.env.DATARA_USER || 'admin'
const pwd = process.env.DATARA_PWD || 'Admin@123'

const navs = [
  { label: '血缘分析', path: '/meta/lineage' },
  { label: '组件目录', path: '/meta/components' },
  { label: '基线化工作台', path: '/meta/components/baseline' },
  { label: '运行时节点', path: '/dep/runtime' },
  { label: '集群监控', path: '/dep/monitor' },
]

const browser = await chromium.launch({ headless: true })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })

const consoleErrors = []
const pageErrors = []
const badResponses = []
const requestFailures = []
const workflowVariableCalls = []

page.on('console', (msg) => {
  if (msg.type() === 'error') consoleErrors.push(msg.text())
})
page.on('pageerror', (err) => pageErrors.push(err.message))
page.on('requestfailed', (req) => {
  requestFailures.push({ url: req.url(), failure: req.failure()?.errorText || '' })
})
page.on('response', (res) => {
  const url = res.url()
  const status = res.status()
  if (url.includes('/workflow-variables')) workflowVariableCalls.push({ url, status })
  if (status >= 400 && !url.includes('/favicon')) badResponses.push({ url, status })
})

async function loginIfNeeded() {
  await page.goto(baseURL, { waitUntil: 'networkidle' })
  const username = page.locator('input[type="text"], input:not([type])').first()
  const password = page.locator('input[type="password"]').first()
  if (await password.count()) {
    await username.fill(user)
    await password.fill(pwd)
    await page.locator('button').filter({ hasText: /登录|登.*录|Login/i }).first().click()
    await page.waitForLoadState('networkidle')
    await page.waitForTimeout(500)
  }
}

async function clickNavOrGoto(label, path) {
  const before = page.url()
  const item = page.getByText(label, { exact: true }).first()
  try {
    await item.click({ timeout: 3000 })
  } catch {
    await page.goto(baseURL + path, { waitUntil: 'networkidle' })
    return { label, clicked: false, before, after: page.url() }
  }
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(800)
  return { label, clicked: true, before, after: page.url() }
}

await loginIfNeeded()

const results = []
const textIssues = []
for (const nav of navs) {
  const result = await clickNavOrGoto(nav.label, nav.path)
  const body = await page.locator('body').innerText({ timeout: 5000 }).catch(() => '')
  const badText = ['变量加载失败', '工作流定义不存在', 'Cannot read', 'Unhandled', '白屏']
    .filter((needle) => body.includes(needle))
  if (badText.length) textIssues.push({ label: nav.label, badText })
  results.push({ ...result, badText })
}

await browser.close()

const fatal = [
  ...textIssues.map((x) => `text:${x.label}:${x.badText.join(',')}`),
  ...pageErrors.map((x) => `pageerror:${x}`),
  ...requestFailures.map((x) => `requestfailed:${x.url}:${x.failure}`),
  ...badResponses
    .filter((x) => !x.url.includes('/workflow-variables?wf=') || x.url.includes('/workflow-variables?wf=lineage_global'))
    .map((x) => `http:${x.status}:${x.url}`),
  ...workflowVariableCalls
    .filter((x) => x.url.includes('wf=lineage_global'))
    .map((x) => `unexpected-lineage-vars-call:${x.status}:${x.url}`),
]

const report = {
  ok: fatal.length === 0,
  baseURL,
  results,
  consoleErrors,
  pageErrors,
  badResponses,
  requestFailures,
  workflowVariableCalls,
  fatal,
}

console.log(JSON.stringify(report, null, 2))
if (!report.ok) process.exit(1)
