import { getJson, patchJson, postJson } from '../http'
import type { AuthRole } from './authApi'

export const USER_ROLES: readonly AuthRole[] = ['admin', 'developer', 'operator', 'viewer'] as const
export type UserStatus = 'enabled' | 'disabled'

export interface PlatformUser {
  id: number
  username: string
  role: AuthRole
  status: UserStatus
  createdAt: string | null
}

interface UserWire extends Omit<PlatformUser, 'createdAt'> { created_at?: string | null; createdAt?: string | null }
interface UserListWire { list: UserWire[] }

const normalize = (user: UserWire): PlatformUser => ({
  id: user.id,
  username: user.username,
  role: user.role,
  status: user.status,
  createdAt: user.createdAt ?? user.created_at ?? null,
})

export async function listUsers(): Promise<{ list: PlatformUser[] }> {
  const data = await getJson<UserListWire>('/rebuild/users')
  return { list: data.list.map(normalize) }
}

export function createUser(input: { username: string; password: string; role: AuthRole }): Promise<UserWire> {
  return postJson<UserWire>('/rebuild/users', input)
}

export function updateUserRole(userId: number, role: AuthRole): Promise<UserWire> {
  return patchJson<UserWire>(`/rebuild/users/${userId}/role`, { role })
}

export function updateUserStatus(userId: number, status: UserStatus): Promise<UserWire> {
  return patchJson<UserWire>(`/rebuild/users/${userId}/status`, { status })
}

export function updateUserPassword(userId: number, password: string): Promise<UserWire> {
  return patchJson<UserWire>(`/rebuild/users/${userId}/password`, { password })
}
