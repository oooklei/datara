/**
 * 票 2-06 验收测试：表格页范式 + 详情抽屉范式组件（WBS 2.3）
 *
 * 锚：渲染测试（筛选/表格/分页插槽三段落位；抽屉开合/遮罩关闭/标题/底部操作区）；
 *     旧前端布局对照——headless 环境无浏览器渲染，以旧实锚行号对照表归档于证据文档
 *     （截图待 1.9 部署验证环境 browser-use E2E 补归档，票面注记）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TablePageLayout from '../TablePageLayout.vue'
import DetailDrawer from '../DetailDrawer.vue'

describe('2-06 TablePageLayout 表格页范式（筛选区+表格+分页三段插槽）', () => {
  const w = mount(TablePageLayout, {
    slots: {
      filters: '<input data-test="q" placeholder="搜索" />',
      table: '<table data-test="tbl"><tr><td>row</td></tr></table>',
      pagination: '<button data-test="pg">1</button>',
    },
  })

  it('三段 data-part 落位且插槽内容进对应段', () => {
    expect(w.find('[data-part="filters"]').exists()).toBe(true)
    expect(w.find('[data-part="table"]').exists()).toBe(true)
    expect(w.find('[data-part="pagination"]').exists()).toBe(true)
    expect(w.find('[data-part="filters"] [data-test="q"]').exists()).toBe(true)
    expect(w.find('[data-part="table"] [data-test="tbl"]').exists()).toBe(true)
    expect(w.find('[data-part="pagination"] [data-test="pg"]').exists()).toBe(true)
  })

  it('纵向三段顺序：筛选区 → 表格 → 分页（旧列表页布局语义）', () => {
    const parts = w.findAll('[data-part]').map((x) => x.attributes('data-part'))
    expect(parts).toEqual(['filters', 'table', 'pagination'])
  })
})

describe('2-06 DetailDrawer 详情抽屉范式（受控开合+遮罩+标题+关闭+底部操作）', () => {
  // Teleport 渲染目标在 body 外，stub 后内容留 wrapper 内可查
  const telOpts = { global: { stubs: { teleport: true } } } as const

  it('关闭态不渲染抽屉', () => {
    const w = mount(DetailDrawer, { props: { modelValue: false, title: '详情' }, ...telOpts })
    expect(w.find('[data-part="mask"]').exists()).toBe(false)
  })

  it('开启态渲染：遮罩+dialog 语义+标题+内容插槽', () => {
    const w = mount(DetailDrawer, {
      props: { modelValue: true, title: '数据源详情' },
      slots: { default: '<p data-test="body">内容</p>' },
      ...telOpts,
    })
    expect(w.find('[data-part="mask"]').exists()).toBe(true)
    expect(w.find('[role="dialog"]').attributes('aria-modal')).toBe('true')
    expect(w.find('.drawer-title').text()).toBe('数据源详情')
    expect(w.find('[data-test="body"]').text()).toBe('内容')
  })

  it('关闭钮触发 update:modelValue=false + close 事件', async () => {
    const w = mount(DetailDrawer, { props: { modelValue: true, title: 'T' }, ...telOpts })
    await w.find('button.drawer-close').trigger('click')
    expect(w.emitted('update:modelValue')![0]).toEqual([false])
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('点遮罩空白关闭；点抽屉本体不关闭', async () => {
    const w = mount(DetailDrawer, {
      props: { modelValue: true, title: 'T' },
      slots: { default: '<p>x</p>' },
      ...telOpts,
    })
    await w.find('[data-part="mask"]').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
    // 抽屉本体点击不冒泡关闭（@click.self 守卫）
    await w.find('.detail-drawer').trigger('click')
    expect(w.emitted('close')).toHaveLength(1)
  })

  it('footer 插槽条件渲染（有则显示底部操作区，无则不渲染）', () => {
    const withFooter = mount(DetailDrawer, {
      props: { modelValue: true },
      slots: { footer: '<button data-test="ok">确定</button>' },
      ...telOpts,
    })
    expect(withFooter.find('[data-part="footer"] [data-test="ok"]').exists()).toBe(true)
    const noFooter = mount(DetailDrawer, { props: { modelValue: true }, ...telOpts })
    expect(noFooter.find('[data-part="footer"]').exists()).toBe(false)
  })

  it('自定义宽度透传（默认 480px）', () => {
    const w = mount(DetailDrawer, { props: { modelValue: true, width: '720px' }, ...telOpts })
    expect(w.find('.detail-drawer').attributes('style')).toContain('width: 720px')
  })
})
