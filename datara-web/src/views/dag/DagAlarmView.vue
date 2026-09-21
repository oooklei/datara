<script setup lang="ts">
/**
 * M13 告警与SLA（对齐 prototype m13-dag.js #/dag/alarm）
 * SLA 产出时限监控（今日状态/达标率）+ 调度告警策略
 * （新建/编辑/启停，写 dataStore.save；渠道多选 邮件/短信/飞书）。
 * 数据：dagAlarms / slaRules。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import type { DagAlarm, SlaRule } from '../../services/types'
import ListFilterPanel from '../../components/ListFilterPanel.vue'

const alarms = ref<DagAlarm[]>([])
const slas = ref<SlaRule[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ event: '', status: '' })

const filteredAlarms = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return alarms.value.filter((r) => {
    if (filters.value.event && r.event !== filters.value.event) return false
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.name, r.scope, r.event].some((s) => s.toLowerCase().includes(kw))
  })
})

async function reload() {
  alarms.value = [...((await dataStore.list<DagAlarm>('dagAlarms')) ?? [])]
  slas.value = [...((await dataStore.list<SlaRule>('slaRules')) ?? [])]
}

onMounted(reload)

/* ---- ST 徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}

/* ---- 渠道标签 ---- */
function channels(c: string): string[] {
  return c.split('+').filter(Boolean)
}

/* ---- 新建 / 编辑告警策略 ---- */
const formVisible = ref(false)
const editing = ref<DagAlarm | null>(null)
const form = ref({ name: '', scope: '所有工作流', event: '节点最终失败', chans: ['邮件'] as string[], receivers: '王工/任务负责人' })

const EVENT_OPTIONS = ['节点最终失败', '恢复运行/自动续跑完成', '工作流整体超时']
const CHAN_OPTIONS = ['邮件', '短信', '飞书']

/* ---- 左侧筛选面板 facet（告警无"级别"字段，按原下拉给 触发事件+状态） ---- */
const facets = [
  { key: 'event', label: '触发事件', options: EVENT_OPTIONS.map((e) => ({ v: e, t: e })) },
  { key: 'status', label: '状态', options: [{ v: 'enabled', t: '已启用' }, { v: 'disabled', t: '已停用' }] },
]

function openCreate() {
  editing.value = null
  form.value = { name: '', scope: '所有工作流', event: '节点最终失败', chans: ['邮件'], receivers: '王工/任务负责人' }
  formVisible.value = true
}
function openEdit(r: DagAlarm) {
  editing.value = r
  form.value = { name: r.name, scope: r.scope, event: r.event, chans: channels(r.channel), receivers: r.receivers }
  formVisible.value = true
}

async function saveForm() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请填写策略名称')
    return
  }
  if (editing.value) {
    Object.assign(editing.value, {
      name: form.value.name.trim(),
      scope: form.value.scope,
      event: form.value.event,
      channel: form.value.chans.join('+') || '邮件',
      receivers: form.value.receivers,
    })
    await dataStore.save<DagAlarm>('dagAlarms', editing.value)
    ElMessage.success('告警策略已保存')
  } else {
    const nextSeq = alarms.value.reduce((mx, a) => {
      const n = Number(String(a.id).replace(/^\D+/, ''))
      return Number.isFinite(n) && n > mx ? n : mx
    }, 0) + 1
    const row: DagAlarm = {
      id: 'DA0' + String(nextSeq),
      name: form.value.name.trim(),
      scope: form.value.scope,
      event: form.value.event,
      channel: form.value.chans.join('+') || '邮件',
      receivers: form.value.receivers,
      status: 'enabled',
    }
    await dataStore.save<DagAlarm>('dagAlarms', row)
    ElMessage.success('告警策略已创建')
  }
  formVisible.value = false
  await reload()
}

/* ---- 启用 / 停用 ---- */
async function toggleStatus(r: DagAlarm) {
  r.status = r.status === 'enabled' ? 'disabled' : 'enabled'
  await dataStore.save<DagAlarm>('dagAlarms', r)
  ElMessage.success(r.status === 'enabled' ? '策略已启用' : '策略已停用')
  await reload()
}

/* ---- SLA 规则编辑（原型演示口径） ---- */
function tipSlaEdit() {
  ElMessage.info('SLA规则编辑（原型演示）：调整时限与升级策略')
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      :result-count="filteredAlarms.length"
      :total-count="alarms.length"
      placeholder="搜索策略/范围/事件"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头：标题 + 顶部操作按钮 -->
    <div class="card head-card">
      <div class="head-top">
        <div>
          <div class="head-title">调度告警与 SLA</div>
          <div class="head-sub">工作流失败/恢复/超时告警策略 + SLA 产出时限监控（今日达标 {{ slas.filter((s) => s.status === 'success').length }}/{{ slas.length }}）</div>
        </div>
        <span class="spacer" />
        <button class="tb-new" @click="openCreate">+ 新建告警策略</button>
      </div>
    </div>

    <!-- SLA 产出时限 -->
    <div class="card" style="padding:16px;margin-top:12px">
      <div class="tbl-toolbar">
        <span class="sec-head">SLA 产出时限</span>
        <span class="pill info">{{ slas.length }} 条规则</span>
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>SLA规则</th><th>工作流</th><th>产出时限</th><th>今日状态</th><th>今日情况</th><th>达标率</th><th style="width:90px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in slas" :key="r.id">
            <td><b class="mono">{{ r.id }}</b></td>
            <td>{{ r.wf }}</td>
            <td>{{ r.deadLine }}</td>
            <td><span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span></td>
            <td style="color:var(--text-2);font-size:12px">{{ r.today }}</td>
            <td><span style="font-size:11.5px;color:var(--text-2)">{{ r.history }}</span></td>
            <td><button class="op-btn" @click="tipSlaEdit">编辑</button></td>
          </tr>
        </tbody>
      </table>
      <div v-if="slas.length === 0" class="empty">暂无 SLA 规则</div>
    </div>

    <!-- 调度告警策略 -->
    <div class="card" style="padding:16px;margin-top:12px">
      <div class="tbl-toolbar">
        <span class="sec-head">调度告警策略</span>
        <span class="pill info">{{ filteredAlarms.length }} / {{ alarms.length }}</span>
        <span class="spacer" />
        <button class="tb-new" @click="openCreate">+ 新建告警策略</button>
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>策略</th><th>范围</th><th>触发事件</th><th>渠道</th><th>接收人</th><th>状态</th><th style="width:130px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filteredAlarms" :key="r.id">
            <td>
              <b>{{ r.name }}</b>
              <div style="color:var(--text-3);font-size:11px">{{ r.id }}</div>
            </td>
            <td>{{ r.scope }}</td>
            <td style="font-size:12px">{{ r.event }}</td>
            <td>
              <span v-for="c in channels(r.channel)" :key="c" class="pill info" style="margin-right:4px">{{ c }}</span>
            </td>
            <td style="font-size:12px">{{ r.receivers }}</td>
            <td><span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span></td>
            <td>
              <button class="op-btn primary" @click="openEdit(r)">编辑</button>
              <button class="op-btn" @click="toggleStatus(r)">{{ r.status === 'enabled' ? '停用' : '启用' }}</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filteredAlarms.length === 0" class="empty">未找到匹配的告警策略，请调整筛选条件</div>
    </div>

    <!-- 新建 / 编辑告警策略抽屉 -->
    <el-drawer v-model="formVisible" :title="editing ? '编辑告警策略 - ' + editing.name : '新建调度告警策略'" size="420px">
      <div class="form-grid">
        <label class="f-item">策略名称 *
          <input v-model="form.name" class="kw" style="width:100%" placeholder="如：工作流失败告警" />
        </label>
        <label class="f-item">生效范围
          <input v-model="form.scope" class="kw" style="width:100%" placeholder="如：所有工作流 / WF001/WF003" />
        </label>
        <label class="f-item">触发事件
          <select v-model="form.event" class="kw" style="width:100%">
            <option v-for="e in EVENT_OPTIONS" :key="e" :value="e">{{ e }}</option>
          </select>
        </label>
        <div class="f-item">通知渠道
          <div class="chan-row">
            <label v-for="c in CHAN_OPTIONS" :key="c" class="chan-item">
              <input v-model="form.chans" type="checkbox" :value="c" />
              <span>{{ c }}</span>
            </label>
          </div>
        </div>
        <label class="f-item">接收人
          <input v-model="form.receivers" class="kw" style="width:100%" placeholder="如：王工/任务负责人" />
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
.head-card{padding:16px}
.head-top{display:flex;align-items:center;gap:10px}
.head-title{font-size:16px;font-weight:700}
.head-sub{color:var(--text-3);font-size:12px;margin-top:2px}
.spacer{flex:1}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border);vertical-align:top}
.tbl tr:hover td{background:var(--primary-light)}
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.tbl-toolbar .spacer{flex:1}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none}
.kw:focus{border-color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease);flex-shrink:0}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.chan-row{display:flex;gap:12px}
.chan-item{display:flex;align-items:center;gap:5px;font-size:12.5px;cursor:pointer}
</style>
