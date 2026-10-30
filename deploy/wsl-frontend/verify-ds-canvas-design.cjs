/**
 * §10.7 A1/A2 海豚集成验收（画布可设计 + 脚本挂接）浏览器验证。
 *
 * A1 可设计：新建/打开 DAG → 拖节点 → 配节点表单 → 连线 → 保存 → 重新打开内容一致。
 * A2 可设计（脚本挂接）：Python/shell 节点可从 datara 脚本库选脚本挂上；
 *     保存后重开仍指向同一脚本 ID。
 *
 * 画布为 @antv/x6：节点 `.x6-node`（标题在 `text` 子节点）、边 `.x6-edge`、
 * 每个节点自带一个 `+` 磁吸端口 `.x6-port`（magnet:true，allowPort:false → 边从节点出发）。
 * 节点设置弹窗确认键 `.btn-submit`、取消键 `.btn-cancel`；
 * 工作流工具栏保存键 `.btn-save` → 保存弹窗（名字 `.input-name`）→ `.btn-submit`。
 *
 * 用法：node deploy/wsl-frontend/verify-ds-canvas-design.cjs [baseUrl] [projectId] [newNodeName]
 * 证据：stdout 输出单行 JSON；任一断言不成立则 exitCode=1。
 */
let playwright
try {
  playwright = require('../../datara-newweb/node_modules/@playwright/test')
} catch {
  playwright = require('playwright-core')
}
const { chromium, request } = playwright

const BASE = process.argv[2] || 'http://192.168.1.9:18091'
const PROJECT_ID = Number(process.argv[3] || 33)
// 画布节点标题经 utils.truncateText(name, 18) 截断，故名称必须 <= 18 字符
let NEW_NODE_NAME = process.argv[4] || `a1_shell_${String(Date.now()).slice(-6)}`
const SCRIPT_SELECTOR_LABEL = '从脚本库选择（可选，留空则执行下方手写脚本）'
const SCRIPT_KIND = 'shell'

async function main() {
  const token = process.env.DATARA_DS_VERIFY_TOKEN
  if (!token) throw new Error('DATARA_DS_VERIFY_TOKEN unavailable')

  const api = await request.newContext({ baseURL: BASE, extraHTTPHeaders: { token } })
  const sessionResponse = await api.get(`/api/v1/rebuild/orchestration/session?project_id=${PROJECT_ID}`)
  if (!sessionResponse.ok()) throw new Error(`orchestration session ${sessionResponse.status()}`)
  const session = (await sessionResponse.json()).data ?? {}
  if (!session.projectCode) throw new Error('orchestration session missing projectCode')

  // A2 真源：datara 脚本库（节点下拉必须与此一致）
  const scriptsResponse = await api.get(
    `/api/v1/rebuild/orchestration/scripts?kind=${SCRIPT_KIND}&project_id=${PROJECT_ID}`,
  )
  if (!scriptsResponse.ok()) throw new Error(`orchestration scripts ${scriptsResponse.status()}`)
  const scriptsBody = await scriptsResponse.json()
  const libraryScripts = Array.isArray(scriptsBody.data) ? scriptsBody.data : []

  const browser = await chromium.launch({ headless: true, executablePath: process.env.DATARA_CHROMIUM_PATH || undefined })
  const result = {
    base: BASE,
    projectCode: session.projectCode,
    newNodeName: NEW_NODE_NAME,
    libraryScriptCount: libraryScripts.length,
    libraryScriptNames: libraryScripts.map((item) => item.name),
    before: null,
    afterDrag: null,
    nodeModal: null,
    scriptOptions: [],
    scriptSelected: null,
    rawScriptFilled: null,
    afterConnect: null,
    saved: null,
    afterReload: null,
    pageErrors: [],
    failures: [],
  }

  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
    page.setDefaultTimeout(15000)
    await page.addInitScript((shortLivedToken) => {
      if (window.top === window) window.__DATARA_TEST_TOKEN__ = shortLivedToken
    }, token)
    page.on('pageerror', (error) =>
      result.pageErrors.push(
        `${error.name}: ${error.message} | ${String(error.stack || '').split('\n').slice(1, 4).join(' <- ')}`.slice(0, 900),
      ),
    )

    // 捕获工作流保存请求的真实响应：DS 会在任务重名等校验失败时返回非 2xx，
    // 仅看弹窗是否关闭会把它误判为保存成功。
    const saveCalls = []
    page.on('response', async (res) => {
      const method = res.request().method()
      if (method !== 'PUT' && method !== 'POST') return
      if (!res.url().includes('workflow-definition')) return
      let body = ''
      try {
        body = (await res.text()).slice(0, 500)
      } catch {
        body = '<body unavailable>'
      }
      saveCalls.push({ method, url: res.url(), status: res.status(), body })
    })

    await openCanvas(page, result)
    const frame = await canvasFrame(page)
    await frame.locator('.dag-container').waitFor({ timeout: 45000 })
    await page.waitForTimeout(2500)

    result.before = await readGraph(frame)
    if (result.before.nodes.length === 0) throw new Error('canvas has no baseline nodes')

    // 同名节点会让 DS 拒绝保存（task name duplicate），故每次运行用唯一名。
    if (result.before.nodes.includes(NEW_NODE_NAME)) {
      const suffix = Date.now().toString(36).slice(-4)
      NEW_NODE_NAME = `${NEW_NODE_NAME.slice(0, 14)}_${suffix}`.slice(0, 18)
      result.newNodeName = NEW_NODE_NAME
    }

    // ---- A1：从侧栏拖一个 SHELL 节点到画布 ----
    await expandCategory(frame, 'universal')
    const box = await frame.locator('.dag-container').boundingBox()
    const stray = frame.locator('.n-modal').last()
    if ((await stray.count()) > 0) await closeNodeModal(stray)
    // 落点必须避开既有节点：重叠后源端口会落在目标包围盒内，X6 命中测试解析不到目标节点本体
    const dropPoint = await freeDropPoint(frame, box, result.before.nodes)
    result.dropPoint = dropPoint
    try {
      await frame.dragAndDrop('.task-item-SHELL', '.dag-container', {
        sourcePosition: { x: 20, y: 10 },
        targetPosition: dropPoint,
        timeout: 15000,
      })
    } catch (error) {
      throw new Error(`drag SHELL failed: ${error.message.split('\n')[0]}`)
    }
    const modal = frame.locator('.n-modal').last()
    await modal.locator('.n-form-item').first().waitFor({ timeout: 20000 })
    await page.waitForTimeout(2500)

    // `.input-node-name` 是 naive-ui NInput 的外层包装 div，真正可填的是其内层 <input>
    const nameInput = modal.locator('.input-node-name input').first()
    result.nodeModal = {
      opened: (await nameInput.count()) > 0,
      labels: [],
      html: (await modal.evaluate((el) => el.outerHTML).catch(() => '')).slice(0, 4000),
    }
    for (const item of await modal.locator('.n-form-item').all()) {
      const label = (await item.locator('.n-form-item-label__text').first().innerText().catch(() => '')).trim()
      if (label) result.nodeModal.labels.push(label)
    }

    // ---- A1：配节点表单（名称）----
    if (result.nodeModal.opened) {
      await nameInput.fill(NEW_NODE_NAME, { timeout: 10000 })
      await page.waitForTimeout(400)
    }

    // ---- A2：从 datara 脚本库选脚本 ----
    // SHELL 节点「脚本」为必填：未选脚本时点提交会静默校验失败（弹窗不关闭、节点标题仍是 code）
    const scriptItem = await findFormItemByLabel(modal, SCRIPT_SELECTOR_LABEL)
    result.nodeModal.hasScriptSelector = Boolean(scriptItem)
    if (scriptItem) {
      await readSelectOptions(page, frame, modal, scriptItem, result.scriptOptions)
      if (result.scriptOptions.length > 0) {
        const picked = await pickOption(page, frame, modal, scriptItem, result.scriptOptions[0])
        await page.waitForTimeout(1500)
        result.scriptSelected = picked ? result.scriptOptions[0] : null
        // 选中后脚本正文应回填到 rawScript（monaco 的隐藏 textarea）
        const raw = modal.locator('textarea, .n-input__textarea').first()
        result.rawScriptFilled =
          (await raw.count()) > 0 && ((await raw.inputValue().catch(() => '')) || '').length > 0
      }
    }

    // ---- A1：保存节点 ----
    if (result.nodeModal.opened) {
      await modal.locator('.btn-submit').click({ timeout: 10000 }).catch(() => {})
      const closed = await modal
        .waitFor({ state: 'detached', timeout: 12000 })
        .then(() => true)
        .catch(() => false)
      result.nodeModal.closedOnSubmit = closed
      if (!closed) result.nodeModal.invalidFields = await readInvalidFields(modal)
    }
    await page.waitForTimeout(1200)
    result.afterDrag = await readGraph(frame)

    // ---- A1：连线（从新节点 `+` 端口拖到既有节点）----
    result.afterConnect = await connectNodes(page, frame, NEW_NODE_NAME, result.before.nodes[0])

    // ---- A1：保存工作流 ----
    result.saved = await saveWorkflow(page, frame, saveCalls)
    result.saveCalls = saveCalls

    // ---- A1/A2：重新打开，内容一致 ----
    await page.goto(`${BASE}/p/${PROJECT_ID}/dag`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-tc-wf-list]').waitFor({ timeout: 30000 })
    await page.locator('[data-wf-open]').first().click()
    await page.locator('[data-tc-ds-frame]').waitFor({ timeout: 30000 })
    const frame2 = await canvasFrame(page)
    await frame2.locator('.dag-container').waitFor({ timeout: 45000 })
    await page.waitForTimeout(3000)
    result.afterReload = await readGraph(frame2)
    // 重开后双击新节点，读回脚本选择器指向（A2 持久化）
    result.reopenedNodeForm = await reopenNodeForm(page, frame2, NEW_NODE_NAME, result.scriptSelected)

    const shot = require('path').join(require('os').tmpdir(), 'datara-ds-canvas-design.png')
    await page.locator('[data-tc-ds-frame]').screenshot({ path: shot }).catch(() => {})
    result.screenshot = shot

    // ---- 断言 ----
    if (!result.nodeModal.opened) result.failures.push('A1: node modal did not open')
    if (result.afterDrag.nodes.length !== result.before.nodes.length + 1) {
      result.failures.push(
        `A1: node count not +1 after drag (${result.before.nodes.length} -> ${result.afterDrag.nodes.length})`,
      )
    }
    if (!result.afterDrag.nodes.includes(NEW_NODE_NAME)) {
      result.failures.push(`A1: new node "${NEW_NODE_NAME}" not on canvas`)
    }
    if (!result.afterConnect.connected) {
      result.failures.push(`A1: connect failed (${result.afterConnect.error || 'no edge added'})`)
    }
    if (!result.saved.saved) {
      result.failures.push(`A1: workflow save failed (${result.saved.error || 'unknown'})`)
    }
    if (!result.afterReload.nodes.includes(NEW_NODE_NAME)) {
      result.failures.push('A1: new node missing after reload (save did not persist)')
    }
    if (result.afterReload.edges !== result.afterConnect.edges) {
      result.failures.push(
        `A1: edge count changed after reload (${result.afterConnect.edges} -> ${result.afterReload.edges})`,
      )
    }
    if (!result.nodeModal.hasScriptSelector) {
      result.failures.push('A2: script library selector missing')
    } else {
      const fromLibrary =
        result.scriptOptions.length > 0 &&
        result.scriptOptions.every((label) => libraryScripts.some((item) => label.includes(item.name)))
      if (!fromLibrary) {
        result.failures.push(`A2: script options not from datara library (${JSON.stringify(result.scriptOptions)})`)
      }
      if (!result.scriptSelected) result.failures.push('A2: could not select a script')
      else if (!result.reopenedNodeForm.scriptIdPersisted) {
        result.failures.push(
          `A2: scriptId not persisted after reload (selected=${result.scriptSelected}, reopened=${JSON.stringify(result.reopenedNodeForm)})`,
        )
      }
    }

    console.log(JSON.stringify(result))
    if (result.failures.length || result.pageErrors.length) process.exitCode = 1
  } finally {
    await browser.close()
    await api.dispose()
  }
}

/** 打开工作流定义列表并进入第一个 DAG 画布。 */
async function openCanvas(page, result) {
  await page.goto(`${BASE}/p/${PROJECT_ID}/dag`, { waitUntil: 'domcontentloaded' })
  await page.locator('[data-tc-wf-list]').waitFor({ timeout: 30000 })
  await page.locator('[data-wf-table]').waitFor({ timeout: 30000 })
  const rows = page.locator('[data-wf-row]')
  result.wfRowCount = await rows.count()
  result.wfFirstRowText =
    result.wfRowCount > 0 ? (await rows.first().innerText()).replace(/\s+/g, ' ').trim() : null
  if (result.wfRowCount === 0) throw new Error('workflow definition list is empty')
  await page.locator('[data-wf-open]').first().click()
  await page.locator('[data-tc-ds-frame]').waitFor({ timeout: 30000 })
}

async function canvasFrame(page) {
  const frame = await (await page.locator('[data-tc-ds-frame]').elementHandle()).contentFrame()
  if (!frame) throw new Error('ds iframe has no content frame')
  return frame
}

/**
 * 读取画布节点标题与边数。
 * 注意：画布容器内有 2 个 `.x6-graph`（主图 `.x6-graph-scroller` + 小地图
 * `.x6-widget-minimap`），同一节点会被渲染两份；必须限定主图作用域，否则双倍计数、
 * 且取到 minimap 里的小尺寸节点会让鼠标坐标全部偏移。
 */
async function readGraph(frame) {
  return frame.evaluate(() => {
    const root = document.querySelector('.x6-graph-scroller') || document
    const nodes = Array.from(root.querySelectorAll('.x6-node'))
      .map((node) => {
        const text = node.querySelector('text')
        return text ? text.textContent.trim() : ''
      })
      .filter(Boolean)
    return { nodes, edges: root.querySelectorAll('.x6-edge').length }
  })
}

/** 在主图作用域内按标题找节点元素句柄。 */
async function nodeHandle(frame, name) {
  const handle = await frame.evaluateHandle(({ wanted }) => {
    const root = document.querySelector('.x6-graph-scroller') || document
    return (
      Array.from(root.querySelectorAll('.x6-node')).find((node) => {
        const text = node.querySelector('text')
        return text && text.textContent.trim() === wanted
      }) || null
    )
  }, { wanted: name })
  return handle.asElement()
}

/**
 * 在画布内挑一个不与既有节点重叠的落点（`.dag-container` 内相对坐标）。
 * 与既有节点重叠时，源节点端口会落在目标包围盒内，X6 命中测试解析不到目标节点本体，
 * 连线必然失败；从源头避开重叠比事后拖动更可靠。
 */
async function freeDropPoint(frame, containerBox, nodeNames) {
  const occupied = []
  for (const name of nodeNames) {
    const handle = await nodeHandle(frame, name)
    const nodeBox = handle ? await handle.boundingBox() : null
    if (!nodeBox) continue
    occupied.push({
      x: nodeBox.x - containerBox.x,
      y: nodeBox.y - containerBox.y,
      width: nodeBox.width,
      height: nodeBox.height,
    })
  }
  const pad = 40
  // 节点约 220x50，落点为节点中心
  const clear = (point) =>
    occupied.every(
      (o) =>
        point.x + 110 + pad < o.x ||
        point.x - 110 - pad > o.x + o.width ||
        point.y + 25 + pad < o.y ||
        point.y - 25 - pad > o.y + o.height,
    )
  const candidates = []
  for (const fy of [0.78, 0.62, 0.88, 0.45, 0.3]) {
    for (const fx of [0.72, 0.56, 0.86, 0.4, 0.26]) {
      candidates.push({ x: Math.round(containerBox.width * fx), y: Math.round(containerBox.height * fy) })
    }
  }
  return candidates.find(clear) || candidates[0]
}

/** 在主图作用域内按标题找节点上的 `+` 磁吸端口。 */
async function portHandle(frame, name) {
  const handle = await frame.evaluateHandle(({ wanted }) => {
    const root = document.querySelector('.x6-graph-scroller') || document
    const hit = Array.from(root.querySelectorAll('.x6-node')).find((node) => {
      const text = node.querySelector('text')
      return text && text.textContent.trim() === wanted
    })
    return hit ? hit.querySelector('.x6-port') : null
  }, { wanted: name })
  return handle.asElement()
}

/**
 * 按标签文本精确匹配表单行。
 * naive-ui 的 NFormItemGi 结构下 `.n-form-item-label__text` 的 hasText 过滤不可靠，
 * 故遍历取 label innerText 精确相等。
 */
async function findFormItemByLabel(modal, label) {
  for (const item of await modal.locator('.n-form-item').all()) {
    const text = (await item.locator('.n-form-item-label__text').first().innerText().catch(() => '')).trim()
    if (text === label) return item
  }
  return null
}

/** 提交失败时读回校验未通过的表单行，便于定位阻断项。 */
async function readInvalidFields(modal) {
  return modal.evaluate((el) =>
    Array.from(el.querySelectorAll('.n-form-item'))
      .map((item) => {
        const label = (item.querySelector('.n-form-item-label__text') || {}).textContent || ''
        const feedback = Array.from(item.querySelectorAll('.n-form-item-feedback__line'))
          .map((line) => (line.textContent || '').trim())
          .filter(Boolean)
        const invalid = item.classList.contains('n-form-item--error') || feedback.length > 0
        return invalid ? { label: label.trim(), feedback } : null
      })
      .filter(Boolean),
  )
}

async function expandCategory(frame, category) {
  const panel = frame.locator(`.task-cate-${category}`).first()
  if ((await panel.count()) === 0) return false
  const hasItems = await panel.evaluate((el) => el.querySelectorAll('[class*="task-item-"]').length > 0)
  if (hasItems) return true
  await panel.locator('.n-collapse-item__header').first().click({ timeout: 5000 }).catch(() => {})
  await frame.waitForTimeout(700)
  return true
}

/**
 * 把目标节点拖离源节点，避免两者重叠。
 * 重叠时源端口会落在目标节点包围盒内，X6 命中测试解析不到目标节点本体，
 * 且拖动距离过短被判定为点击而非连线。
 */
async function separateNode(page, frame, name, dx, dy) {
  const node = await nodeHandle(frame, name)
  if (!node) return false
  const box = await node.boundingBox()
  if (!box) return false
  // 从节点下部按下：标题文本区可能被 X6 当作文本选择而非节点拖拽
  const cx = box.x + box.width / 2
  const cy = box.y + box.height * 0.75
  await page.mouse.move(cx, cy)
  await frame.waitForTimeout(300)
  await page.mouse.down()
  for (let i = 1; i <= 20; i++) {
    await page.mouse.move(cx + (dx * i) / 20, cy + (dy * i) / 20)
    await frame.waitForTimeout(30)
  }
  await page.mouse.up()
  await frame.waitForTimeout(1200)
  const moved = await (await nodeHandle(frame, name))?.boundingBox()
  // 位移生效才算分离成功（X6 可能把拖动判为点击而原地不动）
  return Boolean(moved) && Math.abs(moved.x - box.x) + Math.abs(moved.y - box.y) > 20
}

/**
 * 从新节点的 `+` 端口拖到目标节点本体，返回是否新增了一条边。
 * 坐标一律取 Playwright 的 `boundingBox()`（已换算到主框架坐标系）；
 * `frame.evaluate` 里的 `getBoundingClientRect()` 是 iframe 内坐标，宿主有偏移会全部落空。
 * `connecting.allowPort=false`，故终点必须落在目标**节点本体**（取其左半区，避开自身 `+` 端口）。
 */
async function connectNodes(page, frame, sourceName, targetName) {
  const before = await readGraph(frame)
  const sourceNode = await nodeHandle(frame, sourceName)
  if (!sourceNode) return { connected: false, error: `source node "${sourceName}" not found`, edges: before.edges }
  const sourceBox = await sourceNode.boundingBox()
  if (!sourceBox) return { connected: false, error: 'source node has no box', edges: before.edges }
  // 先悬停让磁吸端口显形
  await page.mouse.move(sourceBox.x + sourceBox.width / 2, sourceBox.y + sourceBox.height / 2)
  await frame.waitForTimeout(500)

  const port = await portHandle(frame, sourceName)
  if (!port) return { connected: false, error: 'source port not found', edges: before.edges }
  const portBox = await port.boundingBox()
  if (!portBox) return { connected: false, error: 'source port has no box', edges: before.edges }

  const targetNode = await nodeHandle(frame, targetName)
  if (!targetNode) return { connected: false, error: `target node "${targetName}" not found`, edges: before.edges }
  const targetBox = await targetNode.boundingBox()
  if (!targetBox) return { connected: false, error: 'target node has no box', edges: before.edges }

  // 节点重叠时端口会落在目标包围盒内，先拖开目标节点
  const overlap =
    sourceBox.x < targetBox.x + targetBox.width &&
    targetBox.x < sourceBox.x + sourceBox.width &&
    sourceBox.y < targetBox.y + targetBox.height &&
    targetBox.y < sourceBox.y + sourceBox.height
  const debug = {
    sourceBox,
    portBox,
    targetBox,
    overlap,
    separated: false,
    movedBox: null,
    from: null,
    to: null,
  }
  if (overlap) {
    debug.separated = await separateNode(page, frame, targetName, 300, 60)
  }
  const moved = await (await nodeHandle(frame, targetName))?.boundingBox()
  if (!moved) return { connected: false, error: 'target node vanished after separate', edges: before.edges, debug }
  debug.movedBox = moved

  const sx = portBox.x + portBox.width / 2
  const sy = portBox.y + portBox.height / 2
  const tx = moved.x + moved.width * 0.35
  const ty = moved.y + moved.height / 2
  debug.from = [Math.round(sx), Math.round(sy)]
  debug.to = [Math.round(tx), Math.round(ty)]

  await page.mouse.move(sx, sy)
  await frame.waitForTimeout(400)
  // X6 在 magnet 上 mousedown 即 createEdge → 图中会立刻出现一条临时边；
  // 边数不变说明连接根本没启动（magnet 不可连 / 按下点没命中 magnet）
  debug.portHover = await frame.evaluate(({ wanted }) => {
    const root = document.querySelector('.x6-graph-scroller') || document
    const node = Array.from(root.querySelectorAll('.x6-node')).find((el) => {
      const text = el.querySelector('text')
      return text && text.textContent.trim() === wanted
    })
    if (!node) return null
    const port = node.querySelector('.x6-port')
    if (!port) return null
    const outer = port.querySelector('circle')
    return {
      portClass: port.getAttribute('class'),
      outerR: outer ? outer.getAttribute('r') : null,
      outerFill: outer ? outer.getAttribute('fill') : null,
    }
  }, { wanted: sourceName })
  await page.mouse.down()
  await frame.waitForTimeout(400)
  debug.edgesAfterDown = (await readGraph(frame)).edges
  await page.mouse.move((sx + tx) / 2, (sy + ty) / 2, { steps: 10 })
  await page.mouse.move(tx, ty, { steps: 10 })
  await frame.waitForTimeout(400)
  debug.edgesBeforeUp = (await readGraph(frame)).edges
  await page.mouse.up()
  await frame.waitForTimeout(1200)

  const after = await readGraph(frame)
  return {
    connected: after.edges > before.edges,
    edges: after.edges,
    beforeEdges: before.edges,
    debug,
  }
}

/**
 * 点工具栏保存 → 保存弹窗确认。
 * 以 DS 侧真实响应为准：弹窗关闭不代表落库（任务重名等校验失败时 DS 返回非 2xx）。
 */
async function saveWorkflow(page, frame, saveCalls = []) {
  const saveBtn = frame.locator('.btn-save')
  if ((await saveBtn.count()) === 0) return { saved: false, error: '.btn-save not found' }
  if (await saveBtn.isDisabled().catch(() => false)) return { saved: false, error: '.btn-save disabled' }
  const before = saveCalls.length
  await saveBtn.click({ timeout: 10000 }).catch(() => {})
  const modal = frame.locator('.n-modal').last()
  try {
    await modal.locator('.input-name input').waitFor({ timeout: 10000 })
  } catch {
    return { saved: false, error: 'save modal did not open' }
  }
  await modal.locator('.btn-submit').click({ timeout: 10000 }).catch(() => {})
  await modal.waitFor({ state: 'detached', timeout: 15000 }).catch(() => {})
  await frame.waitForTimeout(2500)
  const sent = saveCalls.slice(before)
  if (sent.length === 0) return { saved: false, error: 'no save request observed' }
  const last = sent[sent.length - 1]
  const saved = last.status >= 200 && last.status < 300
  return { saved, status: last.status, body: saved ? '' : last.body, responses: sent }
}

/**
 * 重开后双击新节点，读回节点表单里的脚本选择器指向。
 * 用真实鼠标双击（X6 的 `cell:dblclick` 依赖原生事件冒泡，合成事件不触发编辑）。
 */
async function reopenNodeForm(page, frame, nodeName, selectedScript) {
  const node = await nodeHandle(frame, nodeName)
  if (!node) return { opened: false, error: 'node not found' }
  const box = await node.boundingBox()
  if (!box) return { opened: false, error: 'node has no box' }
  const modal = frame.locator('.n-modal').last()
  let opened = false
  // 双击后弹窗有动画延迟，且偶发丢失首次双击；轮询 + 重试一次
  for (let attempt = 0; attempt < 2 && !opened; attempt++) {
    await page.mouse.dblclick(box.x + box.width / 2, box.y + box.height / 2)
    for (let i = 0; i < 16; i++) {
      await page.waitForTimeout(500)
      if ((await modal.locator('.n-form-item').count()) > 0) {
        opened = true
        break
      }
    }
  }
  if (!opened) return { opened: false, error: 'node form did not open on dblclick' }
  // 脚本选择器当前值（含脚本名 + 版本）
  const scriptItem = await findFormItemByLabel(modal, SCRIPT_SELECTOR_LABEL)
  const value = scriptItem
    ? ((await scriptItem.locator('.n-base-selection').first().innerText().catch(() => '')) || '').trim()
    : ''
  const nodeNameInForm = await modal.locator('.input-node-name input').first().inputValue().catch(() => '')
  // 保存后重开仍指向同一脚本（按脚本名比对，版本后缀容错）
  const baseName = selectedScript ? String(selectedScript).split(' (')[0] : ''
  const scriptIdPersisted = Boolean(baseName) && value.includes(baseName)
  await closeNodeModal(modal)
  return { opened: true, scriptSelectorValue: value, nodeNameInForm, scriptIdPersisted }
}

/** 关闭节点设置弹窗并等其脱离 DOM。 */
async function closeNodeModal(modal) {
  await modal.locator('.btn-cancel').click({ timeout: 5000 }).catch(() => {})
  await modal.waitFor({ state: 'detached', timeout: 8000 }).catch(() => {})
}

async function closeDropdown(page, frame, modal) {
  const box = await modal.boundingBox().catch(() => null)
  if (box) await page.mouse.click(box.x + 30, box.y + 18).catch(() => {})
  await frame.waitForTimeout(300)
}

async function readSelectOptions(page, frame, modal, formItem, sink) {
  const trigger = formItem.locator('.n-base-selection').first()
  if ((await trigger.count()) === 0) return
  await trigger.click({ timeout: 5000 }).catch(() => {})
  await frame.waitForTimeout(600)
  sink.push(...(await readVisibleOptions(frame)))
  await closeDropdown(page, frame, modal)
}

async function readVisibleOptions(frame) {
  return frame.evaluate(() => {
    const shown = (el) => {
      const rect = el.getBoundingClientRect()
      const style = window.getComputedStyle(el)
      return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'
    }
    const menus = Array.from(document.querySelectorAll('.n-base-select-menu')).filter(shown)
    const menu = menus[menus.length - 1]
    if (!menu) return []
    return Array.from(menu.querySelectorAll('.n-base-select-option'))
      .map((el) => (el.textContent || '').trim())
      .filter(Boolean)
  })
}

async function pickOption(page, frame, modal, formItem, text) {
  const trigger = formItem.locator('.n-base-selection').first()
  await trigger.click({ timeout: 5000 }).catch(() => {})
  await frame.waitForTimeout(600)
  const option = await findVisibleOption(frame, text)
  const hit = Boolean(option)
  if (hit) await option.click({ timeout: 5000 }).catch(() => {})
  await frame.waitForTimeout(600)
  await closeDropdown(page, frame, modal)
  return hit
}

async function findVisibleOption(frame, text) {
  return frame
    .evaluateHandle(
      ({ wanted }) => {
        const shown = (el) => {
          const rect = el.getBoundingClientRect()
          const style = window.getComputedStyle(el)
          return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none'
        }
        const menus = Array.from(document.querySelectorAll('.n-base-select-menu')).filter(shown)
        const menu = menus[menus.length - 1]
        if (!menu) return null
        const options = Array.from(menu.querySelectorAll('.n-base-select-option'))
        const exact = options.find((el) => (el.textContent || '').trim() === wanted)
        return exact || options[0] || null
      },
      { wanted: text || '' },
    )
    .then((handle) => (handle.asElement() ? handle : null))
}

main().catch((error) => {
  console.error(error.stack || error.message)
  process.exitCode = 1
})
