/**
 * B5-d-3 四角色可见性判定链契约（方案 §5 B5「四角色可见性回归（admin/dev/analyst/viewer 不只验登录）」）。
 *
 * 三段链路逐段锚定：
 *  ① 冻结矩阵 rolePermissions.ts（ROLE_PERMISSIONS × roleHasPermission）——词形与后端
 *     contracts.py 权限枚举逐字一致，禁止前端单侧漂移（已有 rolePermissions.contract.test 快照）；
 *  ② 菜单过滤 filterMenu.permissionPassed——G 组（系统管理）五 formal 项声明冻结矩阵权限词：
 *     admin/developer 全量可见，operator 仅见访问审计（audit:read），viewer 整组隐藏；
 *  ③ 组件消费——AppShell buildCtx 注入角色权限集（会话未就绪空集 fail-closed）、
 *     TaskCenterView 变量抽屉 canEdit 由 task:write 判定。
 * 路由守卫仍是访问控制真源（filterMenu.ts 头注）；本链只收敛导航呈现与 UI 可用性，
 * 后端 authorize() 为最终裁决（fail-closed）。
 */
import { describe, expect, it } from 'vitest'
import { menuGroups } from '../menu'
import { filterMenuGroups, type MenuFilterContext } from '../filterMenu'
import { routes } from '../../router/routes'
import {
  PERMISSION_ORDER,
  ROLE_PERMISSIONS,
  roleHasPermission,
  type Role,
} from '../../services/rebuild/rolePermissions'
import appShellSource from '../../layouts/AppShell.vue?raw'
import taskCenterSource from '../../views/TaskCenterView.vue?raw'

const ROLE_ORDER: readonly Role[] = ['admin', 'developer', 'operator', 'viewer']

function ctxWithRole(role: Role): MenuFilterContext {
  const paths = new Set<string>()
  const names = new Set<string>()
  const collect = (path: string | undefined, name: string | undefined): void => {
    if (path) paths.add(path)
    if (name) names.add(name)
  }
  for (const g of menuGroups) for (const i of g.items) collect(i.path, i.routeName)
  const walk = (records: typeof routes): void => {
    for (const r of records) {
      collect(r.path, r.name === undefined ? undefined : String(r.name))
      if (r.children) walk(r.children)
    }
  }
  walk(routes)
  return { registeredPaths: paths, registeredRouteNames: names, permissions: new Set<string>(ROLE_PERMISSIONS[role]) }
}

describe('B5-d-3 判定链①：G 组权限词取自冻结矩阵', () => {
  const g = menuGroups.find((x) => x.id === 'system')!

  it('五 formal 项逐项对拍（sec-perm→security:read，sec-audit→audit:read，open-api/open-key/llm-config→security:manage）', () => {
    const expectPerm: Record<string, string> = {
      'sec-perm': 'security:read',
      'sec-audit': 'audit:read',
      'open-api': 'security:manage',
      'open-key': 'security:manage',
      'llm-config': 'security:manage',
    }
    for (const [id, perm] of Object.entries(expectPerm)) {
      const item = g.items.find((i) => i.id === id)
      expect(item, `${id} 应存在`).toBeDefined()
      expect(item!.permission, `${id} permission 词`).toBe(perm)
    }
  })

  it('权限词全部属于冻结矩阵 PERMISSION_ORDER（禁漂移词形）', () => {
    const perms = g.items.map((i) => i.permission).filter((p): p is string => !!p)
    expect(perms.length).toBeGreaterThan(0)
    for (const p of perms) expect(PERMISSION_ORDER as readonly string[]).toContain(p)
  })
})

describe('B5-d-3 判定链②：菜单四角色可见性矩阵', () => {
  const viewFor = (role: Role) => filterMenuGroups(ctxWithRole(role))
  const groupIds = (role: Role) => viewFor(role).map((v) => v.group.id)

  it('admin/developer：系统管理组全量 5 个 formal 项（embedded 调用日志不进侧栏）', () => {
    for (const role of ['admin', 'developer'] as const) {
      const system = viewFor(role).find((v) => v.group.id === 'system')
      expect(system, `${role} 应见系统管理组`).toBeDefined()
      expect(system!.items.map((i) => i.id)).toEqual(['sec-perm', 'sec-audit', 'open-api', 'open-key', 'llm-config'])
    }
  })

  it('operator：仅见访问审计（冻结矩阵 operator 含 audit:read，缺 security:read/security:manage）', () => {
    const system = viewFor('operator').find((v) => v.group.id === 'system')
    expect(system).toBeDefined()
    expect(system!.items.map((i) => i.id)).toEqual(['sec-audit'])
    expect(roleHasPermission('operator', 'security:read')).toBe(false)
    expect(roleHasPermission('operator', 'audit:read')).toBe(true)
    expect(roleHasPermission('operator', 'security:manage')).toBe(false)
  })

  it('viewer：系统管理组整组隐藏（三权限词全缺）', () => {
    expect(groupIds('viewer')).not.toContain('system')
    expect(roleHasPermission('viewer', 'security:read')).toBe(false)
    expect(roleHasPermission('viewer', 'audit:read')).toBe(false)
    expect(roleHasPermission('viewer', 'security:manage')).toBe(false)
  })

  it('四角色其余功能组（总览/任务中心/集成/开发/治理/运维）均可见——角色差异只收敛在系统管理面', () => {
    for (const role of ROLE_ORDER) {
      const ids = groupIds(role)
      for (const gid of ['overview', 'task-center', 'integration', 'development', 'governance', 'operations']) {
        expect(ids, `${role} 应见 ${gid}`).toContain(gid)
      }
    }
  })
})

describe('B5-d-3 判定链③：组件消费接线', () => {
  it('AppShell buildCtx 注入角色权限集（会话未就绪空集 fail-closed）', () => {
    expect(appShellSource).toContain('ROLE_PERMISSIONS[role]')
    expect(appShellSource).toContain('permissions: new Set<string>(role ? ROLE_PERMISSIONS[role] : [])')
  })

  it('TaskCenterView 变量抽屉 canEdit 由 task:write 判定并透传', () => {
    expect(taskCenterSource).toContain("roleHasPermission(role, 'task:write')")
    expect(taskCenterSource).toContain(':can-edit="canEditVariables"')
  })

  it('task:write 冒烟：admin/developer 持有，operator/viewer 无（与冻结矩阵一致）', () => {
    expect(roleHasPermission('admin', 'task:write')).toBe(true)
    expect(roleHasPermission('developer', 'task:write')).toBe(true)
    expect(roleHasPermission('operator', 'task:write')).toBe(false)
    expect(roleHasPermission('viewer', 'task:write')).toBe(false)
  })
})
