<script setup lang="ts">
/**
 * M16 组件日志（/dep/log · 原型 m16-deploy.js #/dep/log）
 * 部署与运行日志聚合（dataStore.deployLogs）：关键字检索 + 组件/级别筛选；
 * 行操作：查看（弹窗全文）/ 复制；ERROR 日志提供「去处置」跳转运维操作。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import { ElMessage } from 'element-plus'
import { dataStore } from '../../services/mock/dataStore'
import type { DeployLog } from '../../services/types'

const router = useRouter()

const rows = ref<DeployLog[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ comp: '', level: '' })

const LEVELS = ['INFO', 'WARN', 'ERROR']

const compOptions = computed(() => [...new Set(rows.value.map((r) => r.comp))])

/* ---- 左侧筛选面板 facets ---- */
const facets = computed<Facet[]>(() => [
  { key: 'comp', label: '组件', options: compOptions.value.map((c) => ({ v: c, t: c })) },
  { key: 'level', label: '级别', options: LEVELS.map((l) => ({ v: l, t: l })) },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.comp && r.comp !== filters.value.comp) return false
    if (filters.value.level && r.level !== filters.value.level) return false
    if (!kw) return true
    return [r.id, r.comp, r.node, r.content].some((s) => s.toLowerCase().includes(kw))
  })
})

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，list 返回同一引用
  rows.value = [...((await dataStore.list<DeployLog>('deployLogs')) ?? [])]
}
onMounted(reload)

function levelPill(l: string): string {
  return l === 'ERROR' ? 'err' : l === 'WARN' ? 'warn' : 'off'
}
function goOps(): void {
  router.push('/dep/ops')
}

/* ---- 查看全文 ---- */
const viewVisible = ref(false)
const viewRow = ref<DeployLog | null>(null)
function openView(r: DeployLog): void {
  viewRow.value = r
  viewVisible.value = true
}

/* ---- 复制（剪贴板不可用时降级 execCommand） ---- */
async function copyLog(r: DeployLog): Promise<void> {
  const text = r.content
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    const ta = document.createElement('textarea')
    ta.value = text
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    ta.remove()
  }
  ElMessage.success('日志已复制')
}
function copyViewLog(): void {
  if (viewRow.value) void copyLog(viewRow.value)
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索日志内容"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">日志流</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>时间</th><th>组件</th><th>节点</th><th>级别</th><th>内容</th><th style="width:170px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td><span class="mono" style="font-size:11.5px;color:var(--text-2)">{{ r.time }}</span></td>
            <td><span class="pill info">{{ r.comp }}</span></td>
            <td><span class="mono" style="font-size:11.5px">{{ r.node }}</span></td>
            <td><span class="pill" :class="levelPill(r.level)">{{ r.level }}</span></td>
            <td><span class="mono" style="font-size:11.5px">{{ r.content }}</span></td>
            <td>
              <button class="op-btn primary" @click="openView(r)">查看</button>
              <button v-if="r.level === 'ERROR'" class="op-btn danger" @click="goOps">去处置</button>
              <button v-else class="op-btn" @click="copyLog(r)">复制</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="filtered.length === 0" class="empty">
        未找到匹配的日志，请调整筛选条件
      </div>
    </div>

    <!-- 查看日志弹窗 -->
    <el-dialog v-model="viewVisible" title="日志详情" width="560px">
      <div v-if="viewRow">
        <div class="d-meta">
          <span class="mono">{{ viewRow.id }}</span>
          <span class="pill info">{{ viewRow.comp }}</span>
          <span class="pill" :class="levelPill(viewRow.level)">{{ viewRow.level }}</span>
          <span class="mono cell-sub">{{ viewRow.node }}</span>
          <span class="cell-sub" style="margin-left:auto">{{ viewRow.time }}</span>
        </div>
        <pre class="log-box mono">{{ viewRow.content }}</pre>
      </div>
      <template #footer>
        <button class="op-btn" style="margin-right:8px" @click="copyViewLog">复制内容</button>
        <button class="tb-new" @click="viewVisible = false">关闭</button>
      </template>
    </el-dialog>
    </div>
  </div>
</template>

<style scoped>
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.cell-sub{font-size:11px;color:var(--text-3)}
.d-meta{display:flex;align-items:center;gap:8px;font-size:12px;margin-bottom:10px}
.log-box{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:11px 12px;font-size:11.5px;line-height:1.7;color:var(--text-2);white-space:pre-wrap;word-break:break-all;margin:0;max-height:260px;overflow:auto}
</style>
