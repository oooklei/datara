// The legacy web package deliberately carries playwright-core (the browser
// binary is supplied by the 1.9 validation host), so do not require the full
// Playwright bundle here.
const { chromium } = require('playwright-core')

(async () => {

const base = process.env.BASE_URL || 'http://192.168.1.9:18091'
const token = process.env.DATARA_TEST_TOKEN || ''
const failedRequests = []
const browser = await chromium.launch({
  headless: true,
  ...(process.env.CHROMIUM_EXECUTABLE_PATH
    ? { executablePath: process.env.CHROMIUM_EXECUTABLE_PATH }
    : {}),
})
try {
  const page = await browser.newPage()
  page.on('requestfailed', (request) => failedRequests.push(request.url()))
  await page.addInitScript(({ value }) => { window.__DATARA_TEST_TOKEN__ = value }, { value: token })
  const statuses = {}
  for (const validationPath of ['/rebuild-validation-i1.html', '/rebuild-validation-i2.html']) {
    await page.goto(`${base}${validationPath}`, { waitUntil: 'networkidle' })
    const status = await page.locator('[data-status]').textContent()
    statuses[validationPath] = status
    if (!status || !status.includes('HTTP 200')) {
      throw new Error(`${validationPath} failed: ${status || 'missing status'}`)
    }
  }
  console.log(JSON.stringify({ statuses, failed_requests: failedRequests }))
} finally {
  await browser.close()
}
})()
