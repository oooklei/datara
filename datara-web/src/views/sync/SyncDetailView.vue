<script setup lang="ts">
/**
 * M05 同步任务详情（I6 改造为只读监控视图）
 * 路由 /sync/detail/:id（:id = wfCode 数字编码）。
 * 数据源：GET /sync-tasks（取任务摘要）+ GET /sync-tasks/{wfCode}/instances（实例明细分页）。
 * 展示：任务摘要卡 + 最近实例读写统计 + 实例明细表（批次号=instance_id）；
 * 出口：返回列表 / 运行实例视图（/dag/instances）。编辑操作一律落 DAG 工作台。
 */
import { ref, computed, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { listSyncTasks, listSyncInstances } from '../../services/syncApi'
import type { SyncTaskRow, SyncInstanceRow } from '../../services/syncApi'

const route = useRoute()
const router = useRouter()

const wfCode = computed(() => Number(route.params.id) || 0)
const task = ref<SyncTaskRow | null>(null)
const rows = ref<SyncInstanceRow[]>([])
const total = ref(0)
const pageNo = ref(1)
const pageSize = 20
const loading = ref(false)

const STATE_MAP: Record<string, { label: string; cls: string }> = {
  submitted: { label: '已提交', cls: 'st-gray' },
  running: { label: '运行中', cls: 'st-blue' },
  success: { label: '成功', cls: 'st-green' },
  failure: { label: '失败', cls: 'st-red' },
  kill: { label: '已终止', cls: 'st-gray' },
}

function stCls(s: string | null): string {
  return (s && STATE_MAP[s]?.cls) || 'st-gray'
}
function stLabel(s: string | null): string {
  return (s && STATE_MAP[s]?.label) || s || '-'
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))

async function reload() {
  if (!wfCode.value) return
  loading.value = true
  try {
    const instPage = await listSyncInstances(wfCode.value, { pageNo: pageNo.value, pageSize })
    rows.value = instPage.list
    total.value = instPage.total
    if (!task.value) {
      const tasks = await listSyncTasks({ pageNo: 1, pageSize: 200 })
      task.value = tasks.list.find((t) => t.wfCode === wfCode.value) ?? null
    }
  } finally {
    loading.value = false
  }
}

/* 同一组件实例在 /sync/detail/:id 间切换（hash 导航复用实例）时重新加载 */
watch(wfCode, () => {
  task.value = null
  pageNo.value = 1
  reload()
})
onMounted(reload)

function goPage(p: number) {
  if (p < 1 || p > totalPages.value || p === pageNo.value) return
  pageNo.value = p
  reload()
}
function goRuns() {
  router.push('/dag/instances')
}
function goBack() {
  router.push('/sync/list')
}
function goEdit() {
  /* 编辑统一落 DAG 工作台（同步视角画布） */
  router.push('/dag?tab=sync')
}
</script>

<template>
  <div class="page">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <button class="op-btn" @click="goBack">← 同步任务</button>
        <span class="sec-head">{{ task?.name || `同步任务 #${wfCode}` }}</span>
        <span v-for="t in task?.tags ?? []" :key="t" class="pill info">{{ t }}</span>
        <span class="spacer" />
        <button class="op-btn" @click="goEdit">可视化编排</button>
        <button class="op-btn" @click="goRuns">运行实例视图</button>
      </div>

      <!-- 任务摘要（定义 × 最近实例聚合，与列表口径一致） -->
      <div v-if="task" class="summary-grid">
        <div class="sum-item"><span class="sum-k">工作流编码</span><span class="mono">{{ task.wfCode }}</span></div>
        <div class="sum-item"><span class="sum-k">实例总数</span><span class="mono">{{ task.instanceCount }}</span></div>
        <div class="sum-item"><span class="sum-k">最近批次</span><span class="mono">{{ task.lastInstanceId || '-' }}</span></div>
        <div class="sum-item"><span class="sum-k">最近状态</span>
          <span class="st" :class="stCls(task.lastState)"><span class="dot" />{{ stLabel(task.lastState) }}</span>
        </div>
        <div class="sum-item"><span class="sum-k">读 / 写行数</span><span class="mono">{{ task.readRows }} / {{ task.writeRows }}</span></div>
        <div class="sum-item"><span class="sum-k">坏行</span><span class="mono" :style="task.badRows > 0 ? 'color:var(--danger)' : ''">{{ task.badRows }}</span></div>
        <div class="sum-item sum-wide"><span class="sum-k">参与 schema</span><span class="mono">{{ task.schemas.length ? task.schemas.join(', ') : '-' }}</span></div>
      </div>
      <div v-else class="col-sub" style="padding:8px 0">加载任务摘要中…（未打「同步」标签或已删除的定义无监控数据）</div>

      <div class="sec-head" style="margin:14px 0 8px">同步实例明细（批次号 = instance_id）</div>
      <table class="tbl">
        <thead>
          <tr>
            <th>批次号</th><th>状态</th><th>运行模式</th><th>读 / 写行数</th><th>坏行</th>
            <th>参与 schema</th><th>开始时间</th><th>结束时间</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.instanceId">
            <td><span class="mono" style="font-size:11px">{{ r.batchId }}</span></td>
            <td><span class="st" :class="stCls(r.state)"><span class="dot" />{{ stLabel(r.state) }}</span></td>
            <td>{{ r.runMode }}</td>
            <td><span class="mono">{{ r.readRows }} / {{ r.writeRows }}</span></td>
            <td><span class="mono" :style="r.badRows > 0 ? 'color:var(--danger)' : ''">{{ r.badRows }}</span></td>
            <td><span class="mono col-sub" :title="r.schemas.join(', ')">{{ r.schemas.length ? r.schemas.join(', ') : '-' }}</span></td>
            <td style="color:var(--text-2)">{{ r.startTime || '-' }}</td>
            <td style="color:var(--text-2)">{{ r.endTime || '-' }}</td>
          </tr>
        </tbody>
      </table>
      <div v-if="rows.length === 0 && !loading" class="empty">该同步任务暂无运行实例</div>

      <!-- 分页 -->
      <div v-if="total > pageSize" class="pager">
        <button class="op-btn" :disabled="pageNo <= 1" @click="goPage(pageNo - 1)">上一页</button>
        <span class="col-sub">{{ pageNo }} / {{ totalPages }}（共 {{ total }} 条）</span>
        <button class="op-btn" :disabled="pageNo >= totalPages" @click="goPage(pageNo + 1)">下一页</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.op-btn:disabled{opacity:.45;cursor:not-allowed}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.col-sub{margin-top:2px;font-size:11px;color:var(--text-3)}
.summary-grid{display:grid;grid-template-columns:repeat(6,minmax(0,1fr));gap:10px;padding:12px 0 4px}
.sum-item{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:9px 11px;display:flex;flex-direction:column;gap:4px;font-size:12.5px}
.sum-wide{grid-column:span 3}
.sum-k{font-size:11px;color:var(--text-3)}
.pager{display:flex;align-items:center;gap:10px;justify-content:flex-end;padding:12px 2px 0}
</style>
