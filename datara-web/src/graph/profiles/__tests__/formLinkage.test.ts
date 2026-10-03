/**
 * I4 表单联动测试（设计 §9 vitest 新增之一）：
 * - C22 来源模式切换清空对方参数（c22OnModeChange）
 * - ${tmp.*} 前端侧引用提示（tmpRefUsable / tmpRefHint）
 * - dag profile C15/C16/C22 注册断言（type 对齐 worker EXECUTORS 键，表单含联动钩子）
 * - 同步编排端点合一：旧专业组件下线断言 + 3 编排组件新拓扑展开链（assert 双出口）+ C37 端点选择表单契约 + C17/C24 执行节点精简
 * - 拖边即引用纯函数（onEdgeCreated / onEdgeRemoved）+ 目标表基准探测（probeMatchTables）
 * - M5 组件 initTemplate 落图默认形态合入（applyInitTemplate，优先级链 defaults < 模板 < 上游快照）
 */
import { describe, expect, it } from 'vitest'
import type { GraphDocument } from '../../model'
import type { ConditionDef, NodeSchema } from '../types'
import { TMP_NAME_OK, applyInitTemplate, c22OnModeChange, clearOnConditionHide, condVisible as condVisibleProd, dataScopeState, decideDrop, domainViolations, onEdgeCreated, onEdgeRemoved, prefillFromUpstream, probeMatchTables, renderSummary, requiredMissing, resolveDataContext, tmpRefHint, tmpRefUsable } from '../formLinkage'
import type { DataContext, EdgeLike, GNodeLike } from '../formLinkage'
import type { FieldSchema } from '../types'
import { dagProfile } from '../dag'

/* ================= 八段 DSL conditions 求值辅助（M-B2 迁移后分型显隐的测试侧等价求值） ================= */

/** 单条 when 是否满足（op 口径对齐 dag.ts 迁移声明：eq/ne/notEq/in/notIn/empty/notEmpty） */
function whenMet(when: ConditionDef['when'], d: Record<string, unknown>): boolean {
  const v = d[when.field]
  const empty = v === undefined || v === null || String(v) === ''
  switch (when.op) {
    case 'eq': return v === when.value
    case 'ne':
    case 'notEq': return v !== when.value
    case 'in': return Array.isArray(when.value) && (when.value as unknown[]).includes(v)
    case 'notIn': return Array.isArray(when.value) && !(when.value as unknown[]).includes(v)
    case 'empty': return empty
    case 'notEmpty': return !empty
    default: return false
  }
}

/** 按 conditions 段求值字段可见性：同字段被多条条件引用时取交集（与迁移前 AND 复合 showIf 等价），未被引用恒显示 */
function condVisible(schema: { conditions?: ConditionDef[] }, key: string, d: Record<string, unknown>): boolean {
  const refs = (schema.conditions ?? []).filter((c) => c.show.includes(key))
  return refs.length === 0 || refs.every((c) => whenMet(c.when, d))
}

describe('C22 来源模式切换联动 c22OnModeChange', () => {
  it('切到 manual → 清空数据源引用，手动参数保留', () => {
    const d = { mode: 'manual', datasource: '样例文件源', path: 'a.csv', format: 'csv' }
    c22OnModeChange(d, 'manual')
    expect(d.datasource).toBe('')
    expect(d.path).toBe('a.csv') // 对方侧才清空
  })

  it('切到 datasource → 清空全部手动参数（路径/格式/编码/分隔符/表头/sheet）', () => {
    const d = {
      mode: 'datasource', datasource: '',
      path: 'samples/orders.csv', format: 'csv', encoding: 'gbk',
      delimiter: '\t', header: true, sheet: 'Sheet2',
    }
    c22OnModeChange(d, 'datasource')
    expect(d.datasource).toBe('') // 不动数据源侧
    expect(d.path).toBe('')
    expect(d.format).toBe('')
    expect(d.encoding).toBe('')
    expect(d.delimiter).toBe('')
    expect(d.header).toBe(false)
    expect(d.sheet).toBe('')
  })
})

describe('${tmp.*} 引用提示（前端侧判定）', () => {
  it('命名规则与后端 TMP_NAME_RE 同口径：小写字母开头 3~32 位 a-z0-9_', () => {
    expect(TMP_NAME_OK.test('orders')).toBe(true)
    expect(TMP_NAME_OK.test('od')).toBe(false) // 少于 3 位
    expect(TMP_NAME_OK.test('1orders')).toBe(false) // 数字开头
    expect(TMP_NAME_OK.test('Orders')).toBe(false) // 大写
    expect(TMP_NAME_OK.test('a'.repeat(33))).toBe(false) // 超长
  })

  it('未勾选注册 → 不可用并提示', () => {
    expect(tmpRefUsable({ register: false, tmpName: 'orders' })).toBe(false)
    expect(tmpRefHint({ register: false, tmpName: 'orders' })).toContain('未注册临时数据')
  })

  it('命名缺失/非法 → 提示不可用', () => {
    expect(tmpRefUsable({ register: true, tmpName: '' })).toBe(false)
    expect(tmpRefHint({ register: true, tmpName: 'X1' })).toContain('不合法')
  })

  it('注册且命名合法 → 可用、提示为空', () => {
    expect(tmpRefUsable({ register: true, tmpName: 'orders_2026' })).toBe(true)
    expect(tmpRefHint({ register: true, tmpName: 'orders_2026' })).toBe('')
  })
})

describe('dag profile C15/C16/C22 注册断言', () => {
  const nt = dagProfile.nodeTypes

  it('C15/C16/C22 已注册且 palette 可拖（无灰置）', () => {
    expect(nt.procedure?.code).toBe('C15')
    expect(nt.http?.code).toBe('C16')
    expect(nt.file?.code).toBe('C22')
    // type=file 对齐 worker EXECUTORS 注册键（master 按 nodeType 原样派发）
    expect(nt.file?.type).toBe('file')
    const calc = dagProfile.palette.find((c) => c.name === '数据计算')
    const items = (calc?.items ?? []).map((i) => i.type)
    expect(items).toContain('procedure')
    expect(items).toContain('http')
    expect(items).toContain('file')
    for (const item of calc?.items ?? []) expect(item.disabled).toBeFalsy()
  })

  it('C22 表单迁移八段声明：条件字段显隐由 conditions 段承载，${tmp.*} 提示字面量化', () => {
    const schema = nt.file!
    const form = schema.form
    // mode 仍为分型轴；onChange 不可序列化随迁移移除，清空联动由 formLinkage.c22OnModeChange 纯函数承载（行为断言见上方 C22 describe）
    const modeF = form.find((f) => f.key === 'mode')
    expect(modeF?.type).toBe('select')
    expect(modeF?.options?.map((o) => o.value)).toEqual(['datasource', 'manual'])
    // 原带 showIf 的条件字段均迁移至 conditions 段（纯数据、可序列化）
    const conds = schema.conditions ?? []
    for (const key of ['datasource', 'path', 'tmpName', 'kind', 'retention', 'keepDays']) {
      expect(conds.some((c) => c.show.includes(key)), `conditions 段缺 ${key} 显隐声明`).toBe(true)
    }
    // 分型显隐按声明等价求值（对齐原 showIf 语义：mode/register/retention 分型）
    expect(condVisible(schema, 'datasource', { mode: 'manual' })).toBe(false)
    expect(condVisible(schema, 'datasource', { mode: 'datasource' })).toBe(true)
    expect(condVisible(schema, 'path', { mode: 'manual' })).toBe(true)
    expect(condVisible(schema, 'path', { mode: 'datasource' })).toBe(false)
    expect(condVisible(schema, 'tmpName', { register: false })).toBe(false)
    expect(condVisible(schema, 'tmpName', { register: true })).toBe(true)
    expect(condVisible(schema, 'keepDays', { register: true, retention: 'days' })).toBe(true)
    expect(condVisible(schema, 'keepDays', { register: true, retention: 'immediate' })).toBe(false)
    // ${tmp.*} 提示字段：hint 文案字面量化（决策 5：原函数 text → 固定文案；动态判定保留在 tmpRefHint 纯函数）
    const hintF = form.find((f) => f.key === 'tmpHint')
    expect(hintF?.type).toBe('hint')
    expect(String(hintF?.text)).toContain('${tmp.')
  })

  it('C15 参数表为 rows·args、C16 头/体提取齐备且 GET/HEAD 隐藏请求体', () => {
    expect(nt.procedure!.form.find((f) => f.key === 'args')?.type).toBe('rows')
    expect(nt.procedure!.form.find((f) => f.key === 'args')?.rowsKind).toBe('args')
    const httpSchema = nt.http!
    const httpForm = httpSchema.form
    expect(httpForm.find((f) => f.key === 'headers')?.type).toBe('rows')
    expect(httpForm.find((f) => f.key === 'headers')?.rowsKind).toBe('kv')
    expect(httpForm.find((f) => f.key === 'extract')?.type).toBe('rows')
    expect(httpForm.find((f) => f.key === 'extract')?.rowsKind).toBe('kv')
    // 请求体显隐迁移至 conditions 段：method ∈ GET/HEAD 时隐藏（原 showIf 声明）
    expect(httpSchema.conditions?.find((c) => c.show.includes('body'))).toMatchObject({
      when: { field: 'method', op: 'notIn', value: ['GET', 'HEAD'] },
    })
    expect(httpSchema.conditions?.some((c) => c.show.includes('bodyType'))).toBe(true)
    // 行为等价求值：GET/HEAD 隐藏请求体，其余方法显示
    expect(condVisible(httpSchema, 'body', { method: 'GET' })).toBe(false)
    expect(condVisible(httpSchema, 'body', { method: 'HEAD' })).toBe(false)
    expect(condVisible(httpSchema, 'body', { method: 'POST' })).toBe(true)
  })
})

/* ================= 同步编排端点合一（C29~C31 编排组件 + C34~C37 细项组件 + C17/C24 运行态执行组件） ================= */

describe('同步编排组件注册与 palette 重构断言', () => {
  const nt = dagProfile.nodeTypes

  it('旧 5 专业组件已下线：C17/C24 降级运行态执行组件、C23 通用模板删除，palette 不再提供', () => {
    expect(nt.sync?.label).toBe('同步执行')
    expect(nt.file_sync?.label).toBe('文件入仓执行')
    expect(nt.sync_template).toBeUndefined()
    const syncGroup = dagProfile.palette.find((c) => c.name === '数据同步')
    const items = (syncGroup?.items ?? []).map((i) => i.type)
    expect(items).toEqual([
      'src_base_orch', 'tgt_base_orch', 'file_sync_orch',
      'endpoint_select', 'field_map', 'field_map_union', 'condition_set',
    ])
    for (const item of syncGroup?.items ?? []) expect(item.disabled).toBeFalsy()
  })

  it('3 个编排组件注册且各自唯一模式 build 展开为新拓扑细项节点链（设计态无执行节点，assert 双出口）', () => {
    expect(nt.src_base_orch?.code).toBe('C29')
    expect(nt.tgt_base_orch?.code).toBe('C30')
    expect(nt.file_sync_orch?.code).toBe('C31')
    // 「各自唯一模式」凭据：三编排组件 template.modes 均恰 1 个
    expect(nt.src_base_orch!.template!.modes).toHaveLength(1)
    expect(nt.tgt_base_orch!.template!.modes).toHaveLength(1)
    expect(nt.file_sync_orch!.template!.modes).toHaveLength(1)
    const doc = { id: 'wf_x', name: 'x', version: 1, meta: {}, nodes: [], edges: [] } as unknown as GraphDocument
    const buildOf = (t: keyof typeof nt) => nt[t]!.template!.modes[0]!.build
    const idOf = (res: { nodes: { id: string; type: string }[] }, t: string) => res.nodes.find((n) => n.type === t)!.id
    const linked = (es: { source: string; target: string }[], s: string, t: string) =>
      es.some((e) => e.source === s && e.target === t)
    // 源表基准：开始 → 前置清理 → 端点选择(src_base) → 字段映射-复制 → 条件设定 → 对账校验 → 结束 + 消息通知
    const a = buildOf('src_base_orch')({ doc, pos: { x: 0, y: 0 } })
    expect(a.nodes.map((n) => n.type)).toEqual(['start', 'sql', 'endpoint_select', 'field_map', 'condition_set', 'assert', 'end', 'notify'])
    expect(a.edges).toHaveLength(7)
    expect(a.edges.filter((e) => e.kind === 'flow')).toHaveLength(5)
    expect(a.nodes.find((n) => n.type === 'endpoint_select')!.data.baseMode).toBe('src_base')
    // 主链 5 条 flow 边线性串联
    expect(linked(a.edges, idOf(a, 'start'), idOf(a, 'sql'))).toBe(true)
    expect(linked(a.edges, idOf(a, 'sql'), idOf(a, 'endpoint_select'))).toBe(true)
    expect(linked(a.edges, idOf(a, 'endpoint_select'), idOf(a, 'field_map'))).toBe(true)
    expect(linked(a.edges, idOf(a, 'field_map'), idOf(a, 'condition_set'))).toBe(true)
    expect(linked(a.edges, idOf(a, 'condition_set'), idOf(a, 'assert'))).toBe(true)
    // assert 双出口（三链共用 chainEdgesWithNotify，链 a 上锁定即可）：通过→end / 不通过→notify
    const okEdge = a.edges.find((e) => e.source === idOf(a, 'assert') && e.target === idOf(a, 'end'))!
    expect(okEdge.kind).toBe('branch_true')
    expect(okEdge.sourceHandle).toBe('success')
    expect(okEdge.label).toBe('通过')
    const failEdge = a.edges.find((e) => e.source === idOf(a, 'assert') && e.target === idOf(a, 'notify'))!
    expect(failEdge.kind).toBe('branch_false')
    expect(failEdge.sourceHandle).toBe('failure')
    expect(failEdge.label).toBe('不通过')
    // 目标表基准：端点选择(tgt_base) → 字段映射-联合
    const b = buildOf('tgt_base_orch')({ doc, pos: { x: 0, y: 0 } })
    expect(b.nodes.map((n) => n.type)).toEqual(['start', 'sql', 'endpoint_select', 'field_map_union', 'condition_set', 'assert', 'end', 'notify'])
    expect(b.edges).toHaveLength(7)
    expect(b.nodes.find((n) => n.type === 'endpoint_select')!.data.baseMode).toBe('tgt_base')
    const fu = b.nodes.find((n) => n.type === 'field_map_union')!
    expect(fu.data.addSchemaFlag).toBe(true)
    expect(fu.data.srcSchemaField).toBe('src_schema')
    expect(fu.data.aggOperator).toBe('union_all')
    // 文件同步：端点选择(file_sync) 预置样例文件路径 → 字段映射-复制
    const c = buildOf('file_sync_orch')({ doc, pos: { x: 0, y: 0 } })
    expect(c.nodes.map((n) => n.type)).toEqual(['start', 'sql', 'endpoint_select', 'field_map', 'condition_set', 'assert', 'end', 'notify'])
    expect(c.edges).toHaveLength(7)
    const epC = c.nodes.find((n) => n.type === 'endpoint_select')!
    expect(epC.data.baseMode).toBe('file_sync')
    expect(epC.data.filePath).toBe('samples/orders_part.csv')
    // 展开产物均为标准组件节点（引擎零改动），且设计态链不含运行态执行组件 sync/file_sync
    for (const n of [...a.nodes, ...b.nodes, ...c.nodes]) {
      expect(dagProfile.nodeTypes[n.type]).toBeTruthy()
      expect(['sync', 'file_sync']).not.toContain(n.type)
    }
  })

  it('细项组件表单契约：端点选择三分拣 / 字段映射端点引用 / 字段映射-联合来源标识 / 条件设定增量表达式', () => {
    // C37 端点选择：baseMode 三分拣表单 showIf（默认 src_base）+ 双具名输出端口
    expect(nt.endpoint_select?.code).toBe('C37')
    expect(nt.endpoint_select!.outputs!.map((o) => o.id)).toEqual(['sourceRef', 'targetRef'])
    expect(nt.endpoint_select!.defaults?.probe).toBe(false)
    expect(nt.endpoint_select!.defaults?.matchType).toBe('exact')
    const epForm = nt.endpoint_select!.form
    // srcDs：src_base / tgt_base 可见，file_sync 隐藏（required）
    const srcDs = epForm.find((x) => x.key === 'srcDs')!
    expect(srcDs.required).toBe(true)
    expect(srcDs.showIf!({ baseMode: 'src_base' })).toBe(true)
    expect(srcDs.showIf!({ baseMode: 'tgt_base' })).toBe(true)
    expect(srcDs.showIf!({ baseMode: 'file_sync' })).toBe(false)
    // srcTable：仅 src_base
    const srcTable = epForm.find((x) => x.key === 'srcTable')!
    expect(srcTable.showIf!({ baseMode: 'src_base' })).toBe(true)
    expect(srcTable.showIf!({ baseMode: 'tgt_base' })).toBe(false)
    expect(srcTable.showIf!({ baseMode: 'file_sync' })).toBe(false)
    // 探测族：仅 tgt_base；matchType/matchPrefix/probeResult 还要求 probe 开（matchPrefix 另要求 prefix 规则）
    const probeF = epForm.find((x) => x.key === 'probe')!
    expect(probeF.showIf!({ baseMode: 'tgt_base' })).toBe(true)
    expect(probeF.showIf!({ baseMode: 'src_base' })).toBe(false)
    expect(probeF.showIf!({ baseMode: 'file_sync' })).toBe(false)
    for (const k of ['matchType', 'probeResult']) {
      const f = epForm.find((x) => x.key === k)!
      expect(f.showIf!({ baseMode: 'tgt_base', probe: true })).toBe(true)
      expect(f.showIf!({ baseMode: 'tgt_base', probe: false })).toBe(false)
      expect(f.showIf!({ baseMode: 'src_base', probe: true })).toBe(false)
    }
    expect(epForm.find((x) => x.key === 'probeResult')!.type).toBe('text')
    const mp = epForm.find((x) => x.key === 'matchPrefix')!
    expect(mp.showIf!({ baseMode: 'tgt_base', probe: true, matchType: 'prefix' })).toBe(true)
    expect(mp.showIf!({ baseMode: 'tgt_base', probe: true, matchType: 'exact' })).toBe(false)
    // 文件源区：仅 file_sync（filePath 必填）
    for (const k of ['filePath', 'fileType', 'fileHeaderRows']) {
      const f = epForm.find((x) => x.key === k)!
      expect(f.showIf!({ baseMode: 'file_sync' })).toBe(true)
      expect(f.showIf!({ baseMode: 'src_base' })).toBe(false)
      expect(f.showIf!({ baseMode: 'tgt_base' })).toBe(false)
    }
    expect(epForm.find((x) => x.key === 'filePath')!.required).toBe(true)
    // 目标表双条目按 baseMode 互斥渲染：tgt_base 必选 / 其余分型可留空（按源表同名或文件表头新建）
    const tgtTables = epForm.filter((x) => x.key === 'tgtTable')
    expect(tgtTables).toHaveLength(2)
    expect(tgtTables[0]!.required).toBe(true)
    expect(tgtTables[0]!.showIf!({ baseMode: 'tgt_base' })).toBe(true)
    expect(tgtTables[0]!.showIf!({ baseMode: 'src_base' })).toBe(false)
    expect(tgtTables[1]!.required).toBeFalsy()
    expect(tgtTables[1]!.showIf!({ baseMode: 'tgt_base' })).toBe(false)
    expect(tgtTables[1]!.showIf!({ baseMode: 'src_base' })).toBe(true)
    expect(tgtTables[1]!.showIf!({ baseMode: 'file_sync' })).toBe(true)
    // C34/C36 字段映射：源/目标列枚举均取自 endpoint_select（srcDs/srcTable 与 tgtDs/tgtTable 字段）
    const fmPick = nt.field_map!.form.find((f) => f.key === 'fieldMap')!.cap!
    expect(fmPick.srcNodeType).toBe('endpoint_select')
    expect(fmPick.tgtNodeType).toBe('endpoint_select')
    expect(fmPick.srcDsKey).toBe('srcDs')
    expect(fmPick.srcTableKey).toBe('srcTable')
    expect(fmPick.tgtDsKey).toBe('tgtDs')
    expect(fmPick.tgtTableKey).toBe('tgtTable')
    expect(fmPick.fmSrcIndex).toBe(0)
    expect(fmPick.fmTgtIndex).toBe(1)
    // C36 字段映射-联合：标识列 showIf + 聚合算子 union_all 唯一 + 来源标识取 fmSrcIndex=1（源端探测表）
    const fu = nt.field_map_union!
    expect(fu.code).toBe('C36')
    const fuPick = fu.form.find((f) => f.key === 'fieldMap')!.cap!
    expect(fuPick.srcNodeType).toBe('endpoint_select')
    expect(fuPick.fmSrcIndex).toBe(1)
    expect(fuPick.fmTgtIndex).toBe(0)
    expect(fu.form.find((f) => f.key === 'srcSchemaField')?.showIf?.({ addSchemaFlag: false })).toBe(false)
    expect(fu.form.find((f) => f.key === 'srcSchemaField')?.showIf?.({ addSchemaFlag: true })).toBe(true)
    expect(fu.defaults?.addSchemaFlag).toBe(true)
    expect(fu.defaults?.aggOperator).toBe('union_all')
    // C35 条件设定：增量表达式依赖增量列显示
    const cs = nt.condition_set!
    expect(cs.form.find((f) => f.key === 'incrementalExpr')?.showIf?.({ incrementalColumn: '' })).toBe(false)
    expect(cs.form.find((f) => f.key === 'incrementalExpr')?.showIf?.({ incrementalColumn: 'create_time' })).toBe(true)
  })

  it('C17/C24 执行节点表单精简：仅运行兜底参数，不再直拖业务读写在执行节点上配置', () => {
    const syncKeys = nt.sync!.form.map((f) => f.key)
    for (const k of ['batchSize', 'errorThreshold', 'truncate']) expect(syncKeys).toContain(k)
    for (const k of ['readerDs', 'readerTable', 'writerDs', 'strategy', 'fieldMap']) expect(syncKeys).not.toContain(k)
    expect(nt.sync!.defaults?.readerType).toBe('mysql')
    const fsKeys = nt.file_sync!.form.map((f) => f.key)
    for (const k of ['writeMode', 'flagColumn', 'autoCreate']) expect(fsKeys).toContain(k)
    expect(fsKeys).not.toContain('filePath')
    expect(fsKeys).not.toContain('targetDs')
  })

  it('旧「源表基准/目标表基准」浮窗已删除（floats 不再注册）', () => {
    const ids = (dagProfile.floats ?? []).map((f) => f.id)
    expect(ids).not.toContain('source_base')
    expect(ids).not.toContain('target_base')
  })
})

/* ================= 拖边即引用纯函数（端点合一设计 §3.3） ================= */

describe('拖边即引用（onEdgeCreated / onEdgeRemoved）', () => {
  const mkDoc = (): { nodes: GNodeLike[]; edges: EdgeLike[] } => ({
    nodes: [{ id: 'a', data: {} }, { id: 'b', data: { inputs: [] } }],
    edges: [],
  })

  it('拖边即引用：连边写入 inputs，删边移除', () => {
    const doc = mkDoc()
    onEdgeCreated(doc, { source: 'a', target: 'b', sourceHandle: 'sourceRef' })
    expect(doc.nodes[1]!.data!.inputs).toEqual(['a:sourceRef'])
    onEdgeRemoved(doc, { source: 'a', target: 'b', sourceHandle: 'sourceRef' })
    expect(doc.nodes[1]!.data!.inputs).toEqual([])
  })

  it('target 无 inputs（data 缺失）或 inputs 非数组 → 连边/删边均空操作', () => {
    const doc: { nodes: GNodeLike[]; edges: EdgeLike[] } = {
      nodes: [{ id: 'a', data: {} }, { id: 'b', data: { inputs: 'not-array' } }, { id: 'c' }],
      edges: [],
    }
    onEdgeCreated(doc, { source: 'a', target: 'b' })
    onEdgeRemoved(doc, { source: 'a', target: 'b' })
    expect(doc.nodes[1]!.data!.inputs).toBe('not-array')
    // target 无 data：早退不抛错、不创建 data
    onEdgeCreated(doc, { source: 'a', target: 'c', sourceHandle: 'sourceRef' })
    onEdgeRemoved(doc, { source: 'a', target: 'c', sourceHandle: 'sourceRef' })
    expect(doc.nodes[2]!.data).toBeUndefined()
  })

  it('重复连边不产生重复引用（includes 防重）', () => {
    const doc = mkDoc()
    onEdgeCreated(doc, { source: 'a', target: 'b', sourceHandle: 'sourceRef' })
    onEdgeCreated(doc, { source: 'a', target: 'b', sourceHandle: 'sourceRef' })
    expect(doc.nodes[1]!.data!.inputs).toEqual(['a:sourceRef'])
  })

  it('sourceHandle 缺省（普通连线）→ 引用为 `${source}:`', () => {
    const doc = mkDoc()
    onEdgeCreated(doc, { source: 'a', target: 'b' })
    expect(doc.nodes[1]!.data!.inputs).toEqual(['a:'])
    onEdgeRemoved(doc, { source: 'a', target: 'b' })
    expect(doc.nodes[1]!.data!.inputs).toEqual([])
  })

  it('target 不存在早退；onEdgeRemoved 对不存在 ref 早退（不产生新数组，同引用）', () => {
    const doc = mkDoc()
    // target 不存在：早退无副作用
    onEdgeCreated(doc, { source: 'a', target: 'ghost', sourceHandle: 'sourceRef' })
    expect(doc.nodes[1]!.data!.inputs).toEqual([])
    // ref 不存在：早退且不替换数组引用
    doc.nodes[1]!.data!.inputs = ['other:port']
    const before = doc.nodes[1]!.data!.inputs
    onEdgeRemoved(doc, { source: 'a', target: 'b', sourceHandle: 'sourceRef' })
    expect(doc.nodes[1]!.data!.inputs).toBe(before)
  })
})

/* ================= 目标表基准探测纯函数（端点合一设计 §3.1） ================= */

describe('目标表基准探测 probeMatchTables', () => {
  const tree = { s_b: ['orders', 'orders_east'], s_a: ['orders', 'order_detail'], s_c: ['payment'] }

  it('exact：命中同名（含跨 schema 多命中），schema 按字典序稳定排序', () => {
    expect(probeMatchTables(tree, 'orders', 'exact', '')).toEqual([
      { schema: 's_a', table: 'orders' },
      { schema: 's_b', table: 'orders' },
    ])
  })

  it('prefix：按前缀命中（matchPrefix 非空覆盖目标表名）', () => {
    expect(probeMatchTables(tree, 'orders', 'prefix', 'order')).toEqual([
      { schema: 's_a', table: 'orders' },
      { schema: 's_a', table: 'order_detail' },
      { schema: 's_b', table: 'orders' },
      { schema: 's_b', table: 'orders_east' },
    ])
    // matchPrefix 优先于目标表名：前缀 pay 只命中 s_c.payment
    expect(probeMatchTables(tree, 'orders', 'prefix', 'pay')).toEqual([
      { schema: 's_c', table: 'payment' },
    ])
  })

  it('prefix 且 matchPrefix 留空 → 回退目标表名作为前缀', () => {
    expect(probeMatchTables(tree, 'orders', 'prefix', '')).toEqual([
      { schema: 's_a', table: 'orders' },
      { schema: 's_b', table: 'orders' },
      { schema: 's_b', table: 'orders_east' },
    ])
  })

  it('tgtTable 为空且 exact → 永不命中返回空候选', () => {
    expect(probeMatchTables(tree, '', 'exact', '')).toEqual([])
  })

  it('prefix 且 matchPrefix/tgtTable 均空 → startsWith(\'\') 恒真返回全库候选（有意为之）', () => {
    const all = probeMatchTables(tree, '', 'prefix', '')
    expect(all).toHaveLength(5)
    expect(all.map((c) => c.schema)).toEqual(['s_a', 's_a', 's_b', 's_b', 's_c'])
  })
})

/* ================= F1 configure-first 拖入闸门（治理设计 §11/§12.1） ================= */

describe('拖入前置裁决 decideDrop', () => {
  const mkSchema = (over: Partial<NodeSchema> = {}): NodeSchema => ({
    type: 'sql', label: 'SQL', icon: '?', color: '#000', form: [{ key: 'a', label: 'A', type: 'text' }],
    ...over,
  })

  it('灰置（palette disabled）→ 拦截并给出原因（不弹窗直接 toast 场景）', () => {
    const d = decideDrop(mkSchema(), { sameTypeCount: 0, paletteDisabled: true })
    expect(d.action).toBe('intercept')
    if (d.action === 'intercept') expect(d.reason).toContain('不可用')
  })

  it('runtimeOnly 组件 → 拦截（dataTransfer 伪造防御层）', () => {
    const d = decideDrop(mkSchema({ runtimeOnly: true }), { sameTypeCount: 0 })
    expect(d.action).toBe('intercept')
  })

  it('maxInstances 超限 → 拦截；未达上限放行；0/缺省 = 不限', () => {
    const capped = mkSchema({ dropPolicy: { maxInstances: 2 } })
    expect(decideDrop(capped, { sameTypeCount: 2 }).action).toBe('intercept')
    expect(decideDrop(capped, { sameTypeCount: 1 }).action).toBe('dialog')
    expect(decideDrop(mkSchema({ dropPolicy: { maxInstances: 0 } }), { sameTypeCount: 99 }).action).toBe('dialog')
    expect(decideDrop(mkSchema(), { sameTypeCount: 99 }).action).toBe('dialog')
  })

  it('form 为空（C1/C2/C6/C7「无业务表单，仅六区块」）→ 仍必弹窗，无 direct-add 旁路', () => {
    // 六区块是框架级必填配置面：form: [] 不代表无配置面，绕过弹窗会产生无②输出/无③参数的裸节点
    expect(decideDrop(mkSchema({ form: [] }), { sameTypeCount: 0 }).action).toBe('dialog')
    expect(decideDrop(mkSchema({ form: undefined }), { sameTypeCount: 0 }).action).toBe('dialog')
    expect(decideDrop(mkSchema(), { sameTypeCount: 0 }).action).toBe('dialog')
    // 裁决结果集合只有两种：拦截 or 弹窗（不再产出直接落画布）
    const actions = [mkSchema({ form: [] }), mkSchema({ runtimeOnly: true }), mkSchema()].map(
      (s) => decideDrop(s, { sameTypeCount: 0 }).action,
    )
    expect(new Set(actions)).toEqual(new Set(['dialog', 'intercept']))
  })
})

describe('prefillFromUpstream 快照预填（§11 划界语义）', () => {
  it('取上游同名非空值写入；空值（\'\'/null/undefined/空数组）不覆盖 defaults', () => {
    const data: Record<string, unknown> = { datasource: '默认源', ds: '' }
    prefillFromUpstream(data, { datasource: '上游库', ds: '', x: null, y: undefined, tags: [] }, ['datasource', 'ds', 'x', 'y', 'tags'])
    expect(data.datasource).toBe('上游库') // 上游非空 → 覆盖
    expect(data.ds).toBe('') // 上游空 → 保留 defaults
    expect('x' in data).toBe(false) // 上游 null/undefined → 不写键
    expect('tags' in data).toBe(false)
  })

  it('数组值深拷贝写入（快照语义：上游后续变化不回写弹窗数据）', () => {
    const upTags = ['a', 'b']
    const data: Record<string, unknown> = {}
    prefillFromUpstream(data, { tags: upTags }, ['tags'])
    const snap = data.tags as string[]
    expect(snap).toEqual(['a', 'b'])
    expect(snap).not.toBe(upTags) // 拷贝而非引用
    upTags.push('c')
    expect(snap).toEqual(['a', 'b'])
  })

  it('上游缺失 / keys 为空 → 空操作（起始节点拖入不预填）', () => {
    const data: Record<string, unknown> = { datasource: '默认源' }
    prefillFromUpstream(data, null, ['datasource'])
    prefillFromUpstream(data, { datasource: 'x' }, undefined)
    prefillFromUpstream(data, { datasource: 'x' }, [])
    expect(data.datasource).toBe('默认源')
  })
})

/* ================= M5 组件 initTemplate 落图消费（applyInitTemplate 纯函数，页面设计器 Task 14 消费点） ================= */

describe('applyInitTemplate 组件初始化模板合入（M5）', () => {
  const mkSchema = (over: Partial<NodeSchema> = {}): NodeSchema => ({
    type: 'sql', label: 'SQL', icon: '?', color: '#000', form: [{ key: 'a', label: 'A', type: 'text' }],
    ...over,
  })

  it('无 initTemplate → 等价副本返回：不新增键、不改 name，且不改传入对象', () => {
    const schema = mkSchema()
    const data = { name: 'SQL', ds: 'd1' }
    const out = applyInitTemplate(data, schema)
    expect(out).toEqual({ name: 'SQL', ds: 'd1' })
    expect(out).not.toBe(data) // 副本而非原引用
    expect(data).toEqual({ name: 'SQL', ds: 'd1' }) // 入参未被原地修改
  })

  it('有 initTemplate.props → props 键合入 data（name 等既有键不动）', () => {
    const schema = mkSchema({ initTemplate: { rect: { w: 240, h: 120 }, props: { mode: 'manual', limit: 100 } } })
    const out = applyInitTemplate({ name: 'SQL' }, schema)
    expect(out.mode).toBe('manual')
    expect(out.limit).toBe(100)
    expect(out.name).toBe('SQL')
  })

  it('与 defaults 同名键 → initTemplate.props 覆盖 defaults（组件创作模板更具体）', () => {
    const schema = mkSchema({
      defaults: { mode: 'datasource', path: 'a.csv' },
      initTemplate: { rect: { w: 240, h: 120 }, props: { mode: 'manual' } },
    })
    const out = applyInitTemplate({ name: 'SQL', mode: 'datasource', path: 'a.csv' }, schema)
    expect(out.mode).toBe('manual') // 模板覆盖通用默认
    expect(out.path).toBe('a.csv') // 未声明的键保持 defaults
  })

  it('优先级链完整：applyInitTemplate 之后 prefillFromUpstream 上游同名值仍覆盖 initTemplate 值', () => {
    const schema = mkSchema({
      defaults: { datasource: '默认源' },
      initTemplate: { rect: { w: 240, h: 120 }, props: { datasource: '模板源' } },
    })
    const g = applyInitTemplate({ name: 'SQL', datasource: '默认源' }, schema)
    expect(g.datasource).toBe('模板源') // 模板先压过 defaults
    prefillFromUpstream(g, { datasource: '上游库' }, ['datasource'])
    expect(g.datasource).toBe('上游库') // 上游快照最具体，最后落笔
  })

  it('不可变性：不原地修改传入 data，也不反向污染 schema.initTemplate.props', () => {
    const props = { mode: 'manual' }
    const schema = mkSchema({ initTemplate: { rect: { w: 240, h: 120 }, props } })
    const out = applyInitTemplate({ mode: 'datasource' }, schema)
    expect(out.mode).toBe('manual')
    expect(schema.initTemplate!.props).toEqual({ mode: 'manual' }) // 模板源对象未被改写
    expect(schema.initTemplate!.props).toBe(props)
  })
})

describe('F1 载体组件 dropPolicy 声明断言（sql/procedure 同名 datasource 预填链）', () => {
  const nt = dagProfile.nodeTypes

  it('C11 SQL / C15 存储过程声明 prefillFromUpstream，且预填键均为其表单真实字段', () => {
    for (const t of ['sql', 'procedure'] as const) {
      const keys = nt[t]!.dropPolicy?.prefillFromUpstream
      expect(keys).toEqual(['datasource'])
      // 预填键必须存在于表单（声明有效性：漂移即测试失败）
      expect(nt[t]!.form.some((f) => f.key === 'datasource')).toBe(true)
    }
  })
})

/* ================= F2 resolveDataContext 数据驱动上下文解析（实施计划 F2） ================= */

describe('resolveDataContext 上下文解析器', () => {
  /* 线性三级链 a→b→c→x：x 的多级上游 = c（直接）/b/a（递归） */
  const doc = {
    nodes: [
      { id: 'a', data: {} },
      { id: 'b', data: { inputs: ['a:'] } },
      { id: 'c', data: { inputs: ['b:', 'a:'] } },
      { id: 'x' }, // 无 data：下游收集路径对 inputs 缺失节点静默跳过
    ],
    edges: [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'c' },
      { source: 'c', target: 'x' },
    ],
  }
  const schemas = {
    a: { columns: ['id', 'name'], tables: ['t_a'] },
    b: { columns: ['id', 'age'], tables: [] }, // 空表集：不产生无效条目
    c: { columns: ['name', 'city'] }, // 无 tables 键：跳过
  }

  it('多级上游：BFS 就近优先去重合并列/表集（x 收集 c/b/a 三级）', () => {
    const ctx = resolveDataContext(doc, 'x', { upstreamSchemas: schemas })
    // 就近序：c 先并入，b 次之，a 最后（id/name 与前级重复被去重）
    expect(ctx.upstreamColumns).toEqual(['name', 'city', 'id', 'age'])
    expect(ctx.upstreamTables).toEqual(['t_a'])
  })

  it('环安全：上游成环不死循环；起点自身不算自己的上游', () => {
    const ring = {
      nodes: [{ id: 'p', data: {} }, { id: 'q', data: {} }],
      edges: [{ source: 'p', target: 'q' }, { source: 'q', target: 'p' }],
    }
    const ctx = resolveDataContext(ring, 'p', {
      upstreamSchemas: { q: { columns: ['qc'] }, p: { columns: ['pc'] } },
    })
    expect(ctx.upstreamColumns).toEqual(['qc']) // p 自身的 pc 不并入
  })

  it('空上游降级：无边/无登记/节点不存在 → 全空上下文不抛错', () => {
    const empty = { upstreamColumns: [], upstreamTables: [], vars: [], timeParams: [], downstreamNeeds: [] }
    expect(resolveDataContext({ nodes: [{ id: 'x', data: {} }], edges: [] }, 'x', { upstreamSchemas: schemas })).toEqual(empty)
    expect(resolveDataContext(doc, 'x')).toEqual(empty) // 未注入 upstreamSchemas/vars
    expect(resolveDataContext({ nodes: [], edges: [] }, 'ghost')).toEqual(empty)
  })

  it('vars 去重保序（空串跳过）；downstreamNeeds 收集可达下游 inputs 引用（去重）', () => {
    const ctx = resolveDataContext(doc, 'a', { vars: ['biz_date', 'gp1', 'biz_date', ''] })
    expect(ctx.vars).toEqual(['biz_date', 'gp1'])
    // a 的可达下游 = b/c/x：b 引用 a、c 引用 b+a，x 无 data 静默跳过 → 去重保序后 2 条
    expect(ctx.downstreamNeeds).toEqual(['a:', 'b:'])
  })

  it('timeParams 独立域：与 vars 分域去重互不干扰（F3 分域口径）', () => {
    const ctx = resolveDataContext({ nodes: [{ id: 'x', data: {} }], edges: [] }, 'x', {
      vars: ['gp1', 'gp1'],
      timeParams: ['biz_date', 'biz_date', ''],
    })
    expect(ctx.vars).toEqual(['gp1'])
    expect(ctx.timeParams).toEqual(['biz_date'])
  })
})

/* ================= F3 dataScope 值域过滤（dataScopeState 纯函数） ================= */

describe('dataScopeState 值域过滤（F3：候选只来自 DataContext 对应域）', () => {
  const full: DataContext = {
    upstreamColumns: ['id', 'name'],
    upstreamTables: ['ods_order'],
    vars: ['run.instanceId', 'gp_rate'],
    timeParams: ['biz_date', 'today'],
    downstreamNeeds: [],
  }

  it('四域提取：每个 dataScope 只取对应集合，域间不串', () => {
    expect(dataScopeState(full, 'upstream-columns')).toEqual({ options: ['id', 'name'], disabledReason: '' })
    expect(dataScopeState(full, 'upstream-tables')).toEqual({ options: ['ods_order'], disabledReason: '' })
    expect(dataScopeState(full, 'workflow-vars')).toEqual({ options: ['run.instanceId', 'gp_rate'], disabledReason: '' })
    expect(dataScopeState(full, 'time-params')).toEqual({ options: ['biz_date', 'today'], disabledReason: '' })
  })

  it('域空 → 禁用并说明原因（禁用必说明；上游两域文案含未登记 schema 语义）', () => {
    const empty: DataContext = { upstreamColumns: [], upstreamTables: [], vars: [], timeParams: [], downstreamNeeds: [] }
    for (const s of ['upstream-columns', 'upstream-tables', 'workflow-vars', 'time-params'] as const) {
      const st = dataScopeState(empty, s)
      expect(st.options).toEqual([])
      expect(st.disabledReason).not.toBe('')
    }
    expect(dataScopeState(empty, 'upstream-columns').disabledReason).toContain('未登记输出 schema')
    expect(dataScopeState(empty, 'workflow-vars').disabledReason).toContain('变量')
  })

  it('与 resolveDataContext 串联：上游 schema 登记与否决定上游两域可用性（F3 验收主链）', () => {
    const doc = {
      nodes: [{ id: 'x', data: {} }, { id: 'up', data: {} }],
      edges: [{ source: 'up', target: 'x' }],
    }
    // 未登记输出 schema → 上游列/表域空 → 禁用说明；变量两域不受上游影响
    const none = resolveDataContext(doc, 'x', { vars: ['gp1'], timeParams: ['biz_date'] })
    expect(dataScopeState(none, 'upstream-columns').disabledReason).not.toBe('')
    expect(dataScopeState(none, 'upstream-tables').disabledReason).not.toBe('')
    expect(dataScopeState(none, 'workflow-vars')).toEqual({ options: ['gp1'], disabledReason: '' })
    expect(dataScopeState(none, 'time-params')).toEqual({ options: ['biz_date'], disabledReason: '' })
    // 登记后 → 上游两域可用
    const reg = resolveDataContext(doc, 'x', { upstreamSchemas: { up: { columns: ['uid'], tables: ['t_u'] } } })
    expect(dataScopeState(reg, 'upstream-columns')).toEqual({ options: ['uid'], disabledReason: '' })
    expect(dataScopeState(reg, 'upstream-tables')).toEqual({ options: ['t_u'], disabledReason: '' })
  })
})

/* ================= F4 值域/悬空引用校验（domainViolations 纯函数，configure-first 闸门） ================= */

describe('domainViolations 值域与悬空引用校验（F4 闸门）', () => {
  const ctx: DataContext = {
    upstreamColumns: ['id', 'name'],
    upstreamTables: ['ods_order'],
    vars: ['run.instanceId'],
    timeParams: ['biz_date'],
    downstreamNeeds: [],
  }
  const form: FieldSchema[] = [
    { key: 'tgtTable', label: '目标表', type: 'text', dataScope: 'upstream-tables' },
    { key: 'col', label: '目标列', type: 'text', dataScope: 'upstream-columns' },
    { key: 'p1', label: '日期参数', type: 'text', dataScope: 'time-params' },
    { key: 'free', label: '自由文本', type: 'text' },
    { key: 'hint', label: '提示', type: 'hint' },
  ]

  it('值在域内 → 合规；域外取值 → 违规且文案指出所属域', () => {
    const ok = domainViolations(form, { tgtTable: 'ods_order', col: 'id', p1: 'biz_date', free: '任意' }, ctx)
    expect(ok).toEqual([])

    const bad = domainViolations(form, { tgtTable: 'ods_dim', col: 'id' }, ctx)
    expect(bad).toHaveLength(1)
    expect(bad[0]).toMatchObject({ key: 'f:tgtTable', label: '目标表' })
    expect(bad[0].reason).toContain('ods_dim')
    expect(bad[0].reason).toContain('upstream-tables')
  })

  it('未填值的 dataScope 字段不算违规（必填由 requiredMissing 单独判定）', () => {
    expect(domainViolations(form, { free: 'x' }, ctx)).toEqual([])
  })

  it('域空时存量值按违规计（禁用但留着非法值不得静默通过）', () => {
    const empty: DataContext = { upstreamColumns: [], upstreamTables: [], vars: [], timeParams: [], downstreamNeeds: [] }
    const v = domainViolations(form, { tgtTable: 'ods_order' }, empty)
    expect(v).toHaveLength(1)
    expect(v[0].reason).toContain('无可用候选')
    expect(v[0].reason).toContain('未登记输出 schema')
  })

  it('showIf 未命中的隐藏字段不参与值域判定（不出现在画面的值不拦确认）', () => {
    const gated: FieldSchema[] = [
      { key: 'col', label: '目标列', type: 'text', dataScope: 'upstream-columns', showIf: (d) => d.mode === 'map' },
    ]
    expect(domainViolations(gated, { mode: 'copy', col: 'not_a_col' }, ctx)).toEqual([])
    expect(domainViolations(gated, { mode: 'map', col: 'not_a_col' }, ctx)).toHaveLength(1)
  })

  it('数组值逐项校验：部分越界只报越界项', () => {
    const multi: FieldSchema[] = [{ key: 'cols', label: '目标列集', type: 'text', dataScope: 'upstream-columns' }]
    const v = domainViolations(multi, { cols: ['id', 'oops', 'name'] }, ctx)
    expect(v).toHaveLength(1)
    expect(v[0].reason).toContain('oops')
  })

  it('①输入 悬空引用：引用不在上游②输出候选内 → 违规；无上游（起始节点）不算违规', () => {
    const outs = ['源节点.t1（结果表）', '源节点.p1（参数）']
    expect(domainViolations(form, {}, ctx, ['源节点.t1（结果表）'], outs)).toEqual([])

    const stale = domainViolations(form, {}, ctx, ['源节点.t1（结果表）', '已删节点.t9（结果表）'], outs)
    expect(stale).toHaveLength(1)
    expect(stale[0]).toMatchObject({ key: 'i:已删节点.t9（结果表）' })
    expect(stale[0].reason).toContain('失效')

    // 上游无②输出登记 → 无候选可比，不误判（起始节点或上游未登记 schema）
    expect(domainViolations(form, {}, ctx, ['任意.引用'], [])).toEqual([])
  })
})

/* ================= 八段 DSL conditions 求值器（M-B2 迁移收口：生产 requiredMissing/visibleForm/onSet/副标题的判定真源） ================= */

describe('conditions 求值器：condVisible / clearOnConditionHide / renderSummary（M-B2 迁移收口）', () => {
  const nt = dagProfile.nodeTypes
  const file = nt.file!
  const http = nt.http!

  it('condVisibleProd：同字段多条条件引用取 AND 交集，未引用恒显示（生产求值器直测，签名 conditions 在前）', () => {
    // file.sheet 被 c-manual（mode=manual）与 c-sheet（format=excel）同时引用 → 两者都须满足
    expect(condVisibleProd(file.conditions, 'sheet', { mode: 'manual', format: 'excel' })).toBe(true)
    expect(condVisibleProd(file.conditions, 'sheet', { mode: 'manual', format: 'csv' })).toBe(false)
    expect(condVisibleProd(file.conditions, 'sheet', { mode: 'datasource', format: 'excel' })).toBe(false)
    // http.body 仅被 c-body（method notIn GET/HEAD）引用
    expect(condVisibleProd(http.conditions, 'body', { method: 'GET' })).toBe(false)
    expect(condVisibleProd(http.conditions, 'body', { method: 'POST' })).toBe(true)
    // 未被 conditions 引用的字段恒显示；无 conditions 段恒显示
    expect(condVisibleProd(http.conditions, 'url', { method: 'GET' })).toBe(true)
    expect(condVisibleProd(undefined, 'any', {})).toBe(true)
  })

  it('clearOnConditionHide：file 切 mode 清空隐藏侧参数（与 c22OnModeChange 同口径，bool 清 false）', () => {
    const d: Record<string, unknown> = {
      mode: 'datasource', datasource: '样例文件源',
      path: 'a.csv', format: 'csv', encoding: 'gbk', delimiter: '\t', header: true, sheet: 'S2',
    }
    clearOnConditionHide(file, d, 'mode') // mode=datasource：c-manual 失满足 → 清手动参数族
    expect(d.datasource).toBe('样例文件源') // c-datasource 满足 → 数据源侧保留
    expect(d.path).toBe('')
    expect(d.format).toBe('')
    expect(d.encoding).toBe('')
    expect(d.delimiter).toBe('')
    expect(d.header).toBe(false) // bool 字段清 false（对齐 c22OnModeChange）
    expect(d.sheet).toBe('')

    d.mode = 'manual'
    clearOnConditionHide(file, d, 'mode') // mode=manual：c-datasource 失满足 → 清数据源引用
    expect(d.datasource).toBe('')
  })

  it('clearOnConditionHide：非 when 轴字段变化不触发清空（联动仅挂在分型轴上）', () => {
    const d: Record<string, unknown> = { mode: 'manual', register: true, tmpName: 'orders', path: 'a.csv' }
    clearOnConditionHide(file, d, 'tmpName') // tmpName 不在任何 when.field 上 → 无条件失满足
    expect(d.path).toBe('a.csv')
    expect(d.tmpName).toBe('orders')
  })

  it('renderSummary：summaryRules 按声明序取首条命中（when=null 兜底）+ ${key} 插值', () => {
    const rules: NodeSchema = {
      type: 'ssh', label: 'SSH', icon: '⌖', color: '#000', form: [],
      render: {
        summaryRules: [
          { when: { field: 'execNodeTag', op: 'notEmpty' }, template: '标签 ${execNodeTag}' },
          { when: { field: 'runtimeNode', op: 'notEmpty' }, template: '节点 ${runtimeNode}' },
          { when: null, template: 'SSH 远程脚本' },
        ],
      },
    }
    expect(renderSummary(rules, { execNodeTag: 'etl', runtimeNode: 'node-1' })).toBe('标签 etl')
    expect(renderSummary(rules, { runtimeNode: 'node-1' })).toBe('节点 node-1')
    expect(renderSummary(rules, {})).toBe('SSH 远程脚本')
  })

  it('renderSummary：无规则回退 render.summary 常量，再回退旧 schema.summary（字符串/函数）', () => {
    expect(renderSummary({ render: { summary: 'HTTP 调用' } }, {})).toBe('HTTP 调用')
    expect(renderSummary({ render: {} }, {})).toBe('')
    expect(renderSummary({ summary: '静态' }, {})).toBe('静态')
    const legacy: Pick<NodeSchema, 'summary'> = {
      summary: (d: Record<string, unknown>) => String(d.x || '旧函数'),
    }
    expect(renderSummary(legacy, { x: '' })).toBe('旧函数')
    expect(renderSummary(legacy, { x: 'v' })).toBe('v')
  })

  it('生产 requiredMissing × conditions：notify 仅日志不误报/webhook 分型必填 URL；assert 手选分型必填源表', () => {
    const notify = nt.notify!
    expect(requiredMissing(notify, { ...(notify.defaults ?? {}) })).toEqual([])
    expect(requiredMissing(notify, { ...(notify.defaults ?? {}), channel: 'webhook' })).toEqual(['Webhook URL'])
    const assertSchema = nt.assert!
    expect(requiredMissing(assertSchema, { ...(assertSchema.defaults ?? {}) })).toEqual([])
    expect(requiredMissing(assertSchema, { ...(assertSchema.defaults ?? {}), assertSrc: 'manual' }))
      .toEqual(['校验数据源', '校验表（schema → 表）'])
  })
})
