/**
 * 15.1-C 组件测试：PermissionMatrixView 权限矩阵只读页。
 *
 * 覆盖：表头四角色列序、32 行权限点、单元格授权态与 data-granted 锚、
 * 行 data-perm 词形锚、图例 aria 结构。纯静态消费冻结常量（无 fetch mock 需要），
 * 断言值直接取自 rolePermissions.ts（与矩阵快照契约测试互证）。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import {
  PERMISSION_ORDER,
  ROLE_ORDER,
  ROLE_PERMISSIONS,
  roleHasPermission,
} from '../../services/rebuild/rolePermissions'
import PermissionMatrixView from '../PermissionMatrixView.vue'

describe('15.1-C PermissionMatrixView 权限矩阵只读页', () => {
  const w = mount(PermissionMatrixView)

  it('根结构：main[aria-label=权限矩阵] + 唯一 data-perm-matrix 表格', () => {
    expect(w.find('main[aria-label="权限矩阵"]').exists()).toBe(true)
    expect(w.findAll('[data-perm-matrix]')).toHaveLength(1)
  })

  it('表头列序 = 权限点列 + 四角色（与 ROLE_ORDER 一致）', () => {
    const heads = w.findAll('thead th')
    expect(heads).toHaveLength(1 + ROLE_ORDER.length)
    expect(heads[0].text()).toBe('权限点')
    ROLE_ORDER.forEach((r, i) => {
      expect(heads[i + 1].attributes('data-role-head')).toBe(r)
      expect(heads[i + 1].text()).toBe(r)
    })
  })

  it('行数 = 32 权限点，行序与 data-perm 词形锚与 PERMISSION_ORDER 一致', () => {
    const rows = w.findAll('tbody tr')
    expect(rows).toHaveLength(32)
    rows.forEach((row, i) => {
      expect(row.attributes('data-perm')).toBe(PERMISSION_ORDER[i])
      expect(row.find('[data-perm-code]').text()).toBe(PERMISSION_ORDER[i])
    })
  })

  it('单元格授权态与冻结矩阵逐格一致（32×4=128 格 data-granted 全校验）', () => {
    const rows = w.findAll('tbody tr')
    for (const p of PERMISSION_ORDER) {
      const row = rows.find((r) => r.attributes('data-perm') === p)!
      for (const r of ROLE_ORDER) {
        const cell = row.find(`[data-role="${r}"]`)
        const granted = roleHasPermission(r, p)
        expect(cell.attributes('data-granted'), `${r}×${p}`).toBe(granted ? 'yes' : 'no')
        expect(cell.text()).toBe(granted ? '✓' : '—')
      }
    }
  })

  it('抽查锚点：manage_user 仅 admin 授予；view_all 四角色全授予', () => {
    const manageRow = w.find('[data-perm="manage_user"]')
    expect(manageRow.find('[data-role="admin"]').attributes('data-granted')).toBe('yes')
    for (const r of ['developer', 'operator', 'viewer'] as const) {
      expect(manageRow.find(`[data-role="${r}"]`).attributes('data-granted')).toBe('no')
    }
    const viewAllRow = w.find('[data-perm="view_all"]')
    for (const r of ROLE_ORDER) {
      expect(viewAllRow.find(`[data-role="${r}"]`).attributes('data-granted')).toBe('yes')
    }
  })

  it('图例 role=note 与标题文案存在（只读语义声明）', () => {
    expect(w.find('[role="note"]').exists()).toBe(true)
    expect(w.find('h1').text()).toBe('权限矩阵')
    expect(w.find('header p').text()).toContain('只读快照')
  })

  it('页面零网络依赖：渲染产物不含任何 loading/alert 网络三态（静态只读页）', () => {
    expect(w.find('[role="status"]').exists()).toBe(false)
    expect(w.find('[role="alert"]').exists()).toBe(false)
    expect(ROLE_PERMISSIONS.admin).toHaveLength(32)
  })
})
