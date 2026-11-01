/**
 * 项目成员管理契约层（L3-04 / P1-P2 对齐）。
 *
 * wire 锚（BE datara-backend/rebuild/api/app.py）：
 *   - GET    /api/v1/rebuild/projects/{id}/members  → data.list: [{user_id, username, role, project_role, status, joined_at}]
 *   - POST   /api/v1/rebuild/projects/{id}/members  → body {username, role}；data {project_id, user_id, username, role, project_role}
 *   - DELETE /api/v1/rebuild/projects/{id}/members/{uid}  → data null
 *   - PATCH  /api/v1/rebuild/projects/{id}/members/{uid}  → body {username, role}；data {project_id, user_id, role, project_role}
 *   - GET    /api/v1/rebuild/project-roles           → data.list: [{value, label, inherits_platform, permissions}]
 *
 * 项目角色（BE identity.contracts.ProjectRole）：inherit / viewer / operator。
 * 存量成员 role 可能是平台角色词形（admin/developer/operator/viewer），后端通过 resolve_project_role 自动映射。
 * 前端角色下拉只展示项目角色（inherit/viewer/operator），POST/PATCH 传项目角色词形。
 */

import { ContractApiError, deleteJson, getJson, patchJson, postJson } from '../http'

/** 项目角色（BE ProjectRole StrEnum）。 */
export type MemberRole = 'inherit' | 'viewer' | 'operator'

/** 项目角色下拉选项（由后端 /project-roles 端点驱动，此处为降级常量）。 */
export const PROJECT_ROLES: readonly MemberRole[] = ['inherit', 'viewer', 'operator'] as const

export const PROJECT_ROLE_LABELS: Readonly<Record<MemberRole, string>> = {
  inherit: '继承平台角色',
  viewer: '项目观察者（只读）',
  operator: '项目操作员（运维）',
}

/** 成员域业务错误中文释义。 */
export const MEMBER_ERROR_MESSAGES: Readonly<Record<number, string>> = {
  4002: '不支持的项目角色',
  4041: '项目成员不存在或用户名无效',
  4042: '项目不存在',
  4043: '用户不存在',
  4091: '该用户已经是项目成员',
}

const MEMBER_REQUEST_OPTIONS = { preserveEnvelopeCode: true } as const

function memberError(error: unknown): never {
  if (error instanceof ContractApiError && typeof error.code === 'number') {
    const msg = MEMBER_ERROR_MESSAGES[error.code]
    if (msg) throw new ContractApiError({ httpStatus: error.httpStatus, code: error.code, msg, raw: error.raw })
  }
  throw error
}

async function memberRequest<T>(request: () => Promise<T>): Promise<T> {
  try { return await request() } catch (error) { return memberError(error) }
}

/** 成员列表项（P1 扩展：username / status / joined_at / project_role）。 */
export interface MemberEntry {
  userId: number
  username: string
  role: string          // 存量词形（可能是平台角色词形）
  projectRole: MemberRole | null
  status: string | null // enabled / disabled
  joinedAt: string | null
}

/** 添加成员入参（role 传项目角色词形）。 */
export interface AddMemberInput {
  username: string
  role: MemberRole
}

/** POST 响应。 */
export interface AddMemberResult {
  projectId: number
  userId: number
  username: string
  role: string
  projectRole: MemberRole | null
}

/** PATCH 响应。 */
export interface UpdateMemberResult {
  projectId: number
  userId: number
  role: string
  projectRole: MemberRole | null
}

/** 项目角色目录项（GET /project-roles）。 */
export interface ProjectRoleCatalogEntry {
  value: MemberRole
  label: string
  inheritsPlatform: boolean
  permissions: string[] | null
}

/** 成员列表：GET /api/v1/rebuild/projects/{projectId}/members。 */
export function listMembers(projectId: number): Promise<{ list: MemberEntry[] }> {
  return memberRequest(() => getJson<{ list: Array<{
    user_id: number; username: string; role: string; project_role: string | null;
    status: string | null; joined_at: string | null;
  }> }>(
    `/rebuild/projects/${projectId}/members`, undefined, MEMBER_REQUEST_OPTIONS,
  )).then((page) => ({
    list: page.list.map((m) => ({
      userId: m.user_id,
      username: m.username,
      role: m.role,
      projectRole: (m.project_role as MemberRole | null) ?? null,
      status: m.status,
      joinedAt: m.joined_at,
    })),
  }))
}

/** 添加成员：POST /api/v1/rebuild/projects/{projectId}/members。 */
export function addMember(projectId: number, input: AddMemberInput): Promise<AddMemberResult> {
  return memberRequest(() => postJson<{
    project_id: number; user_id: number; username: string; role: string; project_role: string | null;
  }>(
    `/rebuild/projects/${projectId}/members`, input, MEMBER_REQUEST_OPTIONS,
  )).then((d) => ({
    projectId: d.project_id, userId: d.user_id, username: d.username,
    role: d.role, projectRole: (d.project_role as MemberRole | null) ?? null,
  }))
}

/** 移除成员：DELETE /api/v1/rebuild/projects/{projectId}/members/{userId}。 */
export function removeMember(projectId: number, userId: number): Promise<void> {
  return memberRequest(() => deleteJson<null>(`/rebuild/projects/${projectId}/members/${userId}`, MEMBER_REQUEST_OPTIONS)).then(() => undefined)
}

/**
 * 变更成员角色：PATCH /api/v1/rebuild/projects/{projectId}/members/{userId}。
 * role 传项目角色词形；username 占位空串（wire 必填但后端不消费）。
 */
export function updateMemberRole(projectId: number, userId: number, role: MemberRole): Promise<UpdateMemberResult> {
  return memberRequest(() => patchJson<{ project_id: number; user_id: number; role: string; project_role: string | null }>(
    `/rebuild/projects/${projectId}/members/${userId}`,
    { username: '', role },
    MEMBER_REQUEST_OPTIONS,
  )).then((d) => ({
    projectId: d.project_id, userId: d.user_id, role: d.role,
    projectRole: (d.project_role as MemberRole | null) ?? null,
  }))
}

/** 项目角色目录：GET /api/v1/rebuild/project-roles。 */
export function listProjectRoles(): Promise<ProjectRoleCatalogEntry[]> {
  return getJson<{ list: Array<{ value: string; label: string; inherits_platform: boolean; permissions: string[] | null }> }>(
    '/rebuild/project-roles', undefined, MEMBER_REQUEST_OPTIONS,
  ).then((d) => d.list.map((r) => ({
    value: r.value as MemberRole,
    label: r.label,
    inheritsPlatform: r.inherits_platform,
    permissions: r.permissions,
  })))
}
