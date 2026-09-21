<script setup lang="ts">
/**
 * M05 同步任务列表（I6 F34 接真）
 * 数据源：GET /sync-tasks（打「同步」标签的定义 × 最近实例读写统计聚合，批次号=instance_id）；
 * 关键字 + 最近状态筛选（后端过滤）；行操作：详情(/sync/detail/:wfCode)。
 * 「新建同步」落 DAG 工作台（C17 直拖 / C23 同步编排模板）。
 */
import { ref, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { listSyncTasks } from '../../services/syncApi'
import type { SyncTaskRow } from '../../services/syncApi'
import ListFilterPanel from '../../components/ListFilterPanel.vue'

const router = useRouter()

const rows = ref<SyncTaskRow[]>([])
const total = ref(0)
const keyword = ref('')
const filters = ref<Record<string, string>>({ state: '' })
const loading = ref(false)

/* 引擎实例状态徽标（对齐 master/state.py 实例状态集） */
const STATE_MAP: Record<string, { label: string; cls: string }> = {
  submitted: { label: '已提交', cls: 'st-gray' },
  running: { label: '运行中', cls: 'st-blue' },
  success: { label: '成功', cls: 'st-green' },
  failure: { label: '失败', cls: 'st-red' },
  kill: { label: '已终止', cls: 'st-gray' },
}
const stateOptions = Object.entries(STATE_MAP).map(([v, m]) => ({ v, t: m.label }))

const facets = [{ key: 'state', label: '最近状态', options: stateOptions }]

function stCls(s: string | null): string {
  return (s && STATE_MAP[s]?.cls) || 'st-gray'
}
function stLabel(s: string | null): string {
  return (s && STATE_MAP[s]?.label) || s || '-'
}

async function reload() {
  loading.value = true
  try {
    const page = await listSyncTasks({
      pageNo: 1, pageSize: 200,
      keyword: keyword.value.trim() || undefined,
      state: filters.value.state || undefined,
    })
    rows.value = page.list
    total.value = page.total
  } finally {
    loading.value = false
  }
}

onMounted(reload)

/* 筛选即时生效（后端过滤；ListFilterPanel 无 change 事件，watch 值变化） */
watch([keyword, () => filters.value.state], reload)

function goDetail(r: SyncTaskRow) {
  router.push(`/sync/detail/${r.wfCode}`)
}
function goCreate() {
  /* I1 意见⑬：独立向导移除，同步编排统一落 DAG 工作台（C17 直拖 / C23 模板） */
  router.push('/dag?tab=sync')
}
function goInstances() {
  router.push('/dag/instances')
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      :result-count="rows.length"
      :total-count="total"
      placeholder="搜索同步任务名"
    />
    <div style="flex:1;min-width:0">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">同步任务</span>
        <span class="pill info">{{ rows.length }} / {{ total }}</span>
        <span class="col-sub">批次号 = 运行实例 instance_id；打「同步」标签的工作流纳入监控（C23 保存自动打标）</span>
        <span class="spacer" />
        <button class="tb-new" @click="goCreate">＋ 新建同步</button>
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>任务名</th><th>实例数</th><th>最近批次</th><th>最近状态</th>
            <th>读 / 写行数</th><th>坏行</th><th>参与 schema</th><th>最近同步时间</th><th style="width:110px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in rows" :key="r.wfCode">
            <td>
              <a @click="goDetail(r)"><b>{{ r.name }}</b></a>
              <div class="col-sub">
                <span v-for="t in r.tags" :key="t" class="pill info" style="margin-right:4px">{{ t }}</span>
              </div>
            </td>
            <td>{{ r.instanceCount }}</td>
            <td><span class="mono" style="font-size:11px">{{ r.lastInstanceId || '-' }}</span></td>
            <td>
              <span class="st" :class="stCls(r.lastState)"><span class="dot" />{{ stLabel(r.lastState) }}</span>
            </td>
            <td>
              <span class="mono">{{ r.readRows }} / {{ r.writeRows }}</span>
            </td>
            <td>
              <span class="mono" :style="r.badRows > 0 ? 'color:var(--danger)' : ''">{{ r.badRows }}</span>
            </td>
            <td>
              <span class="mono col-sub" :title="r.schemas.join(', ')">{{ r.schemas.length ? r.schemas.join(', ') : '-' }}</span>
            </td>
            <td style="color:var(--text-2)">{{ r.lastTime || '-' }}</td>
            <td>
              <button class="op-btn primary" @click="goDetail(r)">详情</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="rows.length === 0 && !loading" class="empty">
        暂无同步任务：在 DAG 工作台拖入「数据同步」节点或「同步编排」模板，保存后自动纳入监控
      </div>
      <div v-if="rows.length > 0" class="tbl-foot">
        <button class="op-btn" @click="goInstances">查看运行实例 →</button>
      </div>
    </div>
    </div>
  </div>
</template>

<style scoped>
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.tbl-foot{padding:10px 2px 2px;text-align:right}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.col-sub{margin-top:2px;font-size:11px;color:var(--text-3)}
</style>
