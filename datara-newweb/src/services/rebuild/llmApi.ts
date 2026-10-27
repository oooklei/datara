/**
 * 增量 15.6 / 权威设计 §5E：LLM 模型配置前端契约（六端点）。
 *
 * 唯一后端事实源：`datara-backend/rebuild/llm/api.py` 的 6 个 rebuild llm-models 端点
 * （挂载 `/api/v1/rebuild/llm-models`，见 `rebuild/api/app.py` L1128-1132；路由仅在
 * `LLM_ENCRYPTION_KEY` 注入时挂载）。
 *
 * 凭据纪律（红线 8）：`api_key` 只出现在**写请求体**；任何读取响应只携带后端掩码值
 * （`mask_api_key`：长度 ≤8 全掩码，否则 `"*"*min(8, len-4) + 尾 4 位`）。本层不做解掩码、
 * 不本地重构 key、不在日志/错误消息中回显。
 */

import { deleteJson, getJson, postJson, putJson } from '../http'
import { camelToSnake, snakeToCamel } from './adapterKit'

/** provider 白名单（对齐 `rebuild/llm/api.py` `LlmModelRequest.validate_provider` 与 `ai_copilot/config.py` `SUPPORTED_PROVIDERS`——三方单源）。 */
export const LLM_PROVIDERS = ['siliconflow', 'volcengine', 'longcat'] as const
export type LlmProvider = (typeof LLM_PROVIDERS)[number]

export interface LlmModelDraft {
  name: string
  displayName: string
  provider: LlmProvider
  apiBase: string
  modelId: string
  /** 仅请求方向存在；编辑态留空表示不覆盖既有密文（§5E.1#2）。 */
  apiKey?: string
  maxTokens?: number
  temperature?: number
  isActive?: boolean
  isDefault?: boolean
  sortOrder?: number
}

export interface LlmModelRecord {
  id: number
  name: string
  displayName: string
  provider: LlmProvider
  apiBase: string
  modelId: string
  /** 后端掩码值；禁止在 UI 中解掩码或重构完整 key。 */
  apiKey: string
  maxTokens: number
  temperature: number
  isActive: boolean
  isDefault: boolean
  sortOrder: number
}

export interface LlmListModel {
  items: LlmModelRecord[]
}

/** `POST /{id}/test` 响应（`rebuild/llm/provider.py::test_chat`）。 */
export interface LlmTestResult {
  status: 'success' | 'error'
  message: string
  reply?: string
  detail?: string
  elapsedMs?: number
}

export const LLM_CONTRACT_METHODS = ['list', 'create', 'update', 'remove', 'testModel', 'setDefault'] as const
export type LlmContractMethod = (typeof LLM_CONTRACT_METHODS)[number]

/** 后端稳定错误码（`rebuild/llm/api.py::_error`）；请求统一开启 preserveEnvelopeCode，UI 可按 code 精确分流。 */
export const LLM_ERROR_CODES = {
  invalidToken: 1001,
  permissionDenied: 1003,
  invalidInput: 4001,
  notFound: 4041,
  /** 名称唯一/默认位 IntegrityError（POST/PUT 命中）。 */
  conflict: 4091,
  /** 语义冲突：默认模型禁删（DELETE）、默认模型被停用（PUT）、停用模型被设为默认（PUT /default）。 */
  semanticConflict: 4092,
  /** 连通性测试出站失败。 */
  providerUnavailable: 5021,
} as const

const BASE = '/rebuild/llm-models'
const PRESERVE_ERROR = { preserveEnvelopeCode: true } as const

/** 请求方向 FE→BE：camel → snake（`api_base` / `model_id` / `max_tokens` …）。 */
function toWireDraft(input: LlmModelDraft): Record<string, unknown> {
  return camelToSnake(input) as unknown as Record<string, unknown>
}

/** 响应方向 BE→FE：snake → camel（`elapsed_ms` → `elapsedMs` …）。 */
function fromWire<T>(value: unknown): T {
  return snakeToCamel(value) as T
}

export const llmApi = {
  /** `GET /rebuild/llm-models` —— 分页列表（api_key 掩码回显）。 */
  async list(offset = 0, limit = 50): Promise<LlmListModel> {
    return fromWire<LlmListModel>(await getJson(BASE, { offset, limit }, PRESERVE_ERROR))
  },

  /** `POST /rebuild/llm-models` —— 新增（201；name 冲突 409/4091；api_key 必填 400/4001）。 */
  async create(draft: LlmModelDraft): Promise<LlmModelRecord> {
    return fromWire<LlmModelRecord>(await postJson(BASE, toWireDraft(draft), PRESERVE_ERROR))
  },

  /** `PUT /rebuild/llm-models/{id}` —— 更新（api_key 留空不覆盖既有密文；404/4041）。 */
  async update(id: number, draft: LlmModelDraft): Promise<LlmModelRecord> {
    return fromWire<LlmModelRecord>(await putJson(`${BASE}/${id}`, toWireDraft(draft), PRESERVE_ERROR))
  },

  /** `DELETE /rebuild/llm-models/{id}` —— 删除（默认模型禁删 409/4092；404/4041）。 */
  async remove(id: number): Promise<{ deleted: true; id: number }> {
    return fromWire<{ deleted: true; id: number }>(await deleteJson(`${BASE}/${id}`, PRESERVE_ERROR))
  },

  /** `POST /rebuild/llm-models/{id}/test` —— 连通性测试（无请求体；502/5021 为出站失败）。 */
  async testModel(id: number): Promise<LlmTestResult> {
    return fromWire<LlmTestResult>(await postJson(`${BASE}/${id}/test`, undefined, { ...PRESERVE_ERROR, timeoutMs: null }))
  },

  /** `PUT /rebuild/llm-models/{id}/default` —— 设为默认（无请求体；404/4041）。 */
  async setDefault(id: number): Promise<LlmModelRecord> {
    return fromWire<LlmModelRecord>(await putJson(`${BASE}/${id}/default`, undefined, PRESERVE_ERROR))
  },
}
