<script setup lang="ts">
/**
 * M04 模型血缘影响（/model/lineage/:id）
 * 对齐第4章 L258：模型与ETL任务、数据血缘关联，模型变更时自动提示影响范围。
 * 简洁分层行式血缘（ODS→DWD→DWS→ADS→DIM，不引图内核）：当前模型高亮描边并标注「当前查看」，
 * 其余模型行可点击跳转本页（路由参数复用同一组件实例，computed 响应式跟随）。
 * 影响范围确定性推导：
 *  - 下游表：bizDomain 与当前模型相同、且分层序位在其之后的模型；
 *  - 下游任务：mock 固定映射（dwd_order_pay_detail / dws_pay_summary_daily / ads_kpi_report → etl_pay_clean）；
 *    real 模式（I5 F27）按运行时血缘（/lineage/tables）BFS 推导，无命中显示「暂无注册任务」；
 *  - 受影响指标：indicators 中 srcTable === 当前模型 code。
 */
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { dataStore } from '../../services/mock/dataStore'
import { isMock } from '../../services'
import { listTableLineage } from '../../services/lineageApi'
import { deriveImpact } from '../../services/mock/lineageUtils'
import type { Model, DwLayer, Indicator, TableLineage } from '../../services/types'

const route = useRoute()
const router = useRouter()

const models = ref<Model[]>([])
const layers = ref<DwLayer[]>([])
const indicators = ref<Indicator[]>([])
/** real 模式运行时血缘边（I5 F27：替代固定 TASK_MAP 推导下游任务） */
const realEdges = ref<TableLineage[]>([])

async function reload() {
  const [ms, ls, inds] = await Promise.all([
    dataStore.list<Model>('models'),
    dataStore.list<DwLayer>('dwLayers'),
    dataStore.list<Indicator>('indicators'),
  ])
  models.value = [...(ms ?? [])]
  layers.value = [...(ls ?? [])]
  indicators.value = [...(inds ?? [])]
  if (!isMock) {
    try {
      const edges = await listTableLineage()
      realEdges.value = edges.map((r) => ({ from: r.from, to: r.to, task: r.task, wf: r.wf }))
    } catch { /* 血缘拉取失败不阻断模型页（下游任务显示为空） */ }
  }
}
onMounted(reload)

/* ---- 当前模型（路由参数响应式驱动，站内跳转无需重新拉取集合） ---- */
const modelId = computed(() => String(route.params.id ?? ''))
const current = computed(() => models.value.find((m) => m.id === modelId.value) ?? null)

/* ---- 分层血缘链路：仅展示有模型的分层，按 ODS→DWD→DWS→ADS→DIM 行式排列 ---- */
const LAYER_ORDER = ['ODS', 'DWD', 'DWS', 'ADS', 'DIM']
const LAYER_IDX: Record<string, number> = { ODS: 0, DWD: 1, DWS: 2, ADS: 3, DIM: 4, TMP: 5 }

const layerRows = computed(() =>
  LAYER_ORDER
    .map((code) => ({ code, items: models.value.filter((m) => m.layer === code) }))
    .filter((r) => r.items.length > 0),
)

function layerColor(code: string): string {
  return layers.value.find((l) => l.code === code)?.color ?? '#64748b'
}
function layerName(code: string): string {
  return layers.value.find((l) => l.code === code)?.name ?? ''
}

/* ---- 影响范围（确定性推导，computed 懒计算） ---- */
// 下游任务固定映射（演示集合）：模型/表 → 注册的 ETL 任务
const TASK_MAP: Record<string, string> = {
  dwd_order_pay_detail: 'etl_pay_clean',
  dws_pay_summary_daily: 'etl_pay_clean',
  ads_kpi_report: 'etl_pay_clean',
}

/* 下游表：同 bizDomain 且分层序位在当前模型之后 */
const downTables = computed(() => {
  const m = current.value
  if (!m) return []
  const curIdx = LAYER_IDX[m.layer] ?? -1
  return models.value.filter(
    (x) => x.id !== m.id && (LAYER_IDX[x.layer] ?? 99) > curIdx && x.bizDomain === m.bizDomain,
  )
})

/* 下游任务：mock 固定映射；real 按运行时血缘 BFS 推导（deriveImpact），无命中 → 「暂无注册任务」 */
const downTasks = computed(() => {
  const m = current.value
  if (!m) return []
  if (isMock) {
    const codes = [m.code, ...downTables.value.map((d) => d.code)]
    const tasks: string[] = []
    for (const c of codes) {
      const t = TASK_MAP[c]
      if (t && !tasks.includes(t)) tasks.push(t)
    }
    return tasks
  }
  return deriveImpact(m.code, realEdges.value).downTasks.map((t) => t.name)
})

/* 受影响指标：srcTable === 当前模型 code */
const impactIndicators = computed(() => {
  const m = current.value
  if (!m) return []
  return indicators.value.filter((i) => i.srcTable === m.code)
})
</script>

<template>
  <div class="page">
    <!-- 未找到模型兜底 -->
    <div v-if="!current" class="card" style="padding:32px;text-align:center">
      <div style="color:var(--text-3);font-size:13px">未找到模型（{{ modelId }}），可能已被删除</div>
      <button class="op-btn" style="margin-top:12px" @click="router.back()">← 返回</button>
    </div>

    <template v-else>
      <!-- 顶部模型信息卡 -->
      <div class="card info-card">
        <div class="info-top">
          <div>
            <div class="ph-title">{{ current.name }}</div>
            <div class="ph-desc">模型与 ETL 任务、数据血缘关联；模型变更前请先确认下游表、任务与指标的影响范围</div>
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

      <!-- 分层血缘链路（行式，flex 竖排 + 层间向下箭头） -->
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar">
          <span class="card-title">分层血缘链路</span>
          <span class="pill info">ODS → DWD → DWS → ADS → DIM</span>
          <span class="spacer" />
          <span style="font-size:11.5px;color:var(--text-3)">点击其他模型可查看其血缘与影响</span>
        </div>
        <div class="lineage-flow">
          <template v-for="(row, i) in layerRows" :key="row.code">
            <div class="lg-layer">
              <div class="lg-side" :style="{ color: layerColor(row.code) }">
                <b>{{ row.code }}</b>
                <i>{{ layerName(row.code) }}</i>
              </div>
              <div class="lg-items">
                <div
                  v-for="m in row.items"
                  :key="m.id"
                  class="lg-node"
                  :class="{ cur: m.id === current.id, click: m.id !== current.id }"
                  :style="m.id === current.id ? { borderColor: layerColor(row.code) } : undefined"
                  @click="m.id !== current.id && router.push('/model/lineage/' + m.id)"
                >
                  <b class="mono">{{ m.code }}</b>
                  <span v-if="m.id === current.id" class="pill info" style="margin-left:6px">当前查看</span>
                </div>
              </div>
            </div>
            <div v-if="i < layerRows.length - 1" class="lg-arrow">↓</div>
          </template>
        </div>
      </div>

      <!-- 影响范围（模型变更时自动提示） -->
      <div class="card" style="padding:16px;margin-top:14px">
        <div class="tbl-toolbar">
          <span class="card-title">变更影响范围</span>
          <span class="pill info">变更影响：下游 {{ downTables.length }} 表 / {{ downTasks.length }} 任务 / {{ impactIndicators.length }} 指标</span>
        </div>
        <div class="impact-grid">
          <!-- 下游表 -->
          <div class="impact-box">
            <div class="impact-title">下游表</div>
            <table v-if="downTables.length" class="tbl">
              <thead>
                <tr><th>表名</th><th>分层</th></tr>
              </thead>
              <tbody>
                <tr v-for="d in downTables" :key="d.id">
                  <td><a class="lg-link mono" @click="router.push('/model/lineage/' + d.id)">{{ d.code }}</a></td>
                  <td>
                    <span class="tag" :style="{ background: layerColor(d.layer) + '22', color: layerColor(d.layer) }">{{ d.layer }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="impact-empty">暂无下游表（同业务域内无更深层模型）</div>
          </div>
          <!-- 下游任务 -->
          <div class="impact-box">
            <div class="impact-title">下游任务</div>
            <div v-if="downTasks.length" class="task-list">
              <div v-for="t in downTasks" :key="t" class="task-row"><span class="mono">{{ t }}</span></div>
            </div>
            <div v-else class="impact-empty">暂无注册任务</div>
          </div>
          <!-- 受影响指标 -->
          <div class="impact-box">
            <div class="impact-title">受影响指标</div>
            <table v-if="impactIndicators.length" class="tbl">
              <thead>
                <tr><th>指标</th><th>来源字段</th></tr>
              </thead>
              <tbody>
                <tr v-for="ind in impactIndicators" :key="ind.id">
                  <td>{{ ind.name }} <span class="mono" style="font-size:11px;color:var(--text-3)">{{ ind.en }}</span></td>
                  <td class="mono">{{ ind.srcField }}</td>
                </tr>
              </tbody>
            </table>
            <div v-else class="impact-empty">暂无以本表为来源的指标</div>
          </div>
        </div>
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
/* 血缘链路：分层行式，flex 竖排，层间向下箭头 */
.lineage-flow{display:flex;flex-direction:column;gap:4px;max-width:960px}
.lg-layer{display:flex;align-items:center;gap:14px}
.lg-side{width:88px;flex:none;display:flex;flex-direction:column;font-size:13px}
.lg-side i{font-style:normal;font-size:10.5px;color:var(--text-3)}
.lg-items{display:flex;gap:8px;flex-wrap:wrap;flex:1}
.lg-node{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12px;background:#fff;display:flex;align-items:center}
.lg-node.click{cursor:pointer}
.lg-node.click:hover{border-color:var(--primary);color:var(--primary)}
.lg-node.cur{border-width:2px;box-shadow:0 0 0 2px var(--primary-light)}
.lg-arrow{text-align:center;color:var(--text-3);font-size:14px;line-height:1.2;margin-left:88px}
/* 影响范围三块 */
.impact-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:10px}
.impact-box{border:1px solid var(--border);border-radius:var(--radius);padding:10px 12px}
.impact-title{font-weight:600;font-size:12.5px;margin-bottom:8px}
.impact-empty{padding:14px 4px;text-align:center;color:var(--text-3);font-size:12px}
.task-list{display:flex;flex-direction:column}
.task-row{padding:6px 4px;border-bottom:1px solid var(--border);font-size:12.5px}
.task-row:last-child{border-bottom:none}
.lg-link{color:var(--primary);cursor:pointer}
.lg-link:hover{text-decoration:underline}
</style>
