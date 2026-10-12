<script setup lang="ts">
/**
 * M04 数仓建模列表（对齐 prototype m04-model.js #/model/list）
 * 分层统计卡 + 业务域标签双维筛选（可叠加、再点取消）；
 * 新建模型（草稿）；行操作：字段设计 / 版本 / 血缘影响 / 物理化建表 / 删除；逆向工程导入。
 * 数据：modelApi + datasourceApi（真实后端；isMock 时服务内部走演示文档）。
 */
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listModels, createModel, deleteModel, getModelDicts, getDdl, physicalize,
  reverseScan, reverseImport, reverseImportDdl,
  type ModelRow, type ModelDicts, type ModelListResp,
} from '../../services/modelApi'
import { listDataSources, type DsRow } from '../../services/datasourceApi'
import { useAuthStore } from '../../stores/auth'
import ListFilterPanel from '../../components/ListFilterPanel.vue'

const router = useRouter()
const auth = useAuthStore()

const models = ref<ModelRow[]>([])
const dicts = ref<ModelDicts>({ layers: [], domains: [], engines: [] })
const datasources = ref<DsRow[]>([])
const listStats = ref<ModelListResp>({ list: [], total: 0, layers: [], domains: [] })
const userName = ref(auth.account?.name ?? auth.current.name)

const layers = computed(() => dicts.value.layers)
const domains = computed(() => dicts.value.domains)
const engines = computed(() => dicts.value.engines)

const keyword = ref('')
const filters = ref<Record<string, string>>({ layer: '', status: '', domain: '' })

/* reload 竞态序号：防抖/操作触发的并发 reload 后写胜出（晚到响应丢弃） */
let reloadSeq = 0

async function reloadModels() {
  const seq = ++reloadSeq
  try {
    const ls = await listModels({ keyword: keyword.value || undefined })
    if (seq !== reloadSeq) return
    models.value = ls.list
    listStats.value = ls
  } catch (e) {
    if (seq === reloadSeq) ElMessage.error((e as Error).message)
  }
}

async function reload() {
  const seq = ++reloadSeq
  try {
    const [ls, ds, srcs] = await Promise.all([
      listModels({ keyword: keyword.value || undefined }),
      getModelDicts(),
      listDataSources(),
    ])
    if (seq !== reloadSeq) return
    models.value = ls.list
    listStats.value = ls
    dicts.value = ds
    datasources.value = srcs
  } catch (e) {
    if (seq === reloadSeq) ElMessage.error((e as Error).message)
  }
}

/* 关键字为服务端统计维度（listStats 随 keyword 刷新）；输入防抖后重查（字典/数据源本页无变更路径，不重拉） */
let kwTimer: number | undefined
watch(keyword, () => {
  window.clearTimeout(kwTimer)
  kwTimer = window.setTimeout(() => { void reloadModels() }, 300)
})
onUnmounted(() => window.clearTimeout(kwTimer))

onMounted(reload)

/* ---- 左侧筛选面板：分层/状态 facet（业务域保留原统计卡+域标签交互，避免重复入口） ---- */
const facets = computed(() => [
  { key: 'layer', label: '数仓分层', options: layers.value.map((l) => ({ v: l.code, t: l.code })) },
  {
    key: 'status',
    label: '状态',
    options: [
      { v: 'draft', t: '草稿' },
      { v: 'published', t: '已发布' },
      { v: 'built', t: '已物理化' },
      { v: 'produced', t: '已投产' },
    ],
  },
])

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
    return [m.id, m.name, m.code, m.bizDomain, m.owner].some((s) => String(s).toLowerCase().includes(kw))
  })
})

/* 双维统计取服务端 facet（listStats 随 keyword 维度刷新），不再叠加本地筛选条件 */
function layerCount(code: string): number {
  return listStats.value.layers.find((l) => l.code === code)?.count ?? 0
}
function domainCount(name: string): number {
  return listStats.value.domains.find((d) => d.name === name)?.count ?? 0
}
const allCount = computed(() => listStats.value.total)

function layerColor(code: string): string {
  return layers.value.find((l) => l.code === code)?.color ?? '#64748b'
}
function isXcEngine(name: string): boolean {
  return dicts.value.engines.find((e) => e.name === name)?.xc ?? false
}
function statusOf(m: ModelRow): { cls: string; label: string } {
  if (m.status === 'draft') return { cls: 'st-gray', label: '草稿' }
  if (m.status === 'published') return { cls: 'st-blue', label: '已发布' }
  if (m.status === 'built') return { cls: 'st-green', label: '已物理化' }
  return { cls: 'st-green', label: '已投产' }
}
function typeNameOf(m: ModelRow): string {
  if (m.type === '事实表') return '星型模型（事务事实）'
  if (m.type === '维度表') return '星型模型（维度）'
  if (m.type === '宽表') return '宽表模型'
  return '明细表'
}

/* ---- 新建模型（草稿） ---- */
const createVisible = ref(false)
const form = ref({ name: '', code: '', layer: 'ODS', engine: '', type: '事实表', domain: '' })

function openCreate() {
  /* 默认值取字典首项（真实字典与演示默认不一定一致） */
  form.value = {
    name: '', code: '',
    layer: layers.value[0]?.code ?? 'ODS',
    engine: engines.value[0]?.name ?? '',
    type: '事实表',
    domain: domains.value[0]?.name ?? '',
  }
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
  try {
    await createModel({
      name: form.value.name.trim(),
      code: form.value.code.trim(),
      layer: form.value.layer,
      engine: form.value.engine,
      type: form.value.type,
      bizDomain: form.value.domain,
    })
    createVisible.value = false
    ElMessage.success('草稿已创建')
    await reloadModels()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

/* ---- 物理化建表 / 重新物理化 ---- */
const physVisible = ref(false)
const physMode = ref('exec')
const physEngine = ref('')
const physTarget = ref<ModelRow | null>(null)
const physDsId = ref<number | null>(null)
const physDb = ref('')
const physDdl = ref('')
const physDsOptions = computed(() =>
  datasources.value.filter((d) => d.type === 'mysql' || d.type === 'greatdb'))

function ddlOf(name: string): string {
  return dicts.value.engines.find((e) => e.name === name)?.ddl ?? 'mysql'
}

async function loadPhysDdl() {
  const m = physTarget.value
  if (!m) return
  const myEngine = physEngine.value
  try {
    const r = await getDdl(m.id, ddlOf(myEngine))
    if (myEngine !== physEngine.value) return
    physDdl.value = r.ddl
  } catch (e) {
    if (myEngine !== physEngine.value) return
    physDdl.value = ''
    ElMessage.error((e as Error).message)
  }
}

async function openPhys(m: ModelRow) {
  physTarget.value = m
  physEngine.value = m.engine
  physMode.value = 'exec'
  /* 预填数据源：不属于连接型（mysql/greatdb）时置空，避免 select 空白无提示 */
  physDsId.value = physDsOptions.value.some((d) => d.id === m.dsId) ? m.dsId : null
  physDb.value = m.dbName ?? ''
  physVisible.value = true
  await loadPhysDdl()
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
  if (!physDsId.value) {
    ElMessage.warning('请选择目标数据源')
    return
  }
  try {
    const r = await physicalize(m.id, {
      engine: ddlOf(physEngine.value),
      dsId: physDsId.value,
      dbName: physDb.value || undefined,
      mode: 'exec',
    })
    physVisible.value = false
    ElMessage.success(`建表成功（执行 ${r.executed ?? 1} 条语句）`)
    await reloadModels()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

async function downloadScript() {
  const m = physTarget.value
  if (!m) return
  try {
    const r = await physicalize(m.id, { engine: ddlOf(physEngine.value), mode: 'script' })
    if (!r.script) {
      ElMessage.warning('后端未返回脚本，无法下载')
      return
    }
    download((m.code || 'model') + '.sql', r.script)
    ElMessage.success('DDL 脚本已生成并下载')
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

/* ---- 删除（二次确认） ---- */
async function removeRow(m: ModelRow) {
  try {
    await ElMessageBox.confirm(`确认删除模型「${m.code}」？`, '删除模型', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteModel(m.id)
    ElMessage.success('已删除')
    await reloadModels()
  } catch (e) {
    ElMessage.error((e as Error).message)
  }
}

/* ---- AI 建表助手（R2 规划中：按钮 disabled，click 不可达） ---- */
function aiTip() {
  ElMessage.info('AI 建表助手规划中，敬请期待')
}

/* ---- 逆向工程导入（对齐 prototype m04-model.js #/model/reverse L504-542） ---- */
const revVisible = ref(false)
const revStep = ref<'pick' | 'file'>('pick')
const revDsId = ref<number | null>(null)
const revDb = ref('')
const revLoading = ref(false)
const revImporting = ref(false)
const revScanned = ref(false)
const revTables = ref<{ tb: string; comment: string; rows: number; cols: number; picked: boolean }[]>([])
const revLayer = ref('ODS')
const imported = ref<{ imported: number; skipped: { tb: string; reason: string }[] } | null>(null)
const revDsOptions = computed(() => datasources.value.filter((d) => d.type !== 'file'))

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

/* 扫描会话序号：openReverse 重开/再次扫描使晚到的旧扫描响应失效，不污染新会话 */
let scanSeq = 0

function openReverse() {
  scanSeq++
  revStep.value = 'pick'
  revDsId.value = null
  revDb.value = ''
  revLoading.value = false
  revImporting.value = false
  revScanned.value = false
  revTables.value = []
  revLayer.value = 'ODS'
  revDomain.value = ''
  revTableDomains.value = {}
  imported.value = null
  revVisible.value = true
}

async function doScan() {
  if (!revDsId.value) {
    ElMessage.warning('请选择数据源')
    return
  }
  const seq = ++scanSeq
  revLoading.value = true
  try {
    const r = await reverseScan({ dsId: revDsId.value, dbName: revDb.value || undefined })
    if (seq !== scanSeq) return
    revTables.value = r.tables.map((t) => ({ ...t, picked: false }))
    revScanned.value = true
  } catch (e) {
    if (seq !== scanSeq) return
    ElMessage.error((e as Error).message)
  } finally {
    if (seq === scanSeq) revLoading.value = false
  }
}

async function doImport() {
  const picked = revTables.value.filter((t) => t.picked)
  if (!picked.length) {
    ElMessage.warning('请勾选要导入的表')
    return
  }
  if (!revDsId.value) {
    ElMessage.warning('请选择数据源')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认将选中的 ${picked.length} 张表反向生成为逻辑模型（${revLayer.value} 层）？生成后可调整分层与字段。`,
      '导入确认',
      { confirmButtonText: '导入', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  try {
    revImporting.value = true
    imported.value = await reverseImport({
      dsId: revDsId.value,
      dbName: revDb.value || undefined,
      tables: picked.map((t) => ({ tb: t.tb, layer: revLayer.value, bizDomain: domainOf(t.tb) })),
    })
    /* 记录本次统一标注的业务域为"上次使用"（下次导入 Tab 快速填入） */
    if (revDomain.value.trim()) rememberDomain(revDomain.value)
    await reloadModels()
    ElMessage.success(`导入 ${imported.value.imported} 张，跳过 ${imported.value.skipped.length} 张`)
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    revImporting.value = false
  }
}

async function doImportDdl(file: File) {
  try {
    revImporting.value = true
    imported.value = await reverseImportDdl(file)
    await reloadModels()
    ElMessage.success(`导入 ${imported.value!.imported} 张，跳过 ${imported.value!.skipped.length} 张`)
  } catch (e) {
    ElMessage.error((e as Error).message)
  } finally {
    revImporting.value = false
  }
}

async function onDdlFile(e: Event) {
  const input = e.target as HTMLInputElement
  const f = input.files?.[0]
  input.value = ''
  if (f) await doImportDdl(f)
}

function tipVersion(m: ModelRow) {
  router.push(`/model/version/${m.id}`)
}
function tipLineage(m: ModelRow) {
  router.push(`/model/lineage/${m.id}`)
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
        <el-tooltip content="规划中" placement="top">
          <span class="op-wrap"><button class="op-btn" disabled @click="aiTip">✦ AI 建表助手</button></span>
        </el-tooltip>
        <button class="op-btn" @click="openReverse">逆向工程导入</button>
      </div>
      <div class="hint">操作指引：① 点击分层统计卡与业务域标签可双维筛选（再点取消）；② 「新建模型」创建草稿，列表「字段设计」进入设计器（三阶段：概念→逻辑→物理）；③ 「ER 设计器」直达实体关系画布；④ 物理化后模型进入版本管理与血缘影响分析。</div>
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
        <div class="layer-desc">{{ l.rule }}</div>
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
            <td class="mono">-</td>
            <td><span class="st" :class="statusOf(m).cls"><span class="dot" />{{ statusOf(m).label }}</span></td>
            <td>{{ m.owner || userName }}</td>
            <td>
              <button class="op-btn primary" @click="router.push(`/model/design/${m.id}`)">字段设计</button>
              <button class="op-btn" @click="tipVersion(m)">版本</button>
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
        <button class="tb-new" @click="saveCreate">创建草稿</button>
        <button class="op-btn" @click="createVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 物理化建表弹窗 -->
    <el-dialog v-model="physVisible" :title="(physTarget?.status === 'draft' ? '物理化建表' : '重新物理化') + ' - ' + (physTarget?.code ?? '')" width="640px">
      <div class="form-grid" v-if="physTarget">
        <label class="f-item">目标引擎
          <select v-model="physEngine" class="kw" style="width:100%" @change="loadPhysDdl">
            <option v-for="e in engines" :key="e.name" :value="e.name">{{ e.name }}（{{ e.ddl }}）</option>
          </select>
        </label>
        <label class="f-item">目标数据源（仅 MySQL/GreatDB）*
          <select v-model="physDsId" class="kw" style="width:100%">
            <option :value="null" disabled>请选择数据源</option>
            <option v-for="d in physDsOptions" :key="d.id" :value="d.id">{{ d.name }}（{{ d.type }} · {{ d.host ?? '-' }}）</option>
          </select>
        </label>
        <label class="f-item">目标库名
          <input v-model="physDb" class="kw mono" style="width:100%" placeholder="留空使用数据源默认库" />
        </label>
        <label class="f-item">执行方式
          <select v-model="physMode" class="kw" style="width:100%">
            <option value="exec">直接执行建表</option>
            <option value="script">导出DDL脚本（手工执行）</option>
          </select>
        </label>
      </div>
      <div class="f-label">DDL 预览（后端生成）</div>
      <pre class="code-box">{{ physDdl }}</pre>
      <template #footer>
        <button class="op-btn" @click="physVisible = false">取消</button>
        <button v-if="physMode === 'script'" class="op-btn" @click="downloadScript">⇩ 导出DDL</button>
        <button class="tb-new" @click="execPhys">执行建表</button>
      </template>
    </el-dialog>

    <!-- 逆向工程导入弹窗（对齐 prototype #/model/reverse） -->
    <el-dialog v-model="revVisible" title="逆向工程导入" width="680px">
      <div class="rev-hint">从已有数据库表反向生成逻辑模型（默认导入至 ODS 层，生成后可调整分层与字段）</div>
      <div class="rev-tabs">
        <button class="chip" :class="{ on: revStep === 'pick' }" @click="revStep = 'pick'">数据库扫描导入</button>
        <button class="chip" :class="{ on: revStep === 'file' }" @click="revStep = 'file'">DDL 文件导入</button>
      </div>

      <template v-if="revStep === 'pick'">
        <div class="f-label" style="margin-top:12px">第一步：选择数据源与库表</div>
        <div class="rev-scan-row">
          <select v-model="revDsId" class="rev-domain-input" style="flex:1">
            <option :value="null" disabled>请选择数据源（连接型）</option>
            <option v-for="d in revDsOptions" :key="d.id" :value="d.id">{{ d.name }}（{{ d.type }} · {{ d.host ?? '-' }}）</option>
          </select>
          <input v-model="revDb" class="rev-domain-input" style="flex:none;width:150px" placeholder="库名（可留空）" />
          <button class="op-btn" :disabled="revLoading" @click="doScan">{{ revLoading ? '扫描中…' : '扫描库表' }}</button>
        </div>
        <div v-if="revLoading" class="rev-scanning">正在扫描所选数据源 ...</div>

        <template v-if="revScanned">
          <div class="f-label">第二步：选择要导入的表{{ revTables.length ? `（共 ${revTables.length} 张）` : '' }}</div>
          <table v-if="revTables.length" class="tbl">
            <thead>
              <tr><th style="width:36px"></th><th>表名</th><th>注释</th><th>列数</th><th>行数估</th><th style="width:150px">业务域（可逐表覆盖）</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in revTables" :key="t.tb">
                <td><input v-model="t.picked" type="checkbox" /></td>
                <td><span class="mono">{{ t.tb }}</span></td>
                <td>{{ t.comment }}</td>
                <td>{{ t.cols }}</td>
                <td class="mono">{{ t.rows }}</td>
                <td>
                  <input
                    v-model="revTableDomains[t.tb]"
                    class="rev-domain-input"
                    :placeholder="domainFallback(t.tb)"
                    :disabled="!t.picked"
                  />
                </td>
              </tr>
            </tbody>
          </table>
          <div v-else class="empty">未扫描到表，请确认库名或数据源配置</div>
        </template>

        <template v-if="revScanned && revTables.length">
          <div class="f-label" style="margin-top:12px">第三步：导入分层与业务域批量标注</div>
          <div class="rev-domain-row">
            <select v-model="revLayer" class="rev-domain-input" style="flex:none;width:150px" title="导入分层">
              <option v-for="l in layers" :key="l.code" :value="l.code">{{ l.code }} {{ l.name }}</option>
            </select>
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
      </template>

      <template v-else>
        <div class="f-label" style="margin-top:12px">DDL 文件导入</div>
        <div class="rev-file-row">
          <label class="op-btn rev-file-btn" :class="{ off: revImporting }">⇩ 选择 .sql 文件
            <input type="file" accept=".sql" style="display:none" @change="onDdlFile" />
          </label>
          <span class="rev-tip">上传包含 CREATE TABLE 语句的 DDL 文件，解析后反向生成逻辑模型（超时 15s）</span>
        </div>
      </template>

      <div v-if="imported" class="rev-imported">
        <div class="f-label" style="margin:0 0 6px">导入结果</div>
        <div style="font-size:12.5px">成功导入 <b>{{ imported.imported }}</b> 张，跳过 <b>{{ imported.skipped.length }}</b> 张</div>
        <table v-if="imported.skipped.length" class="tbl" style="margin-top:8px">
          <thead><tr><th>跳过表</th><th>原因</th></tr></thead>
          <tbody>
            <tr v-for="s in imported.skipped" :key="s.tb">
              <td><span class="mono">{{ s.tb }}</span></td>
              <td>{{ s.reason }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <template #footer>
        <button class="op-btn" @click="revVisible = false">关闭</button>
        <button v-if="revStep === 'pick'" class="tb-new" :disabled="revImporting" @click="doImport">{{ revImporting ? '导入中…' : '导入所选' }}</button>
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
.op-wrap{display:inline-flex}
.op-btn:disabled{opacity:.5;cursor:not-allowed}
.tb-new:disabled{opacity:.5;cursor:not-allowed}
.rev-file-btn.off{pointer-events:none;opacity:.5;cursor:not-allowed}
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
.rev-tabs{display:flex;gap:6px;margin-top:10px}
.rev-scan-row{display:flex;gap:8px;align-items:center}
.rev-scan-row .op-btn{flex:none;white-space:nowrap}
.rev-hint{color:var(--text-3);font-size:12px}
.rev-file-row{display:flex;align-items:center;gap:10px}
.rev-file-btn{cursor:pointer;white-space:nowrap}
.rev-imported{border:1px solid var(--border);border-radius:var(--radius-sm);padding:10px 12px;margin-top:12px}
.rev-scanning{color:var(--info);background:var(--info-bg);border-radius:var(--radius-sm);padding:8px 10px;font-size:12px;margin-top:10px}
.rev-domain-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}
.rev-domain-input{border:1px solid var(--border);border-radius:var(--radius-sm);padding:5px 8px;font-size:12px;background:#fff;color:var(--text-1);min-width:0;width:100%}
.rev-domain-input:focus{outline:none;border-color:var(--primary)}
.rev-domain-input:disabled{background:var(--bg-2, #f6f7f9);color:var(--text-3)}
.rev-tip{cursor:help;color:var(--text-3);font-size:13px;flex:none}
.rev-domain-cur{color:var(--text-3);font-size:12px;flex:none}
.code-box{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;background:#0d1424;color:#9fb2d0;border-radius:var(--radius);padding:12px;line-height:1.7;white-space:pre-wrap;max-height:260px;overflow:auto}
</style>
