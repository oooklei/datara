<script setup lang="ts">
/**
 * I8 页面化：C18 流输入 / C19 流融合 运行浮窗。
 * - 定位流任务：listStreamJobs({docId}) → 本画布唯一流任务；
 * - 3s 轮询：指标卡（状态/速率/累计入出/错误）+ 源位点（C18 侧重 lag/offset）+ 日志尾；
 * - 生命周期按钮：启动/重启（startStreamJob 幂等先停再起）/ 停止；
 * - C19 追加窗口触发计数展示；未启动/未保存时给空态引导。
 */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { GNode, GraphDocument } from '../../model'
import { getStreamLogs, isMock, listStreamJobs, startStreamJob, stopStreamJob } from '../../../services'
import type { StreamJobRow } from '../../../services'

const props = defineProps<{ node: GNode; doc: GraphDocument }>()

const job = ref<StreamJobRow | null>(null)
const logs = ref<string[]>([])
const loading = ref(false)
const loadErr = ref('')
const acting = ref(false)
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
/** 源位点展示：metrics.offsets 为 JSON（{sourceKey: {...}}），格式化为多行 */
function offsetLines(m: Record<string, string> | null): string[] {
  const raw = m?.offsets
  if (!raw) return []
  try {
    const obj = JSON.parse(raw) as Record<string, unknown>
    return Object.entries(obj).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : String(v)}`)
  } catch {
    return [String(raw)]
  }
}

async function refresh(): Promise<void> {
  try {
    const rows = await listStreamJobs({ docId: props.doc.id, pageSize: 1 })
    job.value = rows[0] ?? null
    logs.value = job.value ? await getStreamLogs(job.value.id, 30) : []
    loadErr.value = ''
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : String(e)
  }
}

async function act(kind: 'start' | 'stop'): Promise<void> {
  acting.value = true
  try {
    if (kind === 'start') {
      const r = await startStreamJob(props.doc.id)
      ElMessage.success(`流任务已${r.restarted ? '重启' : '启动'}（${r.name}）`)
    } else if (job.value) {
      await stopStreamJob(job.value.id)
      ElMessage.success('流任务已停止')
    }
    await refresh()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    acting.value = false
  }
}

onMounted(async () => {
  if (isMock) return
  loading.value = true
  try {
    await refresh()
  } finally {
    loading.value = false
  }
  timer = window.setInterval(refresh, 3000)
})
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="snp">
    <div class="snp-head">
      <span class="pill info">{{ node.data.name }}</span>
      <span v-if="job" class="pill" :class="stCls(job.status)">{{ stLabel(job.status) }}</span>
      <span class="snp-spacer" />
      <el-button size="small" type="primary" :disabled="acting || isMock" @click="act('start')">启动 / 重启</el-button>
      <el-button size="small" :disabled="acting || !job || ['stopped', 'failed'].includes(job.status)" @click="act('stop')">停止</el-button>
    </div>

    <div v-if="loading" class="snp-empty">加载中…</div>
    <div v-else-if="isMock" class="snp-empty">mock 模式无流引擎数据源。</div>
    <div v-else-if="loadErr" class="snp-empty err">加载失败：{{ loadErr }}</div>
    <div v-else-if="!job" class="snp-empty">
      本画布尚未注册流任务。<br />
      <span style="font-size:11px">保存画布后点「试运行」或在上方点「启动 / 重启」常驻运行。</span>
    </div>
    <template v-else>
      <div class="snp-cards">
        <div class="m-card"><b style="color:var(--primary)">{{ num(job.metrics?.ratePerSec) }}</b><span>当前速率（条/秒）</span></div>
        <div class="m-card"><b>{{ num(job.metrics?.totalIn) }}</b><span>累计接入</span></div>
        <div class="m-card"><b>{{ num(job.metrics?.totalOut) }}</b><span>累计输出</span></div>
        <div class="m-card"><b :style="num(job.metrics?.errors) !== '0' ? 'color:var(--danger)' : ''">{{ num(job.metrics?.errors) }}</b><span>错误计数</span></div>
        <div v-if="node.type === 'stream_fuse'" class="m-card"><b style="color:var(--warning)">{{ num(job.metrics?.windowEmits) }}</b><span>窗口触发</span></div>
      </div>

      <div class="snp-sec">
        <div class="snp-label">源位点（{{ stLabel(job.status) }} · 心跳 {{ job.metrics?.lastBeat ?? '-' }}）</div>
        <div class="snp-offset mono">
          <template v-if="offsetLines(job.metrics).length">
            <div v-for="(l, i) in offsetLines(job.metrics)" :key="i">{{ l }}</div>
          </template>
          <span v-else style="color:var(--text-3)">暂无位点（未启动或未产生消费）</span>
        </div>
        <div v-if="job.lastError" class="snp-err">最近错误：{{ job.lastError }}</div>
      </div>

      <div class="snp-sec snp-logwrap">
        <div class="snp-label">运行日志（尾 30 条）</div>
        <div class="snp-log mono">
          <div v-for="(l, i) in logs" :key="i" :class="{ warn: l.includes('WARN'), err: l.includes('ERROR') }">{{ l }}</div>
          <div v-if="!logs.length" style="color:var(--text-3)">暂无日志</div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.snp{padding:10px 12px;display:flex;flex-direction:column;height:100%;gap:8px}
.snp-head{display:flex;align-items:center;gap:8px;flex-shrink:0}
.snp-spacer{flex:1}
.snp-empty{text-align:center;color:var(--text-3);font-size:12px;padding:24px 8px;line-height:1.9}
.snp-empty.err{color:var(--danger)}
.snp-cards{display:flex;gap:8px;flex-shrink:0}
.m-card{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:8px 6px;text-align:center}
.m-card b{display:block;font-size:16px}
.m-card span{font-size:10px;color:var(--text-3)}
.snp-sec{flex-shrink:0}
.snp-label{font-size:11px;color:var(--text-3);margin-bottom:4px}
.snp-offset{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 8px;font-size:11px;max-height:72px;overflow:auto;white-space:pre-wrap}
.snp-err{margin-top:4px;font-size:11px;color:var(--danger)}
.snp-logwrap{flex:1;min-height:0;display:flex;flex-direction:column}
.snp-log{flex:1;min-height:0;overflow:auto;background:#0b1021;color:#c7d2fe;border-radius:var(--radius-sm);padding:6px 8px;font-size:11px;line-height:1.7}
.snp-log .warn{color:#fbbf24}
.snp-log .err{color:#f87171}
</style>
