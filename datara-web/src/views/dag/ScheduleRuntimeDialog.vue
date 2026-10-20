<script setup lang="ts">
/**
 * R6 调度运行时弹窗骨架（FE-08 / B3 批次，可先行骨架）。
 * 承接 services/rebuild/scheduleApi（RED 阶段：I/O 统一抛 R6_SCHEDULER_NOT_WIRED，
 * 工作流域建模交付后逐方法替换为真实实现，UI 层不感知切换）。
 *
 * 调度语义面：
 *  - misfire：触发注册表单 misfirePolicy 占位（契约字段已存在；持久化域模型证据不足待核，大盘 #31）；
 *  - concurrency / priority：实例队列观测面展示（契约 ScheduleQueueEntry.priority / concurrencySlot）；
 *  - 不伪造契约输入字段（TriggerRegistrationInput 仅含 misfirePolicy，concurrency/priority 无输入位）。
 *
 * 命名说明：正式页 I3 定时调度弹窗（views/dag/ScheduleDialog.vue，t_wf_schedule 旧协议）
 * 与 R6 调度运行时语义不同，本组件独立命名 ScheduleRuntimeDialog，不覆盖旧组件。
 * 旧 I3 页面保持不动（FE-05/06 已收口的变量/依赖页签不受影响）。
 */
import { reactive, ref } from 'vue'
import {
  R6_CONTRACT_METHODS,
  R6_SCHEDULER_NOT_WIRED,
  createScheduleContract,
  type ScheduleAlert,
  type ScheduleQueueEntry,
  type ScheduleRuntimeEvent,
  type TriggerKind,
  type TriggerRegistration,
} from '../../services/rebuild/scheduleApi'

defineOptions({ name: 'ScheduleRuntimeDialog' })

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const contract = createScheduleContract()
const contractMethodCount = R6_CONTRACT_METHODS.length

/* ---------- 触发注册表单（字段面 = TriggerRegistrationInput；misfirePolicy 为契约已有占位字段） ---------- */
const TRIGGER_KINDS: { value: TriggerKind; hint: string }[] = [
  { value: 'MANUAL', hint: '手工触发' },
  { value: 'CRON', hint: 'CRON 周期触发' },
  { value: 'DEPENDENCY', hint: '依赖工作流完成后触发' },
  { value: 'EVENT', hint: '事件源触发' },
  { value: 'TRIAL', hint: '试运行触发（八能力面）' },
]
/** misfire 策略占位选项（草案词形，持久化域模型待核——大盘 #31，建模收口后细化） */
const MISFIRE_POLICIES = ['FIRE_NOW', 'RESCHEDULE', 'SKIP']

const registerForm = reactive({
  name: '',
  kind: 'MANUAL' as TriggerKind,
  cron: '',
  source: '',
  misfirePolicy: 'FIRE_NOW',
  enabled: true,
})
const registeredTrigger = ref<TriggerRegistration | null>(null)

function onRegisterTrigger() {
  statusText.value = '注册触发…'
  contract
    .registerTrigger({
      name: registerForm.name,
      kind: registerForm.kind,
      cron: registerForm.cron || null,
      source: registerForm.source || null,
      misfirePolicy: registerForm.misfirePolicy,
      enabled: registerForm.enabled,
    })
    .then((registered) => {
      registeredTrigger.value = registered
      statusText.value = '注册触发 完成'
    })
    .catch((err: unknown) => {
      statusText.value =
        err instanceof Error && err.message.startsWith(R6_SCHEDULER_NOT_WIRED)
          ? `注册触发：后端未接线（${R6_SCHEDULER_NOT_WIRED.split(':')[0]}）`
          : `注册触发 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

/* ---------- 观测面数据（RED 阶段恒为空，展示空态） ---------- */
const triggers = ref<TriggerRegistration[]>([])
const queue = ref<ScheduleQueueEntry[]>([])
const events = ref<ScheduleRuntimeEvent[]>([])
const alerts = ref<ScheduleAlert[]>([])

const statusText = ref('待操作')

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互（与 ScheduleValidationView 同构） */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value =
        err instanceof Error && err.message.startsWith(R6_SCHEDULER_NOT_WIRED)
          ? `${label}：后端未接线（${R6_SCHEDULER_NOT_WIRED.split(':')[0]}）`
          : `${label} 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

function onListTriggers() {
  return guard(async () => {
    triggers.value = await contract.listTriggers()
  }, '加载触发注册')
}

function onListQueue() {
  return guard(async () => {
    queue.value = await contract.listQueue()
  }, '加载实例队列')
}

function onListEvents() {
  return guard(async () => {
    events.value = await contract.listRuntimeEvents(null)
  }, '加载事件流')
}

function onListAlerts() {
  return guard(async () => {
    alerts.value = await contract.listAlerts()
  }, '加载 Alert')
}

function close() {
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="调度运行时（R6）"
    width="860px"
    append-to-body
    destroy-on-close
    data-testid="r6-schedule-dialog"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      data-testid="r6-red-banner"
      title="R6 RED 骨架（可先行）— rebuild/schedule 后端契约未接入，所有 I/O 返回 R6_SCHEDULER_NOT_WIRED"
    />

    <el-descriptions :column="3" size="small" border class="r6-context">
      <el-descriptions-item label="触发类型面">MANUAL / CRON / DEPENDENCY / EVENT / TRIAL</el-descriptions-item>
      <el-descriptions-item label="观测面">misfire（注册占位）/ 并发槽位 / 优先级（队列观测）</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（全部未接线）</el-descriptions-item>
    </el-descriptions>

    <!-- registerTrigger 注册表单（RED：哨兵落状态栏；成功时回显保存的 trigger） -->
    <div class="r6-panel" data-testid="r6-register-panel">
      <div class="r6-panel-head"><span>触发注册表单 — registerTrigger</span></div>
      <el-form inline size="small" class="r6-form">
        <el-form-item label="名称"><el-input v-model="registerForm.name" data-testid="r6-register-name" style="width: 130px" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="registerForm.kind" data-testid="r6-register-kind" style="width: 140px">
            <el-option v-for="k in TRIGGER_KINDS" :key="k.value" :label="k.value" :value="k.value" :title="k.hint" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="registerForm.kind === 'CRON'" label="CRON"><el-input v-model="registerForm.cron" data-testid="r6-register-cron" placeholder="0 0 * * *" style="width: 140px" /></el-form-item>
        <el-form-item v-if="registerForm.kind === 'DEPENDENCY' || registerForm.kind === 'EVENT'" label="Source"><el-input v-model="registerForm.source" data-testid="r6-register-source" placeholder="依赖工作流ID/事件源" style="width: 150px" /></el-form-item>
        <el-form-item label="Misfire">
          <el-select v-model="registerForm.misfirePolicy" data-testid="r6-register-misfire" style="width: 140px" placeholder=" misfire 策略（待大盘 #31 建模收口细化）">
            <el-option v-for="p in MISFIRE_POLICIES" :key="p" :label="p" :value="p" />
          </el-select>
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="registerForm.enabled" data-testid="r6-register-enabled" /></el-form-item>
        <el-form-item>
          <el-button size="small" type="primary" data-testid="r6-register-trigger" @click="onRegisterTrigger">注册触发</el-button>
        </el-form-item>
      </el-form>
      <el-descriptions v-if="registeredTrigger" :column="4" size="small" border data-testid="r6-register-result">
        <el-descriptions-item label="ID">{{ registeredTrigger.id }}</el-descriptions-item>
        <el-descriptions-item label="名称">{{ registeredTrigger.name }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ registeredTrigger.kind }}</el-descriptions-item>
        <el-descriptions-item label="启用">{{ registeredTrigger.enabled ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="CRON">{{ registeredTrigger.cron ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="Source">{{ registeredTrigger.source ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="Next Fire">{{ registeredTrigger.nextFireAt ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="Misfire">{{ registeredTrigger.misfirePolicy ?? '—' }}</el-descriptions-item>
      </el-descriptions>
      <div v-else class="r6-empty" data-testid="r6-register-empty">（未接线 — registerTrigger 后端接入前恒为空）</div>
    </div>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="r6-panel">
          <div class="r6-panel-head">
            <span>触发注册</span>
            <el-button size="small" @click="onListTriggers">加载</el-button>
          </div>
          <el-table :data="triggers" size="small" empty-text="（未接线）">
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="kind" label="类型" width="110" />
            <el-table-column prop="nextFireAt" label="Next Fire" width="160" />
            <el-table-column prop="misfirePolicy" label="Misfire" width="110" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="r6-panel">
          <div class="r6-panel-head">
            <span>实例队列（并发槽位 / 优先级观测）</span>
            <el-button size="small" @click="onListQueue">加载</el-button>
          </div>
          <el-table :data="queue" size="small" empty-text="（未接线）">
            <el-table-column prop="instanceId" label="实例" width="80" />
            <el-table-column prop="state" label="状态" width="110" />
            <el-table-column prop="priority" label="优先级" width="80" />
            <el-table-column prop="concurrencySlot" label="槽位" width="70" />
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="r6-panel">
          <div class="r6-panel-head">
            <span>超时/重试事件流（Master 分派 + Logger 事件链）</span>
            <el-button size="small" @click="onListEvents">加载</el-button>
          </div>
          <el-table :data="events" size="small" empty-text="（未接线）">
            <el-table-column prop="seq" label="Seq" width="70" />
            <el-table-column prop="type" label="类型" width="120" />
            <el-table-column prop="attempt" label="Attempt" width="80" />
            <el-table-column prop="occurredAt" label="时间" width="160" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="r6-panel">
          <div class="r6-panel-head">
            <span>Alert 记录</span>
            <el-button size="small" @click="onListAlerts">加载</el-button>
          </div>
          <el-table :data="alerts" size="small" empty-text="（未接线）">
            <el-table-column prop="level" label="级别" width="80" />
            <el-table-column prop="channel" label="通道" width="120" />
            <el-table-column prop="createdAt" label="时间" width="160" />
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      data-testid="r6-status-bar"
      :title="statusText"
    />

    <template #footer>
      <el-button @click="close">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.r6-context {
  margin-bottom: 10px;
}
.r6-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}
.r6-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}
.r6-form {
  margin-bottom: 8px;
}
.r6-empty {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
