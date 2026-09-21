<script setup lang="ts">
/**
 * I3 F46 定时调度对话框（§13 DagListView「定时」操作）：
 * - 定时列表（t_wf_schedule）：crontab/状态/优先级/重试参数 + 上线/下线/编辑/删除；
 * - 新建/编辑：cron 编辑 + 即时预览（POST /crontab-preview 未来 3 次）+ 重试参数；
 * - 上线/下线走 run_instance 权限（master 定时线程 10s 扫描触发）。
 * mock 模式：仅提示（后端能力，不演示假数据）。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  isMock, listSchedules, createSchedule, updateSchedule, deleteSchedule,
  onlineSchedule, offlineSchedule, previewCrontab,
} from '../../services'
import type { ScheduleRow } from '../../services'

const props = defineProps<{ modelValue: boolean; wf: string; wfName?: string }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v: boolean) => emit('update:modelValue', v),
})

const rows = ref<ScheduleRow[]>([])
const loading = ref(false)

async function reload() {
  if (!props.wf || isMock) return
  loading.value = true
  try {
    rows.value = await listSchedules(props.wf)
  } catch (e) {
    ElMessage.error('定时列表加载失败：' + errMsg(e))
  } finally {
    loading.value = false
  }
}

watch(() => [props.modelValue, props.wf], ([on]) => {
  if (on) {
    if (isMock) { ElMessage.info('定时调度为 real 后端能力（I3），mock 模式仅示意'); visible.value = false; return }
    reload()
  }
})

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

/* ---------- 新建/编辑表单 ---------- */
const editing = ref(false)          // false=列表视图，true=表单视图
const editId = ref<number | null>(null) // null=新建
const form = ref({
  name: '默认定时',
  crontab: '0 0 2 * * ?',
  start_time: '',
  end_time: '',
  priority: 3,
  worker_group: '',
  fail_retry_times: 0,
  fail_retry_interval: 60,
})
const preview = ref<string[]>([])
const previewErr = ref('')
const submitting = ref(false)

function openCreate() {
  editId.value = null
  form.value = { name: '默认定时', crontab: '0 0 2 * * ?', start_time: '', end_time: '', priority: 3, worker_group: '', fail_retry_times: 0, fail_retry_interval: 60 }
  preview.value = []
  previewErr.value = ''
  editing.value = true
}

function openEdit(r: ScheduleRow) {
  editId.value = r.id
  form.value = {
    name: r.name,
    crontab: r.crontab,
    start_time: (r.startTime ?? '').slice(0, 19).replace('T', ' '),
    end_time: (r.endTime ?? '').slice(0, 19).replace('T', ' '),
    priority: r.priority,
    worker_group: r.workerGroup ?? '',
    fail_retry_times: r.failRetryTimes,
    fail_retry_interval: r.failRetryInterval,
  }
  preview.value = []
  previewErr.value = ''
  editing.value = true
}

/** cron 校验 + 未来 3 次触发预览 */
async function doPreview() {
  preview.value = []
  previewErr.value = ''
  if (!form.value.crontab.trim()) { previewErr.value = '请输入 crontab 表达式'; return }
  try {
    const r = await previewCrontab(form.value.crontab.trim())
    preview.value = r.nextFireTimes ?? []
  } catch (e) {
    previewErr.value = errMsg(e)
  }
}

async function submitForm() {
  if (!form.value.crontab.trim()) { ElMessage.warning('crontab 不能为空'); return }
  if (previewErr.value) { ElMessage.warning('crontab 校验未通过，请修正'); return }
  if (!preview.value.length) await doPreview()
  if (previewErr.value) return
  submitting.value = true
  try {
    const body = {
      name: form.value.name.trim() || '默认定时',
      crontab: form.value.crontab.trim(),
      start_time: form.value.start_time || undefined,
      end_time: form.value.end_time || undefined,
      priority: form.value.priority,
      worker_group: form.value.worker_group || undefined,
      fail_retry_times: form.value.fail_retry_times,
      fail_retry_interval: form.value.fail_retry_interval,
    }
    if (editId.value === null) {
      const created = await createSchedule(props.wf, body)
      ElMessage.success(`定时已创建（初始下线），下次触发：${created.nextFireTimes?.[0] ?? '-'}`)
    } else {
      await updateSchedule(editId.value, body)
      ElMessage.success('定时已更新（master 将按新 update_time 重算触发时间）')
    }
    editing.value = false
    await reload()
  } catch (e) {
    ElMessage.error('保存失败：' + errMsg(e))
  } finally {
    submitting.value = false
  }
}

async function toggleState(r: ScheduleRow) {
  try {
    if (r.state === 'online') {
      await offlineSchedule(r.id)
      ElMessage.success('已下线（不再触发）')
    } else {
      await onlineSchedule(r.id)
      ElMessage.success('已上线（master 定时线程 10s 内扫描生效）')
    }
    await reload()
  } catch (e) {
    ElMessage.error(errMsg(e))
  }
}

async function onDelete(r: ScheduleRow) {
  try {
    await ElMessageBox.confirm(`删除定时「${r.name}」？`, '删除定时', { type: 'warning' })
  } catch { return }
  try {
    await deleteSchedule(r.id)
    ElMessage.success('定时已删除')
    await reload()
  } catch (e) {
    ElMessage.error('删除失败：' + errMsg(e))
  }
}
</script>

<template>
  <el-dialog v-model="visible" :title="`定时调度 - ${wfName ?? wf}`" width="780px" append-to-body destroy-on-close>
    <!-- 列表视图 -->
    <template v-if="!editing">
      <div class="sc-toolbar">
        <span class="sc-cap">定时计划（上线后由 master 定时线程自动触发实例，run_mode=schedule）</span>
        <span class="spacer" />
        <button class="tb-new" @click="openCreate">+ 新建定时</button>
      </div>
      <table class="tbl">
        <thead>
          <tr><th>名称</th><th>crontab</th><th>状态</th><th>优先级</th><th>失败重试</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="6" class="sc-empty">加载中…</td></tr>
          <tr v-for="r in rows" :key="r.id">
            <td style="font-weight:600">{{ r.name }}</td>
            <td class="mono" style="font-size:11.5px">{{ r.crontab }}</td>
            <td><span class="pill" :class="r.state === 'online' ? 'ok' : 'off'">{{ r.state === 'online' ? '已上线' : '已下线' }}</span></td>
            <td>{{ r.priority }}</td>
            <td style="font-size:11px">{{ r.failRetryTimes }} 次 / {{ r.failRetryInterval }}s</td>
            <td>
              <button class="op-btn" :class="{ primary: r.state !== 'online' }" @click="toggleState(r)">{{ r.state === 'online' ? '下线' : '上线' }}</button>
              <button class="op-btn" @click="openEdit(r)">编辑</button>
              <button class="op-btn" @click="onDelete(r)">删除</button>
            </td>
          </tr>
          <tr v-if="!loading && rows.length === 0"><td colspan="6" class="sc-empty">暂无定时计划，点击「+ 新建定时」创建</td></tr>
        </tbody>
      </table>
    </template>

    <!-- 新建/编辑表单 -->
    <template v-else>
      <div class="sc-form">
        <div class="field"><label>名称</label><input v-model="form.name" /></div>
        <div class="field">
          <label>crontab（6 段含秒，`?` 等价 `*`）</label>
          <div class="cron-row">
            <input v-model="form.crontab" class="mono" placeholder="0 0 2 * * ?" @change="doPreview" />
            <button class="op-btn" @click="doPreview">校验并预览</button>
          </div>
          <div v-if="preview.length" class="sc-preview">
            <div class="sc-cap">未来 3 次触发：</div>
            <div v-for="(t, i) in preview" :key="i" class="mono" style="font-size:11.5px">{{ t }}</div>
          </div>
          <div v-else-if="previewErr" class="sc-err">{{ previewErr }}</div>
        </div>
        <div class="field-grid">
          <div class="field"><label>优先级（1~5）</label><input v-model.number="form.priority" type="number" min="1" max="5" /></div>
          <div class="field"><label>Worker 分组（可空）</label><input v-model="form.worker_group" /></div>
          <div class="field"><label>失败重试次数</label><input v-model.number="form.fail_retry_times" type="number" min="0" /></div>
          <div class="field"><label>重试间隔（秒）</label><input v-model.number="form.fail_retry_interval" type="number" min="1" /></div>
          <div class="field"><label>生效开始时间（可空）</label><input v-model="form.start_time" placeholder="YYYY-MM-DD HH:mm:ss" /></div>
          <div class="field"><label>生效结束时间（可空）</label><input v-model="form.end_time" placeholder="YYYY-MM-DD HH:mm:ss" /></div>
        </div>
        <div class="sc-cap" style="margin-top:6px">新建后默认「已下线」，上线需 run_instance 权限；有效期外不触发。</div>
      </div>
    </template>

    <!-- footer 必须是 el-dialog 直接子级（嵌在 v-if 分支内编译失败）：仅表单视图渲染按钮 -->
    <template #footer>
      <template v-if="editing">
        <el-button @click="editing = false">返回列表</el-button>
        <el-button type="primary" :disabled="submitting" @click="submitForm">保存</el-button>
      </template>
    </template>
  </el-dialog>
</template>

<style scoped>
.sc-toolbar{display:flex;align-items:center;margin-bottom:10px}
.sc-toolbar .spacer{flex:1}
.sc-cap{font-size:11px;color:var(--text-3)}
.sc-empty{text-align:center;color:var(--text-3);padding:18px}
.sc-form{display:flex;flex-direction:column;gap:10px}
.sc-form .field{display:flex;flex-direction:column;gap:4px}
.sc-form label{font-size:11.5px;color:var(--text-2);font-weight:600}
.sc-form input{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;outline:none}
.sc-form input:focus{border-color:var(--primary)}
.field-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.cron-row{display:flex;gap:6px}
.cron-row input{flex:1}
.sc-preview{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 9px;margin-top:4px;display:flex;flex-direction:column;gap:2px}
.sc-err{color:var(--danger);font-size:11.5px;margin-top:4px}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:6px 12px;font-size:12px;font-weight:500;cursor:pointer}
.tb-new:hover{background:var(--primary-hover)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:3px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
</style>
