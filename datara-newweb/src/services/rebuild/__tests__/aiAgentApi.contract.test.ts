import { afterEach, describe, expect, it, vi } from 'vitest'
import { completeAgentTurn } from '../aiAgentApi'

afterEach(() => vi.unstubAllGlobals())

describe('aiAgentApi', () => {
  it('posts project-scoped conversation and preserves assistant tool calls', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({
      message: {
        role: 'assistant',
        content: null,
        tool_calls: [{ id: 'call-1', type: 'function', function: { name: 'search_schema', arguments: '{"project_id":35}' } }],
      },
      model: 'agent-model',
      usage: { total_tokens: 10 },
    }), { status: 200, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetchMock)

    const response = await completeAgentTurn(35, [{ role: 'user', content: '查订单表' }])

    expect(response.message.toolCalls?.[0].function.name).toBe('search_schema')
    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/api/v1/rebuild/ai/chat')
    expect(JSON.parse(String(init.body))).toEqual({ project_id: 35, messages: [{ role: 'user', content: '查订单表' }] })
  })

  it('surfaces fail-closed LLM configuration errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 'LLM_UNAVAILABLE', message: 'no active default LLM model',
    }), { status: 503, headers: { 'Content-Type': 'application/json' } })))

    await expect(completeAgentTurn(35, [{ role: 'user', content: '检查' }])).rejects.toThrow('no active default LLM model')
  })
})
