/**
 * 前端权限矩阵冻结常量（增量 15.1-C）。
 *
 * 权威源：datara-backend/rebuild/identity/contracts.py L56-98 `ROLE_PERMISSIONS`
 * （四角色 × 32 权限点；权限词形与后端 Permission StrEnum 的 wire 值逐字一致，
 * 含冒号域前缀如 `project:read`、`sql:write-ddl`）。
 *
 * 契约纪律：本文件为只读冻结快照，对应后端 `authorize()` 契约（contracts.py
 * L101-108，未知角色/权限默认拒绝）。后端矩阵变更须经 15-P0 权限域门 1 评审，
 * 并同步本表与 `__tests__/rolePermissions.contract.test.ts` 快照断言，
 * 禁止前端单侧漂移。口径说明：票面「33 权限点」以后端 Permission 枚举实际
 * 32 项为准（2026-10-21 精读 L21-53 实锚）。
 */

/** 四角色（与后端 Role StrEnum wire 值一致）。 */
export type Role = 'admin' | 'developer' | 'operator' | 'viewer'

/** 角色展示全序（矩阵列序；admin 恒居首）。 */
export const ROLE_ORDER = ['admin', 'developer', 'operator', 'viewer'] as const

/**
 * 权限点全序快照（与 contracts.py Permission 枚举声明序逐项一致，共 32 项）。
 * 该序即矩阵行序；增删/改词形须与后端枚举同步并过契约测试。
 */
export const PERMISSION_ORDER = [
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
] as const

export type Permission = (typeof PERMISSION_ORDER)[number]

/** DEVELOPER：31 项（仅缺 manage_user——用户管理为 admin 专属）。 */
const DEVELOPER_PERMISSIONS: readonly Permission[] = [
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
]

/** OPERATOR：17 项（运行/观测面；无任何 write/manage/publish）。 */
const OPERATOR_PERMISSIONS: readonly Permission[] = [
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
]

/** VIEWER：10 项（纯只读观测面）。 */
const VIEWER_PERMISSIONS: readonly Permission[] = [
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
]

/**
 * 角色 → 授权权限点集合（只读冻结矩阵）。
 * admin 直接引用 PERMISSION_ORDER——与后端 `frozenset(Permission)` 全量语义对齐。
 */
export const ROLE_PERMISSIONS = {
  admin: PERMISSION_ORDER,
  developer: DEVELOPER_PERMISSIONS,
  operator: OPERATOR_PERMISSIONS,
  viewer: VIEWER_PERMISSIONS,
} as const satisfies Record<Role, readonly Permission[]>

/** 判定某角色是否持有某权限点（O(集合) 包含；页面与运行时守卫共用）。 */
export function roleHasPermission(role: Role, permission: Permission): boolean {
  return (ROLE_PERMISSIONS[role] as readonly string[]).includes(permission)
}
