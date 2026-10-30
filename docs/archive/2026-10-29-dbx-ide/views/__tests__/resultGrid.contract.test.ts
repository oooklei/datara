import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ResultGrid from '../ide/ResultGrid.vue'

beforeEach(() => {
  // vxe-table 在 happy-dom 下依赖 ResizeObserver
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('ResultGrid（S4 vxe-grid 呈现面）', () => {
  it('renders the seq column, column titles and formatted cells', async () => {
    const w = mount(ResultGrid, {
      props: { columns: ['id', 'name'], rows: [[1, 'alpha'], [2, null]] },
    })
    await flushPromises()
    expect(w.text()).toContain('id')
    expect(w.text()).toContain('name')
    expect(w.text()).toContain('alpha')
    // null 单元格格式化为空文本而非字符串 "null"
    expect(w.text()).not.toContain('null')
  })

  it('serializes object cells as JSON', async () => {
    const w = mount(ResultGrid, {
      props: { columns: ['meta'], rows: [[{ k: 1 }]] },
    })
    await flushPromises()
    expect(w.text()).toContain('{"k":1}')
  })

  it('emits copied with the display text of the clicked cell', async () => {
    const w = mount(ResultGrid, {
      props: { columns: ['id', 'name'], rows: [[7, 'alpha']] },
    })
    await flushPromises()
    const cells = w.findAll('tbody td')
    expect(cells.length).toBeGreaterThanOrEqual(3)
    await cells[1].trigger('click')
    expect(w.emitted('copied')?.[0]).toEqual(['7'])
  })
})
