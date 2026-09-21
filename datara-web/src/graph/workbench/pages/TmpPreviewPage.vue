<script setup lang="ts">
/**
 * F61 页面化：C22 数据预览检验网格（I4 设计文档 §5.1）。
 * real：listDefinitions 映射 doc.id → 数字 code → /instances 取最新实例 →
 * getInstanceDetail → 本节点 instanceId → listTmpData（GET /tmp-data?instance_id=）→
 * 过滤本节点临时数据行：名称/形态/行数/保留策略/状态 + schema 字段类型推断表
 * （name/type/nullRate 空值率）+ preview_json 抽样网格（worker 前 200 行）；
 * 尚无实例或未注册临时数据 → 空态。mock：无后端实例数据源 → 空态。
 */
import { computed, onMounted, ref } from 'vue'
import type { GNode, GraphDocument } from '../../model'
import { getInstanceDetail, listDefinitions, listInstancesPage, isMock } from '../../../services'
import { listTmpData } from '../../../services/datasourceApi'
import type { TmpRow } from '../../../services/datasourceApi'

const props = defineProps<{ node: GNode; doc: GraphDocument }>()

const tmpRows = ref<TmpRow[]>([])
const loading = ref(false)
const loadErr = ref('')

/** 抽样预览网格列：以当前选中临时数据的 preview 为准（worker 落库形状 {columns, rows}） */
const activeIdx = ref(0)
const active = computed(() => tmpRows.value[activeIdx.value] ?? null)
const previewCols = computed(() => active.value?.preview?.columns ?? [])
const previewBody = computed(() => {
  const rows = active.value?.preview?.rows ?? []
  // worker sample 含表头首行（header=true 时）：与 columns 完全一致则跳过，避免重复展示
  const cols = previewCols.value
  if (rows.length && cols.length && rows[0].every((v, i) => String(v ?? '') === cols[i])) return rows.slice(1)
  return rows
})

const KIND_LABEL: Record<string, string> = { table: '临时表', resultset: '结果集引用', file: '文件登记' }
const RET_LABEL: Record<string, string> = { immediate: '立即清理', days: '保留N天', keep: '转正式表' }
const STATUS_CLS: Record<string, string> = { active: 'ok', cleaned: 'off', consumed: 'info' }
const STATUS_LABEL: Record<string, string> = { active: '有效', cleaned: '已清理', consumed: '已转正' }

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === '') return ''
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}

onMounted(async () => {
  if (isMock) return // mock：无引擎实例数据源，展示空态
  loading.value = true
  try {
    // wf_code 筛选参数为数字 code：经定义列表把 doc.id 映射为 code（SqlPreviewPage 先例）
    const defs = await listDefinitions({ pageSize: 200 })
    const code = defs.find((d) => d.id === props.doc.id)?.code
    if (!code) { loadErr.value = '工作流未注册（请先保存画布）'; return }
    const page = await listInstancesPage({ wfCode: String(code), pageSize: 1 })
    const latest = page.list[0]
    if (!latest) return // 尚无运行实例
    const detail = await getInstanceDetail(latest.instanceId)
    const task = (detail.taskInstances ?? []).filter((n) => n.nodeId === props.node.id).slice(-1)[0]
    if (!task) return // 最新实例无本节点任务
    const rows = await listTmpData(latest.instanceId)
    tmpRows.value = rows.filter((r) => !r.nodeId || r.nodeId === props.node.id)
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="tpp">
    <div class="tpp-head">
      <span class="pill info">{{ node.data.name }}</span>
      <span class="mono" style="font-size:11px;color:var(--text-3)">{{ node.id }}</span>
      <span class="tpp-spacer" />
      <span v-if="tmpRows.length" class="pill">{{ tmpRows.length }} 条临时数据</span>
    </div>

    <div v-if="loading" class="tpp-empty">加载中…</div>
    <div v-else-if="loadErr" class="tpp-empty err">加载失败：{{ loadErr }}</div>
    <div v-else-if="!tmpRows.length" class="tpp-empty">
      暂无临时数据。<br />
      <span style="font-size:11px">节点运行并注册临时数据后，在此展示抽样预览 / 字段类型推断 / 空值统计。</span>
    </div>
    <template v-else>
      <!-- 临时数据行切换（同节点多注册名时） -->
      <div v-if="tmpRows.length > 1" class="tpp-tabs">
        <button
          v-for="(r, i) in tmpRows" :key="r.id"
          class="tpp-tab" :class="{ on: i === activeIdx }"
          @click="activeIdx = i"
        >{{ r.name }}</button>
      </div>

      <div v-if="active" class="tpp-meta">
        <span class="pill info">{{ KIND_LABEL[active.kind] ?? active.kind }}</span>
        <span class="pill" :class="STATUS_CLS[active.status] ?? 'off'">{{ STATUS_LABEL[active.status] ?? active.status }}</span>
        <span class="pill">{{ active.rowsCount ?? 0 }} 行</span>
        <span class="pill">{{ RET_LABEL[active.retention] ?? active.retention }}</span>
        <span v-if="active.kind === 'table'" class="tpp-ref mono" :title="active.ref">ref: {{ active.ref }}</span>
        <span v-else-if="active.kind === 'file'" class="tpp-ref mono" :title="active.ref">ref: {{ active.ref }}</span>
      </div>

      <!-- 字段类型推断表（schema_json：name/type/nullRate 空值统计列） -->
      <div v-if="active?.schema?.columns?.length" class="tpp-sec">
        <label class="tpp-cap">字段类型推断（抽样 {{ active.schema.sampledRows ?? 0 }} 行）</label>
        <div class="tpp-grid">
          <table class="tbl">
            <thead><tr><th class="tpp-idx">#</th><th>字段名</th><th>推断类型</th><th>空值率</th></tr></thead>
            <tbody>
              <tr v-for="(c, i) in active.schema.columns" :key="c.name">
                <td class="tpp-idx mono">{{ i + 1 }}</td>
                <td class="mono">{{ c.name }}</td>
                <td><span class="pill">{{ c.type }}</span></td>
                <td class="mono" :class="{ 'tpp-hi': c.nullRate > 50 }">{{ c.nullRate }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- 抽样预览网格（preview_json 前 200 行，首行为表头） -->
      <div v-if="previewCols.length" class="tpp-sec tpp-sec-grow">
        <label class="tpp-cap">抽样预览（前 {{ previewBody.length }} 行）</label>
        <div class="tpp-grid">
          <table class="tbl">
            <thead>
              <tr><th class="tpp-idx">#</th><th v-for="c in previewCols" :key="c">{{ c }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in previewBody" :key="i">
                <td class="tpp-idx mono">{{ i + 1 }}</td>
                <td v-for="(_, j) in previewCols" :key="j" class="mono">{{ fmt(row[j]) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.tpp{padding:10px 12px;display:flex;flex-direction:column;height:100%;gap:8px}
.tpp-head{display:flex;align-items:center;gap:8px;flex-shrink:0}
.tpp-spacer{flex:1}
.tpp-empty{text-align:center;color:var(--text-3);font-size:12px;padding:28px 8px;line-height:1.9}
.tpp-empty.err{color:var(--danger)}
.tpp-tabs{display:flex;gap:4px;flex-shrink:0}
.tpp-tab{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:2px 10px;font-size:11.5px;color:var(--text-2);cursor:pointer}
.tpp-tab.on{border-color:var(--primary);color:var(--primary);background:var(--primary-light)}
.tpp-meta{display:flex;align-items:center;gap:6px;flex-wrap:wrap;flex-shrink:0}
.tpp-ref{font-size:10.5px;color:var(--text-3);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:260px}
.tpp-sec{display:flex;flex-direction:column;gap:4px;flex-shrink:0}
.tpp-sec-grow{flex:1;min-height:0}
.tpp-cap{font-size:10.5px;color:var(--text-3);font-weight:600}
.tpp-grid{flex:1;min-height:0;overflow:auto;border:1px solid var(--border);border-radius:var(--radius-sm)}
.tpp-idx{color:var(--text-3);width:36px;text-align:right}
.tpp-hi{color:var(--danger)}
</style>
