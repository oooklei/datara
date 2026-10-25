<script setup lang="ts">
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createDependencyContract } from '../services/rebuild/dependencyApi'

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
const selector = computed(() => String(props.modelValue.dependent_execute ?? 'workflow'))

function value(key: string, fallback: string | number = ''): string | number {
  return props.modelValue[key] as string | number ?? fallback
}

function update(key: string, next: unknown) {
  saved.value = false
  emit('update:modelValue', { ...props.modelValue, [key]: next })
}

async function save() {
  const upstreamWorkflowId = Number(props.modelValue.upstream_workflow_id)
  if (!Number.isInteger(upstreamWorkflowId) || upstreamWorkflowId <= 0) {
    ElMessage.warning('请先填写有效的上游工作流 ID')
    return
  }

  const selectedScope = selector.value as 'workflow' | 'all_tasks' | 'task'
  const taskCode = selectedScope === 'workflow' ? '0' : selectedScope === 'all_tasks' ? '-1' : String(props.modelValue.upstream_task_code ?? '')
  if (selectedScope === 'task' && (!/^\d+$/.test(taskCode) || Number(taskCode) <= 0)) {
    ElMessage.warning('指定任务依赖需要填写正整数任务编码')
    return
  }

  saving.value = true
  saved.value = false
  try {
    const failurePolicy = String(props.modelValue.failure_policy ?? 'fail') === 'waiting' ? 'waiting' : 'fail'
    const result = await createDependencyContract().saveDependency({
      projectId: props.projectId,
      workflowId: props.workflowId,
      workflowVersion: props.workflowVersion ?? 1,
      taskId: props.taskId,
      groupRelation: String(props.modelValue.group_relation ?? 'AND') === 'OR' ? 'OR' : 'AND',
      checkIntervalSeconds: Number(props.modelValue.check_interval_seconds ?? 10),
      failurePolicy,
      ...(failurePolicy === 'waiting' ? { failureWaitingSeconds: Number(props.modelValue.failure_waiting_seconds ?? 60) } : {}),
      timeoutSeconds: Number(props.modelValue.timeout_seconds ?? 30),
      groups: [{
        join: String(props.modelValue.relation ?? 'AND') === 'OR' ? 'OR' : 'AND',
        conditions: [{
          kind: selectedScope === 'workflow' ? 'workflow' : 'task',
          selector: selectedScope,
          upstreamWorkflowId,
          upstreamTaskCode: taskCode,
          cycle: String(props.modelValue.cycle ?? 'day') as 'hour' | 'day' | 'week' | 'month',
          dateValue: String(props.modelValue.date_value ?? 'last1Days'),
          dependResult: String(props.modelValue.depend_result ?? 'success') === 'failed' ? 'failed' : 'success',
          parameterPassing: Boolean(props.modelValue.parameter_passing ?? false),
        }],
      }],
    })
    emit('update:modelValue', {
      ...props.modelValue,
      upstream_workflow_id: upstreamWorkflowId,
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
    <label>执行范围<select data-test="dependency-scope" :value="selector" @change="update('dependent_execute', ($event.target as HTMLSelectElement).value)">
      <option value="workflow">整工作流</option><option value="all_tasks">全部任务</option><option value="task">指定任务</option>
    </select></label>
    <label>依赖类型<select :value="value('kind', 'workflow')" disabled title="文件/表状态/外部任务的详细契约尚未冻结"><option value="workflow">工作流/任务</option></select></label>
    <label>上游工作流 ID<input data-test="upstream-workflow" :value="value('upstream_workflow_id')" @input="update('upstream_workflow_id', ($event.target as HTMLInputElement).value)" /></label>
    <small v-if="value('dependency_id')" data-test="dependency-id">已绑定依赖配置 #{{ value('dependency_id') }}</small>
    <label v-if="selector === 'task'">任务编码<input data-test="upstream-task" :value="value('upstream_task_code')" @input="update('upstream_task_code', ($event.target as HTMLInputElement).value)" /></label>
    <label>组内关系<select :value="value('relation', 'AND')" @change="update('relation', ($event.target as HTMLSelectElement).value)"><option>AND</option><option>OR</option></select></label>
    <label>组间关系<select :value="value('group_relation', 'AND')" @change="update('group_relation', ($event.target as HTMLSelectElement).value)"><option>AND</option><option>OR</option></select></label>
    <label>时间周期<select :value="value('cycle', 'day')" @change="update('cycle', ($event.target as HTMLSelectElement).value)"><option value="hour">小时</option><option value="day">天</option><option value="week">周</option><option value="month">月</option></select></label>
    <label>命名窗口<input :value="value('date_value', 'last1Days')" @input="update('date_value', ($event.target as HTMLInputElement).value)" /></label>
    <label>期望结果<select :value="value('depend_result', 'success')" @change="update('depend_result', ($event.target as HTMLSelectElement).value)"><option value="success">成功</option><option value="failed">失败</option></select></label>
    <label>参数透传<input type="checkbox" :checked="Boolean(value('parameter_passing', 0))" @change="update('parameter_passing', ($event.target as HTMLInputElement).checked)" /></label>
    <label>检查周期(秒)<input type="number" min="1" :value="value('check_interval_seconds', 10)" @input="update('check_interval_seconds', Number(($event.target as HTMLInputElement).value))" /></label>
    <label>超时(秒)<input type="number" min="1" :value="value('timeout_seconds', 30)" @input="update('timeout_seconds', Number(($event.target as HTMLInputElement).value))" /></label>
    <label>失败策略<select :value="value('failure_policy', 'fail')" @change="update('failure_policy', ($event.target as HTMLSelectElement).value)"><option value="fail">失败</option><option value="waiting">等待</option></select></label>
    <label v-if="value('failure_policy', 'fail') === 'waiting'">失败等待(秒)<input type="number" min="1" :value="value('failure_waiting_seconds', 60)" @input="update('failure_waiting_seconds', Number(($event.target as HTMLInputElement).value))" /></label>
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
