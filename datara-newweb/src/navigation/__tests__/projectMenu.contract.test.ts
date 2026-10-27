import { beforeEach, describe, expect, it } from 'vitest'
import {
  ACTIVE_PROJECT_KEY,
  PROJECT_MENU_GROUPS,
  PROJECT_MENU_ITEMS,
  projectItemPath,
  selectActiveProject,
} from '../projectMenu'

beforeEach(() => localStorage.removeItem(ACTIVE_PROJECT_KEY))

describe('UX v3：项目侧栏五组十九项', () => {
  it('冻结五组顺序与逐组数量', () => {
    expect(PROJECT_MENU_GROUPS.map((group) => group.label)).toEqual([
      '总览', '任务中心', '数据集成', '数据开发', '数据治理',
    ])
    expect(PROJECT_MENU_GROUPS.map((group) => group.items.length)).toEqual([1, 1, 2, 2, 13])
    expect(PROJECT_MENU_ITEMS).toHaveLength(19)
  })

  it('同步、流处理、部署运维和系统管理不进入项目侧栏', () => {
    const ids = PROJECT_MENU_ITEMS.map((item) => item.id)
    expect(ids).not.toContain('sync-task')
    expect(ids).not.toContain('stream-process')
    expect(ids).not.toContain('dep-runtime')
    expect(ids).not.toContain('system')
  })

  it('项目路径由 projectId 与全局业务路径稳定映射', () => {
    expect(projectItemPath(33, PROJECT_MENU_ITEMS[0])).toBe('/p/33')
    expect(projectItemPath(33, PROJECT_MENU_ITEMS.find((item) => item.id === 'sql-ide')!)).toBe('/p/33/ide')
    expect(projectItemPath(33, PROJECT_MENU_ITEMS.find((item) => item.id === 'meta-lineage')!)).toBe('/p/33/meta/lineage')
  })

  it('id/path 均唯一且 label 非空', () => {
    const ids = PROJECT_MENU_ITEMS.map((item) => item.id)
    const paths = PROJECT_MENU_ITEMS.map((item) => item.path)
    expect(new Set(ids).size).toBe(ids.length)
    expect(new Set(paths).size).toBe(paths.length)
    for (const item of PROJECT_MENU_ITEMS) {
      expect(item.id).toMatch(/^[a-z][a-z0-9-]*$/)
      expect(item.label.trim()).not.toBe('')
    }
  })

  it('无历史选择时优先进入裁定电商项目，并兼容迁移前旧名称', () => {
    const projects = [
      { id: 1, name: 'I1浏览器验证项目' },
      { id: 33, name: '电商数据全域治理项目' },
      { id: 35, name: 'INFRA-DATA-01 电商闭环验证' },
    ]

    expect(selectActiveProject(projects)).toBe(33)
    expect(localStorage.getItem(ACTIVE_PROJECT_KEY)).toBe('33')
  })

  it('裁定新名称优先于迁移前旧名称，且用户历史选择仍具有最高优先级', () => {
    const projects = [
      { id: 33, name: '电商数据全域治理项目' },
      { id: 40, name: '电商全域数据治理项目' },
    ]
    expect(selectActiveProject(projects)).toBe(40)
    localStorage.setItem(ACTIVE_PROJECT_KEY, '33')
    expect(selectActiveProject(projects)).toBe(33)
  })
})
