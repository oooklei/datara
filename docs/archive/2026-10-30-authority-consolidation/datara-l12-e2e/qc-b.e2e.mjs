/**
 * L12-02 质量批 B 收口 E2E —— 1.9 隔离环境 http://192.168.1.9:18091
 * 覆盖：POST /projects/{project_id}/quality-rules/{rule_id}/run 行为矩阵
 *   - 正常执行 → 201 + status=succeeded + summary.engine=structural + 四计数 0
 *   - 危险表达式（分号/DDL）→ 201 + status=failed + summary.issues 非空（不执行）
 *   - 规则不存在 → 404
 *   - 规则 disabled → 409
 *   - GET /projects/{project_id}/quality-runs 可查到落库记录
 * 认证：POST /api/v1/rebuild/login（e2e-runner，密码经 env E2E_PASS 运行时注入，禁入本文件/证据）
 * 证据：evidence/qcb-*.json + result.json（无 token 无密码落盘）
 * 纪律：本文件只写不跑（由主控在隔离环境执行）；不修改 package.json。
 */
import { chromium } from 'playwright'
import { mkdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'

const BASE = process.env.E2E_BASE ?? 'http://192.168.1.9:18091'
const USER = process.env.E2E_USER ?? 'e2e-runner'
const PASS = process.env.E2E_PASS ?? ''
const PROJECT_ID = Number(process.env.E2E_PROJECT_ID ?? '23')
const EV = path.resolve('evidence')
mkdirSync(EV, { recursive: true })

const results = []
const httpErrors = []
const pageErrors = []
const rec = (step, ok, detail = '') => {
  results.push({ step, ok, detail })
  console.log(`${ok ? 'PASS' : 'FAIL'} | ${step} | ${detail}`)
}

if (!PASS) {
  console.error('E2E_PASS 未注入，拒绝运行')
  process.exit(2)
}

const GOV = `${BASE}/api/v1/rebuild/governance`
const H = (token) => ({ 'content-type': 'application/json', authorization: `Bearer ${token}` })
const post = async (token, url, body) => {
  const r = await fetch(url, {
    method: 'POST',
    headers: H(token),
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  let j = null
  try { j = await r.json() } catch { /* 非 JSON 响应 */ }
  return { status: r.status, json: j }
}
const get = async (token, url) => {
  const r = await fetch(url, { headers: { authorization: `Bearer ${token}` } })
  let j = null
  try { j = await r.json() } catch { /* 非 JSON 响应 */ }
  return { status: r.status, json: j }
}

const browser = await chromium.launch()
try {
  /* ---- 0. 登录取 token ---- */
  const resp = await fetch(`${BASE}/api/v1/rebuild/login`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ username: USER, password: PASS }),
  })
  const j = await resp.json()
  const token = j?.data?.token ?? ''
  rec('auth.login', resp.ok && j?.code === 0 && token.length > 0, `code=${j?.code} token_len=${token.length}`)
  if (!token) throw new Error('login 失败，中止')

  const ctx = await browser.newContext({ viewport: { width: 1680, height: 950 } })
  await ctx.route('**/api/**', (route) => {
    const h = { ...route.request().headers(), authorization: `Bearer ${token}` }
    return route.continue({ headers: h })
  })
  await ctx.addInitScript(([t]) => localStorage.setItem('datara_token', t), [token])
  const page = await ctx.newPage()
  page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)))
  page.on('response', (r) => {
    if (r.status() >= 400) httpErrors.push(`${r.request().method()} ${r.url().slice(BASE.length)} -> ${r.status()}`)
  })

  /* ---- B1 准备：创建正常规则 + 危险表达式规则 + 停用规则 ---- */
  const suffix = Date.now()
  const mkRule = async (expression, enabled) => {
    const { status, json } = await post(token, `${GOV}/projects/${PROJECT_ID}/quality-rules`, {
      asset_id: 1,
      name: `E2E-QCB-${suffix}`,
      expression,
      severity: 'error',
      enabled,
    })
    return { status, json, id: json?.data?.id ?? null }
  }

  const normal = await mkRule('id IS NOT NULL', true)
  rec('B1.create_normal_rule', normal.status === 201 && normal.json?.code === 0 && normal.id !== null,
    `HTTP ${normal.status} code=${normal.json?.code} id=${normal.id}`)

  const dangerous = await mkRule('1=1; DROP TABLE t', true)
  rec('B1.create_dangerous_rule', dangerous.status === 201 && dangerous.id !== null,
    `HTTP ${dangerous.status} id=${dangerous.id}`)

  const disabled = await mkRule('id IS NOT NULL', false)
  rec('B1.create_disabled_rule', disabled.status === 201 && disabled.id !== null,
    `HTTP ${disabled.status} id=${disabled.id}`)

  /* ---- B2 正常执行 → 201 + succeeded + structural + 四计数 0 ---- */
  const runOk = await post(token, `${GOV}/projects/${PROJECT_ID}/quality-rules/${normal.id}/run`, undefined)
  const dOk = runOk.json?.data ?? {}
  const countsOk = dOk.checkedRows === 0 && dOk.successRows === 0 && dOk.failedRows === 0 && dOk.skippedRows === 0
  rec('B2.run_succeeded', runOk.status === 201 && runOk.json?.code === 0 && dOk.status === 'succeeded'
    && dOk.ruleId === normal.id && dOk.summary?.engine === 'structural' && countsOk,
    `HTTP ${runOk.status} status=${dOk.status} engine=${dOk.summary?.engine} counts=0?${countsOk}`)

  /* ---- B3 危险表达式 → 201 + failed + issues 非空（不执行） ---- */
  const runBad = await post(token, `${GOV}/projects/${PROJECT_ID}/quality-rules/${dangerous.id}/run`, undefined)
  const dBad = runBad.json?.data ?? {}
  const issues = Array.isArray(dBad.summary?.issues) ? dBad.summary.issues : []
  rec('B3.run_forbidden_failed', runBad.status === 201 && runBad.json?.code === 0 && dBad.status === 'failed' && issues.length > 0,
    `HTTP ${runBad.status} status=${dBad.status} issues=${issues.length}`)

  /* ---- B4 规则不存在 → 404 ---- */
  const runMissing = await post(token, `${GOV}/projects/${PROJECT_ID}/quality-rules/99999999/run`, undefined)
  rec('B4.run_missing_404', runMissing.status === 404, `HTTP ${runMissing.status}`)

  /* ---- B5 规则停用 → 409 ---- */
  const runDisabled = await post(token, `${GOV}/projects/${PROJECT_ID}/quality-rules/${disabled.id}/run`, undefined)
  rec('B5.run_disabled_409', runDisabled.status === 409, `HTTP ${runDisabled.status}`)

  /* ---- B6 GET quality-runs 可查到落库记录 ---- */
  const runs = await get(token, `${GOV}/projects/${PROJECT_ID}/quality-runs?page=1&page_size=50`)
  const list = runs.json?.data?.list ?? runs.json?.data?.items ?? []
  const foundOk = list.some((r) => r.rule_id === normal.id && r.status === 'succeeded')
  const foundBad = list.some((r) => r.rule_id === dangerous.id && r.status === 'failed')
  rec('B6.list_runs_persisted', runs.status === 200 && foundOk && foundBad,
    `HTTP ${runs.status} total=${runs.json?.data?.total} ok=${foundOk} bad=${foundBad}`)

  writeFileSync(path.join(EV, 'qcb-run-matrix.json'), JSON.stringify({
    at: new Date().toISOString(),
    normalRuleId: normal.id,
    dangerousRuleId: dangerous.id,
    disabledRuleId: disabled.id,
    runOk: { status: runOk.status, body: runOk.json },
    runBad: { status: runBad.status, body: runBad.json },
    runMissing: { status: runMissing.status, body: runMissing.json },
    runDisabled: { status: runDisabled.status, body: runDisabled.json },
    runs: { status: runs.status, total: runs.json?.data?.total },
  }, null, 2), 'utf-8')
} catch (e) {
  rec('fatal', false, String(e).slice(0, 300))
} finally {
  await browser.close()
}

const meta = {
  base: BASE,
  projectId: PROJECT_ID,
  at: new Date().toISOString(),
  results,
  httpErrors: httpErrors.slice(0, 20),
  pageErrors: pageErrors.slice(0, 20),
}
writeFileSync(path.join(EV, 'result.json'), JSON.stringify(meta, null, 2), 'utf-8')
const passCount = results.filter((r) => r.ok).length
console.log(`SUMMARY ${passCount}/${results.length} PASS`)
process.exit(results.length > 0 && results.every((r) => r.ok) ? 0 : 1)
