<script setup lang="ts">
/**
 * 增量 15.6 / 权威设计 §5E：LLM 模型 新建/编辑 模态表单。
 *
 * 后端事实源：`datara-backend/rebuild/llm/api.py`（`LlmModelRequest` 校验 + 各端点错误分支）：
 *  - `provider` 白名单 {siliconflow, volcengine}（L36）；`api_base` 必须 https://（L43，后端另做 rstrip('/')）
 *  - `name` / `display_name` 1..64；`max_tokens` ≥1（默认 10000）；`temperature` 0..2（默认 0.7）
 *  - `api_key`：新建必填（L79 → 400/4001）；编辑留空 = **不覆盖**既有密文（L98）
 *  - 默认模型不可停用（L100 → 409/4092）；停用模型不可设为默认（repository L45 → 409/4092）
 * 壳范式锚：沿 ScheduleDialog.vue 手工模态（Teleport + 遮罩 + role=dialog），**禁 el-dialog**——
 *  vitest happy-dom 环境未注册 ElementPlus 组件，未解析组件渲染 slot 不受 v-if 控制不可测。
 *
 * 凭据纪律（红线 8）：本组件只把 `api_key` 放进**写请求体**；编辑态输入框**恒预置为空**且
 *  占位文案显式声明「留空不覆盖」——绝不预填后端掩码值（否则保存会把掩码串写回密文位）。
 *  响应方向的 `record.apiKey` 仅作列表回显，本组件不解掩码、不重构完整 key。
 */
import { computed, reactive, ref, watch } from 'vue'
import {
  LLM_PROVIDERS,
  llmApi,
  type LlmModelDraft,
  type LlmModelRecord,
  type LlmProvider,
} from '../../../services/rebuild/llmApi'

const props = defineProps<{ modelValue: boolean; record: LlmModelRecord | null }>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'saved'): void
}>()

const PROVIDER_LABELS: Record<LlmProvider, string> = {
  siliconflow: '硅基流动 SiliconFlow',
  volcengine: '火山引擎 Volcengine',
}

interface LlmFormState {
  name: string
  displayName: string
  provider: LlmProvider
  apiBase: string
  modelId: string
  apiKey: string
  maxTokens: number | null
  temperature: number | null
  isActive: boolean
  isDefault: boolean
  sortOrder: number | null
}

/** 新建默认值全集 = 后端 `LlmModelRequest` 默认（max 10000 / temp 0.7 / active / sort 0）。 */
function emptyForm(): LlmFormState {
  return {
    name: '',
    displayName: '',
    provider: 'siliconflow',
    apiBase: '',
    modelId: '',
    apiKey: '',
    maxTokens: 10000,
    temperature: 0.7,
    isActive: true,
    isDefault: false,
    sortOrder: 0,
  }
}

/**
 * 编辑态：`apiKey` **恒为空串**（掩码值不可回写）。后端掩码口径为「≤8 全掩码，否则尾 4 位可见」，
 * 预填掩码会让保存动作把 `********1234` 覆写进密文列——故此处显式丢弃 `record.apiKey`。
 */
function fromRecord(record: LlmModelRecord): LlmFormState {
  return {
    name: record.name,
    displayName: record.displayName,
    provider: record.provider,
    apiBase: record.apiBase,
    modelId: record.modelId,
    apiKey: '',
    maxTokens: record.maxTokens,
    temperature: record.temperature,
    isActive: record.isActive,
    isDefault: record.isDefault,
    sortOrder: record.sortOrder,
  }
}

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const form = reactive<LlmFormState>(emptyForm())
const submitting = ref(false)
const formError = ref('')

const isEdit = computed(() => props.record !== null)
const title = computed(() => (isEdit.value ? '编辑 LLM 模型' : '新建 LLM 模型'))

watch(
  () => [props.modelValue, props.record] as const,
  () => {
    formError.value = ''
    Object.assign(form, props.record ? fromRecord(props.record) : emptyForm())
  },
  { immediate: true },
)

function close(): void {
  if (submitting.value) return
  visible.value = false
}

/** 门链顺序镜像后端 `LlmModelRequest`：必填/长度 → provider 白名单 → https → 数值域 → 语义门。 */
function validate(): string {
  const name = form.name.trim()
  const displayName = form.displayName.trim()
  const apiBase = form.apiBase.trim()
  const modelId = form.modelId.trim()

  if (!name) return '请填写模型标识 name'
  if (name.length > 64) return 'name 长度不得超过 64'
  if (!displayName) return '请填写显示名称'
  if (displayName.length > 64) return '显示名称长度不得超过 64'
  if (!(LLM_PROVIDERS as readonly string[]).includes(form.provider)) return 'provider 不在支持范围内'
  if (!apiBase) return '请填写 api_base'
  if (!apiBase.startsWith('https://')) return 'api_base 必须使用 HTTPS'
  if (!modelId) return '请填写 model_id'

  const maxTokens = Number(form.maxTokens)
  if (form.maxTokens === null || !Number.isInteger(maxTokens) || maxTokens < 1) {
    return 'max_tokens 需为不小于 1 的整数'
  }
  const temperature = Number(form.temperature)
  if (form.temperature === null || !Number.isFinite(temperature) || temperature < 0 || temperature > 2) {
    return 'temperature 需在 0..2 之间'
  }
  if (form.sortOrder !== null && (!Number.isInteger(Number(form.sortOrder)) || Number(form.sortOrder) < 0)) {
    return 'sort_order 需为不小于 0 的整数'
  }
  if (!isEdit.value && !form.apiKey.trim()) return '新建模型必须填写 api_key'
  // 语义门（后端 409/4092）：默认模型必须处于启用态——前端先断，避免无谓往返。
  if (form.isDefault && !form.isActive) return '默认模型不可处于停用态'
  return ''
}

async function submit(): Promise<void> {
  if (submitting.value) return
  const message = validate()
  if (message) {
    formError.value = message
    return
  }
  submitting.value = true
  formError.value = ''
  try {
    const draft: LlmModelDraft = {
      name: form.name.trim(),
      displayName: form.displayName.trim(),
      provider: form.provider,
      apiBase: form.apiBase.trim(),
      modelId: form.modelId.trim(),
      // 编辑态留空 = 不覆盖既有密文（api.py L98）
      apiKey: form.apiKey.trim() || undefined,
      maxTokens: Number(form.maxTokens),
      temperature: Number(form.temperature),
      isActive: form.isActive,
      isDefault: form.isDefault,
      sortOrder: Number(form.sortOrder ?? 0),
    }
    if (props.record) await llmApi.update(props.record.id, draft)
    else await llmApi.create(draft)
    visible.value = false
    emit('saved')
  } catch (error) {
    // 后端稳定码透传（preserveEnvelopeCode）：4091 名称冲突 / 4092 默认位语义冲突 / 4001 入参
    formError.value = error instanceof Error ? error.message : '保存失败，请稍后重试'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="lm-mask" data-test="llm-form-mask" @click.self="close">
      <section class="lm-panel" role="dialog" aria-modal="true" :aria-label="title" data-test="llm-form-dialog">
        <header class="lm-header">
          <span class="lm-title" data-test="llm-form-title">{{ title }}</span>
          <button type="button" class="lm-close" aria-label="关闭" data-test="llm-form-close" @click="close">×</button>
        </header>

        <form class="lm-form" data-test="llm-form" @submit.prevent="submit">
          <label class="lm-field">
            <span class="lm-label">模型标识 name</span>
            <input v-model="form.name" class="lm-input" data-test="llm-form-name" placeholder="全局唯一，如 silicon-primary" />
          </label>
          <label class="lm-field">
            <span class="lm-label">显示名称</span>
            <input v-model="form.displayName" class="lm-input" data-test="llm-form-display-name" placeholder="如 Silicon 主模型" />
          </label>
          <label class="lm-field">
            <span class="lm-label">provider</span>
            <select v-model="form.provider" class="lm-input" data-test="llm-form-provider">
              <option v-for="opt in LLM_PROVIDERS" :key="opt" :value="opt">{{ PROVIDER_LABELS[opt] }}</option>
            </select>
          </label>
          <label class="lm-field">
            <span class="lm-label">api_base（HTTPS）</span>
            <input
              v-model="form.apiBase"
              class="lm-input"
              data-test="llm-form-api-base"
              placeholder="https://api.siliconflow.cn/v1"
            />
          </label>
          <label class="lm-field">
            <span class="lm-label">model_id</span>
            <input v-model="form.modelId" class="lm-input" data-test="llm-form-model-id" placeholder="deepseek-ai/DeepSeek-V3" />
          </label>
          <label class="lm-field">
            <span class="lm-label">api_key</span>
            <input
              v-model="form.apiKey"
              class="lm-input"
              type="password"
              autocomplete="new-password"
              data-test="llm-form-api-key"
              :placeholder="isEdit ? '留空不覆盖既有凭据' : 'provider 下发的 API Key'"
            />
          </label>
          <label class="lm-field">
            <span class="lm-label">max_tokens（≥1）</span>
            <input v-model.number="form.maxTokens" type="number" min="1" step="1" class="lm-input" data-test="llm-form-max-tokens" />
          </label>
          <label class="lm-field">
            <span class="lm-label">temperature（0..2）</span>
            <input v-model.number="form.temperature" type="number" min="0" max="2" step="0.1" class="lm-input" data-test="llm-form-temperature" />
          </label>
          <label class="lm-field">
            <span class="lm-label">sort_order（≥0）</span>
            <input v-model.number="form.sortOrder" type="number" min="0" step="1" class="lm-input" data-test="llm-form-sort-order" />
          </label>
          <label class="lm-check">
            <input v-model="form.isActive" type="checkbox" data-test="llm-form-is-active" />
            <span>启用</span>
          </label>
          <label class="lm-check">
            <input v-model="form.isDefault" type="checkbox" data-test="llm-form-is-default" />
            <span>设为默认模型</span>
          </label>

          <p v-if="formError" class="lm-error" role="alert" data-test="llm-form-error">{{ formError }}</p>
        </form>

        <footer class="lm-footer">
          <button type="button" class="lm-btn" data-test="llm-form-cancel" :disabled="submitting" @click="close">取消</button>
          <button type="button" class="lm-btn lm-btn--primary" data-test="llm-form-save" :disabled="submitting" @click="submit">
            {{ submitting ? '提交中…' : '保存' }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
/* 设计令牌：由全局 styles/theme.css 的 :root 提供（§4.4.3 风格统一），本文件不再就地重复定义。 */
.lm-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}
.lm-panel {
  width: 720px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 96px);
  background: var(--card);
  border-radius: var(--radius);
  display: flex;
  flex-direction: column;
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.2);
  overflow: hidden;
}
.lm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
}
.lm-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}
.lm-close {
  border: none;
  background: none;
  font-size: 20px;
  line-height: 1;
  color: var(--text-3);
  cursor: pointer;
  padding: 0 4px;
}
.lm-form {
  padding: 16px 20px;
  overflow-y: auto;
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
}
.lm-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.lm-label {
  font-size: 12px;
  color: var(--text-2);
}
.lm-input {
  height: 32px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0 10px;
  font-size: 13px;
  color: var(--text);
  background: var(--card);
  box-sizing: border-box;
}
.lm-input:focus {
  outline: none;
  border-color: var(--primary);
}
.lm-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text);
}
.lm-error {
  grid-column: 1 / -1;
  margin: 0;
  background: var(--danger-bg);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 12px;
  color: var(--danger);
}
.lm-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}
.lm-btn {
  height: 32px;
  padding: 0 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: var(--card);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
}
.lm-btn--primary {
  background: var(--primary);
  border-color: var(--primary);
  color: var(--card);
}
.lm-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
