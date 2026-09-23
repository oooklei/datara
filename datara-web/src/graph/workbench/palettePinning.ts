/**
 * I12 R1（T7）：组件库分类徽标 + 强关联分组置顶——纯逻辑，供 Palette.vue 与单测复用。
 * 基本盘全域可用：只决定徽标展示与分组排序，不过滤、不隐藏任何组件。
 */
import type { ComponentCategory } from '../profiles/types'

/** I12 R1：分类 → 徽标文案（组件行小胶囊，多类并列）；as const 保留字面量供 CatLabel 锁定 PIN_MAP 键 */
export const CAT_LABEL = {
  sync: '同步',
  etl: 'ETL',
  stream: '流',
  general: '普通',
} as const satisfies Record<ComponentCategory, string>

/** I12 R1：徽标文案字面量类型（= CAT_LABEL 值集，用作 PIN_MAP 键的类型锁定） */
export type CatLabel = (typeof CAT_LABEL)[ComponentCategory]

/** I12 R1：徽标展示固定顺序（专属类在前、兜底「普通」垫后，与 schema 声明顺序无关） */
const CAT_ORDER: readonly ComponentCategory[] = ['sync', 'etl', 'stream', 'general']

/** I12 R1：schema.categories → 徽标文案数组（按固定顺序；未标注分类返回空，不显示徽标） */
export function catLabelsOf(categories?: ComponentCategory[]): string[] {
  if (!categories?.length) return []
  return CAT_ORDER.filter((c) => categories.includes(c)).map((c) => CAT_LABEL[c])
}

/** I12 R1：强关联分组置顶映射（键=activeTag，类型锁定为 CAT_LABEL 值集，防键值漂移） */
export const PIN_MAP: Record<CatLabel, string[]> = {
  ETL: ['数据计算', '逻辑控制', '变量'],
  同步: ['数据同步', '逻辑控制', '变量'],
  流: ['流处理', '变量'],
  普通: ['逻辑控制', '数据计算', '变量'],
}

/**
 * I12 R1：activeTags → 分组置顶名次（值越小越靠前；未命中组不入表 = Infinity 保持原序）。
 * 多标签时前标签的置顶组优先，后标签仅补充新组。
 */
export function pinnedRank(activeTags?: string[]): Map<string, number> {
  const rank = new Map<string, number>()
  if (!activeTags?.length) return rank
  for (const tag of activeTags) {
    for (const g of PIN_MAP[tag as CatLabel] ?? []) { // 非内置标签（如自定义目录名）运行时落空 → ?? []
      if (!rank.has(g)) rank.set(g, rank.size)
    }
  }
  return rank
}

/**
 * I12 R1：分组名列表按置顶名次稳定重排——命中组整体前移（映射优先序），其余组保持原序；
 * 不增删任何分组（所有组件保持全量渲染，折叠态不受影响）。
 */
export function orderPinned(names: string[], activeTags?: string[]): string[] {
  const rank = pinnedRank(activeTags)
  if (rank.size === 0) return names
  return [...names].sort((a, b) => (rank.get(a) ?? Number.POSITIVE_INFINITY) - (rank.get(b) ?? Number.POSITIVE_INFINITY))
}
