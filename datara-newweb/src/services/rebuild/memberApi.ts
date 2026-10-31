/**
 * 项目成员管理契约层（L3-04）。
 *
 * wire 锚（BE datara-backend/rebuild/api/app.py L1009-L1128，冻结实证）：
 *   - GET    /api/v1/rebuild/projects/{id}/members        → data.list: [{user_id, role}]
 *   - POST   /api/v1/rebuild/projects/{id}/members        → body {username, role}；data {project_id, username, role}
 *   - DELETE /api/v1/rebuild/projects/{id}/members/{uid}  → data null
 *   - PATCH  /api/v1/rebuild/projects/{id}/members/{uid}  → body MemberRequest{username, role}；data {project_id, user_id, role}
 *
 * 已知 wire 约束（披露，候 3.2）：
 *   - PATCH 复用 MemberRequest（username: str 必填，Pydantic 校验），后端仅消费 body.role；
 *     GET 列表不含 username，故契约层以空串占位（后端忽略该字段）。
 *   - role wire 词形 = BE identity Role(StrEnum)：admin / developer / operator / viewer。
 *   - 非 2xx 保留成员域业务码，页面按码显示中文（4041/4042/4091）。
 */

import { ContractApiError, deleteJson, getJson, patchJson, postJson } from '../http'

/** 成员角色（wire 词形 = BE `rebuild.identity.contracts.Role` StrEnum）。 */
export type MemberRole = 'admin' | 'developer' | 'operator' | 'viewer'

/** 全量角色选项（与 BE Role 枚举一一对应；POST/patch 下拉与 PATCH 变更共用）。 */
export const MEMBER_ROLES: readonly MemberRole[] = ['admin', 'developer', 'operator', 'viewer'] as const

/** 成员域业务错误中文释义；保留 code 供诊断与重试策略使用。 */
export const MEMBER_ERROR_MESSAGES: Readonly<Record<number, string>> = {
  4041: '项目成员不存在或用户名无效',
  4042: '项目不存在',
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

/** 成员列表项（GET data.list 项，user_id→userId 归一）。 */
export interface MemberEntry {
  userId: number
  role: MemberRole
}

/** 添加成员入参（POST body，wire 直传无大小写差）。 */
export interface AddMemberInput {
  username: string
  role: MemberRole
}

/** POST 响应 data（project_id→projectId 归一）。 */
export interface AddMemberResult {
  projectId: number
  username: string
  role: MemberRole
}

/** PATCH 响应 data（project_id/user_id→projectId/userId 归一）。 */
export interface UpdateMemberResult {
  projectId: number
  userId: number
  role: MemberRole
}

/** 成员列表：GET /api/v1/rebuild/projects/{projectId}/members。 */
export function listMembers(projectId: number): Promise<{ list: MemberEntry[] }> {
  return memberRequest(() => getJson<{ list: Array<{ user_id: number; role: MemberRole }> }>(
    `/rebuild/projects/${projectId}/members`, undefined, MEMBER_REQUEST_OPTIONS,
  )).then((page) => ({ list: page.list.map((m) => ({ userId: m.user_id, role: m.role })) }))
}

/** 添加成员：POST /api/v1/rebuild/projects/{projectId}/members。 */
export function addMember(projectId: number, input: AddMemberInput): Promise<AddMemberResult> {
  return memberRequest(() => postJson<{ project_id: number; username: string; role: MemberRole }>(
    `/rebuild/projects/${projectId}/members`,
    input,
    MEMBER_REQUEST_OPTIONS,
  )).then((d) => ({ projectId: d.project_id, username: d.username, role: d.role }))
}

/** 移除成员：DELETE /api/v1/rebuild/projects/{projectId}/members/{userId}。 */
export function removeMember(projectId: number, userId: number): Promise<void> {
  return memberRequest(() => deleteJson<null>(`/rebuild/projects/${projectId}/members/${userId}`, MEMBER_REQUEST_OPTIONS)).then(() => undefined)
}

/**
 * 变更成员角色：PATCH /api/v1/rebuild/projects/{projectId}/members/{userId}。
 * `username` 占位空串：wire 必填但后端不消费，GET 列表亦不含该字段（见文件头披露）。
 */
export function updateMemberRole(projectId: number, userId: number, role: MemberRole): Promise<UpdateMemberResult> {
  return memberRequest(() => patchJson<{ project_id: number; user_id: number; role: MemberRole }>(
    `/rebuild/projects/${projectId}/members/${userId}`,
    { username: '', role },
    MEMBER_REQUEST_OPTIONS,
  )).then((d) => ({ projectId: d.project_id, userId: d.user_id, role: d.role }))
}
