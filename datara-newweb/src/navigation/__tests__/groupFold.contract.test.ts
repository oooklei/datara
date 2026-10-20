/**
 * 票 2-04 验收测试：「后续批次」折叠组机制（0.8 §7 测试集 4）
 *
 * 锚：空时整组隐藏（2-02 filterMenuGroups 已断言，此处闭环联合断言）；
 *     非空时组存在且默认折叠；展开不改变路由；稳定键 future 持久化断言（R5 键禁中文）。
 */
import { describe, expect, it } from 'vitest'
import { menuGroups } from '../menu'
import { filterMenuGroups, type MenuFilterContext } from '../filterMenu'
import {
  groupFoldKey,
  loadGroupFolded,
  saveGroupFolded,
  toggleGroupFolded,
} from '../groupFold'
import { routes } from '../../router/routes'

function ctx(previewIds: string[]): MenuFilterContext {
  return {
    registeredRouteNames: new Set(['dwModeling']),
    registeredPaths: new Set<string>(),
    permissions: new Set<string>(),
    previewAllowed: new Set(previewIds),
  }
}

describe('2-04 稳定键纪律（0.8 L161 / R5 防漂移）', () => {
  it('future 组折叠键 = 稳定前缀 + 组 id，不含中文标签「后续批次」', () => {
    expect(groupFoldKey('future')).toBe('datara.menu.groupFolded.future')
    expect(/[\u4e00-\u9fff]/.test(groupFoldKey('future'))).toBe(false)
  })

  it('运行时守卫：中文标签作键直接抛错（键漂移硬约束）', () => {
    expect(() => groupFoldKey('后续批次')).toThrow()
    expect(() => groupFoldKey('任务中心')).toThrow()
  })
})

describe('2-04 折叠态存取（0.8 §7 测试集 4）', () => {
  it('无存储时返回 defaultFolded（future 组 menu.ts 冻结 defaultFolded:true）', () => {
    localStorage.clear()
    const g = menuGroups.find((x) => x.id === 'future')!
    expect(loadGroupFolded('future', g.defaultFolded === true)).toBe(true)
  })

  it('存取往返与显式覆盖默认值', () => {
    localStorage.clear()
    saveGroupFolded('future', false)
    expect(loadGroupFolded('future', true)).toBe(false)
    saveGroupFolded('future', true)
    expect(loadGroupFolded('future', false)).toBe(true)
  })

  it('toggle 翻转并持久化（旧 toggleGroup 语义复刻）', () => {
    localStorage.clear()
    expect(toggleGroupFolded('future', true)).toBe(false)
    expect(loadGroupFolded('future', true)).toBe(false)
    expect(toggleGroupFolded('future', false)).toBe(true)
    expect(loadGroupFolded('future', true)).toBe(true)
  })

  it('展开（折叠翻转）不改变路由：routes 内容与长度零变化（0.8 测试集 4 之「展开不改变路由」）', () => {
    localStorage.clear()
    const before = routes.map((r) => r.path)
    const beforeLen = routes.length
    toggleGroupFolded('future', true)
    toggleGroupFolded('future', false)
    expect(routes.length).toBe(beforeLen)
    expect(routes.map((r) => r.path)).toEqual(before)
  })
})

describe('2-04 future 组组装闭环（过滤视图 × 折叠态联合断言）', () => {
  it('非空：组存在+默认折叠+foldable 透传；折叠态读 defaultFolded', () => {
    localStorage.clear()
    const view = filterMenuGroups(ctx(['dw-modeling']))
    const f = view.find((g) => g.group.id === 'future')
    expect(f).toBeDefined()
    expect(f!.items.map((i) => i.id)).toEqual(['dw-modeling'])
    expect(f!.group.foldable).toBe(true)
    expect(f!.group.defaultFolded).toBe(true)
    // 渲染层初始折叠态来源：loadGroupFolded('future', defaultFolded) = true
    expect(loadGroupFolded('future', f!.group.defaultFolded === true)).toBe(true)
  })

  it('空：整组隐藏（previewAllowed 清空即消失，不渲染空折叠组）', () => {
    localStorage.clear()
    expect(filterMenuGroups(ctx([])).find((g) => g.group.id === 'future')).toBeUndefined()
  })
})
