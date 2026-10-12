<script setup lang="ts">
/**
 * M04 模型血缘影响（/model/lineage/:id）
 * 对齐第4章 L258：模型与ETL任务、数据血缘关联，模型变更时自动提示影响范围。
 * 数据：modelApi 真实后端（getModel / getModelLineage / getModelImpact；isMock 时服务内部走演示文档）。
 * 血缘链路为「上游 → 当前 → 下游」三段式行式布局（无图内核）：
 *  - 边端点已归一化为节点 id（Task 9 裁定），模型节点 id === 模型 code，直接按 id 匹配边端点；
 *  - 边双线型：声明血缘实线（#1668dc）/ 运行时血缘虚线（6 4 #94a3b8），顶部图例附 sources 计数；
 *  - 外部节点（kind==='ext'，未注册为模型的库表）虚线底框 + 「外部」tag，不可点击；
 *  - 模型节点经 listModels 建立的 code→id 映射点击跳 /model/lineage/{id}
 *    （hash 复用组件实例，watch :id 重载，reload 序号防竞态）。
 * 变更影响范围：getModelImpact 下游递归清单（表名/名称/影响路径），点表名跳其血缘页。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  getModel, getModelLineage, getModelImpact, getModelDicts, listModels,
  type ModelDetail, type ModelDicts, type LineageResp, type LineageNode, type ImpactItem,
} from '../../services/modelApi'

const route = useRoute()
const router = useRouter()

const current = ref<ModelDetail | null>(null)
const notFound = ref(false)
const lineage = ref<LineageResp | null>(null)
const impacts = ref<ImpactItem[]>([])
const dicts = ref<ModelDicts>({ layers: [], domains: [], engines: [] })
/** lineage 模型节点 id === code → 数字模型 id 的跳转映射（本页无变更路径，拉一次即可） */
const codeToId = ref<Map<string, number>>(new Map())

/* reload 竞态序号：hash 导航复用实例的并发 reload 后写胜出（晚到响应丢弃） */
let reloadSeq = 0

async function reload() {
  const seq = ++reloadSeq
  const id = String(route.params.id ?? '')
  /* 先取模型详情（信息卡 + 当前节点 code 匹配血缘节点） */
  try {
    const d = await getModel(id)
    if (seq !== reloadSeq) return
    current.value = d
    notFound.value = false
  } catch (e) {
    if (seq !== reloadSeq) return
    const err = e as Error & { code?: number }
    /* 仅「模型不存在」（8001）进兜底；超时/500/鉴权等仅提示 */
    if (err.code === 8001) {
      current.value = null
      notFound.value = true
    } else {
      ElMessage.error(err.message)
    }
    return
  }
  /* 血缘 + 影响 + 字典 + code→id 映射并行；失败置空仅提示，不阻断信息卡 */
  try {
    const [lg, im, ds, ms] = await Promise.all([
      getModelLineage(id),
      getModelImpact(id),
      dicts.value.layers.length ? Promise.resolve(dicts.value) : getModelDicts(),
      codeToId.value.size ? Promise.resolve(null) : listModels({ size: 200 }),
    ])
    if (seq !== reloadSeq) return
    lineage.value = lg
    impacts.value = im.list
    dicts.value = ds
    if (ms) codeToId.value = new Map(ms.list.map((m) => [m.code, m.id]))
  } catch (e) {
    if (seq !== reloadSeq) return
    lineage.value = null
    impacts.value = []
    ElMessage.error((e as Error).message)
  }
}

onMounted(reload)
// hash 导航复用实例时按 :id 重新加载
watch(() => route.params.id, reload)

const modelId = computed(() => String(route.params.id ?? ''))
/** 当前模型 code（lineage 模型节点 id 与 code 一致） */
const currentCode = computed(() => current.value?.code ?? '')

function layerColor(code: string): string {
  return dicts.value.layers.find((l) => l.code === code)?.color ?? '#64748b'
}
function layerName(code: string): string {
  return dicts.value.layers.find((l) => l.code === code)?.name ?? ''
}

/* ---- 血缘链路：上游/下游集合（edges 端点按节点 id 匹配；同对节点去重，边类型聚合） ---- */
interface RelEntry { node: LineageNode; kinds: string[]; relType: string }

function collectRels(dir: 'up' | 'down'): RelEntry[] {
  const lg = lineage.value
  const cur = currentCode.value
  if (!lg || !cur) return []
  const byId = new Map(lg.nodes.map((n) => [n.id, n]))
  const seen = new Map<string, RelEntry>()
  for (const e of lg.edges) {
    const otherId = dir === 'up' ? (e.to === cur ? e.from : '') : (e.from === cur ? e.to : '')
    if (!otherId) continue
    const n = byId.get(otherId)
    if (!n) continue
    let r = seen.get(otherId)
    if (!r) {
      r = { node: n, kinds: [], relType: '' }
      seen.set(otherId, r)
    }
    if (!r.kinds.includes(e.kind)) r.kinds.push(e.kind)
    if (e.relType && !r.relType) r.relType = e.relType
  }
  return [...seen.values()]
}

const upstream = computed(() => collectRels('up'))
const downstream = computed(() => collectRels('down'))

/** 边双线型（图例：声明=实线 / 运行时=虚线） */
function edgeStyle(kind: string): Record<string, string> {
  return kind === 'runtime' ? { strokeDasharray: '6 4', stroke: '#94a3b8' } : { strokeDasharray: 'none', stroke: '#1668dc' }
}

/** 节点副标题：模型节点 label 为 "code name"，剥掉 id 前缀得名称；ext 节点 label===id 无副标题 */
function nodeSub(n: LineageNode): string {
  return n.label !== n.id ? n.label.replace(n.id, '').trim() : ''
}

/** 模型节点可解析出数字 id 则可点击跳其血缘页；外部节点与当前节点不可点击 */
function goNode(n: LineageNode) {
  if (n.kind !== 'model' || n.id === currentCode.value) return
  const nid = codeToId.value.get(n.id)
  if (nid != null) router.push('/model/lineage/' + nid)
}
</script>

<template>
  <div class="page">
    <!-- 未找到模型兜底 -->
    <div v-if="notFound" class="card" style="padding:32px;text-align:center">
      <div style="color:var(--text-3);font-size:13px">未找到模型（{{ modelId }}），可能已被删除</div>
      <button class="op-btn" style="margin-top:12px" @click="router.back()">← 返回</button>
    </div>

    <template v-else-if="current">
      <!-- 顶部模型信息卡 -->
      <div class="card info-card">
        <div class="info-top">
          <div>
            <div class="ph-title">{{ current.name }}</div>
            <div class="ph-desc">模型与 ETL 任务、数据血缘关联；模型变更前请先确认下游影响范围</div>
          </div>
          <span class="spacer" />
          <button class="op-btn" @click="router.back()">← 返回</button>
        </div>
        <div class="info-grid">
          <span class="d-k">表名</span><span class="mono"><b>{{ current.code }}</b></span>
          <span class="d-k">分层</span>
          <span>
            <span class="tag" :style="{ background: layerColor(current.layer) + '22', color: layerColor(current.layer) }">{{ current.layer }}</span>
            <span style="font-size:11px;color:var(--text-3);margin-left:4px">{{ layerName(current.layer) }}</span>
          </span>
          <span class="d-k">引擎</span><span>{{ current.engine }}</span>
          <span class="d-k">表类型</span><span>{{ current.type }}</span>
          <span class="d-k">负责人</span><span>{{ current.owner }}</span>
          <span class="d-k">更新时间</span><span>{{ current.updatedAt }}</span>
        </div>
      </div>

      <!-- 血缘链路（上游 → 当前 → 下游 三段式；SVG 线段区分声明/运行时） -->
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar">
          <span class="card-title">血缘链路</span>
          <span class="pill info">上游 → 当前 → 下游</span>
          <span class="spacer" />
          <span v-if="lineage" class="lg-legend">
            <svg class="lg-line" viewBox="0 0 28 4"><line x1="0" y1="2" x2="28" y2="2" stroke-width="2" :style="edgeStyle('declared')" /></svg>
            声明 {{ lineage.sources.declared }}
            <svg class="lg-line" viewBox="0 0 28 4"><line x1="0" y1="2" x2="28" y2="2" stroke-width="2" :style="edgeStyle('runtime')" /></svg>
            运行时 {{ lineage.sources.runtime }}
          </span>
          <span style="font-size:11.5px;color:var(--text-3);margin-left:10px">点击模型节点可查看其血缘与影响</span>
        </div>
        <div v-if="lineage" class="lineage-flow">
          <!-- 上游 -->
          <div class="lg-col">
            <div class="lg-col-title">上游（{{ upstream.length }}）</div>
            <template v-if="upstream.length">
              <div v-for="r in upstream" :key="r.node.id" class="lg-rel">
                <div
                  class="lg-node"
                  :class="{ ext: r.node.kind === 'ext', click: r.node.kind === 'model' && codeToId.has(r.node.id) }"
                  @click="goNode(r.node)"
                >
                  <b class="mono">{{ r.node.id }}</b>
                  <span v-if="r.node.kind === 'ext'" class="tag ext-tag">外部</span>
                  <i v-if="nodeSub(r.node)">{{ nodeSub(r.node) }}</i>
                </div>
                <span class="lg-conns">
                  <svg v-for="k in r.kinds" :key="k" class="lg-line" viewBox="0 0 28 4"><line x1="0" y1="2" x2="28" y2="2" stroke-width="2" :style="edgeStyle(k)" /></svg>
                </span>
                <span class="lg-arr">→</span>
                <span v-if="r.relType" class="lg-reltype">{{ r.relType }}</span>
              </div>
            </template>
            <div v-else class="impact-empty">无上游节点</div>
          </div>
          <!-- 当前 -->
          <div class="lg-col cur-col">
            <div class="lg-col-title" style="text-align:center">当前</div>
            <div class="lg-node cur" :style="{ borderColor: layerColor(current.layer) }">
              <b class="mono">{{ current.code }}</b>
              <span class="pill info" style="margin-left:6px">当前查看</span>
            </div>
          </div>
          <!-- 下游 -->
          <div class="lg-col">
            <div class="lg-col-title">下游（{{ downstream.length }}）</div>
            <template v-if="downstream.length">
              <div v-for="r in downstream" :key="r.node.id" class="lg-rel">
                <span class="lg-arr">→</span>
                <span class="lg-conns">
                  <svg v-for="k in r.kinds" :key="k" class="lg-line" viewBox="0 0 28 4"><line x1="0" y1="2" x2="28" y2="2" stroke-width="2" :style="edgeStyle(k)" /></svg>
                </span>
                <div
                  class="lg-node"
                  :class="{ ext: r.node.kind === 'ext', click: r.node.kind === 'model' && codeToId.has(r.node.id) }"
                  @click="goNode(r.node)"
                >
                  <b class="mono">{{ r.node.id }}</b>
                  <span v-if="r.node.kind === 'ext'" class="tag ext-tag">外部</span>
                  <i v-if="nodeSub(r.node)">{{ nodeSub(r.node) }}</i>
                </div>
                <span v-if="r.relType" class="lg-reltype">{{ r.relType }}</span>
              </div>
            </template>
            <div v-else class="impact-empty">无下游节点</div>
          </div>
        </div>
        <div v-else class="impact-empty">暂无血缘数据（血缘加载失败或无血缘记录）</div>
      </div>

      <!-- 变更影响范围（模型变更时自动提示） -->
      <div class="card" style="padding:16px;margin-top:14px">
        <div class="tbl-toolbar">
          <span class="card-title">变更影响范围</span>
          <span class="pill info">下游影响模型 {{ impacts.length }} 个</span>
          <span class="spacer" />
          <span style="font-size:11.5px;color:var(--text-3)">模型变更前请先确认下游影响范围</span>
        </div>
        <table v-if="impacts.length" class="tbl" style="margin-top:10px">
          <thead>
            <tr><th>表名</th><th>名称</th><th>影响路径</th></tr>
          </thead>
          <tbody>
            <tr v-for="im in impacts" :key="im.modelId">
              <td><a class="lg-link mono" @click="router.push('/model/lineage/' + im.modelId)">{{ im.code }}</a></td>
              <td>{{ im.name }}</td>
              <td class="mono" style="font-size:11.5px;color:var(--text-3)">{{ im.path }}</td>
            </tr>
          </tbody>
        </table>
        <div v-else class="impact-empty">暂无下游影响模型</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.info-card{padding:16px}
.info-top{display:flex;align-items:center;gap:12px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-3);margin-top:2px}
.spacer{flex:1}
.card-title{font-weight:700;font-size:14px}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:8px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:8px 10px;border-bottom:1px solid var(--border)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.info-grid{display:grid;grid-template-columns:64px 1fr 64px 1fr 64px 1fr;gap:8px 10px;font-size:12.5px;margin-top:12px}
.info-grid .d-k{color:var(--text-3)}
.tag{display:inline-block;border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600}
/* 血缘链路：上游 → 当前 → 下游 三段式 */
.lineage-flow{display:flex;gap:18px;align-items:flex-start}
.lg-col{flex:1;min-width:0;display:flex;flex-direction:column;gap:8px}
.lg-col-title{font-size:12px;color:var(--text-3);font-weight:600}
.lg-col.cur-col{flex:none}
.lg-rel{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
.lg-node{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12px;background:#fff;display:flex;align-items:center;max-width:100%}
.lg-node.click{cursor:pointer}
.lg-node.click:hover{border-color:var(--primary);color:var(--primary)}
.lg-node.cur{border-width:2px;box-shadow:0 0 0 2px var(--primary-light)}
.lg-node.ext{background:#f8fafc;border-style:dashed;color:var(--text-2)}
.lg-node i{font-style:normal;font-size:10.5px;color:var(--text-3);margin-left:6px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ext-tag{background:var(--bg);color:var(--text-3);margin-left:6px}
.lg-line{width:28px;height:4px;flex:none}
.lg-conns{display:inline-flex;flex-direction:column;gap:2px;flex:none}
.lg-arr{color:var(--text-3);font-size:12px}
.lg-reltype{font-size:10.5px;color:var(--text-3)}
.lg-legend{display:inline-flex;align-items:center;gap:6px;font-size:11.5px;color:var(--text-2)}
.impact-empty{padding:14px 4px;text-align:center;color:var(--text-3);font-size:12px}
.lg-link{color:var(--primary);cursor:pointer}
.lg-link:hover{text-decoration:underline}
</style>
