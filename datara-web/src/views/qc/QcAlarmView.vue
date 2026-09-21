<script setup lang="ts">
/**
 * M07 质量告警（/qc/alarm）
 * 原型对齐：prototype/assets/pages/m07-quality.js L352-396（#/qc/alarm + A.qa* 系列）
 * 告警策略表格 + 顶部工具栏「+ 新建告警策略」；行操作：编辑 / 启停用 /
 * 模拟触发（不发送真实消息）/ 删除。
 * 数据：qcAlarms（读写）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { QcAlarm } from '../../services/types'

const rows = ref<QcAlarm[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '', channel: '' })

onMounted(async () => {
  await reload()
})

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发响应式更新。
  rows.value = [...((await dataStore.list<QcAlarm>('qcAlarms')) ?? [])]
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.status && r.status !== filters.value.status) return false
    if (filters.value.channel && !r.channel.includes(filters.value.channel)) return false
    if (!kw) return true
    return [r.id, r.name, r.scope].some((s) => s.toLowerCase().includes(kw))
  })
})

function channels(r: QcAlarm): string[] {
  return r.channel.split('+').filter(Boolean)
}

/* ---- 状态徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}

/* ---- 新建 / 编辑 ---- */
const formVisible = ref(false)
const editing = ref<QcAlarm | null>(null)
const drawerTitle = computed(() => (editing.value ? `编辑告警策略 - ${editing.value.name}` : '新建告警策略'))
const form = ref({ name: '', scope: '', threshold: '', channels: ['邮件'] as string[], receivers: '' })

const CHANNELS = ['邮件', '短信', '飞书']

const facets: Facet[] = [
  { key: 'status', label: '状态', options: [{ v: 'enabled', t: '启用' }, { v: 'disabled', t: '停用' }] },
  { key: 'channel', label: '通知渠道', options: CHANNELS.map((c) => ({ v: c, t: c })) },
]

function openCreate() {
  editing.value = null
  form.value = { name: '', scope: '', threshold: '', channels: ['邮件'], receivers: '' }
  formVisible.value = true
}

function openEdit(r: QcAlarm) {
  editing.value = r
  form.value = {
    name: r.name, scope: r.scope, threshold: r.threshold,
    channels: r.channel ? r.channel.split('+').filter((c) => CHANNELS.includes(c)) : [],
    receivers: r.receivers,
  }
  formVisible.value = true
}

function nextAlarmId(): string {
  let max = 0
  for (const r of rows.value) {
    const n = Number(r.id.replace(/\D/g, ''))
    if (Number.isFinite(n) && n > max) max = n
  }
  return 'QA' + String(max + 1).padStart(2, '0')
}

async function saveForm() {
  const name = form.value.name.trim()
  if (!name) {
    ElMessage.warning('请填写策略名称')
    return
  }
  const channel = form.value.channels.join('+') || '邮件'
  if (editing.value) {
    Object.assign(editing.value, {
      name, scope: form.value.scope.trim(), threshold: form.value.threshold.trim(),
      channel, receivers: form.value.receivers.trim(),
    })
    await dataStore.save('qcAlarms', editing.value)
    ElMessage.success('告警策略已保存')
  } else {
    const alarm: QcAlarm = {
      id: nextAlarmId(), name, scope: form.value.scope.trim(), threshold: form.value.threshold.trim(),
      channel, receivers: form.value.receivers.trim(), status: 'enabled',
    }
    await dataStore.save('qcAlarms', alarm)
    ElMessage.success('告警策略已创建')
  }
  formVisible.value = false
  await reload()
}

/* ---- 模拟触发 ---- */
const fireVisible = ref(false)
const fireTarget = ref<QcAlarm | null>(null)

function openFire(r: QcAlarm) {
  fireTarget.value = r
  fireVisible.value = true
}

/* ---- 启停用 / 删除 ---- */
async function toggleStatus(r: QcAlarm) {
  r.status = r.status === 'enabled' ? 'disabled' : 'enabled'
  await dataStore.save('qcAlarms', r)
  ElMessage.success(r.status === 'enabled' ? `策略「${r.name}」已启用` : `策略「${r.name}」已停用`)
}

async function removeAlarm(r: QcAlarm) {
  try {
    await ElMessageBox.confirm(`确认删除告警策略「${r.name}」？该操作不可恢复。`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await dataStore.remove('qcAlarms', r.id)
  ElMessage.success('告警策略已删除')
  await reload()
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索策略"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部工具栏按钮 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">质量告警</div>
        <div class="ph-desc">告警策略：强规则失败即时告警 / 弱规则汇总告警 / 评分阈值告警，多渠道触达</div>
      </div>
      <div class="ph-acts">
        <button class="tb-new" @click="openCreate">+ 新建告警策略</button>
      </div>
    </div>

    <!-- 告警策略列表 -->
    <div class="card panel">
      <div class="tbl-toolbar">
        <span class="sec-head">告警策略</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>策略</th><th>范围</th><th>触发条件</th><th>渠道</th><th>接收人</th><th>状态</th>
            <th style="width:230px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td>
              <b>{{ r.name }}</b>
              <div style="font-size:11px;color:var(--text-3)">{{ r.id }}</div>
            </td>
            <td style="font-size:12px">{{ r.scope }}</td>
            <td style="font-size:12px">{{ r.threshold }}</td>
            <td>
              <span v-for="c in channels(r)" :key="c" class="pill info ch-pill">{{ c }}</span>
            </td>
            <td style="font-size:12px">{{ r.receivers }}</td>
            <td><span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span></td>
            <td>
              <button class="op-btn primary" @click="openEdit(r)">编辑</button>
              <button class="op-btn" @click="toggleStatus(r)">{{ r.status === 'enabled' ? '停用' : '启用' }}</button>
              <button class="op-btn" @click="openFire(r)">模拟触发</button>
              <button class="op-btn danger" @click="removeAlarm(r)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的告警策略</div>
    </div>

    <!-- 模拟触发弹窗 -->
    <el-dialog v-model="fireVisible" :title="fireTarget ? `模拟告警触发 - ${fireTarget.name}` : ''" width="420px">
      <template v-if="fireTarget">
        <div class="fire-line">
          <span class="fire-ico">⚠</span>
          <div>
            <b>[{{ fireTarget.channel }}] 质量告警</b>
            <div class="fire-sub">触发条件：{{ fireTarget.threshold }}<br />接收人：{{ fireTarget.receivers }}</div>
          </div>
        </div>
        <div class="lock-tip">模拟触发不发送真实消息。</div>
      </template>
    </el-dialog>

    <!-- 新建 / 编辑抽屉 -->
    <el-drawer v-model="formVisible" :title="drawerTitle" size="440px">
      <div class="form-grid">
        <label class="f-item">策略名称 *
          <input v-model="form.name" class="kw" style="width:100%" placeholder="如：强规则失败即时告警" />
        </label>
        <label class="f-item">生效范围
          <input v-model="form.scope" class="kw" style="width:100%" placeholder="如：所有强规则失败 / WF001" />
        </label>
        <label class="f-item">触发条件 *
          <input v-model="form.threshold" class="kw" style="width:100%" placeholder="如：规则失败即告警 / 评分 < 90" />
        </label>
        <div class="f-item">通知渠道
          <div class="chk-row">
            <label v-for="c in CHANNELS" :key="c" class="radio-line">
              <input v-model="form.channels" type="checkbox" :value="c" />{{ c }}
            </label>
          </div>
        </div>
        <label class="f-item">接收人
          <input v-model="form.receivers" class="kw" style="width:100%" placeholder="如：王工/李工/值班" />
        </label>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveForm">保存</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>
    </div>
  </div>
</template>

<style scoped>
.page-head{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;margin-bottom:14px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-2);margin-top:3px}
.ph-acts{margin-left:auto;display:flex;gap:8px;flex-shrink:0}
.panel{padding:14px 16px}
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.tbl-toolbar .spacer{flex:1}
.pill.info{display:inline-flex;align-items:center;padding:1px 9px;border-radius:var(--radius-lg);font-size:11px;background:var(--info-bg);color:var(--info)}
.ch-pill{margin-right:4px}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none}
.kw:focus{border-color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.lock-tip{margin-top:12px;border-left:3px solid var(--warn);background:var(--warn-bg);color:var(--warn);font-size:11.5px;padding:7px 10px;border-radius:0 7px 7px 0}
.fire-line{display:flex;gap:10px;align-items:flex-start;border:1px solid rgba(229,72,77,.4);border-radius:var(--radius);padding:10px 12px;font-size:12.5px;color:var(--danger)}
.fire-ico{font-size:15px}
.fire-sub{font-size:11.5px;margin-top:3px;color:var(--text-2)}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.chk-row{display:flex;gap:14px;flex-wrap:wrap}
.radio-line{display:flex;gap:6px;align-items:center;font-size:12.5px;color:var(--text);cursor:pointer}
</style>
