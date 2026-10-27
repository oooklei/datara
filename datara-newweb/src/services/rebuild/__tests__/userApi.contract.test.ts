import { afterEach, describe, expect, it, vi } from 'vitest'
import { clearToken, setToken } from '../../http'
import { createUser, listUsers, updateUserRole, updateUserStatus } from '../userApi'

afterEach(() => { vi.unstubAllGlobals(); clearToken() })

describe('platform user lifecycle API', () => {
  it('lists users and normalizes created_at', async () => {
    setToken('admin-token')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 0, msg: 'success', data: { list: [{ id: 2, username: 'dev', role: 'developer', status: 'enabled', created_at: '2026-10-27T00:00:00' }] },
    }), { status: 200 })))

    await expect(listUsers()).resolves.toEqual({ list: [{ id: 2, username: 'dev', role: 'developer', status: 'enabled', createdAt: '2026-10-27T00:00:00' }] })
  })

  it('creates users and mutates role/status through the authoritative endpoints', async () => {
    setToken('admin-token')
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ code: 0, msg: 'success', data: { id: 8, username: 'new', role: 'viewer', status: 'enabled' } }), { status: 200 })))
    vi.stubGlobal('fetch', fetchMock)
    await createUser({ username: 'new', password: 'Safe@123', role: 'viewer' })
    await updateUserRole(8, 'operator')
    await updateUserStatus(8, 'disabled')
    expect(fetchMock.mock.calls.map((call) => [call[0], (call[1] as RequestInit).method])).toEqual([
      ['/api/v1/rebuild/users', 'POST'],
      ['/api/v1/rebuild/users/8/role', 'PATCH'],
      ['/api/v1/rebuild/users/8/status', 'PATCH'],
    ])
  })
})
