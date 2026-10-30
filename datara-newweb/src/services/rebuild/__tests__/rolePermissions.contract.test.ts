/**
 * 15.1-C 契约测试：前端权限矩阵冻结快照（矩阵契约）。
 *
 * 权威源：datara-backend/rebuild/identity/contracts.py
 *   - L14-18 Role StrEnum（admin/developer/operator/viewer）
 *   - L21-53 Permission StrEnum（32 项 wire 词形）
 *   - L56-98 ROLE_PERMISSIONS（ADMIN=32 / DEVELOPER=31 / OPERATOR=17 / VIEWER=10）
 *
 * 本测试把后端权威矩阵逐值冻结为快照断言：后端枚举词形、集合成员、角色基数
 * 任一漂移即红，强制走 15-P0 门 1 评审同步链（rolePermissions.ts 头注契约）。
 */
import { describe, expect, it } from 'vitest'
import {
  PERMISSION_ORDER,
  ROLE_ORDER,
  ROLE_PERMISSIONS,
  roleHasPermission,
  type Permission,
  type Role,
} from '../rolePermissions'

/** 后端 contracts.py L21-53 Permission 枚举声明序快照（32 项 wire 词形）。 */
const BACKEND_PERMISSION_SNAPSHOT: readonly Permission[] = [
  'manage_user',
  'edit_definition',
  'run_instance',
  'view_all',
  'execute_sql',
  'project:read',
  'project:write',
  'workflow:read',
  'workflow:write',
  'workflow:publish',
  'workflow:run',
  'workflow:delete',
  'task:read',
  'task:write',
  'task:run',
  'datasource:read',
  'datasource:use',
  'datasource:manage',
  'sql:read',
  'sql:write-ddl',
  'schedule:read',
  'schedule:manage',
  'lineage:read',
  'quality:read',
  'quality:write',
  'quality:run',
  'standard:read',
  'standard:write',
  'standard:approve',
  'security:read',
  'security:manage',
  'audit:read',
  'monitor:read',
]

describe('15.1-C 权限矩阵冻结快照（权威源 identity/contracts.py）', () => {
  it('PERMISSION_ORDER 与后端 Permission 枚举 33 项逐词形逐序精确一致', () => {
    expect(PERMISSION_ORDER).toEqual(BACKEND_PERMISSION_SNAPSHOT)
    expect(PERMISSION_ORDER).toHaveLength(33)
  })

  it('ROLE_ORDER 四角色与后端 Role StrEnum 一致且 admin 居首', () => {
    expect(ROLE_ORDER).toEqual(['admin', 'developer', 'operator', 'viewer'])
  })

  it('矩阵键 = 恰好四角色，无多余/缺失', () => {
    expect(Object.keys(ROLE_PERMISSIONS).sort()).toEqual(['admin', 'developer', 'operator', 'viewer'])
  })

  it('ADMIN = 全量 33 项（后端 frozenset(Permission) 语义）', () => {
    expect([...ROLE_PERMISSIONS.admin].sort()).toEqual([...PERMISSION_ORDER].sort())
    expect(ROLE_PERMISSIONS.admin).toHaveLength(33)
  })

  it('DEVELOPER = 31 项，不含用户管理和监控权限', () => {
    expect(ROLE_PERMISSIONS.developer).toHaveLength(31)
    expect(ROLE_PERMISSIONS.developer).not.toContain('manage_user')
    const missing = PERMISSION_ORDER.filter(
      (p) => !(ROLE_PERMISSIONS.developer as readonly string[]).includes(p),
    )
    expect(missing).toEqual(['manage_user', 'monitor:read'])
  })

  it('OPERATOR = 18 项精确快照（运行/观测面）', () => {
    expect([...ROLE_PERMISSIONS.operator].sort()).toEqual(
      [
        'run_instance',
        'view_all',
        'execute_sql',
        'project:read',
        'workflow:read',
        'workflow:run',
        'task:read',
        'task:run',
        'datasource:read',
        'datasource:use',
        'sql:read',
        'schedule:read',
        'lineage:read',
        'quality:read',
        'quality:run',
        'standard:read',
        'audit:read',
        'monitor:read',
      ].sort(),
    )
  })

  it('VIEWER = 10 项精确快照（纯只读观测面）', () => {
    expect([...ROLE_PERMISSIONS.viewer].sort()).toEqual(
      [
        'view_all',
        'project:read',
        'workflow:read',
        'task:read',
        'datasource:read',
        'sql:read',
        'schedule:read',
        'lineage:read',
        'quality:read',
        'standard:read',
      ].sort(),
    )
  })

  it('角色基数链：admin(33) > developer(31) > operator(18) > viewer(10)', () => {
    const sizes = ROLE_ORDER.map((r) => ROLE_PERMISSIONS[r].length)
    expect(sizes).toEqual([33, 31, 18, 10])
  })

  it('写/管理类权限点零授予 operator 与 viewer（越权防线快照）', () => {
    const writeish = PERMISSION_ORDER.filter(
      (p) =>
        p.endsWith(':write') ||
        p.endsWith(':write-ddl') ||
        p.endsWith(':manage') ||
        p.endsWith(':publish') ||
        p.endsWith(':delete') ||
        p.endsWith(':approve') ||
        p === 'manage_user' ||
        p === 'edit_definition',
    )
    for (const r of ['operator', 'viewer'] as const) {
      for (const p of writeish) {
        expect(roleHasPermission(r, p), `${r} 不应持有写/管理类权限 ${p}`).toBe(false)
      }
    }
  })

  it('roleHasPermission 与矩阵一致（抽查 granted / denied 两向）', () => {
    expect(roleHasPermission('admin', 'manage_user')).toBe(true)
    expect(roleHasPermission('developer', 'manage_user')).toBe(false)
    expect(roleHasPermission('operator', 'workflow:run')).toBe(true)
    expect(roleHasPermission('operator', 'workflow:publish')).toBe(false)
    expect(roleHasPermission('viewer', 'project:read')).toBe(true)
    expect(roleHasPermission('viewer', 'audit:read')).toBe(false)
  })
})
