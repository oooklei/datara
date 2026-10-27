import { describe, expect, it, vi } from 'vitest'

import { ContractApiError } from '../adapterKit'
import {
  LLM_CONTRACT_METHODS,
  LLM_ERROR_CODES,
  LLM_PROVIDERS,
  llmApi,
  type LlmModelDraft,
  type LlmModelRecord,
} from '../llmApi'

type RecordedCall = { url: string; init?: RequestInit }

/** 后端掩码口径（`rebuild/llm/crypto.py::mask_api_key`）：≤8 全掩码，否则 `"*"*min(8,len-4) + 尾4位`。 */
const PLACEHOLDER_KEY = 'sk-datara-placeholder-key-1234'
const MASKED_KEY = '********' + PLACEHOLDER_KEY.slice(-4)

const draft: LlmModelDraft = {
  name: 'silicon-primary',
  displayName: 'Silicon 主模型',
  provider: 'siliconflow',
  apiBase: 'https://api.siliconflow.cn/v1',
  modelId: 'deepseek-ai/DeepSeek-V3',
  apiKey: PLACEHOLDER_KEY,
  maxTokens: 10000,
  temperature: 0.7,
  isActive: true,
  isDefault: true,
  sortOrder: 0,
}

const recordWire = {
  id: 3,
  name: 'silicon-primary',
  display_name: 'Silicon 主模型',
  provider: 'siliconflow',
  api_base: 'https://api.siliconflow.cn/v1',
  model_id: 'deepseek-ai/DeepSeek-V3',
  api_key: MASKED_KEY,
  max_tokens: 10000,
  temperature: 0.7,
  is_active: true,
  is_default: true,
  sort_order: 0,
}

const testResultWire = {
  status: 'success',
  message: 'LLM connectivity test succeeded',
  reply: 'OK',
  elapsed_ms: 812,
}

function installFetch(dataFor: (url: string, init?: RequestInit) => unknown): RecordedCall[] {
  const calls: RecordedCall[] = []
  globalThis.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, init })
    return new Response(JSON.stringify({ code: 0, msg: 'success', data: dataFor(url, init) }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    })
  }) as typeof fetch
  return calls
}

describe('15.6 rebuild llm-models contract (§5E)', () => {
  it('does not apply the generic 15-second HTTP timeout to an external provider probe', async () => {
    vi.useFakeTimers()
    globalThis.fetch = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((resolve, reject) => {
      init?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
      setTimeout(() => resolve(new Response(JSON.stringify({ code: 0, msg: 'success', data: testResultWire }), { status: 200 })), 20_000)
    })) as typeof fetch
    const probe = llmApi.testModel(3)
    await vi.advanceTimersByTimeAsync(15_100)
    await vi.advanceTimersByTimeAsync(5_000)
    await expect(probe).resolves.toMatchObject({ status: 'success' })
    vi.useRealTimers()
  })

  it('freezes exactly the six §5E methods', () => {
    expect(LLM_CONTRACT_METHODS).toEqual(['list', 'create', 'update', 'remove', 'testModel', 'setDefault'])
    expect(Object.keys(llmApi)).toEqual([...LLM_CONTRACT_METHODS])
    expect(LLM_PROVIDERS).toEqual(['siliconflow', 'volcengine', 'longcat'])
  })

  it('maps the six methods onto the six §5E routes with the contracted verbs', async () => {
    const calls = installFetch((url) => {
      if (url.endsWith('/test')) return testResultWire
      if (url.endsWith('/default')) return recordWire
      if (url.includes('/rebuild/llm-models?')) return { items: [recordWire] }
      if (/\/rebuild\/llm-models\/\d+$/.test(url)) return recordWire
      return recordWire
    })

    await llmApi.list()
    await llmApi.create(draft)
    await llmApi.update(3, { ...draft, apiKey: '' })
    await llmApi.testModel(3)
    await llmApi.setDefault(3)
    await llmApi.remove(3)

    expect(calls.map(({ url, init }) => [url, init?.method])).toEqual([
      ['/api/v1/rebuild/llm-models?offset=0&limit=50', 'GET'],
      ['/api/v1/rebuild/llm-models', 'POST'],
      ['/api/v1/rebuild/llm-models/3', 'PUT'],
      ['/api/v1/rebuild/llm-models/3/test', 'POST'],
      ['/api/v1/rebuild/llm-models/3/default', 'PUT'],
      ['/api/v1/rebuild/llm-models/3', 'DELETE'],
    ])
    // test / default 为无请求体端点（后端签名为空 body）
    expect(calls[3].init?.body).toBeUndefined()
    expect(calls[4].init?.body).toBeUndefined()
    expect(calls.every(({ url }) => !url.startsWith('/api/v1/llm-models'))).toBe(true)
  })

  it('writes snake_case wire fields and never echoes the credential on response records', async () => {
    const calls = installFetch(() => recordWire)

    const created = await llmApi.create(draft)
    const body = JSON.parse(String(calls[0].init?.body))
    expect(body).toEqual({
      name: 'silicon-primary',
      display_name: 'Silicon 主模型',
      provider: 'siliconflow',
      api_base: 'https://api.siliconflow.cn/v1',
      model_id: 'deepseek-ai/DeepSeek-V3',
      api_key: PLACEHOLDER_KEY,
      max_tokens: 10000,
      temperature: 0.7,
      is_active: true,
      is_default: true,
      sort_order: 0,
    })

    // 响应方向：只有掩码值，且键名归 camel；完整 key 不得出现
    expect(created).toEqual({
      id: 3,
      name: 'silicon-primary',
      displayName: 'Silicon 主模型',
      provider: 'siliconflow',
      apiBase: 'https://api.siliconflow.cn/v1',
      modelId: 'deepseek-ai/DeepSeek-V3',
      apiKey: MASKED_KEY,
      maxTokens: 10000,
      temperature: 0.7,
      isActive: true,
      isDefault: true,
      sortOrder: 0,
    } satisfies LlmModelRecord)
    expect(JSON.stringify(created)).not.toContain(PLACEHOLDER_KEY)
    expect(JSON.stringify(created)).not.toContain(PLACEHOLDER_KEY.slice(0, -4))
    expect(Object.keys(created).sort()).toEqual(
      ['id', 'name', 'displayName', 'provider', 'apiBase', 'modelId', 'apiKey', 'maxTokens', 'temperature', 'isActive', 'isDefault', 'sortOrder'].sort(),
    )
  })

  it('maps the connectivity-test payload to FE naming (elapsed_ms → elapsedMs)', async () => {
    installFetch((url) => (url.endsWith('/test') ? testResultWire : recordWire))
    const result = await llmApi.testModel(3)
    expect(result).toEqual({
      status: 'success',
      message: 'LLM connectivity test succeeded',
      reply: 'OK',
      elapsedMs: 812,
    })
    expect('elapsed_ms' in result).toBe(false)
  })

  it('preserves stable backend error codes for UI handling (409 default-model guard / 404 / 502)', async () => {
    // 码位镜像 rebuild/llm/api.py 逐分支：
    //  DELETE 默认模型 → repository.delete 抛 ValueError → 409/4092（非 4091；4091 仅 IntegrityError 兜底）
    //  PUT 停用默认模型 → 409/4092；PUT/POST 名称唯一冲突 → 409/4091
    //  POST /{id}/test 出站失败 → 502/5021
    const cases: Array<{ status: number; code: number; msg: string; call: () => Promise<unknown> }> = [
      { status: 409, code: 4092, msg: 'default model cannot be deleted', call: () => llmApi.remove(3) },
      { status: 409, code: 4092, msg: 'default model cannot be disabled', call: () => llmApi.update(3, { ...draft, isActive: false }) },
      { status: 409, code: 4091, msg: 'model name or default conflicts', call: () => llmApi.create({ ...draft, name: 'dup' }) },
      { status: 404, code: 4041, msg: 'LLM model not found', call: () => llmApi.update(9, draft) },
      { status: 502, code: 5021, msg: 'LLM connectivity failed: HTTPError', call: () => llmApi.testModel(3) },
    ]

    for (const item of cases) {
      globalThis.fetch = vi.fn(async () => new Response(
        JSON.stringify({ code: item.code, msg: item.msg, data: null }),
        { status: item.status, headers: { 'Content-Type': 'application/json' } },
      )) as typeof fetch

      const error = await item.call().catch((caught: unknown) => caught)
      expect(error).toBeInstanceOf(ContractApiError)
      expect(error).toMatchObject({ httpStatus: item.status, code: item.code })
    }

    expect(LLM_ERROR_CODES).toEqual({
      invalidToken: 1001,
      permissionDenied: 1003,
      invalidInput: 4001,
      notFound: 4041,
      conflict: 4091,
      semanticConflict: 4092,
      providerUnavailable: 5021,
    })
  })
})
