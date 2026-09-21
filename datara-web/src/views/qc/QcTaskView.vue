<script setup lang="ts">
/**
 * M07 质量检查任务（/qc/task）
 * 原型对齐：prototype/assets/pages/m07-quality.js L155-227（#/qc/task + A.qt* 系列）
 * 任务表格 + 顶部工具栏「+ 新建检查任务」；行操作：立即执行（结果时间线弹窗）/
 * 编排规则（勾选规则联动 linkTask）/ 编辑 / 启停用 / 删除。
 * 数据：qcTasks（读写）/ qcRules（编排联动写入 linkTask）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { QcTask, QcRule, QcDim } from '../../services/types'

const tasks = ref<QcTask[]>([])
const rules = ref<QcRule[]>([])
const dims = ref<QcDim[]>([])

onMounted(async () => {
  await reload()
  dims.value = [...((await dataStore.list<QcDim>('qcDims')) ?? [])]
})

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发响应式更新。
  tasks.value = [...((await dataStore.list<QcTask>('qcTasks')) ?? [])]
  rules.value = [...((await dataStore.list<QcRule>('qcRules')) ?? [])]
}

const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '', lastResult: '', cron: '' })

const facets = computed<Facet[]>(() => {
  const crons = [...new Set(tasks.value.map((t) => t.cron).filter((c) => c && c !== '-'))]
  return [
    { key: 'status', label: '状态', options: [{ v: 'enabled', t: '启用' }, { v: 'disabled', t: '停用' }] },
    { key: 'lastResult', label: '最近结果', options: [{ v: 'success', t: '成功' }, { v: 'fail', t: '失败' }] },
    { key: 'cron', label: '调度周期', options: crons.map((c) => ({ v: c, t: c })) },
  ]
})

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return tasks.value.filter((t) => {
    if (filters.value.status && t.status !== filters.value.status) return false
    if (filters.value.lastResult && t.lastResult !== filters.value.lastResult) return false
    if (filters.value.cron && t.cron !== filters.value.cron) return false
    if (!kw) return true
    return [t.id, t.name].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 状态徽标 ---- */
const EXTRA_ST: Record<string, { label: string; cls: string }> = {
  fail: { label: '失败', cls: 'st-red' },
}
function stCls(s: string): string {
  return ST[s]?.cls ?? EXTRA_ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? EXTRA_ST[s]?.label ?? s
}
function dimTagStyle(code: string): Record<string, string> {
  const d = dims.value.find((x) => x.code === code)
  const c = d?.color ?? '#1668dc'
  return { background: c + '18', color: c }
}
function dimName(code: string): string {
  return dims.value.find((x) => x.code === code)?.name ?? code
}

function today(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/* ---- 新建 / 编辑任务 ---- */
const formVisible = ref(false)
const editing = ref<QcTask | null>(null)
const drawerTitle = computed(() => (editing.value ? `编辑检查任务 - ${editing.value.name}` : '新建检查任务'))
const form = ref({ name: '', cron: '0 0 3 * * ?', link: false })

function openCreate() {
  editing.value = null
  form.value = { name: '', cron: '0 0 3 * * ?', link: false }
  formVisible.value = true
}

function openEdit(t: QcTask) {
  editing.value = t
  form.value = { name: t.name, cron: t.cron, link: !!t.linkEtl && t.linkEtl !== '否' }
  formVisible.value = true
}

function nextTaskId(): string {
  let max = 0
  for (const t of tasks.value) {
    const n = Number(t.id.replace(/\D/g, ''))
    if (Number.isFinite(n) && n > max) max = n
  }
  return 'QT' + String(max + 1).padStart(3, '0')
}

async function saveForm() {
  const name = form.value.name.trim()
  if (!name) {
    ElMessage.warning('请填写任务名称')
    return
  }
  if (editing.value) {
    // 原型对齐：编辑仅保存名称与 Cron，联动方式不变
    editing.value.name = name
    editing.value.cron = form.value.cron.trim() || '0 0 3 * * ?'
    await dataStore.save('qcTasks', editing.value)
    ElMessage.success('检查任务已保存')
  } else {
    const task: QcTask = {
      id: nextTaskId(), name, tables: 0, rules: 0, cron: form.value.cron.trim() || '0 0 3 * * ?',
      linkEtl: form.value.link ? '是（新建联动）' : '否', status: 'enabled', lastRun: '-', lastResult: '-',
    }
    await dataStore.save('qcTasks', task)
    ElMessage.success('检查任务已创建，请编排规则')
  }
  formVisible.value = false
  await reload()
}

/* ---- 立即执行 ---- */
const runVisible = ref(false)
const runInfo = ref<{ name: string; rules: number; bad: boolean; lastRun: string } | null>(null)

function runTask(t: QcTask) {
  ElMessage.info(`正在执行检查任务「${t.name}」...`)
  window.setTimeout(async () => {
    const bad = t.lastResult === 'fail'
    t.lastRun = `${today()} 23:05`
    t.lastResult = bad ? 'fail' : 'success'
    await dataStore.save('qcTasks', t)
    runInfo.value = { name: t.name, rules: t.rules, bad, lastRun: t.lastRun }
    runVisible.value = true
    if (bad) ElMessage.warning(`任务「${t.name}」执行完成：存在失败规则，已生成异常单并阻断下游`)
    else ElMessage.success(`任务「${t.name}」执行完成：全部规则通过`)
    await reload()
  }, 1200)
}

/* ---- 编排规则 ---- */
const linkVisible = ref(false)
const linkTarget = ref<QcTask | null>(null)
const checkedIds = ref<string[]>([])

function openRules(t: QcTask) {
  linkTarget.value = t
  checkedIds.value = rules.value.filter((r) => r.linkTask === t.id).map((r) => r.id)
  linkVisible.value = true
}

async function saveLinks() {
  const d = linkTarget.value
  if (!d) return
  const vals = new Set(checkedIds.value)
  for (const r of rules.value) {
    const want = vals.has(r.id)
    if (want && r.linkTask !== d.id) {
      r.linkTask = d.id
      await dataStore.save('qcRules', r)
    } else if (!want && r.linkTask === d.id) {
      r.linkTask = '-'
      await dataStore.save('qcRules', r)
    }
  }
  d.rules = checkedIds.value.length
  await dataStore.save('qcTasks', d)
  ElMessage.success(`已编排 ${checkedIds.value.length} 条规则`)
  linkVisible.value = false
  await reload()
}

/* ---- 启停用 / 删除 ---- */
async function toggleStatus(t: QcTask) {
  t.status = t.status === 'enabled' ? 'disabled' : 'enabled'
  await dataStore.save('qcTasks', t)
  ElMessage.success(t.status === 'enabled' ? `任务「${t.name}」已启用` : `任务「${t.name}」已停用`)
}

async function removeTask(t: QcTask) {
  try {
    await ElMessageBox.confirm(`确认删除检查任务「${t.name}」？该操作不可恢复。`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await dataStore.remove('qcTasks', t.id)
  ElMessage.success('检查任务已删除')
  await reload()
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索任务"
      :result-count="filtered.length"
      :total-count="tasks.length"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部工具栏按钮 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">质量检查任务</div>
        <div class="ph-desc">规则编排执行：支持独立调度与 ETL 前置联动（产出即检核），失败可阻断工作流下游节点</div>
      </div>
      <div class="ph-acts">
        <button class="tb-new" @click="openCreate">+ 新建检查任务</button>
      </div>
    </div>

    <!-- 检查任务列表 -->
    <div class="card panel">
      <div class="tbl-toolbar">
        <span class="sec-head">检查任务列表</span>
        <span class="pill info">{{ filtered.length }} / {{ tasks.length }}</span>
        <span class="spacer" />
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>任务</th><th>范围</th><th>调度</th><th>ETL联动</th><th>最近执行</th><th>结果</th><th>状态</th>
            <th style="width:250px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in filtered" :key="t.id">
            <td>
              <b>{{ t.name }}</b>
              <div style="font-size:11px;color:var(--text-3)">{{ t.id }}</div>
            </td>
            <td>表 {{ t.tables }} · 规则 {{ t.rules }}</td>
            <td><span class="mono" style="font-size:11.5px">{{ t.cron }}</span></td>
            <td style="font-size:12px">{{ t.linkEtl }}</td>
            <td style="color:var(--text-2)">{{ t.lastRun }}</td>
            <td>
              <span v-if="t.lastResult !== '-'" class="st" :class="stCls(t.lastResult)"><span class="dot" />{{ stLabel(t.lastResult) }}</span>
              <span v-else style="color:var(--text-3)">-</span>
            </td>
            <td><span class="st" :class="stCls(t.status)"><span class="dot" />{{ stLabel(t.status) }}</span></td>
            <td>
              <button class="op-btn primary" @click="runTask(t)">立即执行</button>
              <button class="op-btn" @click="openRules(t)">编排规则</button>
              <button class="op-btn" @click="openEdit(t)">编辑</button>
              <button class="op-btn" @click="toggleStatus(t)">{{ t.status === 'enabled' ? '停用' : '启用' }}</button>
              <button class="op-btn danger" @click="removeTask(t)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的检查任务</div>
    </div>

    <!-- 执行结果弹窗（时间线） -->
    <el-dialog v-model="runVisible" :title="runInfo ? `执行结果 - ${runInfo.name}` : ''" width="520px">
      <template v-if="runInfo">
        <div class="tl">
          <div class="tl-item">
            <span class="tl-dot" />
            <div class="tl-body">
              <b>任务启动</b><span class="tl-time">23:05:00</span>
              <div>调度触发，加载规则 {{ runInfo.rules }} 条</div>
            </div>
          </div>
          <div class="tl-item">
            <span class="tl-dot" />
            <div class="tl-body">
              <b>规则执行</b><span class="tl-time">23:05:02</span>
              <div>逐条执行 SQL 检核，强规则优先</div>
            </div>
          </div>
          <div class="tl-item">
            <span class="tl-dot" :class="runInfo.bad ? 'err' : 'ok'" />
            <div class="tl-body" :class="runInfo.bad ? 'txt-err' : 'txt-ok'">
              <b>结果判定</b><span class="tl-time">23:05:08</span>
              <div>{{ runInfo.bad ? 'QC-R-012 失败：异常 12 行 → 已生成异常单 QE20260912-001，弱规则通过' : '全部规则通过' }}</div>
            </div>
          </div>
          <div class="tl-item">
            <span class="tl-dot" :class="runInfo.bad ? 'err' : 'ok'" />
            <div class="tl-body" :class="runInfo.bad ? 'txt-err' : 'txt-ok'">
              <b>{{ runInfo.bad ? '下游阻断' : '下游放行' }}</b><span class="tl-time">23:05:09</span>
              <div>{{ runInfo.bad ? '强规则失败，联动 ETL 下游节点已阻断，并触发告警（QA01 邮件+短信）' : '检查通过，允许下游任务继续' }}</div>
            </div>
          </div>
        </div>
        <div class="lock-tip">最近执行：{{ runInfo.lastRun }} 23:05。试跑结果不影响调度状态，仅更新最近执行与结果。</div>
      </template>
    </el-dialog>

    <!-- 编排规则抽屉 -->
    <el-drawer v-model="linkVisible" :title="linkTarget ? `编排规则 - ${linkTarget.name}` : ''" size="480px">
      <div class="lock-tip" style="margin:0 0 10px">勾选需要纳入本任务的规则；强规则失败将阻断联动 ETL 下游。</div>
      <label v-for="r in rules" :key="r.id" class="rule-line">
        <input v-model="checkedIds" type="checkbox" :value="r.id" />
        <span class="tag" :style="dimTagStyle(r.dim)">{{ dimName(r.dim) }}</span>
        <span style="font-size:12px">{{ r.name }}</span>
        <span class="pill" :class="r.level === '强规则' ? 'err' : 'warn'" style="margin-left:auto">{{ r.level }}</span>
      </label>
      <div style="margin-top:14px;display:flex;gap:8px">
        <button class="tb-new" @click="saveLinks">保存（{{ checkedIds.length }} 条）</button>
        <button class="op-btn" @click="linkVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 新建 / 编辑抽屉 -->
    <el-drawer v-model="formVisible" :title="drawerTitle" size="440px">
      <div class="form-grid">
        <label class="f-item">任务名称 *
          <input v-model="form.name" class="kw" style="width:100%" placeholder="如：ODS层日检任务" />
        </label>
        <label class="f-item">Cron 表达式
          <input v-model="form.cron" class="kw mono" style="width:100%" placeholder="0 0 3 * * ?" />
        </label>
        <label class="f-item switch-line">
          <span style="display:flex;gap:8px;align-items:center">
            <input v-model="form.link" type="checkbox" />
            ETL 前置联动（产出即检核，失败阻断下游）
          </span>
          <span style="font-size:11px;color:var(--text-3)">选择后在 ETL 任务中挂载为前置校验节点</span>
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
.pill{display:inline-flex;align-items:center;padding:1px 9px;border-radius:var(--radius-lg);font-size:11px;font-weight:500}
.pill.err{background:var(--danger-bg);color:var(--danger)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.info{background:var(--info-bg);color:var(--info)}
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
.tag{display:inline-block;border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600}
.lock-tip{border-left:3px solid var(--warn);background:var(--warn-bg);color:var(--warn);font-size:11.5px;padding:7px 10px;border-radius:0 7px 7px 0}
/* 时间线 */
.tl{display:flex;flex-direction:column}
.tl-item{display:flex;gap:10px;padding:7px 0}
.tl-dot{width:9px;height:9px;border-radius:50%;background:var(--border-strong);margin-top:6px;flex-shrink:0}
.tl-dot.ok{background:var(--success)}
.tl-dot.err{background:var(--danger)}
.tl-body{font-size:12.5px;color:var(--text-2);border-bottom:1px dashed var(--border);padding-bottom:7px;flex:1}
.tl-body b{color:var(--text)}
.tl-time{margin-left:8px;font-size:11px;color:var(--text-3)}
.txt-ok b{color:var(--success)}
.txt-err b{color:var(--danger)}
/* 规则勾选行 */
.rule-line{display:flex;gap:8px;align-items:center;padding:8px 10px;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:7px;cursor:pointer}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.switch-line span:first-child{font-weight:600;color:var(--text)}
</style>
