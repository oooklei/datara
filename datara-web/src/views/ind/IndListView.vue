<script setup lang="ts">
/**
 * M10i 指标目录（/ind/list）
 * 对齐 prototype/assets/pages/m10-standard.js L599-687：
 * 指标表格（indicators：指标/类型/业务口径/来源表/主题域/状态/负责人）+ 新建/编辑抽屉；
 * 顶部工具栏：新建指标、一致性检查；行操作：详情 / 趋势 / 口径变更 / 删除（被引用禁止）。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, DB, ST } from '../../services/mock/dataStore'
import type { BizDomain, DbUser, DwLayer, ImpactExample, Indicator, MetaTable, Model } from '../../services/types'

const router = useRouter()

const rows = ref<Indicator[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ type: '', domain: '', status: '' })

const typeOptions = ['原子', '派生', '计算']
const statusOptions = [
  { v: 'published', t: '已发布' },
]
const periodOptions = ['日', '近7天', '本月', '实时', '-']

const domainNames = ref<string[]>(['交易域', '经营域', '商品域', '财务域', '公共'])
const tableNames = ref<string[]>([])
const user = ref<DbUser>({ name: '王工', role: '' })
const impact = ref<ImpactExample | null>(null)

/* ---- 左侧筛选面板 facets ---- */
const facets = computed<Facet[]>(() => [
  { key: 'type', label: '指标类型', options: typeOptions.map((t) => ({ v: t, t: t + '指标' })) },
  { key: 'domain', label: '主题域', options: domainNames.value.map((d) => ({ v: d, t: d })) },
  { key: 'status', label: '状态', options: statusOptions },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.type && r.type !== filters.value.type) return false
    if (filters.value.domain && r.domain !== filters.value.domain) return false
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.id, r.name, r.en, r.domain].some((s) => s.toLowerCase().includes(kw))
  })
})

async function reload() {
  // 展开为新数组触发响应式更新（save 原地修改数组，list 返回同一引用）
  rows.value = [...((await dataStore.list<Indicator>('indicators')) ?? [])]
}

onMounted(async () => {
  await reload()
  const [domains, tables, u, imp] = await Promise.all([
    dataStore.list<BizDomain>('bizDomains'),
    dataStore.list<MetaTable>('metaTables'),
    dataStore.get<DbUser>('user'),
    dataStore.get<ImpactExample>('impactExample'),
  ])
  if (domains.length) domainNames.value = domains.map((d) => d.name)
  tableNames.value = tables.map((t) => t.name)
  if (u) user.value = u
  if (imp) impact.value = imp
})

/* ---- ST 徽标 / 类型徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
function typePillStyle(t: string): Record<string, string> {
  if (t === '派生') return { background: '#f1e9ff', color: 'var(--purple)' }
  if (t === '计算') return { background: '#e3f6f8', color: 'var(--cyan)' }
  return {}
}

/* ---- 时间 ---- */
function nowStr(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
function todayStr(): string {
  return nowStr().slice(0, 10)
}

/* ---- 详情抽屉 ---- */
const detailVisible = ref(false)
const detailRow = ref<Indicator | null>(null)

function openDetail(r: Indicator) {
  detailRow.value = r
  detailVisible.value = true
}

/* ---- 新建指标 ---- */
const formVisible = ref(false)
const form = ref({
  name: '', en: '', type: '原子', domain: '交易域',
  bizDef: '', techDef: '', srcTable: '', srcField: '', period: '日', dims: '',
})

function openCreate() {
  form.value = {
    name: '', en: '', type: '原子', domain: domainNames.value[0] ?? '交易域',
    bizDef: '', techDef: '',
    srcTable: tableNames.value[0] ?? '', srcField: '', period: '日', dims: '',
  }
  formVisible.value = true
}

async function saveCreate() {
  const name = form.value.name.trim()
  if (!name || !form.value.bizDef.trim()) {
    ElMessage.warning('请填写指标名称与业务口径')
    return
  }
  if (rows.value.some((i) => i.name === name)) {
    ElMessage.error(`已存在同名指标「${name}」，禁止同名不同义`)
    return
  }
  const nextSeq = rows.value.reduce((m, r) => {
    const n = Number(r.id.replace(/^\D+/, ''))
    return Number.isFinite(n) && n > m ? n : m
  }, 0) + 1
  const row: Indicator = {
    id: 'METRIC_' + String(nextSeq).padStart(3, '0'),
    name,
    en: form.value.en.trim(),
    type: form.value.type,
    bizDef: form.value.bizDef.trim(),
    techDef: form.value.techDef.trim(),
    srcTable: form.value.srcTable,
    srcField: form.value.srcField.trim(),
    outTable: '-',
    outTask: '-',
    period: form.value.period,
    dims: form.value.dims.trim() || '-',
    owner: user.value.name,
    domain: form.value.domain,
    status: 'published',
    v: 1,
    trend: [0, 0, 0, 0, 0, 0, 0, 0],
    unit: '-',
    versions: [{ v: 1, date: todayStr(), note: '初版', author: user.value.name }],
  }
  rows.value.push(row)
  await dataStore.save('indicators', row)
  formVisible.value = false
  ElMessage.success('指标已创建')
}

/* ---- 口径变更 ---- */
const changeVisible = ref(false)
const changeTarget = ref<Indicator | null>(null)
const changeForm = ref({ reason: '', bizDef: '', techDef: '' })

function openChange(r: Indicator) {
  changeTarget.value = r
  changeForm.value = { reason: '', bizDef: r.bizDef, techDef: r.techDef }
  changeVisible.value = true
}

async function saveChange() {
  const d = changeTarget.value
  if (!d) return
  const reason = changeForm.value.reason.trim()
  if (!reason) {
    ElMessage.warning('请填写变更原因')
    return
  }
  // 口径变更直接发布（无审批流）：版本 +1，记录变更历史
  d.bizDef = changeForm.value.bizDef.trim() || d.bizDef
  d.techDef = changeForm.value.techDef.trim() || d.techDef
  d.v += 1
  d.status = 'published'
  d.changeNote = reason
  d.versions = [...(d.versions ?? []), { v: d.v, date: todayStr(), note: `口径变更：${reason}`, author: user.value.name }]
  await dataStore.save('indicators', d)
  await reload()
  changeVisible.value = false
  ElMessage.success(`口径变更已发布（v${d.v}）`)
}

/* ---- 删除（被派生指标或报表引用禁止） ---- */
async function removeRow(r: Indicator) {
  const used = rows.value.some((i) => i.baseMetric === r.id)
    || (impact.value?.downIndicators ?? []).some((x) => x.code === r.id)
  if (used) {
    ElMessageBox.alert(`指标「${r.name}」被派生指标或报表引用，请先解除引用或走口径变更流程。`, '无法删除', { confirmButtonText: '知道了' })
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除指标「${r.name}」？该操作不可恢复。`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await dataStore.remove('indicators', r.id)
  ElMessage.success('已删除')
  await reload()
}

/* ==================================================================
 * 指标核查三入口（设计方案第10章）：查看血缘 / 查看数据 / 查看任务
 * ================================================================== */

/* ---- 血缘：分层配色（沿用 M04 数仓建模 dwLayers 的色板，同步读取 seed 常量） ---- */
const LAYER_FALLBACK: Record<string, { name: string; color: string; desc: string }> = {
  ODS: { name: '原始数据层', color: '#0891b2', desc: '从数据源原样同步，不做加工' },
  DWD: { name: '明细数据层', color: '#1668dc', desc: '清洗、标准化、维度退化后的明细事实表' },
  DWS: { name: '汇总数据层', color: '#7c3aed', desc: '按主题、维度进行轻度/重度汇总聚合' },
  ADS: { name: '应用数据层', color: '#16a34a', desc: '面向应用的宽表/指标结果表' },
  DIM: { name: '维度层', color: '#d97706', desc: '公共维度表' },
}
const layerMeta: Record<string, { name: string; color: string; desc: string }> = { ...LAYER_FALLBACK }
;(DB.dwLayers as DwLayer[]).forEach((l) => {
  layerMeta[l.code] = { name: l.name, color: l.color, desc: l.desc }
})
function layerInfo(code: string): { name: string; color: string; desc: string } {
  return layerMeta[code] ?? { name: code, color: '#8b93a7', desc: '' }
}

/* ---- 血缘：确定性纯函数 buildLineage(sourceTable) ----
 * 推导规则：
 * 1) 在 DB.models 中按 code 找到 sourceTable 对应模型，取其 layer 与 bizDomain；
 * 2) 链路固定四层 ODS→DWD→DWS→ADS（当前层之前的层按通用分层产出，之后的层按下游继续）；
 * 3) 每层选 1 张代表表：优先用 models 中同 bizDomain、同层、已发布模型的 code；
 * 4) ODS 层匹配不到时合成 'ods_' + 来源库前缀 + '_source'（来源库前缀取表名第 2 段，如 ods_gdb_xxx → gdb）；
 * 5) sourceTable 若不在 models 中（自定义表），放进其命名前缀推断的层（dws_/dwd_/ads_），兜底 DWD，
 *    并按规则 3 为其余层选代表表。
 */
function buildLineage(sourceTable: string): { layer: string; table: string; highlight: boolean }[] {
  const layers = ['ODS', 'DWD', 'DWS', 'ADS']
  const models: Model[] = DB.models
  const self = models.find((m) => m.code === sourceTable)
  const bizDomain = self?.bizDomain ?? ''
  // 同主题域、同层、已发布的代表表（按 models 定义序取首个，结果确定）
  const pickInLayer = (layer: string): string | null => {
    const hit = models.find((m) => m.layer === layer && m.status === 'published' && m.bizDomain === bizDomain)
    return hit ? hit.code : null
  }
  // ODS 匹配不到时按来源表名推断库名前缀合成一张源表（如 ods_gdb_biz_trade_order → ods_gdb_source）
  const synthOds = (table: string): string => {
    const seg = table.split('_')
    const dbPrefix = seg.length > 1 ? seg[1] : 'biz'
    return 'ods_' + dbPrefix + '_source'
  }
  // sourceTable 归属层：优先模型登记的 layer，否则按命名前缀推断（默认 DWD）
  const selfLayer = self?.layer
    ?? (sourceTable.startsWith('ods_') ? 'ODS'
      : sourceTable.startsWith('dws_') ? 'DWS'
      : sourceTable.startsWith('ads_') ? 'ADS'
      : sourceTable.startsWith('dim_') ? 'DIM' : 'DWD')
  return layers.map((layer) => {
    // 当前来源表所在层直接用 sourceTable 并高亮；其余层选同域代表表，缺失时兜底合成
    const table = layer === selfLayer
      ? sourceTable
      : (layer === 'ODS' ? pickInLayer('ODS') ?? synthOds(sourceTable) : pickInLayer(layer) ?? layer.toLowerCase() + '_' + (sourceTable.split('_')[1] ?? 'biz') + '_table')
    return { layer, table, highlight: layer === selfLayer }
  })
}

/* ---- 血缘弹层 ---- */
const lineageVisible = ref(false)
const lineageRows = ref<{ layer: string; table: string; highlight: boolean }[]>([])
const lineageMetric = ref('')

function openLineage(r: Indicator) {
  lineageMetric.value = r.name
  lineageRows.value = buildLineage(r.srcTable)
  lineageVisible.value = true
}

/* ---- 数据弹层：确定性 mock 近 7 日指标值 ---- */
const dataVisible = ref(false)
const dataRow = ref<Indicator | null>(null)
interface DataRow { stat_date: string; channel: string; value: number; yoy: string }
const dataRows = ref<DataRow[]>([])
const CHANNELS = ['PC', 'APP', '小程序', 'H5']

// 确定性数值：以 (日期序 × 渠道序) 为种子的正弦波动（不依赖运行时随机，刷新结果不变）
// 行数约束 8-12：取近 7 天窗口内 3 个递减日期 × 4 渠道 = 12 行；基准 120000、±8% 波动
function buildDataRows(): DataRow[] {
  const out: DataRow[] = []
  for (let i = 0; i < 3; i++) {
    const d = new Date()
    d.setDate(d.getDate() - i * 3) // 今天 / 3天前 / 6天前，落在近7日窗口内
    const p = (x: number) => String(x).padStart(2, '0')
    const statDate = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
    CHANNELS.forEach((ch, j) => {
      const wave = Math.sin((i * 4 + j) * 1.7) // 确定性波动源
      const value = Math.round(120000 * (1 + wave * 0.08) + j * 8600)
      const yoy = ((wave * 12) + 6.4).toFixed(1) // 同比：+x.x%，范围约 -5.6% ~ +18.4%
      out.push({ stat_date: statDate, channel: ch, value, yoy: (Number(yoy) >= 0 ? '+' : '') + yoy + '%' })
    })
  }
  return out
}

function openData(r: Indicator) {
  dataRow.value = r
  dataRows.value = buildDataRows()
  dataVisible.value = true
}

/* ---- 任务弹层 ---- */
const taskVisible = ref(false)
const taskRow = ref<Indicator | null>(null)

function openTask(r: Indicator) {
  taskRow.value = r
  taskVisible.value = true
}
function gotoTask() {
  taskVisible.value = false
  /* /etl/design/:id 路由已移除（I1 意见③）：ETL 编排统一走任务中心 ETL 视角 */
  router.push('/dag?tab=etl')
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索指标"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">指标管理</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
        <button class="tb-new" @click="openCreate">＋ 新建指标</button>
        <button class="op-btn" @click="router.push('/ind/consistency')">一致性检查</button>
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>指标</th><th>类型</th><th>业务口径</th><th>来源表</th>
            <th>主题域</th><th>状态</th><th>负责人</th><th style="width:210px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td>
              <a @click="openDetail(r)"><b>{{ r.name }}</b></a>
              <div style="font-size:11px;color:var(--text-3)">{{ r.id }} · {{ r.en }} · v{{ r.v }}</div>
            </td>
            <td><span class="pill info" :style="typePillStyle(r.type)">{{ r.type }}</span></td>
            <td style="font-size:11.5px;color:var(--text-2)">{{ r.bizDef }}</td>
            <td><span class="mono" style="font-size:11.5px">{{ r.srcTable }}</span></td>
            <td><span class="pill info">{{ r.domain }}</span></td>
            <td>
              <span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span>
            </td>
            <td>{{ r.owner }}</td>
            <td>
              <button class="op-btn primary" @click="openDetail(r)">详情</button>
              <button class="op-btn" @click="router.push('/ind/board')">趋势</button>
              <button class="op-btn" @click="openChange(r)">口径变更</button>
              <button class="op-btn danger" @click="removeRow(r)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="filtered.length === 0" class="empty">未找到匹配的指标，请调整筛选条件</div>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="detailVisible" :title="detailRow ? '指标详情 - ' + detailRow.name : ''" size="560px">
      <template v-if="detailRow">
        <!-- 核查操作区：血缘 / 数据 / 任务（设计方案第10章） -->
        <div class="check-bar">
          <button class="op-btn primary" @click="openLineage(detailRow)">查看血缘</button>
          <button class="op-btn primary" @click="openData(detailRow)">查看数据</button>
          <button class="op-btn primary" @click="openTask(detailRow)">查看任务</button>
        </div>
        <div class="desc-grid">
          <span class="k">编号</span><span class="mono">{{ detailRow.id }}</span>
          <span class="k">英文名</span><span class="mono">{{ detailRow.en }}</span>
          <span class="k">类型</span><span>{{ detailRow.type }}</span>
          <span class="k">主题域</span><span>{{ detailRow.domain }}</span>
          <span class="k">版本</span><span>v{{ detailRow.v }}</span>
          <span class="k">状态</span>
          <span><span class="st" :class="stCls(detailRow.status)"><span class="dot" />{{ stLabel(detailRow.status) }}</span></span>
          <span class="k">负责人</span><span>{{ detailRow.owner }}</span>
          <span class="k">业务口径</span><span>{{ detailRow.bizDef }}</span>
          <span class="k">技术口径</span><span class="mono" style="font-size:11.5px">{{ detailRow.techDef }}</span>
          <span class="k">来源</span>
          <span class="mono" style="font-size:11.5px">{{ detailRow.srcTable }}.{{ detailRow.srcField || '-' }}</span>
          <span class="k">产出</span>
          <span>
            <template v-if="detailRow.outTable && detailRow.outTable !== '-'">
              <span class="mono">{{ detailRow.outTable }}</span>（{{ detailRow.outTask }}）
            </template>
            <template v-else>未落表（即席计算）</template>
          </span>
          <span class="k">统计周期</span><span>{{ detailRow.period }}</span>
          <span class="k">维度</span><span>{{ detailRow.dims }}</span>
        </div>
        <div class="sec-title">版本历史</div>
        <div class="tl">
          <div v-for="v in detailRow.versions" :key="v.v" class="tl-item done">
            <span class="tl-dot" />
            <div>
              <b style="font-size:12.5px">v{{ v.v }} · {{ v.note }}</b>
              <div style="font-size:11px;color:var(--text-3)">{{ v.date }} · {{ v.author }}</div>
            </div>
          </div>
        </div>
      </template>
    </el-drawer>

    <!-- 新建指标抽屉 -->
    <el-drawer v-model="formVisible" title="新建指标" size="520px">
      <div class="form-grid">
        <label class="f-item">指标名称
          <input v-model="form.name" placeholder="如：支付金额" />
        </label>
        <label class="f-item">英文名
          <input v-model="form.en" placeholder="如：pay_amount" />
        </label>
        <label class="f-item">指标类型
          <select v-model="form.type">
            <option v-for="t in typeOptions" :key="t" :value="t">{{ t }}指标</option>
          </select>
        </label>
        <label class="f-item">主题域
          <select v-model="form.domain">
            <option v-for="d in domainNames" :key="d" :value="d">{{ d }}</option>
          </select>
        </label>
        <label class="f-item">业务口径定义
          <textarea v-model="form.bizDef" rows="2" style="resize:vertical" placeholder="指标业务含义与统计范围" />
        </label>
        <label class="f-item">技术口径（SQL/公式）
          <textarea v-model="form.techDef" rows="2" class="mono" style="resize:vertical" placeholder="如：SUM(pay_amount) WHERE pay_status=1" />
        </label>
        <label class="f-item">来源表
          <select v-model="form.srcTable">
            <option v-for="t in tableNames" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
        <label class="f-item">来源字段
          <input v-model="form.srcField" placeholder="如：pay_amount" />
        </label>
        <label class="f-item">统计周期
          <select v-model="form.period">
            <option v-for="p in periodOptions" :key="p" :value="p">{{ p }}</option>
          </select>
        </label>
        <label class="f-item">维度
          <input v-model="form.dims" placeholder="如：日期/渠道" />
        </label>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveCreate">保存</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 口径变更抽屉 -->
    <el-drawer
      v-model="changeVisible"
      :title="changeTarget ? '口径变更 - ' + changeTarget.name + '（当前 v' + changeTarget.v + '）' : ''"
      size="480px"
    >
      <template v-if="changeTarget">
        <div class="form-grid">
          <label class="f-item">变更原因（必填）
            <textarea v-model="changeForm.reason" rows="3" style="resize:vertical" placeholder="说明变更原因与影响" />
          </label>
          <label class="f-item">新业务口径
            <textarea v-model="changeForm.bizDef" rows="2" style="resize:vertical" />
          </label>
          <label class="f-item">新技术口径
            <textarea v-model="changeForm.techDef" rows="2" class="mono" style="resize:vertical" />
          </label>
        </div>
        <div class="hint">
          变更保存后直接发布为版本 v{{ changeTarget.v + 1 }}，并触发一致性复检。
        </div>
        <div style="margin-top:16px;display:flex;gap:8px">
          <button class="tb-new" @click="saveChange">保存并发布</button>
          <button class="op-btn" @click="changeVisible = false">取消</button>
        </div>
      </template>
    </el-drawer>

    <!-- 核查弹层 A：查看血缘（分层溯源链路 ODS→DWD→DWS→ADS→指标） -->
    <el-dialog v-model="lineageVisible" :title="lineageMetric ? '指标血缘 - ' + lineageMetric : '指标血缘'" width="520px">
      <div class="ln-list">
        <template v-for="row in lineageRows" :key="row.layer">
          <div class="ln-row" :class="{ 'ln-row-cur': row.highlight }">
            <span class="ln-tag" :style="{ background: layerInfo(row.layer).color }">{{ row.layer }}</span>
            <div style="flex:1;min-width:0">
              <div class="mono" style="font-size:12.5px;font-weight:600">{{ row.table }}</div>
              <div style="font-size:11px;color:var(--text-3)">{{ layerInfo(row.layer).name }} · {{ layerInfo(row.layer).desc }}</div>
            </div>
            <span v-if="row.highlight" class="pill info">来源表</span>
          </div>
          <div class="ln-arrow">↓</div>
        </template>
        <div class="ln-row ln-row-out">
          <span class="ln-tag" style="background:var(--primary)">指标</span>
          <div style="font-size:12.5px;font-weight:700">产出指标：{{ lineageMetric }}</div>
        </div>
      </div>
      <div class="hint">链路自上而下溯源：ODS 原始层 → DWD 明细层 → DWS 汇总层 → ADS 应用层 → 指标。</div>
    </el-dialog>

    <!-- 核查弹层 B：查看数据（口径 + 近7日 mock 值） -->
    <el-dialog v-model="dataVisible" :title="dataRow ? '指标数据 - ' + dataRow.name : '指标数据'" width="640px">
      <template v-if="dataRow">
        <div style="margin-bottom:12px">
          <div style="font-weight:700;font-size:13.5px">{{ dataRow.name }}<span class="mono" style="font-weight:400;color:var(--text-3);margin-left:8px;font-size:11.5px">{{ dataRow.id }} · {{ dataRow.en }}</span></div>
          <div style="font-size:12px;color:var(--text-2);margin-top:5px;line-height:1.6">业务口径：{{ dataRow.bizDef }}</div>
          <pre class="mono sql-blk" style="margin-top:8px">技术口径：{{ dataRow.techDef || '-' }}</pre>
        </div>
        <table class="tbl">
          <thead>
            <tr><th>统计日期</th><th>渠道</th><th>指标值</th><th>同比</th></tr>
          </thead>
          <tbody>
            <tr v-for="(d, i) in dataRows" :key="i">
              <td class="mono">{{ d.stat_date }}</td>
              <td>{{ d.channel }}</td>
              <td class="mono">{{ d.value.toLocaleString() }}</td>
              <td>
                <span class="mono" :style="{ color: d.yoy.startsWith('+') ? 'var(--success)' : 'var(--danger)' }">{{ d.yoy }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <div class="hint">数据截取自 dws_pay_summary_daily 最近7天分区（模拟查询结果，用于口径核验）。</div>
      </template>
    </el-dialog>

    <!-- 核查弹层 C：查看任务（产出任务卡片 + SQL 片段 + 跳转 ETL 设计器） -->
    <el-dialog v-model="taskVisible" :title="taskRow ? '产出任务 - ' + taskRow.name : '产出任务'" width="560px">
      <template v-if="taskRow">
        <div class="task-card">
          <div style="flex:1;min-width:0">
            <div class="mono" style="font-weight:700;font-size:13px">{{ taskRow.outTask && taskRow.outTask !== '-' ? taskRow.outTask : 'dws_pay_summary_daily 产出任务' }}</div>
            <div style="font-size:11px;color:var(--text-3);margin-top:3px">产出表：<span class="mono">{{ taskRow.outTable && taskRow.outTable !== '-' ? taskRow.outTable : 'dws_pay_summary_daily' }}</span></div>
          </div>
          <span class="pill info">ETL任务</span>
          <span class="st st-green"><span class="dot" />运行正常</span>
        </div>
        <div class="sec-title">SQL 片段（技术口径）</div>
        <pre class="mono sql-blk">{{ taskRow.techDef || 'SELECT SUM(pay_amount) FROM dws_pay_summary_daily' }}</pre>
        <div style="margin-top:14px;display:flex;gap:8px">
          <button class="tb-new" @click="gotoTask">前往 ETL 任务</button>
          <button class="op-btn" @click="taskVisible = false">关闭</button>
        </div>
      </template>
    </el-dialog>
    </div>
  </div>
</template>

<style scoped>
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:170px;outline:none}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.desc-grid{display:grid;grid-template-columns:84px 1fr;gap:7px 10px;font-size:12.5px}
.desc-grid .k{color:var(--text-3)}
.sec-title{font-weight:700;font-size:13px;margin:16px 0 8px;color:var(--text)}
.tl{display:flex;flex-direction:column;gap:12px}
.tl-item{display:flex;gap:10px}
.tl-dot{width:8px;height:8px;border-radius:50%;background:var(--success);margin-top:5px;flex-shrink:0}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.f-item input,.f-item select,.f-item textarea{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;outline:none;font-family:inherit;background:#fff;color:var(--text)}
.f-item input:focus,.f-item select:focus,.f-item textarea:focus{border-color:var(--primary)}
.hint{font-size:11.5px;color:var(--text-3);margin-top:12px;line-height:1.6}
/* ---- 指标核查（血缘/数据/任务） ---- */
.check-bar{display:flex;gap:8px;margin-bottom:14px;padding:9px 10px;background:var(--bg);border-radius:var(--radius)}
.ln-list{display:flex;flex-direction:column}
.ln-row{display:flex;align-items:center;gap:10px;border:1px solid var(--border);border-radius:var(--radius);padding:10px 12px;background:#fff}
.ln-row-cur{border-color:var(--primary);background:#f0f6ff}
.ln-row-out{border-color:rgba(22,104,220,.35);background:#f8faff}
.ln-tag{color:#fff;font-size:11px;font-weight:700;border-radius:4px;padding:2px 8px;letter-spacing:.5px;flex-shrink:0;min-width:38px;text-align:center}
.ln-arrow{text-align:center;color:var(--text-3);font-size:12px;line-height:1;padding:4px 0}
.sql-blk{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:10px 12px;font-size:11.5px;line-height:1.7;white-space:pre-wrap;word-break:break-all;color:var(--text);margin:0;font-family:inherit}
.task-card{display:flex;align-items:center;gap:10px;border:1px solid var(--border);border-radius:var(--radius);padding:12px;background:#fff}
</style>
