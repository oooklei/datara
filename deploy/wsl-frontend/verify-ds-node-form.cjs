/**
 * §10.7 A3/A4 海豚集成验收（节点表单数据源来源 + 运行位置字段）浏览器验证。
 *
 * A3：任意含数据源字段的节点（SQL/PROCEDURE/DATAX/SQOOP/…）数据源下拉均来自 dbx
 *     连接（编排网关 /api/v1/rebuild/orchestration/datasources）；选中项回写
 *     `datasource`；「数据源类型」随所选 dbx 连接自动带出。
 * A4：运行位置类节点（SHELL/PYTHON/REMOTESHELL）只出现 worker 分组下拉；
 *     REMOTESHELL 不再出现数据源选择。
 *
 * 两类节点的表单结构不同，需分别判定：
 *   - 共享字段类（SQL/PROCEDURE/DATAX，`fields/use-datasource.ts`）：
 *     两个可见 select，标签「数据源类型」+「数据源实例」。
 *   - SQOOP（`fields/use-sqoop-datasource.ts` 独立实现）：
 *     可见 select 标签「数据源」（实例）；类型由「类型」select（sourceType/targetType）
 *     驱动，实际类型字段是 span=0 的隐藏 input（标签同为「数据源」）→ 读其 value。
 *   隐藏项仍渲染进 DOM（`components/form/index.tsx` span 缺省 24，0 会退化为极窄列），
 *   故以宽度阈值区分可见/隐藏。
 *
 * 前提：192.168.1.9 隔离栈已起（18091 前端 + /dolphinscheduler 同源反代）。
 * token 由 DATARA_DS_VERIFY_TOKEN 注入（短时验证 token，仅内存，不落盘）。
 *
 * 用法：node deploy/wsl-frontend/verify-ds-node-form.cjs [baseUrl] [projectId]
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

// A3：含数据源字段的节点（共享字段 Fields.useDatasource 覆盖 + SQOOP 独立字段）
const A3_TYPES = ['SQL', 'PROCEDURE', 'DATAX', 'SQOOP']
// A4：运行位置类节点
const A4_TYPES = ['SHELL', 'PYTHON', 'REMOTESHELL']

const DS_TYPE_LABEL = '数据源类型'
const DS_INSTANCE_LABEL = '数据源实例'
const DS_LEGACY_LABEL = '数据源'
// SQOOP 的引擎类型下拉（MYSQL/ORACLE/SQLSERVER/HANA…），用于反向过滤验证
const DS_ENGINE_TYPE_LABEL = '类型'
const WORKER_GROUP_LABEL = 'Worker分组'
// 可见表单项宽度下限（span=0 的隐藏项在 24 栅格里退化到约 1 列，远小于此值）
const VISIBLE_MIN_WIDTH = 120

async function main() {
  const token = process.env.DATARA_DS_VERIFY_TOKEN
  if (!token) throw new Error('DATARA_DS_VERIFY_TOKEN unavailable')

  const api = await request.newContext({ baseURL: BASE, extraHTTPHeaders: { token } })
  const sessionResponse = await api.get(`/api/v1/rebuild/orchestration/session?project_id=${PROJECT_ID}`)
  if (!sessionResponse.ok()) throw new Error(`orchestration session ${sessionResponse.status()}`)
  const session = (await sessionResponse.json()).data ?? {}
  if (!session.projectCode) throw new Error('orchestration session missing projectCode')

  // 真源：编排网关的 dbx 连接列表（A3 断言下拉必须与此一致）
  const dsResponse = await api.get(`/api/v1/rebuild/orchestration/datasources?project_id=${PROJECT_ID}`)
  if (!dsResponse.ok()) throw new Error(`orchestration datasources ${dsResponse.status()}`)
  const dsBody = await dsResponse.json()
  const dbxConnections = Array.isArray(dsBody.data) ? dsBody.data : []

  const browser = await chromium.launch({ headless: true, executablePath: process.env.DATARA_CHROMIUM_PATH || undefined })
  const result = {
    base: BASE,
    projectCode: session.projectCode,
    dbxConnectionCount: dbxConnections.length,
    dbxConnectionNames: dbxConnections.map((item) => item.name),
    dbxConnectionTypes: [...new Set(dbxConnections.map((item) => item.type))],
    nodeForms: [],
    skipped: [],
    dragSupported: null,
    pageErrors: [],
    failures: [],
  }

  try {
    const page = await browser.newPage({ viewport: { width: 1600, height: 1000 } })
    await page.addInitScript((shortLivedToken) => {
      if (window.top === window) window.__DATARA_TEST_TOKEN__ = shortLivedToken
    }, token)
    page.on('pageerror', (error) =>
      result.pageErrors.push(
        `${error.name}: ${error.message} | ${String(error.stack || '').split('\n').slice(1, 4).join(' <- ')}`.slice(0, 900),
      ),
    )

    await page.goto(`${BASE}/p/${PROJECT_ID}/dag`, { waitUntil: 'domcontentloaded' })
    await page.locator('[data-tc-wf-list]').waitFor({ timeout: 30000 })
    // 可选第 4 参：按名称定向工作流（默认取列表首个）。海豚侧已上线（ONLINE）的定义
    // 为只读态（dag/index.tsx readonly = releaseState === 'ONLINE'），拖拽不建节点，
    // 因此探针须能定向到未上线定义，否则 A3/A4 全部误报。
    const WORKFLOW_NAME = process.argv[4]
    const targetRow = WORKFLOW_NAME
      ? (await (async () => {
          await page.locator('[data-wf-keyword]').fill(WORKFLOW_NAME)
          await page.locator('[data-wf-search]').click()
          await page.waitForTimeout(800)
          return page.locator('[data-wf-row]').filter({ hasText: WORKFLOW_NAME }).first()
        })())
      : page.locator('[data-wf-row]').first()
    const releaseCell = (await targetRow.locator('td').nth(1).innerText().catch(() => '')).trim()
    result.workflowName = WORKFLOW_NAME || (await targetRow.locator('[data-wf-open]').innerText().catch(() => ''))
    result.releaseState = releaseCell
    if (releaseCell.includes('已上线')) {
      throw new Error(`target workflow "${result.workflowName}" is ONLINE (readonly in DS); pick an offline workflow`)
    }
    await targetRow.locator('[data-wf-open]').click()
    await page.locator('[data-tc-ds-frame]').waitFor({ timeout: 30000 })
    const frame = await (await page.locator('[data-tc-ds-frame]').elementHandle()).contentFrame()
    if (!frame) throw new Error('ds iframe has no content frame')
    await frame.locator('.dag-container').waitFor({ timeout: 45000 })

    // 侧栏是手风琴（accordion），一次只展开一个任务分类；且折叠面板默认懒渲染，
    // 收起即销毁 DOM。因此需按分类逐个展开、记录归属，探测前再确保对应分类展开。
    const CATEGORIES = ['fav', 'universal', 'cloud', 'logic', 'di', 'dq', 'ml', 'other']
    const typeToCategory = {}

    const readTypes = async (category) => {
      const panel = frame.locator(`.task-cate-${category}`).first()
      if ((await panel.count()) === 0) return []
      return panel.evaluate((el) =>
        Array.from(el.querySelectorAll('[class*="task-item-"]'))
          .map((node) => (node.className.match(/task-item-([A-Z_]+)/) || [])[1])
          .filter(Boolean),
      )
    }

    const expandCategory = async (category) => {
      const panel = frame.locator(`.task-cate-${category}`).first()
      if ((await panel.count()) === 0) return false
      if ((await readTypes(category)).length > 0) return true
      await panel.locator('.n-collapse-item__header').first().click({ timeout: 5000 }).catch(() => {})
      await page.waitForTimeout(700)
      return (await readTypes(category)).length > 0
    }

    const sidebarTypes = []
    for (const category of CATEGORIES) {
      if (!(await expandCategory(category))) continue
      const types = await readTypes(category)
      for (const type of types) typeToCategory[type] = category
      sidebarTypes.push(...types)
    }
    result.sidebarTypes = sidebarTypes
    result.sidebarCategoryOf = typeToCategory
    // §10.8 M1/M2：DBX_SQL 自定义任务类型已清除（后端 yaml + SPI + 前端白名单
    // 同时下线），侧栏不得再出现该项。出现即为清除未生效。
    result.dbxSqlAbsent = !sidebarTypes.includes('DBX_SQL')
    if (!result.dbxSqlAbsent) result.failures.push('M1/M2: DBX_SQL still present in sidebar task types')

    const probe = async (taskType) => {
      const entry = {
        taskType,
        modalOpened: false,
        labels: [],
        datasourceTypeOptions: [],
        datasourceInstanceOptions: [],
        hiddenTypeValues: [],
        engineTypeOptions: [],
        foreignType: null,
        optionsAfterForeignType: [],
        hasWorkerGroup: false,
        hasDatasourceField: false,
        typeAfterSelect: null,
        instanceSelected: null,
        error: null,
      }

      // 手风琴收起时会销毁 DOM，探测前先确保该任务类型所在分类处于展开态
      const category = typeToCategory[taskType]
      if (category) await expandCategory(category)

      const source = frame.locator(`.task-item-${taskType}`).first()
      if ((await source.count()) === 0) {
        entry.error = `sidebar item not found (category=${category || 'unknown'})`
        return entry
      }
      const box = await frame.locator('.dag-container').boundingBox()
      // 上一轮残留弹窗的遮罩会吞掉拖拽事件，先清干净
      const stray = frame.locator('.n-modal').last()
      if ((await stray.count()) > 0) await closeNodeModal(stray)
      try {
        await frame.dragAndDrop(`.task-item-${taskType}`, '.dag-container', {
          sourcePosition: { x: 20, y: 10 },
          targetPosition: { x: Math.round(box.width / 2), y: Math.round(box.height / 2) },
          timeout: 15000,
        })
      } catch (error) {
        entry.error = `drag failed: ${error.message.split('\n')[0]}`
        return entry
      }

      // 节点设置弹窗：`@/components/modal` 渲染 NModal，表单项为 NFormItem（非 NFormItemGi）
      const modal = frame.locator('.n-modal').last()
      try {
        await modal.locator('.n-form-item').first().waitFor({ timeout: 20000 })
      } catch {
        entry.error = entry.error || 'node modal did not open'
        return entry
      }
      entry.modalOpened = true
      await page.waitForTimeout(2500)

      // 收集表单项：标签 + 实测宽度（区分可见/隐藏）+ 控件形态
      const nodes = []
      for (const item of await modal.locator('.n-form-item').all()) {
        const label = (await item.locator('.n-form-item-label__text').first().innerText().catch(() => '')).trim()
        if (!label) continue
        const rect = await item.boundingBox().catch(() => null)
        const width = rect ? Math.round(rect.width) : 0
        const hasSelect = (await item.locator('.n-base-selection').count()) > 0
        const hasInput = (await item.locator('input').count()) > 0
        nodes.push({ item, label, width, hasSelect, hasInput })
        entry.labels.push(`${label}:${width}`)
        if (label === WORKER_GROUP_LABEL) entry.hasWorkerGroup = true
      }

      const visible = (node) => node.width >= VISIBLE_MIN_WIDTH
      // 实例 select：共享字段类标签「数据源实例」；SQOOP 标签「数据源」
      const instanceNode =
        nodes.find((node) => node.label === DS_INSTANCE_LABEL && node.hasSelect && visible(node)) ||
        nodes.find((node) => node.label === DS_LEGACY_LABEL && node.hasSelect && visible(node))
      // 类型 select：仅共享字段类有（SQOOP 的类型是「类型」select + 隐藏 input）
      const typeSelectNode = nodes.find((node) => node.label === DS_TYPE_LABEL && node.hasSelect)
      // SQOOP 隐藏类型字段：标签「数据源」+ input + 极窄
      const hiddenTypeNodes = nodes.filter(
        (node) => node.label === DS_LEGACY_LABEL && node.hasInput && !visible(node),
      )

      entry.hasDatasourceField = Boolean(instanceNode)
      if (!instanceNode) {
        await closeNodeModal(modal)
        return entry
      }

      await readSelectOptions(page, frame, modal, instanceNode.item, entry.datasourceInstanceOptions)
      if (typeSelectNode) await readSelectOptions(page, frame, modal, typeSelectNode.item, entry.datasourceTypeOptions)

      // 选中第一个数据源实例 → 类型字段应自动带出该连接的类型
      if (entry.datasourceInstanceOptions.length > 0) {
        await selectFirstOption(page, frame, modal, instanceNode.item)
        await page.waitForTimeout(1200)
        entry.instanceSelected = await instanceNode.item
          .locator('.n-base-selection')
          .first()
          .innerText()
          .catch(() => null)
        if (typeSelectNode) {
          entry.typeAfterSelect = await typeSelectNode.item
            .locator('.n-base-selection')
            .first()
            .innerText()
            .catch(() => null)
        }
        for (const node of hiddenTypeNodes) {
          const value = await node.item.locator('input').first().inputValue().catch(() => '')
          if (value) entry.hiddenTypeValues.push(value)
        }
      }

      // SQOOP：类型字段（sourceMysqlType）是 span=0 的非渲染传输字段，DOM 不可观测。
      // 改用反向过滤证明数据源面板绑定的是 dbx 连接类型：把引擎类型切到 dbx 里
      // 不存在的值，实例下拉应变为空。
      if (taskType === 'SQOOP') {
        const engineNode = nodes.find(
          (node) => node.label === DS_ENGINE_TYPE_LABEL && node.hasSelect && visible(node),
        )
        if (engineNode) {
          const engineOptions = []
          await readSelectOptions(page, frame, modal, engineNode.item, engineOptions)
          entry.engineTypeOptions = engineOptions
          const foreign = engineOptions.find(
            (name) => !result.dbxConnectionTypes.some((type) => String(type).toUpperCase() === name.toUpperCase()),
          )
          if (foreign && (await pickOption(page, frame, modal, engineNode.item, foreign))) {
            entry.foreignType = foreign
            await page.waitForTimeout(800)
            await readSelectOptions(page, frame, modal, instanceNode.item, entry.optionsAfterForeignType)
          }
        }
      }

      await closeNodeModal(modal)
      return entry
    }

    for (const taskType of [...A3_TYPES, ...A4_TYPES]) {
      result.nodeForms.push(await probe(taskType))
    }
    result.dragSupported = result.nodeForms.some((entry) => entry.modalOpened)

    // ---- 断言 ----
    const a3Entries = result.nodeForms.filter((entry) => A3_TYPES.includes(entry.taskType))
    const a4Entries = result.nodeForms.filter((entry) => A4_TYPES.includes(entry.taskType))

    for (const entry of a3Entries) {
      if (!entry.modalOpened) {
        // 侧栏缺失 = 后端未注册该任务类型，不在本脚本能力范围内（单列 skipped）
        if (entry.error && entry.error.startsWith('sidebar item not found')) {
          result.skipped.push(`A3 ${entry.taskType}: ${entry.error}`)
        } else {
          result.failures.push(`A3 ${entry.taskType}: modal not opened (${entry.error || 'unknown'})`)
        }
        continue
      }
      if (!entry.hasDatasourceField) {
        result.failures.push(`A3 ${entry.taskType}: no datasource field`)
        continue
      }
      const fromDbx =
        entry.datasourceInstanceOptions.length > 0 &&
        entry.datasourceInstanceOptions.every((name) => result.dbxConnectionNames.includes(name))
      if (!fromDbx) {
        result.failures.push(
          `A3 ${entry.taskType}: datasource options not from dbx (${JSON.stringify(entry.datasourceInstanceOptions)})`,
        )
      }
      const expectedType = dbxConnections.find((item) => item.name === entry.instanceSelected)?.type
      if (entry.typeAfterSelect !== null || entry.hiddenTypeValues.length > 0) {
        if (entry.instanceSelected && expectedType) {
          const derived = [entry.typeAfterSelect, ...entry.hiddenTypeValues]
            .filter(Boolean)
            .some((value) => value.trim().toUpperCase() === String(expectedType).toUpperCase())
          if (!derived) {
            result.failures.push(
              `A3 ${entry.taskType}: type not derived from selected connection ` +
                `(${JSON.stringify(entry.typeAfterSelect)}/${JSON.stringify(entry.hiddenTypeValues)} != ${expectedType})`,
            )
          }
        }
      } else if (entry.foreignType) {
        // SQOOP 等无「数据源类型」可读字段：以反向过滤证明面板绑定 dbx 连接类型
        if (entry.optionsAfterForeignType.length > 0) {
          result.failures.push(
            `A3 ${entry.taskType}: datasource options not filtered by type ` +
              `(type=${entry.foreignType} 仍有 ${JSON.stringify(entry.optionsAfterForeignType)})`,
          )
        }
      } else {
        result.skipped.push(`A3 ${entry.taskType}: 无可读类型字段且无反向过滤证据`)
      }
    }
    for (const entry of a4Entries) {
      if (!entry.modalOpened) {
        result.failures.push(`A4 ${entry.taskType}: modal not opened (${entry.error || 'unknown'})`)
        continue
      }
      if (!entry.hasWorkerGroup) result.failures.push(`A4 ${entry.taskType}: worker group field missing`)
      if (entry.hasDatasourceField) result.failures.push(`A4 ${entry.taskType}: unexpected datasource field`)
    }

    const shot = require('path').join(require('os').tmpdir(), 'datara-ds-node-form.png')
    await page.screenshot({ path: shot }).catch(() => {})
    result.screenshot = shot

    console.log(JSON.stringify(result))
    if (result.failures.length || result.pageErrors.length) process.exitCode = 1
  } finally {
    await browser.close()
    await api.dispose()
  }
}

/** 关闭节点设置弹窗并等其脱离 DOM：残留遮罩会让后续拖拽超时。 */
async function closeNodeModal(modal) {
  await modal.locator('.btn-cancel').click({ timeout: 5000 }).catch(() => {})
  await modal.waitFor({ state: 'detached', timeout: 8000 }).catch(() => {})
}

/**
 * 收起下拉：点弹窗标题区的空白处（外部点击）。
 *
 * 不能用 Escape —— DS 的 `components/modal` 用 `v-model={[this.show,'show']}` 绑
 * 只读 props，NModal 收到 Escape 后 emit `update:show` → 写 props 抛
 * `TypeError: 'set' on proxy: trap returned falsish for property 'show'`。
 */
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

/** 只读当前可见的下拉面板：naive-ui 会把已关闭的菜单留在 DOM 里，全量查询会串选项。 */
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

/** 在当前可见下拉里按文本选中一项；返回是否点中。 */
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

/** 在当前可见下拉里取第一个选项元素（跳过 naive-ui 残留在 DOM 里的旧菜单）。 */
async function findVisibleOption(frame, text) {
  return frame.evaluateHandle(
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
  ).then((handle) => (handle.asElement() ? handle : null))
}

async function selectFirstOption(page, frame, modal, formItem) {
  const trigger = formItem.locator('.n-base-selection').first()
  await trigger.click({ timeout: 5000 }).catch(() => {})
  await frame.waitForTimeout(600)
  const option = await findVisibleOption(frame)
  if (option) await option.click({ timeout: 5000 }).catch(() => {})
  await frame.waitForTimeout(400)
  await closeDropdown(page, frame, modal)
}

main().catch((error) => {
  console.error(error.stack || error.message)
  process.exitCode = 1
})
