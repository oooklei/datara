/**
 * R2 变量契约测试（node 环境，纯契约层无组件挂载）。
 * RED describe：方法清单冻结、七级优先级链为设计真源、本地引用语法解析行为。
 * GREEN describe：R2 批次接线断言（接线计划 §1.3；包络 {code,msg,data} 已实证固化）。
 * 语义源：docs/increments/2026-10-14-datara-platform-rebuild-design.md §5。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  R2_VARIABLE_CONTRACT_METHODS,
  VARIABLE_SCOPE_PRIORITY,
  createVariableContract,
  parseVariableReferences,
} from '../../../../services/rebuild/variableApi'

describe('R2 variableApi contract (RED)', () => {
  it('freezes the seven-level priority chain from design section 5', () => {
    expect(VARIABLE_SCOPE_PRIORITY).toEqual(['run', 'task', 'workflow', 'project', 'global', 'env', 'builtin'])
  })

  it('contract method list is frozen to the variable service subset', () => {
    expect(R2_VARIABLE_CONTRACT_METHODS).toHaveLength(6)
    expect(R2_VARIABLE_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'listVariables',
        'saveVariable',
        'completeVariables',
        'checkReference',
        'previewResolution',
        'getRunSnapshot',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createVariableContract()
    for (const method of R2_VARIABLE_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })
})

describe('parseVariableReferences (local pure fn)', () => {
  it('extracts refs, time expressions, and dedupes repeated refs', () => {
    const parsed = parseVariableReferences('a ${global.region} b ${run.dt} c ${global.region} d $[yyyy-MM-dd]')
    expect(parsed.refs).toEqual([
      { scope: 'global', name: 'region' },
      { scope: 'run', name: 'dt' },
    ])
    expect(parsed.timeExpressions).toEqual(['yyyy-MM-dd'])
    expect(parsed.syntaxErrors).toEqual([])
  })

  it('flags unknown scopes, missing dots, and empty names as syntax errors', () => {
    const parsed = parseVariableReferences('${bogus.x} ${nodot} ${global.}')
    expect(parsed.syntaxErrors).toEqual(['${bogus.x}', '${nodot}', '${global.}'])
  })

  it('returns empty result for plain text', () => {
    expect(parseVariableReferences('no variables here')).toEqual({ refs: [], timeExpressions: [], syntaxErrors: [] })
  })
})

/* ---------- GREEN 接线断言（R2 批次，接线计划 §1.3；包络 {code,msg,data} 已实证固化） ---------- */

const TOKEN = 'test-token-r2'

/** stub localStorage 供 getToken()（http.ts）读取 token header */
function stubTokenStorage(): void {
  vi.stubGlobal('localStorage', { getItem: () => TOKEN, setItem: vi.fn(), removeItem: vi.fn() })
}

/** 后端成功包络形态（datara-backend rebuild 域全域实证：{code:0,msg:'success',data}） */
function stubFetchWithEnvelope(data: unknown): ReturnType<typeof vi.fn> {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status: 200 }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('R2 variableApi contract (GREEN wired)', () => {
  it('listVariables GETs the frozen endpoint with snake_case query and maps value_type to valueType', async () => {
    stubTokenStorage()
    const fetchMock = stubFetchWithEnvelope([
      { scope: 'global', name: 'region', value_type: 'string', value: 'cn', description: '大区' },
    ])
    vi.stubGlobal('fetch', fetchMock)
    const rows = await createVariableContract().listVariables(1, ['global', 'project'])
    expect(rows).toEqual([{ scope: 'global', name: 'region', valueType: 'string', value: 'cn', description: '大区' }])
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/variables?project_id=1&scopes=global%2Cproject')
    expect((init.headers as Record<string, string>).token).toBe(TOKEN)
  })

  it('saveVariable POSTs the definition camel-to-snake and validates saved:true', async () => {
    const fetchMock = stubFetchWithEnvelope({ saved: true, scope: 'global', name: 'region' })
    vi.stubGlobal('fetch', fetchMock)
    const result = await createVariableContract().saveVariable(1, {
      scope: 'global',
      name: 'region',
      valueType: 'string',
      value: 'cn',
      sensitive: true,
    })
    expect(result).toEqual({ saved: true, scope: 'global', name: 'region' })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/variables?project_id=1')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      scope: 'global',
      name: 'region',
      value_type: 'string',
      value: 'cn',
      sensitive: true,
    })
  })

  it('saveVariable rejects with ContractApiError when the backend does not confirm saved:true', async () => {
    vi.stubGlobal('fetch', stubFetchWithEnvelope({ saved: false }))
    await expect(
      createVariableContract().saveVariable(1, { scope: 'global', name: 'x', valueType: 'string', value: 'y' }),
    ).rejects.toMatchObject({ name: 'ContractApiError' })
  })

  it('completeVariables POSTs /complete with snake_case context and passes null currentValue through', async () => {
    const fetchMock = stubFetchWithEnvelope([
      { scope: 'global', name: 'region', value_type: 'string', current_value: null, unavailable_reason: 'no value' },
    ])
    vi.stubGlobal('fetch', fetchMock)
    const items = await createVariableContract().completeVariables('reg', {
      projectId: 1,
      workflowId: 2,
      workflowVersion: 3,
      taskId: 't1',
      attemptNo: 4,
    })
    expect(items).toEqual([
      { scope: 'global', name: 'region', valueType: 'string', currentValue: null, unavailableReason: 'no value' },
    ])
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/variables/complete')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      prefix: 'reg',
      context: { project_id: 1, workflow_id: 2, workflow_version: 3, task_id: 't1', attempt_no: 4 },
    })
  })

  it('checkReference POSTs /check-reference and passes diagnostic enum codes through untouched', async () => {
    const fetchMock = stubFetchWithEnvelope({
      expression: '${bogus.x}',
      valid: false,
      diagnostics: [
        { code: 'SYNTAX', message: '未知作用域' },
        { code: 'CYCLE', message: '循环引用' },
      ],
    })
    vi.stubGlobal('fetch', fetchMock)
    const result = await createVariableContract().checkReference('${bogus.x}', { projectId: 1 })
    expect(result).toEqual({
      expression: '${bogus.x}',
      valid: false,
      diagnostics: [
        { code: 'SYNTAX', message: '未知作用域' },
        { code: 'CYCLE', message: '循环引用' },
      ],
    })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/rebuild/variables/check-reference')
    expect(JSON.parse(init.body as string)).toEqual({ expression: '${bogus.x}', context: { project_id: 1 } })
  })

  it('previewResolution POSTs /preview and maps resolved_value with null passthrough', async () => {
    const fetchMock = stubFetchWithEnvelope({
      expression: '${global.region}',
      resolved_value: null,
      diagnostics: [{ code: 'UNDEFINED', message: '变量未定义' }],
    })
    vi.stubGlobal('fetch', fetchMock)
    const preview = await createVariableContract().previewResolution('${global.region}', { projectId: 1 })
    expect(preview).toEqual({
      expression: '${global.region}',
      resolvedValue: null,
      diagnostics: [{ code: 'UNDEFINED', message: '变量未定义' }],
    })
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/v1/rebuild/variables/preview')
  })

  it('getRunSnapshot GETs /run-snapshot with instance_id and attempt_no and maps the snapshot row', async () => {
    const fetchMock = stubFetchWithEnvelope([
      {
        expression: '${global.region}',
        scope: 'global',
        name: 'region',
        resolved_value: 'cn-east',
        value_type: 'string',
        source: 'global.region',
        resolved_at: '2026-10-17 10:00:00',
        attempt_no: 2,
      },
    ])
    vi.stubGlobal('fetch', fetchMock)
    const rows = await createVariableContract().getRunSnapshot(9, 5, 2)
    expect(rows).toEqual([
      {
        expression: '${global.region}',
        scope: 'global',
        name: 'region',
        resolvedValue: 'cn-east',
        valueType: 'string',
        source: 'global.region',
        resolvedAt: '2026-10-17 10:00:00',
        attemptNo: 2,
      },
    ])
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/v1/rebuild/variables/run-snapshot?instance_id=9&project_id=5&attempt_no=2')
  })

  it('getRunSnapshot omits attempt_no from the query when not provided', async () => {
    const fetchMock = stubFetchWithEnvelope([])
    vi.stubGlobal('fetch', fetchMock)
    await expect(createVariableContract().getRunSnapshot(9, 5)).resolves.toEqual([])
    const [url] = fetchMock.mock.calls[0] as unknown as [string]
    expect(url).toBe('/api/v1/rebuild/variables/run-snapshot?instance_id=9&project_id=5')
  })

  it('non-2xx maps to ContractApiError with httpStatus preserved', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 500 })))
    await expect(createVariableContract().listVariables(1)).rejects.toMatchObject({
      httpStatus: 500,
      name: 'ContractApiError',
    })
  })

  it('envelope business error (code !== 0) maps to ContractApiError with the backend code', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 4001, msg: '变量不存在', data: null }), { status: 200 })),
    )
    await expect(createVariableContract().listVariables(1)).rejects.toMatchObject({
      httpStatus: 200,
      code: 4001,
      name: 'ContractApiError',
    })
  })

  it('aborted fetch normalizes to a TIMEOUT ContractApiError', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))
    await expect(createVariableContract().listVariables(1)).rejects.toMatchObject({
      httpStatus: 0,
      code: 'TIMEOUT',
      name: 'ContractApiError',
    })
  })
})
