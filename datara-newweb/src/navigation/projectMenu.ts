import { menuGroups } from './menu'

export interface ProjectMenuItem {
  id: string
  label: string
  icon: string
  /** 原全局业务路径；项目路径通过 projectItemPath 注入 projectId。 */
  path: string
}

export interface ProjectMenuGroup {
  id: string
  label: string
  items: readonly ProjectMenuItem[]
}

const PROJECT_GROUP_ORDER = ['overview', 'task-center', 'integration', 'governance'] as const
const GROUP_LABELS: Record<(typeof PROJECT_GROUP_ORDER)[number], string> = {
  overview: '总览',
  'task-center': '任务中心',
  integration: '数据集成',
  governance: '数据治理',
}

const LABEL_OVERRIDES: Record<string, string> = {
  'meta-tag': '标签管理',
  'std-element': '标准管理',
}

/**
 * UX v3 项目导航直接消费 menuGroups 的正式业务项：同步/流继续由 DAG 内部承载，
 * 部署运维和系统管理属于全局顶层，因此不会进入这里。
 */
export const PROJECT_MENU_GROUPS: readonly ProjectMenuGroup[] = PROJECT_GROUP_ORDER.map((groupId) => {
  const source = menuGroups.find((group) => group.id === groupId)
  if (!source) throw new Error(`missing project menu source group: ${groupId}`)
  const items = source.items
    .filter((item) => item.disposition === 'formal' && typeof item.path === 'string')
    .map((item): ProjectMenuItem => ({
      id: item.id,
      label: LABEL_OVERRIDES[item.id] ?? item.label,
      icon: item.icon ?? '·',
      path: item.path!,
    }))
  return { id: groupId, label: GROUP_LABELS[groupId], items }
})

export const PROJECT_MENU_ITEMS: readonly ProjectMenuItem[] = PROJECT_MENU_GROUPS.flatMap((group) => group.items)

export const ACTIVE_PROJECT_KEY = 'datara.active-project' as const
export const PROJECT_SCOPED_ALIASES = new Set([
  ...PROJECT_MENU_ITEMS.map((item) => item.path).filter((path) => path !== '/'),
])

export function rememberActiveProject(projectId: number): void {
  if (Number.isInteger(projectId) && projectId > 0) globalThis.localStorage?.setItem(ACTIVE_PROJECT_KEY, String(projectId))
}

export interface ProjectChoice {
  id: number
  name: string
}

const PREFERRED_PROJECT_NAMES = ['电商全域数据治理项目', '电商数据全域治理项目'] as const

export function selectActiveProject(projects: readonly ProjectChoice[]): number | null {
  const remembered = Number(globalThis.localStorage?.getItem(ACTIVE_PROJECT_KEY))
  const rememberedProject = projects.find((project) => project.id === remembered)
  const preferred = PREFERRED_PROJECT_NAMES
    .map((name) => projects.find((project) => project.name === name))
    .find((project) => project !== undefined)
  const selected = rememberedProject?.id ?? preferred?.id ?? projects[0]?.id ?? null
  if (selected !== null) rememberActiveProject(selected)
  return selected
}

export function projectItemPath(projectId: number, item: ProjectMenuItem): string {
  return item.path === '/' ? `/p/${projectId}` : `/p/${projectId}${item.path}`
}

/** @deprecated UX v3 使用分组结构；保留别名避免外部插件瞬时断裂。 */
export const PROJECT_MENU_SECTIONS = PROJECT_MENU_ITEMS
