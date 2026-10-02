/**
 * 表单分组纯函数 + 模板向导「可配置内容」判定单测。
 *
 * 覆盖三件事：
 *  1. `formSections` 切分口径：相邻同组合并、交错切段、无 group 保持平铺（88 个组件零回归的根据）
 *  2. 分组标题/副标题语义（`groupHint` 取组内首个）
 *  3. `hasConfigurableContent` 与 configure-first 一致：有表单/六区块有值才需用户配置，
 *     纯装饰节点（C1 开始 / C2 结束）判 false → 模板向导跳过
 */
import { describe, expect, it } from 'vitest'
import { formSections, hasConfigurableContent, hasGroupTitle } from '../formSections'
import type { FieldSchema } from '../types'
import { dagProfile } from '../dag'
import { streamProfile } from '../stream'

const f = (key: string, group?: string, groupHint?: string): FieldSchema => ({
  key, label: key, type: 'text', ...(group ? { group } : {}), ...(groupHint ? { groupHint } : {}),
})

/** 按 type 取内置 schema（DAG / stream 两视图合并，覆盖跨视图复用组件） */
function schemaOf(type: string): { form: FieldSchema[]; defaults?: Record<string, unknown> } {
  const s = dagProfile.nodeTypes[type] ?? streamProfile.nodeTypes[type]
  if (!s) throw new Error(`未找到组件 schema: ${type}`)
  return s as { form: FieldSchema[]; defaults?: Record<string, unknown> }
}

describe('formSections', () => {
  it('全部无 group → 单一平铺段且不出标题（既有组件呈现逐字不变）', () => {
    const secs = formSections([f('a'), f('b'), f('c')])
    expect(secs).toHaveLength(1)
    expect(secs[0]!.key).toBe('')
    expect(secs[0]!.fields.map((x) => x.key)).toEqual(['a', 'b', 'c'])
    expect(hasGroupTitle(secs[0]!)).toBe(false)
  })

  it('相邻同组合并为一段，标题/副标题取声明值', () => {
    const secs = formSections([
      f('mode', 'base', '决定源端形态'),
      f('ds', 'src'),
      f('table', 'src'),
      f('tgtDs', 'tgt', '数据落到哪'),
    ])
    expect(secs.map((s) => s.key)).toEqual(['base', 'src', 'tgt'])
    expect(secs[0]!.hint).toBe('决定源端形态')
    expect(secs[1]!.hint).toBe('')
    expect(secs[2]!.hint).toBe('数据落到哪')
    expect(secs.every(hasGroupTitle)).toBe(true)
  })

  it('同组交错（A-B-A）→ 切为两段，每段字段保持声明序', () => {
    const secs = formSections([f('a1', 'A'), f('b1', 'B'), f('a2', 'A')])
    expect(secs.map((s) => s.key)).toEqual(['A', 'B', 'A'])
    expect(secs[0]!.fields.map((x) => x.key)).toEqual(['a1'])
    expect(secs[2]!.fields.map((x) => x.key)).toEqual(['a2'])
  })

  it('空表单 → 零段（不产出空区块）', () => {
    expect(formSections([])).toEqual([])
  })

  it('入参已是 showIf 过滤后的可见字段：整组隐藏则该段不出现', () => {
    // 模拟 endpoint_select 切到 file_sync：源端/目标端隐藏后仅剩同步基准 + 文件源 + 目标端
    const visible = [f('baseMode', '同步基准'), f('filePath', '文件源'), f('tgtDs', '目标端')]
    expect(formSections(visible).map((s) => s.key)).toEqual(['同步基准', '文件源', '目标端'])
  })
})

describe('hasConfigurableContent（模板向导跳过判据）', () => {
  it('有业务表单字段 → 需配置', () => {
    expect(hasConfigurableContent([f('a')], {})).toBe(true)
  })

  it('纯装饰节点（form 空 + 六区块无值）→ 跳过（C1 开始 / C2 结束）', () => {
    expect(hasConfigurableContent([], {})).toBe(false)
    expect(hasConfigurableContent([], { inputs: [], params: [], outputs: { params: [], tables: [] } })).toBe(false)
  })

  it('六区块任一有值/引用 → 需配置', () => {
    expect(hasConfigurableContent([], { inputs: ['nd_1'] })).toBe(true)
    expect(hasConfigurableContent([], { params: [{ k: 'a' }] })).toBe(true)
    expect(hasConfigurableContent([], { outputs: { tables: [{ k: 't1' }] } })).toBe(true)
    expect(hasConfigurableContent([], { condition: 'x > 1' })).toBe(true)
    expect(hasConfigurableContent([], { constraints: ['c1'] })).toBe(true)
    expect(hasConfigurableContent([], { exclude: ['e1'] })).toBe(true)
  })

  it('六区块的「空值形态」不算有内容（0/空串/false 不触发）', () => {
    expect(hasConfigurableContent([], { condition: '', constraints: [], exclude: false })).toBe(false)
  })

  it('C1 开始 / C2 结束 在真实 profile 下判为跳过', () => {
    for (const type of ['start', 'end']) {
      const p = schemaOf(type)
      expect(p.form).toEqual([])
      expect(hasConfigurableContent(p.form, { ...(p.defaults ?? {}) })).toBe(false)
    }
  })
})

describe('已分组的模板链组件（分组回归护栏）', () => {
  it('C37 endpoint_select：源端/文件源/目标端/同步基准四组齐备', () => {
    const keys = new Set(schemaOf('endpoint_select').form.map((x) => x.group ?? ''))
    for (const g of ['同步基准', '源端', '文件源', '目标端']) expect(keys).toContain(g)
  })

  it('C36 field_map_union：联合输入/来源标识/合并与输出分组', () => {
    const keys = new Set(schemaOf('field_map_union').form.map((x) => x.group ?? ''))
    for (const g of ['联合输入', '来源标识', '合并与输出']) expect(keys).toContain(g)
  })

  it('C35 condition_set：数据流 / 筛选与增量', () => {
    const keys = new Set(schemaOf('condition_set').form.map((x) => x.group ?? ''))
    for (const g of ['数据流', '筛选与增量']) expect(keys).toContain(g)
  })

  it('C11 SQL：执行目标 / SQL 脚本', () => {
    const keys = new Set(schemaOf('sql').form.map((x) => x.group ?? ''))
    for (const g of ['执行目标', 'SQL 脚本']) expect(keys).toContain(g)
  })

  it('C37 切到 file_sync 模式时，源端/目标端字段被 showIf 隐藏 → 分组不残留空卡', () => {
    const form = schemaOf('endpoint_select').form
    const visible = form.filter((x) => (x.showIf ? x.showIf({ baseMode: 'file_sync' }) : true))
    const secs = formSections(visible)
    // 源端组字段（srcDs）在 file_sync 下全部隐藏 → 不应出现「源端」段
    expect(secs.map((s) => s.key)).not.toContain('源端')
    expect(secs.map((s) => s.key)).toContain('文件源')
  })

  it('stream 输出的 uniqueKey 仍带 dataScope 声明（分组不得丢值域闸门）', () => {
    const uq = schemaOf('stream_output').form.find((x) => x.key === 'uniqueKey')
    expect(uq?.dataScope).toBe('upstream-columns')
  })

  it('condition_set 的 incrementalColumn 仍带 dataScope（值域闸门在分组后仍生效）', () => {
    const inc = schemaOf('condition_set').form.find((x) => x.key === 'incrementalColumn')
    expect(inc?.dataScope).toBe('upstream-columns')
  })
})
