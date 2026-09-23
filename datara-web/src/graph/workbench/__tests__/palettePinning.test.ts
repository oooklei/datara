/**
 * I12 T7（R1）组件库分类徽标 + 强关联分组置顶——纯逻辑单测（不挂载组件）：
 * - CAT_LABEL 映射：sync/etl/stream/general → 同步/ETL/流/普通，多类并列；
 * - 置顶排序：传 ['同步'] 后分组首项 = 数据同步；命中组整体前移，其余分组保持原序；
 * - R1 基本盘：不过滤不隐藏——任意 activeTags 下分组与组件保持全量。
 */
import { describe, it, expect } from 'vitest'
import { CAT_LABEL, PIN_MAP, catLabelsOf, orderPinned } from '../palettePinning'
import { dagProfile } from '../../profiles/dag'

/** dag palette 实际分组名序（任务书映射表组名须与其对齐） */
const DAG_GROUPS = dagProfile.palette.map((c) => c.name)

describe('I12 T7 CAT_LABEL 分类徽标映射', () => {
  it('四类映射齐全且文案正确', () => {
    expect(CAT_LABEL).toEqual({ sync: '同步', etl: 'ETL', stream: '流', general: '普通' })
  })

  it('多类并列：按固定顺序输出多个徽标；未标注分类输出空（不显示徽标）', () => {
    expect(catLabelsOf(['general', 'sync', 'etl'])).toEqual(['同步', 'ETL', '普通'])
    expect(catLabelsOf(['stream'])).toEqual(['流'])
    expect(catLabelsOf(undefined)).toEqual([])
    expect(catLabelsOf([])).toEqual([])
  })
})

describe('I12 T7 强关联分组置顶排序', () => {
  it("传 ['同步'] 后分组首项 = 数据同步（dag 分组实序验证）", () => {
    expect(DAG_GROUPS[0]).toBe('逻辑控制') // 前置：原序首个为逻辑控制
    expect(orderPinned(DAG_GROUPS, ['同步'])[0]).toBe('数据同步')
  })

  it('ETL / 流 / 普通 各自置顶首项符合映射表', () => {
    expect(orderPinned(DAG_GROUPS, ['ETL'])[0]).toBe('数据计算')
    expect(orderPinned(DAG_GROUPS, ['流'])[0]).toBe('流处理')
    expect(orderPinned(DAG_GROUPS, ['普通'])[0]).toBe('逻辑控制')
  })

  it('命中组整体前移且保持映射优先序，其余分组保持原序', () => {
    /* I12 T11：palette 新增「通用」组（notify），未命中映射保持原序垫在「模板」前 */
    expect(orderPinned(DAG_GROUPS, ['同步'])).toEqual([
      '数据同步', '逻辑控制', '变量', '数据计算', '流处理', '通用', '模板',
    ])
  })

  it('不过滤不隐藏：任意 activeTags 下分组集合与个数不变（全量渲染前提）', () => {
    for (const tags of [undefined, [], ['同步'], ['ETL'], ['流'], ['普通'], ['同步', '流']]) {
      const ordered = orderPinned(DAG_GROUPS, tags)
      expect(ordered).toHaveLength(DAG_GROUPS.length)
      expect([...ordered].sort()).toEqual([...DAG_GROUPS].sort())
    }
  })

  it('组件全量：置顶重排不改变任何分组下的组件集合', () => {
    const byName = new Map(dagProfile.palette.map((c) => [c.name, c]))
    const ordered = orderPinned(DAG_GROUPS, ['同步']).map((n) => byName.get(n)!)
    const typesOf = (cs: typeof dagProfile.palette) =>
      cs
        .flatMap((c) => c.items ?? (c.types ?? []).map((t) => ({ type: t })))
        .map((i) => i.type)
        .sort()
    expect(typesOf(ordered)).toEqual(typesOf(dagProfile.palette))
  })

  it('多标签：前标签优先序在前，后标签仅补充新组；映射外组保持原位', () => {
    expect(orderPinned(['A', '数据同步', 'B', '变量'], ['同步', '普通'])).toEqual(['数据同步', '变量', 'A', 'B'])
  })

  it('映射表与任务书一致', () => {
    expect(PIN_MAP).toEqual({
      ETL: ['数据计算', '逻辑控制', '变量'],
      同步: ['数据同步', '逻辑控制', '变量'],
      流: ['流处理', '变量'],
      普通: ['逻辑控制', '数据计算', '变量'],
    })
  })
})
