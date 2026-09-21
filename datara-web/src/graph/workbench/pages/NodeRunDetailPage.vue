<script setup lang="ts">
/**
 * F61 页面化演示页：节点运行详情（验证页面化框架闭环，不依赖任何流组件）。
 * real：listDefinitions 映射 doc.id → 数字 code → /instances?wf_code= →
 * 从最新实例向前（最多 3 个）取首个含本节点任务的实例详情，展示该节点全部任务行
 * （状态/attempt/起止/时长/输出参数，I3 引擎 task_instances 真实形状）；
 * mock：无后端实例数据源 → 空态提示。
 */
import { onMounted, ref } from 'vue'
import type { GNode, GraphDocument } from '../../model'
import { getInstanceDetail, listDefinitions, listInstances, isMock } from '../../../services'

interface NodeRunRow {
  state: string
  startTime: string
  endTime: string
  duration: string
  attempt: number
  outputs?: Record<string, unknown> | null
}

const props = defineProps<{ node: GNode; doc: GraphDocument }>()

const rows = ref<NodeRunRow[]>([])
const loading = ref(false)
const loadErr = ref('')

const STATE_LABEL: Record<string, string> = {
  success: '成功', failure: '失败', running: '运行中', submitted: '已提交',
  kill: '终止', retry: '重试', skip: '跳过', fault_tolerance: '容错', pause: '暂停',
}
function stCls(s: string): string {
  return s === 'success' ? 'ok'
    : s === 'failure' ? 'err'
    : ['running', 'retry', 'fault_tolerance'].includes(s) ? 'info' : 'off'
}
function stLabel(s: string): string {
  return STATE_LABEL[s] ?? s
}

function calcDuration(s?: string | null, e?: string | null): string {
  if (!s || !e) return '-'
  const t = new Date(e.replace(' ', 'T')).getTime() - new Date(s.replace(' ', 'T')).getTime()
  if (!Number.isFinite(t) || t < 0) return '-'
  const m = Math.floor(t / 60000)
  const sec = Math.floor((t % 60000) / 1000)
  return m ? `${m}分${sec}秒` : `${sec}秒`
}

onMounted(async () => {
  if (isMock) return // mock：无实例数据源，展示空态
  loading.value = true
  try {
    // wf_code 筛选参数为数字 code：经定义列表把 doc.id 映射为 code
    const defs = await listDefinitions({ pageSize: 200 })
    const code = defs.find((d) => d.id === props.doc.id)?.code
    if (!code) { loadErr.value = '工作流未注册（请先保存画布）'; return }
    const list = await listInstances({ wfCode: String(code), pageSize: 10 })
    // 从最新实例向前找首个包含本节点任务的实例（最多 3 次详情请求）
    for (const r of list.slice(0, 3)) {
      const detail = await getInstanceDetail(r.instanceId)
      const hits = (detail.taskInstances ?? []).filter((n) => n.nodeId === props.node.id)
      if (hits.length) {
        rows.value = hits.map((n) => ({
          state: n.state ?? '-',
          startTime: n.startTime ?? '',
          endTime: n.endTime ?? '',
          duration: calcDuration(n.startTime, n.endTime),
          attempt: n.attempt,
          outputs: n.outputs,
        })).slice(0, 10)
        return
      }
    }
  } catch (e) {
    loadErr.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="nrdp">
    <div class="nrdp-head">
      <span class="pill info">{{ node.data.name }}</span>
      <span class="mono" style="font-size:11px;color:var(--text-3)">{{ node.id }}</span>
      <span class="nrdp-spacer" />
      <span class="pill">{{ isMock ? 'mock 空态' : `工作流 ${doc.name}` }}</span>
    </div>

    <div v-if="loading" class="nrdp-empty">加载中…</div>
    <div v-else-if="loadErr" class="nrdp-empty err">加载失败：{{ loadErr }}</div>
    <div v-else-if="!rows.length" class="nrdp-empty">
      暂无该节点的运行实例明细。<br />
      <span style="font-size:11px">real 模式：调度引擎产生 task_instance 后在此展示；mock 模式：无后端实例数据源。</span>
    </div>
    <table v-else class="tbl">
      <thead>
        <tr><th>状态</th><th>#</th><th>开始</th><th>结束</th><th>时长</th><th>输出参数</th></tr>
      </thead>
      <tbody>
        <tr v-for="(r, i) in rows" :key="i">
          <td><span class="pill" :class="stCls(r.state)">{{ stLabel(r.state) }}</span></td>
          <td><span v-if="r.attempt > 1" class="pill warn">#{{ r.attempt }}</span><span v-else style="color:var(--text-3)">-</span></td>
          <td class="mono" style="font-size:11px">{{ r.startTime || '-' }}</td>
          <td class="mono" style="font-size:11px">{{ r.endTime || '-' }}</td>
          <td>{{ r.duration }}</td>
          <td>
            <template v-if="r.outputs && Object.keys(r.outputs).length">
              <span
                v-for="(v, k) in r.outputs" :key="k"
                class="pill info" style="margin-right:4px"
              >{{ k }}={{ String(v) }}</span>
            </template>
            <span v-else style="color:var(--text-3)">-</span>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<style scoped>
.nrdp{padding:10px 12px}
.nrdp-head{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.nrdp-spacer{flex:1}
.nrdp-empty{text-align:center;color:var(--text-3);font-size:12px;padding:28px 8px;line-height:1.9}
.nrdp-empty.err{color:var(--danger)}
</style>
