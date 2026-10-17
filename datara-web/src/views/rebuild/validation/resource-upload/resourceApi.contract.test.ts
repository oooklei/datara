/**
 * R4-RESOURCE 契约测试（node 环境，纯契约层无组件挂载）。
 * RED describe：方法清单冻结、本地预校验行为（扩展名白名单 + 大小上限）。
 * GREEN describe：R4 批次接线断言（接线计划 Task 4；包络 {code,msg,data} 沿 R2/R7 固化；
 * multipart 不手工设 Content-Type（浏览器自动 boundary）；响应 snake→camel；
 * contentBase64 缺失 fail-fast；RES_* 非 2xx 保码透出）。
 * 语义源：客户要求 #4 + 纠偏设计 §5.3（资源身份/版本/禁隐式 latest）+ A2 v2.1 冻结契约。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  R4_RESOURCE_CONTRACT_METHODS,
  RESOURCE_MAX_SIZE_BYTES,
  createResourceContract,
  validateUploadDraft,
} from '../../../../services/rebuild/resourceApi'

describe('R4 resourceApi contract (RED)', () => {
  it('contract method list is frozen to the resource version subset', () => {
    expect(R4_RESOURCE_CONTRACT_METHODS).toHaveLength(5)
    expect(R4_RESOURCE_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'uploadResource',
        'listResources',
        'listResourceVersions',
        'getResourceVersion',
        'bindResourceVersion',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createResourceContract()
    for (const method of R4_RESOURCE_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('validateUploadDraft enforces per-kind extension whitelist', () => {
    expect(validateUploadDraft('sql', 'job.sql', 100)).toEqual([])
    expect(validateUploadDraft('python', 'job.py', 100)).toEqual([])
    expect(validateUploadDraft('shell', 'job.sh', 100)).toEqual([])
    const wrong = validateUploadDraft('sql', 'job.py', 100)
    expect(wrong).toHaveLength(1)
    expect(wrong[0]).toMatchObject({ field: 'filename', code: 'TYPE_NOT_ALLOWED' })
    const noExt = validateUploadDraft('shell', 'job', 100)
    expect(noExt[0]).toMatchObject({ field: 'filename', code: 'TYPE_NOT_ALLOWED' })
  })

  it('validateUploadDraft enforces the size limit draft constant', () => {
    expect(RESOURCE_MAX_SIZE_BYTES).toBe(20 * 1024 * 1024)
    const exceeded = validateUploadDraft('sql', 'big.sql', RESOURCE_MAX_SIZE_BYTES + 1)
    expect(exceeded).toHaveLength(1)
    expect(exceeded[0]).toMatchObject({ field: 'sizeBytes', code: 'SIZE_EXCEEDED' })
    expect(validateUploadDraft('sql', 'ok.sql', RESOURCE_MAX_SIZE_BYTES)).toEqual([])
  })
})

/* ---------- GREEN 接线断言（R4 批次，接线计划 Task 4；包络沿 R2/R7 固化） ---------- */

function stubFetchWithEnvelope(data: unknown, status = 200): ReturnType<typeof vi.fn> {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('R4 resourceApi contract (GREEN wired)', () => {
  it('uploadResource posts real multipart /uploads without manual Content-Type and maps the version payload snake-to-camel', async () => {
    const fetchMock = stubFetchWithEnvelope({
      resource_id: 5,
      version: 1,
      size_bytes: 4,
      digest: 'abc',
      uploaded_at: '2026-10-17T00:00:00Z',
    })
    vi.stubGlobal('fetch', fetchMock)
    const version = await createResourceContract().uploadResource({
      projectId: 1,
      kind: 'sql',
      filename: 'etl.sql',
      sizeBytes: 4,
      contentBase64: 'ZGF0YQ==',
    })
    expect(version).toEqual({
      resourceId: 5,
      version: 1,
      sizeBytes: 4,
      digest: 'abc',
      uploadedAt: '2026-10-17T00:00:00Z',
    })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/resources/uploads')
    expect(init.method).toBe('POST')
    const form = init.body as FormData
    expect(form instanceof FormData).toBe(true)
    expect(form.get('project_id')).toBe('1')
    expect(form.get('kind')).toBe('sql')
    const file = form.get('file') as File
    expect(file.name).toBe('etl.sql')
    expect((init.headers as Record<string, string>)['Content-Type']).toBeUndefined()
  })

  it('uploadResource without contentBase64 fails fast with CONTRACT_VIOLATION (no request sent)', async () => {
    const fetchMock = stubFetchWithEnvelope({})
    vi.stubGlobal('fetch', fetchMock)
    await expect(
      createResourceContract().uploadResource({ projectId: 1, kind: 'sql', filename: 'etl.sql', sizeBytes: 4 }),
    ).rejects.toMatchObject({ code: 'CONTRACT_VIOLATION', name: 'ContractApiError' })
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('listResources GETs the collection root with project_id and optional kind filter', async () => {
    const fetchMock = stubFetchWithEnvelope([{ resource_id: 5, name: 'etl.sql', kind: 'sql', size_bytes: 4, latest_version: 2 }])
    vi.stubGlobal('fetch', fetchMock)
    await expect(createResourceContract().listResources(1, 'sql')).resolves.toEqual([
      { resourceId: 5, name: 'etl.sql', kind: 'sql', sizeBytes: 4, latestVersion: 2 },
    ])
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/resources?project_id=1&kind=sql')
    expect(init.method).toBe('GET')
  })

  it('listResourceVersions GETs the immutable version chain', async () => {
    const fetchMock = stubFetchWithEnvelope([
      { resource_id: 5, version: 1, size_bytes: 4, digest: 'abc', uploaded_at: '2026-10-17T00:00:00Z' },
    ])
    vi.stubGlobal('fetch', fetchMock)
    await expect(createResourceContract().listResourceVersions(5, 1)).resolves.toEqual([
      { resourceId: 5, version: 1, sizeBytes: 4, digest: 'abc', uploadedAt: '2026-10-17T00:00:00Z' },
    ])
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/v1/rebuild/resources/5/versions?project_id=1')
  })

  it('getResourceVersion GETs one explicit version (no implicit latest)', async () => {
    const fetchMock = stubFetchWithEnvelope({
      resource_id: 5,
      version: 2,
      size_bytes: 8,
      digest: 'def',
      uploaded_at: '2026-10-17T01:00:00Z',
    })
    vi.stubGlobal('fetch', fetchMock)
    await expect(createResourceContract().getResourceVersion(5, 2, 1)).resolves.toEqual({
      resourceId: 5,
      version: 2,
      sizeBytes: 8,
      digest: 'def',
      uploadedAt: '2026-10-17T01:00:00Z',
    })
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/v1/rebuild/resources/5/versions/2?project_id=1')
  })

  it('bindResourceVersion POSTs /bindings with the snake body and maps binding_id', async () => {
    const fetchMock = stubFetchWithEnvelope({ bound: true, binding_id: 9 })
    vi.stubGlobal('fetch', fetchMock)
    await expect(
      createResourceContract().bindResourceVersion({
        projectId: 1,
        workflowId: 10,
        workflowVersion: 3,
        taskId: 'clean',
        resourceId: 5,
        resourceVersion: 2,
      }),
    ).resolves.toEqual({ bound: true, bindingId: 9 })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/resources/bindings')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      project_id: 1,
      workflow_id: 10,
      workflow_version: 3,
      task_id: 'clean',
      resource_id: 5,
      resource_version: 2,
    })
  })

  it('RES_* business error on HTTP 400 keeps both httpStatus and the backend code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: 'RES_TYPE_NOT_ALLOWED', msg: 'kind/extension mismatch', data: null }), { status: 400 }),
      ),
    )
    await expect(
      createResourceContract().uploadResource({
        projectId: 1,
        kind: 'sql',
        filename: 'etl.sql',
        sizeBytes: 4,
        contentBase64: 'ZGF0YQ==',
      }),
    ).rejects.toMatchObject({ httpStatus: 400, code: 'RES_TYPE_NOT_ALLOWED', name: 'ContractApiError' })
  })
})
