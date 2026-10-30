<script setup lang="ts">
/**
 * 告警与 SLA（§10.10 R6 告警桥接，任务中心 alarm 页签）。
 *
 * 海豚告警组/实例/插件一律不接入：只保留 datara 项目级「告警规则」与
 * 「触发记录」。失败感知由编排网关轮询海豚实例状态完成（后台间隔任务），
 * 本页只做规则配置与触发记录查看。
 *
 * 通道仅站内/邮件/Webhook；短信未接供应商接口，契约不含。
 * 写操作门禁与后端一致：EDIT_DEFINITION（前端仅收敛按钮可见性）。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { authAccount } from '../services/rebuild/authApi'
import { roleHasPermission } from '../services/rebuild/rolePermissions'
import {
  orchestrationApi,
  type AlarmChannel,
  type AlarmRecordRow,
  type AlarmRuleRow,
  type AlarmTrigger,
} from '../services/rebuild/orchestrationApi'

const props = defineProps<{ projectId: number | undefined }>()

const TRIGGER_OPTIONS: { value: AlarmTrigger; label: string }[] = [
  { value: 'failure', label: '实例失败' },
  { value: 'timeout', label: '运行超时' },
]
const CHANNEL_OPTIONS: { value: AlarmChannel; label: string }[] = [
  { value: 'system', label: '站内' },
  { value: 'email', label: '邮件' },
  { value: 'webhook', label: 'Webhook' },
]

const rules = ref<AlarmRuleRow[]>([])
const records = ref<AlarmRecordRow[]>([])
const loading = ref(false)
const error = ref('')
const saving = ref(false)
/** 列表请求代际：项目切换竞态时丢弃迟到响应。 */
let generation = 0

const canManage = computed(() => {
  const role = authAccount.value?.role
  return !!role && roleHasPermission(role, 'edit_definition')
})

const draft = ref<{
  workflowDefinitionCode: number
  trigger: AlarmTrigger
  channel: AlarmChannel
  timeoutMinutes: number | null
  enabled: boolean
}>({
  workflowDefinitionCode: 0,
  trigger: 'failure',
  channel: 'system',
  timeoutMinutes: null,
  enabled: true,
})

async function load() {
  const current = ++generation
  if (props.projectId === undefined) {
    rules.value = []
    records.value = []
    error.value = ''
    loading.value = false
    return
  }
  loading.value = true
  try {
    const [ruleRows, recordRows] = await Promise.all([
      orchestrationApi.listAlarmRules(props.projectId),
      orchestrationApi.listAlarmRecords(props.projectId),
    ])
    if (current !== generation) return
    rules.value = ruleRows
    records.value = recordRows
    error.value = ''
  } catch (reason) {
    if (current !== generation) return
    rules.value = []
    records.value = []
    error.value = reason instanceof Error ? reason.message : '告警配置加载失败'
  } finally {
    if (current === generation) loading.value = false
  }
}

async function submit() {
  const pid = props.projectId
  if (pid === undefined) return
  const isTimeout = draft.value.trigger === 'timeout'
  if (isTimeout && !draft.value.timeoutMinutes) {
    ElMessage.warning('运行超时告警需填写超时分钟数')
    return
  }
  saving.value = true
  try {
    await orchestrationApi.createAlarmRule({
      projectId: pid,
      workflowDefinitionCode: draft.value.workflowDefinitionCode || 0,
      trigger: draft.value.trigger,
      channel: draft.value.channel,
      timeoutMinutes: isTimeout ? draft.value.timeoutMinutes : null,
      enabled: draft.value.enabled,
    })
    ElMessage.success('告警规则已创建')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '告警规则创建失败')
  } finally {
    saving.value = false
  }
}

async function toggleEnabled(row: AlarmRuleRow) {
  try {
    await orchestrationApi.updateAlarmRule(row.id, { enabled: !row.enabled })
    ElMessage.success(row.enabled ? '告警规则已停用' : '告警规则已启用')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '告警规则更新失败')
  }
}

async function remove(row: AlarmRuleRow) {
  try {
    await ElMessageBox.confirm(`确认删除告警规则「${triggerLabel(row.trigger)}」？`, '删除确认', {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await orchestrationApi.deleteAlarmRule(row.id)
    ElMessage.success('告警规则已删除')
    await load()
  } catch (reason) {
    ElMessage.error(reason instanceof Error ? reason.message : '告警规则删除失败')
  }
}

function triggerLabel(value: AlarmTrigger): string {
  return TRIGGER_OPTIONS.find((t) => t.value === value)?.label ?? value
}
function channelLabel(value: AlarmChannel): string {
  return CHANNEL_OPTIONS.find((c) => c.value === value)?.label ?? value
}
function stateLabel(value: string): string {
  return value === 'sent' ? '已发送' : value === 'fail' ? '发送失败' : '待发送'
}
function scopeLabel(row: AlarmRuleRow): string {
  return row.workflowDefinitionCode === 0 ? '全部工作流' : `#${row.workflowDefinitionCode}`
}

watch(
  () => props.projectId,
  () => void load(),
)
onMounted(() => void load())
</script>

<template>
  <section class="tc-alarm" data-tc-alarm>
    <header>
      <h3>告警规则</h3>
      <button :disabled="loading || projectId === undefined" data-alarm-refresh @click="load">刷新</button>
    </header>
    <p v-if="projectId === undefined">请先选择项目以配置告警</p>
    <p v-else-if="loading">加载中…</p>
    <p v-else-if="error" role="alert" data-alarm-error>{{ error }}</p>
    <template v-else>
      <form v-if="canManage" class="tc-alarm-form" data-alarm-create @submit.prevent="submit">
        <label>范围
          <input
            v-model.number="draft.workflowDefinitionCode"
            type="number"
            min="0"
            step="1"
            data-alarm-workflow
            title="0 = 全部工作流"
          />
        </label>
        <label>触发
          <select v-model="draft.trigger" data-alarm-trigger>
            <option v-for="opt in TRIGGER_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
        <label v-if="draft.trigger === 'timeout'">超时(分钟)
          <input v-model.number="draft.timeoutMinutes" type="number" min="1" step="1" data-alarm-timeout />
        </label>
        <label>通道
          <select v-model="draft.channel" data-alarm-channel>
            <option v-for="opt in CHANNEL_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </label>
        <label class="tc-alarm-enabled"><input v-model="draft.enabled" type="checkbox" data-alarm-enabled /> 启用</label>
        <button type="submit" :disabled="saving" data-alarm-submit>新增规则</button>
      </form>
      <p v-else class="tc-alarm-readonly" data-alarm-readonly>当前角色仅可查看告警配置</p>

      <p v-if="!rules.length" data-alarm-rule-empty>暂无告警规则。</p>
      <table v-else data-alarm-rule-table>
        <thead>
          <tr><th>范围</th><th>触发</th><th>超时</th><th>通道</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in rules" :key="row.id" :data-alarm-rule-row="row.id">
            <td>{{ scopeLabel(row) }}</td>
            <td>{{ triggerLabel(row.trigger) }}</td>
            <td>{{ row.trigger === 'timeout' ? `${row.timeoutMinutes ?? '—'} 分钟` : '—' }}</td>
            <td>{{ channelLabel(row.channel) }}</td>
            <td>{{ row.enabled ? '已启用' : '已停用' }}</td>
            <td v-if="canManage">
              <button data-alarm-toggle @click="toggleEnabled(row)">{{ row.enabled ? '停用' : '启用' }}</button>
              <button data-alarm-delete @click="remove(row)">删除</button>
            </td>
            <td v-else>—</td>
          </tr>
        </tbody>
      </table>

      <h3 class="tc-alarm-records-title">触发记录</h3>
      <p v-if="!records.length" data-alarm-record-empty>暂无触发记录。</p>
      <table v-else data-alarm-record-table>
        <thead>
          <tr><th>时间</th><th>实例</th><th>触发</th><th>通道</th><th>状态</th><th>标题</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in records" :key="row.id" :data-alarm-record-row="row.id">
            <td>{{ row.createTime }}</td>
            <td>#{{ row.instanceId }}</td>
            <td>{{ triggerLabel(row.trigger) }}</td>
            <td>{{ channelLabel(row.channel) }}</td>
            <td>{{ stateLabel(row.state) }}</td>
            <td>{{ row.title }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </section>
</template>

<style scoped>
.tc-alarm { padding: 18px; overflow: auto; }
header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h3 { margin: 0 0 12px; }
.tc-alarm-records-title { margin-top: 22px; }
.tc-alarm-form { display: flex; flex-wrap: wrap; align-items: flex-end; gap: 12px; margin-bottom: 14px; }
.tc-alarm-form label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; }
.tc-alarm-form .tc-alarm-enabled { flex-direction: row; align-items: center; }
.tc-alarm-form input[type='number'] { width: 96px; }
.tc-alarm-readonly { font-size: 13px; color: var(--text-secondary, var(--text-2)); }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 9px; border-bottom: 1px solid #dce3eb; text-align: left; }
td:last-child { white-space: nowrap; }
button { margin-right: 8px; cursor: pointer; }
</style>
