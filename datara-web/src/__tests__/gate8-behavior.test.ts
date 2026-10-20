/**
 * FE-20 门 8「试运行和正式运行行为验收通过」— 重试/恢复回归测试（vitest，当前可跑）
 *
 * 覆盖：
 *   - resumeFromNodes API 调用链路（graphApi.ts → http.post → resume-from 端点）
 *   - 包络 {code, msg, data} 解包语义
 *   - ContractApiError 三态（成功 / 业务错误 / 系统错误）
 *
 * 依据：WBS FE-20；后端 tests/test_resume_from_api.py；graphApi.ts L442。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { resumeFromNodes } from '../services/graphApi'

const TOKEN = 'test-token-gate8'

function stubTokenStorage(): void {
  vi.stubGlobal('localStorage', { getItem: () => TOKEN, setItem: vi.fn(), removeItem: vi.fn() })
}

function stubFetchWithEnvelope(data: unknown): ReturnType<typeof vi.fn> {
  return vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 0, msg: 'success', data }), { status: 200 }))
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('FE-20 门 8 — resumeFromNodes API 链路回归', () => {
  it('POSTs to the resume-from endpoint with fromNodeIds and priority', async () => {
    stubTokenStorage()
    const fetchMock = stubFetchWithEnvelope({ commandId: 42 })
    vi.stubGlobal('fetch', fetchMock)

    const result = await resumeFromNodes('wf-1', 'run-1', ['n2', 'n1'], 3)

    expect(result).toEqual({ commandId: 42 })
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/v1/workflow-definitions/wf-1/runs/run-1/resume-from')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({ fromNodeIds: ['n2', 'n1'], priority: 3 })
    expect((init.headers as Record<string, string>).token).toBe(TOKEN)
  })

  it('defaults priority to 3 when not provided', async () => {
    stubTokenStorage()
    const fetchMock = stubFetchWithEnvelope({ commandId: 7 })
    vi.stubGlobal('fetch', fetchMock)

    await resumeFromNodes('wf-1', 'run-1', ['n1'])

    const [, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({ fromNodeIds: ['n1'], priority: 3 })
  })

  it('maps envelope business error (code !== 0) to Error with code and msg', async () => {
    stubTokenStorage()
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ code: 4004, msg: '实例不存在', data: null }), { status: 200 }),
      ),
    )

    await expect(resumeFromNodes('wf-1', 'run-x', ['n1'])).rejects.toMatchObject({
      code: 4004,
      message: '实例不存在',
    })
  })

  it('maps non-JSON response to Error with status info', async () => {
    stubTokenStorage()
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('boom', { status: 500 })))

    await expect(resumeFromNodes('wf-1', 'run-1', ['n1'])).rejects.toThrow('响应解析失败')
  })

  it('aborted fetch normalizes to timeout Error', async () => {
    stubTokenStorage()
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new DOMException('aborted', 'AbortError')))

    await expect(resumeFromNodes('wf-1', 'run-1', ['n1'])).rejects.toThrow('请求超时')
  })
})
