const { chromium } = require('playwright-core')

const BASE = process.env.BASE_URL || 'http://127.0.0.1:8090'
const executablePath = process.env.CHROMIUM_PATH || '/usr/bin/chromium-browser'

function assert(ok, message) {
  if (!ok) throw new Error(message)
  console.log(`[PASS] ${message}`)
}

(async () => {
  const browser = await chromium.launch({ executablePath, headless: true, args: ['--no-sandbox'] })
  const page = await browser.newPage({ viewport: { width: 1680, height: 960 } })
  const pageErrors = []
  const badResponses = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  page.on('response', (response) => {
    if (response.url().includes('/api/') && response.status() >= 500) {
      badResponses.push(`${response.status()} ${response.url()}`)
    }
  })

  let createdTemplateId = null
  try {
    await page.goto(`${BASE}/#/login`, { waitUntil: 'networkidle' })
    await page.fill('input.lg-input', 'admin')
    await page.fill('input[placeholder="请输入密码"]', 'Admin@123')
    await page.click('button.lg-submit')
    await page.waitForFunction(() => Boolean(localStorage.getItem('datara_token')))

    const definitions = await page.evaluate(async () => {
      const token = localStorage.getItem('datara_token') || ''
      const response = await fetch('/api/v1/workflow-definitions?page_no=1&page_size=100', { headers: { token } })
      return response.json()
    })
    const first = definitions?.data?.items?.[0] || definitions?.data?.[0]
    assert(Boolean(first?.id), '远端存在可用于编排回归的工作流定义')

    await page.goto(`${BASE}/#/dag?tab=edit&doc=${encodeURIComponent(first.id)}`, { waitUntil: 'networkidle' })
    await page.waitForSelector('[data-testid="new-workflow"]', { timeout: 20000 })
    assert(await page.isVisible('[data-testid="new-workflow"]'), '有活动画布时仍显示“新建工作流”')

    await page.click('[data-testid="new-workflow"]')
    await page.waitForSelector('.el-dialog', { state: 'visible' })
    assert((await page.locator('.el-dialog').innerText()).includes('新建工作流'), '“新建工作流”按钮打开统一创建对话框')
    await page.click('.el-dialog__headerbtn')

    const bodyText = await page.locator('body').innerText()
    assert(!bodyText.includes('ETL 设计器') && !bodyText.includes('流设计器'), '任务中心不再暴露独立 ETL/流设计器')

    const templateName = `UI回归模板-${Date.now()}`
    const responsePromise = page.waitForResponse((response) =>
      response.url().includes('/api/v1/workflow-templates') && response.request().method() === 'POST')
    await page.getByRole('button', { name: '另存为模板' }).click()
    await page.waitForSelector('.el-message-box input', { state: 'visible' })
    await page.fill('.el-message-box input', templateName)
    await page.click('.el-message-box__btns .el-button--primary')
    const templateResponse = await responsePromise
    const templatePayload = await templateResponse.json()
    createdTemplateId = templatePayload?.data?.id ?? null
    assert(templateResponse.ok() && templatePayload?.code === 0, '响应式画布可成功“另存为模板”')
    await page.waitForFunction(() => document.body.innerText.includes('已另存为模板'))

    assert(!pageErrors.some((message) => message.includes('structuredClone') || message.includes('DataCloneError')), '页面无 structuredClone/DataCloneError')
    assert(pageErrors.length === 0, `页面脚本异常为 0（实际 ${pageErrors.length}）`)
    assert(badResponses.length === 0, `API 5xx 为 0（实际 ${badResponses.length}）`)
  } finally {
    if (createdTemplateId != null) {
      await page.evaluate(async (id) => {
        const token = localStorage.getItem('datara_token') || ''
        await fetch(`/api/v1/workflow-templates/${id}`, { method: 'DELETE', headers: { token } })
      }, createdTemplateId).catch(() => {})
    }
    await browser.close()
  }
})().catch((error) => {
  console.error('[FAIL]', error)
  process.exit(1)
})
