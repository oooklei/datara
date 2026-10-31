/**
 * §10.7 B1 海豚集成验收（可试运行）浏览器验证。
 *
 * B1：画布「试运行」开关置真 → 启动 → 生成实例 → 任务实例日志可见。
 * （dryRun=1 语义：海豚 AbstractTaskExecutor.start() 跳过 trigger 直接 SUCCEEDED，
 *   但 worker 仍派发、任务实例 SUCCESS 且日志文件有内容。）
 *
 * 节点类型限定：当前只验证 SHELL / PYTHON / SQL（用户裁定，其余排后）。
 * 画布入口：右键节点 → 右键菜单「运行」(dag-context-menu.tsx L189-196)。
 * 启动弹窗：start-modal.tsx L655-664 的 NFormItem「是否空跑」路径 dryRun。
 *
 * 证据：stdout 单行 JSON；任一断言不成立则 exitCode=1。
 */
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
  const sessionResp = await api.get(`/api/v1/rebuild/orchestration/session?project_id=${PROJECT_ID}`)
  if (!sessionResp.ok()) throw new Error(`session ${sessionResp.status()}`)
  const session = (await sessionResp.json()).data ?? {}

  const result = {
    base: BASE,
    projectCode: session.projectCode,
    beforeInstanceTotal: 0,
    started: null,       // { instanceId, dryRun, status }
    startedResponse: null,
    instanceOnList: null,
    instanceExpanded: null,
    tasksVisible: false,
    ganttVisible: false,
    logVisible: null,    // { lineCount, firstLine }
    failures: [],
    pageErrors: [],
  }

  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.DATARA_CHROMIUM_PATH || undefined,
  })

  try {
    // 1. 取基线：启动前实例总数
    const baselineResp = await api.get(
      `/api/v1/rebuild/orchestration/workflow-instances?project_id=${PROJECT_ID}&page_no=1&page_size=1`,
    )
    const baselineBody = await baselineResp.json()
    result.beforeInstanceTotal = baselineBody.data?.total ?? 0

    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
    page.setDefaultTimeout(15000)
    await page.addInitScript((shortLivedToken) => {
      if (window.top === window) window.__DATARA_TEST_TOKEN__ = shortLivedToken
    }, token)
    page.on('pageerror', (error) =>
      result.pageErrors.push(`${error.name}: ${error.message}`.slice(0, 500)),
    )

    // 捕获 DS startWorkflowInstance 响应 → 解析新实例 ID
    let startResp = null
    page.on('response', async (res) => {
      if (!res.url().includes('executors/start-workflow-instance')) return
      if (!res.ok()) return
      try {
        const body = await res.json()
        startResp = {
          url: res.url(),
          status: res.status(),
          code: body.code,
          data: body.data,
        }
      } catch {
        startResp = { url: res.url(), status: res.status(), raw: (await res.text()).slice(0, 500) }
      }
    })

    // 2. 打开工作流列表 → 点"打开"进入画布（iframe 此时才渲染）
    await page.goto(`${BASE}/p/${PROJECT_ID}/dag`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-tc-wf-list]').waitFor({ timeout: 30000 })
    await page.locator('[data-wf-open]').first().click()
    await page.locator('[data-tc-ds-frame]').waitFor({ timeout: 30000 })
    const frameHandle = await page.locator('[data-tc-ds-frame]').elementHandle()
    const frame = await frameHandle.contentFrame()
    await frame.locator('.dag-container').waitFor({ timeout: 45000 })
    await page.waitForTimeout(2500)

    // 3. 画布首节点右键 → 右键菜单 → 点"运行"
    const firstNode = frame.locator('.x6-graph-scroller .x6-node').first()
    const firstBox = await firstNode.boundingBox()
    if (!firstBox) { result.failures.push('canvas has no node'); throw new Error('no node') }
    // 右键节点中心
    await page.mouse.click(firstBox.x + firstBox.width / 2, firstBox.y + firstBox.height / 2, { button: 'right' })
    await frame.waitForTimeout(600)
    const menuRun = frame.getByRole('button', { name: /运行/ })
    if ((await menuRun.count()) === 0) {
      // 兜底：按 class 找 context menu 里按钮
      const ctxBtns = frame.locator('.dag-context-menu .n-button, .dag-context-menu button')
      const count = await ctxBtns.count()
      for (let i = 0; i < count; i++) {
        const txt = (await ctxBtns.nth(i).innerText().catch(() => '')).trim()
        if (txt.includes('运行')) { await ctxBtns.nth(i).click(); break }
      }
    } else {
      await menuRun.click()
    }
    await frame.waitForTimeout(1500)

    // 4. 启动弹窗 → dry-run 开关置真 → 提交
    const modal = frame.locator('.n-modal').last()
    await modal.locator('.n-form-item').first().waitFor({ timeout: 15000 })

    // 找 dry-run FormItem：label 含 "空跑" 或 path 含 dryRun
    let dryRunSwitch = null
    const items = await modal.locator('.n-form-item').all()
    for (const item of items) {
      const label = (await item.locator('.n-form-item-label__text').first().innerText().catch(() => '')).trim()
      if (label.includes('空跑')) { dryRunSwitch = item.locator('.n-switch').first(); break }
    }
    if (!dryRunSwitch) dryRunSwitch = modal.locator('.n-switch').last()

    // 确保 dryRun=1：点击 NSwitch
    const switchOn = await dryRunSwitch.locator('.n-switch__button').evaluate((el) => {
      const parent = el.closest('.n-switch')
      return parent?.classList.contains('n-switch--active') ?? false
    }).catch(() => false)
    if (!switchOn) await dryRunSwitch.click({ timeout: 5000 }).catch(() => {})
    await frame.waitForTimeout(600)

    // 提交
    const submitBtn = modal.locator('.n-button--primary, .btn-submit, button').filter({ hasText: /(启动|运行|确认|OK)/ }).first()
    // naive-ui 启动弹窗主按钮文本可能是 "运行" → 点 primary 风格按钮
    const primaryBtn = modal.locator('.n-button.n-button--primary').first()
    const target = (await primaryBtn.count()) > 0 ? primaryBtn : submitBtn
    await target.click({ timeout: 10000 }).catch(() => {})

    // 等待 start 弹窗关闭 + start-workflow-instance 响应
    await modal.waitFor({ state: 'detached', timeout: 20000 }).catch(() => {})
    await frame.waitForTimeout(2000)

    result.startedResponse = startResp
    if (!startResp) {
      result.failures.push('no start-workflow-instance response observed')
    } else {
      result.started = {
        instanceId: startResp.data?.id ?? null,
        dryRun: startResp.data?.dryRun ?? null,
        workflowInstanceCode: startResp.data?.workflowInstanceCode ?? null,
      }
    }

    // 5. 轮询编排网关，拿最新实例（dryRun=1 的那一条）
    const deadline = Date.now() + 45000
    let latestInstance = null
    while (Date.now() < deadline) {
      const resp = await api.get(
        `/api/v1/rebuild/orchestration/workflow-instances?project_id=${PROJECT_ID}&page_no=1&page_size=10`,
      )
      const body = await resp.json()
      const list = body.data?.list ?? []
      latestInstance = list.find((row) => row.dryRun === 1) ?? null
      if (latestInstance) break
      await new Promise((r) => setTimeout(r, 2000))
    }
    result.instanceOnList = latestInstance

    if (!latestInstance) {
      result.failures.push('dryRun=1 workflow instance not found on list after 45s')
    } else {
      // 6. 切到 runs 页签（datara 自建实例页，DsRunMonitor）
      await page.goto(`${BASE}/p/${PROJECT_ID}/dag?tab=runs`, { waitUntil: 'domcontentloaded' })
      await page.locator('[data-tc-runs-view-dolphin]').waitFor({ timeout: 20000 })
      await page.locator('[data-tc-runs-view-dolphin]').click()
      await page.locator('[data-ds-run-monitor]').waitFor({ timeout: 25000 })
      await page.waitForTimeout(3000)

      // 7. 实例表应有 dryRun=1 行
      const instRow = page.locator(`[data-ds-run-row="${latestInstance.id}"]`)
      if ((await instRow.count()) > 0) {
        result.instanceExpanded = { id: latestInstance.id }
        // 展开详情
        await instRow.locator('[data-ds-run-detail]').click()
        await page.waitForTimeout(2500)

        result.ganttVisible = (await page.locator('[data-ds-run-gantt-bar]').count()) > 0
        result.tasksVisible = (await page.locator('[data-ds-run-tasks] tr[data-ds-run-task]').count()) > 0

        // 8. 点任务日志按钮 → 验证日志可见
        const logBtn = page.locator('[data-ds-run-task-log]').first()
        if ((await logBtn.count()) > 0) {
          const firstLogTaskId = await logBtn.getAttribute('data-ds-run-task-log-id')
          await logBtn.click()
          await page.waitForTimeout(2500)
          const body = page.locator('[data-ds-run-logs-body]')
          const hasLog = (await body.count()) > 0
          const logText = hasLog ? await body.innerText().catch(() => '') : ''
          result.logVisible = {
            taskId: firstLogTaskId,
            hasLog,
            lineCount: logText ? logText.split('\n').filter((l) => l.trim()).length : 0,
            firstLine: logText ? logText.split('\n')[0].slice(0, 120) : '',
          }
          if (result.logVisible.lineCount === 0) result.failures.push('task log body empty')
        } else {
          result.failures.push('no task log button visible in detail')
        }
      } else {
        result.failures.push(`dryRun=1 instance #${latestInstance.id} not in DsRunMonitor table`)
      }
    }

    const shot = require('path').join(require('os').tmpdir(), 'datara-b1-dryrun.png')
    await page.screenshot({ path: shot, fullPage: true }).catch(() => {})
    result.screenshot = shot

    // 最终断言
    if (!result.startedResponse || (result.startedResponse.status ?? 0) < 200 || (result.startedResponse.status ?? 0) >= 300) {
      result.failures.push(`B1 start call failed: ${JSON.stringify(result.startedResponse)}`)
    }
    if (result.started && result.started.dryRun !== 1) {
      result.failures.push(`B1 dryRun flag not 1: ${result.started.dryRun}`)
    }
    if (!result.instanceOnList) result.failures.push('B1 no dryRun instance on orchestration list')
    if (!result.logVisible) result.failures.push('B1 task log not reached')
  } finally {
    await browser.close()
    await api.dispose()
  }

  console.log(JSON.stringify(result))
  if (result.failures.length || result.pageErrors.length) process.exitCode = 1
}

main().catch((error) => {
  console.error(error.stack || error.message)
  process.exitCode = 1
})
