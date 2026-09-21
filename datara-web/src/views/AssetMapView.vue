<script setup lang="ts">
/**
 * M09 数据资产地图（todo 11 · F55）
 * 多维归类浏览数据资产：按业务域（默认）/ 按数仓分层 / 按模块 / 框图。
 * - 按业务域：组标题=域名（色点），组内表卡片：表名/引擎/字段数/质量分入口
 * - 按数仓分层：ODS/DIM/DWD/DWS/ADS 分组，同款表卡片
 * - 按模块：数据表/指标/标准/报告 大类卡片（含纳管样本与入口）
 * - 框图：大框=业务域（表数/列数/记录数 + 事实表/维表/字典统计），小框=表，底部=码表编码数；
 *   末尾独立大框「码表标准（字典）」列出各码表编码项数与引用处数
 * 数据源 = dataStore（metaTables/bizDomains/models/indicators/stdElements/stdCodes），
 * 标签不写入图文档（metaTags 独立集合，约束 M1）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { dataStore } from '../services/mock/dataStore'
import type { BizDomain, Indicator, MetaTable, Model, StdElement, StdCode, StdMapping } from '../services/types'

const router = useRouter()

const view = ref<'domain' | 'layer' | 'category' | 'box'>('domain')

const tables = ref<MetaTable[]>([])
const domains = ref<BizDomain[]>([])
const models = ref<Model[]>([])
const indicators = ref<Indicator[]>([])
const stdElements = ref<StdElement[]>([])
const stdCodes = ref<StdCode[]>([])
const stdMappings = ref<StdMapping[]>([])

const LAYERS = ['ODS', 'DIM', 'DWD', 'DWS', 'ADS'] as const
const LAYER_COLOR: Record<string, string> = {
  ODS: '#0891b2', DIM: '#d97706', DWD: '#1668dc', DWS: '#7c3aed', ADS: '#16a34a',
}

async function reload() {
  tables.value = [...((await dataStore.list<MetaTable>('metaTables')) ?? [])]
  domains.value = [...((await dataStore.list<BizDomain>('bizDomains')) ?? [])]
  models.value = [...((await dataStore.list<Model>('models')) ?? [])]
  indicators.value = [...((await dataStore.list<Indicator>('indicators')) ?? [])]
  stdElements.value = [...((await dataStore.list<StdElement>('stdElements')) ?? [])]
  stdCodes.value = [...((await dataStore.list<StdCode>('stdCodes')) ?? [])]
  stdMappings.value = [...((await dataStore.list<StdMapping>('stdMappings')) ?? [])]
}

onMounted(reload)

function modelOf(t: MetaTable) {
  return models.value.find((m) => m.code === t.name)
}

function engineOf(t: MetaTable) {
  return modelOf(t)?.engine ?? 'Apache Doris'
}

function fieldCountOf(t: MetaTable) {
  return modelOf(t)?.fields.length ?? 0
}

function fmt(n: number) {
  if (n >= 10000) return (n / 10000).toFixed(n >= 1000000 ? 1 : 0) + '万'
  return String(n)
}

function goScore(table: string) {
  // 质量分入口 → 细项质量报告（表级），携带表名直达
  router.push({ path: '/qc/report-table', query: { table } })
}

function goCatalog() {
  router.push('/meta/catalog')
}

function goIndicators() {
  router.push('/ind/list')
}

function goStd() {
  router.push('/std/element')
}

/* ---- 按业务域 ---- */
const domainGroups = computed(() =>
  domains.value
    .filter((d) => tables.value.some((t) => t.domain === d.name))
    .map((d) => ({
      domain: d,
      items: tables.value.filter((t) => t.domain === d.name),
    })))

/* ---- 按数仓分层 ---- */
const layerGroups = computed(() =>
  LAYERS.map((l) => ({
    layer: l,
    items: tables.value.filter((t) => t.layer === l),
  })))

/* ---- 按模块 ---- */
const reportDemo = ['经营日报', '支付渠道分析', '运营周报', '用户活跃分析']
const categoryGroups = computed(() => [
  {
    name: '数据表', icon: '▤', color: '#1668dc', cnt: tables.value.length, unit: '张',
    link: goCatalog, linkTxt: '进入元数据目录',
    items: tables.value.slice(0, 5).map((t) => t.name),
  },
  {
    name: '指标', icon: '✦', color: '#7c3aed', cnt: indicators.value.length, unit: '项',
    link: goIndicators, linkTxt: '指标目录',
    items: indicators.value.slice(0, 5).map((i) => `${i.name}（${i.id}）`),
  },
  {
    name: '标准', icon: '§', color: '#16a34a',
    cnt: stdElements.value.length + stdCodes.value.length, unit: '项',
    link: goStd, linkTxt: '标准管理',
    items: stdElements.value.slice(0, 3).map((s) => `${s.cn} ${s.en}`)
      .concat(stdCodes.value.slice(0, 2).map((c) => `${c.name}（${c.id}）`)),
  },
  {
    name: '报告', icon: '◫', color: '#d97706', cnt: reportDemo.length, unit: '份',
    link: null, linkTxt: '', items: reportDemo,
  },
])

/* ---- 框图（大框=业务域，小框=表；每表只算一次 modelOf 避免重复计算） ---- */
const boxDomains = computed(() =>
  domains.value
    .map((d) => {
      const tbls = tables.value
        .filter((t) => t.domain === d.name)
        .map((t) => {
          const m = modelOf(t)
          return {
            id: t.id,
            name: t.name,
            layer: t.layer,
            rows: t.rows,
            cols: m?.fields.length ?? 0,
            engine: m?.engine ?? 'Apache Doris',
            isFact: m?.type === '事实表',
            isDim: m?.type === '维度表' || t.layer === 'DIM',
          }
        })
      const tblNames = new Set(tbls.map((t) => t.name))
      const stdIdSet = new Set(
        stdMappings.value.filter((m) => tblNames.has(m.table)).map((m) => m.stdId))
      const chips = [...stdIdSet]
        .map((id) => stdCodes.value.find((c) => c.id === id))
        .filter((c): c is StdCode => !!c)
        .map((c) => ({ id: c.id, name: c.name, vals: c.values.length }))
      return {
        domain: d,
        items: tbls,
        cols: tbls.reduce((s, t) => s + t.cols, 0),
        rows: tbls.reduce((s, t) => s + t.rows, 0),
        fact: tbls.filter((t) => t.isFact).length,
        dim: tbls.filter((t) => t.isDim).length,
        dictCnt: stdIdSet.size,
        chips,
      }
    })
    .filter((g) => g.items.length > 0))

const totalRows = computed(() => tables.value.reduce((s, t) => s + t.rows, 0))
</script>

<template>
  <div class="map-page">
    <div class="map-toolbar">
      <div class="seg">
        <button :class="{ on: view === 'domain' }" @click="view = 'domain'">按业务域</button>
        <button :class="{ on: view === 'layer' }" @click="view = 'layer'">按数仓分层</button>
        <button :class="{ on: view === 'category' }" @click="view = 'category'">按模块</button>
        <button :class="{ on: view === 'box' }" @click="view = 'box'">框图</button>
      </div>
      <span class="hint">
        {{ domains.length }} 个业务域 · {{ LAYERS.length }} 个分层 · {{ tables.length }} 张表 · 共 {{ fmt(totalRows) }} 行
      </span>
    </div>

    <!-- 按业务域 -->
    <div v-if="view === 'domain'" class="map-body">
      <div class="legend">按业务域归类 · 组标题=域名 · 表卡片：表名 / 引擎 / 字段数 / 质量分入口</div>
      <div class="cols">
        <div v-for="g in domainGroups" :key="g.domain.name" class="col">
          <div class="col-head">
            <span class="dot" :style="{ background: g.domain.color }" />
            <b>{{ g.domain.name }}</b>
            <span class="cnt">{{ g.items.length }} 张</span>
          </div>
          <div class="col-desc">{{ g.domain.desc }}</div>
          <div v-for="t in g.items" :key="t.id" class="tbl-card">
            <div class="tbl-name mono" @click="goCatalog">{{ t.name }}</div>
            <div class="tbl-meta">
              <span>{{ engineOf(t) }}</span>
              <span>{{ fieldCountOf(t) }} 字段</span>
              <button class="score-btn" @click="goScore(t.name)">质量分</button>
            </div>
          </div>
        </div>
      </div>
      <div class="lock-tip">业务域由主题域标签自动归类（采集时按命名规则映射），可在元数据目录中调整表的主题域归属。</div>
    </div>

    <!-- 按数仓分层 -->
    <div v-else-if="view === 'layer'" class="map-body">
      <div class="legend">按数据分层归类 · 每列一个分层（ODS/DIM/DWD/DWS/ADS） · 表卡片：表名 / 引擎 / 字段数 / 质量分入口</div>
      <div class="cols">
        <div v-for="g in layerGroups" :key="g.layer" class="col">
          <div class="col-head">
            <span class="layer-tag" :style="{ background: LAYER_COLOR[g.layer] + '18', color: LAYER_COLOR[g.layer] }">{{ g.layer }}</span>
            <span class="cnt">{{ g.items.length }} 张</span>
          </div>
          <div v-for="t in g.items" :key="t.id" class="tbl-card">
            <div class="tbl-name mono" @click="goCatalog">{{ t.name }}</div>
            <div class="tbl-meta">
              <span>{{ engineOf(t) }}</span>
              <span>{{ fieldCountOf(t) }} 字段</span>
              <button class="score-btn" @click="goScore(t.name)">质量分</button>
            </div>
          </div>
          <div v-if="!g.items.length" class="empty">暂无</div>
        </div>
      </div>
      <div class="lock-tip">各层语义：ODS 原样接入 · DIM 公共维度 · DWD 明细加工 · DWS 轻度汇总 · ADS 应用宽表。</div>
    </div>

    <!-- 按模块 -->
    <div v-else-if="view === 'category'" class="map-body">
      <div class="legend">按资产大类归类：数据表 / 指标 / 标准 / 报告 · 每类卡片列出纳管样本与入口链接</div>
      <div class="cat-grid">
        <div v-for="c in categoryGroups" :key="c.name" class="cat-card">
          <div class="cat-head">
            <h3><span class="dot" :style="{ background: c.color }" />{{ c.name }}</h3>
            <span class="layer-tag" :style="{ background: c.color + '18', color: c.color }">{{ c.cnt }} {{ c.unit }}</span>
          </div>
          <div class="cat-body">
            <div v-for="it in c.items" :key="it" class="cat-item">
              <span>{{ c.icon }}</span><span class="mono">{{ it }}</span>
            </div>
            <button v-if="c.link" class="cat-link" @click="c.link">{{ c.linkTxt }} →</button>
          </div>
        </div>
      </div>
      <div class="lock-tip">报告类为演示数据：正式报告资产将在 BI/报表模块纳管后自动归入；指标/标准数量来自指标管理与数据标准登记。</div>
    </div>

    <!-- 框图 -->
    <div v-else-if="view === 'box'" class="map-body">
      <div class="legend">框图视图 · 大框=业务域（表数 / 列数 / 记录数 + 事实表 / 维表 / 字典统计） · 小框=数据表（列数 / 行数 / 引擎） · 大框底部=业务类型及码表编码数</div>
      <div class="box-grid">
        <div v-for="g in boxDomains" :key="g.domain.name" class="box-domain" :style="{ borderLeftColor: g.domain.color }">
          <div class="box-head">
            <span class="dot" :style="{ background: g.domain.color }" />
            <b>{{ g.domain.name }}</b>
            <span class="box-stat">
              <span class="box-badge">表 {{ g.items.length }}</span>
              <span class="box-badge">列 {{ g.cols }}</span>
              <span class="box-badge">记录 {{ fmt(g.rows) }}</span>
            </span>
          </div>
          <div class="box-stat box-line2">
            <span class="box-badge fact">事实表 {{ g.fact }}</span>
            <span class="box-badge dimb">维表 {{ g.dim }}</span>
            <span class="box-badge dictb">字典 {{ g.dictCnt }}</span>
          </div>
          <div class="box-tbls">
            <div v-for="t in g.items" :key="t.id" class="box-tbl">
              <div class="box-tbl-top">
                <span class="tbl-name mono" @click="goCatalog">{{ t.name }}</span>
                <span class="layer-tag" :style="{ background: LAYER_COLOR[t.layer] + '18', color: LAYER_COLOR[t.layer] }">{{ t.layer }}</span>
              </div>
              <div class="box-tbl-meta">
                <span>{{ t.cols }} 列</span>
                <span>{{ fmt(t.rows) }} 行</span>
                <span class="box-engine">{{ t.engine }}</span>
              </div>
            </div>
          </div>
          <div class="box-foot">
            <span class="box-foot-label">业务类型及编码数</span>
            <span v-if="g.chips.length" class="box-chips">
              <span v-for="c in g.chips" :key="c.id" class="box-chip">{{ c.name }} {{ c.vals }}</span>
            </span>
            <span v-else class="box-none">未关联码表</span>
          </div>
        </div>

        <div class="box-domain std-box" style="border-left-color:#16a34a">
          <div class="box-head">
            <span class="dot" style="background:#16a34a" />
            <b>码表标准（字典）</b>
            <span class="box-stat">
              <span class="box-badge">共 {{ stdCodes.length }} 类业务类型</span>
            </span>
          </div>
          <div class="box-tbls">
            <div v-for="c in stdCodes" :key="c.id" class="box-tbl">
              <div class="box-tbl-top"><span class="box-code-name">{{ c.name }}</span></div>
              <div class="box-tbl-meta">
                <span>编码 {{ c.values.length }} 项</span>
                <span>引用 {{ c.used }} 处</span>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="lock-tip">口径：列数=表关联模型的字段数合计 · 记录数=表行数合计 · 事实/维表按模型类型或 DIM 层判定 · 字典=域内表在标准映射中关联到的去重码表数。</div>
    </div>
  </div>
</template>

<style scoped>
.map-page{height:100%;display:flex;flex-direction:column}
.map-toolbar{display:flex;align-items:center;gap:12px;padding:10px 16px;border-bottom:1px solid var(--border);background:#fff;z-index:5}
/* 现代分段控件（AntD segmented：灰底容器 + 白底浮起 active） */
.seg{display:flex;gap:2px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:2px}
.seg button{border:none;background:transparent;padding:5px 14px;font-size:12px;cursor:pointer;color:var(--text-2);border-radius:var(--radius-sm);transition:all var(--dur-base) var(--ease);min-height:28px}
.seg button:hover{color:var(--text)}
.seg button.on{background:#fff;color:var(--primary);font-weight:600;box-shadow:0 1px 3px rgba(16,24,40,.14)}
.hint{margin-left:auto;font-size:11.5px;color:var(--text-3)}
.map-body{flex:1;overflow:auto;padding:14px 16px}
.legend{font-size:11.5px;color:var(--text-3);margin-bottom:10px}
.lock-tip{margin-top:12px;font-size:11px;color:var(--text-3);background:var(--bg);border-radius:var(--radius-sm);padding:8px 10px}
.cols{display:flex;gap:12px;align-items:stretch;overflow:auto}
.col{flex:1;min-width:216px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-lg);padding:10px;transition:border-color var(--dur-base) var(--ease),box-shadow var(--dur-base) var(--ease)}
.col:hover{border-color:var(--border-strong);box-shadow:var(--shadow)}
.col-head{display:flex;align-items:center;gap:7px;margin-bottom:5px}
.col-head b{font-size:12.5px}
.dot{width:9px;height:9px;border-radius:3px;flex-shrink:0}
.cnt{margin-left:auto;font-size:11px;color:var(--text-3)}
.col-desc{font-size:10.5px;color:var(--text-3);margin-bottom:9px}
.layer-tag{border-radius:4px;padding:1px 7px;font-size:11px;font-weight:600}
.tbl-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius-sm);padding:7px 9px;margin-bottom:7px;transition:border-color var(--dur-fast) var(--ease),box-shadow var(--dur-fast) var(--ease),transform var(--dur-fast) var(--ease)}
.tbl-card:hover{border-color:rgba(22,104,220,.45);box-shadow:var(--shadow);transform:translateY(-1px)}
.tbl-name{font-size:11.5px;cursor:pointer;color:var(--text)}
.tbl-name:hover{color:var(--primary)}
.tbl-meta{display:flex;align-items:center;gap:8px;margin-top:4px;font-size:10.5px;color:var(--text-3)}
.score-btn{margin-left:auto;border:1px solid rgba(22,104,220,.4);background:#fff;color:var(--primary);border-radius:4px;padding:2px 8px;font-size:10.5px;cursor:pointer;transition:all var(--dur-fast) var(--ease)}
.score-btn:hover{background:var(--primary);color:#fff;box-shadow:var(--shadow-primary)}
.empty{padding:10px;text-align:center;color:var(--text-3);font-size:11.5px}
.cat-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.cat-card{background:#fff;border:1px solid var(--border);border-radius:var(--radius-lg);overflow:hidden;transition:border-color var(--dur-base) var(--ease),box-shadow var(--dur-base) var(--ease),transform var(--dur-base) var(--ease)}
.cat-card:hover{border-color:rgba(22,104,220,.45);box-shadow:var(--shadow-md);transform:translateY(-2px)}
.cat-head{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid var(--border)}
.cat-head h3{font-size:13px;margin:0;display:flex;align-items:center;gap:7px}
.cat-body{padding:10px 12px}
.cat-item{display:flex;gap:8px;align-items:center;margin-bottom:7px;font-size:11.5px;color:var(--text-2)}
.cat-item .mono{flex:1;font-size:11.5px}
.cat-link{margin-top:4px;border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:5px 14px;font-size:11.5px;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.cat-link:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
/* ---- 框图 ---- */
.box-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
.box-domain{background:#fff;border:1px solid var(--border);border-left:4px solid var(--border);border-radius:var(--radius-lg);padding:10px 12px;transition:border-color var(--dur-base) var(--ease),box-shadow var(--dur-base) var(--ease)}
.box-domain:hover{box-shadow:var(--shadow-md)}
.box-head{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.box-head b{font-size:13px}
.box-stat{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.box-badge{font-size:11px;color:var(--text-2);background:var(--bg);border-radius:4px;padding:1px 7px;white-space:nowrap}
.box-badge.fact{color:#1668dc;background:rgba(22,104,220,.08)}
.box-badge.dimb{color:#d97706;background:rgba(217,119,6,.08)}
.box-badge.dictb{color:#7c3aed;background:rgba(124,58,237,.08)}
.box-line2{margin:7px 0 9px}
.box-tbls{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:7px}
.box-tbl{background:var(--bg);border:1px solid var(--border);border-radius:7px;padding:6px 8px}
.box-tbl-top{display:flex;align-items:center;justify-content:space-between;gap:6px}
.box-tbl .tbl-name{font-size:11.5px}
.box-tbl-meta{display:flex;align-items:center;gap:8px;margin-top:3px;font-size:10.5px;color:var(--text-3);flex-wrap:wrap}
.box-engine{margin-left:auto}
.box-foot{margin-top:9px;padding-top:8px;border-top:1px dashed var(--border);display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.box-foot-label{font-size:11px;color:var(--text-3)}
.box-chips{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.box-chip{font-size:11px;color:#16a34a;background:rgba(22,163,74,.08);border-radius:4px;padding:1px 7px}
.box-none{font-size:11px;color:var(--text-3)}
.box-code-name{font-size:11.5px;font-weight:600}
</style>