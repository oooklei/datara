<script setup lang="ts">
/**
 * M10i 一致性检查（/ind/consistency）
 * 对齐 prototype/assets/pages/m10-standard.js L767-791：
 * 统计卡片（检查指标数/口径一致/口径冲突）+ 检查结果表（indConsistency）；
 * 行操作：fail → 发起整改（确认后按标准口径修正并复检）；pass → 详情。
 */
import { ref, computed, onMounted } from 'vue'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import type { IndConsistency } from '../../services/types'

/** 种子行无 id 字段：补 id=metric 后 dataStore.save 才能按 id 原位替换并持久化 */
type IndConsRow = IndConsistency & { id: string }

const rows = ref<IndConsRow[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ result: '' })

const passCount = computed(() => rows.value.filter((r) => r.result === 'pass').length)
const failCount = computed(() => rows.value.length - passCount.value)

/* ---- 左侧筛选面板 facets ---- */
const facets = computed<Facet[]>(() => [
  {
    key: 'result',
    label: '一致性结果',
    options: [
      { v: 'pass', t: '一致' },
      { v: 'fail', t: '不一致' },
    ],
  },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.result && r.result !== filters.value.result) return false
    if (!kw) return true
    return r.metric.toLowerCase().includes(kw)
  })
})

async function reload() {
  // 保留 dataStore 内数组引用（不展开）：行对象补 id 后可直接 save 原位替换
  const arr = await dataStore.list<IndConsistency>('indConsistency')
  for (const r of arr) {
    const row = r as IndConsRow
    if (!row.id) row.id = row.metric
  }
  rows.value = arr as IndConsRow[]
}

onMounted(reload)

/* ---- ST 徽标（原型：pass → 通过，fail → 按 reject 展示） ---- */
function resultCls(r: IndConsRow): string {
  return ST[r.result === 'pass' ? 'pass' : 'reject']?.cls ?? 'st-gray'
}
function resultLabel(r: IndConsRow): string {
  return ST[r.result === 'pass' ? 'pass' : 'reject']?.label ?? r.result
}

/* ---- 发起整改 ---- */
async function fix(r: IndConsRow) {
  try {
    await ElMessageBox.confirm(
      `对「${r.metric}」发起口径对齐整改？整改方向：按标准口径（不含退款）修正经营日报计算逻辑，修正后复检。`,
      '发起口径整改',
      { confirmButtonText: '发起整改', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  r.result = 'pass'
  r.detail = '已整改：经营日报调整为标准口径（不含退款），复检一致'
  await dataStore.save('indConsistency', r)
  ElMessage.success('整改完成，复检通过')
}

/* ---- 详情 ---- */
function showDetail(r: IndConsRow) {
  ElMessage.info(`${r.metric}：${r.detail}`)
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索指标"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <!-- 统计卡片 -->
    <div class="stat-row">
      <div class="stat-card">
        <span class="type-icon" style="background:#1668dc">⇋</span>
        <div><div class="stat-num">{{ rows.length }}</div><div class="stat-label">检查指标数</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:#16a34a">✓</span>
        <div><div class="stat-num" style="color:var(--success)">{{ passCount }}</div><div class="stat-label">口径一致</div></div>
      </div>
      <div class="stat-card">
        <span class="type-icon" style="background:#e5484d">✗</span>
        <div><div class="stat-num" style="color:var(--danger)">{{ failCount }}</div><div class="stat-label">口径冲突</div></div>
      </div>
    </div>

    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">检查结果</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>指标</th><th>使用位置</th><th>结果</th><th>差异详情</th><th style="width:110px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td><b>{{ r.metric }}</b></td>
            <td>
              <span v-for="p in r.places" :key="p" class="pill info" style="margin:1px 4px 1px 0">{{ p }}</span>
            </td>
            <td>
              <span class="st" :class="resultCls(r)"><span class="dot" />{{ resultLabel(r) }}</span>
            </td>
            <td style="font-size:11.5px;color:var(--text-2)">{{ r.detail }}</td>
            <td>
              <button v-if="r.result === 'fail'" class="op-btn primary" @click="fix(r)">发起整改</button>
              <button v-else class="op-btn" @click="showDetail(r)">详情</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="filtered.length === 0" class="empty">未找到匹配的检查结果</div>
    </div>
    </div>
  </div>
</template>

<style scoped>
.stat-row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:14px}
.stat-card{display:flex;align-items:center;gap:10px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);padding:14px 16px;box-shadow:var(--shadow)}
.stat-num{font-size:22px;font-weight:700}
.stat-label{font-size:11.5px;color:var(--text-3)}
.type-icon{width:34px;height:34px;border-radius:var(--radius);display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;flex-shrink:0}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none}
.kw:focus{border-color:var(--primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
</style>
