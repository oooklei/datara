/**
 * §10.7 海豚集成验收（D1/D4/A1/A3/A4 + 宿主握手）浏览器验证。
 *
 * 前提：192.168.1.9 隔离栈已起（8090 前端 + /dolphinscheduler 同源反代 + 任务运行底座通道）。
 * token 由调用方经环境变量 DATARA_DS_VERIFY_TOKEN 注入（短时验证 token，仅内存，不落盘）。
 *
 * 用法：
 *   node deploy/wsl-frontend/verify-ds-embed-browser.cjs [baseUrl] [projectId]
 * 证据：stdout 输出单行 JSON；任一断言不成立则 exitCode=1。
 */
// 本机（Windows）用仓库内 @playwright/test；1.9 隔离目录用 playwright-core（NODE_PATH 指向已装依赖）。
let playwright
try {
  playwright = require('../../datara-newweb/node_modules/@playwright/test')
} catch {
  playwright = require('playwright-core')
}
const { chromium, request } = playwright

const BASE = process.argv[2] || 'http://192.168.1.9:8090'
const PROJECT_ID = Number(process.argv[3] || 33)

async function main() {
  const token = process.env.DATARA_DS_VERIFY_TOKEN
  if (!token) throw new Error('DATARA_DS_VERIFY_TOKEN unavailable')

  const api = await request.newContext({ baseURL: BASE, extraHTTPHeaders: { token } })
  const sessionResponse = await api.get(`/api/v1/rebuild/orchestration/session?project_id=${PROJECT_ID}`)
  if (!sessionResponse.ok()) throw new Error(`orchestration session ${sessionResponse.status()}`)
  const sessionBody = await sessionResponse.json()
  const session = sessionBody.data ?? {}
  if (!session.projectCode) throw new Error('orchestration session missing projectCode')

  // 1.9 上 playwright-core 与本地缓存 chromium 版本号不一致时，用 DATARA_CHROMIUM_PATH 指定二进制。
  const browser = await chromium.launch({ headless: true, executablePath: process.env.DATARA_CHROMIUM_PATH || undefined })
  const result = {
    base: BASE,
    projectId: PROJECT_ID,
    projectCode: session.projectCode,
    sessionUser: session.user,
    frameUrl: null,
    dsUiMounted: false,
    dsNavHidden: null,
    dsHeaderHidden: null,
    dsLoginFormVisible: null,
    dsUnauthorized: [],
    hostPersistedToken: null,
    canvasToolbar: [],
    pageErrors: [],
    wfRowCount: null,
    wfFirstRowText: null,
    frameRouteIsCanvasRoute: null,
  }

  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
    await page.addInitScript((shortLivedToken) => {
      // token 仅注入顶层（datara 前端 http.ts 在顶层读取）；message 监听在所有 frame 注册，
      // 才能同时捕获宿主→DS（落在 frame 窗口）与 DS→宿主（落在顶层窗口）两个方向。
      if (window.top === window) {
        window.__DATARA_TEST_TOKEN__ = shortLivedToken
      }
      window.__dsMsgLog = []
      window.addEventListener('message', (event) => {
        const data = event.data && typeof event.data === 'object' ? event.data : {}
        const payload = data.payload && typeof data.payload === 'object' ? data.payload : null
        window.__dsMsgLog.push({
          type: data.type || null,
          origin: event.origin,
          // 只留字段名，不留值（token 禁入产物）
          fields: payload ? Object.keys(payload) : [],
        })
      })
    }, token)

    page.on('pageerror', (error) => result.pageErrors.push(error.name))
    page.on('response', (response) => {
      const url = new URL(response.url())
      if (url.pathname.startsWith('/dolphinscheduler/') && response.status() === 401) {
        result.dsUnauthorized.push(`${response.request().method()} ${url.pathname}`)
      }
    })

    await page.goto(`${BASE}/p/${PROJECT_ID}/dag`, { waitUntil: 'domcontentloaded' })

    // §10.5 B：工作流定义列表是 datara 自建页（不进 iframe），先等列表渲染。
    await page.locator('[data-tc-wf-list]').waitFor({ timeout: 30000 })
    await page.locator('[data-wf-table]').waitFor({ timeout: 30000 })
    const listRows = page.locator('[data-wf-row]')
    result.wfRowCount = await listRows.count()
    result.wfFirstRowText = result.wfRowCount > 0 ? (await listRows.first().innerText()).replace(/\s+/g, ' ').trim() : null
    if (result.wfRowCount === 0) throw new Error('workflow definition list is empty; cannot open canvas')

    // §10.4：点行 → 宿主切到画布态并挂载单个 DAG 画布 iframe。
    await page.locator('[data-wf-open]').first().click()
    await page.locator('[data-tc-ds-frame]').waitFor({ timeout: 30000 })

    const frameHandle = await page.locator('[data-tc-ds-frame]').elementHandle()
    const frame = await frameHandle.contentFrame()
    if (!frame) throw new Error('ds iframe has no content frame')
    result.frameUrl = frame.url()
    // §10.7 A1：iframe 必须落在单个 DAG 画布路由（不是 DS 列表页），且带 embed=1。
    const frameParsed = new URL(frame.url())
    result.frameRouteIsCanvasRoute =
      /^\/dolphinscheduler\/ui\/projects\/[^/]+\/workflow\/definitions\/(?:\d+|create)$/.test(frameParsed.pathname) &&
      frameParsed.search.includes('embed=1')

    await frame.locator('body').waitFor({ timeout: 30000 })
    // 海豚 UI 挂载成功的判据：embed 占位消失且根节点渲染出内容（占位存在 = 仍在等宿主会话）
    result.dsUiMounted = await frame
      .waitForFunction(
        () => !document.getElementById('datara-embed-pending') && (document.getElementById('app')?.children.length ?? 0) > 0,
        null,
        { timeout: 45000 },
      )
      .then(() => true)
      .catch(() => false)

    // 会话落地后 DS 会走一次列表拉取；等网络静默再取 DOM 快照，避免抓到空壳。
    await page.waitForTimeout(4000)
    result.frameRoute = await frame.evaluate(() => location.pathname + location.search)
    const shotPath = require('path').join(require('os').tmpdir(), 'datara-ds-embed.png')
    await page.locator('[data-tc-ds-frame]').screenshot({ path: shotPath }).catch(() => {})
    result.screenshot = shotPath

    const probe = await frame.evaluate(() => {
      const text = (document.body.innerText || '').slice(0, 4000)
      const visible = (el) => {
        if (!el) return false
        const rect = el.getBoundingClientRect()
        const style = getComputedStyle(el)
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'
      }
      const navSelectors = ['.n-layout-sider', 'aside', '[class*="sider"]', '[class*="side-menu"]']
      const navNodes = navSelectors.flatMap((sel) => Array.from(document.querySelectorAll(sel))).filter(visible)
      // 海豚全局顶栏：embed 模式应隐藏。只认语义化顶栏选择器——列表页卡片标题
      // （.n-card-header）等 `[class*="header"]` 宽匹配属内容元素，不算全局顶栏。
      const headerSelectors = ['header', '.n-layout-header', '[class*="layout-header"]', '.n-layout-header__main']
      const headerNodes = headerSelectors.flatMap((sel) => Array.from(document.querySelectorAll(sel))).filter(visible)
      const passwordInputs = Array.from(document.querySelectorAll('input[type="password"]')).filter(visible)
      const buttons = Array.from(document.querySelectorAll('button')).map((b) => (b.innerText || '').trim()).filter(Boolean)
      return {
        hasText: text.length > 0,
        textSample: text.slice(0, 400),
        navCount: navNodes.length,
        headerCount: headerNodes.length,
        passwordCount: passwordInputs.length,
        buttons: buttons.slice(0, 40),
        embedFlag: location.search.includes('embed=1'),
      }
    })
    result.dsNavHidden = probe.navCount === 0
    result.dsHeaderHidden = probe.headerCount === 0
    result.dsLoginFormVisible = probe.passwordCount > 0
    result.canvasToolbar = probe.buttons
    result.embedFlag = probe.embedFlag
    result.dsTextSample = probe.textSample

    const state = await page.evaluate(() => ({
      pathname: location.pathname,
      hostTabs: !!document.querySelector('[data-tc-tabs]'),
      embedVisible: !!document.querySelector('[data-tc-embed]'),
      emptyVisible: !!document.querySelector('[data-tc-empty]'),
      persistedToken: !!localStorage.getItem('datara_token') || !!sessionStorage.getItem('datara_token'),
      urlHasToken: location.href.includes('token='),
    }))
    result.hostPersistedToken = state.persistedToken
    result.hostTabs = state.hostTabs
    result.embedVisible = state.embedVisible
    result.emptyVisible = state.emptyVisible
    result.hostUrlHasToken = state.urlHasToken
    result.hostPathname = state.pathname
    result.hostMsgLog = await page.evaluate(() => window.__dsMsgLog || [])
    const frameMsgLog = await frame.evaluate(() => window.__dsMsgLog || [])
    result.frameMsgLog = frameMsgLog
    result.dsReadyReceived = result.hostMsgLog.some((entry) => entry.type === 'datara:ds-ready')
    result.dsSessionSent = frameMsgLog.some((entry) => entry.type === 'datara:ds-session')
    const sessionEntry = frameMsgLog.find((entry) => entry.type === 'datara:ds-session')
    result.dsSessionFields = sessionEntry?.fields ?? null

    console.log(JSON.stringify(result))
    const failures = [
      result.wfRowCount === 0,
      !result.frameRouteIsCanvasRoute,
      !result.dsUiMounted,
      !result.embedFlag,
      !result.dsNavHidden,
      !result.dsHeaderHidden,
      !result.dsReadyReceived,
      result.dsLoginFormVisible,
      result.hostPersistedToken,
      result.hostUrlHasToken,
      result.dsUnauthorized.length > 0,
      result.pageErrors.length > 0,
    ].filter(Boolean).length
    if (failures) process.exitCode = 1
  } finally {
    await browser.close()
    await api.dispose()
  }
}

main().catch((error) => {
  console.error(error.message)
  process.exitCode = 1
})
