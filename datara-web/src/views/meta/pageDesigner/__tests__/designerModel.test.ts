/**
 * 组件页面设计器 Task 6：PageDSL 模型/归一化/校验单测。
 * 与后端 api/component_design.py _validate_page_spec 同口径
 * （kind 白名单 43 项 / 绑定 fallback 必填 / 画布钳制 140-1920 / 160-2160）。
 * 纯函数用例，无需 DOM。
 */
import { describe, expect, it } from 'vitest'
import { bindTemplates, newWidget, normalizePage, validatePage } from '../designerModel'

/** Task 7 才有真实模板；此处注入最小桩模板让 newWidget 工厂用例独立可测。 */
bindTemplates((kind) =>
  kind === 'text'
    ? { props: { text: '示例' }, style: {}, rect: { x: 0, y: 0, w: 120, h: 24 } }
    : undefined,
)

describe('designerModel', () => {
  it('normalizePage 补齐缺省（画布 288×520、widget id）', () => {
    const p = normalizePage({ page: { version: 1, widgets: [{ kind: 'text' }] } })
    expect(p.canvas.width).toBe(288)
    expect(p.canvas.height).toBe(520)
    expect(p.widgets[0].id).toMatch(/^w_/)
    expect(p.widgets[0].style).toEqual({})
  })
  it('validatePage：未知 kind / 绑定缺 fallback / 尺寸越界', () => {
    const p = normalizePage({ page: { version: 1, canvas: { width: 10, height: 520 }, widgets: [
      { kind: 'nope', bindings: { value: { kind: 'metadata' } } },
    ] } })
    const vs = validatePage(p)
    expect(vs.some((v) => v.includes('kind'))).toBe(true)
    expect(vs.some((v) => v.includes('fallback'))).toBe(true)
    expect(vs.some((v) => v.includes('canvas'))).toBe(true)
  })
  it('newWidget 套模板：rect/props/style 来自模板', () => {
    const w = newWidget('text', { x: 10, y: 10 })
    expect(w.props.text).toBeTruthy()
    expect(w.rect.w).toBeGreaterThan(0)
  })
})
