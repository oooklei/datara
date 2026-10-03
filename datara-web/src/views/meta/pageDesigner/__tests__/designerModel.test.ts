/**
 * 组件页面设计器 Task 6 + Task 7：PageDSL 模型/归一化/校验 + 模板单测。
 * 与后端 api/component_design.py _validate_page_spec 同口径
 * （kind 白名单 43 项 / 绑定 fallback 必填 / 画布钳制 宽 140-520 / 高 320-1200）。
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
    const p = normalizePage({ page: { version: 1, widgets: [
      { kind: 'nope', bindings: { value: { kind: 'metadata' } } },
    ] } })
    p.canvas.width = 10 // 越界值直改 DSL（normalizePage 钳制在先，钳制行为另测）
    const vs = validatePage(p)
    expect(vs.some((v) => v.includes('kind'))).toBe(true)
    expect(vs.some((v) => v.includes('fallback'))).toBe(true)
    expect(vs.some((v) => v.includes('canvas'))).toBe(true)
  })
  it('validatePage：query 绑定 datasourceId 或 query 二者有其一即合法，皆缺才违规（镜像后端形状）', () => {
    const mk = (b: Record<string, unknown>) => validatePage(normalizePage({ page: { version: 1, widgets: [
      { kind: 'table', bindings: { data: b } },
    ] } }))
    expect(mk({ kind: 'query', datasourceId: 1, fallback: '数据集' })).toEqual([])
    expect(mk({ kind: 'query', query: 'SELECT 1', fallback: '数据集' })).toEqual([])
    const vs = mk({ kind: 'query', fallback: '数据集' })
    expect(vs.some((v) => v.includes('datasourceId 或 query'))).toBe(true)
  })
  it('validatePage：画布尺寸边界（设计口径 宽 140-520 / 高 320-1200）', () => {
    // normalizePage 会钳制画布值，边界校验直改 DSL 绕开钳制，单测 validatePage 分支
    const mk = (width: number, height: number) => {
      const p = normalizePage({ page: { version: 1, widgets: [] } })
      p.canvas.width = width
      p.canvas.height = height
      return validatePage(p)
    }
    expect(mk(140, 320)).toEqual([])
    expect(mk(520, 1200)).toEqual([])
    expect(mk(139, 520).some((v) => v.includes('canvas'))).toBe(true)
    expect(mk(521, 520).some((v) => v.includes('canvas'))).toBe(true)
    expect(mk(288, 319).some((v) => v.includes('canvas'))).toBe(true)
    expect(mk(288, 1201).some((v) => v.includes('canvas'))).toBe(true)
  })
  it('normalizePage 钳制旧草稿越界尺寸（旧口径 宽 1920 / 高 2000 → 新口径合法）', () => {
    const p = normalizePage({ page: { version: 1, canvas: { width: 1920, height: 2000 }, widgets: [] } })
    expect(p.canvas.width).toBe(520)
    expect(p.canvas.height).toBe(1200)
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
