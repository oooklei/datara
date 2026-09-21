<script setup lang="ts">
/**
 * I3 运行对话框（§13「Workbench 运行对话框」增强，GraphWorkbench「试运行」real 模式弹出）：
 * - 手工运行页签：优先级 + 环境组（可选）→ POST /workflow-definitions/{wf}/run（START_PROCESS）；
 * - 补数页签：日期范围 + 并行开关 → POST /workflow-definitions/{wf}/complement（COMPLEMENT_DATA 展开多实例）；
 * - 均写 t_command 由 master 2s 内消费；实例产生后到「运行实例（引擎）」页查看。
 * mock 模式不弹本框（保持 execService 本地演示链路）。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { runWorkflow, complementWorkflow } from '../../services'

const props = defineProps<{ modelValue: boolean; wf: string; wfName?: string }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'submitted', kind: 'run' | 'complement', info: string): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const tab = ref<'run' | 'complement'>('run')
const priority = ref(3)
const envGroupId = ref<number | ''>('')
const dateFrom = ref('')
const dateTo = ref('')
const parallel = ref(false)
const submitting = ref(false)

watch(visible, (v) => { if (v) { tab.value = 'run'; priority.value = 3; envGroupId.value = ''; dateFrom.value = ''; dateTo.value = ''; parallel.value = false } })

/** 环境组 ID（可选；t_env_group.id，管理 UI 后置增量——输入数字或留空） */
function envGroupPayload(): number | undefined {
  return envGroupId.value === '' ? undefined : Number(envGroupId.value)
}

function validDates(): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateFrom.value) || !/^\d{4}-\d{2}-\d{2}$/.test(dateTo.value)) {
    ElMessage.warning('补数日期格式应为 YYYY-MM-DD')
    return false
  }
  if (dateTo.value < dateFrom.value) {
    ElMessage.warning('结束日期早于开始日期')
    return false
  }
  return true
}

async function submit() {
  submitting.value = true
  try {
    if (tab.value === 'run') {
      const r = await runWorkflow(props.wf, {
        priority: priority.value,
        env_group_id: envGroupPayload(),
      })
      if (r.mode === 'stream') {
        ElMessage.success(`流任务已${r.restarted ? '重启' : '启动'}（${r.name ?? ''}，jobId=${r.streamJobId}）；运行态见组件浮窗与运行监控`)
        emit('submitted', 'run', `流任务 jobId=${r.streamJobId}`)
      } else {
        ElMessage.success(`运行命令已提交（commandId=${r.commandId}，master 2s 内建实例）`)
        emit('submitted', 'run', `commandId=${r.commandId}`)
      }
    } else {
      if (!validDates()) return
      const r = await complementWorkflow(props.wf, {
        date_from: dateFrom.value,
        date_to: dateTo.value,
        parallel: parallel.value,
        priority: priority.value,
        env_group_id: envGroupPayload(),
      })
      ElMessage.success(`补数命令已提交：${r.instances} 个实例（${parallel.value ? '并行' : '串行'}，commandId=${r.commandId}）`)
      emit('submitted', 'complement', `${r.instances} 个实例`)
    }
    visible.value = false
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" :title="`运行工作流 - ${wfName ?? wf}`" width="460px" append-to-body>
    <div class="rd-tabs">
      <button class="rd-tab" :class="{ on: tab === 'run' }" @click="tab = 'run'">手工运行</button>
      <button class="rd-tab" :class="{ on: tab === 'complement' }" @click="tab = 'complement'">补数</button>
    </div>

    <template v-if="tab === 'run'">
      <div class="rd-hint">提交 START_PROCESS 命令，master 建实例后按拓扑执行；画布为空时后端拒绝。</div>
    </template>
    <template v-else>
      <div class="rd-hint">提交 COMPLEMENT_DATA 命令：按日期范围每日展开一个实例（schedule_time=当日，时间变量以其为基准）。</div>
      <div class="rd-grid">
        <div class="rd-field"><label>开始日期</label><input v-model="dateFrom" type="date" class="mono" /></div>
        <div class="rd-field"><label>结束日期</label><input v-model="dateTo" type="date" class="mono" /></div>
      </div>
      <label class="rd-check">
        <input v-model="parallel" type="checkbox" />
        <span>并行展开（勾选后多实例同时入队；否则按日期串行排队）</span>
      </label>
    </template>

    <div class="rd-grid" style="margin-top:10px">
      <div class="rd-field">
        <label>优先级（1~5）</label>
        <input v-model.number="priority" type="number" min="1" max="5" />
      </div>
      <div class="rd-field">
        <label>环境组 ID（可选）</label>
        <input v-model="envGroupId" type="number" min="1" placeholder="留空 = 不绑定" />
      </div>
    </div>
    <div class="rd-hint" style="margin-top:6px">
      环境组取 t_env_group.id（变量解析「环境组」层级用）；环境组管理 UI 为后置增量。
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="submitting" @click="submit">
        {{ tab === 'run' ? '提交运行' : '提交补数' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.rd-tabs{display:flex;gap:6px;margin-bottom:10px}
.rd-tab{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:5px 14px;font-size:12.5px;cursor:pointer;color:var(--text-2)}
.rd-tab.on{border-color:var(--primary);color:var(--primary);background:var(--primary-light);font-weight:600}
.rd-hint{font-size:11px;color:var(--text-3);line-height:1.6}
.rd-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:8px}
.rd-field{display:flex;flex-direction:column;gap:4px}
.rd-field label{font-size:11.5px;color:var(--text-2);font-weight:600}
.rd-field input{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;outline:none}
.rd-field input:focus{border-color:var(--primary)}
.rd-check{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--text-2);margin-top:8px;cursor:pointer}
</style>
