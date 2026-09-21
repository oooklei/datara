<script setup lang="ts">
/**
 * F61 页面化：C11 SQL 结果预览（I3 §13）。
 * real：listDefinitions 映射 doc.id → 数字 code → /instances?wf_code= 取最新实例 →
 * getInstanceDetail → 本节点最新任务行 outputs.result_preview 网格渲染
 * （形状 {columns: string[], rows: any[][]}，worker executors/sql.py 前 200 行）；
 * 非查询语句无 result_preview，仅显示影响行数；mock：无实例数据源 → 空态。
 */
import { onMounted, ref } from 'vue'
import type { GNode, GraphDocument } from '../../model'
import { getInstanceDetail, listDefinitions, listInstancesPage, isMock } from '../../../services'

const props = defineProps<{ node: GNode; doc: GraphDocument }>()

const columns = ref<string[]>([])
const rows = ref<Record<string, unknown>[]>([])
const rowCount = ref<number | null>(null)
const taskState = ref('')
const loading = ref(false)
const loadErr = ref('')

function stCls(s: string): string {
  return s === 'success' ? 'ok' : s === 'failure' ? 'err' : ['running', 'retry'].includes(s) ? 'info' : 'off'
}
function stLabel(s: string): string {
  return ({ success: '成功', failure: '失败', running: '运行中', retry: '重试', kill: '终止', skip: '跳过' } as Record<string, string>)[s] ?? s
}
function fmt(v: unknown): string {
  if (v === null || v === undefined) return 'NULL'
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}

onMounted(async () => {
  if (isMock) return // mock：无引擎实例数据源，展示空态
  loading.value = true
  try {
    // wf_code 筛选参数为数字 code：经定义列表把 doc.id 映射为 code
    const defs = await listDefinitions({ pageSize: 200 })
    const code = defs.find((d) => d.id === props.doc.id)?.code
    if (!code) { loadErr.value = '工作流未注册（请先保存画布）'; return }
    const page = await listInstancesPage({ wfCode: String(code), pageSize: 1 })
    const latest = page.list[0]
    if (!latest) return // 尚无运行实例
    const detail = await getInstanceDetail(latest.instanceId)
    const task = (detail.taskInstances ?? []).filter((n) => n.nodeId === props.node.id).slice(-1)[0]
    if (!task) return // 最新实例无本节点任务（如节点为运行后新增）
    taskState.value = task.state
    rowCount.value = typeof task.outputs?.row_count === 'number' ? task.outputs.row_count : null
    const rp = task.outputs?.result_preview
    if (rp && typeof rp === 'object' && Array.isArray((rp as { columns?: unknown }).columns)) {
      const obj = rp as { columns: unknown[]; rows?: unknown }
      columns.value = obj.columns.map((c) => String(c))
      const raw = Array.isArray(obj.rows) ? obj.rows : []
      rows.value = raw.map((r) => {
        const arr = Array.isArray(r) ? r : columns.value.map((c) => (r as Record<string, unknown>)?.[c])
        const o: Record<string, unknown> = {}
        columns.value.forEach((h, i) => { o[h] = (arr as unknown[])[i] })
        return o
      })
    }
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="sqp">
    <div class="sqp-head">
      <span class="pill info">{{ node.data.name }}</span>
      <span class="mono" style="font-size:11px;color:var(--text-3)">{{ node.id }}</span>
      <span class="sqp-spacer" />
      <span v-if="taskState" class="pill" :class="stCls(taskState)">{{ stLabel(taskState) }}</span>
      <span v-if="rowCount !== null" class="pill">共 {{ rowCount }} 行</span>
    </div>

    <div v-if="loading" class="sqp-empty">加载中…</div>
    <div v-else-if="loadErr" class="sqp-empty err">加载失败：{{ loadErr }}</div>
    <div v-else-if="!columns.length" class="sqp-empty">
      暂无结果预览。<br />
      <span style="font-size:11px">非查询语句（INSERT/DDL）仅记录影响行数；查询语句运行后在此展示结果前 200 行。</span>
    </div>
    <div v-else class="sqp-grid">
      <table class="tbl">
        <thead>
          <tr><th class="sqp-idx">#</th><th v-for="c in columns" :key="c">{{ c }}</th></tr>
        </thead>
        <tbody>
          <tr v-for="(r, i) in rows" :key="i">
            <td class="sqp-idx mono">{{ i + 1 }}</td>
            <td v-for="c in columns" :key="c" class="mono">{{ fmt(r[c]) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.sqp{padding:10px 12px;display:flex;flex-direction:column;height:100%}
.sqp-head{display:flex;align-items:center;gap:8px;margin-bottom:10px;flex-shrink:0}
.sqp-spacer{flex:1}
.sqp-empty{text-align:center;color:var(--text-3);font-size:12px;padding:28px 8px;line-height:1.9}
.sqp-empty.err{color:var(--danger)}
.sqp-grid{flex:1;overflow:auto;border:1px solid var(--border);border-radius:var(--radius-sm)}
.sqp-idx{color:var(--text-3);width:36px;text-align:right}
</style>
