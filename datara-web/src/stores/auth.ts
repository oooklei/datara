/**
 * 认证与授权中心（Pinia）。
 * F5 登录鉴权（I1）：login/logout + token（localStorage 'datara_token'）+ 角色权限点静态映射
 *   ROLE_PERMS（前端镜像 §6.1）：admin=[manage_user,edit_definition,run_instance,view_all] /
 *   dev=[edit_definition,run_instance,view_all] / analyst=[run_instance,view_all] / viewer=[view_all]。
 * M15 数据安全（既有）：数据权限=密级×许可×业务域；系统权限降级 canEdit/can；演示态身份切换。
 * mock 模式（VITE_API_MODE=mock）：login 本地校验四账号默认密码，不调后端（不挡本地测试，默认 admin 视角）。
 */
import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import { dataStore } from '../services/mock/dataStore'
import { http, setToken, getToken } from '../services/http'
import { apiMode, isMock } from '../services'
import type { DbUser, User } from '../services/types'

const LS_KEY = 'datara.currentUser'
/** 登录账号缓存（与 token 同生命周期）：刷新后恢复 account，避免 canEdit 误降级只读 */
const ACCOUNT_KEY = 'datara.account'

/** 密级序：数值越大越敏感 */
export const SECURITY_LEVELS = ['公开', '内部', '机密', '绝密'] as const
export function secRank(s: string | undefined): number {
  const i = SECURITY_LEVELS.indexOf((s ?? '内部') as (typeof SECURITY_LEVELS)[number])
  return i < 0 ? 1 : i
}

/* ---------- 权限点静态映射（前端镜像 §6.1，无权限配置 UI） ---------- */
export const ROLE_PERMS: Record<string, string[]> = {
  admin: ['manage_user', 'edit_definition', 'run_instance', 'view_all'],
  dev: ['edit_definition', 'run_instance', 'view_all'],
  analyst: ['run_instance', 'view_all'],
  viewer: ['view_all'],
}
export const ROLE_LABELS: Record<string, string> = {
  admin: '管理员', dev: '开发', analyst: '分析师', viewer: '观察者',
}

/** mock 模式本地账号（与 install.sh 初始账号一致；仅 mock 模式校验用） */
const MOCK_ACCOUNTS: Record<string, string> = {
  admin: 'Admin@123', dev: 'Dev@123', analyst: 'Analyst@123', viewer: 'Viewer@123',
}

export interface AccountInfo { name: string; role: string }

export const useAuthStore = defineStore('auth', () => {
  /* ================= F5 登录态 ================= */
  const token = ref<string>(getToken())
  const account = ref<AccountInfo | null>(null)

  /* 刷新恢复（同步）：token 在而 account 空会使 canEdit 误判 false（画布静默降级只读、palette 消失），
     故登录时随 token 一并持久化 account，store 首次实例化即恢复。 */
  try {
    const saved = localStorage.getItem(ACCOUNT_KEY)
    if (saved) account.value = JSON.parse(saved) as AccountInfo
  } catch { /* 忽略损坏缓存 */ }

  async function login(userName: string, pwd: string): Promise<void> {
    if (apiMode === 'mock') {
      // 纯前端测试：本地校验四账号，不触后端
      if (MOCK_ACCOUNTS[userName] !== pwd) throw new Error('用户名或密码错误')
      setToken(`mock-${userName}`)
      token.value = `mock-${userName}`
      account.value = { name: userName, role: userName }
    } else {
      const data = await http.post<{ token: string; user: AccountInfo }>('/login', {
        user_name: userName, user_pwd: pwd,
      })
      setToken(data.token)
      token.value = data.token
      account.value = data.user
    }
    // 登录身份同步到 M15 数据权限视角（密级/域沿用默认）
    current.value = { name: account.value.name, role: ROLE_LABELS[account.value.role] ?? account.value.role, clearance: '绝密' }
    try {
      localStorage.setItem(LS_KEY, JSON.stringify(current.value))
      localStorage.setItem(ACCOUNT_KEY, JSON.stringify(account.value))
    } catch { /* 忽略隐私模式 */ }
  }

  function logout(): void {
    setToken('')
    token.value = ''
    account.value = null
    try { localStorage.removeItem(ACCOUNT_KEY) } catch { /* 忽略隐私模式 */ }
  }

  /** 是否持有登录态（token 存在即视为已登录；mock 模式默认 admin，不挡本地测试） */
  const isLoggedIn = computed(() => isMock || !!token.value)

  /** 权限点判定：mock 模式默认 admin 全量；登录后按角色静态映射 */
  function hasPerm(p: string): boolean {
    if (isMock && !account.value) return true
    const role = account.value?.role ?? ''
    return (ROLE_PERMS[role] ?? []).includes(p)
  }
  /** 全局编辑能力（画布/表单）：F5 权限点优先；未登录走 M15 演示态降级 */
  const canEdit = computed(() =>
    token.value || account.value ? hasPerm('edit_definition') : legacyCanEdit.value)

  /* ================= M15 演示态与数据权限（既有） ================= */
  const current = ref<DbUser>({ name: '王工', role: '数据平台管理员', clearance: '绝密' })
  const users = ref<User[]>([])

  async function init() {
    users.value = (await dataStore.list<User>('users')) ?? []
    // localStorage 恢复 > 集合默认 user
    try {
      const saved = localStorage.getItem(LS_KEY)
      if (saved) {
        const u = JSON.parse(saved) as DbUser
        if (u?.name) current.value = u
        return
      }
    } catch { /* 忽略损坏的本地缓存 */ }
    const dbUser = await dataStore.get<DbUser>('user')
    if (dbUser?.name) current.value = dbUser
  }

  /** 演示态切换身份（按 users 集合的账号；mock 测试用途） */
  function switchUser(u: User) {
    if (u.status === 'disabled') return
    current.value = { name: u.name, role: u.roleName, clearance: u.clearance }
  }

  watch(current, (v) => { try { localStorage.setItem(LS_KEY, JSON.stringify(v)) } catch { /* 私有模式等 */ } })

  /* ---- 系统权限：3 档角色判定 ---- */
  const legacyRoleCode = computed(() => {
    const u = users.value.find((x) => x.name === current.value.name)
    return u?.role ?? (current.value.role === '数据平台管理员' ? 'admin' : 'viewer')
  })
  const roleCode = computed(() =>
    account.value?.role ?? (token.value ? '' : legacyRoleCode.value))
  const roleName = computed(() => account.value ? (ROLE_LABELS[account.value.role] ?? account.value.role) : current.value.role)

  /** 既有系统动作授权（M15）：admin 全量；dev 除审批/部署外可编辑；analyst/viewer 只读 */
  function can(action: string): boolean {
    if (account.value) return hasPerm(action)
    if (legacyRoleCode.value === 'admin') return true
    if (legacyRoleCode.value === 'dev') return !action.startsWith('approve') && !action.startsWith('deploy')
    return false
  }
  const legacyCanEdit = computed(() => legacyRoleCode.value === 'admin' || legacyRoleCode.value === 'dev')

  /* ---- 数据权限：行级（表级） ---- */
  const clearance = computed(() => current.value.clearance ?? '内部')
  const authDomains = computed(() => users.value.find((x) => x.name === current.value.name)?.domains ?? [])
  /** 表是否可访问：密级 ≤ 许可上限；非管理员再叠加域授权（空=全部域） */
  function canSeeTable(t: { security?: string; domain?: string }): boolean {
    if (secRank(t.security) > secRank(clearance.value)) return false
    const ds = authDomains.value
    if (legacyRoleCode.value === 'admin' || ds.length === 0) return true
    return ds.includes(t.domain ?? '')
  }
  /** 预览 sample 前记录审计（谁、何时、查了什么、多少行） */
  async function audit(target: string, rows: number, allowed: boolean, reason: string) {
    const log = {
      id: 'AL' + String(Date.now()).slice(-6),
      user: current.value.name,
      action: '预览',
      target,
      rows: allowed ? rows : 0,
      ts: new Date().toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-').slice(0, 16),
      result: allowed ? '允许' : '拒绝',
      reason,
    }
    await dataStore.save('accessLogs', log)
  }

  return {
    token, account, login, logout, isLoggedIn, hasPerm,
    current, users, init, switchUser, roleCode, roleName, can, canEdit,
    clearance, authDomains, canSeeTable, audit,
  }
})
