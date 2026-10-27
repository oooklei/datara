/**
 * IMPL-v4-03 票面 v1.1 · 增补件 2：质量规则 E2E 全闭环（RT-IMPL-V4-07 前置用例）。
 *
 * 闭环：路由承载（项目上下文）→ 无项目选择器兜底 → 新建规则 → 重名保护（后端 4091）
 *       → 执行规则（structural 口径回显）→ structural 红线直证（行级四字段恒 0）→ 跳运行记录。
 *
 * 运行宿主：**192.168.1.9**（本机禁跑任何可执行验证；见 TEST-ENVIRONMENT-POLICY）。
 * 前置：1.9 部署栈含 `/api/v1/rebuild/governance` 路由（`rebuild/governance/api.py`）、
 *       `/api/v1/rebuild/projects` 与登录端点；且**至少存在一个项目**（用于规则挂靠）。
 *
 * 鉴权：POST /api/v1/rebuild/login 换 token → addInitScript 注入 localStorage（document-start），
 *       值不落盘；另经 route 层补写 `Authorization: Bearer`（双通道词形失配兜底）。
 *
 * 视图锚点口径：本页走布尔 `data-*` 属性（`[data-create]` / `[data-rule-id]` / `[data-run]` …），
 *   按 `QualityRuleView.vue` 原样取用。
 *
 * structural 语义红线（验收 ④，`governanceApi.QUALITY_STRUCTURAL_ONLY`）：run 端点只做**结构谓词校验**，
 *   `checked_rows/success_rows/failed_rows/skipped_rows` **恒 0**，`summary.engine` 恒 `"structural"`；
 *   前端不得把四字段渲染成真实行级结果。本件以「UI 回显 + 后端直证」双侧坐实该红线。
 *
 * 隔离与并发（支撑 1.9 双线并行，Ops 指令）：本件**不依赖任何全局计数**、不复用固定名，
 *   规则名以 `Date.now()` 后缀自命名，断言仅作用于本件自建行 → 与 `sshNode.spec.ts`（RT-02a）并行无互扰。
 *
 * 证据：PNG 截图 + `e2e/evidence/qc.evidence.json` 成对落档（验收 v4 A3）。
 */
import { expect, test as base, type Page } from '@playwright/test'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const BASE = process.env.E2E_BASE ?? 'http://192.168.1.9:18091'
const USER = process.env.E2E_USER ?? 'e2e-runner'
const PASS = process.env.E2E_PASS ?? ''

const EV_DIR = path.resolve('e2e', 'evidence')
mkdirSync(EV_DIR, { recursive: true })

const evidence: {
  ticket: string
  businessKey: string
  revision: string
  host: string
  base_url: string
  executed_at: string
  route: string
  project_id: number
  steps: Array<{ name: string; ok: boolean; detail: string }>
  screenshots: string[]
  unverified: string[]
} = {
  ticket: 'IMPL-v4-03',
  businessKey: 'IMPL-v4-03:impl:v1.1',
  revision: 'v1.1',
  host: '192.168.1.9',
  base_url: BASE,
  executed_at: new Date().toISOString(),
  route: '/qc/rule',
  project_id: 0,
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

type AuthFixtures = { qcToken: string; qcPage: Page }

const test = base.extend<AuthFixtures>({
  qcToken: async ({}, use) => {
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

  qcPage: async ({ browser, qcToken }, use) => {
    const ctx = await browser.newContext({ viewport: { width: 1680, height: 950 } })
    // token 注入走 addInitScript（document-start，规避首轮导航竞态）；值不落盘
    await ctx.addInitScript(([tk]) => globalThis.localStorage.setItem('datara_token', tk), [qcToken])
    await ctx.route('**/api/**', (route) =>
      route.continue({ headers: { ...route.request().headers(), authorization: `Bearer ${qcToken}` } }),
    )
    const page = await ctx.newPage()
    await use(page)
    await ctx.close()
  },
})

/* ---------------- 路由 + 项目上下文前置 ----------------
 * `/qc/rule` 为全局模式路由（项目上下文经 route params/query 承接）。本件取用既有项目：
 * 优先 `E2E_PROJECT_ID`，否则经 `/api/v1/rebuild/projects` 取首个。无项目即整组 skip（环境闸）。
 */
let routeReady = false
let projectId = Number(process.env.E2E_PROJECT_ID ?? 0) || 0
let probeNote = ''

test.beforeAll(async ({ browser, qcToken }) => {
  const ctx = await browser.newContext()
  await ctx.addInitScript(([tk]) => globalThis.localStorage.setItem('datara_token', tk), [qcToken])
  await ctx.route('**/api/**', (route) =>
    route.continue({ headers: { ...route.request().headers(), authorization: `Bearer ${qcToken}` } }),
  )
  const probe = await ctx.newPage()
  try {
    await probe.goto('/qc/rule', { waitUntil: 'domcontentloaded' })
    const hit = await probe.waitForSelector('[data-structural-note]', { timeout: 8000 }).catch(() => null)
    routeReady = hit !== null
    if (routeReady && projectId === 0) {
      const res = await fetch(`${BASE}/api/v1/rebuild/projects`, {
        headers: { authorization: `Bearer ${qcToken}`, token: qcToken },
      })
      const body = (await res.json().catch(() => null)) as { data?: { list?: Array<{ id?: number }> } } | null
      projectId = Number(body?.data?.list?.[0]?.id ?? 0)
    }
    probeNote = !routeReady
      ? `路由未承载（落点 url=${probe.url()}，标题=${await probe.title()}）——1.9 制品须含 /qc/rule 与 governance 后端域`
      : projectId === 0
        ? '无可用项目（/api/v1/rebuild/projects 为空）——须先建项目'
        : `ok（projectId=${projectId}）`
  } finally {
    await ctx.close()
  }
  if (!routeReady || projectId === 0) test.skip(true, `环境闸：${probeNote}`)
})

/* ---------------- 闭环用例 ---------------- */

test.describe.serial('质量规则闭环（IMPL-v4-03 v1.1 / RT-07 前置）', () => {
  const suffix = `${Date.now()}`
  const ruleName = `e2e-qc-rule-${suffix}`
  const ruleId = { value: 0 }
  const assetId = Number(process.env.E2E_QC_ASSET_ID ?? 1)
  const expression = `column_count > 0 /* e2e-${suffix} */`

  test('01 路由承载：/qc/rule 渲染质量规则页 + structural 口径注记', async ({ qcPage: page }) => {
    await page.goto(`/qc/rule?projectId=${projectId}`)
    await expect(page.getByRole('heading', { name: '质量规则' })).toBeVisible()
    await expect(page.locator('[data-structural-note]')).toContainText('structural')
    await expect(page.locator('[data-create]')).toBeEnabled()
    await shot(page, 'q1_route_list')
    record('01.route', true, `页面渲染 + structural 注记 + 新建入口可用（projectId=${projectId}）`)
  })

  test('02 无项目兜底：未带项目上下文呈现选择器而非空壳', async ({ qcPage: page }) => {
    await page.goto('/qc/rule')
    await expect(page.locator('[data-no-project]')).toBeVisible({ timeout: 15_000 })
    await expect(page.locator('[data-create]')).toBeDisabled()
    await shot(page, 'q2_no_project')
    record('02.no_project', true, '无项目上下文 → 选择器兜底，不渲染空壳')
  })

  test('03 新建：创建质量规则（POST /projects/{id}/quality-rules，201）', async ({ qcPage: page }) => {
    await page.goto(`/qc/rule?projectId=${projectId}`)
    await page.click('[data-create]')
    await expect(page.getByRole('dialog', { name: '新建质量规则' })).toBeVisible()

    await page.fill('[data-name]', ruleName)
    await page.fill('[data-asset-input]', String(assetId))
    await page.fill('[data-expr-input]', expression)
    await page.selectOption('[data-severity-select]', 'warning')
    await shot(page, 'q3a_form_filled')

    await page.click('[data-save]')
    await expect(page.getByRole('dialog', { name: '新建质量规则' })).toBeHidden({ timeout: 15_000 })

    const row = page.locator('tr[data-rule-id]', { hasText: ruleName })
    await expect(row).toBeVisible({ timeout: 15_000 })
    ruleId.value = Number(await row.getAttribute('data-rule-id'))
    expect(ruleId.value).toBeGreaterThan(0)
    await expect(row.locator('[data-severity]')).toHaveText('警告')
    await shot(page, 'q3b_created')
    record('03.create', true, `name=${ruleName} id=${ruleId.value} assetId=${assetId}`)
  })

  test('04 重名保护：同项目同名创建被拒（后端 4091 duplicateName）', async ({ qcPage: page }) => {
    // 前端路径：表单提交后不新增本名行，错误横幅出现
    await page.goto(`/qc/rule?projectId=${projectId}`)
    await page.click('[data-create]')
    await page.fill('[data-name]', ruleName)
    await page.fill('[data-asset-input]', String(assetId))
    await page.fill('[data-expr-input]', expression)
    await page.click('[data-save]')
    await expect(page.getByRole('dialog', { name: '新建质量规则' })).toBeVisible() // 失败不清场
    await expect(page.locator('[data-error]')).toBeVisible({ timeout: 15_000 })

    // 后端契约直证：同源 fetch 直连，坐实 4091
    const dup = await page.evaluate(
      async ({ base, pid, name, aid, expr }) => {
        const tk = globalThis.localStorage.getItem('datara_token') ?? ''
        const res = await fetch(`${base}/api/v1/rebuild/governance/projects/${pid}/quality-rules`, {
          method: 'POST',
          headers: { 'content-type': 'application/json', token: tk },
          body: JSON.stringify({ asset_id: aid, name, expression: expr, severity: 'warning', enabled: true }),
        })
        const body = (await res.json().catch(() => ({}))) as { code?: number }
        return { status: res.status, code: body.code }
      },
      { base: BASE, pid: projectId, name: ruleName, aid: assetId, expr: expression },
    )
    expect(dup.code).toBe(4091)
    await shot(page, 'q4_duplicate_guard')
    record('04.duplicate_guard', true, `前端错误横幅 + 后端 POST → ${dup.status}/${dup.code}`)
  })

  test('05 执行规则：structural 口径回显（POST /{ruleId}/run，201）', async ({ qcPage: page }) => {
    await page.goto(`/qc/rule?projectId=${projectId}`)
    const row = page.locator(`tr[data-rule-id="${ruleId.value}"]`)
    await row.locator('[data-run]').click()

    const result = page.locator('[data-run-result]')
    await expect(result).toBeVisible({ timeout: 40_000 })
    // 回显模板含 structural 引擎标识与「行级四字段恒 0」口径；不渲染行级结论
    await expect(result).toContainText('structural')
    await expect(result).toContainText('行级四字段恒 0')
    await shot(page, 'q5_run_result')
    record('05.run', true, `执行回显：${(await result.innerText()).slice(0, 160)}`)
  })

  test('06 structural 红线直证：行级四字段恒 0 且 engine 恒 structural', async ({ qcPage: page }) => {
    const run = await page.evaluate(
      async ({ base, pid, rid }) => {
        const tk = globalThis.localStorage.getItem('datara_token') ?? ''
        const res = await fetch(`${base}/api/v1/rebuild/governance/projects/${pid}/quality-rules/${rid}/run`, {
          method: 'POST',
          headers: { token: tk },
        })
        const body = (await res.json().catch(() => ({}))) as {
          code?: number
          data?: {
            status?: string
            checked_rows?: number
            success_rows?: number
            failed_rows?: number
            skipped_rows?: number
            summary?: { engine?: string; message?: string }
          }
        }
        return { status: res.status, code: body.code, data: body.data }
      },
      { base: BASE, pid: projectId, rid: ruleId.value },
    )
    expect(run.code).toBe(0)
    expect(run.data?.checked_rows).toBe(0)
    expect(run.data?.success_rows).toBe(0)
    expect(run.data?.failed_rows).toBe(0)
    expect(run.data?.skipped_rows).toBe(0)
    expect(run.data?.summary?.engine).toBe('structural')
    await shot(page, 'q6_structural_proof')
    record('06.structural_redline', true, `四字段恒 0 + engine=structural（status=${run.data?.status}）`)
  })

  test('07 跳运行记录：/qc/task 携带 projectId 上下文', async ({ qcPage: page }) => {
    await page.goto(`/qc/rule?projectId=${projectId}`)
    const row = page.locator(`tr[data-rule-id="${ruleId.value}"]`)
    await row.locator('[data-goto-runs]').click()
    await expect(page).toHaveURL(new RegExp(`/qc/task\\?projectId=${projectId}`))
    await shot(page, 'q7_goto_runs')
    record('07.goto_runs', true, `跳转 ${page.url()}`)
  })
})

/* ---------------- 证据落档（v4 A3 成对） ---------------- */

test.afterAll(() => {
  evidence.project_id = projectId
  evidence.unverified = [
    '本机零执行：本文件为交付物，全部断言须在 192.168.1.9 执行方成立（TEST-ENVIRONMENT-POLICY）',
    '依赖 1.9 至少存在一个项目；无项目时前置探测失败整组 skip，属环境闸非代码缺陷',
    '规则挂靠的 assetId 缺省取 1（可经 E2E_QC_ASSET_ID 覆盖）；后端是否校验资产归属由本票外增量承接',
    '本件为 RT-IMPL-V4-07 的 1.9 实跑前置，不构成 07 验收通过证据',
  ]
  writeFileSync(path.join(EV_DIR, 'qc.evidence.json'), JSON.stringify(evidence, null, 2), 'utf-8')
  console.log(`evidence → ${path.join(EV_DIR, 'qc.evidence.json')}`)
})
