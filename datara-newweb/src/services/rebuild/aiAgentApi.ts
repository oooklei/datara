import { requestRaw } from '../http'
import { camelToSnake, snakeToCamel } from './adapterKit'

export interface AiToolCall {
  id: string
  type: 'function'
  function: { name: string; arguments: string }
}

export interface AiAgentMessage {
  role: 'user' | 'assistant' | 'tool'
  content: string | null
  toolCalls?: AiToolCall[]
  toolCallId?: string
}

export interface AiAgentTurn {
  message: AiAgentMessage
  model: string
  usage: Record<string, number>
}

export interface AiAgentContract {
  complete: (projectId: number, messages: AiAgentMessage[]) => Promise<AiAgentTurn>
}

export async function completeAgentTurn(projectId: number, messages: AiAgentMessage[]): Promise<AiAgentTurn> {
  const response = await requestRaw<unknown>('/rebuild/ai/chat', {
    method: 'POST',
    timeoutMs: 60_000,
    json: camelToSnake({ projectId, messages }),
  })
  const normalized = snakeToCamel(response) as AiAgentTurn & { code?: string; message?: AiAgentMessage | string }
  if (!normalized || typeof normalized.message !== 'object' || normalized.message?.role !== 'assistant') {
    const detail = typeof normalized?.message === 'string' ? normalized.message : normalized?.code
    throw new Error(detail || 'LLM response is invalid')
  }
  return normalized as AiAgentTurn
}

export function createAiAgentContract(): AiAgentContract {
  return { complete: completeAgentTurn }
}
