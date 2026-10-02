/**
 * B4：组件声明纯数据校验单测（红线 2 前端镜像，与后端 api/component_design.py
 * validate_spec_pure_data 同口径——设计器「打字即校验」行内红标的判定真源）。
 * 纯函数用例，无需 DOM。
 */
import { describe, expect, it } from 'vitest'
import { normalizeSpec, SPEC_UI_TYPES, validateSpecPureData } from '../componentSpec'

describe('validateSpecPureData（红线 2 前端镜像）', () => {
  it('非对象声明直接违规', () => {
    expect(validateSpecPureData(null)[0].msg).toContain('JSON 对象')
    expect(validateSpecPureData('x')[0].msg).toContain('JSON 对象')
    expect(validateSpecPureData([1])[0].msg).toContain('JSON 对象')
  })

  it('干净声明通过（autoName 仅 {type}/{n} 白名单）', () => {
    const spec = {
      icon: '⚙',
      fields: [{ key: 'sql', label: 'SQL', uiType: 'text' }],
      dropPolicy: { autoName: 'SQL转换_{n}', maxInstances: 0 },
    }
    expect(validateSpecPureData(spec)).toEqual([])
  })

  it('字符串值含代码片段 → 违规路径定位到字段', () => {
    const out = validateSpecPureData({ fields: [{ key: 'a', label: 'x => y' }] })
    expect(out.length).toBe(1)
    expect(out[0].path).toBe('fields[0].label')
    expect(out[0].msg).toContain('=>')
  })

  it('字段名含片段（键大小写不敏感兜底）→ 违规', () => {
    const out = validateSpecPureData({ FunctionMap: 1 })
    expect(out.length).toBe(1)
    expect(out[0].path).toBe('FunctionMap')
    expect(out[0].msg).toContain('function')
  })

  it('NaN/Infinity 数值 → 违规（JSON.stringify 会静默变 null，编辑期必须拦住）', () => {
    const out = validateSpecPureData({ dropPolicy: { maxInstances: Number.NaN } })
    expect(out.length).toBe(1)
    expect(out[0].path).toBe('dropPolicy.maxInstances')
  })

  it('autoName 非白名单占位符 → dropPolicy.autoName 违规', () => {
    const out = validateSpecPureData({ dropPolicy: { autoName: '{type}_{date}' } })
    expect(out.length).toBe(1)
    expect(out[0].path).toBe('dropPolicy.autoName')
    expect(out[0].msg).toContain('{date}')
  })

  it('模板语法 ${…} 与反引号 → 违规', () => {
    expect(validateSpecPureData({ summary: '${env.HOME}' }).length).toBe(1)
    expect(validateSpecPureData({ summary: '`id`' }).length).toBe(1)
  })
})

describe('normalizeSpec（服务端 spec → 编辑器规范化骨架）', () => {
  it('冻结空草稿 {} → 完整可编辑形态', () => {
    const s = normalizeSpec({})
    expect(s.fields).toEqual([])
    expect(s.ports.inputs).toEqual([])
    expect(s.ports.outputs).toEqual([])
    expect(s.dropPolicy.autoName).toBe('')
    expect(s.dropPolicy.maxInstances).toBe(0)
    expect(s.dropPolicy.autoConnect).toEqual({ upstream: 'nearest', downstream: 'nearest' })
  })

  it('未知 uiType 降级为 text；select 字段保留 options，非 select 不携带', () => {
    const s = normalizeSpec({
      fields: [
        { key: 'a', uiType: 'widget' },
        { key: 'b', uiType: 'select', options: [{ label: 'X', value: 'x' }, { label: 'N', value: 3 }] },
      ],
    })
    expect(s.fields[0].uiType).toBe('text')
    expect(s.fields[0].options).toBeUndefined() // 非 select 字段不携带 options
    expect(s.fields[1].uiType).toBe('select')
    expect(s.fields[1].options).toEqual([{ label: 'X', value: 'x' }, { label: 'N', value: 3 }])
  })

  it('uiType 白名单 = B3 收敛 FieldKind 9 基元', () => {
    expect(SPEC_UI_TYPES.map((t) => t.value)).toEqual(
      ['text', 'number', 'bool', 'select', 'expr', 'hint', 'rows', 'mapEditor', 'resource'])
  })

  it('paletteVisible：缺省 true；显式 false 保留（D1 闸门 §13-5 runtime-only 强制位）', () => {
    expect(normalizeSpec({}).paletteVisible).toBe(true)
    expect(normalizeSpec({ paletteVisible: false }).paletteVisible).toBe(false)
    expect(normalizeSpec({ paletteVisible: true }).paletteVisible).toBe(true)
  })
})
