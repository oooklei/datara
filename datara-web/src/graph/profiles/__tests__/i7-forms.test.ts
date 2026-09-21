/**
 * I7 i7-1 留痕（设计文档 §3.1/§3.2 + §1.2 本机验证门）：
 * - C21 变量组件：palette 解禁、defaults 示例行、summary 变量名清单、老数据归一化；
 * - C9 依赖组件：deps-list 表单升级、老数据（字符串 deps）兼容归一化、summary 产出。
 * 防回归锁点：C21/C9 表单类型漂移、palette 灰置状态漂移。
 */
import { describe, it, expect } from 'vitest'
import { dagProfile, varRowsOf, depRowsOf, varSummary, depSummary } from '../dag'

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

  it('业务表单为 var-table 且含 $[wf.*] 引用提示（hint）', () => {
    const form = dagProfile.nodeTypes.variable.form
    expect(form.some((f) => f.type === 'var-table')).toBe(true)
    const hint = form.find((f) => f.type === 'hint')
    expect(hint?.text?.({})).toContain('$[wf.')
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
  it('业务表单升级为 deps-list（原 textarea 占位废除）', () => {
    const form = dagProfile.nodeTypes.dependent.form
    expect(form).toHaveLength(1)
    expect(form[0].key).toBe('deps')
    expect(form[0].type).toBe('deps-list')
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
  it('表单含 exec-node-tag 字段；未选标签时才显示 runtime-node 字段（showIf 联动）', () => {
    const form = dagProfile.nodeTypes.ssh.form
    const tagField = form.find((f) => f.type === 'exec-node-tag')
    const nodeField = form.find((f) => f.type === 'runtime-node')
    expect(tagField).toBeTruthy()
    expect(tagField!.key).toBe('execNodeTag')
    expect(nodeField).toBeTruthy()
    expect(nodeField!.showIf!({ execNodeTag: '' })).toBe(true)
    expect(nodeField!.showIf!({ execNodeTag: 'etl' })).toBe(false)
  })

  it('summary：标签优先，其次运行时节点，均空回退通用文案', () => {
    const summary = dagProfile.nodeTypes.ssh.summary!
    expect(summary({ execNodeTag: 'etl', runtimeNode: '1.9宿主机' })).toBe('SSH @ 标签:etl')
    expect(summary({ execNodeTag: '', runtimeNode: '1.9宿主机' })).toBe('SSH @ 1.9宿主机')
    expect(summary({})).toBe('SSH 远程脚本')
  })
})
