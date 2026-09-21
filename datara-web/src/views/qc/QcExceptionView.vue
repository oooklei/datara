<script setup lang="ts">
/**
 * M07 异常数据核查（/qc/exception）
 * 原型对齐：prototype/assets/pages/m07-quality.js L230-302（#/qc/exception + A.qe* 系列）
 * 状态流转图 + 统计卡（待处理/已修复/已忽略）+ 异常单表格；顶部工具栏「隔离区查看」；
 * 行操作：样本（动态样本表）+ 待处理单的 修复（生成清理SQL等）/ 忽略（豁免留痕）。
 * 数据：qcExceptions（读写：status 流转 pending → fixed / ignored）。
 * 新增（设计方案第7章 L539-598）：下载三格式（CSV/Excel/JSON，范围可选）、异常统计与趋势
 * （总体/分类趋势 + 纯函数异常判断：疑似处理异常/疑似业务异常，仅提示、人工处理）、
 * 保留策略（N 天可配置 + 到期自动清理开关 + 表格「剩余保留」列）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { QcException } from '../../services/types'

const rows = ref<QcException[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '', dim: '' })

const facets = computed<Facet[]>(() => {
  const dimOpts = [...new Set(rows.value.map((e) => e.dim).filter(Boolean))].map((d) => ({ v: d, t: d }))
  return [
    { key: 'status', label: '状态', options: [{ v: 'pending', t: '待处理' }, { v: 'fixed', t: '已修复' }, { v: 'ignored', t: '已忽略' }] },
    { key: 'dim', label: '质量维度', options: dimOpts },
  ]
})

onMounted(async () => {
  await reload()
  // 新增：加载规则名（分类趋势「按规则」取前4个）与保留策略配置
  ruleNames.value = (await dataStore.list<{ name: string }>('qcRules')).map((r) => r.name).slice(0, 4)
  await loadRetention()
})

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发响应式更新。
  rows.value = [...((await dataStore.list<QcException>('qcExceptions')) ?? [])]
}

/* ---- 状态流转图（静态展示，对齐原型 UI.stateFlow） ---- */
const FLOW = [
  { k: 'pending', t: '待处理', d: '检查失败 · 待定责' },
  { k: 'fixing', t: '整改中', d: '清理SQL · 关联任务' },
  { k: 'done', t: '已处置', d: '已修复 / 豁免忽略' },
  { k: 'closed', t: '已归档', d: '复检通过 · 闭环留痕' },
]

/* ---- 统计卡 ---- */
const pendingCnt = computed(() => rows.value.filter((e) => e.status === 'pending').length)
const fixedCnt = computed(() => rows.value.filter((e) => e.status === 'fixed').length)
const ignoredCnt = computed(() => rows.value.filter((e) => e.status === 'ignored').length)

/* ---- 搜索 / 筛选 ---- */
const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((e) => {
    if (filters.value.status && e.status !== filters.value.status) return false
    if (filters.value.dim && e.dim !== filters.value.dim) return false
    if (!kw) return true
    return [e.id, e.ruleName, e.table].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 状态徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}

/* ---- 异常样本 ---- */
const sampleVisible = ref(false)
const sampleTarget = ref<QcException | null>(null)
const sampleKeys = computed(() => {
  const s = sampleTarget.value?.sample ?? []
  return s.length ? Object.keys(s[0]) : []
})
function sampleVal(v: unknown): string {
  return v == null ? 'NULL' : String(v)
}

function openSample(e: QcException) {
  sampleTarget.value = e
  sampleVisible.value = true
}

/* ---- 修复 ---- */
const fixVisible = ref(false)
const fixTarget = ref<QcException | null>(null)
const fixWay = ref('clean')
const fixNote = ref('')

const FIX_WAYS = [
  { v: 'clean', t: '生成清理SQL（删除/订正异常行）' },
  { v: 'patch', t: '回补源数据后重跑分区' },
  { v: 'transfer', t: '流转修复工单给负责人' },
]

function openFix(e: QcException) {
  fixTarget.value = e
  fixWay.value = 'clean'
  fixNote.value = ''
  fixVisible.value = true
}

function wayText(v: string): string {
  return v === 'clean' ? '清理SQL' : v === 'patch' ? '回补重跑' : '工单流转'
}

async function saveFix() {
  const e = fixTarget.value
  if (!e) return
  if (!fixNote.value.trim()) {
    ElMessage.warning('请填写修复说明')
    return
  }
  e.status = 'fixed'
  await dataStore.save('qcExceptions', e)
  ElMessage.success(`修复完成：异常 ${e.cnt} 行已处理（${wayText(fixWay.value)}），状态更新为「已修复」，已通知报告重算`)
  fixVisible.value = false
  await reload()
}

/* ---- 忽略（豁免留痕） ---- */
const ignoreVisible = ref(false)
const ignoreTarget = ref<QcException | null>(null)
const ignoreReason = ref('')

function openIgnore(e: QcException) {
  ignoreTarget.value = e
  ignoreReason.value = ''
  ignoreVisible.value = true
}

async function saveIgnore() {
  const e = ignoreTarget.value
  if (!e) return
  if (!ignoreReason.value.trim()) {
    ElMessage.warning('请填写忽略理由')
    return
  }
  e.status = 'ignored'
  await dataStore.save('qcExceptions', e)
  ElMessage.info('异常已忽略并留痕（下次检查不再生成同类异常单）')
  ignoreVisible.value = false
  await reload()
}

/* ==================== 新增一：下载三格式（CSV / Excel / JSON） ====================
 * 方案沿用 StdElementView：Excel = BOM + HTML table 的 .xls；CSV = Blob + a[download]。
 * 下载范围：全部异常 / 当前筛选结果；内容：样本明细（原始数据 + 错误原因 + 检查时间），
 * 无样本明细时降级为异常单汇总字段（异常ID/来源表/来源字段/规则/错误类型/数量/检查时间/状态）并在 CSV 头注明。 */
type ExportFormat = 'csv' | 'excel' | 'json'
const dlScope = ref('all') // 'all'=全部异常 | 'filtered'=当前筛选结果
const exportList = computed<QcException[]>(() => (dlScope.value === 'all' ? rows.value : filtered.value))

function csvCell(v: unknown): string {
  const s = v == null ? '' : String(v)
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

function escHtml(c: string | number): string {
  return String(c).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function dateStamp(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url) // 及时释放对象 URL，避免内存泄漏
}

const REASON_KEYS = ['desc', 'reason', '错误原因']
const EXPORT_SUMMARY_HEADS = ['异常ID', '来源表', '来源字段', '规则', '错误类型', '数量', '检查时间', '状态']

/* 样本明细列 = 固定上下文列 + 各异常单样本字段并集（错误原因字段剔除后单独成列） */
const exportSampleKeys = computed<string[]>(() => {
  const keys: string[] = []
  for (const e of exportList.value) {
    for (const k of Object.keys(e.sample?.[0] ?? {})) {
      if (!keys.includes(k) && !REASON_KEYS.includes(k)) keys.push(k)
    }
  }
  return keys
})

function reasonOf(s: Record<string, unknown>): string {
  for (const k of REASON_KEYS) {
    if (s[k] != null && s[k] !== '') return String(s[k])
  }
  return '-'
}

/* 组装导出矩阵：mode=detail 样本明细（每条样本一行）；mode=summary 异常单汇总（无样本明细时降级） */
function buildExport(): { mode: 'detail' | 'summary'; heads: string[]; body: (string | number)[][] } {
  const list = exportList.value
  if (list.every((e) => (e.sample?.length ?? 0) > 0)) {
    const heads = ['异常ID', '来源表', '来源字段', '规则', '检查时间', '状态', ...exportSampleKeys.value, '错误原因']
    const body = list.flatMap((e) =>
      (e.sample ?? []).map((s) => [
        e.id, e.table, e.field, e.ruleName, e.dt, stLabel(e.status),
        ...exportSampleKeys.value.map((k) => (s[k] == null ? 'NULL' : (s[k] as string | number))),
        reasonOf(s),
      ]),
    )
    return { mode: 'detail', heads, body }
  }
  const body = list.map((e) => [e.id, e.table, e.field, e.ruleName, e.dim, e.cnt, e.dt, stLabel(e.status)])
  return { mode: 'summary', heads: EXPORT_SUMMARY_HEADS, body }
}

function exportRows(format: ExportFormat) {
  if (!exportList.value.length) {
    ElMessage.warning('没有可下载的异常数据')
    return
  }
  const { mode, heads, body } = buildExport()
  const name = `qc_exceptions_${dateStamp(new Date())}_${dlScope.value === 'all' ? 'all' : 'filtered'}`
  if (format === 'csv') {
    // 需求：无样本明细、导出汇总字段时在 CSV 头注明口径
    const note = mode === 'summary'
      ? '# 注：当前异常单无样本明细，以下为异常单汇总字段（异常ID/来源表/来源字段/规则/错误类型/数量/检查时间/状态）\n'
      : ''
    const lines = [note + heads.map(csvCell).join(','), ...body.map((r) => r.map(csvCell).join(','))]
    triggerDownload(new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8' }), `${name}.csv`)
  } else if (format === 'excel') {
    const head = `<tr>${heads.map((h) => `<th>${escHtml(h)}</th>`).join('')}</tr>`
    const trs = body.map((r) => `<tr>${r.map((c) => `<td>${escHtml(c)}</td>`).join('')}</tr>`).join('')
    triggerDownload(new Blob(['\ufeff' + `<table>${head}${trs}</table>`], { type: 'application/vnd.ms-excel' }), `${name}.xls`)
  } else {
    const payload = {
      exportedAt: new Date().toLocaleString(),
      scope: dlScope.value === 'all' ? '全部异常' : '当前筛选结果',
      mode: mode === 'detail' ? '样本明细（原始数据+错误原因+检查时间）' : '异常单汇总',
      count: body.length,
      rows: body.map((r) => Object.fromEntries(heads.map((h, i) => [h, r[i]]))),
    }
    triggerDownload(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' }), `${name}.json`)
  }
  ElMessage.success(`已导出 ${body.length} 行（${heads.join(' / ')}）`)
}

/* el-dropdown 的 command 回调（string | number | object）→ 收敛到三种格式 */
function onExportCmd(cmd: string | number | object) {
  if (cmd === 'csv' || cmd === 'excel' || cmd === 'json') exportRows(cmd)
}

/* ==================== 新增二：异常统计与趋势（确定性写死数据 + 纯函数判断） ==================== */

/* 近 N 日日期标签（末日 = 今天，MM-DD） */
function lastNDayLabels(n: number): string[] {
  const out: string[] = []
  const now = new Date()
  for (let i = n - 1; i >= 0; i--) {
    const t = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i)
    out.push(`${String(t.getMonth() + 1).padStart(2, '0')}-${String(t.getDate()).padStart(2, '0')}`)
  }
  return out
}
const allDayLabels = lastNDayLabels(30) // 复用同一数组切片，避免重复生成（计算优化）
const trendDays = allDayLabels
const groupDayLabels = allDayLabels.slice(23)

/* 近30日总体每日异常量：前23日为确定性基线波动（240~389，落在 150~420 区间），
 * 末7日为写死值且与下方两类分类趋势逐日合计一致；末日叠加「空值类激增」构成可解释的判断场景 */
const TREND30: number[] = (() => {
  const base = Array.from({ length: 23 }, (_, i) => 240 + ((i * 37) % 90) + (i % 7 === 6 ? 60 : 0))
  return [...base, 281, 318, 265, 302, 309, 286, 503]
})()
const trendMax = Math.max(...TREND30)

/* 近7日按错误类型分组（各日四类之和 = 总体趋势对应日数值）；「空值」末日激增 */
const TYPE_GROUPS: { name: string; color: string; vals: number[] }[] = [
  { name: '空值', color: '#1668dc', vals: [128, 141, 119, 136, 125, 130, 320] },
  { name: '重复', color: '#d97706', vals: [72, 65, 78, 70, 74, 68, 71] },
  { name: '范围', color: '#16a34a', vals: [56, 88, 48, 76, 90, 68, 82] },
  { name: '格式', color: '#7c3aed', vals: [25, 24, 20, 20, 20, 20, 30] },
]

/* 近7日按规则分组：规则名取质量检查模块前4个（onMounted 加载），数值模板按「空值类规则优先激增」轮转对齐；
 * 模板仅在各规则间置换、不改变日合计，因此逐日合计与总体趋势一致 */
const RULE_TEMPLATES: number[][] = [
  [128, 141, 119, 136, 125, 130, 320],
  [72, 65, 78, 70, 74, 68, 82],
  [56, 88, 48, 76, 90, 68, 61],
  [25, 24, 20, 20, 20, 20, 40],
]
const GROUP_COLORS = ['#1668dc', '#d97706', '#16a34a', '#7c3aed']
const ruleNames = ref<string[]>([])
const ruleGroups = computed<{ name: string; color: string; vals: number[] }[]>(() => {
  const names = ruleNames.value.length >= 4
    ? ruleNames.value.slice(0, 4)
    : ruleNames.value.length ? ruleNames.value : ['手机号非空检查', '支付金额范围检查', '身份证格式校验', '邮箱格式校验']
  const spikeAt = Math.max(0, names.findIndex((n) => n.includes('空')))
  return names.map((name, i) => ({ name, color: GROUP_COLORS[i % GROUP_COLORS.length], vals: RULE_TEMPLATES[(i - spikeAt + 4) % 4] }))
})

/* 分类维度切换：按错误类型 / 按规则 */
const groupDim = ref('type')
const activeGroups = computed(() => (groupDim.value === 'type' ? TYPE_GROUPS : ruleGroups.value))
const groupMax = computed(() => Math.max(1, ...activeGroups.value.flatMap((g) => g.vals)))

/**
 * 趋势判断纯函数（确定性、可解释）：
 * 输入 total=总体每日异常量序列（末位为当日）；groups=各分类近7日序列（末位为当日）。
 * 规则1：当日总量 > 前7日均值×2 → 整批同向激增 →「疑似处理异常」（同步/调度故障，建议检查上游任务）；
 * 规则2：总量平稳但单一分类当日 > 自身前6日均值×2 →「疑似业务异常」（上游业务变化，建议联系业务确认）。
 * 输出 {level, label, advice}；多分类同时激增时取倍数最高者（并列取先出现者）。
 */
interface TrendVerdict { level: 'normal' | 'warn' | 'danger'; label: string; advice: string }
function judgeTrend(total: number[], groups: { name: string; vals: number[] }[]): TrendVerdict {
  const today = total[total.length - 1]
  const prev7 = total.slice(-8, -1)
  const base = prev7.reduce((s, v) => s + v, 0) / (prev7.length || 1)
  if (base > 0 && today > base * 2) {
    return { level: 'danger', label: '疑似处理异常', advice: `当日异常量 ${today} 超过前7日均值（${Math.round(base)}）的2倍，整批同向激增，可能是同步/调度故障，建议检查上游任务` }
  }
  let hit: { name: string; ratio: number; today: number; base: number } | null = null
  for (const g of groups) {
    const gToday = g.vals[g.vals.length - 1]
    const gPrev = g.vals.slice(0, -1)
    const gBase = gPrev.reduce((s, v) => s + v, 0) / (gPrev.length || 1)
    if (gBase > 0 && gToday > gBase * 2) {
      const ratio = gToday / gBase
      if (!hit || ratio > hit.ratio) hit = { name: g.name, ratio, today: gToday, base: gBase }
    }
  }
  if (hit) {
    return { level: 'warn', label: '疑似业务异常', advice: `分类「${hit.name}」当日异常量 ${hit.today} 为自身前6日均值（${Math.round(hit.base)}）的 ${hit.ratio.toFixed(1)} 倍，而总体趋势平稳，疑似上游业务变化，建议联系业务方确认` }
  }
  return { level: 'normal', label: '波动正常', advice: '总体与各分类异常量均处于历史波动区间，未发现异常' }
}
/* 合并两个维度分组一并判断（总体判定优先，分类判定其次） */
const verdict = computed<TrendVerdict>(() => judgeTrend(TREND30, [...TYPE_GROUPS, ...ruleGroups.value]))

/* 异常统计三小表：按字段 / 按规则 / 按错误类型（dim 质量维度），实时聚合自页面异常单（Map 去重计数，避免重复计算） */
function aggBy(list: QcException[], keyFn: (e: QcException) => string): { name: string; orders: number; cnt: number }[] {
  const m = new Map<string, { name: string; orders: number; cnt: number }>()
  for (const e of list) {
    const k = keyFn(e) || '-'
    const it = m.get(k)
    if (it) { it.orders += 1; it.cnt += e.cnt } else { m.set(k, { name: k, orders: 1, cnt: e.cnt }) }
  }
  return [...m.values()].sort((a, b) => b.cnt - a.cnt)
}
const statByField = computed(() => aggBy(rows.value, (e) => `${e.table}.${e.field}`))
const statByRule = computed(() => aggBy(rows.value, (e) => e.ruleName))
const statByDim = computed(() => aggBy(rows.value, (e) => e.dim))
const miniTables = computed(() => [
  { title: '按字段统计', list: statByField.value },
  { title: '按规则统计', list: statByRule.value },
  { title: '按错误类型统计', list: statByDim.value },
])

/* ==================== 新增三：异常数据保留策略（N 天可配置 + 到期自动清理开关） ====================
 * 读写走 dataStore 集合 qcRetention（seed 为 {days:30, autoClean:true}，需求结构一致）：
 * 保存为带固定 id 的配置对象原地替换；读取用 list 取最新一条对象行，兼容数字行兜底 */
interface KeepCfg { days: number; autoClean: boolean }
const keepDays = ref<number | string>(30)
const autoClean = ref(true)

async function loadRetention() {
  const list = await dataStore.list<unknown>('qcRetention')
  for (let i = list.length - 1; i >= 0; i--) {
    const v = list[i]
    if (v && typeof v === 'object') {
      const o = v as Partial<KeepCfg>
      keepDays.value = Math.max(1, Math.round(Number(o.days) || 30))
      autoClean.value = o.autoClean !== false
      return
    }
  }
  const num = list.find((v): v is number => typeof v === 'number')
  if (num && num > 0) keepDays.value = num
}

async function saveRetention() {
  const days = Math.round(Number(keepDays.value))
  if (!Number.isFinite(days) || days < 1) {
    ElMessage.warning('保留天数需为 ≥ 1 的整数')
    return
  }
  keepDays.value = days
  // 带固定 id 保存：dataStore.save 按 id 原地替换，重复保存不会使集合无限增长（内存优化）
  const cfg: KeepCfg & { id: string } = { id: 'qc_keep_cfg', days, autoClean: autoClean.value }
  await dataStore.save('qcRetention', cfg)
  ElMessage.success(`保留策略已保存：异常数据保留 ${days} 天，到期自动清理已${autoClean.value ? '开启（每日凌晨执行清理）' : '关闭'}`)
}

/* 剩余保留 = 保留天数 −（今天 − 检查日期）；异常单无独立 checkedAt 字段，以数据日期 dt 作为检查时间口径 */
function remainDays(dt: string): number {
  if (!dt) return NaN
  const t = new Date(`${dt}T00:00:00`).getTime()
  if (Number.isNaN(t)) return NaN
  const now = new Date()
  now.setHours(0, 0, 0, 0)
  return (Number(keepDays.value) || 30) - Math.round((now.getTime() - t) / 86400000)
}
function remainText(dt: string): string {
  const r = remainDays(dt)
  if (Number.isNaN(r)) return '—'
  return r < 0 ? '已到期' : `${r} 天`
}
function isKeepLow(dt: string): boolean {
  const r = remainDays(dt)
  return !Number.isNaN(r) && r <= 3
}

/* ---- 隔离区查看 ---- */
function quarantine() {
  ElMessage.info('异常数据已同步至隔离区（/data/quarantine），可下载分析')
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索单号/规则/表"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部工具栏按钮 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">异常数据核查</div>
        <div class="ph-desc">检查失败生成的异常单：查看异常样本 → 核查定责 → 修复（生成清理SQL）或忽略（豁免留痕）→ 归档闭环</div>
      </div>
      <div class="ph-acts">
        <span class="dl-scope">
          下载范围
          <label class="radio-line"><input v-model="dlScope" type="radio" value="all" />全部异常</label>
          <label class="radio-line"><input v-model="dlScope" type="radio" value="filtered" />当前筛选结果</label>
        </span>
        <el-dropdown trigger="click" @command="onExportCmd">
          <button class="tb-new" type="button">⇩ 下载异常数据 ▾</button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="csv">CSV（原始数据 + 错误原因 + 检查时间）</el-dropdown-item>
              <el-dropdown-item command="excel">Excel（.xls）</el-dropdown-item>
              <el-dropdown-item command="json">JSON</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <button class="op-btn" @click="quarantine">隔离区查看</button>
      </div>
    </div>

    <!-- 状态流转 -->
    <div class="card panel" style="margin-bottom:14px">
      <div class="flow">
        <template v-for="(s, i) in FLOW" :key="s.k">
          <div class="flow-node">
            <b>{{ s.t }}</b>
            <div class="flow-desc">{{ s.d }}</div>
          </div>
          <span v-if="i < FLOW.length - 1" class="flow-arrow">→</span>
        </template>
      </div>
      <div class="lock-tip">闭环说明：待处理 →（修复或忽略）→ 已处置 →（复检/豁免审批通过）→ 已归档；未闭环异常会在质量流图上持续标红并阻塞产出表质量评分。</div>
    </div>

    <!-- 统计卡 -->
    <div class="stat-grid">
      <div class="card stat-card">
        <span class="sc-icon" style="background:#d97706">⚑</span>
        <div><div class="stat-num">{{ pendingCnt }}</div><div class="stat-label">待处理</div></div>
      </div>
      <div class="card stat-card">
        <span class="sc-icon" style="background:#16a34a">✓</span>
        <div><div class="stat-num">{{ fixedCnt }}</div><div class="stat-label">已修复</div></div>
      </div>
      <div class="card stat-card">
        <span class="sc-icon" style="background:#475569">⊘</span>
        <div><div class="stat-num">{{ ignoredCnt }}</div><div class="stat-label">已忽略（豁免）</div></div>
      </div>
    </div>

    <!-- 异常统计与趋势（新增）：总体趋势 / 分类趋势 / 趋势判断（仅提示，人工处理） / 三小表 / 保留策略 -->
    <div class="card panel" style="margin-bottom:14px">
      <div class="tbl-toolbar">
        <span class="sec-head">异常统计与趋势</span>
        <span class="vd-pill" :class="verdict.level" :title="verdict.advice">{{ verdict.label }}</span>
        <span class="spacer" />
        <span class="keep-box">
          保留策略：保留 <input v-model="keepDays" type="number" min="1" class="kw keep-input" /> 天
          <el-switch v-model="autoClean" size="small" /> 到期自动清理
          <button class="op-btn" @click="saveRetention">保存策略</button>
        </span>
      </div>
      <div class="verdict-line" :class="verdict.level">
        <template v-if="verdict.level !== 'normal'">🔔 {{ verdict.advice }}。已通知人工处理（系统仅提示，不自动处理）。</template>
        <template v-else>✓ {{ verdict.advice }}</template>
      </div>

      <div class="trend-block">
        <div class="trend-cap">总体趋势 · 近 30 天每日异常数量（行）</div>
        <div class="vbars30">
          <div v-for="(v, i) in TREND30" :key="i" class="vbar30">
            <div class="vbar30-track">
              <div
                class="vbar30-bar"
                :class="{ hot: i === TREND30.length - 1 && verdict.level !== 'normal' }"
                :style="{ height: Math.max(3, Math.round((v / trendMax) * 100)) + 'px' }"
                :title="`${trendDays[i]}：${v} 行`"
              />
            </div>
            <span v-if="i % 5 === 4 || i === TREND30.length - 1" class="vbar30-l">{{ trendDays[i] }}</span>
            <span v-else class="vbar30-l">&nbsp;</span>
          </div>
        </div>
      </div>

      <div class="trend-block">
        <div class="trend-cap">
          分类趋势 · 近 7 日分组柱状
          <span class="dim-switch">
            <label class="radio-line"><input v-model="groupDim" type="radio" value="type" />按错误类型</label>
            <label class="radio-line"><input v-model="groupDim" type="radio" value="rule" />按规则</label>
          </span>
          <span class="glegend">
            <span v-for="g in activeGroups" :key="g.name" class="gleg"><i :style="{ background: g.color }" />{{ g.name }}</span>
          </span>
        </div>
        <div class="gwrap">
          <div v-for="(d, di) in groupDayLabels" :key="d" class="gcol">
            <div class="gtrack">
              <div
                v-for="g in activeGroups"
                :key="g.name"
                class="gbar"
                :style="{ height: Math.max(3, Math.round((g.vals[di] / groupMax) * 100)) + 'px', background: g.color }"
                :title="`${g.name} · ${d}：${g.vals[di]} 行`"
              />
            </div>
            <span class="gday">{{ d }}</span>
          </div>
        </div>
      </div>

      <div class="mini-grid">
        <div v-for="t in miniTables" :key="t.title">
          <div class="mini-title">{{ t.title }}</div>
          <table class="tbl">
            <thead>
              <tr><th>名称</th><th style="width:64px">异常单</th><th style="width:76px">异常行数</th></tr>
            </thead>
            <tbody>
              <tr v-for="it in t.list" :key="it.name">
                <td class="mono" style="font-size:11.5px">{{ it.name }}</td>
                <td>{{ it.orders }}</td>
                <td><b style="color:var(--danger)">{{ it.cnt }}</b></td>
              </tr>
              <tr v-if="t.list.length === 0">
                <td colspan="3" style="text-align:center;color:var(--text-3);padding:14px">暂无数据</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- 异常单列表 -->
    <div class="card panel">
      <div class="tbl-toolbar">
        <span class="sec-head">异常单列表</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>异常单</th><th>规则</th><th>表.字段</th><th>维度</th><th>异常数</th><th>数据日期</th><th>剩余保留</th><th>状态</th>
            <th style="width:170px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="e in filtered" :key="e.id">
            <td>
              <b class="mono" style="font-size:12px">{{ e.id }}</b>
              <div style="font-size:11px;color:var(--text-3)">检查单 {{ e.qcId }}</div>
            </td>
            <td>
              {{ e.ruleName }}
              <div style="font-size:11px;color:var(--text-3)">{{ e.ruleId }}</div>
            </td>
            <td><span class="mono" style="font-size:11.5px">{{ e.table }}.{{ e.field }}</span></td>
            <td>{{ e.dim }}</td>
            <td><b style="color:var(--danger)">{{ e.cnt }}</b></td>
            <td style="color:var(--text-2)">{{ e.dt }}</td>
            <td :class="{ 'keep-low': isKeepLow(e.dt) }" :title="`按保留策略（${keepDays} 天）计算，剩余 ≤3 天标橙`">{{ remainText(e.dt) }}</td>
            <td><span class="st" :class="stCls(e.status)"><span class="dot" />{{ stLabel(e.status) }}</span></td>
            <td>
              <button class="op-btn primary" @click="openSample(e)">样本</button>
              <template v-if="e.status === 'pending'">
                <button class="op-btn" @click="openFix(e)">修复</button>
                <button class="op-btn" @click="openIgnore(e)">忽略</button>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的异常单，请调整筛选条件</div>
    </div>

    <!-- 异常样本弹窗 -->
    <el-dialog v-model="sampleVisible" :title="sampleTarget ? `异常样本 - ${sampleTarget.id}` : ''" width="680px">
      <template v-if="sampleTarget">
        <div class="desc-grid">
          <div class="d-row"><span class="d-k">规则</span><span>{{ sampleTarget.ruleName }}（{{ sampleTarget.ruleId }}）</span></div>
          <div class="d-row"><span class="d-k">表.字段</span><span class="mono">{{ sampleTarget.table }}.{{ sampleTarget.field }}</span></div>
          <div class="d-row"><span class="d-k">维度</span><span>{{ sampleTarget.dim }}</span></div>
          <div class="d-row"><span class="d-k">异常数</span><span><b style="color:var(--danger)">{{ sampleTarget.cnt }}</b> 行</span></div>
          <div class="d-row"><span class="d-k">数据日期</span><span>{{ sampleTarget.dt }}</span></div>
        </div>
        <div class="sample-wrap">
          <table class="tbl">
            <thead>
              <tr><th v-for="k in sampleKeys" :key="k">{{ k }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in sampleTarget.sample" :key="i">
                <td v-for="k in sampleKeys" :key="k"><span class="mono">{{ sampleVal(row[k]) }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="lock-tip">异常数据已同步至隔离区 /data/quarantine/{{ sampleTarget.dt }}，修复动作将生成清理 SQL 供审批执行。</div>
      </template>
    </el-dialog>

    <!-- 修复抽屉 -->
    <el-drawer v-model="fixVisible" :title="fixTarget ? `修复异常 - ${fixTarget.id}` : ''" size="460px">
      <template v-if="fixTarget">
        <div class="banner-info">ℹ 规则：{{ fixTarget.ruleName }} · 表 <b class="mono">{{ fixTarget.table }}.{{ fixTarget.field }}</b> · 异常 {{ fixTarget.cnt }} 行</div>
        <div class="form-grid" style="margin-top:12px">
          <div class="f-item">修复方式
            <div class="radio-col">
              <label v-for="w in FIX_WAYS" :key="w.v" class="radio-line">
                <input v-model="fixWay" type="radio" :value="w.v" />{{ w.t }}
              </label>
            </div>
          </div>
          <label class="f-item">修复说明 *
            <textarea v-model="fixNote" class="kw" style="width:100%;resize:vertical" rows="2" placeholder="如：负值金额为测试数据，按 pay_id 清理" />
          </label>
        </div>
        <div style="margin-top:16px;display:flex;gap:8px">
          <button class="tb-new" @click="saveFix">执行修复</button>
          <button class="op-btn" @click="fixVisible = false">取消</button>
        </div>
      </template>
    </el-drawer>

    <!-- 忽略抽屉 -->
    <el-drawer v-model="ignoreVisible" :title="ignoreTarget ? `忽略异常 - ${ignoreTarget.id}` : ''" size="380px">
      <label class="f-item">忽略理由（必填，审计留痕）*
        <textarea v-model="ignoreReason" class="kw" style="width:100%;resize:vertical" rows="3" placeholder="如：历史存量数据，业务确认豁免" />
      </label>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveIgnore">确认忽略</button>
        <button class="op-btn" @click="ignoreVisible = false">取消</button>
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
.flow{display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap}
.flow-node{border:1px solid var(--border);border-radius:var(--radius);padding:8px 14px}
.flow-node b{font-size:12.5px}
.flow-desc{font-size:11px;color:var(--text-3)}
.flow-arrow{color:var(--text-3);font-size:14px}
.lock-tip{border-left:3px solid var(--warn);background:var(--warn-bg);color:var(--warn);font-size:11.5px;padding:7px 10px;border-radius:0 7px 7px 0}
.stat-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-bottom:14px}
.stat-card{display:flex;align-items:center;gap:12px;padding:13px 15px}
.sc-icon{width:34px;height:34px;border-radius:9px;color:#fff;font-size:15px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}
.stat-num{font-size:21px;font-weight:700;line-height:1.2}
.stat-label{font-size:11.5px;color:var(--text-3)}
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.tbl-toolbar .spacer{flex:1}
.pill.info{display:inline-flex;align-items:center;padding:1px 9px;border-radius:var(--radius-lg);font-size:11px;background:var(--info-bg);color:var(--info)}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.desc-grid{display:flex;flex-direction:column;margin-bottom:10px}
.d-row{display:flex;gap:12px;padding:6px 0;border-bottom:1px dashed var(--border);font-size:12.5px}
.d-k{width:80px;color:var(--text-3);flex-shrink:0}
.sample-wrap{max-height:260px;overflow:auto;border:1px solid var(--border);border-radius:var(--radius);margin-bottom:4px}
.banner-info{background:var(--info-bg);color:var(--info);border-radius:var(--radius);padding:9px 12px;font-size:12.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.radio-col{display:flex;flex-direction:column;gap:6px}
.radio-line{display:flex;gap:7px;align-items:center;font-size:12.5px;color:var(--text);cursor:pointer}

/* ===== 新增：下载 / 异常统计趋势 / 保留策略 ===== */
.dl-scope{display:inline-flex;align-items:center;gap:8px;font-size:11.5px;color:var(--text-2)}
.vd-pill{font-size:11px;font-weight:600;padding:2px 10px;border-radius:var(--radius-lg);flex-shrink:0}
.vd-pill.danger{background:rgba(220,38,38,.1);color:#dc2626}
.vd-pill.warn{background:var(--warn-bg);color:var(--warn)}
.vd-pill.normal{background:rgba(22,163,74,.1);color:#16a34a}
.verdict-line{font-size:12px;border-radius:var(--radius-sm);padding:7px 10px;margin-bottom:12px}
.verdict-line.danger{background:rgba(220,38,38,.08);color:#dc2626}
.verdict-line.warn{background:var(--warn-bg);color:var(--warn)}
.verdict-line.normal{background:var(--info-bg);color:var(--info)}
.keep-box{display:inline-flex;align-items:center;gap:8px;font-size:11.5px;color:var(--text-2);flex-wrap:wrap}
.keep-input{width:64px;padding:3px 8px;font-size:12px}
.trend-block{margin-bottom:14px}
.trend-cap{font-size:12px;color:var(--text-2);font-weight:600;margin-bottom:8px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.vbars30{display:flex;gap:4px;align-items:flex-end;overflow-x:auto;border-bottom:1px solid var(--border);padding:0 2px}
.vbar30{width:18px;flex-shrink:0;display:flex;flex-direction:column;align-items:center}
.vbar30-track{height:104px;display:flex;align-items:flex-end;justify-content:center;width:100%}
.vbar30-bar{width:12px;min-height:3px;background:linear-gradient(180deg,#3c86f7,#1668dc);border-radius:2px 2px 0 0}
.vbar30-bar.hot{background:linear-gradient(180deg,#f59e0b,#d97706)}
.vbar30-l{height:16px;font-size:10px;color:var(--text-3);line-height:16px;white-space:nowrap}
.dim-switch{display:inline-flex;gap:10px;font-weight:400}
.gwrap{display:flex;gap:14px;align-items:flex-end;border-bottom:1px solid var(--border);padding:0 4px}
.gcol{display:flex;flex-direction:column;align-items:center}
.gtrack{height:110px;display:flex;align-items:flex-end;gap:3px}
.gbar{width:12px;border-radius:2px 2px 0 0}
.gday{height:16px;font-size:10.5px;color:var(--text-3);line-height:16px}
.glegend{display:inline-flex;gap:12px;font-size:11px;color:var(--text-2);font-weight:400;flex-wrap:wrap}
.gleg{display:inline-flex;align-items:center;gap:5px}
.gleg i{width:9px;height:9px;border-radius:2px;display:inline-block}
.mini-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
.mini-title{font-size:12px;font-weight:600;color:var(--text-2);margin-bottom:6px}
.keep-low{color:#d97706;font-weight:700}
</style>
