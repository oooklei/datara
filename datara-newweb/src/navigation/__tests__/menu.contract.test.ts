/**
 * 票 2-01 验收测试：菜单配置契约落地（0.8 §7 测试集 1）
 *
 * 锚定裁定 R-15：快照锚配置对象（逐行参数化断言，不依赖渲染 DOM / snapshot 文件）
 * 覆盖面：
 *  - §4.2 七组 + H 挂载逐行「有且唯一」结论（0.8 §7 测试集 1）
 *  - 任务中心空组标题且一级直达（F56a 裁定 2A/3B）
 *  - source 非空可追溯（权威设计 §4.4 登记前置 / 红线 2）
 *  - R-15 批次开关初始值保守关闭
 *  - R-28 脱敏/审计纳入批次注记；R-29 future routeName 预留不注册
 *  - 0.8 L66 构建纪律：deleted 项不得进入运行时配置
 */
import { describe, expect, it } from 'vitest'
import {
  BATCH_SWITCHES,
  globalMountedItems,
  menuGroups,
  type MenuItemConfig,
} from '../menu'

const allGroups = menuGroups as readonly {
  id: string
  label: string
  direct?: boolean
  foldable?: boolean
  defaultFolded?: boolean
  items: readonly MenuItemConfig[]
}[]

function flatItems(): { item: MenuItemConfig; groupId: string }[] {
  const rows: { item: MenuItemConfig; groupId: string }[] = []
  for (const g of allGroups) {
    for (const it of g.items) rows.push({ item: it, groupId: g.id })
  }
  return rows
}

describe('2-01 菜单配置契约（0.8 §7 测试集 1：§4.2 逐行有且唯一）', () => {
  it('组序列 = 七组 A–G + future 机制组，顺序与 id 冻结（0.8 L47-49）', () => {
    expect(allGroups.map((g) => g.id)).toEqual([
      'overview',
      'task-center',
      'integration',
      'development',
      'governance',
      'operations',
      'system',
      'future',
    ])
  })

  it('A 组 总览：工作台唯一 formal 项，路径已实证', () => {
    const g = allGroups.find((x) => x.id === 'overview')!
    expect(g.label).toBe('总览')
    expect(g.items.map((i) => i.id)).toEqual(['workbench'])
    expect(g.items[0]).toMatchObject({
      label: '工作台',
      path: '/',
      routeName: 'home',
      disposition: 'formal',
      batch: 'inc3',
    })
  })

  it('B 组 任务中心：空组标题 + 一级直达（F56a 2A/3B；0.8 §3 L95）', () => {
    const g = allGroups.find((x) => x.id === 'task-center')!
    expect(g.label).toBe('')
    expect(g.direct).toBe(true)
    expect(g.items.map((i) => i.id)).toEqual(['task-center-entry'])
    expect(g.items[0]).toMatchObject({ label: '任务中心', path: '/dag', disposition: 'formal', batch: 'inc4' })
  })

  it('C 组 数据集成：formal/embedded/formal+decisionGate 四项唯一落位（0.8 §3 L96-99）', () => {
    const g = allGroups.find((x) => x.id === 'integration')!
    expect(g.label).toBe('数据集成')
    const byId = Object.fromEntries(g.items.map((i) => [i.id, i]))
    expect(Object.keys(byId).sort()).toEqual(['ds-list', 'resource-mgmt', 'stream-process', 'sync-task'].sort())
    expect(byId['ds-list']).toMatchObject({ label: '数据源管理', path: '/ds/list', disposition: 'formal', batch: 'inc10' })
    expect(byId['sync-task']).toMatchObject({ label: '同步任务', disposition: 'embedded' })
    expect(byId['sync-task'].path).toBeUndefined()
    expect(byId['stream-process']).toMatchObject({ label: '流数据处理', disposition: 'embedded' })
    // 资源管理：formal 但路径待路由契约（增量 10 冻结）——TBD 不进运行时配置（0.8 L62），以 decisionGate 表达
    expect(byId['resource-mgmt']).toMatchObject({ label: '资源管理', disposition: 'formal', batch: 'inc10' })
    expect(byId['resource-mgmt'].decisionGate).toBe('route-frozen-inc10')
    expect(byId['resource-mgmt'].path).toBeUndefined()
    expect(byId['resource-mgmt'].routeName).toBeUndefined()
  })

  it('D 组 数据开发：SQL IDE formal + 数仓建模 future（S175/S179；R-29 routeName 预留）', () => {
    const g = allGroups.find((x) => x.id === 'development')!
    const byId = Object.fromEntries(g.items.map((i) => [i.id, i]))
    expect(Object.keys(byId).sort()).toEqual(['dw-modeling', 'sql-ide'].sort())
    expect(byId['sql-ide']).toMatchObject({ label: '数据开发IDE', path: '/ide', disposition: 'formal', batch: 'inc11' })
    expect(byId['dw-modeling']).toMatchObject({ label: '数仓建模', path: '/model/list', disposition: 'future', batch: 'inc17' })
    expect(byId['dw-modeling'].routeName).toBe('dwModeling')
  })

  it('E 组 数据治理：8 formal 已实证路径 + 5 质量项 future（0.8 §3 L102-103 / §4 #3-#7）', () => {
    const g = allGroups.find((x) => x.id === 'governance')!
    expect(g.label).toBe('数据治理')
    const formal = g.items.filter((i) => i.disposition === 'formal')
    const future = g.items.filter((i) => i.disposition === 'future')
    expect(formal.map((i) => i.path)).toEqual([
      '/meta/lineage',
      '/meta/map',
      '/meta/catalog',
      '/meta/tag',
      '/std/element',
      '/ind/list',
      '/ind/board',
      '/ind/consistency',
    ])
    expect(future.map((i) => i.id)).toEqual(['qc-rule', 'qc-task', 'qc-exception', 'qc-report', 'qc-alarm'])
    for (const i of future) expect(i.batch).toBe('inc14')
  })

  it('F 组 部署运维：运行时节点/集群监控双 future（S175/S179；0.8 §3 L104）', () => {
    const g = allGroups.find((x) => x.id === 'operations')!
    expect(g.label).toBe('部署运维')
    expect(g.items.map((i) => [i.id, i.path, i.disposition, i.batch])).toEqual([
      ['dep-runtime', '/dep/runtime', 'future', 'inc17'],
      ['dep-monitor', '/dep/monitor', 'future', 'inc17'],
    ])
  })

  it('G 组 系统管理：7 项唯一落位（#9 formal + R-28 两项 + #12/13 + #14 embedded + LLM）', () => {
    const g = allGroups.find((x) => x.id === 'system')!
    expect(g.label).toBe('系统管理')
    const byId = Object.fromEntries(g.items.map((i) => [i.id, i]))
    expect(Object.keys(byId).sort()).toEqual(
      ['sec-perm', 'sec-mask', 'sec-audit', 'open-api', 'open-key', 'api-call-log', 'llm-config'].sort(),
    )
    expect(byId['sec-perm']).toMatchObject({ label: '权限管理', path: '/sec/perm', disposition: 'formal', batch: 'inc15' })
    // R-28：脱敏·审计纳入（增量 15 后追加立项，可复议）
    expect(byId['sec-mask']).toMatchObject({ label: '脱敏规则', path: '/sec/mask', disposition: 'future', batch: 'inc15-post' })
    expect(byId['sec-audit']).toMatchObject({ label: '访问审计', path: '/sec/audit', disposition: 'future', batch: 'inc15-post' })
    expect(byId['open-api']).toMatchObject({ label: 'API 管理', path: '/open/api', disposition: 'future', batch: 'inc15' })
    expect(byId['open-key']).toMatchObject({ label: 'API-Key 管理', path: '/open/key', disposition: 'future', batch: 'inc15' })
    // #14 调用日志：并入 #12，独立页签/附属列未确认（0.8 §4 L128）
    expect(byId['api-call-log']).toMatchObject({ label: '调用日志', disposition: 'embedded' })
    expect(byId['api-call-log'].decisionGate).toBe('api-call-log-form')
    expect(byId['api-call-log'].path).toBeUndefined()
    // LLM 模型配置：不为其编造路径（0.8 §3 L109）
    expect(byId['llm-config']).toMatchObject({ label: 'LLM 模型配置', disposition: 'future', batch: 'inc15' })
    expect(byId['llm-config'].decisionGate).toBe('route-frozen-inc15')
    expect(byId['llm-config'].path).toBeUndefined()
  })

  it('future 机制组：固定配置 foldable/defaultFolded，静态 items 空（0.8 §5.1；机制归 2-02/2-04）', () => {
    const g = allGroups.find((x) => x.id === 'future')!
    expect(g.label).toBe('后续批次')
    expect(g.foldable).toBe(true)
    expect(g.defaultFolded).toBe(true)
    expect(g.items).toEqual([])
  })

  it('H 全局挂载：AI 助手 embedded 唯一登记，无菜单组（0.8 §3 L107）', () => {
    expect(globalMountedItems).toHaveLength(1)
    expect(globalMountedItems[0]).toMatchObject({ id: 'ai-assistant', label: 'AI 助手', disposition: 'embedded' })
  })
})

describe('2-01 配置纪律（0.8 L57-68 字段规则）', () => {
  const rows = [...flatItems(), ...globalMountedItems.map((item) => ({ item, groupId: 'H-global' }))]

  it('source 全量非空可追溯（红线 2 登记前置）', () => {
    const bad = rows.filter((r) => !r.item.source || r.item.source.trim() === '')
    expect(bad.map((r) => r.item.id)).toEqual([])
  })

  it('deleted 处置不进入运行时配置（0.8 L66 构建纪律；审计清单归 2-03）', () => {
    const deleted = rows.filter((r) => r.item.disposition === 'deleted')
    expect(deleted.map((r) => r.item.id)).toEqual([])
  })

  it('item id 全局唯一且为稳定键（禁中文标签）', () => {
    const ids = rows.map((r) => r.item.id)
    expect(new Set(ids).size).toBe(ids.length)
    const cjk = ids.filter((id) => /[\u4e00-\u9fff]/.test(id))
    expect(cjk).toEqual([])
  })

  it('formal 项：批次必填且已登记于 BATCH_SWITCHES；无 decisionGate 者必有 path 或 routeName（0.8 L62）', () => {
    const formals = rows.filter((r) => r.item.disposition === 'formal')
    expect(formals.length).toBeGreaterThan(0)
    for (const r of formals) {
      expect(r.item.batch, `${r.item.id} 缺 batch`).toBeDefined()
      expect(BATCH_SWITCHES[r.item.batch as string], `${r.item.id} batch 未登记`).toBeDefined()
      if (!r.item.decisionGate) {
        expect(r.item.path ?? r.item.routeName, `${r.item.id} 无 path/routeName 且无 decisionGate`).toBeDefined()
      }
    }
  })

  it('R-15：批次开关初始值保守关闭（全 false）', () => {
    const keys = Object.keys(BATCH_SWITCHES)
    expect(keys.length).toBeGreaterThan(0)
    for (const k of keys) expect(BATCH_SWITCHES[k], `batch ${k} 初始值应为 false`).toBe(false)
  })

  it('formal 批次键与 BATCH_SWITCHES 键域一致（无未登记批次引用）', () => {
    const batchRefs = new Set(
      rows.filter((r) => r.item.batch).map((r) => r.item.batch as string),
    )
    for (const b of batchRefs) expect(BATCH_SWITCHES[b]).toBeDefined()
  })
})
