<script setup lang="ts">
/**
 * M10 标准映射与合规（/std/mapping）
 * 对齐 prototype/assets/pages/m10-standard.js L470-544：
 * 统计卡片（总数/合规/不合规）+ 映射检核明细表（stdMappings）；
 * 顶部工具栏：全量检核、新增映射检核；行操作：整改（调整模型/扩展标准走审批/豁免留痕）、复检。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import { ElMessage } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import type { DbUser, Model, StdElement, StdMapping } from '../../services/types'

const router = useRouter()

const rows = ref<StdMapping[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ result: '' })
const resultOptions = [
  { v: 'pass', t: '合规' },
  { v: 'fail', t: '不合规' },
]

const modelCodes = ref<string[]>([])
const stdOptions = ref<StdElement[]>([])
const user = ref<DbUser>({ name: '王工', role: '' })

const passCount = computed(() => rows.value.filter((r) => r.result === 'pass').length)

/* ---- 左侧筛选面板 facets ---- */
const facets = computed<Facet[]>(() => [
  { key: 'result', label: '映射结果', options: resultOptions },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.result && r.result !== filters.value.result) return false
    if (!kw) return true
    return [r.table, r.field, r.stdName, r.stdId].some((s) => s.toLowerCase().includes(kw))
  })
})

async function reload() {
  // 展开为新数组触发响应式更新（save 原地修改数组，list 返回同一引用）
  rows.value = [...((await dataStore.list<StdMapping>('stdMappings')) ?? [])]
}

onMounted(async () => {
  await reload()
  const [models, stds, u] = await Promise.all([
    dataStore.list<Model>('models'),
    dataStore.list<StdElement>('stdElements'),
    dataStore.get<DbUser>('user'),
  ])
  modelCodes.value = models.map((m) => m.code)
  stdOptions.value = [...stds]
  if (u) user.value = u
})

/* ---- ST 徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}

/* ---- 时间 ---- */
function nowStr(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function todayCompact(): string {
  return nowStr().slice(0, 10).replace(/-/g, '')
}

/* ---- 全量检核 ---- */
const running = ref(false)
async function runAll() {
  if (running.value) return
  running.value = true
  ElMessage.info(`正在执行全量映射检核（${rows.value.length} 项）...`)
  await new Promise((res) => setTimeout(res, 800))
  for (const m of rows.value) {
    m.checkedAt = nowStr()
    await dataStore.save('stdMappings', m)
  }
  const fail = rows.value.length - passCount.value
  ElMessage({
    type: fail ? 'warning' : 'success',
    message: fail
      ? `检核完成：合规 ${passCount.value} 项，不合规 ${fail} 项（已生成整改工单）`
      : `检核完成：${passCount.value} 项全部合规`,
  })
  running.value = false
}

/* ---- 新增映射检核 ---- */
const createVisible = ref(false)
const createForm = ref({ table: '', field: '', stdId: '' })

function openCreate() {
  createForm.value = {
    table: modelCodes.value[0] ?? '',
    field: '',
    stdId: stdOptions.value[0]?.id ?? '',
  }
  createVisible.value = true
}

async function saveCreate() {
  const field = createForm.value.field.trim()
  if (!field) {
    ElMessage.warning('请填写字段名')
    return
  }
  if (!createForm.value.stdId) {
    ElMessage.warning('请选择关联标准')
    return
  }
  const std = stdOptions.value.find((s) => s.id === createForm.value.stdId)
  const nextSeq = rows.value.reduce((m, r) => {
    const n = Number(r.id.replace(/^\D+/, ''))
    return Number.isFinite(n) && n > m ? n : m
  }, 0) + 1
  const row: StdMapping = {
    id: 'SM' + String(nextSeq).padStart(3, '0'),
    table: createForm.value.table,
    field,
    stdId: createForm.value.stdId,
    stdName: std?.cn ?? '',
    result: 'pass',
    diff: '类型/精度一致',
    checkedAt: nowStr(),
  }
  rows.value.unshift(row)
  await dataStore.save('stdMappings', row)
  createVisible.value = false
  ElMessage.success('映射检核已创建并通过')
}

/* ---- 整改 ---- */
const fixVisible = ref(false)
const fixTarget = ref<StdMapping | null>(null)
const fixWay = ref<'alter' | 'extend' | 'ignore'>('alter')
const fixNote = ref('')

function openFix(r: StdMapping) {
  fixTarget.value = r
  fixWay.value = 'alter'
  fixNote.value = ''
  fixVisible.value = true
}

async function saveFix() {
  const m = fixTarget.value
  if (!m) return
  const note = fixNote.value.trim()
  if (!note) {
    ElMessage.warning('请填写整改说明')
    return
  }
  if (fixWay.value === 'extend') {
    const seq = String(rows.value.length + 1).padStart(2, '0')
    await dataStore.save('stdApprovals', {
      id: 'SA' + todayCompact() + '-' + seq,
      type: '数据元标准',
      target: `扩展标准 ${m.stdId}（整改触发）`,
      proposer: user.value.name,
      submitAt: nowStr(),
      flow: ['起草', '评审', '发布'],
      current: 1,
      status: 'review',
      opinion: '',
    })
    ElMessage.info('已发起标准变更审批，审批通过后复检')
  } else if (fixWay.value === 'ignore') {
    m.result = 'pass'
    m.diff = '豁免：' + note
    await dataStore.save('stdMappings', m)
    ElMessage.info('已豁免并留痕')
  } else {
    m.result = 'pass'
    m.diff = '已整改：' + note
    await dataStore.save('stdMappings', m)
    ElMessage.success('已生成DDL变更并整改完成，复检通过')
  }
  fixVisible.value = false
}

/* ---- 复检 ---- */
async function recheck(r: StdMapping) {
  ElMessage.info(`正在复检 ${r.table}.${r.field} ...`)
  await new Promise((res) => setTimeout(res, 600))
  r.result = 'pass'
  r.diff = '复检通过：类型/长度/格式约束一致'
  r.checkedAt = nowStr()
  await dataStore.save('stdMappings', r)
  ElMessage.success('复检通过')
}

function goStdElement() {
  router.push('/std/element')
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索表/字段/标准"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <!-- 统计卡片 -->
    <div class="stat-row">
      <div class="stat-card">
        <span class="type-icon" style="background:var(--primary)">⌇</span>
        <div><div class="stat-num">{{ rows.length }}</div><div class="stat-label">映射检核总数</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:var(--success)">✓</span>
        <div><div class="stat-num" style="color:var(--success)">{{ passCount }}</div><div class="stat-label">合规通过</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:var(--danger)">✗</span>
        <div><div class="stat-num" style="color:var(--danger)">{{ rows.length - passCount }}</div><div class="stat-label">不合规待整改</div></div>
      </div>
    </div>

    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">映射检核明细</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
        <button class="tb-new" :disabled="running" @click="runAll">▶ 全量检核</button>
        <button class="op-btn" @click="openCreate">＋ 新增映射检核</button>
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>模型字段</th><th>关联标准</th><th>检核结果</th><th>差异说明</th><th>检核时间</th><th style="width:120px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td><span class="mono"><b>{{ r.table }}.{{ r.field }}</b></span></td>
            <td><a @click="goStdElement"><span class="mono">{{ r.stdId }}</span> {{ r.stdName }}</a></td>
            <td>
              <span class="st" :class="stCls(r.result === 'pass' ? 'pass' : 'reject')">
                <span class="dot" />{{ stLabel(r.result === 'pass' ? 'pass' : 'reject') }}
              </span>
            </td>
            <td style="font-size:11.5px;color:var(--text-2)">{{ r.diff }}</td>
            <td style="color:var(--text-2)">{{ r.checkedAt }}</td>
            <td>
              <button class="op-btn" @click="openFix(r)">整改</button>
              <button class="op-btn primary" @click="recheck(r)">复检</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="filtered.length === 0" class="empty">未找到匹配的映射检核，请调整筛选条件</div>
    </div>

    <!-- 新增映射检核抽屉 -->
    <el-drawer v-model="createVisible" title="新增映射检核" size="440px">
      <div class="form-grid">
        <label class="f-item">模型表
          <select v-model="createForm.table">
            <option v-for="c in modelCodes" :key="c" :value="c">{{ c }}</option>
          </select>
        </label>
        <label class="f-item">字段名
          <input v-model="createForm.field" placeholder="如：pay_channel" />
        </label>
        <label class="f-item">关联标准
          <select v-model="createForm.stdId">
            <option v-for="s in stdOptions" :key="s.id" :value="s.id">{{ s.id }} {{ s.cn }}</option>
          </select>
        </label>
      </div>
      <div class="hint">保存后立即执行一次映射检核（类型/长度/格式约束比对）。</div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveCreate">保存</button>
        <button class="op-btn" @click="createVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 整改抽屉 -->
    <el-drawer v-model="fixVisible" :title="fixTarget ? '整改 - ' + fixTarget.table + '.' + fixTarget.field : ''" size="440px">
      <template v-if="fixTarget">
        <div class="diff-banner">⚠ 差异：{{ fixTarget.diff }}</div>
        <div class="form-grid" style="margin-top:12px">
          <div class="f-item">整改方式
            <label class="radio-line">
              <input v-model="fixWay" type="radio" value="alter" /> 调整模型字段（生成DDL变更）
            </label>
            <label class="radio-line">
              <input v-model="fixWay" type="radio" value="extend" /> 扩展标准（走标准变更审批）
            </label>
            <label class="radio-line">
              <input v-model="fixWay" type="radio" value="ignore" /> 豁免（记录理由，审计留痕）
            </label>
          </div>
          <label class="f-item">整改说明
            <textarea v-model="fixNote" rows="3" style="resize:vertical" placeholder="说明整改内容与影响" />
          </label>
        </div>
        <div style="margin-top:16px;display:flex;gap:8px">
          <button class="tb-new" @click="saveFix">提交整改</button>
          <button class="op-btn" @click="fixVisible = false">取消</button>
        </div>
      </template>
    </el-drawer>
    </div>
  </div>
</template>

<style scoped>
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}
.stat-card{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:14px 16px;box-shadow:var(--shadow)}
.stat-num{font-size:24px;font-weight:700;line-height:1.2;letter-spacing:-.3px;font-variant-numeric:tabular-nums}
.stat-label{font-size:12.5px;color:var(--text-2);margin-top:2px}
.type-icon{width:28px;height:28px;border-radius:var(--radius);display:flex;align-items:center;justify-content:center;color:#fff;font-size:13px;flex-shrink:0}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:190px;outline:none;transition:all var(--dur-fast) var(--ease)}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2);transition:all var(--dur-fast) var(--ease)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.tb-new:disabled{opacity:.6;cursor:not-allowed}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2);transition:all var(--dur-fast) var(--ease)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.f-item input,.f-item select,.f-item textarea{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;outline:none;font-family:inherit;background:#fff;color:var(--text);transition:all var(--dur-fast) var(--ease)}
.f-item input:focus,.f-item select:focus,.f-item textarea:focus{border-color:var(--primary)}
.radio-line{display:flex;gap:6px;align-items:center;font-size:12.5px;color:var(--text);margin-bottom:6px}
.diff-banner{background:var(--warn-bg);color:var(--warn);border-radius:var(--radius);padding:9px 11px;font-size:12.5px}
.hint{font-size:11.5px;color:var(--text-3);margin-top:12px;line-height:1.6}
</style>
