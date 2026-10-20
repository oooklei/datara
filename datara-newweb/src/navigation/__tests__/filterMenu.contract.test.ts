/**
 * 票 2-02 验收测试：唯一显隐过滤函数（0.8 §7 测试集 5）
 *
 * 锚：未注册路由/未闭合 decisionGate/无权限项均不可见；空组不渲染；B 组 direct 断言（F56a）；
 *     future 四纳入门（previewAllowed 缺失不渲染，杜绝空壳与「敬请期待」替代）；R-15 批次门。
 */
import { describe, expect, it } from 'vitest'
import type { MenuItemConfig } from '../menu'
import {
  filterGlobalMounts,
  filterMenuGroups,
  isFormalItemVisible,
  isFutureItemEligible,
  isMenuItemVisible,
  type MenuFilterContext,
} from '../filterMenu'

function ctx(over: Partial<MenuFilterContext> = {}): MenuFilterContext {
  return {
    registeredRouteNames: new Set<string>(),
    registeredPaths: new Set<string>(),
    permissions: new Set<string>(),
    ...over,
  }
}

function formalItem(over: Partial<MenuItemConfig> = {}): MenuItemConfig {
  return {
    id: 'x',
    label: 'X',
    disposition: 'formal',
    source: '§4.2 测试合成项',
    batch: 'inc4',
    path: '/dag',
    ...over,
  }
}

describe('2-02 formal 五门（0.8 L75-81）', () => {
  it('全门通过才可见：批次开+路由注册', () => {
    const item = formalItem()
    expect(isFormalItemVisible(item, ctx({
      registeredPaths: new Set(['/dag']),
      batchSwitches: { inc4: true },
    }))).toBe(true)
  })

  it('批次关（R-15 初始态）不可见', () => {
    const item = formalItem()
    expect(isFormalItemVisible(item, ctx({ registeredPaths: new Set(['/dag']) }))).toBe(false)
    expect(isFormalItemVisible(item, ctx({
      registeredPaths: new Set(['/dag']),
      batchSwitches: { inc4: false },
    }))).toBe(false)
  })

  it('未注册路由不可见（routeName/path 均不可解析；无 path/routeName 同判不可见）', () => {
    const item = formalItem()
    expect(isFormalItemVisible(item, ctx({ batchSwitches: { inc4: true } }))).toBe(false)
    // 仅 routeName 可解析也算通过（0.8 L78 routeName/path 至少一个可解析）
    expect(isFormalItemVisible(formalItem({ path: undefined, routeName: 'home' }), ctx({
      registeredRouteNames: new Set(['home']),
      batchSwitches: { inc4: true },
    }))).toBe(true)
    // routeName 与 path 均缺失
    expect(isFormalItemVisible(formalItem({ path: undefined }), ctx({ batchSwitches: { inc4: true } }))).toBe(false)
  })

  it('未闭合 decisionGate 不可见（0.8 L81；resolvedDecisionGates 缺省空=全未闭合）', () => {
    const item = formalItem({ decisionGate: 'some-gate' })
    const c = ctx({ registeredPaths: new Set(['/dag']), batchSwitches: { inc4: true } })
    expect(isFormalItemVisible(item, c)).toBe(false)
    expect(isFormalItemVisible(item, ctx({
      registeredPaths: new Set(['/dag']),
      batchSwitches: { inc4: true },
      resolvedDecisionGates: new Set(['some-gate']),
    }))).toBe(true)
  })

  it('无权限不可见；未配置 permission 视为通过（0.8 L79）', () => {
    const gated = formalItem({ permission: 'dag:read' })
    const c = ctx({
      registeredPaths: new Set(['/dag']),
      batchSwitches: { inc4: true },
      permissions: new Set(['dag:read']),
    })
    expect(isFormalItemVisible(gated, c)).toBe(true)
    expect(isFormalItemVisible(gated, ctx({
      registeredPaths: new Set(['/dag']),
      batchSwitches: { inc4: true },
      permissions: new Set<string>(),
    }))).toBe(false)
    expect(isFormalItemVisible(formalItem(), ctx({
      registeredPaths: new Set(['/dag']),
      batchSwitches: { inc4: true },
    }))).toBe(true)
  })

  it('source 空不可见（登记前置红线 2）', () => {
    expect(isFormalItemVisible(formalItem({ source: '' }), ctx({
      registeredPaths: new Set(['/dag']),
      batchSwitches: { inc4: true },
    }))).toBe(false)
    expect(isFormalItemVisible(formalItem({ source: '  ' }), ctx({
      registeredPaths: new Set(['/dag']),
      batchSwitches: { inc4: true },
    }))).toBe(false)
  })

  it('embedded/deleted 侧栏永不可见', () => {
    const c = ctx({ registeredPaths: new Set(['/dag']), batchSwitches: { inc4: true } })
    expect(isMenuItemVisible({ ...formalItem(), disposition: 'embedded' }, c)).toBe(false)
    expect(isMenuItemVisible({ ...formalItem(), disposition: 'deleted' }, c)).toBe(false)
  })
})

describe('2-02 future 四门（0.8 L82-86 / §5.2）', () => {
  const futureItem: MenuItemConfig = {
    id: 'dw-modeling',
    label: '数仓建模',
    path: '/model/list',
    routeName: 'dwModeling',
    disposition: 'future',
    batch: 'inc17',
    source: '§4.2 D 行；S175/S179',
  }

  it('四门全过才 eligible：路由可解析+previewAllowed+权限', () => {
    expect(isFutureItemEligible(futureItem, ctx({
      registeredRouteNames: new Set(['dwModeling']),
      previewAllowed: new Set(['dw-modeling']),
    }))).toBe(true)
  })

  it('路由未实现不可 eligible（杜绝点击 404/空壳/mock）', () => {
    expect(isFutureItemEligible(futureItem, ctx({ previewAllowed: new Set(['dw-modeling']) }))).toBe(false)
  })

  it('监督线未允许预览不可 eligible（四纳入门③）', () => {
    expect(isFutureItemEligible(futureItem, ctx({
      registeredRouteNames: new Set(['dwModeling']),
    }))).toBe(false)
  })

  it('无权限不可 eligible（四纳入门④）', () => {
    expect(isFutureItemEligible({ ...futureItem, permission: 'model:read' }, ctx({
      registeredRouteNames: new Set(['dwModeling']),
      previewAllowed: new Set(['dw-modeling']),
      permissions: new Set<string>(),
    }))).toBe(false)
  })
})

describe('2-02 filterMenuGroups 组装（空组不渲染 + direct 断言 + future 组收集）', () => {
  it('R-15 初始态（开关全关+仅 /login / 注册）：输出空视图，无空壳组', () => {
    const view = filterMenuGroups(ctx({
      registeredPaths: new Set(['/', '/login']),
      registeredRouteNames: new Set(['home', 'login']),
    }))
    expect(view).toEqual([])
  })

  it('开启 inc3：A 组可见；embedded 项（同步任务/流处理）永不产生条目', () => {
    const view = filterMenuGroups(ctx({
      registeredPaths: new Set(['/', '/login']),
      registeredRouteNames: new Set(['home', 'login']),
      batchSwitches: { inc3: true },
    }))
    expect(view.map((g) => g.group.id)).toEqual(['overview'])
    expect(view[0].items.map((i) => i.id)).toEqual(['workbench'])
  })

  it('开启 inc4 且 /dag 已注册：B 组一级直达可见且 direct:true 透传（组标题不渲染由渲染层保证）', () => {
    const view = filterMenuGroups(ctx({
      registeredPaths: new Set(['/', '/dag']),
      registeredRouteNames: new Set(['home', 'login']),
      batchSwitches: { inc4: true },
    }))
    const b = view.find((g) => g.group.id === 'task-center')
    expect(b).toBeDefined()
    expect(b!.group.label).toBe('')
    expect(b!.group.direct).toBe(true)
    expect(b!.items.map((i) => i.id)).toEqual(['task-center-entry'])
  })

  it('decisionGate 未闭合的 formal 项（资源管理）即使批次开也不渲染空壳', () => {
    const view = filterMenuGroups(ctx({
      registeredPaths: new Set(['/ds/list', '/res']),
      batchSwitches: { inc10: true },
      resolvedDecisionGates: new Set<string>(),
    }))
    const c = view.find((g) => g.group.id === 'integration')
    expect(c).toBeDefined()
    expect(c!.items.map((i) => i.id)).toEqual(['ds-list'])
    expect(c!.items.some((i) => i.id === 'resource-mgmt')).toBe(false)
  })

  it('future 四门未满足时「后续批次」组整组不渲染（0 项空壳禁止）', () => {
    const view = filterMenuGroups(ctx({
      registeredPaths: new Set(['/model/list']),
      batchSwitches: { inc17: true },
    }))
    expect(view.find((g) => g.group.id === 'future')).toBeUndefined()
  })

  it('future 项四门全过：收集进 future 组且 defaultFolded:true 透传（默认折叠）', () => {
    const view = filterMenuGroups(ctx({
      registeredRouteNames: new Set(['dwModeling']),
      previewAllowed: new Set(['dw-modeling']),
    }))
    const f = view.find((g) => g.group.id === 'future')
    expect(f).toBeDefined()
    expect(f!.group.foldable).toBe(true)
    expect(f!.group.defaultFolded).toBe(true)
    expect(f!.items.map((i) => i.id)).toEqual(['dw-modeling'])
  })

  it('embedded/disposition 非法项不因任何开关回流菜单（含 globalMounted 隔离）', () => {
    const view = filterMenuGroups(ctx({
      registeredPaths: new Set(['/', '/dag', '/ds/list', '/ide', '/sec/perm']),
      batchSwitches: { inc3: true, inc4: true, inc10: true, inc11: true, inc15: true },
    }))
    const allIds = view.flatMap((g) => g.items.map((i) => i.id))
    for (const banned of ['sync-task', 'stream-process', 'api-call-log', 'resource-mgmt']) {
      expect(allIds).not.toContain(banned)
    }
    // 菜单面与全局挂载面隔离：ai-assistant 只经 filterGlobalMounts 暴露
    expect(allIds).not.toContain('ai-assistant')
  })

  it('H 全局挂载：AI 助手无未决门时可见（挂载结构归 2-05 AppShell）', () => {
    const mounts = filterGlobalMounts(ctx({}))
    expect(mounts.map((i) => i.id)).toEqual(['ai-assistant'])
  })
})
