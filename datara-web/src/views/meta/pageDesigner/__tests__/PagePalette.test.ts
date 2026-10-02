// @vitest-environment happy-dom
/**
 * Task 10 左侧组件库 Palette 挂载用例（happy-dom）：
 * - 六分组标题全部渲染；空词显示全部 43 项
 * - 搜索「表格」→ item 收敛 1 项（label/kind 过滤）；无命中分组隐藏
 * - item dragstart 以专用 MIME application/x-datara-widget 携带 kind（text/plain 兜底）
 * el-input 桩为原生 input（双向绑定），与既有组件用例同法。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import PagePalette from '../palette/PagePalette.vue'

const stubs = {
  ElInput: {
    props: ['modelValue'],
    emits: ['update:modelValue'],
    template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
  },
}

function mountPalette() {
  return mount(PagePalette, { global: { components: stubs } })
}

describe('PagePalette', () => {
  it('六个分组标题全部渲染', () => {
    const w = mountPalette()
    const titles = w.findAll('.pd-pal-group-title').map((n) => n.text())
    expect(titles).toEqual(['布局容器', '基础元素', '表单输入', '数据展示', '图表', '绑定元素'])
  })

  it('空关键词：全部 43 个 item 可见', () => {
    const w = mountPalette()
    expect(w.findAll('.pd-pal-item').length).toBe(43)
  })

  it('搜索「表格」→ item 收敛为 1 项且 label 含「表格」', async () => {
    const w = mountPalette()
    await w.find('input').setValue('表格')
    const items = w.findAll('.pd-pal-item')
    expect(items.length).toBe(1)
    expect(items[0].text()).toContain('表格')
  })

  it('搜索无命中：分组与 item 全部隐藏', async () => {
    const w = mountPalette()
    await w.find('input').setValue('zzz_no_hit')
    expect(w.findAll('.pd-pal-group').length).toBe(0)
    expect(w.findAll('.pd-pal-item').length).toBe(0)
  })

  it('dragstart 以专用 MIME + text/plain 兜底携带 kind', async () => {
    const w = mountPalette()
    const store: Record<string, string> = {}
    const dte = { setData: (t: string, v: string) => { store[t] = v } }
    await w.findAll('.pd-pal-item')[0].trigger('dragstart', { dataTransfer: dte })
    expect(store['application/x-datara-widget']).toBe('grid-row')
    expect(store['text/plain']).toBe('grid-row')
  })
})
