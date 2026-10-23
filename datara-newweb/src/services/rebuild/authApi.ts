/**
 * 认证域契约层 — 登录 / 登出。
 *
 * 端点实证：datara-backend/rebuild/api/app.py
 *   POST /api/v1/rebuild/login    body `{username, password}`
 *     → `{code:0, msg:'success', data:{token, user:{id, username, role}}}`
 *     401 `{code:1001}` 凭据无效；403 `{code:1006}` 账号停用（不签发 token）
 *   POST /api/v1/rebuild/logout  → `{code:0, msg:'success', data:null}`（吊销 active token）
 *
 * 角色词形（rebuild/identity/contracts.py `Role`）：admin / developer / operator / viewer。
 * 与旧前端（datara-web）的 admin/dev/analyst/viewer 不同名，本页与 UI 一律消费后端词形。
 */

import { clearToken, postJson, setToken } from '../http'

export type AuthRole = 'admin' | 'developer' | 'operator' | 'viewer'

export interface AuthAccount {
  id: number
  username: string
  role: AuthRole
}

export interface LoginResult {
  token: string
  account: AuthAccount
}

interface LoginWire {
  token: string
  user: { id: number; username: string; role: AuthRole }
}

/**
 * 登录：成功即落 token（localStorage `datara_token`），返回账号信息供 UI 展示。
 * 匿名请求（登录端点无鉴权），故显式 `anonymous`。
 */
export function login(username: string, password: string): Promise<LoginResult> {
  return postJson<LoginWire>('/rebuild/login', { username, password }, { anonymous: true }).then((d) => {
    setToken(d.token)
    return {
      token: d.token,
      account: { id: d.user.id, username: d.user.username, role: d.user.role },
    }
  })
}

/**
 * 登出：调后端吊销 active token，随后清本地 token。
 * 后端吊销失败（网络/已失效）不阻断本地清理——本地态必须收敛。
 */
export async function logout(): Promise<void> {
  try {
    await postJson<null>('/rebuild/logout')
  } catch {
    // 后端吊销失败（网络/已失效）不阻断本地清理
  } finally {
    clearToken()
  }
}
