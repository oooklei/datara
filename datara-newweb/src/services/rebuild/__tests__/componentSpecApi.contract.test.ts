import { beforeEach, describe, expect, it, vi } from 'vitest'

import { loadComponentSpecs, resetComponentSpecCache } from '../componentSpecApi'
import { setToken } from '../../http'

const ETAG = `"${'a'.repeat(64)}"`

describe('componentSpecApi exception contract', () => {
  beforeEach(() => {
    resetComponentSpecCache()
    setToken('ordinary-token')
    vi.unstubAllGlobals()
  })

  it('loads the naked items document with the ordinary token and records the strong ETag', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [{ type: 'sql' }] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json', ETag: ETAG },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(loadComponentSpecs()).resolves.toMatchObject({
      items: [{ type: 'sql' }], etag: ETAG, source: 'network',
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/rebuild/components/spec', {
      headers: { token: 'ordinary-token' },
    })
  })

  it('revalidates with If-None-Match and reuses the successful body on 304', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ type: 'sql' }] }), { status: 200, headers: { ETag: ETAG } }))
      .mockResolvedValueOnce(new Response(null, { status: 304, headers: { ETag: ETAG } }))
    vi.stubGlobal('fetch', fetchMock)

    await loadComponentSpecs()
    await expect(loadComponentSpecs()).resolves.toMatchObject({ source: 'not-modified', items: [{ type: 'sql' }] })
    expect(fetchMock.mock.calls[1]?.[1]).toEqual({ headers: { token: 'ordinary-token', 'If-None-Match': ETAG } })
  })

  it('uses only the last successful response after a refresh failure', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [{ type: 'python' }] }), { status: 200, headers: { ETag: ETAG } }))
      .mockRejectedValueOnce(new Error('offline')))
    await loadComponentSpecs()
    await expect(loadComponentSpecs()).resolves.toMatchObject({ source: 'last-success', items: [{ type: 'python' }] })
  })

  it('fails closed on the first request and remains retryable', async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [] }), { status: 200, headers: { ETag: ETAG } }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(loadComponentSpecs()).rejects.toThrow('offline')
    await expect(loadComponentSpecs()).resolves.toMatchObject({ source: 'network', items: [] })
  })

  it('rejects weak or truncated validators instead of caching them', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), {
      status: 200,
      headers: { ETag: '"short"' },
    })))
    await expect(loadComponentSpecs()).rejects.toThrow('strong SHA-256 ETag')
  })
})

