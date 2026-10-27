/**
 * L3-05 契约测试：路由守卫 projectId 归属校验（上下文守护，s251 派令）
 *
 * 锚定面：越权项目访问被拦截（4041 负断言：不在 listProjects 可见集合 → 回 /）；
 * 认证先行（增量 1 基线零变化）；非整数 projectId 拦截；listProjects 失败 fail-closed；
 * seg 不归守卫管（4042 后端语义，ProjectSegmentView 占位承载）；非项目路径零归属请求。
 * 注：产品真实 router（index.ts default，守卫本身）；projectApi mock 走 vi.hoisted。
 * 4041/4042/403 语义映射披露见 router/index.ts 头注释（前端唯一可判定源=listProjects）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { clearToken, setToken } from '../../services/http'
import productRouter from '../index'

const { listProjectsSpy, currentSessionSpy, authAccountStub } = vi.hoisted(() => ({
  listProjectsSpy: vi.fn(),
  currentSessionSpy: vi.fn(),
  authAccountStub: { value: null as null | { id: number; username: string; role: string } },
}))

vi.mock('../../services/rebuild/projectApi', () => ({
  listProjects: listProjectsSpy,
}))

vi.mock('../../services/rebuild/authApi', () => ({
  authAccount: authAccountStub,
  currentSession: currentSessionSpy,
}))

beforeEach(() => {
  localStorage.clear()
  setToken('t-guard-project')
  listProjectsSpy.mockReset()
  currentSessionSpy.mockReset()
  authAccountStub.value = null
  currentSessionSpy.mockRejectedValue(new Error('no session cookie'))
  listProjectsSpy.mockResolvedValue({
    total: 2,
    list: [
      { id: 9, name: '项目九' },
      { id: 10, name: '项目十' },
    ],
  })
})

describe('L3-05：路由守卫 projectId 归属校验（越权负断言）', () => {
  it('越权项目被拦截（4041 负断言）：token 有效但 /p/99 不在可见集合 → 拦截回 /', async () => {
    await productRouter.push('/p/99')
    expect(productRouter.currentRoute.value.path).toBe('/')
    expect(productRouter.currentRoute.value.name).toBe('home')
    expect(listProjectsSpy).toHaveBeenCalledTimes(1)
  })

  it('合法归属放行：/p/9 在可见集合 → 正常进入 project-workbench', async () => {
    await productRouter.push('/p/9')
    expect(productRouter.currentRoute.value.path).toBe('/p/9')
    expect(productRouter.currentRoute.value.name).toBe('project-workbench')
  })

  it('非整数 projectId 拦截（4041 形态）：/p/abc 不触发归属请求直接回 /', async () => {
    await productRouter.push('/p/abc')
    expect(productRouter.currentRoute.value.path).toBe('/')
    expect(listProjectsSpy).not.toHaveBeenCalled()
  })

  it('认证先行：未登录访问 /p/9 → /login（归属校验后置，零归属请求）', async () => {
    clearToken()
    await productRouter.push('/p/9')
    expect(productRouter.currentRoute.value.path).toBe('/login')
    expect(listProjectsSpy).not.toHaveBeenCalled()
  })

  it('内存 token 丢失时通过 HttpOnly 会话恢复原深链接', async () => {
    clearToken()
    currentSessionSpy.mockResolvedValue({ id: 1, username: 'admin', role: 'admin' })
    await productRouter.push('/p/9/ide')
    expect(productRouter.currentRoute.value.path).toBe('/p/9/ide')
    expect(currentSessionSpy).toHaveBeenCalledTimes(1)
    expect(listProjectsSpy).toHaveBeenCalledTimes(1)
  })

  it('匿名访问登录页不探测会话，避免产生预期内但污染控制台的 401', async () => {
    clearToken()
    await productRouter.push('/login')
    expect(productRouter.currentRoute.value.path).toBe('/login')
    expect(currentSessionSpy).not.toHaveBeenCalled()
  })

  it('fail-closed：listProjects 请求失败 → 拦截回 /（守护正确性优先于可达性）', async () => {
    listProjectsSpy.mockRejectedValue(new Error('HTTP 500 /rebuild/projects'))
    await productRouter.push('/p/9')
    expect(productRouter.currentRoute.value.path).toBe('/')
  })

  it('seg 不归守卫管（4042 占位语义）：合法项目 + 未知 seg → 放行 project-segment', async () => {
    await productRouter.push('/p/9/unknown-seg')
    expect(productRouter.currentRoute.value.path).toBe('/p/9/unknown-seg')
    expect(productRouter.currentRoute.value.name).toBe('project-segment')
  })

  it('非项目路径零归属请求：全局路由导航不触发 listProjects（归属校验仅 /p/ 前缀）', async () => {
    await productRouter.push('/')
    expect(productRouter.currentRoute.value.path).toBe('/')
    expect(listProjectsSpy).not.toHaveBeenCalled()
  })

  it('旧项目业务入口使用首个可见项目归一到项目作用域', async () => {
    await productRouter.push('/ide')
    expect(productRouter.currentRoute.value.path).toBe('/p/9/ide')
    expect(localStorage.getItem('datara.active-project')).toBe('9')
  })

  it('旧任务中心入口优先使用最近活动且仍可见的项目', async () => {
    localStorage.setItem('datara.active-project', '10')
    await productRouter.push('/dag')
    expect(productRouter.currentRoute.value.path).toBe('/p/10/dag')
  })

  it('部署运维与系统管理保持全局路径，不发生项目归一', async () => {
    await productRouter.push('/dep/runtime')
    expect(productRouter.currentRoute.value.path).toBe('/dep/runtime')
    await productRouter.push('/sys')
    expect(productRouter.currentRoute.value.path).toBe('/sys')
  })
})
