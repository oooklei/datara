<!--
  9-03 ScheduleDialog 尾随配置组件（rebuild 域，消费 scheduleCrudApi GREEN 契约）
  壳范式锚：DetailDrawer.vue 手工模态（Teleport+遮罩+role=dialog）——禁 el-dialog：
  vitest happy-dom 环境无 ElementPlus 插件，未解析组件渲染 slot 不受 v-if 控制不可测。
  校验语义镜像 datara-backend/rebuild/scheduling/api.py normalized()：
  crontab 非空→misfire/concurrency 白名单拒绝→maxRunning(<1 拒绝不钳位)→preview；
  priority/failRetryTimes/failRetryInterval 后端钳位，UI 同语义钳位后提交。
  T55 边界（权威设计 §5A.4/§7.2 八门）：本组件可开发、契约可接线；SKIP 语义断言已按 R-05（2026-10-21 裁定，B SCAN_SECONDS 宽限）于 9-05 契约测试落实，融合宣告核验归 9-06（已 PASS 收口）。
-->
<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDraggable } from '../composables/useDraggable'
import {
  createScheduleCrudContract,
  type ScheduleInput,
  type ScheduleMisfirePolicy,
  type ScheduleConcurrencyPolicy,
  type ScheduleRow,
} from '../services/rebuild/scheduleCrudApi'

const props = defineProps<{
  modelValue: boolean
  projectId: number
  wf: number | string
  wfName?: string
}>()

const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const MISFIRE_OPTIONS = ['FIRE_ONCE', 'SKIP', 'FIRE_ALL_LIMITED'] as const
const CONCURRENCY_OPTIONS = ['ALLOW', 'FORBID', 'QUEUE'] as const
const MISFIRE_LABELS: Record<ScheduleMisfirePolicy, string> = {
  FIRE_ONCE: '仅触发一次',
  SKIP: '跳过',
  FIRE_ALL_LIMITED: '全部补跑（限量）',
}
const CONCURRENCY_LABELS: Record<ScheduleConcurrencyPolicy, string> = {
  ALLOW: '允许并行',
  FORBID: '禁止并行',
  QUEUE: '排队等待',
}

/** 响应式契约工厂：projectId 变更时 previewCrontab 携带正确 projectId。 */
const api = computed(() => createScheduleCrudContract(props.projectId))

/* G14 §2.2：弹窗默认可拖动 + 视口钳制 + 位置记忆（把手=标题栏） */
const sdPanelRef = ref<HTMLElement | null>(null)
const sdHeaderRef = ref<HTMLElement | null>(null)
const { dragStyle: sdDragStyle, onHandlePointerdown: onSdDragStart } = useDraggable(sdPanelRef, sdHeaderRef, { storageKey: 'schedule.dialog' })

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

interface ScheduleForm {
  name: string
  crontab: string
  startTime: string
  endTime: string
  priority: number
  workerGroup: string
  failRetryTimes: number
  failRetryInterval: number
  misfirePolicy: ScheduleMisfirePolicy
  concurrencyPolicy: ScheduleConcurrencyPolicy
  maxRunningInstances: number
  timezone: string
}

/** 默认值全集 = 后端 ScheduleBody 默认（priority 3 / retry 0 / interval 60 / FIRE_ONCE / ALLOW / max 1 / Asia/Shanghai）。 */
function emptyForm(): ScheduleForm {
  return {
    name: '',
    crontab: '',
    startTime: '',
    endTime: '',
    priority: 3,
    workerGroup: '',
    failRetryTimes: 0,
    failRetryInterval: 60,
    misfirePolicy: 'FIRE_ONCE',
    concurrencyPolicy: 'ALLOW',
    maxRunningInstances: 1,
    timezone: 'Asia/Shanghai',
  }
}

const rows = ref<ScheduleRow[]>([])
const loading = ref(false)
const editing = ref(false)
const editId = ref<number | null>(null)
const preview = ref<string[] | null>(null)
const previewErr = ref('')
const submitting = ref(false)
const form = reactive<ScheduleForm>(emptyForm())

watch(
  () => [props.modelValue, props.wf, props.projectId] as const,
  () => {
    editing.value = false
    preview.value = null
    previewErr.value = ''
    if (props.modelValue) void reload()
  },
  { immediate: true },
)

function close(): void {
  visible.value = false
}

async function reload(): Promise<void> {
  loading.value = true
  try {
    rows.value = await api.value.listSchedules(props.wf)
  } catch {
    ElMessage.error('定时列表加载失败')
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editId.value = null
  Object.assign(form, emptyForm())
  preview.value = null
  previewErr.value = ''
  editing.value = true
}

function openEdit(row: ScheduleRow): void {
  editId.value = row.id
  form.name = row.name
  form.crontab = row.crontab
  form.startTime = (row.startTime ?? '').slice(0, 19).replace('T', ' ')
  form.endTime = (row.endTime ?? '').slice(0, 19).replace('T', ' ')
  form.priority = row.priority
  form.workerGroup = row.workerGroup ?? ''
  form.failRetryTimes = row.failRetryTimes
  form.failRetryInterval = row.failRetryInterval
  form.misfirePolicy = row.misfirePolicy
  form.concurrencyPolicy = row.concurrencyPolicy
  form.maxRunningInstances = row.maxRunningInstances
  form.timezone = row.timezone
  preview.value = null
  previewErr.value = ''
  editing.value = true
}

function backToList(): void {
  editing.value = false
  preview.value = null
  previewErr.value = ''
}

async function doPreview(): Promise<void> {
  const crontab = form.crontab.trim()
  if (!crontab) {
    preview.value = null
    previewErr.value = '请先填写 crontab 表达式'
    return
  }
  preview.value = null
  previewErr.value = ''
  try {
    const r = await api.value.previewCrontab(crontab, form.timezone.trim() || 'Asia/Shanghai')
    if (r.valid === false) {
      previewErr.value = 'crontab 表达式无效，请检查后重试'
      return
    }
    preview.value = r.nextFireTimes
  } catch {
    previewErr.value = '预览失败，请稍后重试'
  }
}

/** 门链顺序镜像后端 normalized()：crontab→misfire→concurrency→maxRunning(拒绝)→previewErr→自动预览→复查→钳位提交。 */
async function submitForm(): Promise<void> {
  if (submitting.value) return
  const crontab = form.crontab.trim()
  if (!crontab) {
    ElMessage.warning('请填写 crontab 表达式')
    return
  }
  if (!(MISFIRE_OPTIONS as readonly string[]).includes(form.misfirePolicy)) {
    ElMessage.warning('misfire 策略不在允许范围内')
    return
  }
  if (!(CONCURRENCY_OPTIONS as readonly string[]).includes(form.concurrencyPolicy)) {
    ElMessage.warning('并发策略不在允许范围内')
    return
  }
  // maxRunning 为后端拒绝语义（非整数/<1 → 4001），UI 阻断不钳位。
  const maxRunning = Math.trunc(Number(form.maxRunningInstances))
  if (!Number.isFinite(Number(form.maxRunningInstances)) || maxRunning < 1) {
    ElMessage.warning('最大并行实例数需为不小于 1 的整数')
    return
  }
  if (previewErr.value) {
    ElMessage.warning(previewErr.value)
    return
  }
  if (preview.value === null) {
    await doPreview()
  }
  if (previewErr.value) {
    ElMessage.warning(previewErr.value)
    return
  }
  submitting.value = true
  try {
    const priority = Math.min(5, Math.max(1, Math.trunc(Number(form.priority) || 3)))
    const failRetryTimes = Math.max(0, Math.trunc(Number(form.failRetryTimes) || 0))
    const failRetryInterval = Math.max(1, Math.trunc(Number(form.failRetryInterval) || 60))
    const input: ScheduleInput = {
      name: form.name.trim() || undefined,
      crontab,
      startTime: form.startTime.trim() || null,
      endTime: form.endTime.trim() || null,
      priority,
      workerGroup: form.workerGroup.trim() || null,
      failRetryTimes,
      failRetryInterval,
      misfirePolicy: form.misfirePolicy,
      concurrencyPolicy: form.concurrencyPolicy,
      maxRunningInstances: maxRunning,
      timezone: form.timezone.trim() || 'Asia/Shanghai',
    }
    const result = editId.value === null
      ? await api.value.createSchedule(props.wf, input)
      : await api.value.updateSchedule(editId.value, input)
    ElMessage.success(
      editId.value === null
        ? `定时已创建（初始下线），下次触发：${result.nextFireTimes?.[0] ?? '-'}`
        : '定时已更新',
    )
    editing.value = false
    preview.value = null
    previewErr.value = ''
    await reload()
  } catch {
    ElMessage.error('保存失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}

async function toggleState(row: ScheduleRow): Promise<void> {
  try {
    const updated = row.state === 'online'
      ? await api.value.offlineSchedule(row.id)
      : await api.value.onlineSchedule(row.id)
    Object.assign(row, updated)
  } catch {
    ElMessage.error('状态切换失败，请稍后重试')
  }
}

async function onDelete(row: ScheduleRow): Promise<void> {
  try {
    await ElMessageBox.confirm('确认删除该定时任务？', '提示', { type: 'warning' })
  } catch {
    return
  }
  try {
    await api.value.deleteSchedule(row.id)
    ElMessage.success('定时已删除')
    await reload()
  } catch {
    ElMessage.error('删除失败，请稍后重试')
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="visible" class="sd-mask" data-part="mask" @click.self="close">
      <section ref="sdPanelRef" class="sd-panel" role="dialog" aria-modal="true" :aria-label="`定时调度 - ${wfName ?? wf}`" :style="sdDragStyle">
        <header ref="sdHeaderRef" class="sd-header" data-part="header" @pointerdown="onSdDragStart">
          <span class="sd-title">定时调度 - {{ wfName ?? wf }}</span>
          <button type="button" class="sd-close" aria-label="关闭" data-test="close-btn" @click="close">×</button>
        </header>

        <div class="sd-body" data-part="body">
          <template v-if="!editing">
            <div class="sd-toolbar">
              <button type="button" class="sd-btn sd-btn--primary" data-test="create-btn" @click="openCreate">新建定时</button>
            </div>
            <p v-if="loading" class="sd-hint" data-test="list-loading">加载中…</p>
            <p v-else-if="rows.length === 0" class="sd-hint" data-test="list-empty">暂无定时任务</p>
            <table v-else class="sd-table">
              <thead>
                <tr>
                  <th>名称</th>
                  <th>crontab</th>
                  <th>状态</th>
                  <th>优先级</th>
                  <th>失败重试</th>
                  <th>操作</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="row in rows" :key="row.id">
                  <td>{{ row.name || '-' }}</td>
                  <td>{{ row.crontab }}</td>
                  <td>
                    <span
                      class="sd-pill"
                      :class="row.state === 'online' ? 'sd-pill--online' : 'sd-pill--offline'"
                      data-test="state-pill"
                    >{{ row.state === 'online' ? '已上线' : '已下线' }}</span>
                  </td>
                  <td>{{ row.priority }}</td>
                  <td>{{ row.failRetryTimes }}</td>
                  <td class="sd-actions">
                    <button type="button" class="sd-link" data-test="edit-btn" @click="openEdit(row)">编辑</button>
                    <button type="button" class="sd-link" data-test="toggle-btn" @click="toggleState(row)">
                      {{ row.state === 'online' ? '下线' : '上线' }}
                    </button>
                    <button type="button" class="sd-link sd-link--danger" data-test="delete-btn" @click="onDelete(row)">删除</button>
                  </td>
                </tr>
              </tbody>
            </table>
          </template>

          <form v-else class="sd-form" @submit.prevent="submitForm">
            <div class="sd-field">
              <span class="sd-label">任务名称</span>
              <input v-model="form.name" class="sd-input" data-test="name" placeholder="留空默认按工作流命名" />
            </div>
            <div class="sd-field">
              <span class="sd-label">时区</span>
              <input v-model="form.timezone" class="sd-input" data-test="timezone" placeholder="Asia/Shanghai" />
            </div>
            <div class="sd-field sd-field--full">
              <span class="sd-label">crontab 表达式</span>
              <div class="sd-crontab-row">
                <input v-model="form.crontab" class="sd-input" data-test="crontab" placeholder="* * * * *" @change="doPreview" />
                <button type="button" class="sd-btn" data-test="preview-btn" @click="doPreview">预览下次触发</button>
              </div>
            </div>
            <div v-if="previewErr" class="sd-field sd-field--full">
              <p class="sd-preview-err" data-test="preview-err">{{ previewErr }}</p>
            </div>
            <div v-else-if="preview" class="sd-field sd-field--full">
              <div class="sd-preview" data-test="preview-list">
                <span>下次触发时间：</span>
                <ul>
                  <li v-for="(t, i) in preview" :key="i">{{ t }}</li>
                </ul>
              </div>
            </div>
            <div class="sd-field">
              <span class="sd-label">优先级（1-5）</span>
              <input v-model.number="form.priority" type="number" min="1" max="5" class="sd-input" data-test="priority" />
            </div>
            <div class="sd-field">
              <span class="sd-label">Worker 分组</span>
              <input v-model="form.workerGroup" class="sd-input" data-test="worker-group" placeholder="default" />
            </div>
            <div class="sd-field">
              <span class="sd-label">misfire 错峰策略</span>
              <select v-model="form.misfirePolicy" class="sd-input" data-test="misfire">
                <option v-for="opt in MISFIRE_OPTIONS" :key="opt" :value="opt">{{ MISFIRE_LABELS[opt] }}</option>
              </select>
            </div>
            <div class="sd-field">
              <span class="sd-label">并发策略</span>
              <select v-model="form.concurrencyPolicy" class="sd-input" data-test="concurrency">
                <option v-for="opt in CONCURRENCY_OPTIONS" :key="opt" :value="opt">{{ CONCURRENCY_LABELS[opt] }}</option>
              </select>
            </div>
            <div class="sd-field">
              <span class="sd-label">最大并行实例数</span>
              <input v-model.number="form.maxRunningInstances" type="number" min="1" step="1" class="sd-input" data-test="max-running" />
            </div>
            <div class="sd-field">
              <span class="sd-label">失败重试次数</span>
              <input v-model.number="form.failRetryTimes" type="number" min="0" class="sd-input" data-test="retry-times" />
            </div>
            <div class="sd-field">
              <span class="sd-label">重试间隔（秒）</span>
              <input v-model.number="form.failRetryInterval" type="number" min="1" class="sd-input" data-test="retry-interval" />
            </div>
            <div class="sd-field">
              <span class="sd-label">开始时间</span>
              <input v-model="form.startTime" class="sd-input" data-test="start-time" placeholder="YYYY-MM-DD HH:mm:ss" />
            </div>
            <div class="sd-field">
              <span class="sd-label">结束时间</span>
              <input v-model="form.endTime" class="sd-input" data-test="end-time" placeholder="YYYY-MM-DD HH:mm:ss" />
            </div>
          </form>
        </div>

        <footer v-if="editing" class="sd-footer" data-part="footer">
          <button type="button" class="sd-btn" data-test="back-btn" @click="backToList">返回列表</button>
          <button type="button" class="sd-btn sd-btn--primary" data-test="save-btn" :disabled="submitting" @click="submitForm">保存</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.sd-mask {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}
.sd-panel {
  width: 780px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 96px);
  background: var(--card);
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  box-shadow: var(--shadow-xl);
  overflow: hidden;
}
.sd-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  cursor: grab;
  user-select: none;
}
.sd-header:active {
  cursor: grabbing;
}
.sd-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}
.sd-close {
  border: none;
  background: none;
  font-size: 20px;
  line-height: 1;
  color: var(--text-3);
  cursor: pointer;
  padding: 0 4px;
}
.sd-body {
  padding: 16px 20px;
  overflow-y: auto;
  flex: 1;
}
.sd-toolbar {
  margin-bottom: 12px;
}
.sd-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.sd-table th,
.sd-table td {
  border-bottom: 1px solid var(--border);
  padding: 8px 10px;
  text-align: left;
}
.sd-table th {
  color: var(--text-2);
  font-weight: 500;
  background: var(--bg);
}
.sd-pill {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
}
.sd-pill--online {
  background: var(--success-bg);
  color: var(--success);
}
.sd-pill--offline {
  background: var(--bg-deep);
  color: var(--text-2);
}
.sd-actions {
  white-space: nowrap;
}
.sd-link {
  border: none;
  background: none;
  color: var(--primary);
  cursor: pointer;
  font-size: 13px;
  padding: 0 6px;
}
.sd-link--danger {
  color: var(--danger);
}
.sd-hint {
  color: var(--text-3);
  text-align: center;
  padding: 24px 0;
  font-size: 13px;
  margin: 0;
}
.sd-form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px 16px;
}
.sd-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.sd-field--full {
  grid-column: 1 / -1;
}
.sd-label {
  font-size: 12px;
  color: var(--text-2);
}
.sd-input {
  height: 32px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  padding: 0 10px;
  font-size: 13px;
  color: var(--text);
  background: var(--card);
  box-sizing: border-box;
}
.sd-input:focus {
  outline: none;
  border-color: var(--primary);
}
.sd-crontab-row {
  display: flex;
  gap: 8px;
  align-items: center;
}
.sd-crontab-row .sd-input {
  flex: 1;
}
.sd-preview {
  border: 1px solid var(--border);
  background: var(--info-bg);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--info);
}
.sd-preview ul {
  margin: 4px 0 0;
  padding-left: 18px;
}
.sd-preview-err {
  border: 1px solid var(--danger);
  background: var(--danger-bg);
  border-radius: 6px;
  padding: 8px 12px;
  font-size: 12px;
  color: var(--danger);
  margin: 0;
}
.sd-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 12px 20px;
  border-top: 1px solid var(--border);
}
.sd-btn {
  height: 32px;
  padding: 0 16px;
  border-radius: 6px;
  border: 1px solid var(--border-strong);
  background: var(--card);
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
}
.sd-btn--primary {
  background: var(--primary);
  border-color: var(--primary);
  color: var(--card);
}
.sd-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
