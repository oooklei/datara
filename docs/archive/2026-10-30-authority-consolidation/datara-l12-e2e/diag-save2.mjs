/** API 层诊断：节点 upsert → readback 逐字段对比（draft.save dirty 根因） */
const BASE = process.env.E2E_BASE ?? 'http://192.168.1.9:18091'
const USER = process.env.E2E_USER ?? 'e2e-runner'
const PASS = process.env.E2E_PASS ?? ''

const entries = []
const log = (s) => { entries.push(s); console.log(s) }
const api = async (method, p, body) => {
  const r = await fetch(`${BASE}/api/v1${p}`, {
    method,
    headers: { 'content-type': 'application/json', authorization: `Bearer ${TOK}` },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const t = await r.text()
  let j
  try { j = JSON.parse(t) } catch { j = t.slice(0, 200) }
  if (r.status >= 400 || j?.code !== 0) log(`API ${method} ${p} -> ${r.status} ${JSON.stringify(j).slice(0, 200)}`)
  return j
}
let TOK = ''

if (!PASS) { console.error('E2E_PASS 未注入'); process.exit(2) }

const lr = await fetch(`${BASE}/api/v1/rebuild/login`, {
  method: 'POST', headers: { 'content-type': 'application/json' },
  body: JSON.stringify({ username: USER, password: PASS }),
})
const lj = await lr.json()
TOK = lj?.data?.token ?? ''
log(`LOGIN code=${lj?.code} token_len=${TOK.length}`)

/* 新建工作流 */
const wf = await api('POST', '/rebuild/workflows', { project_id: 23, name: `E2E-DIAG-API-${Date.now()}` })
log(`WF_RAW=${JSON.stringify(wf).slice(0, 300)}`)
const wfId = wf?.definition_id ?? wf?.id ?? wf?.data?.definition_id ?? wf?.data?.id
log(`WF_CREATED id=${wfId}`)

const cmp = (label, sent, back) => {
  if (!back) { log(`${label} back=undefined`); return }
  const s = [sent.node_code, sent.node_type, sent.name, JSON.stringify(sent.params ?? null), sent.position_x, sent.position_y]
  const b = [back.nodeCode ?? back.node_code, back.nodeType ?? back.node_type, back.name, JSON.stringify(back.params ?? null), back.positionX ?? back.position_x, back.positionY ?? back.position_y]
  const diff = s.map((v, i) => (String(v) === String(b[i]) ? null : `${['nodeCode','nodeType','name','params','positionX','positionY'][i]}: sent=${v} back=${b[i]}`)).filter(Boolean)
  log(`${label} diff=${diff.length === 0 ? 'NONE' : JSON.stringify(diff)}`)
}

/* 步骤1：加节点（模拟 onAddSpecNode：nodeType=SYNC + params.component） */
const n1 = { project_id: 23, node_code: 'n1', node_type: 'SYNC', name: null, params: { component: 'endpoint_select' }, position_x: 24, position_y: 24 }
log(`SEND1=${JSON.stringify(n1)}`)
await api('POST', `/rebuild/workflows/${wfId}/nodes`, n1)
let def = await api('GET', `/rebuild/workflows/${wfId}?project_id=23&include_draft=true`)
const back1 = def?.data?.draft?.nodes?.find((n) => n.node_code === 'n1')
log(`BACK1_RAW=${JSON.stringify(back1)}`)
cmp('STEP1', n1, back1)

/* 步骤2：upsert n1 带 params.mapping（模拟 ncp-save 后保存） */
const n1b = { ...n1, params: { component: 'endpoint_select', mapping: 'e2e-smoke' } }
log(`SEND2=${JSON.stringify(n1b)}`)
await api('POST', `/rebuild/workflows/${wfId}/nodes`, n1b)
def = await api('GET', `/rebuild/workflows/${wfId}?project_id=23&include_draft=true`)
const back2 = def?.data?.draft?.nodes?.find((n) => n.node_code === 'n1')
log(`BACK2_RAW=${JSON.stringify(back2)}`)
cmp('STEP2', n1b, back2)

/* 步骤3：再 upsert 一次同 payload（模拟保存重试） */
await api('POST', `/rebuild/workflows/${wfId}/nodes`, n1b)
def = await api('GET', `/rebuild/workflows/${wfId}?project_id=23&include_draft=true`)
const back3 = def?.data?.draft?.nodes?.find((n) => n.node_code === 'n1')
cmp('STEP3', n1b, back3)

/* 步骤4：加 n2 + 边 name=null 测物化 */
const n2 = { ...n1, node_code: 'n2', position_x: 194 }
await api('POST', `/rebuild/workflows/${wfId}/nodes`, n2)
const e1 = { project_id: 23, from_node: 'n1', to_node: 'n2', name: null }
log(`SEND_EDGE=${JSON.stringify(e1)}`)
await api('POST', `/rebuild/workflows/${wfId}/edges`, e1)
def = await api('GET', `/rebuild/workflows/${wfId}?project_id=23&include_draft=true`)
const backE = def?.data?.draft?.edges?.find((e) => e.from_node === 'n1' && e.to_node === 'n2')
log(`BACK_EDGE_RAW=${JSON.stringify(backE)}`)
cmpE('STEP4-EDGE', e1, backE)

function cmpE(label, sent, back) {
  if (!back) { log(`${label} back=undefined`); return }
  const s = [sent.from_node, sent.to_node, JSON.stringify(sent.name ?? null)]
  const b = [back.from_node ?? back.fromNode, back.to_node ?? back.toNode, JSON.stringify(back.name ?? null)]
  const diff = s.map((v, i) => (String(v) === String(b[i]) ? null : `${['fromNode','toNode','name'][i]}: sent=${v} back=${b[i]}`)).filter(Boolean)
  log(`${label} diff=${diff.length === 0 ? 'NONE' : JSON.stringify(diff)}`)
}

import { writeFileSync } from 'node:fs'
writeFileSync('d:/diag_api_result.json', entries.join('\n'), 'utf-8')
console.log('DIAG2_DONE')
