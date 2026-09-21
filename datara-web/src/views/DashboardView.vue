<script setup lang="ts">
/* 工作台（/）—— 首页：真实通道实时统计（F56a：替代硬编码假数据）+ 快捷入口 */
import { onMounted, ref } from 'vue'
import { listDefinitions, listRuntimeNodes } from '../services'
import { listDataSources } from '../services/datasourceApi'
import { listSyncTasks } from '../services/syncApi'

interface Stat {
  k: string; v: string; d: string
  ic: string; ib: string; ic2: string; cls?: string
}

const stats = ref<Stat[]>([
  { k: '工作流定义', v: '—', d: '调度引擎注册定义', ic: '⑃', ib: 'rgba(22,104,220,.10)', ic2: '#1668dc' },
  { k: '同步任务', v: '—', d: '已配置同步任务', ic: '⇄', ib: 'rgba(22,104,220,.10)', ic2: '#1668dc' },
  { k: '数据源', v: '—', d: '已接入数据源连接', ic: '⛁', ib: 'rgba(22,163,74,.10)', ic2: '#16a34a' },
  { k: '运行时节点', v: '—', d: '集群运行节点', ic: '⌂', ib: 'rgba(217,119,6,.10)', ic2: '#d97706' },
])

/** 统一拉四类真实通道计数（F56a）：任一失败该卡显示 —，不阻断其余 */
onMounted(async () => {
  const safe = async <T,>(p: Promise<T>): Promise<T | null> => { try { return await p } catch { return null } }
  const [defs, syncs, dss, nodes] = await Promise.all([
    safe(listDefinitions({ pageNo: 1, pageSize: 500 })),
    safe(listSyncTasks()),
    safe(listDataSources()),
    safe(listRuntimeNodes()),
  ])
  if (defs) stats.value[0] = { ...stats.value[0]!, v: String(defs.length) }
  if (syncs) stats.value[1] = { ...stats.value[1]!, v: String(syncs.total) }
  if (dss) stats.value[2] = { ...stats.value[2]!, v: String(dss.length) }
  if (nodes) stats.value[3] = { ...stats.value[3]!, v: String(nodes.length) }
})

const entries = [
  { title: 'DAG 可视化编排', desc: '任务中心直达编排：任务库拖拽 / 环校验 / 试运行 / 版本管理', path: '/dag', tag: '任务中心' },
  { title: '集群拓扑监控', desc: '五层泳道：接入 → 运行时 → 中间件 → 计算引擎 → 存储', path: '/dep/monitor', tag: '集群监控' },
]
</script>

<template>
  <div class="page">
    <div class="stat-grid">
      <div v-for="s in stats" :key="s.k" class="card stat">
        <div class="stat-top">
          <span class="stat-ico" :style="{ background: s.ib, color: s.ic2 }">{{ s.ic }}</span>
          <span class="k">{{ s.k }}</span>
        </div>
        <div class="v" :style="s.cls ? { color: s.cls } : {}">{{ s.v }}</div>
        <div class="d">{{ s.d }}</div>
      </div>
    </div>

    <div class="card" style="padding:16px">
      <div class="sec-title">快捷入口</div>
      <div class="sec-sub">
        从任务中心直达可视化编排（工作流 / 同步 / ETL / 流统一入口），或前往集群监控查看运行状态。
      </div>
      <div class="entry-grid">
        <div
          v-for="e in entries" :key="e.path"
          class="entry-card"
          @click="$router.push(e.path)"
        >
          <div class="entry-top">
            <div class="entry-title">{{ e.title }}</div>
            <span class="entry-arrow">→</span>
          </div>
          <div class="entry-desc">{{ e.desc }}</div>
          <span class="pill info">{{ e.tag }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stat{padding:16px}
.stat-top{display:flex;align-items:center;gap:8px;margin-bottom:10px}
.stat-ico{width:28px;height:28px;border-radius:var(--radius);display:inline-flex;align-items:center;justify-content:center;font-size:13px;flex-shrink:0}
.k{font-size:12.5px;color:var(--text-2)}
.v{font-size:24px;font-weight:700;line-height:1.2;letter-spacing:-.3px;font-variant-numeric:tabular-nums}
.d{font-size:11.5px;color:var(--text-3);margin-top:3px}
.sec-title{display:flex;align-items:center;gap:8px;font-weight:700;font-size:14px;margin-bottom:4px}
.sec-title::before{content:'';width:3px;height:14px;border-radius:2px;background:linear-gradient(180deg,var(--primary),var(--purple))}
.sec-sub{font-size:12px;color:var(--text-3);margin-bottom:12px}
.entry-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:10px}
.entry-card{border:1px solid var(--border);border-radius:var(--radius);padding:14px;cursor:pointer;transition:all var(--dur-base) var(--ease);background:var(--card)}
.entry-card:hover{border-color:var(--primary);box-shadow:var(--shadow-primary);transform:translateY(-1px)}
.entry-top{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
.entry-title{font-weight:700;font-size:13.5px}
.entry-arrow{color:var(--text-3);transition:transform var(--dur-base) var(--ease)}
.entry-card:hover .entry-arrow{transform:translateX(3px);color:var(--primary)}
.entry-desc{font-size:12px;color:var(--text-2);line-height:1.55;margin-bottom:10px}
.pill{display:inline-flex;align-items:center;padding:2px 9px;border-radius:999px;font-size:11px;font-weight:600}
.pill.info{background:var(--info-bg);color:var(--info)}
</style>
