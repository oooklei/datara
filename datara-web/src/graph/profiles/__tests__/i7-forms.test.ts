/**
 * I7 i7-1 留痕（设计文档 §3.1/§3.2 + §1.2 本机验证门）：
 * - C21 变量组件：palette 解禁、defaults 示例行、summary 变量名清单、老数据归一化；
 * - C9 依赖组件：deps-list 表单升级、老数据（字符串 deps）兼容归一化、summary 产出。
 * 防回归锁点：C21/C9 表单类型漂移、palette 灰置状态漂移。
 */
import { describe, it, expect } from 'vitest'
import type { ConditionDef } from '../types'
import { dagProfile, varRowsOf, depRowsOf, varSummary, depSummary } from '../dag'

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

describe('I7 C21 变量组件（F51）', () => {
  it('palette 变量分组解禁（无 disabled / 无 phase 灰置标记）', () => {
    const grp = dagProfile.palette.find((g) => g.name === '变量')
    const item = grp?.items?.find((i) => i.type === 'variable')
    expect(item).toBeTruthy()
    expect(item!.disabled).toBeFalsy()
    expect(item!.phase).toBeUndefined()
  })

  it('defaults 含示例行 wf.period=20261001（字面量，默认不覆盖）', () => {
    const defaults = dagProfile.nodeTypes.variable.defaults ?? {}
    const rows = varRowsOf(defaults)
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ name: 'wf.period', value: '20261001', type: 'literal', override: false })
  })

  it('业务表单为 rows·var（变量表）且含 $[wf.*] 引用提示（hint）', () => {
    const form = dagProfile.nodeTypes.variable.form
    expect(form.some((f) => f.type === 'rows' && f.rowsKind === 'var')).toBe(true)
    const hint = form.find((f) => f.type === 'hint')
    const text = hint?.text
    const textStr = typeof text === 'function' ? text({}) : text
    expect(textStr).toContain('$[wf.')
  })

  it('summary 显示变量名清单；空表回退未配置变量', () => {
    expect(varSummary({ vars: [{ name: 'wf.period', value: 'x', type: 'literal', override: false }] })).toBe('注入 wf.period')
    expect(varSummary({ vars: [{ name: 'wf.period', value: '1', type: 'literal', override: false }, { name: 'wf.batch', value: '2', type: 'literal', override: false }] })).toBe('注入 wf.period、wf.batch')
    expect(varSummary({})).toBe('未配置变量')
    expect(varSummary({ vars: [{ name: '', value: 'x', type: 'literal', override: false }] })).toBe('未配置变量')
  })

  it('varRowsOf 对非数组老数据回退空数组（向后兼容）', () => {
    expect(varRowsOf({ vars: 'legacy' })).toEqual([])
    expect(varRowsOf({})).toEqual([])
  })
})

describe('I7 C9 依赖组件（F52）', () => {
  it('业务表单为 rows·deps（依赖项列表，原 textarea 占位废除）', () => {
    const form = dagProfile.nodeTypes.dependent.form
    expect(form).toHaveLength(1)
    expect(form[0].key).toBe('deps')
    expect(form[0].type).toBe('rows')
    expect(form[0].rowsKind).toBe('deps')
  })

  it('老数据 deps 为字符串时归一化为空数组（不抛错）', () => {
    expect(depRowsOf({ deps: 'WF-A/节点a' })).toEqual([])
    expect(depRowsOf({})).toEqual([])
  })

  it('deps 数组行原样返回', () => {
    const rows = [{ wf: 'wf_1', node: 'nd_1', cond: '' }]
    expect(depRowsOf({ deps: rows })).toEqual(rows)
  })

  it('summary：未配置回退；已配置显示 工作流名/节点名', () => {
    expect(depSummary({})).toBe('未配置依赖')
    expect(depSummary({ deps: [{ wf: 'wf_1', node: 'nd_9', cond: '', wfName: 'A流', nodeName: '节点a' }] })).toBe('A流/节点a')
    expect(depSummary({ deps: [{ wf: 'wf_1', node: 'nd_9', cond: '' }] })).toBe('wf_1/nd_9')
  })
})

describe('I7 C14 执行节点标签（F53）', () => {
  it('表单含执行节点标签 select（selectFrom: exec-node-tags）；未选标签时才显示运行时节点字段（conditions 联动）', () => {
    const schema = dagProfile.nodeTypes.ssh
    const form = schema.form
    const tagField = form.find((f) => f.type === 'select' && f.selectFrom === 'exec-node-tags')
    const nodeField = form.find((f) => f.type === 'resource' && f.cap?.mode === 'runtimeNode')
    expect(tagField).toBeTruthy()
    expect(tagField!.key).toBe('execNodeTag')
    expect(nodeField).toBeTruthy()
    // showIf → conditions：execNodeTag 为空时显示 runtimeNode（两种寻址互斥，标签优先）
    expect(schema.conditions?.find((c) => c.show.includes('runtimeNode'))).toMatchObject({
      when: { field: 'execNodeTag', op: 'empty' },
    })
    // 分型显隐按声明等价求值
    expect(condVisible(schema, 'runtimeNode', { execNodeTag: '' })).toBe(true)
    expect(condVisible(schema, 'runtimeNode', { execNodeTag: 'etl' })).toBe(false)
  })

  it('summary 已迁 render.summary 常量兜底：通用文案保留，动态优先级模板（标签→运行时节点）待 summaryRules 落地', () => {
    const schema = dagProfile.nodeTypes.ssh
    // M-B2 迁移契约：函数 summary 已迁出（未迁移组件仍可为函数），通用兜底文案由 render.summary 声明
    expect(schema.summary).toBeUndefined()
    expect(schema.render?.summary).toBe('SSH 远程脚本')
  })
})
