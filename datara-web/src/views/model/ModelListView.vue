<script setup lang="ts">
/**
 * M04 数仓建模列表（对齐 prototype m04-model.js #/model/list）
 * 分层统计卡 + 业务域标签双维筛选（可叠加、再点取消）；
 * 新建模型（草稿→字段设计器）；行操作：字段设计 / 版本 / 血缘影响 / 物理化建表 / 删除。
 * 数据：models / dwLayers / bizDomains / engineTypes（dataStore 持久化）。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import { localTime } from '../../services/mock/timeUtil'
import type { Model, DwLayer, BizDomain, EngineType, ModelVersion, DataSource, DbUser } from '../../services/types'
import ListFilterPanel from '../../components/ListFilterPanel.vue'

const router = useRouter()

const models = ref<Model[]>([])
const layers = ref<DwLayer[]>([])
const domains = ref<BizDomain[]>([])
const engines = ref<EngineType[]>([])
const datasources = ref<DataSource[]>([])
const userName = ref('王工')

const keyword = ref('')
const filters = ref<Record<string, string>>({ layer: '', status: '', domain: '' })

/* ---- 左侧筛选面板：分层/状态 facet（业务域保留原统计卡+域标签交互，避免重复入口） ---- */
const facets = computed(() => [
  { key: 'layer', label: '数仓分层', options: layers.value.map((l) => ({ v: l.code, t: l.code })) },
  {
    key: 'status',
    label: '状态',
    options: [
      { v: 'draft', t: '草稿' },
      { v: 'published', t: '已物理化' },
    ],
  },
])

async function reload() {
  const [ms, ls, ds, es, srcs, u] = await Promise.all([
    dataStore.list<Model>('models'),
    dataStore.list<DwLayer>('dwLayers'),
    dataStore.list<BizDomain>('bizDomains'),
    dataStore.list<EngineType>('engineTypes'),
    dataStore.list<DataSource>('datasources'),
    dataStore.get<DbUser>('user'),
  ])
  models.value = [...(ms ?? [])]
  layers.value = [...(ls ?? [])]
  domains.value = [...(ds ?? [])]
  engines.value = [...(es ?? [])]
  datasources.value = [...(srcs ?? [])]
  userName.value = u?.name ?? '王工'
}

onMounted(reload)

/* ---- 分层 / 业务域双维筛选（再点取消，与左侧面板同源 filters） ---- */
function toggleLayer(code: string) {
  filters.value.layer = filters.value.layer === code ? '' : code
}
function toggleDomain(name: string) {
  filters.value.domain = filters.value.domain === name ? '' : name
}
function clearFilter() {
  filters.value = { layer: '', status: '', domain: '' }
  keyword.value = ''
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return models.value.filter((m) => {
    if (filters.value.layer && m.layer !== filters.value.layer) return false
    if (filters.value.status && m.status !== filters.value.status) return false
    if (filters.value.domain && m.bizDomain !== filters.value.domain) return false
    if (!kw) return true
    return [m.id, m.name, m.code, m.bizDomain, m.owner].some((s) => s.toLowerCase().includes(kw))
  })
})

function layerCount(code: string): number {
  return models.value.filter((m) => m.layer === code && (!filters.value.domain || m.bizDomain === filters.value.domain)).length
}
function domainCount(name: string): number {
  return models.value.filter((m) => m.bizDomain === name && (!filters.value.layer || m.layer === filters.value.layer)).length
}
const allCount = computed(() =>
  models.value.filter((m) => !filters.value.layer || m.layer === filters.value.layer).length,
)

function layerColor(code: string): string {
  return layers.value.find((l) => l.code === code)?.color ?? '#64748b'
}
function isXcEngine(name: string): boolean {
  return engines.value.find((e) => e.name === name)?.xc ?? false
}
function statusOf(m: Model): { cls: string; label: string } {
  return m.status === 'draft' ? { cls: 'st-gray', label: '草稿' } : { cls: 'st-green', label: '已物理化' }
}
function typeNameOf(m: Model): string {
  if (m.type === '事实表') return '星型模型（事务事实）'
  if (m.type === '维度表') return '星型模型（维度）'
  if (m.type === '宽表') return '宽表模型'
  return '明细表'
}

/* ---- 新建模型（草稿） ---- */
const createVisible = ref(false)
const form = ref({ name: '', code: '', layer: 'DWD', engine: 'Apache Doris', type: '事实表', domain: '交易域' })

function openCreate() {
  form.value = { name: '', code: '', layer: 'DWD', engine: 'Apache Doris', type: '事实表', domain: '交易域' }
  createVisible.value = true
}
const layerHint = computed(() => {
  const l = layers.value.find((x) => x.code === form.value.layer)
  return l ? `${l.code}规范：${l.rule}` : ''
})

async function saveCreate() {
  if (!form.value.name.trim() || !form.value.code.trim()) {
    ElMessage.warning('请填写模型名称与表名')
    return
  }
  const nextSeq = models.value.reduce((mx, m) => {
    const n = Number(String(m.id).replace(/^\D+/, ''))
    return Number.isFinite(n) && n > mx ? n : mx
  }, 0) + 1
  const now = nowStr()
  const id = 'MD' + String(nextSeq).padStart(3, '0')
  const version: ModelVersion = { v: 1, date: now, author: '王工', note: '初版（字段设计器创建）', status: '当前版本' }
  const model: Model = {
    id,
    name: form.value.name.trim(),
    code: form.value.code.trim(),
    layer: form.value.layer,
    engine: form.value.engine,
    type: form.value.type,
    status: 'draft',
    fields: [
      { n: 'id', t: 'BIGINT', len: '', pk: true, pkPart: false, cmt: '主键', def: '' },
      { n: 'dt', t: 'DATE', len: '', pk: false, pkPart: true, cmt: '分区字段', def: '' },
    ],
    version: 1,
    owner: '王工',
    bizDomain: form.value.domain,
    updatedAt: now,
    versions: [version],
  }
  await dataStore.save<Model>('models', model)
  createVisible.value = false
  ElMessage.success('模型已创建（草稿），进入字段设计器')
  await reload()
  router.push(`/model/design/${id}`)
}

/* ---- 物理化建表 / 重新物理化 ---- */
const physVisible = ref(false)
const physMode = ref('exec')
const physEngine = ref('')
const physTarget = ref<Model | null>(null)
const physDdl = computed(() => (physTarget.value ? genDdl(physTarget.value, physEngine.value) : ''))

function openPhys(m: Model) {
  physTarget.value = m
  physEngine.value = m.engine
  physMode.value = 'exec'
  physVisible.value = true
}
function genDdl(m: Model, engine: string): string {
  const isDoris = engine.indexOf('Doris') >= 0 || engine === '万里 GreatDB'
  const cols = m.fields.map((f) => {
    const len = String(f.len ?? '')
    const t = f.t + (len !== '' ? (len.charAt(0) === '(' ? len : `(${len})`) : '')
    return `  ${f.n} ${t}${f.cmt ? ` COMMENT '${f.cmt}'` : ''}`
  }).join(',\n')
  const part = m.fields.find((f) => f.pkPart)
  let s = `CREATE TABLE ${m.code} (\n${cols}\n)\n`
  if (part) s += `PARTITION BY ${part.n}\n`
  if (isDoris) {
    const pkField = m.fields.find((f) => f.pk) ?? m.fields[0]
    s += `DISTRIBUTED BY HASH(${pkField ? pkField.n : 'id'}) BUCKETS 10\nPROPERTIES("replication_num"="3");`
  } else {
    s += `COMMENT '${m.name}';`
  }
  return s
}
function download(name: string, content: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = name
  a.click()
  URL.revokeObjectURL(url)
}
async function execPhys() {
  const m = physTarget.value
  if (!m) return
  m.engine = physEngine.value
  m.status = 'published'
  m.updatedAt = nowStr()
  await dataStore.save<Model>('models', m)
  physVisible.value = false
  ElMessage.success(`建表成功：${m.code}（${m.engine}），模型已与ETL任务建立血缘关联`)
  await reload()
}

/* ---- 删除（二次确认） ---- */
async function removeRow(m: Model) {
  try {
    await ElMessageBox.confirm(`确认删除模型「${m.name}（${m.code}）」？该操作不可恢复。`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await dataStore.remove('models', m.id)
  ElMessage.success('已删除')
  await reload()
}

/* ---- 其他模块入口（路由由主控接线，本页仅提示） ---- */
function aiTip() {
  ElMessage.info('AI 建表助手为独立模块入口，请在字段设计器中使用')
}
/* ---- 逆向工程导入（对齐 prototype m04-model.js #/model/reverse L504-542） ---- */
const revVisible = ref(false)
const revScanning = ref(false)
const revScanned = ref(false)
const revDs = ref<DataSource | null>(null)
const revSelected = ref<string[]>([])
// 静态 mock：与原型第二步表清单一致
const revTables = [
  { n: 'user_info', c: 8 },
  { n: 'order_info', c: 12 },
  { n: 'product_info', c: 7 },
  { n: 'coupon_record', c: 11 },
]
const revSources = computed(() => datasources.value.filter((d) => d.type !== 'Kafka'))

/* ---- 批量业务域标注：逆向导入时支持多表统一标注 + 逐表覆盖 ----
 * 交互约定（已确认）：placeholder 显示上次使用的业务域；按 Tab 快速填入；
 * 不填则默认使用上次业务域；ⓘ 提示；最近使用历史下拉（datalist）；localStorage 持久化 */
const LAST_DOMAIN_KEY = 'datara_last_biz_domain'
const DOMAIN_HISTORY_KEY = 'datara_biz_domain_history'
const revDomain = ref('')
const revTableDomains = ref<Record<string, string>>({})
const domainHistory = ref<string[]>(loadDomainHistory())

function loadDomainHistory(): string[] {
  try { return JSON.parse(localStorage.getItem(DOMAIN_HISTORY_KEY) || '[]') as string[] } catch { return [] }
}
/* 上次使用的业务域：历史最近一条，兼容旧的单值 key */
const lastDomain = computed(() => domainHistory.value[0] || localStorage.getItem(LAST_DOMAIN_KEY) || '')
const domainPlaceholder = computed(() =>
  lastDomain.value ? `上次：${lastDomain.value}（按 Tab 快速填入）` : '如：交易域（首次使用，直接输入）')
/* 最近使用 + 现有业务域合并去重，供 datalist 下拉 */
const domainSuggestions = computed(() => [...new Set([...domainHistory.value, ...domains.value.map((d) => d.name)])])

function fillLastDomain() {
  if (!revDomain.value.trim() && lastDomain.value) revDomain.value = lastDomain.value
}
/* 表级业务域：行内覆盖 > 统一输入 > 上次使用 > 公共 */
function domainOf(t: string): string {
  return revTableDomains.value[t]?.trim() || domainFallback(t)
}
function domainFallback(t: string): string {
  void t
  return revDomain.value.trim() || lastDomain.value || '公共'
}
function rememberDomain(name: string) {
  const v = name.trim()
  if (!v) return
  domainHistory.value = [v, ...domainHistory.value.filter((d) => d !== v)].slice(0, 8)
  localStorage.setItem(DOMAIN_HISTORY_KEY, JSON.stringify(domainHistory.value))
  localStorage.setItem(LAST_DOMAIN_KEY, v)
}

function openReverse() {
  revDs.value = null
  revScanning.value = false
  revScanned.value = false
  revSelected.value = []
  revDomain.value = ''
  revTableDomains.value = {}
  revVisible.value = true
}

function revScan(d: DataSource) {
  revDs.value = d
  revScanned.value = false
  revSelected.value = []
  revScanning.value = true
  ElMessage.info(`正在扫描 ${d.name} ...`)
  window.setTimeout(() => {
    revScanning.value = false
    revScanned.value = true
  }, 700)
}

async function revImport() {
  if (revSelected.value.length === 0) {
    ElMessage.warning('请先勾选要导入的表')
    return
  }
  const ds = revDs.value
  if (!ds) return
  const count = revSelected.value.length
  try {
    await ElMessageBox.confirm(
      `确认将选中的 ${count} 张表反向生成为逻辑模型？默认导入至 ODS 层，生成后可调整分层与字段。`,
      '导入确认',
      { confirmButtonText: '导入', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  // 取现有 models 中 MD 前缀最大序号 +1（禁止用数组长度）
  let seq = models.value.reduce((mx, m) => {
    const s = String(m.id)
    if (!s.startsWith('MD')) return mx
    const n = Number(s.slice(2))
    return Number.isFinite(n) && n > mx ? n : mx
  }, 0)
  for (const t of revSelected.value) {
    seq += 1
    const id = 'MD' + String(seq).padStart(3, '0')
    const now = localTime()
    const model: Model = {
      id,
      name: t + '（逆向导入）',
      code: 'ods_imported_' + t,
      layer: 'ODS',
      engine: 'Apache Doris',
      type: '明细表',
      status: 'draft',
      fields: [
        { n: 'id', t: 'BIGINT', len: '', pk: true, pkPart: false, cmt: '主键', def: '' },
        { n: 'dt', t: 'DATE', len: '', pk: false, pkPart: true, cmt: '分区', def: '' },
      ],
      version: 1,
      owner: userName.value,
      bizDomain: domainOf(t),
      updatedAt: now,
      versions: [{ v: 1, date: now, author: userName.value, note: '逆向工程导入自 ' + ds.id, status: '当前版本' }],
    }
    await dataStore.save<Model>('models', model)
  }
  // 记录本次统一标注的业务域为"上次使用"（下次导入 Tab 快速填入）
  if (revDomain.value.trim()) rememberDomain(revDomain.value)
  revVisible.value = false
  ElMessage.success(`已导入生成 ${count} 个逻辑模型（ODS层草稿）`)
  await reload()
}

function tipVersion() {
  ElMessage.info('版本管理为独立页面（/model/version/:id），暂由后续迭代提供')
}
function tipLineage(m: Model) {
  router.push(`/model/lineage/${m.id}`)
}

function nowStr(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      :result-count="filtered.length"
      :total-count="models.length"
      placeholder="搜索模型/表名/业务域/负责人"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头：标题 + 顶部操作按钮 -->
    <div class="card head-card">
      <div class="head-top">
        <div>
          <div class="head-title">数仓搭建与建模</div>
          <div class="head-sub">ODS→DWD→DWS→ADS→DIM 分层建模；三阶段建模（概念→逻辑→物理）；ER 可视化设计 + 表间血缘影响分析</div>
        </div>
        <span class="spacer" />
        <button class="tb-new" @click="openCreate">+ 新建模型</button>
        <button class="op-btn" @click="router.push('/model/er')">ER 设计器</button>
        <button class="op-btn" @click="aiTip">✦ AI 建表助手</button>
        <button class="op-btn" @click="openReverse">逆向工程导入</button>
      </div>
      <div class="hint">操作指引：① 点击分层统计卡与业务域标签可双维筛选（再点取消）；② 「新建模型」进入字段设计器（三阶段：概念→逻辑→物理）；③ 「ER 设计器」直达实体关系画布；④ 物理化后模型进入版本管理与血缘影响分析。</div>
    </div>

    <!-- 状态流转 -->
    <div class="card" style="padding:12px 16px;margin-top:12px">
      <div class="flow-row">
        <span class="flow-step"><b>概念/逻辑建模</b><i>字段设计器 · 评审</i></span>
        <span class="flow-arrow">→</span>
        <span class="flow-step"><b>已发布</b><i>字段冻结 · 可被引用</i></span>
        <span class="flow-arrow">→</span>
        <span class="flow-step"><b>已物理化</b><i>DDL 执行 · 自动分区</i></span>
        <span class="flow-arrow">→</span>
        <span class="flow-step"><b>已投产</b><i>ETL/流任务引用 · 血缘受管</i></span>
      </div>
      <div class="hint" style="margin-top:6px">闭环说明：建模 →（评审发布）→ 已发布 →（物理化建表）→ 已投产；投产模型变更走版本管理（新版本→对比→发布），旧版本可回滚。</div>
    </div>

    <!-- 分层统计卡（点击筛选分层） -->
    <div class="layer-grid">
      <div
        v-for="l in layers"
        :key="l.code"
        class="layer-card"
        :class="{ on: filters.layer === l.code }"
        @click="toggleLayer(l.code)"
      >
        <div class="layer-num" :style="{ color: l.color }">{{ layerCount(l.code) }}</div>
        <div class="layer-label">
          <b>{{ l.code }}</b> {{ l.name }}
          <span v-if="filters.layer === l.code" class="pill info">筛选中</span>
        </div>
        <div class="layer-desc">{{ l.desc }}</div>
      </div>
    </div>

    <!-- 业务域筛选 -->
    <div class="domain-bar">
      <span class="domain-label">业务域筛选：</span>
      <button class="chip" :class="{ on: !filters.domain }" @click="filters.domain = ''">全部 · {{ allCount }}</button>
      <button
        v-for="d in domains"
        :key="d.name"
        class="chip"
        :class="{ on: filters.domain === d.name }"
        @click="toggleDomain(d.name)"
      >{{ d.name }} · {{ domainCount(d.name) }}</button>
      <a v-if="filters.layer || filters.domain" @click="clearFilter">重置筛选</a>
    </div>

    <!-- 建模规范 -->
    <div class="banner-info">
      <span>ℹ</span>
      <span>建模规范：<b v-for="(l, i) in layers" :key="l.code">{{ l.code }}（{{ l.rule }}）<template v-if="i < layers.length - 1">；</template></b></span>
    </div>

    <!-- 模型列表 -->
    <div class="card" style="padding:16px;margin-top:12px">
      <div class="tbl-toolbar">
        <span class="sec-head">逻辑模型列表</span>
        <span class="pill info">{{ filtered.length }} / {{ models.length }}</span>
        <span class="spacer" />
      </div>
      <table class="tbl">
        <thead>
          <tr>
            <th>模型/表</th><th>分层</th><th>表类型</th><th>引擎</th><th>业务域</th>
            <th>字段数</th><th>状态</th><th>负责人</th><th style="width:250px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in filtered" :key="m.id">
            <td>
              <a @click="router.push(`/model/design/${m.id}`)"><b class="mono">{{ m.code }}</b></a>
              <div style="color:var(--text-3);font-size:11px">{{ m.name }} · v{{ m.version }}</div>
            </td>
            <td>
              <span class="tag" :style="{ background: layerColor(m.layer) + '22', color: layerColor(m.layer) }">{{ m.layer }}</span>
            </td>
            <td>{{ m.type }}<div style="color:var(--text-3);font-size:11px">{{ typeNameOf(m) }}</div></td>
            <td>{{ m.engine }} <span v-if="isXcEngine(m.engine)" class="tag xc">信创</span></td>
            <td>{{ m.bizDomain }}</td>
            <td><span class="mono">{{ m.fields.length }}</span></td>
            <td><span class="st" :class="statusOf(m).cls"><span class="dot" />{{ statusOf(m).label }}</span></td>
            <td>{{ m.owner }}</td>
            <td>
              <button class="op-btn primary" @click="router.push(`/model/design/${m.id}`)">字段设计</button>
              <button class="op-btn" @click="tipVersion">版本</button>
              <button class="op-btn" @click="tipLineage(m)">血缘影响</button>
              <button class="op-btn" @click="openPhys(m)">{{ m.status === 'draft' ? '物理化建表' : '重新物理化' }}</button>
              <button class="op-btn danger" @click="removeRow(m)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的模型，请调整筛选条件</div>
    </div>

    <!-- 新建模型抽屉 -->
    <el-drawer v-model="createVisible" title="新建逻辑模型" size="440px">
      <div class="form-grid">
        <label class="f-item">模型名称 *
          <input v-model="form.name" class="kw" style="width:100%" placeholder="如：订单支付明细表" />
        </label>
        <label class="f-item">表名 *
          <input v-model="form.code" class="kw mono" style="width:100%" placeholder="dwd_order_pay_detail" />
          <span class="f-help">命名规范 NR-02：dwd_[业务域]_[业务过程]</span>
        </label>
        <label class="f-item">数仓分层
          <select v-model="form.layer" class="kw" style="width:100%">
            <option v-for="l in layers" :key="l.code" :value="l.code">{{ l.code }} {{ l.name }}</option>
          </select>
        </label>
        <label class="f-item">引擎
          <select v-model="form.engine" class="kw" style="width:100%">
            <option v-for="e in engines" :key="e.name" :value="e.name">{{ e.name }}</option>
          </select>
        </label>
        <label class="f-item">建模类型
          <select v-model="form.type" class="kw" style="width:100%">
            <option>事实表</option><option>维度表</option><option>宽表</option>
          </select>
        </label>
        <label class="f-item">业务域
          <select v-model="form.domain" class="kw" style="width:100%">
            <option v-for="d in domains" :key="d.name" :value="d.name">{{ d.name }}</option>
          </select>
        </label>
        <div class="lock-tip">{{ layerHint }}</div>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveCreate">创建并进入设计器</button>
        <button class="op-btn" @click="createVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 物理化建表弹窗 -->
    <el-dialog v-model="physVisible" :title="(physTarget?.status === 'draft' ? '物理化建表' : '重新物理化') + ' - ' + (physTarget?.code ?? '')" width="640px">
      <div class="form-grid" v-if="physTarget">
        <label class="f-item">目标引擎
          <select v-model="physEngine" class="kw" style="width:100%">
            <option v-for="e in engines" :key="e.name" :value="e.name">{{ e.name }}（{{ e.ddl }}）</option>
          </select>
        </label>
        <label class="f-item">执行方式
          <select v-model="physMode" class="kw" style="width:100%">
            <option value="exec">直接执行建表</option>
            <option value="script">导出DDL脚本（手工执行）</option>
          </select>
        </label>
      </div>
      <div class="f-label">DDL预览（一键生成，可编辑）</div>
      <pre class="code-box">{{ physDdl }}</pre>
      <template #footer>
        <button class="op-btn" @click="physVisible = false">取消</button>
        <button v-if="physMode === 'script'" class="op-btn" @click="download((physTarget?.code ?? 'model') + '.sql', physDdl)">⇩ 导出DDL</button>
        <button class="tb-new" @click="execPhys">执行建表</button>
      </template>
    </el-dialog>

    <!-- 逆向工程导入弹窗（对齐 prototype #/model/reverse） -->
    <el-dialog v-model="revVisible" title="逆向工程导入" width="680px">
      <div class="rev-hint">从已有数据库表反向生成逻辑模型（默认导入至 ODS 层，生成后可调整分层与字段）</div>
      <div class="f-label" style="margin-top:12px">第一步：选择数据源与库表</div>
      <table class="tbl">
        <thead>
          <tr><th>数据源</th><th>环境</th><th>状态</th><th style="width:110px">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="d in revSources" :key="d.id">
            <td><b>{{ d.name }}</b><div style="color:var(--text-3);font-size:11px">{{ d.type }} · {{ d.host }}</div></td>
            <td>{{ d.env }}</td>
            <td>
              <span class="pill" :class="d.status === 'enabled' ? 'ok' : 'off'">{{ d.status === 'enabled' ? '已启用' : '已停用' }}</span>
            </td>
            <td><a class="rev-link" @click="revScan(d)">扫描库表 →</a></td>
          </tr>
        </tbody>
      </table>

      <div v-if="revScanning && revDs" class="rev-scanning">正在扫描 {{ revDs.name }} ...</div>

      <template v-if="revScanned && revDs">
        <div class="f-label">第二步：选择要导入的表（{{ revDs.name }}）</div>
        <table class="tbl">
          <thead>
            <tr><th style="width:36px"></th><th>表名</th><th>字段数</th><th style="width:150px">业务域（可逐表覆盖）</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in revTables" :key="t.n">
              <td><input v-model="revSelected" type="checkbox" :value="t.n" /></td>
              <td><span class="mono">{{ t.n }}</span></td>
              <td>{{ t.c }}</td>
              <td>
                <input
                  v-model="revTableDomains[t.n]"
                  class="rev-domain-input"
                  :placeholder="domainFallback(t.n)"
                  :disabled="!revSelected.includes(t.n)"
                />
              </td>
            </tr>
          </tbody>
        </table>

        <div class="f-label" style="margin-top:12px">第三步：业务域批量标注</div>
        <div class="rev-domain-row">
          <input
            v-model="revDomain"
            class="rev-domain-input"
            style="flex:1"
            list="rev-domain-history"
            :placeholder="domainPlaceholder"
            @keydown.tab.prevent="fillLastDomain"
          />
          <datalist id="rev-domain-history">
            <option v-for="d in domainSuggestions" :key="d" :value="d" />
          </datalist>
          <span class="rev-tip" title="输入框默认显示上次使用的业务域：按 Tab 键快速填入上次名称；不填则默认使用上次业务域。可在上方表列表中逐表覆盖，留空沿用统一业务域。">ⓘ</span>
          <span class="rev-domain-cur">当前标注：<b>{{ revDomain.trim() || lastDomain || '公共' }}</b></span>
        </div>
      </template>

      <template #footer>
        <button class="op-btn" @click="revVisible = false">取消</button>
        <button class="tb-new" @click="revImport">导入生成逻辑模型</button>
      </template>
    </el-dialog>
    </div>
  </div>
</template>

<style scoped>
.head-card{padding:16px}
.head-top{display:flex;align-items:flex-start;gap:10px}
.head-title{font-size:16px;font-weight:700}
.head-sub{color:var(--text-3);font-size:12px;margin-top:2px}
.hint{color:var(--text-3);font-size:11.5px;margin-top:8px}
.spacer{flex:1}
.flow-row{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.flow-step{display:flex;flex-direction:column;font-size:12.5px}
.flow-step i{font-style:normal;color:var(--text-3);font-size:11px}
.flow-arrow{color:var(--text-3)}
.layer-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:12px}
.layer-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:12px 14px;cursor:pointer;box-shadow:var(--shadow)}
.layer-card:hover{border-color:var(--primary)}
.layer-card.on{border-color:var(--primary);box-shadow:0 0 0 2px var(--primary-light)}
.layer-num{font-size:22px;font-weight:700}
.layer-label{font-size:12.5px;margin-top:2px}
.layer-desc{font-size:11px;color:var(--text-3);margin-top:2px}
.domain-bar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:12px}
.domain-label{font-size:12.5px;color:var(--text-3)}
.chip{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-xl);padding:3px 12px;font-size:12px;cursor:pointer;color:var(--text-2)}
.chip.on{background:var(--primary-light);border-color:var(--primary);color:var(--primary);font-weight:600}
.banner-info{display:flex;gap:8px;align-items:flex-start;background:var(--info-bg);color:var(--info);border-radius:var(--radius);padding:10px 14px;font-size:12.5px;margin-top:12px}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:220px;outline:none}
.kw:focus{border-color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease);flex-shrink:0}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.tag{display:inline-block;border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600}
.tag.xc{background:rgba(217,119,6,.12);color:var(--warn)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.f-label{font-size:12px;color:var(--text-2);margin:12px 0 6px;font-weight:600}
.f-help{font-size:11px;color:var(--text-3)}
.lock-tip{background:var(--warn-bg);color:var(--warn);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px}
.rev-hint{color:var(--text-3);font-size:12px}
.rev-link{color:var(--primary);cursor:pointer;font-size:12px}
.rev-link:hover{text-decoration:underline}
.rev-scanning{color:var(--info);background:var(--info-bg);border-radius:var(--radius-sm);padding:8px 10px;font-size:12px;margin-top:10px}
.rev-domain-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.rev-domain-input{border:1px solid var(--border);border-radius:var(--radius-sm);padding:5px 8px;font-size:12px;background:#fff;color:var(--text-1);min-width:0;width:100%}
.rev-domain-input:focus{outline:none;border-color:var(--primary)}
.rev-domain-input:disabled{background:var(--bg-2, #f6f7f9);color:var(--text-3)}
.rev-tip{cursor:help;color:var(--text-3);font-size:13px;flex:none}
.rev-domain-cur{color:var(--text-3);font-size:12px;flex:none}
.code-box{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;background:#0d1424;color:#9fb2d0;border-radius:var(--radius);padding:12px;line-height:1.7;white-space:pre-wrap;max-height:260px;overflow:auto}
</style>
