<script setup lang="ts">
/**
 * M09 元数据目录（todo 9 · F52）
 * 左侧主题域树（全部 + bizDomains 展开到表），右侧元数据表列表：
 * 名称/所属域/引擎/表类型/采集时间/质量概要入口；搜索即时过滤；
 * 行点击打开详情抽屉（资产概览 + 字段结构 + 血缘入口）。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import { useAuthStore } from '../../stores/auth'
import { maskRow } from '../../utils/mask'
import type { MaskRule, BizDomain, MetaTable, MetaTag, Model } from '../../services/types'

const router = useRouter()
const auth = useAuthStore()

const tables = ref<MetaTable[]>([])
const domains = ref<BizDomain[]>([])
const models = ref<Model[]>([])
const tags = ref<MetaTag[]>([])
const maskRules = ref<MaskRule[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ layer: '', domain: '' }) // domain '' = 全部
const expanded = ref<Set<string>>(new Set())

async function reload() {
  tables.value = (await dataStore.list<MetaTable>('metaTables')) ?? []
  domains.value = (await dataStore.list<BizDomain>('bizDomains')) ?? []
  models.value = (await dataStore.list<Model>('models')) ?? []
  tags.value = (await dataStore.list<MetaTag>('metaTags')) ?? []
  maskRules.value = (await dataStore.list<MaskRule>('maskRules')) ?? []
}

onMounted(reload)

/* ---- 左侧筛选面板 facets（分层按数据派生，保持 ODS→DIM 顺序） ---- */
const LAYERS = ['ODS', 'DWD', 'DWS', 'ADS', 'DIM']
const facets = computed<Facet[]>(() => {
  const layers = [...new Set(tables.value.map((t) => t.layer))].sort(
    (a, b) => LAYERS.indexOf(a) - LAYERS.indexOf(b),
  )
  return [
    { key: 'layer', label: '分层', options: layers.map((l) => ({ v: l, t: l })) },
    { key: 'domain', label: '业务域', options: domains.value.map((d) => ({ v: d.name, t: d.name })) },
  ]
})

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return tables.value.filter((t) => {
    if (filters.value.domain && t.domain !== filters.value.domain) return false
    if (filters.value.layer && t.layer !== filters.value.layer) return false
    if (!kw) return true
    return [t.name, t.domain, t.owner, t.desc, (t.tags ?? []).join(',')]
      .join(' ').toLowerCase().includes(kw)
  })
})

function tablesOf(domain: string) {
  return tables.value.filter((t) => t.domain === domain)
}

function toggleDomain(name: string) {
  const s = new Set(expanded.value)
  if (s.has(name)) s.delete(name)
  else s.add(name)
  expanded.value = s
}

function selectDomain(name: string) {
  filters.value.domain = name
}

function modelOf(t: MetaTable) {
  return models.value.find((m) => m.code === t.name)
}

function engineOf(t: MetaTable) {
  return modelOf(t)?.engine ?? 'Apache Doris'
}

function typeOf(t: MetaTable) {
  return modelOf(t)?.type ?? t.layer
}

/* ---- 数据安全：密级徽标 / 行级授权 / 脱敏预览 ---- */
const SEC_COLORS: Record<string, string> = {
  公开: '#16a34a', 内部: '#1668dc', 机密: '#d97706', 绝密: '#dc2626',
}
function secOf(t: MetaTable) { return t.security ?? '内部' }
/** 行级控制：密级 > 许可上限 或 域未授权 → 无权限（保留行，血缘完整性不受影响） */
function deniedOf(t: MetaTable) { return !auth.canSeeTable(t) }

/** 详情抽屉数据预览（列级脱敏后展示） */
const previewRows = computed(() => {
  if (!current.value || deniedOf(current.value)) return []
  return (current.value.sample ?? []).map((r) => maskRow(r, maskRules.value))
})

/* ---- 质量概要 ---- */
async function showQuality(t: MetaTable) {
  const tags = (t.tags ?? []).join('、') || '-'
  await ElMessageBox.alert(
    `表名：${t.name}\n行数：${t.rows.toLocaleString()}\n大小：${t.size}\n昨日产出：${t.yesterdayOk ? '正常' : '异常'}\n负责人：${t.owner}\n标签：${tags}\n描述：${t.desc}`,
    `质量概要 · ${t.name}`,
    { confirmButtonText: '关闭' },
  )
}

/* ---- 详情抽屉 ---- */
const drawerVisible = ref(false)
const current = ref<MetaTable | null>(null)

function openDetail(t: MetaTable) {
  const denied = deniedOf(t)
  // 访问审计：谁、何时、查了什么、多少行（拒绝也记录）
  auth.audit(t.name, denied ? 0 : (t.sample ?? []).length, !denied,
    denied ? `密级（${secOf(t)}）＞ 许可（${auth.clearance}）` : `密级（${secOf(t)}）≤ 许可（${auth.clearance}）`)
  current.value = t
  checkedTags.value = [...(t.tags ?? [])]
  drawerVisible.value = true
}

function goLineage() {
  drawerVisible.value = false
  router.push('/meta/lineage')
}

/* ---- 标签编辑（todo 11 · F56，双向同步） ---- */
const checkedTags = ref<string[]>([])

async function saveTags() {
  const t = current.value
  if (!t) return
  const vals = [...checkedTags.value]
  t.tags = vals
  for (const tg of tags.value) {
    const had = tg.tables.includes(t.id)
    const want = vals.includes(tg.name)
    if (had !== want) {
      tg.tables = tg.tables.filter((x) => x !== t.id)
      if (want) tg.tables.push(t.id)
      tg.cnt = tg.tables.length
      await dataStore.save('metaTags', tg)
    }
  }
  await dataStore.save('metaTables', t)
  ElMessage.success(`「${t.name}」标签已更新`)
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索表名/域/负责人/描述"
      :result-count="filtered.length"
      :total-count="tables.length"
    />
    <div style="flex:1;min-width:0">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">元数据目录</span>
        <span class="pill info">{{ filtered.length }} / {{ tables.length }}</span>
        <span class="spacer" />
      </div>

      <div class="catalog">
        <!-- 左侧主题域树 -->
        <aside class="tree">
          <div
            class="node root"
            :class="{ active: filters.domain === '' }"
            @click="selectDomain('')"
          >
            <span class="caret" />
            <span>全部</span>
            <span class="cnt">{{ tables.length }}</span>
          </div>
          <div v-for="d in domains" :key="d.name" class="grp">
            <div
              class="node"
              :class="{ active: filters.domain === d.name }"
              @click="selectDomain(d.name)"
            >
              <span class="caret" :class="{ open: expanded.has(d.name) }" @click.stop="toggleDomain(d.name)">▸</span>
              <span class="dot" :style="{ background: d.color }" />
              <span>{{ d.name }}</span>
              <span class="cnt">{{ tablesOf(d.name).length }}</span>
            </div>
            <div v-if="expanded.has(d.name)" class="kids">
              <div
                v-for="t in tablesOf(d.name)"
                :key="t.id"
                class="node leaf"
                @click="openDetail(t)"
              >
                <span class="caret" />
                <span class="mono" style="font-size:11.5px">{{ t.name }}</span>
              </div>
            </div>
          </div>
        </aside>

        <!-- 右侧表列表 -->
        <section class="list">
          <table class="tbl">
            <thead>
              <tr>
                <th>表名</th><th>所属域</th><th>密级</th><th>引擎</th><th>表类型</th>
                <th>采集时间</th><th>质量概要</th><th style="width:120px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="t in filtered" :key="t.id" :class="{ denied: deniedOf(t) }">
                <td>
                  <a @click="openDetail(t)"><span class="mono" style="font-size:12px">{{ t.name }}</span></a>
                  <div style="color:var(--text-3);font-size:11px">{{ t.id }}</div>
                </td>
                <td>
                  <span class="pill info">{{ t.domain }}</span>
                </td>
                <td>
                  <span class="pill" :style="{ background: (SEC_COLORS[secOf(t)] ?? '#999') + '1a', color: SEC_COLORS[secOf(t)] }">{{ secOf(t) }}</span>
                  <span v-if="deniedOf(t)" class="pill err" style="margin-left:4px" title="密级高于当前用户许可或业务域未授权">无权限</span>
                </td>
                <td style="color:var(--text-2)">{{ engineOf(t) }}</td>
                <td>{{ typeOf(t) }}</td>
                <td style="color:var(--text-3)">
                  <span v-if="t.collectedAt" class="mono" style="font-size:11.5px">{{ t.collectedAt }}</span>
                  <span v-else>-</span>
                </td>
                <td>
                  <button class="op-btn" @click="showQuality(t)">查看</button>
                </td>
                <td>
                  <button class="op-btn primary" @click="openDetail(t)">详情</button>
                  <button class="op-btn" @click="goLineage">血缘</button>
                </td>
              </tr>
            </tbody>
          </table>
          <div v-if="filtered.length === 0" class="empty">未找到匹配的元数据表</div>
        </section>
      </div>
    </div>

    <!-- 详情抽屉 -->
    <el-drawer v-model="drawerVisible" :title="current ? current.name : ''" size="480px">
      <template v-if="current">
        <div class="sec-title">资产概览</div>
        <div class="kv">
          <div class="row"><span>表 ID</span><b class="mono">{{ current.id }}</b></div>
          <div class="row"><span>分层</span><b>{{ current.layer }}</b></div>
          <div class="row"><span>主题域</span><b>{{ current.domain }}</b></div>
          <div class="row"><span>引擎</span><b>{{ engineOf(current) }}</b></div>
          <div class="row"><span>表类型</span><b>{{ typeOf(current) }}</b></div>
          <div class="row"><span>行数</span><b>{{ current.rows.toLocaleString() }}</b></div>
          <div class="row"><span>大小</span><b>{{ current.size }}</b></div>
          <div class="row"><span>负责人</span><b>{{ current.owner }}</b></div>
          <div class="row"><span>数据密级</span><b><span class="pill" :style="{ background: (SEC_COLORS[secOf(current)] ?? '#999') + '1a', color: SEC_COLORS[secOf(current)] }">{{ secOf(current) }}</span></b></div>
          <div class="row"><span>昨日产出</span><b>{{ current.yesterdayOk ? '正常' : '异常' }}</b></div>
          <div class="row"><span>采集时间</span><b>{{ current.collectedAt ?? '-' }}</b></div>
          <div class="row"><span>标签</span><b>{{ (current.tags ?? []).join('、') || '-' }}</b></div>
          <div class="row"><span>描述</span><b>{{ current.desc }}</b></div>
        </div>

        <div class="sec-title">数据预览（{{ deniedOf(current) ? '无权限' : '已脱敏' }}）</div>
        <div v-if="deniedOf(current)" class="denied-box">
          ⛔ 行级权限拦截：表密级「{{ secOf(current) }}」高于当前许可「{{ auth.clearance }}」<template v-if="auth.roleCode !== 'admin'">或业务域未授权</template>，已记录访问审计。
        </div>
        <table v-else-if="previewRows.length" class="tbl mini">
          <thead><tr><th v-for="k in Object.keys(previewRows[0])" :key="k" class="mono">{{ k }}</th></tr></thead>
          <tbody>
            <tr v-for="(r, i) in previewRows" :key="i">
              <td v-for="k in Object.keys(previewRows[0])" :key="k" class="mono" style="font-size:11.5px">{{ r[k] }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else style="color:var(--text-3);font-size:12px">暂无采样数据</div>

        <div class="sec-title">字段结构</div>
        <table class="tbl mini">
          <thead>
            <tr><th>字段</th><th>类型</th><th>长度</th><th>主键</th><th>注释</th></tr>
          </thead>
          <tbody>
            <tr v-for="f in (modelOf(current)?.fields ?? [])" :key="f.n">
              <td class="mono" style="font-size:11.5px">{{ f.n }}</td>
              <td>{{ f.t }}</td>
              <td>{{ f.len ?? '-' }}</td>
              <td>{{ f.pk ? '是' : '-' }}</td>
              <td style="color:var(--text-2)">{{ f.cmt }}</td>
            </tr>
            <tr v-if="!(modelOf(current)?.fields ?? []).length">
              <td colspan="5" style="color:var(--text-3);text-align:center">暂无字段信息</td>
            </tr>
          </tbody>
        </table>

        <div class="sec-title">标签</div>
        <div class="tag-edit">
          <label v-for="tg in tags" :key="tg.id" class="tag-check">
            <input type="checkbox" :value="tg.name" v-model="checkedTags" />
            <span class="tag" :style="{ background: tg.color + '22', color: tg.color }">{{ tg.name }}</span>
            <span style="font-size:11px;color:var(--text-3)">{{ tg.cat }} · {{ tg.desc }}</span>
          </label>
          <div v-if="tags.length === 0" style="color:var(--text-3);font-size:12px">暂无标签，请先到「标签管理」创建</div>
          <button class="tb-new" style="margin-top:10px" @click="saveTags">保存标签</button>
        </div>

        <div style="margin-top:16px">
          <button class="tb-new" @click="goLineage">查看血缘关系 →</button>
        </div>
      </template>
    </el-drawer>
    </div>
  </div>
</template>

<style scoped>
.catalog{display:flex;gap:16px;margin-top:12px;align-items:flex-start}
.tree{width:230px;flex-shrink:0;border:1px solid var(--border);border-radius:var(--radius);padding:8px;max-height:520px;overflow-y:auto}
.node{display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:var(--radius-sm);cursor:pointer;font-size:12.5px;color:var(--text-2)}
.node:hover{background:var(--bg)}
.node.active{background:rgba(22,104,220,.08);color:var(--primary);font-weight:600}
.node.root{font-weight:700;color:var(--text)}
.caret{width:12px;flex-shrink:0;display:inline-block;transition:transform .15s}
.caret.open{transform:rotate(90deg)}
.dot{width:8px;height:8px;border-radius:50%;flex-shrink:0}
.cnt{margin-left:auto;font-size:11px;color:var(--text-3);background:var(--bg);border-radius:var(--radius);padding:0 6px}
.node.leaf{padding-left:26px;font-size:12px}
.kids{margin:2px 0}
.list{flex:1;min-width:0}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.tbl.mini{font-size:12px}
.tbl.mini th{padding:6px 8px}
.tbl.mini td{padding:6px 8px}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:220px;outline:none}
.kw:focus{border-color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.sec-title{font-weight:700;font-size:13px;margin:14px 0 8px;color:var(--text)}
.kv{border:1px solid var(--border);border-radius:var(--radius);padding:4px 10px}
.kv .row{display:flex;justify-content:space-between;gap:12px;padding:6px 0;border-bottom:1px dashed var(--border);font-size:12.5px}
.kv .row:last-child{border-bottom:none}
.kv .row span{color:var(--text-3);flex-shrink:0}
.kv .row b{text-align:right;font-weight:500}
.tag{display:inline-block;border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600;margin-right:4px}
.tag-check{display:flex;gap:8px;align-items:center;padding:6px 10px;border:1px solid var(--border);border-radius:7px;margin-bottom:7px;cursor:pointer;font-size:12.5px}
/* 行级权限：无权行淡化 + 预览拒绝提示 */
.tbl tr.denied td{opacity:.55}
.tbl tr.denied td a{cursor:not-allowed;text-decoration:line-through}
.denied-box{border:1px dashed #f0a0a0;background:#fef2f2;color:#b91c1c;border-radius:var(--radius);padding:10px 12px;font-size:12.5px;line-height:1.6}
</style>