/**
 * 组件页面设计器 Task 6 + Task 7：PageDSL 模型/归一化/校验 + 模板单测。
 * 与后端 api/component_design.py _validate_page_spec 同口径
 * （kind 白名单 43 项 / 绑定 fallback 必填 / 画布钳制 140-1920 / 160-2160）。
 * 纯函数用例，无需 DOM。导入 templates.ts 即完成 bindTemplates 注入（模块顶层侧效应）。
 */
import { describe, expect, it } from 'vitest'
import { newWidget, normalizePage, validatePage, WIDGET_KINDS } from '../designerModel'
import { widgetGroups, widgetTemplate, pageTemplates } from '../templates'

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

describe('templates', () => {
  it('六大分组 43 个 widget 全部带模板', () => {
    const all = widgetGroups.flatMap((g) => g.items)
    expect(all.length).toBe(43)
    expect(new Set(all.map((w) => w.kind)).size).toBe(43)
    all.forEach((w) => expect(widgetTemplate(w.kind)).toBeTruthy())
  })
  it('模板 kind 与 WIDGET_KINDS 白名单双向一致（防漂移/防 typo）', () => {
    const all = widgetGroups.flatMap((g) => g.items)
    expect(new Set(all.map((w) => w.kind))).toEqual(WIDGET_KINDS)
  })
  it('页面级模板 4 套且均可生成', () => {
    expect(pageTemplates.map((t) => t.name)).toEqual(['空白页', '数据看板', '表单页', '列表页'])
    pageTemplates.forEach((t) => expect(Array.isArray(t.page().widgets)).toBe(true))
  })
  it('bindTemplates 已注入：newWidget 套真实模板', () => {
    const w = newWidget('table', { x: 4, y: 4 })
    expect((w.props as Record<string, unknown>).columns).toBeTruthy()
    expect(w.rect.w).toBeGreaterThan(0)
  })
})
