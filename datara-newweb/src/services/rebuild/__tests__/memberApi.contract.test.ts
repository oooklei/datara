/**
 * memberApi 契约测试（L3-04）。
 *
 * 锚定 BE datara-backend/rebuild/api/app.py members 四端点（L1009/L1046/L1074/L1100，冻结实证）：
 *   - URL 形态 / method / token header / 请求体（含 PATCH username 占位）
 *   - snake wire 归一（user_id/project_id → userId/projectId）
 *   - 非 2xx 默认冻结行为（ContractApiError{httpStatus}，不透业务码）
 */

import { afterEach, describe, expect, it, vi } from 'vitest'
import { ContractApiError } from '../../http'
import { addMember, listMembers, removeMember, updateMemberRole } from '../memberApi'

function stubFetchWithEnvelope(data: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status }),
  )
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('memberApi 契约（members 四端点承接）', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
    globalThis.localStorage?.clear()
  })

  it('listMembers：GET /api/v1/rebuild/projects/{id}/members，携带 token header', async () => {
    globalThis.localStorage?.setItem('datara_token', 'tok-1')
    const fetchMock = stubFetchWithEnvelope({ list: [] })

    await listMembers(3)

    expect(fetchMock).toHaveBeenCalledTimes(1)
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/projects/3/members')
    expect(init.method).toBe('GET')
    expect((init.headers as Record<string, string>).token).toBe('tok-1')
  })

  it('listMembers：wire snake 归一 user_id→userId', async () => {
    stubFetchWithEnvelope({
      list: [
        { user_id: 7, role: 'developer' },
        { user_id: 9, role: 'viewer' },
      ],
    })

    const page = await listMembers(3)

    expect(page.list).toEqual([
      { userId: 7, role: 'developer' },
      { userId: 9, role: 'viewer' },
    ])
  })

  it('addMember：POST 请求体 {username, role} 直传，响应 project_id→projectId', async () => {
    const fetchMock = stubFetchWithEnvelope({ project_id: 3, username: 'bob', role: 'developer' })

    const result = await addMember(3, { username: 'bob', role: 'developer' })

    expect(result).toEqual({ projectId: 3, username: 'bob', role: 'developer' })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/projects/3/members')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ username: 'bob', role: 'developer' })
  })

  it('removeMember：DELETE /api/v1/rebuild/projects/{id}/members/{uid}', async () => {
    const fetchMock = stubFetchWithEnvelope(null)

    await removeMember(3, 7)

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/projects/3/members/7')
    expect(init.method).toBe('DELETE')
  })

  it('updateMemberRole：PATCH 请求体含 username 占位空串 + {role}，响应归一', async () => {
    const fetchMock = stubFetchWithEnvelope({ project_id: 3, user_id: 7, role: 'admin' })

    const result = await updateMemberRole(3, 7, 'admin')

    expect(result).toEqual({ projectId: 3, userId: 7, role: 'admin' })
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/projects/3/members/7')
    expect(init.method).toBe('PATCH')
    expect(JSON.parse(init.body as string)).toEqual({ username: '', role: 'admin' })
  })

  it('非 2xx：默认冻结行为抛 ContractApiError{httpStatus}（403 权限 / 409 重复），不透业务码', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: 1003, msg: 'permission denied', data: null }), { status: 403 }),
      ),
    )
    await expect(listMembers(3)).rejects.toMatchObject({ httpStatus: 403, code: 403 })

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: 4091, msg: 'member already exists', data: null }), { status: 409 }),
      ),
    )
    const err = await addMember(3, { username: 'bob', role: 'viewer' }).catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ContractApiError)
    expect(err).toMatchObject({ httpStatus: 409, code: 409 })
  })
})
