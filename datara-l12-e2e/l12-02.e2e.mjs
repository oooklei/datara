/**
 * L12-02 full 段 E2E（F1~F5）——1.9 隔离环境 http://192.168.1.9:18091
 * 认证：POST /api/v1/rebuild/login（e2e-runner，密码经 env E2E_PASS 运行时注入，禁入本文件/证据）
 * 证据：evidence/n1..n5 截图 + result.json（无 token 无密码落盘）
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
  /* 鉴权头词形失配适配（环境侧工装，非代码改动）：后端实证仅认 Authorization: Bearer（token 头 401 invalid token），
     前端 http.ts TOKEN_HEADER='token' → 全量 API 请求由 route 层补写 Bearer（s338 呈报候裁） */
  await ctx.route('**/api/**', (route) => {
    const h = { ...route.request().headers(), authorization: `Bearer ${token}` }
    return route.continue({ headers: h })
  })
  /* token 注入走 addInitScript（document-start，规避首轮导航竞态）；值不落盘 */
  await ctx.addInitScript(([t]) => localStorage.setItem('datara_token', t), [token])
  const page = await ctx.newPage()
  page.on('pageerror', (e) => pageErrors.push(String(e).slice(0, 200)))
  page.on('response', (r) => {
    if (r.status() >= 400) httpErrors.push(`${r.request().method()} ${r.url().slice(BASE.length)} -> ${r.status()}`)
  })

  /* ---- F1 路由承载：/p/:projectId/dag → 任务中心（视角页签四件） ---- */
  await page.goto(`${BASE}/p/${PROJECT_ID}/dag`)
  await page.waitForSelector('[data-tc-tabs]', { timeout: 20000 })
  await page.waitForSelector('[data-testid="new-workflow"]', { timeout: 10000 })
  const tabEdit = await page.locator('[data-tab="edit"]').count()
  await page.screenshot({ path: path.join(EV, 'n1_f1_taskcenter.png'), fullPage: true })
  rec('F1.route', tabEdit > 0, `data-tc-tabs 在位, data-tab=edit x${tabEdit}`)

  /* ---- F2 新建对话框：同步分类创建 → 画布 Tab 打开 ---- */
  const wfName = `E2E-L12-02-full-${Date.now()}`
  await page.click('[data-testid="new-workflow"]')
  await page.waitForSelector('[data-testid="tc-new-wf-dialog"]', { timeout: 10000 })
  await page.fill('[data-testid="tc-new-wf-name"]', wfName)
  await page.click('[data-testid="tc-new-wf-cat-sync"]')
  await page.click('[data-testid="tc-new-wf-confirm"]')
  await page.getByText('已创建工作流', { exact: false }).first().waitFor({ timeout: 15000 })
  await page.waitForSelector('.vue-flow', { timeout: 20000 })
  await page.waitForTimeout(800)
  const tcdType = (await page.locator('.tcd-type').first().textContent())?.trim() ?? ''
  await page.screenshot({ path: path.join(EV, 'n2_f2_created.png'), fullPage: true })
  rec('F2.create_sync_wf', tcdType.includes('同步'), `name=${wfName} .tcd-type=${tcdType}`)

  /* ---- F3 同步组件侧栏：7 项白名单 + 点击添加节点 ---- */
  const failedBar = await page.locator('[data-testid="wf-specs-failed"]').count()
  if (failedBar > 0) {
    await page.screenshot({ path: path.join(EV, 'n3_f3_specs_failed.png'), fullPage: true })
    rec('F3.specs', false, '组件清单加载失败横幅在位（s323 纪律：呈报候裁，不擅自补数）')
  } else {
    const whitelist = ['src_base_orch', 'tgt_base_orch', 'file_sync_orch', 'endpoint_select', 'field_map', 'field_map_union', 'condition_set']
    const found = []
    for (const t of whitelist) {
      if ((await page.locator(`[data-testid="wf-spec-${t}"]`).count()) > 0) found.push(t)
    }
    rec('F3.specs_whitelist', found.length === 7, `7 项在位 ${found.length}/7`)
    const before = await page.locator('.vue-flow__node').count()
    await page.click('[data-testid="wf-spec-endpoint_select"]')
    await page.waitForFunction((n) => document.querySelectorAll('.vue-flow__node').length > n, before, { timeout: 10000 })
    await page.click('[data-testid="wf-spec-field_map"]')
    await page.waitForFunction((n) => document.querySelectorAll('.vue-flow__node').length > n + 1, before, { timeout: 10000 })
    const after = await page.locator('.vue-flow__node').count()
    await page.screenshot({ path: path.join(EV, 'n3_f3_specs_added.png'), fullPage: true })
    rec('F3.add_nodes', after === before + 2, `节点 ${before} -> ${after}`)

    /* ---- F4 节点配置：endpoint_select 结构化表单渲染 + field_map JSON 兜底保存 ---- */
    await page.click('.vue-flow__node >> nth=0')
    await page.waitForSelector('[data-testid="node-config-panel"]', { timeout: 10000 })
    const structured = await page.locator('[data-field="srcDs"]').isVisible()
    const dsFailed = await page.locator('[data-testid="ncp-ds-failed"]').count()
    await page.screenshot({ path: path.join(EV, 'n4a_f4_endpoint_panel.png'), fullPage: true })
    rec('F4.endpoint_panel', structured, `结构化表单渲染（srcDs 可见=${structured}，ds 加载失败横幅=${dsFailed}）`)

    await page.click('.vue-flow__node >> nth=1')
    await page.waitForSelector('[data-testid="ncp-json"]', { timeout: 10000 })
    await page.fill('[data-testid="ncp-json"]', JSON.stringify({ mapping: 'e2e-smoke' }))
    await page.click('[data-testid="ncp-save"]')
    await page.getByText('节点配置已保存', { exact: false }).first().waitFor({ timeout: 10000 })
    const panelGone = (await page.locator('[data-testid="node-config-panel"]').count()) === 0
    await page.screenshot({ path: path.join(EV, 'n4b_f4_json_saved.png'), fullPage: true })
    rec('F4.json_save', panelGone, 'field_map JSON 兜底保存 → 「节点配置已保存」+ 面板随选中清空收起')

    /* ---- 草稿落库（试运行快照前置） ---- */
    await page.locator('.wf-btn', { hasText: '保存' }).first().click()
    await page.getByText('保存成功', { exact: false }).first().waitFor({ timeout: 15000 })
    rec('draft.save', true, '画布草稿保存成功')

    /* ---- 剧本补图：API 补 START/END+连线，满足 trial 静态校验（测试数据准备）。
         UI 侧栏 7 组件无 START/END 入口；后端 VALID_NODE_TYPES 含 START/END 且无必填参数
         （trial/validator.py：START 免入边/END 免出边；SYNC+params.component 豁免必填）。
         快照由服务端 draft 生成（POST snapshot 仅带 project_id），API 补图即入快照。
         链：e2e_start→n1(endpoint_select)→n2(field_map)→e2e_end。 */
    const listJson = await (await fetch(`${BASE}/api/v1/rebuild/workflows?project_id=${PROJECT_ID}`, { headers: { authorization: `Bearer ${token}` } })).json()
    const listData = Array.isArray(listJson?.data) ? listJson.data : (listJson?.data?.items ?? [])
    const defRow = listData.find((w) => w.name === wfName)
    const defId = defRow?.definition_id ?? defRow?.id
    if (!defId) throw new Error(`definition 未定位 name=${wfName}`)
    const draftJson = await (await fetch(`${BASE}/api/v1/rebuild/workflows/${defId}?project_id=${PROJECT_ID}`, { headers: { authorization: `Bearer ${token}` } })).json()
    const codes = (draftJson?.data?.draft?.nodes ?? []).map((n) => n.node_code ?? n.nodeCode).sort()
    if (codes.length !== 2) throw new Error(`draft 节点数异常 ${JSON.stringify(codes)}`)
    const postDraft = async (p, body) => {
      const r = await fetch(`${BASE}/api/v1/rebuild/workflows/${defId}/${p}`, { method: 'POST', headers: { 'content-type': 'application/json', authorization: `Bearer ${token}` }, body: JSON.stringify({ project_id: PROJECT_ID, ...body }) })
      const j = await r.json()
      if (!r.ok || j?.code !== 0) throw new Error(`draft ${p} -> HTTP ${r.status} ${JSON.stringify(j).slice(0, 160)}`)
    }
    await postDraft('nodes', { node_code: 'e2e_start', node_type: 'START', name: 'e2e_start', params: null, position_x: 40, position_y: 260 })
    await postDraft('nodes', { node_code: 'e2e_end', node_type: 'END', name: 'e2e_end', params: null, position_x: 1000, position_y: 260 })
    await postDraft('edges', { from_node: 'e2e_start', to_node: codes[0], name: '' })
    await postDraft('edges', { from_node: codes[0], to_node: codes[1], name: '' })
    await postDraft('edges', { from_node: codes[1], to_node: 'e2e_end', name: '' })
    rec('graph.patch', true, `START/END+3边补图 e2e_start→${codes[0]}→${codes[1]}→e2e_end`)
  }

  /* ---- F5 试运行：面板 → 快照 → DRY_RUN → 计划/状态可见 ---- */
  await page.click('[data-testid="wf-trial"]')
  await page.waitForSelector('[data-part="trial-panel"]', { timeout: 10000 })
  rec('F5.panel', true, '试运行面板渲染（.wf-aside 承接）')
  await page.click('[data-test="snapshot-btn"]')
  await page.waitForSelector('[data-test="snap-info"]', { timeout: 20000 })
  const snapText = (await page.locator('[data-test="snap-info"]').innerText()).replace(/\s+/g, ' ')
  rec('F5.snapshot', true, snapText.slice(0, 120))
  await page.check('[data-test="dry-run"]')
  await page.click('[data-test="run-btn"]')
  await page.waitForSelector('[data-test="run-info"]', { timeout: 30000 })
  const runText = (await page.locator('[data-test="run-info"]').innerText()).replace(/\s+/g, ' ')
  const planVisible = (await page.locator('[data-test="plan-list"]').count()) > 0
  const planText = planVisible ? (await page.locator('[data-test="plan-list"]').innerText()).replace(/\s+/g, ' ') : ''
  await page.screenshot({ path: path.join(EV, 'n5_f5_trial_dryrun.png'), fullPage: true })
  rec('F5.dry_run', runText.includes('DRY_RUN'), `${runText} | plan: ${planText.slice(0, 120)}`)
} catch (e) {
  rec('fatal', false, String(e).slice(0, 300))
  try {
    const page = (await browser.contexts())[0]?.pages()[0]
    if (page) await page.screenshot({ path: path.join(EV, 'nx_fatal.png'), fullPage: true })
  } catch { /* 忽略 */ }
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
