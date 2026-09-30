// @vitest-environment happy-dom
/**
 * FieldLineageMap 组件单测（Task 6 字段级图上呈现）：
 * - 左右列节点去重与排序（表部按最后点分界，同表相邻）；
 * - 连线数 = 映射行数；transform 悬浮标签（hover 展示 / 空 transform 兜底）；
 * - 深链 field 高亮 chip（.hl）。
 * 纯展示组件，无服务依赖。
 */
import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import FieldLineageMap from '../FieldLineageMap.vue'

const ROWS = [
  { target: 'dwd_order.pay_amount', from: 'ods_order.amount', transform: 'amount * 0.9' },
  { target: 'dwd_order.pay_amount', from: 'ods_order.discount', transform: 'amount - discount' },
  { target: 'dwd_order.uid', from: 'ods_user.uid', transform: '' },
]

describe('FieldLineageMap 映射图', () => {
  it('左列来源字段去重同表相邻排序；右列目标字段去重；连线数 = 映射行数', () => {
    const wrapper = mount(FieldLineageMap, { props: { rows: ROWS } })
    const chips = wrapper.findAll('.flm-chip').map((c) => c.text())
    // chip 文本 = 表部 + 字段部相邻拼接（<i>表</i><span>字段</span>）
    expect(chips).toEqual(['ods_orderamount', 'ods_orderdiscount', 'ods_useruid', 'pay_amount', 'uid'])
    expect(wrapper.findAll('line.flm-line')).toHaveLength(ROWS.length)
  })

  it('transform 悬浮标签：hover 连线展示表达式，空 transform 兜底「（无表达式）」', async () => {
    const wrapper = mount(FieldLineageMap, { props: { rows: ROWS } })
    const groups = wrapper.findAll('g')
    await groups[0]!.trigger('mouseenter')
    expect(wrapper.find('.flm-tip').text()).toBe('amount * 0.9')
    await groups[0]!.trigger('mouseleave')
    expect(wrapper.find('.flm-tip').exists()).toBe(false)
    await groups[2]!.trigger('mouseenter')
    expect(wrapper.find('.flm-tip').text()).toBe('（无表达式）')
  })

  it('highlight 命中目标字段 chip → .hl 高亮（深链 field 定位）', () => {
    const wrapper = mount(FieldLineageMap, { props: { rows: ROWS, highlight: 'uid' } })
    const hl = wrapper.findAll('.flm-chip.hl')
    expect(hl).toHaveLength(1)
    expect(hl[0]!.text()).toBe('uid')
    // 命中连线同步高亮
    expect(wrapper.findAll('line.flm-line.hl')).toHaveLength(1)
  })

  it('端点缺失行不参与连线（数据不自洽防兜底假边，如 from="" 常量项漏过滤）', () => {
    const rows = [
      { target: 'dwd_order.pay_amount', from: 'ods_order.amount', transform: 'a' },
      { target: 'dwd_order.uid', from: '', transform: "'常量'" },  // 左端缺失：lefts 不含空 id
    ]
    const wrapper = mount(FieldLineageMap, { props: { rows } })
    // 左列仅 1 个来源 chip + 右列 2 个目标 chip；仅自洽行画 1 条线（旧实现 ?? 0 会贴顶画 2 条假边）
    expect(wrapper.findAll('.flm-chip')).toHaveLength(3)
    expect(wrapper.findAll('line.flm-line')).toHaveLength(1)
  })
})
