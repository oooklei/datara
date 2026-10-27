<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createDependencyContract, type DependencyCondition } from '../services/rebuild/dependencyApi'
import VariableReferenceInput from './VariableReferenceInput.vue'

const props = defineProps<{
  projectId: number
  workflowId: number
  workflowVersion?: number
  taskId: string
  modelValue: Record<string, unknown>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: Record<string, unknown>] }>()
const saving = ref(false)
const saved = ref(false)
const variableContext = computed(() => ({
  projectId: props.projectId,
  workflowId: props.workflowId,
  workflowVersion: props.workflowVersion ?? 1,
  taskId: props.taskId,
}))
const selector = computed(() => String(props.modelValue.dependent_execute ?? 'workflow'))
const windowMode = computed(() => String(props.modelValue.window_mode ?? 'named') === 'range' ? 'range' : 'named')
const failureWaitingMinutes = computed(() => {
  const explicit = props.modelValue.failure_waiting_minutes
  if (explicit !== undefined && explicit !== null && explicit !== '') return Number(explicit)
  return Number(props.modelValue.failure_waiting_seconds ?? 60) / 60
})
type DependencyKind = NonNullable<DependencyCondition['kind']>
type DependencyCycle = NonNullable<DependencyCondition['cycle']>
const DATE_VALUES: Record<DependencyCycle, readonly string[]> = {
  hour: ['currentHour', 'last1Hour', 'last2Hours', 'last3Hours', 'last24Hours'],
  day: ['today', 'last1Days', 'last2Days', 'last3Days', 'last7Days'],
  week: ['thisWeek', 'lastWeek', 'lastMonday', 'lastTuesday', 'lastWednesday', 'lastThursday', 'lastFriday', 'lastSaturday', 'lastSunday'],
  month: ['thisMonth', 'thisMonthBegin', 'lastMonth', 'lastMonthBegin', 'lastMonthEnd'],
}
const kind = computed<DependencyKind>(() => {
  const candidate = String(props.modelValue.kind ?? '')
  if (['workflow', 'task', 'file', 'table_state', 'external_task'].includes(candidate)) return candidate as DependencyKind
  return selector.value === 'workflow' ? 'workflow' : 'task'
})
const cycle = computed<DependencyCycle>(() => {
  const candidate = String(props.modelValue.cycle ?? 'day')
  return ['hour', 'day', 'week', 'month'].includes(candidate) ? candidate as DependencyCycle : 'day'
})
const namedDateValues = computed(() => DATE_VALUES[cycle.value])

function value(key: string, fallback: string | number = ''): string | number {
  return props.modelValue[key] as string | number ?? fallback
}

function update(key: string, next: unknown) {
  saved.value = false
  emit('update:modelValue', { ...props.modelValue, [key]: next })
}

function updateCycle(next: DependencyCycle) {
  const currentDateValue = String(props.modelValue.date_value ?? '')
  emit('update:modelValue', {
    ...props.modelValue,
    cycle: next,
    date_value: DATE_VALUES[next].includes(currentDateValue) ? currentDateValue : DATE_VALUES[next][0],
  })
  saved.value = false
}

function updateFailureWaitingMinutes(next: number) {
  saved.value = false
  const value: Record<string, unknown> = { ...props.modelValue, failure_waiting_minutes: next }
  delete value.failure_waiting_seconds
  emit('update:modelValue', value)
}

function updateKind(next: DependencyKind) {
  saved.value = false
  const value: Record<string, unknown> = { ...props.modelValue, kind: next }
  if (next === 'workflow') value.dependent_execute = 'workflow'
  if (next === 'task' && selector.value === 'workflow') value.dependent_execute = 'all_tasks'
  emit('update:modelValue', value)
}

function updateScope(next: 'workflow' | 'all_tasks' | 'task') {
  saved.value = false
  emit('update:modelValue', {
    ...props.modelValue,
    kind: next === 'workflow' ? 'workflow' : 'task',
    dependent_execute: next,
  })
}

async function save() {
  const selectedKind = kind.value
  const condition: DependencyCondition = { kind: selectedKind }
  let upstreamWorkflowId: number | undefined
  if (selectedKind === 'workflow' || selectedKind === 'task') {
    upstreamWorkflowId = Number(props.modelValue.upstream_workflow_id)
    if (!Number.isInteger(upstreamWorkflowId) || upstreamWorkflowId <= 0) {
      ElMessage.warning('请先填写有效的上游工作流 ID')
      return
    }
    const selectedScope = selectedKind === 'workflow'
      ? 'workflow'
      : (selector.value === 'task' ? 'task' : 'all_tasks')
    const taskCode = selectedScope === 'workflow' ? '0' : selectedScope === 'all_tasks' ? '-1' : String(props.modelValue.upstream_task_code ?? '')
    if (selectedScope === 'task' && (!/^\d+$/.test(taskCode) || Number(taskCode) <= 0)) {
      ElMessage.warning('指定任务依赖需要填写正整数任务编码')
      return
    }
    condition.selector = selectedScope
    condition.upstreamWorkflowId = upstreamWorkflowId
    condition.upstreamTaskCode = taskCode
  } else {
    const field = selectedKind === 'file' ? 'file_id' : selectedKind === 'table_state' ? 'table_id' : 'external_key'
    const target = String(props.modelValue[field] ?? '').trim()
    if (!target || target.length > 512) {
      ElMessage.warning('扩展依赖目标标识不能为空且不得超过 512 个字符')
      return
    }
    if (selectedKind === 'file') condition.fileId = target
    else if (selectedKind === 'table_state') condition.tableId = target
    else condition.externalKey = target
  }
  const windowInput = windowMode.value === 'range'
    ? (() => {
        const beginOffset = Number(props.modelValue.begin_offset ?? 0)
        const endOffset = Number(props.modelValue.end_offset ?? 0)
        if (!Number.isInteger(beginOffset) || !Number.isInteger(endOffset) || endOffset < beginOffset) return null
        return {
          dateRange: {
            periodType: String(props.modelValue.period_type ?? 'day') as 'hour' | 'day' | 'week' | 'month',
            beginOffset,
            endOffset,
          },
        }
      })()
    : {
        cycle: String(props.modelValue.cycle ?? 'day') as 'hour' | 'day' | 'week' | 'month',
        dateValue: String(props.modelValue.date_value ?? 'last1Days'),
      }
  if (windowInput === null) {
    ElMessage.warning('相对窗口要求起止偏移为整数，且结束偏移不得早于开始偏移')
    return
  }
  Object.assign(condition, windowInput, {
    dependResult: String(props.modelValue.depend_result ?? 'success') === 'failed' ? 'failed' : 'success',
    parameterPassing: Boolean(props.modelValue.parameter_passing ?? false),
  })

  const checkIntervalSeconds = Number(props.modelValue.check_interval_seconds ?? 10)
  const timeoutSeconds = Number(props.modelValue.timeout_seconds ?? 30)
  if (!Number.isInteger(checkIntervalSeconds) || checkIntervalSeconds <= 0
    || !Number.isInteger(timeoutSeconds) || timeoutSeconds <= 0) {
    ElMessage.warning('检查周期和超时必须是正整数秒')
    return
  }
  const failurePolicy = String(props.modelValue.failure_policy ?? 'fail') === 'waiting' ? 'waiting' : 'fail'
  let failureWaitingSeconds: number | undefined
  if (failurePolicy === 'waiting') {
    const minutes = failureWaitingMinutes.value
    if (!Number.isInteger(minutes) || minutes <= 0) {
      ElMessage.warning('失败等待时长必须是正整数分钟')
      return
    }
    failureWaitingSeconds = minutes * 60
  }

  saving.value = true
  saved.value = false
  try {
    const result = await createDependencyContract().saveDependency({
      projectId: props.projectId,
      workflowId: props.workflowId,
      workflowVersion: props.workflowVersion ?? 1,
      taskId: props.taskId,
      groupRelation: String(props.modelValue.group_relation ?? 'AND') === 'OR' ? 'OR' : 'AND',
      checkIntervalSeconds,
      failurePolicy,
      ...(failureWaitingSeconds !== undefined ? { failureWaitingSeconds } : {}),
      timeoutSeconds,
      groups: [{
        join: String(props.modelValue.relation ?? 'AND') === 'OR' ? 'OR' : 'AND',
        conditions: [condition],
      }],
    })
    emit('update:modelValue', {
      ...props.modelValue,
      ...(upstreamWorkflowId !== undefined ? { upstream_workflow_id: upstreamWorkflowId } : {}),
      dependency_id: result.configId,
    })
    saved.value = true
    ElMessage.success('依赖配置已保存')
  } catch (error) {
    ElMessage.error(`依赖配置保存失败：${error instanceof Error ? error.message : '请求异常'}`)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <section class="dependency-editor" data-dependent-editor>
    <strong>依赖组件参数 · {{ taskId }}</strong>
    <label>依赖类型<select data-test="dependency-kind" :value="kind" @change="updateKind(($event.target as HTMLSelectElement).value as DependencyKind)">
      <option value="workflow">工作流</option><option value="task">任务</option><option value="file">文件</option><option value="table_state">表状态</option><option value="external_task">外部任务</option>
    </select></label>
    <label v-if="kind === 'workflow' || kind === 'task'">执行范围<select data-test="dependency-scope" :value="selector" @change="updateScope(($event.target as HTMLSelectElement).value as 'workflow' | 'all_tasks' | 'task')">
      <option value="workflow">整工作流</option><option value="all_tasks">全部任务</option><option value="task">指定任务</option>
    </select></label>
    <label v-if="kind === 'workflow' || kind === 'task'">上游工作流 ID<input data-test="upstream-workflow" type="number" min="1" step="1" :value="value('upstream_workflow_id')" @input="update('upstream_workflow_id', ($event.target as HTMLInputElement).value)" /></label>
    <VariableReferenceInput v-else-if="kind === 'file'" data-test="dependency-target" data-variable-field="dependency-target" :model-value="String(value('file_id'))" :context="variableContext" label="文件标识" @update:model-value="update('file_id', $event)" />
    <VariableReferenceInput v-else-if="kind === 'table_state'" data-test="dependency-target" data-variable-field="dependency-target" :model-value="String(value('table_id'))" :context="variableContext" label="表状态标识" @update:model-value="update('table_id', $event)" />
    <VariableReferenceInput v-else data-test="dependency-target" data-variable-field="dependency-target" :model-value="String(value('external_key'))" :context="variableContext" label="外部任务标识" @update:model-value="update('external_key', $event)" />
    <small v-if="value('dependency_id')" data-test="dependency-id">已绑定依赖配置 #{{ value('dependency_id') }}</small>
    <label v-if="kind === 'task' && selector === 'task'">任务编码<input data-test="upstream-task" type="number" min="1" step="1" :value="value('upstream_task_code')" @input="update('upstream_task_code', ($event.target as HTMLInputElement).value)" /></label>
    <label>组内关系<select :value="value('relation', 'AND')" @change="update('relation', ($event.target as HTMLSelectElement).value)"><option>AND</option><option>OR</option></select></label>
    <label>组间关系<select :value="value('group_relation', 'AND')" @change="update('group_relation', ($event.target as HTMLSelectElement).value)"><option>AND</option><option>OR</option></select></label>
    <label>时间窗模式<select data-test="dependency-window-mode" :value="windowMode" @change="update('window_mode', ($event.target as HTMLSelectElement).value)"><option value="named">命名窗口</option><option value="range">相对范围</option></select></label>
    <template v-if="windowMode === 'named'">
      <label>时间周期<select data-test="dependency-cycle" :value="cycle" @change="updateCycle(($event.target as HTMLSelectElement).value as DependencyCycle)"><option value="hour">小时</option><option value="day">天</option><option value="week">周</option><option value="month">月</option></select></label>
      <label>命名窗口<select data-test="dependency-date-value" :value="value('date_value', namedDateValues[0])" @change="update('date_value', ($event.target as HTMLSelectElement).value)"><option v-for="item in namedDateValues" :key="item" :value="item">{{ item }}</option></select></label>
    </template>
    <template v-else>
      <label>范围周期<select :value="value('period_type', 'day')" @change="update('period_type', ($event.target as HTMLSelectElement).value)"><option value="hour">小时</option><option value="day">天</option><option value="week">周</option><option value="month">月</option></select></label>
      <label>开始偏移<input type="number" step="1" :value="value('begin_offset', 0)" @input="update('begin_offset', Number(($event.target as HTMLInputElement).value))" /></label>
      <label>结束偏移<input type="number" step="1" :value="value('end_offset', 0)" @input="update('end_offset', Number(($event.target as HTMLInputElement).value))" /></label>
    </template>
    <label>期望结果<select :value="value('depend_result', 'success')" @change="update('depend_result', ($event.target as HTMLSelectElement).value)"><option value="success">成功</option><option value="failed">失败</option></select></label>
    <label>参数透传<input type="checkbox" :checked="Boolean(value('parameter_passing', 0))" @change="update('parameter_passing', ($event.target as HTMLInputElement).checked)" /></label>
    <label>检查周期(秒)<input type="number" min="1" :value="value('check_interval_seconds', 10)" @input="update('check_interval_seconds', Number(($event.target as HTMLInputElement).value))" /></label>
    <label>超时(秒)<input type="number" min="1" :value="value('timeout_seconds', 30)" @input="update('timeout_seconds', Number(($event.target as HTMLInputElement).value))" /></label>
    <label>失败策略<select :value="value('failure_policy', 'fail')" @change="update('failure_policy', ($event.target as HTMLSelectElement).value)"><option value="fail">失败</option><option value="waiting">等待</option></select></label>
    <label v-if="value('failure_policy', 'fail') === 'waiting'">失败等待(分钟)<input data-test="failure-waiting-minutes" type="number" min="1" step="1" :value="failureWaitingMinutes" @input="updateFailureWaitingMinutes(Number(($event.target as HTMLInputElement).value))" /></label>
    <button type="button" class="wf-btn dependency-save" data-test="save-dependency" :disabled="saving" @click="save">{{ saving ? '保存中…' : saved ? '已保存' : '保存依赖配置' }}</button>
  </section>
</template>

<style scoped>
.dependency-editor { display: grid; grid-template-columns: repeat(3, minmax(130px, 1fr)); align-items: center; gap: 8px; }
.dependency-editor strong { grid-column: 1 / -1; }
.dependency-editor label { display: grid; gap: 4px; font-size: 12px; color: var(--text-secondary, #64748b); }
.dependency-editor input, .dependency-editor select { min-width: 0; min-height: 30px; border: 1px solid var(--border-color, #dbe3ef); border-radius: 4px; padding: 0 8px; color: #1e293b; background: #fff; }
.dependency-save { justify-self: start; }
</style>
