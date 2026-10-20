/**
 * L3-03 契约测试：项目工作区路由注册（/p/:projectId 层，s251 派令）
 *
 * 锚定面：routes.ts 1.4 冻结决策延续——无 catch-all、每条路由 name+component；
 * 本件只锚定项目层两条新路由的注册形态 / props 数字化 / 解析行为
 * （既有四条基线断言归 routes.contract.test.ts，本件不重复）。
 */
import { describe, expect, it } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import { routes } from '../routes'
import ProjectWorkbenchView from '../../views/ProjectWorkbenchView.vue'
import ProjectSegmentView from '../../views/ProjectSegmentView.vue'
import { PROJECT_MENU_SECTIONS } from '../../navigation/projectMenu'

type PropsFn = (route: { params: Record<string, string | string[]> }) => Record<string, unknown>

const SEG_KEYS = PROJECT_MENU_SECTIONS.map((s) => s.key)

describe('L3-03：项目工作区路由注册契约', () => {
  it('注册形态：/p/:projectId→project-workbench→ProjectWorkbenchView；/p/:projectId/:seg→project-segment→ProjectSegmentView', () => {
    const wb = routes.find((r) => r.path === '/p/:projectId')
    const seg = routes.find((r) => r.path === '/p/:projectId/:seg')
    expect(wb).toBeDefined()
    expect(wb?.name).toBe('project-workbench')
    expect(wb?.component).toBe(ProjectWorkbenchView)
    expect(seg).toBeDefined()
    expect(seg?.name).toBe('project-segment')
    expect(seg?.component).toBe(ProjectSegmentView)
  })

  it('props 数字化注入：projectId Number 化；seg 字符串化（直接调用 props 函数断言）', () => {
    const wb = routes.find((r) => r.path === '/p/:projectId')
    const seg = routes.find((r) => r.path === '/p/:projectId/:seg')
    const wbProps = wb?.props as PropsFn | undefined
    const segProps = seg?.props as PropsFn | undefined
    expect(wbProps).toBeTypeOf('function')
    expect(segProps).toBeTypeOf('function')
    expect(wbProps?.({ params: { projectId: '9' } })).toEqual({ projectId: 9 })
    expect(segProps?.({ params: { projectId: '9', seg: 'dag' } })).toEqual({
      projectId: 9,
      seg: 'dag',
    })
  })

  it('解析行为（真实 memory router）：/p/9 归工作台、/p/9/<seg> 归功能段（七段逐段可解析）', () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    expect(router.resolve('/p/9').name).toBe('project-workbench')
    for (const key of SEG_KEYS) {
      const resolved = router.resolve(`/p/9/${key}`)
      expect(resolved.name).toBe('project-segment')
      expect(resolved.params.seg).toBe(key)
    }
  })

  it('未知 seg 仍归 project-segment 占位承载（无 catch-all 兜底、不落首页/工作台）', () => {
    const router = createRouter({ history: createMemoryHistory(), routes })
    const resolved = router.resolve('/p/9/unknown-seg')
    expect(resolved.name).toBe('project-segment')
    expect(resolved.params.seg).toBe('unknown-seg')
    expect(resolved.name).not.toBe('home')
    expect(resolved.name).not.toBe('project-workbench')
  })
})
