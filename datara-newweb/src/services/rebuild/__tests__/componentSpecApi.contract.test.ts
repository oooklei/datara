import { beforeEach, describe, expect, it, vi } from 'vitest'

import { isDesignComponent, loadComponentSpecs, resetComponentSpecCache, type ComponentSpecItem } from '../componentSpecApi'
import { setToken } from '../../http'

const ETAG = `"${'a'.repeat(64)}"`
const item = (type = 'sql') => ({
  type,
  publishedVersion: 1,
  componentRef: { type, version: 1 },
  workflowTypes: ['NORMAL'],
  runtimeOnly: false,
  identity: { displayName: type },
  description: {},
  inputs: [],
  outputs: [],
  form: { inputs: [], outputs: [], params: [], conditions: [], constraints: [], exclusions: [], refs: [], exports: [] },
  visual: {},
  behaviors: [],
  dropPolicy: null,
  extensions: {},
  specVersion: 1,
  ports: {},
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

describe('componentSpecApi exception contract', () => {
  beforeEach(() => {
    resetComponentSpecCache()
    setToken('ordinary-token')
    vi.unstubAllGlobals()
  })

  it('loads the naked items document with the ordinary token and records the strong ETag', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [item()] }), {
      status: 200,
      headers: { 'Content-Type': 'application/json', ETag: ETAG },
    }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(loadComponentSpecs()).resolves.toMatchObject({
      items: [item()], etag: ETAG, source: 'network',
    })
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/rebuild/components/spec', expect.objectContaining({
      headers: { token: 'ordinary-token' },
      signal: expect.any(AbortSignal),
    }))
  })

  it('revalidates with If-None-Match and reuses the successful body on 304', async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [item()] }), { status: 200, headers: { ETag: ETAG } }))
      .mockResolvedValueOnce(new Response(null, { status: 304, headers: { ETag: ETAG } }))
    vi.stubGlobal('fetch', fetchMock)

    await loadComponentSpecs()
    await expect(loadComponentSpecs()).resolves.toMatchObject({ source: 'not-modified', items: [item()] })
    expect(fetchMock.mock.calls[1]?.[1]).toEqual(expect.objectContaining({
      headers: { token: 'ordinary-token', 'If-None-Match': ETAG },
      signal: expect.any(AbortSignal),
    }))
  })

  it('uses only the last successful response after a refresh failure', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [item('python')] }), { status: 200, headers: { ETag: ETAG } }))
      .mockRejectedValueOnce(new Error('offline')))
    await loadComponentSpecs()
    await expect(loadComponentSpecs()).resolves.toMatchObject({ source: 'last-success', items: [item('python')] })
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

  it('requests and caches each workflow catalogue independently', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ items: [] }), {
      status: 200, headers: { ETag: ETAG },
    }))
    vi.stubGlobal('fetch', fetchMock)
    await loadComponentSpecs('SYNC')
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/rebuild/components/spec?workflow_type=SYNC', expect.objectContaining({
      headers: { token: 'ordinary-token' },
      signal: expect.any(AbortSignal),
    }))
  })

  it('deduplicates concurrent requests for the same catalogue', async () => {
    const response = deferred<Response>()
    const fetchMock = vi.fn().mockReturnValue(response.promise)
    vi.stubGlobal('fetch', fetchMock)

    const first = loadComponentSpecs('NORMAL')
    const second = loadComponentSpecs('NORMAL')

    expect(fetchMock).toHaveBeenCalledTimes(1)
    response.resolve(new Response(JSON.stringify({ items: [item()] }), {
      status: 200,
      headers: { ETag: ETAG },
    }))
    const [firstSnapshot, secondSnapshot] = await Promise.all([first, second])
    expect(firstSnapshot.items).toEqual(secondSnapshot.items)
  })

  it('aborts the network request when its only subscriber cancels', async () => {
    let requestSignal: AbortSignal | undefined
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined
      return new Promise<Response>((_resolve, reject) => {
        requestSignal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      })
    })
    vi.stubGlobal('fetch', fetchMock)
    const controller = new AbortController()

    const pending = loadComponentSpecs('NORMAL', controller.signal)
    controller.abort()

    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    expect(requestSignal?.aborted).toBe(true)
  })

  it('keeps a shared request alive while another subscriber still needs it', async () => {
    const response = deferred<Response>()
    let requestSignal: AbortSignal | undefined
    const fetchMock = vi.fn().mockImplementation((_url: string, init?: RequestInit) => {
      requestSignal = init?.signal ?? undefined
      return response.promise
    })
    vi.stubGlobal('fetch', fetchMock)
    const cancelled = new AbortController()

    const first = loadComponentSpecs('NORMAL', cancelled.signal)
    const second = loadComponentSpecs('NORMAL')
    cancelled.abort()

    await expect(first).rejects.toMatchObject({ name: 'AbortError' })
    expect(requestSignal?.aborted).toBe(false)
    response.resolve(new Response(JSON.stringify({ items: [item()] }), {
      status: 200,
      headers: { ETag: ETAG },
    }))
    await expect(second).resolves.toMatchObject({ source: 'network' })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('fails closed for runtime-only, mismatched-kind, and unpinned catalogue rows', () => {
    const base = {
      type: 'sql', publishedVersion: 1, componentRef: { type: 'sql', version: 1 }, workflowTypes: ['NORMAL'],
      runtimeOnly: false, identity: {}, description: {}, inputs: [], outputs: [],
      form: { inputs: [], outputs: [], params: [], conditions: [], constraints: [], exclusions: [], refs: [], exports: [] },
      visual: {}, behaviors: [], dropPolicy: null, extensions: {}, specVersion: 1, ports: {},
    } as ComponentSpecItem
    expect(isDesignComponent(base, 'NORMAL')).toBe(true)
    expect(isDesignComponent({ ...base, runtimeOnly: true }, 'NORMAL')).toBe(false)
    expect(isDesignComponent({ ...base, workflowTypes: ['SYNC'] }, 'NORMAL')).toBe(false)
    expect(isDesignComponent({ ...base, componentRef: { type: 'sql', version: 0 } }, 'NORMAL')).toBe(false)
  })

  it.each([
    { ...item(), runtimeOnly: 'false' },
    { ...item(), workflowTypes: ['ETL'] },
    { ...item(), componentRef: { type: 'python', version: 1 } },
    { ...item(), form: { params: [] } },
    { ...item(), identity: null },
  ])('rejects malformed items without poisoning the cache', async (malformed) => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [malformed] }), { status: 200, headers: { ETag: ETAG } }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ items: [item()] }), { status: 200, headers: { ETag: ETAG } }))
    vi.stubGlobal('fetch', fetchMock)
    await expect(loadComponentSpecs()).rejects.toThrow()
    await expect(loadComponentSpecs()).resolves.toMatchObject({ source: 'network', items: [item()] })
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})

