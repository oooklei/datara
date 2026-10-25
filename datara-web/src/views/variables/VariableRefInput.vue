<script setup lang="ts">
/**
 * 变量引用输入组件（全局可复用，L5-02 票面产出②；WBS 5.1「变量引用输入组件（全局可复用）」）：
 * - 语法（§5B.2）：${scope.name} 变量引用 + $[时间表达式]；本地即时语法提示（parseVariableReferences 纯前端）；
 * - 引用校验（§5B.3）：全域引用位=校验按钮，POST /check-reference 五诊断码透传展示；
 * - 现时值（§5B.4）：「现值」按钮 POST /preview，label 展示当前时点解析值；
 * - 补全提示（§5B.5）：「引用」按钮 POST /complete 拉候选，SQL IDE 式插入 ${scope.name}。
 */
import { computed, ref } from 'vue'
import {
  createVariableContract,
  parseVariableReferences,
  type ReferenceCheckResult,
  type VariableCompletionItem,
  type VariableContext,
} from '../../services/rebuild/variableApi'

const props = defineProps<{
  modelValue: string
  projectId: number
  /** 可选运行上下文（工作流/任务/尝试），透传 check-reference / preview / complete */
  context?: Partial<VariableContext>
  disabled?: boolean
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const contract = createVariableContract()

/* 本地即时语法提示（零网络） */
const syntaxErrors = computed(() => parseVariableReferences(props.modelValue).syntaxErrors)

/* §5B.3 引用校验 */
const checking = ref(false)
const checkResult = ref<ReferenceCheckResult | null>(null)
const checkError = ref('')

async function onCheck() {
  checkError.value = ''
  checkResult.value = null
  checking.value = true
  try {
    checkResult.value = await contract.checkReference(props.modelValue, { projectId: props.projectId, ...props.context })
  } catch (e) {
    checkError.value = '校验失败：' + (e instanceof Error ? e.message : String(e))
  } finally {
    checking.value = false
  }
}

/* §5B.4 现时值 */
const previewing = ref(false)
const previewLabel = ref('')
const previewError = ref('')

async function onPreview() {
  previewError.value = ''
  previewLabel.value = ''
  previewing.value = true
  try {
    const r = await contract.previewResolution(props.modelValue, { projectId: props.projectId, ...props.context })
    const diag = r.diagnostics?.map((d) => `${d.code}:${d.message}`).join('；') ?? ''
    previewLabel.value = r.resolvedValue !== null ? r.resolvedValue : diag || '（暂不可解析）'
  } catch (e) {
    previewError.value = '解析失败：' + (e instanceof Error ? e.message : String(e))
  } finally {
    previewing.value = false
  }
}

/* §5B.5 补全候选 */
const completionOpen = ref(false)
const completions = ref<VariableCompletionItem[]>([])

async function toggleCompletions() {
  if (completionOpen.value) {
    completionOpen.value = false
    return
  }
  try {
    completions.value = await contract.completeVariables('', { projectId: props.projectId, ...props.context })
    completionOpen.value = true
  } catch {
    completionOpen.value = false
  }
}

/** 插入引用：尾部悬空 ${ 先收回再补全 token */
function insertRef(item: VariableCompletionItem) {
  const base = props.modelValue.endsWith('${') ? props.modelValue.slice(0, -2) : props.modelValue
  emit('update:modelValue', `${base}\${${item.scope}.${item.name}}`)
  completionOpen.value = false
}
</script>

<template>
  <div class="vref" data-testid="vref-root">
    <div class="vref-row">
      <el-input
        :model-value="modelValue"
        :disabled="disabled"
        data-testid="vref-input"
        placeholder="支持 ${scope.name} 变量引用与 $[时间表达式]"
        @update:model-value="emit('update:modelValue', $event)"
      />
      <el-button size="small" :type="completionOpen ? 'primary' : 'default'" data-testid="vref-completions" @click="toggleCompletions">引用</el-button>
      <el-button size="small" :loading="checking" data-testid="vref-check" @click="onCheck">校验</el-button>
      <el-button size="small" :loading="previewing" data-testid="vref-preview" @click="onPreview">现值</el-button>
    </div>
    <div v-if="completionOpen" class="vref-cands" data-testid="vref-candidates">
      <button
        v-for="c in completions"
        :key="c.scope + '.' + c.name"
        type="button"
        class="vref-cand"
        :disabled="!!c.unavailableReason"
        @click="insertRef(c)"
      >
        {{ '${' + c.scope + '.' + c.name + '}' }}<span v-if="c.unavailableReason" class="vref-why">（{{ c.unavailableReason }}）</span>
      </button>
      <span v-if="!completions.length" class="vref-why">无候选变量</span>
    </div>
    <div v-if="checkResult" class="vref-diag" data-testid="vref-diagnostics">
      <el-tag :type="checkResult.valid ? 'success' : 'danger'" size="small">{{ checkResult.valid ? '引用有效' : '引用无效' }}</el-tag>
      <span v-for="(d, i) in checkResult.diagnostics" :key="i" class="vref-diag-item">{{ d.code }}: {{ d.message }}</span>
    </div>
    <div v-if="previewLabel" class="vref-now" data-testid="vref-preview-label">现时值：{{ previewLabel }}</div>
    <div v-if="checkError || previewError" class="vref-err">{{ checkError || previewError }}</div>
    <div v-if="syntaxErrors.length" class="vref-err" data-testid="vref-syntax">本地语法：{{ syntaxErrors.join('、') }}</div>
  </div>
</template>

<style scoped>
.vref-row { display: flex; gap: 8px; align-items: center; }
.vref-row .el-input { flex: 1; }
.vref-cands { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; padding: 6px; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; background: var(--el-fill-color-lighter); }
.vref-cand { border: 1px solid var(--el-border-color); background: #fff; border-radius: 3px; padding: 2px 8px; font-size: 12px; cursor: pointer; color: var(--el-text-color-primary); }
.vref-cand:disabled { cursor: not-allowed; color: var(--el-text-color-placeholder); }
.vref-why { font-size: 12px; color: var(--el-text-color-secondary); }
.vref-diag { margin-top: 6px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.vref-diag-item { font-size: 12px; color: var(--el-color-danger); }
.vref-now { margin-top: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.vref-err { margin-top: 4px; font-size: 12px; color: var(--el-color-danger); }
</style>
