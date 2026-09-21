/**
 * 缺陷回测留痕（2026-09-19）：任务中心 DAG 画布「左侧组件栏缺失」。
 * 机制链（代码走查 + 1.9 浏览器实测确认）：
 * - GraphWorkbench.vue L443：<Palette v-if="effMode === 'edit' && profile.palette.length" />
 * - GraphWorkbench.vue L46：effMode = profile.mode==='edit' && !auth.canEdit ? 'view' : profile.mode
 * - auth.ts：canEdit = 登录态 ? hasPerm('edit_definition') : legacy
 * 角色矩阵（设计行为）：admin/dev 显示组件栏；analyst/viewer 只读降级 view → 组件栏隐藏。
 * 缺陷（已修复）：account 仅在 login() 赋值、不持久化——刷新后「token 在、account 空」，
 *   hasPerm 读空角色 → canEdit 误判 false → admin 画布也静默降级只读、组件栏消失。
 *   修复=登录时持久化 account（datara.account），store 首次实例化同步恢复。
 * 本测试锁定角色矩阵 + 刷新恢复两机制。
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useAuthStore, ROLE_PERMS } from '../auth'
import { dagProfile } from '../../graph/profiles'

/* node 环境无 localStorage：内存 stub（store 实例化前必须就位） */
function stubLocalStorage(): Map<string, string> {
  const map = new Map<string, string>()
  const ls = {
    getItem: (k: string) => map.get(k) ?? null,
    setItem: (k: string, v: string) => void map.set(k, String(v)),
    removeItem: (k: string) => void map.delete(k),
    clear: () => map.clear(),
    key: (i: number) => [...map.keys()][i] ?? null,
    get length() { return map.size },
  }
  Object.defineProperty(globalThis, 'localStorage', { value: ls, configurable: true, writable: true })
  return map
}

describe('任务中心组件栏显隐机制（角色权限降级）', () => {
  it('admin/dev 持有 edit_definition → effMode 保持 edit，组件栏显示', () => {
    expect(ROLE_PERMS.admin).toContain('edit_definition')
    expect(ROLE_PERMS.dev).toContain('edit_definition')
  })
  it('analyst/viewer 无 edit_definition → effMode 降级 view，组件栏隐藏（设计行为）', () => {
    expect(ROLE_PERMS.analyst).not.toContain('edit_definition')
    expect(ROLE_PERMS.viewer).not.toContain('edit_definition')
  })
  it('dagProfile 为 edit 模式且 palette 非空 → admin 登录时组件栏必然渲染', () => {
    expect(dagProfile.mode).toBe('edit')
    expect(dagProfile.palette.length).toBeGreaterThan(0)
    const types = dagProfile.palette.flatMap((g) => (g.items ?? []).map((i) => i.type))
    expect(types).toContain('sync') // I6 C17 解禁在列（数据同步分组）
  })
})

describe('刷新后登录态恢复（组件栏缺失缺陷回归锁定）', () => {
  let map: Map<string, string>
  beforeEach(() => {
    map = stubLocalStorage()
    setActivePinia(createPinia())
  })

  it('token + 缓存账号 → store 实例化即恢复 account，admin 的 canEdit=true', () => {
    map.set('datara_token', 'tok-1')
    map.set('datara.account', JSON.stringify({ name: 'admin', role: 'admin' }))
    const auth = useAuthStore()
    expect(auth.account).toEqual({ name: 'admin', role: 'admin' })
    expect(auth.canEdit).toBe(true)
  })

  it('token 在但无缓存账号（修复前刷新形态）→ canEdit=false（hasPerm 空角色），画布降级只读', () => {
    map.set('datara_token', 'tok-2')
    const auth = useAuthStore()
    expect(auth.account).toBeNull()
    expect(auth.canEdit).toBe(false)
  })

  it('dev 角色恢复后同样可编辑；logout 清除缓存账号', () => {
    map.set('datara_token', 'tok-3')
    map.set('datara.account', JSON.stringify({ name: 'dev', role: 'dev' }))
    const auth = useAuthStore()
    expect(auth.canEdit).toBe(true)
    auth.logout()
    expect(map.has('datara.account')).toBe(false)
    expect(auth.account).toBeNull()
    // token/account 双空 → 走 M15 legacy 演示态（current 默认数据平台管理员 → admin → true），与既有行为一致
    expect(auth.canEdit).toBe(true)
  })
})
