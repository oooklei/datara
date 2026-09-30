/**
 * lineage profile 用例（Task 7）：
 * - 详情抽屉 lineageRelated：数据面条目（数据源/临时表/来源/参与工作流/上下游计数）+ 明细列表 + 孤岛空态；
 * - 一键聚焦注册：dep_focus edgeKinds（高亮色 + 流动动画）；nodeCenter 声明（双击/右键以此为中心）。
 */
import { describe, expect, it } from 'vitest'
import { lineageProfile, lineageRelated } from '../lineage'
import type { GNode, GraphDocument } from '../../model'

function node(id: string, data: Record<string, unknown>): GNode {
  return { id, type: 'ln_dwd', position: { x: 0, y: 0 }, data: { name: id, ...data } }
}

const doc: GraphDocument = {
  id: 'd1', name: '血缘', version: 1,
  meta: { profile: 'lineage' },
  nodes: [
    node('ods_a', { ds: 'mysql_biz', tmp: true, wfs: [101, 102], sources: ['design', 'runtime'] }),
    node('dwd_b', {}),
    node('solo_c', {}),
  ],
  edges: [
    { id: 'e1', source: 'ods_a', target: 'dwd_b', kind: 'dep', label: 'wf101·n1' },
  ],
}

describe('lineageRelated（Task 7 详情抽屉升级）', () => {
  it('数据面条目 + 上下游计数 + 明细列表按序产出', () => {
    const items = lineageRelated(doc.nodes[0]!, doc).map((i) => i.text)
    expect(items[0]).toBe('数据源：mysql_biz')
    expect(items[1]).toBe('临时表')
    expect(items[2]).toBe('来源：设计推导 + 运行事实')
    expect(items[3]).toBe('参与工作流：wf101、wf102')
    expect(items[4]).toBe('上游 0 条 · 下游 1 条')
    expect(items[5]).toBe('下游 → dwd_b（wf101·n1）')
  })

  it('下游节点：来源/工作流未注入（旧路径）不显示，上游列表可见', () => {
    const items = lineageRelated(doc.nodes[1]!, doc).map((i) => i.text)
    expect(items).toEqual(['上游 1 条 · 下游 0 条', '上游 ← ods_a（wf101·n1）'])
  })

  it('孤岛资产：仅计数行 + 孤岛提示', () => {
    const items = lineageRelated(doc.nodes[2]!, doc)
    expect(items.map((i) => i.text)).toEqual([
      '上游 0 条 · 下游 0 条',
      '无上下游血缘（孤岛资产）',
    ])
    expect(items[1]!.color).toBe('#e5484d')
  })
})

describe('lineageProfile Task 7 注册', () => {
  it('dep_focus 边语义（高亮色 + animated）；nodeCenter 声明以此为中心', () => {
    expect(lineageProfile.edgeKinds.dep_focus).toMatchObject({ kind: 'dep_focus', animated: true })
    expect(lineageProfile.edgeKinds.dep_focus!.dashed).toBeFalsy()
    expect(lineageProfile.nodeCenter).toBe(true)
  })
})
