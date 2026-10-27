/**
 * 增量 15.6 / LLM-01-FE 节点 B：LLM 模型配置页 E2E 全闭环（权威设计 §5E.1 六件套）。
 *
 * 闭环：配置（新建）→ 测试（连通性，elapsed_ms）→ 设默认 → 删除保护（前端禁用 + 后端 409）→ 掩码回显。
 *
 * 运行宿主：**192.168.1.9**（本机禁跑任何可执行验证；见 TEST-ENVIRONMENT-POLICY）。
 * 前置：1.9 部署栈含本票节点 A 产物构建版本 + rebuild 后端基线，且已注入 LLM_ENCRYPTION_KEY
 *       使 `/api/v1/rebuild/llm-models` 路由挂载（S6：key 禁入静态产物/URL/证据文件）。
 *
 * 鉴权：POST /api/v1/rebuild/login 换 token → addInitScript 注入 localStorage（document-start），
 *       值不落盘；另经 route 层补写 `Authorization: Bearer`（沿用 datara-l12-e2e 既有工装，
 *       应对后端部分域仅认 Bearer 的词形失配）。
 *
 * 连通性测试口径（票面 stop_rules 明示）：**不得**依赖真实 LLM provider 凭据（D4 人工门）。
 *   默认走 `E2E_LLM_PROBE_BASE`（缺省 https://127.0.0.1:9/v1，不可路由）→ 断言**结构化失败**路径
 *   （后端 502/5021 → 页面展示 detail）；若注入 `E2E_LLM_TEST_BASE` + `E2E_LLM_TEST_KEY`
 *   （1.9 可达的 OpenAI 兼容测试端点，D4 放行后），则断言**成功**路径（elapsed_ms + reply）。
 *
 * 证据：PNG 截图 + `e2e/evidence/llm-models.evidence.json` 成对落档（验收 v4 A3）。
 */
import { expect, test as base, type Page } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const BASE = process.env.E2E_BASE ?? 'http://192.168.1.9:18091'
const USER = process.env.E2E_USER ?? 'e2e-runner'
const PASS = process.env.E2E_PASS ?? ''

/** 连通性测试端点：缺省为不可路由地址（无需任何凭据，走失败路径）。 */
const PROBE_BASE = process.env.E2E_LLM_PROBE_BASE ?? 'https://127.0.0.1:9/v1'
const REAL_TEST_BASE = process.env.E2E_LLM_TEST_BASE ?? ''
const REAL_TEST_KEY = process.env.E2E_LLM_TEST_KEY ?? ''

const EV_DIR = path.resolve('e2e', 'evidence')
mkdirSync(EV_DIR, { recursive: true })

/** 视图锚点统一走 `data-test`（本页约定，见 LlmModelsView.vue）。 */
const t = (name: string): string => `[data-test="${name}"]`

const evidence: {
  ticket: string
  businessKey: string
  revision: string
  host: string
  base_url: string
  executed_at: string
  route: string
  connectivity_mode: string
  steps: Array<{ name: string; ok: boolean; detail: string }>
  screenshots: string[]
  unverified: string[]
} = {
  ticket: 'LLM-01-FE',
  businessKey: 'LLM-01-FE:impl:R1',
  revision: 'R1',
  host: '192.168.1.9',
  base_url: BASE,
  executed_at: new Date().toISOString(),
  route: '/system/llm-models',
  connectivity_mode: REAL_TEST_BASE ? 'success-path(real-test-endpoint)' : 'failure-path(unroutable-probe-base)',
  steps: [],
  screenshots: [],
  unverified: [],
}

function record(name: string, ok: boolean, detail = ''): void {
  evidence.steps.push({ name, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} | ${name} | ${detail}`)
}

async function shot(page: Page, name: string): Promise<void> {
  const file = `${name}.png`
  await page.screenshot({ path: path.join(EV_DIR, file), fullPage: true })
  evidence.screenshots.push(file)
}

/* ---------------- 鉴权 fixture ---------------- */

type AuthFixtures = { llmToken: string; llmPage: Page }

const test = base.extend<AuthFixtures>({
  llmToken: async ({}, use) => {
    if (!PASS) throw new Error('E2E_PASS 未注入：拒绝运行（密码禁入代码库/证据——红线 8 / S6）')
    const res = await fetch(`${BASE}/api/v1/rebuild/login`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ username: USER, password: PASS }),
    })
    const body = (await res.json().catch(() => null)) as { code?: number; data?: { token?: string } } | null
    const token = body?.data?.token ?? ''
    if (!res.ok || body?.code !== 0 || !token) {
      throw new Error(`login 失败：status=${res.status} code=${body?.code ?? '-'}`)
    }
    await use(token)
  },

  llmPage: async ({ browser, llmToken }, use) => {
    const ctx = await browser.newContext({ viewport: { width: 1680, height: 950 } })
    // token 注入走 addInitScript（document-start，规避首轮导航竞态）；值不落盘
    await ctx.addInitScript(([tk]) => globalThis.localStorage.setItem('datara_token', tk), [llmToken])
    await ctx.route('**/api/**', (route) =>
      route.continue({ headers: { ...route.request().headers(), authorization: `Bearer ${llmToken}` } }),
    )
    const page = await ctx.newPage()
    await use(page)
    await ctx.close()
  },
})

/** Element Plus 二次确认弹窗（§5E.1#6）。 */
async function confirmMessageBox(page: Page, label: string): Promise<void> {
  const box = page.locator('.el-message-box')
  await box.waitFor({ state: 'visible', timeout: 15_000 })
  await box.getByRole('button', { name: label, exact: true }).click()
}

/* ---------------- 路由可达性前置 ----------------
 * R1 `allowed_paths` 禁 `src/router/routes.ts`，菜单与路由登记由 **R2 票**承接
 * （票面 stop_rules 明示）。故本页在 R1 窗口内**尚无注册路由**，E2E 为环境闸而非代码缺陷：
 * 前置探测失败即整组 skip 并留明原因，路由落位后本文件**无需改动**自动转 GREEN。
 */
let routeReady = false
let routeProbeNote = ''

test.beforeAll(async ({ browser, llmToken }) => {
  const ctx = await browser.newContext()
  await ctx.addInitScript(([tk]) => globalThis.localStorage.setItem('datara_token', tk), [llmToken])
  await ctx.route('**/api/**', (route) =>
    route.continue({ headers: { ...route.request().headers(), authorization: `Bearer ${llmToken}` } }),
  )
  const probe = await ctx.newPage()
  try {
    await probe.goto('/system/llm-models', { waitUntil: 'domcontentloaded' })
    const hit = await probe.waitForSelector(t('llm-page'), { timeout: 8000 }).catch(() => null)
    routeReady = hit !== null
    routeProbeNote = routeReady
      ? 'ok'
      : `路由未承载（落点 url=${probe.url()}，标题=${await probe.title()}）——R1 禁改 routes.ts，路由与菜单登记由 R2 票承接`
  } finally {
    await ctx.close()
  }
  if (!routeReady) test.skip(true, `R1 环境闸：${routeProbeNote}`)
})

/* ---------------- 闭环用例 ---------------- */

test.describe.serial('15.6 LLM 模型配置闭环（§5E.1 六件套）', () => {
  const suffix = `${Date.now()}`
  const primaryName = `e2e-llm-primary-${suffix}`
  const secondaryName = `e2e-llm-secondary-${suffix}`
  /** 实际写入的 api_key：D4 放行真实测试端点时用注入 key，否则用本地伪 key（仅入库密文，不出网）。 */
  const primaryKeyValue = REAL_TEST_KEY || 'sk-datara-e2e-primary-9911'
  const primaryApiBase = REAL_TEST_BASE || PROBE_BASE
  const primaryId = { value: 0 }
  const secondaryId = { value: 0 }

  test('01 路由承载：/system/llm-models 渲染 LLM 模型配置页', async ({ llmPage: page }) => {
    await page.goto('/system/llm-models')
    await expect(page.locator(t('llm-page'))).toBeVisible()
    await expect(page.getByRole('heading', { name: 'LLM 模型配置' })).toBeVisible()
    await expect(page.locator(t('llm-create'))).toBeEnabled()
    await shot(page, 'n1_route_list')
    record('01.route', true, '页面渲染 + 新建入口可用')
  })

  test('02 配置：新建 LLM 模型（六端点之 POST）', async ({ llmPage: page }) => {
    await page.goto('/system/llm-models')
    await page.click(t('llm-create'))
    await expect(page.locator(t('llm-form-dialog'))).toBeVisible()

    await page.fill(t('llm-form-name'), primaryName)
    await page.fill(t('llm-form-display-name'), 'E2E 主模型')
    await page.selectOption(t('llm-form-provider'), 'siliconflow')
    await page.fill(t('llm-form-api-base'), primaryApiBase)
    await page.fill(t('llm-form-model-id'), 'e2e-probe-model')
    await page.fill(t('llm-form-api-key'), primaryKeyValue)
    await page.fill(t('llm-form-max-tokens'), '10000')
    await page.fill(t('llm-form-temperature'), '0.7')
    await shot(page, 'n2a_form_filled')

    await page.click(t('llm-form-save'))
    await expect(page.locator(t('llm-form-dialog'))).toBeHidden()

    const row = page.locator(`[data-test="llm-row"][data-llm-name="${primaryName}"]`)
    await expect(row).toBeVisible({ timeout: 15_000 })
    primaryId.value = Number(await row.getAttribute('data-llm-id'))
    expect(primaryId.value).toBeGreaterThan(0)
    await shot(page, 'n2b_created')
    record('02.create', true, `name=${primaryName} id=${primaryId.value}`)
  })

  test('03 掩码回显：列表仅尾 4 位可见，完整 key 零泄露（红线 8）', async ({ llmPage: page }) => {
    const row = page.locator(`[data-test="llm-row"][data-llm-name="${primaryName}"]`)
    await expect(row).toBeVisible()
    const cell = row.locator(t('llm-api-key'))
    const masked = (await cell.innerText()).trim()
    const last4 = primaryKeyValue.slice(-4)

    // 后端 mask_api_key（rebuild/llm/crypto.py）：≤8 全掩码；否则 "*"*min(8, len-4) + 尾 4 位
    if (primaryKeyValue.length <= 8) {
      expect(masked).toMatch(/^\*+$/)
    } else {
      expect(masked).toBe(`${'*'.repeat(Math.min(8, primaryKeyValue.length - 4))}${last4}`)
    }
    expect(masked).not.toContain(primaryKeyValue)
    expect(masked).not.toContain(primaryKeyValue.slice(0, -4))

    // 整页零泄露：完整 key 不得出现在任何渲染文本中
    const bodyText = await page.locator('body').innerText()
    expect(bodyText).not.toContain(primaryKeyValue)
    await shot(page, 'n3_masked')
    record('03.mask', true, `列表回显="${masked}"，完整 key 未出现`)
  })

  test('04 连通性测试：POST /{id}/test 结果回显（elapsed_ms 或 detail）', async ({ llmPage: page }) => {
    const row = page.locator(`[data-test="llm-row"][data-llm-name="${primaryName}"]`)
    await row.locator(t('llm-test')).click()

    const result = page.locator(t(`llm-test-result-${primaryId.value}`))
    await expect(result).toBeVisible({ timeout: 40_000 })

    if (REAL_TEST_BASE) {
      await expect(result).toContainText('连通性测试通过')
      await expect(result).toContainText('ms')
      await expect(result).toContainText('模型返回')
      record('04.test', true, `成功路径：${(await result.innerText()).slice(0, 120)}`)
    } else {
      // 不可路由端点 → 后端 502/5021 → 页面失败分支 + detail
      await expect(result).toContainText('连通性测试失败')
      await expect(result).toContainText('5021')
      record('04.test', true, `失败路径（无需真实凭据）：${(await result.innerText()).slice(0, 120)}`)
    }
    await shot(page, 'n4_test_result')
  })

  test('05 设默认：PUT /{id}/default，默认 tag 落位且按钮转禁用', async ({ llmPage: page }) => {
    const row = page.locator(`[data-test="llm-row"][data-llm-name="${primaryName}"]`)
    await row.locator(t('llm-set-default')).click()
    await expect(row.locator(t('llm-default-tag'))).toHaveText('默认', { timeout: 15_000 })

    // 后端清全表既有默认位 → 页面整表刷新后，本行「设默认」「删除」双禁用（§5E.3 前端双保险）
    await expect(row.locator(t('llm-set-default'))).toBeDisabled()
    await expect(row.locator(t('llm-delete'))).toBeDisabled()
    await shot(page, 'n5_default')
    record('05.set_default', true, `id=${primaryId.value} 默认 tag 落位 + 双按钮禁用`)
  })

  test('06 删除保护：默认模型禁删（前端禁用 + 后端 409/4092 兜底）', async ({ llmPage: page }) => {
    const row = page.locator(`[data-test="llm-row"][data-llm-name="${primaryName}"]`)
    await expect(row.locator(t('llm-delete'))).toBeDisabled()

    // 后端 409 兜底直证：前端按钮已禁用，此处经页面同源 fetch 直连后端坐实后端契约
    // （repository.delete 对默认模型抛 ValueError → api.py L116 → 409/4092）
    const conflict = await page.evaluate(
      async (id) => {
        const tk = globalThis.localStorage.getItem('datara_token') ?? ''
        const res = await fetch(`/api/v1/rebuild/llm-models/${id}`, {
          method: 'DELETE',
          headers: { token: tk },
        })
        const body = (await res.json().catch(() => ({}))) as { code?: number }
        return { status: res.status, code: body.code }
      },
      primaryId.value,
    )
    expect(conflict.status).toBe(409)
    expect(conflict.code).toBe(4092)
    await shot(page, 'n6_delete_guard')
    record('06.delete_guard', true, `前端禁用 + 后端 DELETE → ${conflict.status}/${conflict.code}`)
  })

  test('07 删除：非默认模型二次确认后删除（DELETE 200）', async ({ llmPage: page }) => {
    // 造一条非默认模型
    await page.click(t('llm-create'))
    await page.fill(t('llm-form-name'), secondaryName)
    await page.fill(t('llm-form-display-name'), 'E2E 次模型')
    await page.selectOption(t('llm-form-provider'), 'volcengine')
    await page.fill(t('llm-form-api-base'), primaryApiBase)
    await page.fill(t('llm-form-model-id'), 'e2e-probe-model-2')
    await page.fill(t('llm-form-api-key'), 'sk-datara-e2e-secondary-8822')
    await page.click(t('llm-form-save'))

    const row = page.locator(`[data-test="llm-row"][data-llm-name="${secondaryName}"]`)
    await expect(row).toBeVisible({ timeout: 15_000 })
    secondaryId.value = Number(await row.getAttribute('data-llm-id'))
    expect(secondaryId.value).toBeGreaterThan(0)

    // 非默认行删除按钮可用
    await expect(row.locator(t('llm-delete'))).toBeEnabled()
    await row.locator(t('llm-delete')).click()
    await confirmMessageBox(page, '删除')

    await expect(row).toBeHidden({ timeout: 15_000 })
    await shot(page, 'n7_deleted')
    record('07.delete', true, `name=${secondaryName} id=${secondaryId.value} 二次确认后删除`)
  })
})

/* ---------------- 证据落档（v4 A3 成对） ---------------- */

test.afterAll(() => {
  evidence.unverified = [
    '本机零执行：本文件为交付物，全部断言须在 192.168.1.9 执行方成立（TEST-ENVIRONMENT-POLICY）',
    REAL_TEST_BASE
      ? '连通性测试走真实测试端点（D4 放行）'
      : '连通性测试缺省走不可路由端点（失败路径）；成功路径需 D4 放行后注入 E2E_LLM_TEST_BASE/KEY',
    'R1 窗口内 /system/llm-models 尚无注册路由（routes.ts 禁改，R2 票承接）——前置探测失败时整组 skip',
  ]
  writeFileSync(
    path.join(EV_DIR, 'llm-models.evidence.json'),
    JSON.stringify(evidence, null, 2),
    'utf-8',
  )
  console.log(`evidence → ${path.join(EV_DIR, 'llm-models.evidence.json')}`)
})
