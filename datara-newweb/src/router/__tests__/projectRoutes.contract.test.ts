import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import { routes } from '../routes'
import ProjectWorkbenchView from '../../views/ProjectWorkbenchView.vue'
import ProjectSegmentView from '../../views/ProjectSegmentView.vue'
import SystemAdminView from '../../views/system/SystemAdminView.vue'
import { PROJECT_MENU_ITEMS, projectItemPath } from '../../navigation/projectMenu'

type PropsFn = (route: { params: Record<string, string | string[]> }) => Record<string, unknown>

describe('UX v3：项目工作区路由', () => {
  it('工作台使用精确路由，其余多段业务路径进入项目功能承载页', () => {
    const workbench = routes.find((route) => route.path === '/p/:projectId')
    const segment = routes.find((route) => route.path === '/p/:projectId/:pathMatch(.*)*')
    expect(workbench?.component).toBe(ProjectWorkbenchView)
    expect(segment?.component).toBe(ProjectSegmentView)
    expect(segment?.name).toBe('project-segment')
  })

  it('多段 pathMatch 归一为 segmentPath 并数字化 projectId', () => {
    const segment = routes.find((route) => route.path === '/p/:projectId/:pathMatch(.*)*')
    const props = segment?.props as PropsFn
    expect(props({ params: { projectId: '33', pathMatch: ['meta', 'lineage'] } })).toEqual({
      projectId: 33,
      segmentPath: 'meta/lineage',
    })
  })

  it('十九项项目导航均可由真实路由解析', () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    for (const item of PROJECT_MENU_ITEMS) {
      const resolved = router.resolve(projectItemPath(33, item))
      expect(resolved.matched.length, item.id).toBeGreaterThan(0)
      const expected = item.path === '/' ? 'project-workbench' : item.path === '/ide' ? 'project-dbx-sql-ide' : 'project-segment'
      expect(resolved.name, item.id).toBe(expected)
    }
  })

  it('部署运维与系统管理保持全局顶层路由', () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    expect(router.resolve('/dep/runtime').name).toBe('dep-runtime')
    expect(router.resolve('/sys').name).toBe('system-admin')
  })

  it('项目作用域系统段直达 SystemAdminView 并透传 projectId（B5-c：redirect 丢参致成员管理不可达的纠偏）', () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    const resolved = router.resolve('/p/33/system')
    expect(resolved.name).toBe('project-system-admin')
    const systemRoute = routes.find((route) => route.path === '/p/:projectId/system')
    expect(systemRoute?.component).toBe(SystemAdminView)
    const props = systemRoute?.props as PropsFn
    expect(props({ params: { projectId: '33' } })).toEqual({ projectId: 33 })
  })
})
