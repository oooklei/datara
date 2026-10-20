/**
 * 票 2-07 验收测试：页签组织范式组件（WBS 2.3；0.8 页签交互壳）
 * 边界：只测通用范式（增删/激活/容器语义）；DAG 专用页签内容归增量 4.2（预研 §2.4）。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import TabsView from '../TabsView.vue'

const tabs = [
  { id: 't1', label: '页签一' },
  { id: 't2', label: '页签二', closable: true },
  { id: 't3', label: '页签三', closable: true },
]

describe('2-07 TabsView 页签范式（增删/激活/容器语义）', () => {
  it('渲染全部页签且激活态 aria-selected 正确', () => {
    const w = mount(TabsView, { props: { tabs, modelValue: 't2' } })
    const els = w.findAll('[role="tab"]')
    expect(els).toHaveLength(3)
    expect(els[1].classes()).toContain('active')
    expect(els[1].attributes('aria-selected')).toBe('true')
    expect(els[0].attributes('aria-selected')).toBe('false')
  })

  it('点击未激活页签触发 update:modelValue；点击当前激活页签不重复上报', async () => {
    const w = mount(TabsView, { props: { tabs, modelValue: 't1' } })
    await w.findAll('[role="tab"]')[2].trigger('click')
    expect(w.emitted('update:modelValue')![0]).toEqual(['t3'])
    // t1 === 当前 modelValue：激活页签重复点击不追加事件
    await w.findAll('[role="tab"]')[0].trigger('click')
    expect(w.emitted('update:modelValue')).toHaveLength(1)
  })

  it('关闭钮仅 closable 页签渲染；点击关闭上报 close(id) 且不触发激活切换', async () => {
    const w = mount(TabsView, { props: { tabs, modelValue: 't1' } })
    expect(w.findAll('.tab-close')).toHaveLength(2)
    const t2 = w.find('[data-tab-id="t2"]')
    await t2.find('.tab-close').trigger('click')
    expect(w.emitted('close')![0]).toEqual(['t2'])
    // @click.stop：关闭不冒泡为页签激活
    expect(w.emitted('update:modelValue')).toBeUndefined()
  })

  it('容器语义：tabpanel 插槽渲染内容（KeepAlive 缓存由消费方包裹）', () => {
    const w = mount(TabsView, {
      props: { tabs, modelValue: 't1' },
      slots: { default: '<section data-test="pane">内容面板</section>' },
    })
    expect(w.find('[role="tabpanel"]').exists()).toBe(true)
    expect(w.find('[data-test="pane"]').text()).toBe('内容面板')
  })

  it('空页签列表：渲染空页签条不报错（消费方控制增删）', () => {
    const w = mount(TabsView, { props: { tabs: [], modelValue: '' } })
    expect(w.findAll('[role="tab"]')).toHaveLength(0)
  })

  it('tab id 为稳定键：组件渲染 data-tab-id 锚点供测试选择器/权限映射（转正保持 id 语义）', () => {
    const w = mount(TabsView, { props: { tabs, modelValue: 't1' } })
    expect(w.find('[data-tab-id="t2"]').exists()).toBe(true)
  })
})
