// @vitest-environment happy-dom
/**
 * Task 11 画布 + widget 渲染分派用例（happy-dom）：
 * - 画布卡居中（stage 内联 flex）+ 初始 288×520（CANVAS_DEFAULT 规格）+ box-shadow 非空
 * - drop 拖入：dataTransfer stub 返回 kind → emit add {kind,x,y}（getBoundingClientRect stub 卡内相对坐标）
 * - 拖尺寸：grip mousedown → window mousemove → emit canvasSize 且宽度钳制 [140,1920]；mouseup 解绑
 * - 预览态：table widget 渲染 preview 2 行真实数据；无预览渲染模板列 + 空态文案
 * - 选中：点击 widget 根元素 emit select（携带 id）
 * WidgetRenderer 为零 UI 库依赖的只读骨架渲染（原生元素 + SVG），测试直接轻量 DOM 断言。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PageCanvas from '../canvas/PageCanvas.vue'
import { normalizePage, type PageDSL } from '../designerModel'
import type { PreviewResult } from '../pageApi'

function makePage(): PageDSL {
  return normalizePage({
    page: {
      version: 1,
      canvas: { width: 288, height: 520, background: { fill: '#ffffff' } },
      widgets: [
        { id: 'wt', kind: 'text', rect: { x: 8, y: 8, w: 120, h: 24 }, props: { text: '文本内容' }, style: {}, bindings: {} },
        {
          id: 'w1', kind: 'table', rect: { x: 8, y: 40, w: 264, h: 160 },
          props: { columns: [{ title: '名称', dataIndex: 'name' }, { title: '状态', dataIndex: 'status' }], emptyText: '暂无数据' },
          style: {}, bindings: {},
        },
      ],
    },
  })
}

function mountCanvas(props: Record<string, unknown> = {}) {
  return mount(PageCanvas, { props: { page: makePage(), ...props } })
}

describe('PageCanvas 画布', () => {
  it('画布卡居中 + 初始 288×520（CANVAS_DEFAULT）+ 阴影非空', () => {
    const w = mountCanvas()
    const stageStyle = w.find('.pd-stage').attributes('style') ?? ''
    expect(stageStyle).toMatch(/display:\s*flex/)
    expect(stageStyle).toMatch(/align-items:\s*center/)
    const cs = w.find('.pd-canvas').attributes('style') ?? ''
    expect(cs).toMatch(/width:\s*288px/)
    expect(cs).toMatch(/height:\s*520px/)
    expect(cs).toMatch(/box-shadow:\s*\S/)
  })

  it('drop 拖入：emit add {kind,x,y}（卡内相对坐标）', async () => {
    const w = mountCanvas()
    const canvas = w.find('.pd-canvas')
    canvas.element.getBoundingClientRect = () =>
      ({ left: 40, top: 60, width: 288, height: 520, x: 40, y: 60, right: 328, bottom: 580, toJSON: () => ({}) }) as DOMRect
    await canvas.trigger('drop', { dataTransfer: { getData: () => 'text' }, clientX: 90, clientY: 140 })
    expect(w.emitted('add')?.[0]).toEqual(['text', 50, 80])
  })

  it('拖尺寸：mousemove emit canvasSize 且宽度钳制 [140,1920]；mouseup 解绑', async () => {
    const w = mountCanvas()
    await w.find('.pd-grip-e').trigger('mousedown', { clientX: 100 })
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 3000 }))
    const evts = w.emitted('canvasSize')
    expect(evts).toBeTruthy()
    const [ew] = evts![evts!.length - 1] as [number, number]
    expect(ew).toBe(1920) // 288+(3000-100) 远超上限 → 钳到 1920
    expect(ew).toBeGreaterThanOrEqual(140)
    window.dispatchEvent(new MouseEvent('mouseup'))
    const n = w.emitted('canvasSize')!.length
    window.dispatchEvent(new MouseEvent('mousemove', { clientX: 4000 }))
    expect(w.emitted('canvasSize')!.length).toBe(n)
  })

  it('预览态：table widget 渲染 preview 2 行真实数据', () => {
    const preview: Record<string, PreviewResult> = {
      w1: { columns: ['a', 'b'], rows: [['1', 'x'], ['2', 'y']], truncated: false, error: '' },
    }
    const w = mountCanvas({ preview })
    expect(w.find('.pd-w-table thead').text()).toContain('a')
    const rows = w.findAll('.pd-w-table tbody tr')
    expect(rows.length).toBe(2)
    expect(rows[1].text()).toContain('2')
  })

  it('无预览：table 渲染模板列 + 空态文案', () => {
    const w = mountCanvas()
    expect(w.find('.pd-w-table thead').text()).toContain('名称')
    expect(w.find('.pd-w-table').text()).toContain('暂无数据')
  })

  it('点击 widget 根元素 emit select（带 id）', async () => {
    const w = mountCanvas()
    await w.findAll('.pd-w-root')[0].trigger('click')
    expect(w.emitted('select')?.[0]).toEqual(['wt'])
  })
})
