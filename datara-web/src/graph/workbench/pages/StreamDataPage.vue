<script setup lang="ts">
/**
 * I8 页面化：C20 流输出实时数据展示页（大屏联调形态，意见⑩示例场景）。
 * - 定位流任务（本画布 docId）→ SSE 增量推送（streamSseUrl，token 查询参数鉴权）；
 * - SSE 失败自动回退 3s 轮询（pollStreamData）；
 * - 表格列 = C20 schema 声明（schemaText）或兜底行键；指标卡：速率/累计/窗口条数/状态。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { GNode, GraphDocument } from '../../model'
import { isMock, listStreamJobs, pollStreamData, startStreamJob, stopStreamJob, streamSseUrl } from '../../../services'
import type { StreamDataPage, StreamJobRow } from '../../../services'

const props = defineProps<{ node: GNode; doc: GraphDocument }>()

const job = ref<StreamJobRow | null>(null)
const fields = ref<string[]>([])
const rows = ref<Record<string, unknown>[]>([])
const mode = ref<'sse' | 'poll' | 'off'>('off')
const loadErr = ref('')
const acting = ref(false)
let es: EventSource | null = null
let timer = 0

function stCls(s: string): string {
  return s === 'running' ? 'ok' : s === 'failed' ? 'err' : ['starting', 'reconnecting'].includes(s) ? 'info' : 'off'
}
function stLabel(s: string): string {
  return ({
    starting: '启动中', running: '运行中', reconnecting: '重连中', stopped: '已停止', failed: '失败',
  } as Record<string, string>)[s] ?? (s || '未启动')
}
function num(v: unknown): string {
  const n = Number(v)
  return Number.isFinite(n) ? n.toLocaleString() : '0'
}
function fmt(v: unknown): string {
  if (v === null || v === undefined) return ''
  return typeof v === 'object' ? JSON.stringify(v) : String(v)
}
/** 列集：优先 schema 声明（逗号分隔），空则取最近行的键并集 */
function applyPage(p: StreamDataPage): void {
  if (p.fields?.length) fields.value = p.fields
  else if (!fields.value.length && p.rows.length) {
    const set = new Set<string>()
    p.rows.slice(0, 20).forEach((r) => Object.keys(r).forEach((k) => set.add(k)))
    fields.value = [...set]
  }
  rows.value = p.rows
  if (p.metrics) job.value = job.value ? { ...job.value, metrics: p.metrics, status: p.metrics.status || job.value.status } : job.value
}

function openSse(id: number): void {
  es?.close()
  mode.value = 'sse'
  es = new EventSource(streamSseUrl(id))
  es.onmessage = (ev) => {
    try { applyPage(JSON.parse(ev.data) as StreamDataPage) } catch { /* 忽略坏帧 */ }
  }
  es.onerror = () => {
    es?.close()
    es = null
    // SSE 断开回退轮询（网络抖动/代理不支持流式时兜底）
    mode.value = 'poll'
    timer = window.setInterval(refreshPoll, 3000)
  }
}

async function refreshPoll(): Promise<void> {
  if (!job.value) return
  try {
    applyPage(await pollStreamData(job.value.id, 100))
    loadErr.value = ''
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : String(e)
  }
}

async function refreshJob(): Promise<void> {
  const list = await listStreamJobs({ docId: props.doc.id, pageSize: 1 })
  job.value = list[0] ?? null
  if (job.value && mode.value === 'off') {
    if (['running', 'reconnecting'].includes(job.value.status)) openSse(job.value.id)
    else mode.value = 'poll'
  }
}

async function act(kind: 'start' | 'stop'): Promise<void> {
  acting.value = true
  try {
    if (kind === 'start') {
      const r = await startStreamJob(props.doc.id)
      ElMessage.success(`流任务已${r.restarted ? '重启' : '启动'}（${r.name}）`)
      await refreshJob()
    } else if (job.value) {
      await stopStreamJob(job.value.id)
      ElMessage.success('流任务已停止')
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    acting.value = false
  }
}

onMounted(async () => {
  if (isMock) return
  try {
    await refreshJob()
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : String(e)
  }
  if (mode.value === 'poll') timer = window.setInterval(refreshPoll, 3000)
})
onBeforeUnmount(() => {
  es?.close()
  es = null
  window.clearInterval(timer)
})
</script>

<template>
  <div class="sdp">
    <div class="sdp-head">
      <span class="pill info">{{ node.data.name }}</span>
      <span v-if="job" class="pill" :class="stCls(job.status)">{{ stLabel(job.status) }}</span>
      <span v-if="mode !== 'off'" class="pill">{{ mode === 'sse' ? 'SSE 推送' : '轮询 3s' }}</span>
      <span class="sdp-spacer" />
      <el-button size="small" type="primary" :disabled="acting || isMock" @click="act('start')">启动 / 重启</el-button>
      <el-button size="small" :disabled="acting || !job || ['stopped', 'failed'].includes(job.status)" @click="act('stop')">停止</el-button>
    </div>

    <div v-if="isMock" class="sdp-empty">mock 模式无流引擎数据源。</div>
    <div v-else-if="!job" class="sdp-empty">
      本画布尚未注册流任务。<br />
      <span style="font-size:11px">保存画布后点「试运行」启动常驻流任务，本页即为 API 通道实时数据展示位。</span>
    </div>
    <template v-else>
      <div class="sdp-cards">
        <div class="m-card"><b style="color:var(--primary)">{{ num(job.metrics?.ratePerSec) }}</b><span>速率（条/秒）</span></div>
        <div class="m-card"><b>{{ num(job.metrics?.totalOut) }}</b><span>累计输出</span></div>
        <div class="m-card"><b style="color:var(--warning)">{{ rows.length }}</b><span>窗口保留（Last-N）</span></div>
        <div class="m-card"><b>{{ job.metrics?.lastBeat ?? '-' }}</b><span>最后心跳</span></div>
      </div>

      <div v-if="loadErr" class="sdp-empty err">{{ loadErr }}</div>
      <div v-else-if="!rows.length" class="sdp-empty">暂无实时数据（流任务未产生输出或保留窗口为空）。</div>
      <div v-else class="sdp-grid">
        <table class="tbl">
          <thead>
            <tr><th class="sdp-idx">#</th><th v-for="c in fields" :key="c">{{ c }}</th></tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in rows" :key="i">
              <td class="sdp-idx mono">{{ i + 1 }}</td>
              <td v-for="c in fields" :key="c" class="mono">{{ fmt(r[c]) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sdp{padding:10px 12px;display:flex;flex-direction:column;height:100%;gap:8px}
.sdp-head{display:flex;align-items:center;gap:8px;flex-shrink:0}
.sdp-spacer{flex:1}
.sdp-empty{text-align:center;color:var(--text-3);font-size:12px;padding:24px 8px;line-height:1.9}
.sdp-empty.err{color:var(--danger)}
.sdp-cards{display:flex;gap:8px;flex-shrink:0}
.m-card{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:8px 6px;text-align:center}
.m-card b{display:block;font-size:16px}
.m-card span{font-size:10px;color:var(--text-3)}
.sdp-grid{flex:1;min-height:0;overflow:auto;border:1px solid var(--border);border-radius:var(--radius-sm)}
.sdp-idx{color:var(--text-3);width:36px;text-align:right}
</style>
