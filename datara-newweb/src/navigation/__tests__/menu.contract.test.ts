/**
 * 票 2-01 验收测试：菜单配置契约落地（0.8 §7 测试集 1）
 *
 * 锚定裁定 R-15：快照锚配置对象（逐行参数化断言，不依赖渲染 DOM / snapshot 文件）
 * 覆盖面：
 *  - §4.2 七组 + H 挂载逐行「有且唯一」结论（0.8 §7 测试集 1）
 *  - 任务中心空组标题且一级直达（F56a 裁定 2A/3B）
 *  - source 非空可追溯（权威设计 §4.4 登记前置 / 红线 2）
 *  - R-15 批次开关与已交付页面状态一致
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
  it('dbx 统一后菜单组顺序稳定', () => {
    expect(allGroups.map((g) => g.id)).toEqual([
      'overview',
      'task-center',
      'integration',
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
    expect(g.items.map((i) => i.id)).toEqual(['task-center-entry', 'task-group'])
    expect(g.items[0]).toMatchObject({ label: '任务中心', path: '/dag', disposition: 'formal', batch: 'inc4' })
  })

  it('C 组 数据集成：脚本开发入口', () => {
    const g = allGroups.find((x) => x.id === 'integration')!
    expect(g.label).toBe('数据集成')
    const byId = Object.fromEntries(g.items.map((i) => [i.id, i]))
    expect(Object.keys(byId).sort()).toEqual(['dbx-sql-ide', 'resource-mgmt', 'stream-process', 'sync-task'].sort())
    expect(byId['dbx-sql-ide']).toMatchObject({ label: 'SQL IDE', path: '/ide', disposition: 'formal' })
    expect(byId['sync-task']).toMatchObject({ label: '同步任务', disposition: 'embedded' })
    expect(byId['sync-task'].path).toBeUndefined()
    expect(byId['stream-process']).toMatchObject({ label: '流数据处理', disposition: 'embedded' })
    expect(byId['resource-mgmt']).toMatchObject({
      label: '脚本开发',
      path: '/resources',
      routeName: 'resource-mgmt',
      disposition: 'formal',
      batch: 'inc10',
    })
    expect(byId['resource-mgmt'].decisionGate).toBeUndefined()
  })

  it('旧数据开发组已退役', () => {
    expect(allGroups.find((x) => x.id === 'development')).toBeUndefined()
  })

  it('E 组 数据治理：五个质量页面均正式开放', () => {
    const g = allGroups.find((x) => x.id === 'governance')!
    expect(g.label).toBe('数据治理')
    const formal = g.items.filter((i) => i.disposition === 'formal')
    const future = g.items.filter((i) => i.disposition === 'future')
    expect(formal.map((i) => i.path)).toEqual([
      '/meta/tag',
      '/std/element',
      '/ind/list',
      '/ind/board',
      '/ind/consistency',
      '/qc/rule',
      '/qc/task',
      '/qc/exception',
      '/qc/report',
      '/qc/alarm',
    ])
    expect(future).toEqual([])
  })

  it('F 组部署运维只保留 worker 运行模型所需入口', () => {
    const g = allGroups.find((x) => x.id === 'operations')!
    expect(g.label).toBe('部署运维')
    expect(g.items.map((i) => [i.id, i.path, i.disposition, i.batch])).toEqual([
      ['dep-monitor', '/dep/monitor', 'formal', 'inc17'],
      ['dep-ssh', '/dep/ssh', 'formal', 'inc17'],
      ['dep-worker-group', '/dep/worker-group', 'formal', 'inc17'],
      ['dep-environment', '/dep/environment', 'formal', 'inc17'],
      ['dep-queue', '/dep/queue', 'formal', 'inc17'],
      ['dep-cluster', '/dep/cluster', 'formal', 'inc17'],
      ['dep-resource-file', '/dep/resource-file', 'formal', 'inc17'],
    ])
    expect(g.items.find((item) => item.id === 'dep-resource-file')?.label).toBe('运行依赖文件')
  })

  it('G 组 系统管理：保留权限、审计与开放能力', () => {
    const g = allGroups.find((x) => x.id === 'system')!
    expect(g.label).toBe('系统管理')
    const byId = Object.fromEntries(g.items.map((i) => [i.id, i]))
    expect(Object.keys(byId).sort()).toEqual(
      ['sec-perm', 'sec-audit', 'open-api', 'open-key', 'api-call-log'].sort(),
    )
    expect(byId['sec-perm']).toMatchObject({ label: '权限管理', path: '/sec/perm', disposition: 'formal', batch: 'inc15' })
    expect(byId['sec-audit']).toMatchObject({ label: '访问审计', path: '/sec/audit', disposition: 'formal', batch: 'inc15' })
    expect(byId['open-api']).toMatchObject({ label: 'API 管理', path: '/open/api', disposition: 'formal', batch: 'inc15' })
    expect(byId['open-key']).toMatchObject({ label: 'API-Key 管理', path: '/open/key', disposition: 'formal', batch: 'inc15' })
    // #14 调用日志：并入 #12，独立页签/附属列未确认（0.8 §4 L128）
    expect(byId['api-call-log']).toMatchObject({ label: '调用日志', disposition: 'embedded' })
    expect(byId['api-call-log'].decisionGate).toBe('api-call-log-form')
    expect(byId['api-call-log'].path).toBeUndefined()
  })

  it('future 机制组：固定配置 foldable/defaultFolded，静态 items 空（0.8 §5.1；机制归 2-02/2-04）', () => {
    const g = allGroups.find((x) => x.id === 'future')!
    expect(g.label).toBe('后续批次')
    expect(g.foldable).toBe(true)
    expect(g.defaultFolded).toBe(true)
    expect(g.items).toEqual([])
  })

  it('全局 AI 助手已退役', () => {
    expect(globalMountedItems).toHaveLength(0)
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

  it('正式菜单项均提供非空图标字形', () => {
    const formals = rows.filter((r) => r.item.disposition === 'formal')
    expect(formals).toHaveLength(26)
    expect(formals.filter((r) => !r.item.icon?.trim()).map((r) => r.item.id)).toEqual([])
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

  it('已交付批次开启，未交付批次仍保持关闭', () => {
    const keys = Object.keys(BATCH_SWITCHES)
    expect(keys.length).toBeGreaterThan(0)
    for (const k of keys) {
      const delivered = new Set(['inc3', 'inc4', 'inc10', 'inc11', 'inc14', 'inc15', 'inc17'])
      expect(BATCH_SWITCHES[k], `batch ${k} 开关状态`).toBe(delivered.has(k))
    }
  })

  it('formal 批次键与 BATCH_SWITCHES 键域一致（无未登记批次引用）', () => {
    const batchRefs = new Set(
      rows.filter((r) => r.item.batch).map((r) => r.item.batch as string),
    )
    for (const b of batchRefs) expect(BATCH_SWITCHES[b]).toBeDefined()
  })
})
