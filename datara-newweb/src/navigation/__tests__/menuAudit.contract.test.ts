/**
 * 票 2-03 验收测试：删除判定 18 项落地（0.8 §7 测试集 2 + 3）
 *
 * 双重负断言（拆票登记 2-03 锚；WBS 退出标准 2 严于 0.8 测试集 3）：
 *   A——8 条旧路径不出现在菜单生成结果（极限语境：批次全开+路由全注册+预览全许+门全闭合，仍不得回流）；
 *   B——8 条旧路径不存在于 routes.ts 路由表（真实 import，非 mock）。
 */
import { describe, expect, it } from 'vitest'
import type { RouteRecordRaw } from 'vue-router'
import { menuGroups, globalMountedItems, type MenuItemConfig } from '../menu'
import { filterMenuGroups, type MenuFilterContext } from '../filterMenu'
import {
  AUDIT_COUNTS,
  DELETED_LEGACY_PATHS,
  MENU_AUDIT_18,
} from '../menuAudit'
import { routes } from '../../router/routes'

function collectRoutePaths(records: readonly RouteRecordRaw[], acc: string[] = []): string[] {
  for (const r of records) {
    if (r.path) acc.push(r.path)
    if (r.children) collectRoutePaths(r.children, acc)
  }
  return acc
}

/** 极限语境：一切门全开——证明 deleted 项在任何语境都不回流菜单 */
function extremeCtx(): MenuFilterContext {
  const paths = new Set<string>(DELETED_LEGACY_PATHS)
  const names = new Set<string>()
  const futureIds = new Set<string>()
  const gates = new Set<string>()
  for (const g of menuGroups) {
    for (const i of g.items as MenuItemConfig[]) {
      if (i.path) paths.add(i.path)
      if (i.routeName) names.add(i.routeName)
      if (i.disposition === 'future') futureIds.add(i.id)
      if (i.decisionGate) gates.add(i.decisionGate)
    }
  }
  return {
    registeredPaths: paths,
    registeredRouteNames: names,
    permissions: new Set<string>(),
    batchSwitches: { inc3: true, inc4: true, inc10: true, inc11: true, inc14: true, inc15: true, 'inc15-post': true, inc17: true },
    resolvedDecisionGates: gates,
    previewAllowed: futureIds,
  }
}

describe('2-03 审计清单结构与计数（0.8 §7 测试集 2）', () => {
  it('清单恰为 18 项且序号 1-18 连续（0.8 §4 表）', () => {
    expect(MENU_AUDIT_18).toHaveLength(18)
    expect(MENU_AUDIT_18.map((e) => e.no)).toEqual(Array.from({ length: 18 }, (_, k) => k + 1))
  })

  it('逐项参数化：10 归组 + #14 内嵌 + 7 删除，数量与目标组一致（0.8 L134）', () => {
    const grouped = MENU_AUDIT_18.filter((e) => e.disposition === 'formal' || e.disposition === 'future')
    const embedded = MENU_AUDIT_18.filter((e) => e.disposition === 'embedded')
    const deleted = MENU_AUDIT_18.filter((e) => e.disposition === 'deleted')
    expect(grouped.map((e) => e.no)).toEqual([3, 4, 5, 6, 7, 9, 10, 11, 12, 13])
    expect(embedded.map((e) => e.no)).toEqual([14])
    expect(deleted.map((e) => e.no)).toEqual([1, 2, 8, 15, 16, 17, 18])
    expect({ grouped: grouped.length, embedded: embedded.length, deleted: deleted.length }).toEqual(AUDIT_COUNTS)
  })

  it('归组/内嵌项衔接锚在 menu.ts 真实存在且 disposition 一致（清单↔配置对拍）', () => {
    const configItems = new Map<string, MenuItemConfig>()
    for (const g of menuGroups) for (const i of g.items) configItems.set(i.id, i)
    for (const e of MENU_AUDIT_18) {
      if (e.disposition === 'deleted') {
        expect(e.targetItemId, `#${e.no} deleted 项不应有衔接锚`).toBeUndefined()
        continue
      }
      const cfg = configItems.get(e.targetItemId!)
      expect(cfg, `#${e.no} ${e.legacyLabel} 衔接锚 ${e.targetItemId} 未在 menu.ts 登记`).toBeDefined()
      expect(cfg!.disposition, `#${e.no} 处置态不一致`).toBe(e.disposition)
      expect(cfg!.source).toBeTruthy()
    }
  })

  it('18 项旧路径参数化对照（0.8 §4「旧项/旧路径」列逐行）', () => {
    const expected: [number, string, string][] = [
      [1, '脚本任务', '/script/list'],
      [2, '参数配置', '/param/global'],
      [3, '质量规则', '/qc/rule'],
      [4, '检查任务', '/qc/task'],
      [5, '异常数据核查', '/qc/exception'],
      [6, '质量报告', '/qc/report'],
      [7, '质量告警', '/qc/alarm'],
      [8, '评分总览', '/qc/score'],
      [9, '权限管理', '/sec/perm'],
      [10, '脱敏规则', '/sec/mask'],
      [11, '访问审计', '/sec/audit'],
      [12, 'API 管理', '/open/api'],
      [13, 'API-Key 管理', '/open/key'],
      [14, '调用日志', '/open/log'],
      [15, '部署中心', '/dep/center'],
      [16, '组件日志', '/dep/log'],
      [17, '告警管理', '/dep/alarm'],
      [18, '运维操作', '/dep/ops'],
    ]
    for (const [no, label, path] of expected) {
      const e = MENU_AUDIT_18.find((x) => x.no === no)!
      expect([e.legacyLabel, e.legacyPath]).toEqual([label, path])
    }
  })
})

describe('2-03 双重负断言（8 条旧路径）', () => {
  const view = filterMenuGroups(extremeCtx())

  it('A：菜单生成结果不含 8 条旧路径（极限语境下任何项不回流）', () => {
    const allPaths = view.flatMap((g) => g.items.map((i) => i.path).filter((p): p is string => !!p))
    for (const p of DELETED_LEGACY_PATHS) {
      expect(allPaths, `${p} 不得出现在菜单生成结果`).not.toContain(p)
    }
    // 同步任务旧语义：sync-task 为 embedded 且无 path（0.8 §3 L97）
    const sync = view.flatMap((g) => g.items).find((i) => i.id === 'sync-task')
    expect(sync).toBeUndefined()
  })

  it('B：routes.ts 路由表不存在 8 条旧路径（真实 import 断言，WBS 退出标准 2）', () => {
    const routePaths = collectRoutePaths(routes)
    for (const p of DELETED_LEGACY_PATHS) {
      expect(routePaths, `${p} 不得残留在路由表`).not.toContain(p)
    }
  })

  it('负断言样本自检：极限语境确有正式项可见（防测试恒真）', () => {
    const allIds = view.flatMap((g) => g.items.map((i) => i.id))
    expect(allIds.length).toBeGreaterThan(0)
    expect(allIds).toContain('task-center-entry')
    expect(allIds).toContain('sql-ide')
  })
})

describe('2-03 globalMounted 隔离（H 挂载不参与 18 项迁移面）', () => {
  it('AI 挂载项不在审计清单衔接锚中（H 行独立于 §4.3 18 项）', () => {
    const anchors = MENU_AUDIT_18.map((e) => e.targetItemId).filter(Boolean)
    for (const g of globalMountedItems) expect(anchors).not.toContain(g.id)
  })
})
