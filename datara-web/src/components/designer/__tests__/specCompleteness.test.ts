/**
 * Task 6（方案§2.1/§2.6）：specCompleteness 纯函数单测 + SpecCompletenessBadge 挂载用例。
 * 覆盖计划草案 3 例（测试 1 按「实现为准」裁定补 type 字段——type 在草稿创建时必生成，
 * canDrop=身份齐∧表现齐，缺 type 身份不齐）与 logical 组件 / layer optional / 空 spec 边界。
 */
// @vitest-environment happy-dom
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { specCompleteness, isRequiredField } from '../specCompleteness'
import SpecCompletenessBadge from '../SpecCompletenessBadge.vue'

describe('specCompleteness（8 要素 4 组完整度）', () => {
  it('计划草案 1：身份+表现齐 → canDrop=true（裁定补 type；扩展组恒完成）', () => {
    const r = specCompleteness({
      type: 'op_demo', icon: '⬢', color: '#1677ff', summary: '演示组件',
      fields: [{ required: true }],
      outputs: [{ name: 'out', type: 'table' }],
    })
    expect(r.canDrop).toBe(true)
    expect(r.missing).toEqual([])
    expect(r.groups.map((g) => g.done)).toEqual([true, true, true, true])
  })

  it('计划草案 2：缺 type → 身份不齐 canDrop=false（实现为准裁定），契约/表现缺项入清单', () => {
    const r = specCompleteness({ summary: '', fields: [{ required: false }] })
    expect(r.canDrop).toBe(false)
    expect(r.missing).toEqual(['type', 'summary', 'fields.required', 'outputs', 'icon'])
    expect(r.groups[0].missing).toEqual(['type', 'summary'])
    expect(r.groups[1].missing).toEqual(['fields.required', 'outputs'])
    expect(r.groups[2].missing).toEqual(['icon'])
  })

  it('计划草案 3：layer optional 不计 required；layer 缺省视为 required（Task 2 既定语义）', () => {
    // 输入 fields 为 Task 2 归一后形态（normField 已把 layer 缺省补 'required'），判定式按字面匹配
    const optionalOnly = specCompleteness({
      type: 'op_x', summary: 's', icon: 'i',
      fields: [{ required: false, layer: 'optional' }],
      outputs: [{ name: 'out', type: 'table' }],
    })
    expect(optionalOnly.groups[1].missing).toContain('fields.required')

    const layerRequired = specCompleteness({
      type: 'op_x', summary: 's', icon: 'i',
      fields: [{ required: false, layer: 'required' }],
      outputs: [{ name: 'out', type: 'table' }],
    })
    expect(layerRequired.groups[1].missing).not.toContain('fields.required')
    const requiredByFlag = specCompleteness({
      type: 'op_x', summary: 's', icon: 'i',
      fields: [{ required: true, layer: 'optional' }],
      outputs: [{ name: 'out', type: 'table' }],
    })
    expect(requiredByFlag.groups[1].missing).not.toContain('fields.required')
    // 字面判定式：归一（缺省补 required）由上游 normField 负责，本函数不做缺省兜底
    expect(isRequiredField({ required: false, layer: 'required' })).toBe(true)
    expect(isRequiredField({ required: true })).toBe(true)
    expect(isRequiredField({})).toBe(false)
  })

  it('logical 组件豁免 outputs 缺项；非逻辑无 outputs 报缺', () => {
    const logical = specCompleteness({ type: 'page_x', summary: 's', icon: 'i', fields: [{ required: true }], logical: true })
    expect(logical.groups[1].missing).toEqual([])
    const dataComp = specCompleteness({ type: 'op_x', summary: 's', icon: 'i', fields: [{ required: true }], logical: false })
    expect(dataComp.groups[1].missing).toEqual(['outputs'])
    // 缺省（undefined）按非逻辑处理，报 outputs 缺项
    const omitted = specCompleteness({ type: 'op_x', summary: 's', icon: 'i', fields: [{ required: true }] })
    expect(omitted.groups[1].missing).toEqual(['outputs'])
    // 空数组 outputs 视为未声明
    const empty = specCompleteness({ type: 'op_x', summary: 's', icon: 'i', fields: [{ required: true }], outputs: [], logical: false })
    expect(empty.groups[1].missing).toEqual(['outputs'])
  })

  it('空 spec：全组缺项（除扩展），canDrop=false', () => {
    const r = specCompleteness({})
    expect(r.missing).toEqual(['type', 'summary', 'fields.required', 'outputs', 'icon'])
    expect(r.groups[3]).toEqual({ id: 'extension', missing: [], done: true })
    expect(r.canDrop).toBe(false)
  })

  it('canDrop 仅看身份∧表现：契约缺项不阻塞拖入（方案§2.1 最低门槛）', () => {
    const r = specCompleteness({ type: 'op_x', summary: 's', icon: 'i', fields: [] })
    expect(r.canDrop).toBe(true)
    expect(r.missing).toEqual(['fields.required', 'outputs'])
  })
})

describe('SpecCompletenessBadge（缺项 chips 点击直达）', () => {
  it('完整态：绿色「8/8」，无 chips，不 emit goto', () => {
    const w = mount(SpecCompletenessBadge, {
      props: { result: specCompleteness({ type: 'x', summary: 's', icon: 'i', fields: [{ required: true }], outputs: [{}] }) },
    })
    expect(w.find('[data-testid="scb-ok"]').exists()).toBe(true)
    expect(w.find('[data-testid="scb-ok"]').text()).toContain('8/8')
    expect(w.findAll('[data-testid^="scb-chip-"]').length).toBe(0)
    expect(w.emitted('goto')).toBeUndefined()
  })

  it('缺项态：黄色 chips 按组渲染，点击 chip emit 对应组 id', async () => {
    const w = mount(SpecCompletenessBadge, {
      // summary 已填：缺 type（身份）+ fields.required/outputs（契约）+ icon（表现）
      props: { result: specCompleteness({ summary: 's' }) },
    })
    expect(w.find('[data-testid="scb-miss"]').exists()).toBe(true)
    const chips = w.findAll('[data-testid^="scb-chip-"]')
    // chip 以缺项 key 为 testid 后缀，按组序渲染
    expect(chips.map((c) => c.attributes('data-testid')))
      .toEqual(['scb-chip-type', 'scb-chip-fields.required', 'scb-chip-outputs', 'scb-chip-icon'])
    await chips[0].trigger('click')
    await chips[1].trigger('click')
    expect(w.emitted('goto')).toEqual([['identity'], ['contract']])
  })
})
