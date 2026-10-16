<!--
  R2：统一变量体系验证页（RED/原型态）。
  权威范围：docs/increments/2026-10-14-datara-platform-rebuild-design.md §5（设计真源）
  + 纠偏设计 §2.2（编辑变量可搜索补全；引用校验/作用域可见性/现值/来源展示；
  保存草稿与运行前一致校验；运行实例保存不可变解析快照）。
  边界：独立验证页，不进正式菜单；服务端契约全部经 services/rebuild/variableApi
  （后端接入前抛 R2_VARIABLE_NOT_WIRED，UI 统一状态栏提示）；引用语法解析为本地纯前端逻辑。
-->
<template>
  <div class="r2-var-page">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      data-testid="r2-variable-red-banner"
      title="R2 VARIABLE RED 骨架（原型态）— rebuild/variables 后端契约未接入，所有服务端 I/O 返回 R2_VARIABLE_NOT_WIRED"
    />

    <el-descriptions :column="3" size="small" border class="r2-var-context">
      <el-descriptions-item label="优先级链（设计真源）">{{ priorityChain }}</el-descriptions-item>
      <el-descriptions-item label="语法">$\{scope.name\}（global/project/workflow/task/env/run/tmp）+ $[时间表达式]</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（全部未接线）</el-descriptions-item>
    </el-descriptions>

    <!-- ① 变量清单 / 编辑 -->
    <div class="r2-var-panel">
      <div class="r2-var-panel-head"><span>① 变量定义（清单/编辑/保存走未接线契约）</span></div>
      <el-form inline size="small" class="r2-var-form">
        <el-form-item label="项目ID"><el-input v-model.number="form.projectId" style="width: 90px" /></el-form-item>
        <el-form-item label="作用域">
          <el-select v-model="form.scope" style="width: 110px">
            <el-option v-for="s in allScopes" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="变量名"><el-input v-model="form.name" style="width: 130px" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.valueType" style="width: 100px">
            <el-option label="string" value="string" />
            <el-option label="number" value="number" />
            <el-option label="boolean" value="boolean" />
            <el-option label="json" value="json" />
          </el-select>
        </el-form-item>
        <el-form-item label="值"><el-input v-model="form.value" style="width: 160px" /></el-form-item>
        <el-form-item>
          <el-checkbox v-model="form.sensitive">敏感</el-checkbox>
        </el-form-item>
      </el-form>
      <el-form inline size="small" class="r2-var-form">
        <el-form-item>
          <el-button size="small" data-testid="r2-variable-list" @click="onList">加载清单</el-button>
          <el-button size="small" type="primary" data-testid="r2-variable-save" @click="onSave">保存变量</el-button>
        </el-form-item>
      </el-form>
      <el-table
        :data="definitions"
        size="small"
        border
        max-height="200"
        empty-text="（未接线 — listVariables 后端接入前恒为空）"
        data-testid="r2-variable-definitions"
      >
        <el-table-column prop="scope" label="作用域" width="100" />
        <el-table-column prop="name" label="变量名" width="150" />
        <el-table-column prop="valueType" label="类型" width="90" />
        <el-table-column prop="value" label="值" show-overflow-tooltip />
        <el-table-column label="敏感" width="70">
          <template #default="{ row }">{{ row.sensitive ? '是' : '否' }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ② 引用校验 / 补全 / 现值预览 -->
    <div class="r2-var-panel">
      <div class="r2-var-panel-head"><span>② 引用校验 / 补全 / 现值预览（语法解析本地真实；语义校验走服务端）</span></div>
      <el-input
        v-model="referenceText"
        type="textarea"
        :rows="3"
        data-testid="r2-variable-input"
        placeholder="示例：SELECT * FROM t WHERE dt = $[yyyy-MM-dd] AND region = ${global.region}"
        class="r2-var-input"
      />
      <el-form inline size="small" class="r2-var-form">
        <el-form-item>
          <el-button size="small" data-testid="r2-variable-parse" @click="onParse">本地语法解析</el-button>
          <el-button size="small" type="primary" data-testid="r2-variable-check" @click="onCheck">服务端引用校验</el-button>
          <el-button size="small" data-testid="r2-variable-preview" @click="onPreview">现值预览</el-button>
        </el-form-item>
        <el-form-item label="补全前缀"><el-input v-model="completionPrefix" style="width: 130px" /></el-form-item>
        <el-form-item>
          <el-button size="small" data-testid="r2-variable-complete" @click="onComplete">搜索补全</el-button>
        </el-form-item>
      </el-form>
      <div v-if="parseResult" class="r2-var-parse" data-testid="r2-variable-parse-result">
        <el-table
          v-if="parseResult.refs.length"
          :data="parseResult.refs"
          size="small"
          border
          max-height="160"
          data-testid="r2-variable-refs-table"
        >
          <el-table-column prop="scope" label="作用域" width="110" />
          <el-table-column prop="name" label="变量名" width="170" />
          <el-table-column label="链位" width="120">
            <template #default="{ row }">{{ chainRank(row.scope) }}</template>
          </el-table-column>
          <el-table-column label="完整引用">
            <template #default="{ row }">${{ row.scope }}.{{ row.name }}</template>
          </el-table-column>
        </el-table>
        <div v-else>引用：（无）</div>
        <div>时间表达式：{{ parseResult.timeExpressions.join('、') || '（无）' }}</div>
        <div v-if="parseResult.syntaxErrors.length" class="r2-var-err" data-testid="r2-variable-syntax-errors">
          语法错误：{{ parseResult.syntaxErrors.join('、') }}
        </div>
        <div v-else>语法错误：（无）</div>
      </div>
      <div v-if="checkResult" class="r2-var-result" data-testid="r2-variable-check-result">
        <div>
          校验结论：
          <el-tag :type="checkResult.valid ? 'success' : 'danger'" size="small">{{ checkResult.valid ? 'VALID' : 'INVALID' }}</el-tag>
        </div>
        <div v-for="(d, i) in checkResult.diagnostics" :key="i" class="r2-var-err">[{{ d.code }}] {{ d.message }}</div>
      </div>
      <div v-if="previewResult" class="r2-var-result" data-testid="r2-variable-preview-result">
        <div>现时解析值：{{ previewResult.resolvedValue ?? '（不可用 — 见诊断）' }}</div>
        <div v-if="previewResult.source">来源：{{ previewResult.source.scope }}.{{ previewResult.source.name }}</div>
        <div v-for="(d, i) in previewResult.diagnostics" :key="i" class="r2-var-err">[{{ d.code }}] {{ d.message }}</div>
      </div>
      <el-table
        :data="completionItems"
        size="small"
        border
        max-height="180"
        empty-text="（未接线 — completeVariables 后端接入前恒为空）"
        data-testid="r2-variable-completions"
      >
        <el-table-column prop="scope" label="作用域" width="110" />
        <el-table-column prop="name" label="变量名" width="170" />
        <el-table-column prop="valueType" label="类型" width="90" />
        <el-table-column label="现值">
          <template #default="{ row }">{{ row.currentValue ?? row.unavailableReason ?? '—' }}</template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ③ 运行快照 -->
    <div class="r2-var-panel">
      <div class="r2-var-panel-head"><span>③ 运行快照（task_instance_variable_runtime，不可变）</span></div>
      <el-form inline size="small" class="r2-var-form">
        <el-form-item label="实例ID"><el-input v-model.number="snapshot.instanceId" style="width: 100px" /></el-form-item>
        <el-form-item label="Attempt"><el-input v-model.number="snapshot.attemptNo" style="width: 80px" /></el-form-item>
        <el-form-item>
          <el-button size="small" data-testid="r2-variable-snapshot" @click="onSnapshot">查询快照</el-button>
        </el-form-item>
      </el-form>
      <el-table
        :data="snapshotEntries"
        size="small"
        border
        max-height="220"
        empty-text="（未接线 — getRunSnapshot 后端接入前恒为空）"
        data-testid="r2-variable-snapshot-table"
      >
        <el-table-column prop="expression" label="表达式" show-overflow-tooltip />
        <el-table-column prop="scope" label="作用域" width="90" />
        <el-table-column prop="name" label="变量名" width="130" />
        <el-table-column prop="resolvedValue" label="解析值" show-overflow-tooltip />
        <el-table-column prop="valueType" label="类型" width="80" />
        <el-table-column prop="source" label="来源" width="110" />
        <el-table-column prop="resolvedAt" label="解析时间" width="160" />
        <el-table-column prop="attemptNo" label="Attempt" width="80" />
      </el-table>
    </div>

    <el-alert type="info" :closable="false" show-icon data-testid="r2-variable-status-bar" :title="statusText" />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import {
  R2_VARIABLE_CONTRACT_METHODS,
  R2_VARIABLE_NOT_WIRED,
  VARIABLE_SCOPE_PRIORITY,
  createVariableContract,
  parseVariableReferences,
  type ParsedReferences,
  type ReferenceCheckResult,
  type ResolutionPreview,
  type VariableCompletionItem,
  type VariableDefinition,
  type VariableScope,
  type VariableSnapshotEntry,
  type VariableValueType,
} from '../../../../services/rebuild/variableApi'

defineOptions({ name: 'VariableValidationView' })

const contract = createVariableContract()
const contractMethodCount = R2_VARIABLE_CONTRACT_METHODS.length
const priorityChain = VARIABLE_SCOPE_PRIORITY.join(' > ')
const allScopes: VariableScope[] = [...VARIABLE_SCOPE_PRIORITY, 'tmp']

const form = reactive({ projectId: 1, scope: 'global' as VariableScope, name: '', valueType: 'string' as VariableValueType, value: '', sensitive: false })
const referenceText = ref('')
const completionPrefix = ref('')
const parseResult = ref<ParsedReferences | null>(null)
const snapshot = reactive({ instanceId: 1, attemptNo: 1 })
const statusText = ref('待操作')

/* R2 深化：消费面结果区（未接线契约恒为空态；本地解析真实运行） */
const definitions = ref<VariableDefinition[]>([])
const completionItems = ref<VariableCompletionItem[]>([])
const checkResult = ref<ReferenceCheckResult | null>(null)
const previewResult = ref<ResolutionPreview | null>(null)
const snapshotEntries = ref<VariableSnapshotEntry[]>([])

/** 实时本地解析（200ms 防抖延迟计算；语义校验仍以服务端 checkReference 为准） */
let parseTimer: ReturnType<typeof setTimeout> | undefined
watch(referenceText, (text) => {
  if (parseTimer !== undefined) clearTimeout(parseTimer)
  parseTimer = setTimeout(() => {
    parseResult.value = parseVariableReferences(text)
  }, 200)
})

/** 作用域在七级优先级链中的位置（tmp 不入链，解析时不参与覆盖） */
function chainRank(scope: string): string {
  const idx = VARIABLE_SCOPE_PRIORITY.indexOf(scope as (typeof VARIABLE_SCOPE_PRIORITY)[number])
  return idx >= 0 ? `#${idx + 1}` : 'tmp（不入链）'
}

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互 */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value =
        err instanceof Error && err.message.startsWith(R2_VARIABLE_NOT_WIRED)
          ? `${label}：后端未接线（${R2_VARIABLE_NOT_WIRED.split(':')[0]}）`
          : `${label} 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

function context() {
  return { projectId: form.projectId }
}

function onList() {
  return guard(async () => {
    definitions.value = await contract.listVariables(form.projectId)
  }, '加载变量清单')
}

function onSave() {
  return guard(
    () => contract.saveVariable(form.projectId, { scope: form.scope, name: form.name, valueType: form.valueType, value: form.value, sensitive: form.sensitive }),
    '保存变量',
  )
}

/** 本地语法解析（真实运行）：仅归类引用/时间表达式/语法错误，语义校验走服务端 */
function onParse() {
  parseResult.value = parseVariableReferences(referenceText.value)
  statusText.value =
    parseResult.value.syntaxErrors.length > 0
      ? `本地语法解析：发现 ${parseResult.value.syntaxErrors.length} 处语法问题`
      : '本地语法解析通过（语义校验以服务端 checkReference 为准）'
}

function onCheck() {
  return guard(async () => {
    checkResult.value = await contract.checkReference(referenceText.value, context())
  }, '引用校验')
}

function onPreview() {
  return guard(async () => {
    previewResult.value = await contract.previewResolution(referenceText.value, context())
  }, '现值预览')
}

function onComplete() {
  return guard(async () => {
    completionItems.value = await contract.completeVariables(completionPrefix.value, context())
  }, '搜索补全')
}

function onSnapshot() {
  return guard(async () => {
    snapshotEntries.value = await contract.getRunSnapshot(snapshot.instanceId, snapshot.attemptNo)
  }, '查询运行快照')
}
</script>

<style scoped>
.r2-var-page {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.r2-var-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}

.r2-var-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.r2-var-form {
  margin-bottom: 0;
}

.r2-var-input {
  margin-bottom: 8px;
}

.r2-var-parse {
  font-size: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.r2-var-err {
  color: var(--el-color-danger);
}

.r2-var-result {
  font-size: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>
