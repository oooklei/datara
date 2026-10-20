<!--
  I7：调度运行时验证页（RED/原型态）。
  权威范围：plan I7（docs/superpowers/plans/2026-10-14-datara-platform-rebuild.md）
  + docs/increments/I7-I9-前端消费面分析.md §1/§3。
  边界：独立验证页，不进正式菜单（I11 融合）；契约全部经 services/rebuild/scheduleApi
  （后端接入前抛 R6_SCHEDULER_NOT_WIRED，UI 统一横幅提示）；不触发增量 GREEN。
-->
<template>
  <div class="r6-page">
    <el-alert
      :type="bannerType"
      :closable="false"
      show-icon
      data-testid="r6-red-banner"
      :title="bannerTitle"
    />

    <el-descriptions :column="3" size="small" border class="r6-context">
      <el-descriptions-item label="触发类型面">MANUAL / CRON / DEPENDENCY / EVENT / TRIAL</el-descriptions-item>
      <el-descriptions-item label="观测面">misfire / 并发 / 优先级 / 超时 / 重试 / Master 分派</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（全部未接线）</el-descriptions-item>
    </el-descriptions>

    <!-- registerTrigger 注册表单（RED：哨兵落状态栏；成功时回显保存的 trigger） -->
    <div class="r6-panel" data-testid="r6-register-panel">
      <div class="r6-panel-head"><span>触发注册表单 — registerTrigger</span></div>
      <el-form inline size="small" class="r6-form">
        <el-form-item label="名称"><el-input v-model="registerForm.name" data-testid="r6-register-name" style="width: 140px" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="registerForm.kind" data-testid="r6-register-kind" style="width: 130px">
            <el-option label="MANUAL" value="MANUAL" />
            <el-option label="CRON" value="CRON" />
            <el-option label="DEPENDENCY" value="DEPENDENCY" />
            <el-option label="EVENT" value="EVENT" />
            <el-option label="TRIAL" value="TRIAL" />
          </el-select>
        </el-form-item>
        <el-form-item label="CRON"><el-input v-model="registerForm.cron" data-testid="r6-register-cron" placeholder="0 0 * * *" style="width: 140px" /></el-form-item>
        <el-form-item label="Source"><el-input v-model="registerForm.source" data-testid="r6-register-source" placeholder="依赖工作流ID/事件源" style="width: 150px" /></el-form-item>
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
            <span>实例队列（并发/优先级/misfire）</span>
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
  </div>
</template>

<script setup lang="ts">
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
} from '../../../../services/rebuild/scheduleApi'
import { bannerAlertType, bannerTitleFor } from '../../../../services/rebuild/bannerStatus'

defineOptions({ name: 'ScheduleValidationView' })

const contract = createScheduleContract()
const contractMethodCount = R6_CONTRACT_METHODS.length

/* 横幅状态词表（FE-01 单一事实源）：RED 未接线 */
const bannerTitle = bannerTitleFor(
  { code: 'R6', contractName: 'schedule', methodCount: contractMethodCount, sentinel: R6_SCHEDULER_NOT_WIRED },
  'RED',
)
const bannerType = bannerAlertType('RED')

/* 观测面数据（后端接入前恒为空，展示空态） */
const triggers = ref<TriggerRegistration[]>([])
const queue = ref<ScheduleQueueEntry[]>([])
const events = ref<ScheduleRuntimeEvent[]>([])
const alerts = ref<ScheduleAlert[]>([])

/* registerTrigger 注册表单（字段按 TriggerRegistrationInput） */
const registerForm = reactive({ name: '', kind: 'MANUAL' as TriggerKind, cron: '', source: '', enabled: true })
const registeredTrigger = ref<TriggerRegistration | null>(null)

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互 */
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

const statusText = ref('待操作')

function onListTriggers() {
  return guard(async () => {
    triggers.value = await contract.listTriggers()
  }, '加载触发注册')
}

function onRegisterTrigger() {
  return guard(async () => {
    const registered = await contract.registerTrigger({
      name: registerForm.name,
      kind: registerForm.kind,
      cron: registerForm.cron || null,
      source: registerForm.source || null,
      enabled: registerForm.enabled,
    })
    registeredTrigger.value = registered
  }, '注册触发')
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
</script>

<style scoped>
.r6-page {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
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
