/**
 * 组件页面设计器 Task 6 + Task 7：PageDSL 模型/归一化/校验 + 模板单测。
 * 与后端 api/component_design.py _validate_page_spec 同口径
 * （kind 白名单 43 项 / 绑定 fallback 必填 / 画布钳制 宽 140-520 / 高 320-1200）。
 * 纯函数用例，无需 DOM。导入 templates.ts 即完成 bindTemplates 注入（模块顶层侧效应）。
 */
import { describe, expect, it } from 'vitest'
import { alignRects, distributeRects, newWidget, normalizePage, reorderWidget, validatePage, WIDGET_KINDS, type WidgetNode } from '../designerModel'
import { widgetGroups, widgetTemplate, pageTemplates, componentSeedPage } from '../templates'

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

describe('reorderWidget（D5/M6 层级控制，数组序 = z 序，靠后者在上层渲染）', () => {
  const mk = (ids: string[]): WidgetNode[] =>
    ids.map((id) => ({ id, kind: 'text', rect: { x: 0, y: 0, w: 10, h: 10 }, props: {}, style: {}, bindings: {} }))

  it('四动作：top 移末尾 / bottom 移开头 / up 与后一位交换 / down 与前一位交换', () => {
    expect(reorderWidget(mk(['a', 'b', 'c']), 'a', 'top').map((w) => w.id)).toEqual(['b', 'c', 'a'])
    expect(reorderWidget(mk(['a', 'b', 'c']), 'c', 'bottom').map((w) => w.id)).toEqual(['c', 'a', 'b'])
    expect(reorderWidget(mk(['a', 'b', 'c']), 'b', 'up').map((w) => w.id)).toEqual(['a', 'c', 'b'])
    expect(reorderWidget(mk(['a', 'b', 'c']), 'b', 'down').map((w) => w.id)).toEqual(['b', 'a', 'c'])
  })

  it('边界：单元素 / 找不到 id / 已到界 → 等价副本；恒新数组不改入参', () => {
    const src = mk(['a', 'b'])
    const ids = () => src.map((w) => w.id)
    // 单元素
    expect(reorderWidget([src[0]], 'a', 'top').map((w) => w.id)).toEqual(['a'])
    // 找不到 id
    expect(reorderWidget(src, 'zz', 'top').map((w) => w.id)).toEqual(['a', 'b'])
    // 已到界（b 已在顶：再 top / 再 up 无位移；a 已在底：再 bottom / 再 down 无位移）
    expect(reorderWidget(src, 'b', 'top').map((w) => w.id)).toEqual(['a', 'b'])
    expect(reorderWidget(src, 'a', 'bottom').map((w) => w.id)).toEqual(['a', 'b'])
    expect(reorderWidget(src, 'b', 'up').map((w) => w.id)).toEqual(['a', 'b'])
    expect(reorderWidget(src, 'a', 'down').map((w) => w.id)).toEqual(['a', 'b'])
    // up/down 有位移（a 在底层 up 与后一位交换；b 在顶层 down 与前一位交换）
    expect(reorderWidget(src, 'a', 'up').map((w) => w.id)).toEqual(['b', 'a'])
    expect(reorderWidget(src, 'b', 'down').map((w) => w.id)).toEqual(['b', 'a'])
    // 入参不被修改 + 返回新数组（不可变）
    expect(ids()).toEqual(['a', 'b'])
    expect(reorderWidget(src, 'a', 'top')).not.toBe(src)
  })
})

describe('distributeRects / alignRects（多选等距分布与对齐，纯函数）', () => {
  const mk = (id: string, x: number, y: number): WidgetNode => ({
    id, kind: 'text', rect: { x, y, w: 10, h: 10 }, props: { t: id }, style: { fill: '#fff' }, bindings: {},
  })

  it('distributeRects：3 元素 x 轴等距（首尾不动，中间 round(first+i*(last-first)/(n-1))）', () => {
    const ws = [mk('a', 0, 0), mk('b', 20, 5), mk('c', 100, 10)]
    const out = distributeRects(ws, ['a', 'b', 'c'], 'x')
    expect(out.map((w) => w.rect.x)).toEqual([0, 50, 100])
    // 只改 x：y/w/h 与其余字段深保真
    expect(out.map((w) => w.rect.y)).toEqual([0, 5, 10])
    expect(out[1]).toEqual({ ...ws[1], rect: { ...ws[1].rect, x: 50 } })
  })

  it('distributeRects：顺序无关（ids 乱序仍按坐标升序分布）', () => {
    const ws = [mk('a', 0, 0), mk('b', 20, 0), mk('c', 100, 0)]
    const out = distributeRects(ws, ['c', 'a', 'b'], 'x')
    expect(out.map((w) => w.rect.x)).toEqual([0, 50, 100])
  })

  it('distributeRects：y 轴分布 + 负坐标 round 取整（x 不动）', () => {
    const ws = [mk('a', 5, -100), mk('b', 7, 0), mk('c', 9, 60)]
    const out = distributeRects(ws, ['a', 'b', 'c'], 'y')
    expect(out.map((w) => w.rect.y)).toEqual([-100, -20, 60])
    expect(out.map((w) => w.rect.x)).toEqual([5, 7, 9])
  })

  it('distributeRects：有效 ids < 3 返回等价副本；不存在 id 忽略；恒新数组不改入参', () => {
    const ws = [mk('a', 10, 0), mk('b', 40, 0), mk('c', 90, 0)]
    // 2 个 → 等价副本
    const two = distributeRects(ws, ['a', 'b'], 'x')
    expect(two).toEqual(ws)
    expect(two).not.toBe(ws)
    // 含不存在 id（过滤后仅 2 个有效）→ 等价副本
    expect(distributeRects(ws, ['a', 'zz', 'b'], 'x')).toEqual(ws)
    // 3 个分布：入参不被修改 + 返回新数组（不可变）
    const out = distributeRects(ws, ['a', 'b', 'c'], 'x')
    expect(out).not.toBe(ws)
    expect(ws.map((w) => w.rect.x)).toEqual([10, 40, 90])
  })

  it('alignRects：多选（≥2）全体 axis = min；y 不动；不存在 id 忽略；单元素等价副本', () => {
    const ws = [mk('a', 30, 5), mk('b', 10, 6), mk('c', 20, 7)]
    const out = alignRects(ws, ['a', 'b', 'c'], 'x')
    expect(out.map((w) => w.rect.x)).toEqual([10, 10, 10])
    expect(out.map((w) => w.rect.y)).toEqual([5, 6, 7])
    expect(alignRects(ws, ['a', 'zz'], 'x')).toEqual(ws)
    const one = alignRects(ws, ['a'], 'x')
    expect(one).toEqual(ws)
    expect(one).not.toBe(ws)
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

describe('componentSeedPage（Task 15 统一入口 · 深链自动建稿种子页）', () => {
  it('页面名 = 组件名；标题文本 = 组件名；说明文本 = 目录描述', () => {
    const p = componentSeedPage('SQL 转换', '对数据集执行 SQL 加工')
    expect(p.version).toBe(1)
    expect(p.name).toBe('SQL 转换')
    expect(p.widgets).toHaveLength(2)
    const [h, t] = p.widgets
    expect(h.kind).toBe('heading')
    expect((h.props as Record<string, unknown>).text).toBe('SQL 转换')
    expect(t.kind).toBe('text')
    expect((t.props as Record<string, unknown>).text).toBe('对数据集执行 SQL 加工')
  })
  it('描述缺省 → 引导文案兜底（用户可直接从组件库继续设计）', () => {
    const p = componentSeedPage('某组件')
    expect((p.widgets[1].props as Record<string, unknown>).text)
      .toBe('组件设计画布：从左侧组件库拖入元素开始设计')
  })
  it('种子页过 validatePage 纯数据校验（与后端红线同口径）', () => {
    expect(validatePage(normalizePage(componentSeedPage('演示', '说明')))).toEqual([])
  })
})
