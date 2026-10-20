/**
 * 唯一显隐过滤函数（增量 2 / 票 2-02）
 *
 * 蓝本：0.8 方案 §2.2（L72-88）——菜单是否可见由本模块同一函数族决定，
 * 页面组件禁散落自定义显隐判断；路由守卫仍是访问控制真源，菜单过滤只管导航呈现不替代鉴权。
 * 裁定锚：R-15（批次开关数据源 BATCH_SWITCHES 初始保守关闭）；
 *         R-29（future routeName 字段可解析判定与 formal 同口径）。
 * future 四纳入门（0.8 §5.2 L154-158）：①§3 登记且裁定纳入（source 非空承载）
 *  ②有可解析路由可进页面 ③监督线明确允许预览（previewAllowed）④权限过滤通过。
 */
import {
  BATCH_SWITCHES,
  globalMountedItems,
  menuGroups,
  type MenuItemConfig,
  type MenuGroupConfig,
} from './menu'

export interface MenuFilterContext {
  /** 已注册路由 name 集合（来自路由表） */
  registeredRouteNames: ReadonlySet<string>
  /** 已注册路径集合（来自路由表） */
  registeredPaths: ReadonlySet<string>
  /** 当前用户权限标识集合 */
  permissions: ReadonlySet<string>
  /** 批次开关覆盖（缺省读 menu.ts BATCH_SWITCHES 常量表） */
  batchSwitches?: Readonly<Record<string, boolean>>
  /** 已闭合的 decisionGate 门标识集合（缺省空=全部未闭合） */
  resolvedDecisionGates?: ReadonlySet<string>
  /** 监督线明确允许正式批次前预览的 future 项 id 集合（四纳入门③） */
  previewAllowed?: ReadonlySet<string>
}

function routeResolvable(item: MenuItemConfig, ctx: MenuFilterContext): boolean {
  if (item.routeName && ctx.registeredRouteNames.has(item.routeName)) return true
  if (item.path && ctx.registeredPaths.has(item.path)) return true
  return false
}

function permissionPassed(item: MenuItemConfig, ctx: MenuFilterContext): boolean {
  return !item.permission || ctx.permissions.has(item.permission)
}

function sourceRegistered(item: MenuItemConfig): boolean {
  return !!item.source && item.source.trim() !== ''
}

/** formal 五门（0.8 L75-81）：source 已登记 + 批次已启用 + 路由可解析 + 权限通过 + decisionGate 已闭合 */
export function isFormalItemVisible(item: MenuItemConfig, ctx: MenuFilterContext): boolean {
  if (item.disposition !== 'formal') return false
  if (!sourceRegistered(item)) return false
  const switches = ctx.batchSwitches ?? BATCH_SWITCHES
  if (!item.batch || switches[item.batch] !== true) return false
  if (!routeResolvable(item, ctx)) return false
  if (!permissionPassed(item, ctx)) return false
  if (item.decisionGate && !(ctx.resolvedDecisionGates?.has(item.decisionGate) ?? false)) return false
  return true
}

/** future 四门（0.8 L82-86 / §5.2）：source 已登记 + 路由已实现且允许预览 + 权限通过 */
export function isFutureItemEligible(item: MenuItemConfig, ctx: MenuFilterContext): boolean {
  if (item.disposition !== 'future') return false
  if (!sourceRegistered(item)) return false
  if (!routeResolvable(item, ctx)) return false
  if (!(ctx.previewAllowed?.has(item.id) ?? false)) return false
  if (!permissionPassed(item, ctx)) return false
  return true
}

/** 侧栏菜单项可见性唯一入口（embedded/deleted 永不进侧栏） */
export function isMenuItemVisible(item: MenuItemConfig, ctx: MenuFilterContext): boolean {
  if (item.disposition === 'formal') return isFormalItemVisible(item, ctx)
  if (item.disposition === 'future') return isFutureItemEligible(item, ctx)
  return false
}

export interface RenderableMenuGroup {
  group: MenuGroupConfig
  items: readonly MenuItemConfig[]
}

/**
 * 组装侧栏渲染视图：
 * - 逐组过滤可见项，无可见子项的组整体不渲染（0.8 L88）
 * - B 组 direct 语义透传（渲染层不画组标题；F56a 2A/3B）
 * - 各组 future 项过四门后收集进「后续批次」组；空时整组不渲染，非空默认折叠（defaultFolded 透传）
 * - embedded 项（同步任务/流处理/调用日志/AI 助手）不产生侧栏条目
 */
export function filterMenuGroups(ctx: MenuFilterContext): readonly RenderableMenuGroup[] {
  const out: RenderableMenuGroup[] = []
  const futureGroup = menuGroups.find((g) => g.id === 'future')
  const eligibleFuture: MenuItemConfig[] = []

  for (const g of menuGroups) {
    if (g.id === 'future') continue
    const visible = g.items.filter((i) => isMenuItemVisible(i, ctx))
    for (const i of g.items) {
      if (isFutureItemEligible(i, ctx)) eligibleFuture.push(i)
    }
    if (visible.length === 0) continue
    out.push({ group: g, items: visible })
  }

  if (futureGroup && eligibleFuture.length > 0) {
    out.push({ group: futureGroup, items: eligibleFuture })
  }
  return out
}

/**
 * H 全局挂载可见性（AI 助手）：embedded 项仅当所在 decisionGate 闭合时交付挂载层消费；
 * 挂载结构本身归 AppShell（票 2-05），本函数只做门判定（0.8 §6 规则 5：未接线不伪装已交付）。
 */
export function isGlobalMountVisible(item: MenuItemConfig, ctx: MenuFilterContext): boolean {
  if (item.disposition !== 'embedded') return false
  if (!sourceRegistered(item)) return false
  if (item.decisionGate && !(ctx.resolvedDecisionGates?.has(item.decisionGate) ?? false)) return false
  return true
}

/** 便捷导出：H 挂载登记项的门判定视图 */
export function filterGlobalMounts(ctx: MenuFilterContext): readonly MenuItemConfig[] {
  return globalMountedItems.filter((i) => isGlobalMountVisible(i, ctx))
}
