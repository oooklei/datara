/**
 * I4 表单联动测试（设计 §9 vitest 新增之一）：
 * - C22 来源模式切换清空对方参数（c22OnModeChange）
 * - ${tmp.*} 前端侧引用提示（tmpRefUsable / tmpRefHint）
 * - dag profile C15/C16/C22 注册断言（type 对齐 worker EXECUTORS 键，表单含联动钩子）
 * - I6：C17 读端类型联动/SQL 预览 + C17/C23 注册与两套模板展开断言
 */
import { describe, expect, it } from 'vitest'
import type { GraphDocument } from '../../model'
import { TMP_NAME_OK, c17IsConnReader, c17IsFileReader, c17OnReaderTypeChange, c17SqlPreview, c22OnModeChange, tmpRefHint, tmpRefUsable } from '../formLinkage'
import { dagProfile } from '../dag'

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
    expect(tmpRefUsable({ register: false, name: 'orders' })).toBe(false)
    expect(tmpRefHint({ register: false, name: 'orders' })).toContain('未注册临时数据')
  })

  it('命名缺失/非法 → 提示不可用', () => {
    expect(tmpRefUsable({ register: true, name: '' })).toBe(false)
    expect(tmpRefHint({ register: true, name: 'X1' })).toContain('不合法')
  })

  it('注册且命名合法 → 可用、提示为空', () => {
    expect(tmpRefUsable({ register: true, name: 'orders_2026' })).toBe(true)
    expect(tmpRefHint({ register: true, name: 'orders_2026' })).toBe('')
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
    for (const it of calc?.items ?? []) expect(it.disabled).toBeFalsy()
  })

  it('C22 表单含联动钩子：mode.onChange 已挂、条件字段均带 showIf', () => {
    const form = nt.file!.form
    const modeF = form.find((f) => f.key === 'mode')
    expect(typeof modeF?.onChange).toBe('function')
    // onChange 行为与纯函数一致
    const d: Record<string, unknown> = { path: 'a.csv', datasource: 'x' }
    modeF!.onChange!(d, 'manual')
    expect(d.datasource).toBe('')
    // 条件字段均声明 showIf（来源模式/保留策略分支展示）
    for (const key of ['datasource', 'path', 'name', 'kind', 'retention', 'keepDays']) {
      expect(typeof form.find((f) => f.key === key)?.showIf).toBe('function')
    }
    // ${tmp.*} 提示字段：text 动态产出
    const hintF = form.find((f) => f.key === 'tmpHint')
    expect(hintF?.type).toBe('hint')
    expect(hintF!.text!({ register: false })).toContain('${tmp.*}')
  })

  it('C15 参数表为 args-table、C16 头/体提取齐备且 GET/HEAD 隐藏请求体', () => {
    expect(nt.procedure!.form.find((f) => f.key === 'args')?.type).toBe('args-table')
    const httpForm = nt.http!.form
    expect(httpForm.find((f) => f.key === 'headers')?.type).toBe('kv-table')
    expect(httpForm.find((f) => f.key === 'extract')?.type).toBe('kv-table')
    const bodyF = httpForm.find((f) => f.key === 'body')
    expect(bodyF?.showIf?.({ method: 'GET' })).toBe(false)
    expect(bodyF?.showIf?.({ method: 'POST' })).toBe(true)
  })
})

/* ================= I6 C17/C23 数据同步 ================= */

describe('I6 C17 读端类型联动与 SQL 预览', () => {
  it('c17IsConnReader / c17IsFileReader 判定（缺省按连接型）', () => {
    expect(c17IsConnReader({ readerType: 'mysql' })).toBe(true)
    expect(c17IsConnReader({ readerType: 'greatdb' })).toBe(true)
    expect(c17IsConnReader({ readerType: 'csv' })).toBe(false)
    expect(c17IsConnReader({})).toBe(true)
    expect(c17IsFileReader({ readerType: 'excel' })).toBe(true)
    expect(c17IsFileReader({ readerType: 'mysql' })).toBe(false)
  })

  it('c17OnReaderTypeChange：切连接型清文件参数；切文件型清数据源/表/schema/增量', () => {
    const d: Record<string, unknown> = {
      readerType: 'csv', readerPath: 'a.csv', readerSheet: 'S2',
      readerDs: '内置源库', readerTable: 'ods_order', readerSchemasText: 'a,b',
      autoSchema: false, incrementalColumn: 'create_time', incrementalExpr: '${d}',
    }
    c17OnReaderTypeChange(d, 'mysql')
    expect(d.readerPath).toBe('')
    expect(d.readerSheet).toBe('')
    expect(d.readerDs).toBe('内置源库') // 对方侧不动
    c17OnReaderTypeChange(d, 'csv')
    expect(d.readerDs).toBe('')
    expect(d.readerTable).toBe('')
    expect(d.readerSchemasText).toBe('')
    expect(d.autoSchema).toBe(true)
    expect(d.incrementalColumn).toBe('')
    expect(d.incrementalExpr).toBe('')
  })

  it('c17SqlPreview：单 schema 单语句；多 schema UNION ALL；src_flag 附标识列；增量列包 WHERE', () => {
    expect(c17SqlPreview({ readerType: 'mysql', readerTable: 'ods_order' })).toBe('SELECT * FROM `ods_order`')
    expect(c17SqlPreview({ readerType: 'mysql', readerTable: '' })).toBe('')
    expect(c17SqlPreview({ readerType: 'csv', readerTable: 'a' })).toBe('') // 文件型不预览
    const unionSql = c17SqlPreview({ readerType: 'mysql', readerTable: 't', readerSchemasText: 'a, b，c' })
    expect(unionSql).toContain('SELECT * FROM `a`.`t`')
    expect(unionSql).toContain('UNION ALL')
    expect(unionSql).toContain('`c`.`t`') // 中文逗号分隔兼容
    const flagSql = c17SqlPreview({ readerType: 'mysql', readerTable: 't', readerSchemasText: 'a,b', strategy: 'src_flag', flagColumn: 'src_schema' })
    expect(flagSql).toContain("'a' AS `src_schema`")
    const incSql = c17SqlPreview({ readerType: 'mysql', readerTable: 't', readerSchemasText: 'a', incrementalColumn: 'create_time', incrementalExpr: '${yyyyMMdd-1}' })
    expect(incSql).toContain('WHERE `create_time` > ${yyyyMMdd-1}')
  })
})

describe('dag profile C17/C23 I6 注册断言', () => {
  const nt = dagProfile.nodeTypes

  it('C17/C23 已注册且「数据同步」palette 组可拖（无灰置）', () => {
    expect(nt.sync?.code).toBe('C17')
    expect(nt.sync_template?.code).toBe('C23')
    const group = dagProfile.palette.find((c) => c.name === '数据同步')
    const items = (group?.items ?? []).map((i) => i.type)
    expect(items).toEqual(['sync', 'sync_template'])
    for (const it of group?.items ?? []) expect(it.disabled).toBeFalsy()
  })

  it('C17 表单/defaults 键对齐 worker sync.py 参数契约', () => {
    const keys = nt.sync!.form.map((f) => f.key)
    for (const k of [
      'readerType', 'readerDs', 'readerTable', 'readerSchemasText', 'autoSchema',
      'incrementalColumn', 'readerPath', 'readerHeader', 'readerSheet',
      'writerType', 'writerDs', 'writerTable', 'autoCreate', 'truncate',
      'strategy', 'flagColumn', 'fieldMap', 'batchSize', 'errorThreshold',
    ]) expect(keys).toContain(k)
    expect(nt.sync!.form.find((f) => f.key === 'fieldMap')?.type).toBe('kv-table')
    // defaults：strategy=union 缺省、autoSchema=true（裁定②）、批大小 1000
    expect(nt.sync!.defaults?.strategy).toBe('union')
    expect(nt.sync!.defaults?.autoSchema).toBe(true)
    expect(nt.sync!.defaults?.batchSize).toBe(1000)
    // 标识列仅在 src_flag 显示；SQL 预览 hint 动态产出
    expect(nt.sync!.form.find((f) => f.key === 'flagColumn')?.showIf?.({ strategy: 'union' })).toBe(false)
    expect(nt.sync!.form.find((f) => f.key === 'flagColumn')?.showIf?.({ strategy: 'src_flag' })).toBe(true)
    const previewF = nt.sync!.form.find((f) => f.key === 'sqlPreview')
    expect(previewF?.type).toBe('hint')
    expect(previewF!.text!({ readerType: 'mysql', readerTable: 't', strategy: 'src_flag', readerSchemasText: 'a' })).toContain('src_schema')
  })

  it('C23 两套模板 build 展开：开始→同步→对账→结束，差异仅 C17 defaults 策略', () => {
    const modes = nt.sync_template!.template!.modes
    expect(modes.map((m) => m.key)).toEqual(['source_base', 'target_base'])
    const doc = { id: 'wf_x', name: 'x', version: 1, meta: {}, nodes: [], edges: [] } as unknown as GraphDocument
    const a = modes[0].build({ doc, pos: { x: 0, y: 0 } })
    expect(a.nodes.map((n) => n.type)).toEqual(['start', 'sync', 'sql', 'end'])
    expect(a.edges).toHaveLength(3)
    expect(a.nodes.find((n) => n.type === 'sync')!.data.strategy).toBe('union')
    const b = modes[1].build({ doc, pos: { x: 0, y: 0 } })
    const syncB = b.nodes.find((n) => n.type === 'sync')!
    expect(syncB.data.strategy).toBe('src_flag')
    expect(syncB.data.autoSchema).toBe(true)
    expect(syncB.data.flagColumn).toBe('src_schema')
    // 展开产物均为标准组件节点（引擎零改动）；对账节点预置 SQL 模板
    for (const n of [...a.nodes, ...b.nodes]) expect(dagProfile.nodeTypes[n.type]).toBeTruthy()
    expect(String(a.nodes.find((n) => n.type === 'sql')!.data.sql)).toContain('COUNT(*)')
  })
})
