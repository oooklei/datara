<script setup lang="ts">
/**
 * ResultPanel（I10 G17~G20 + G5 日志区）：
 * - 结果 Tab 组：每次运行按语句独立 Tab（结果 #N），关闭单个/一键清空；点击 Tab 回显原始 SQL（store.setActiveResult）
 * - 查询 Tab：vxe-table v4（列排序/列宽拖拽/虚拟滚动/单元格点击复制）
 * - 列筛选：7 操作符多列组合，仅作用于内存首屏（Tab 隔离，绝不触发后端）
 * - 分页：内存分页优先；超出首屏且已落历史 → /ide/result 重放端点（提示页间可能漂移）
 * - DML/DDL Tab：只显受影响行数；错误 Tab：错误详情 + SQL 回显
 * - 导出弹窗：全部原始（后端重放 csv/json/xlsx）/ 筛选子集（前端内存生成 csv/json）
 * - 执行日志面板（start/end/error/vars/txn 全渲染，自动滚底）
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
// vxe-table 4.21 自包含构建按需引入：根入口未导出组件值且深路径无 d.ts（显式豁免），样式单独引入
// @ts-expect-error vxe-table 深路径模块无类型声明
import VxeTable from 'vxe-table/es/vxe-table/index.js'
// @ts-expect-error vxe-table 深路径模块无类型声明
import VxeColumn from 'vxe-table/es/vxe-column/index.js'
import 'vxe-table/es/style.css'
import dayjs from 'dayjs'
import { useIdeStore, FILTER_OPS, type ResultFilter } from '../../../stores/ideStore'
import { fetchResultPage, exportIdeResult, downloadBlob, type IdeExportFormat } from '../../../services/ideApi'

const store = useIdeStore()

const activeTab = computed(() => store.results.find((t) => t.id === store.activeResultId) ?? null)

/* ================= 列筛选（G19：仅内存首屏，Tab 隔离） ================= */

function filterActive(f: ResultFilter): boolean {
  return f.op === 'empty' || f.op === 'notEmpty' || f.value.trim() !== ''
}

function matchFilter(row: string[], f: ResultFilter): boolean {
  const cell = row[f.col] ?? ''
  switch (f.op) {
    case 'include': return cell.includes(f.value)
    case 'eq': return cell === f.value
    case 'ne': return cell !== f.value
    case 'empty': return cell.trim() === ''
    case 'notEmpty': return cell.trim() !== ''
    case 'gt': {
      const a = Number(cell); const b = Number(f.value)
      return !Number.isNaN(a) && !Number.isNaN(b) ? a > b : cell > f.value
    }
    case 'lt': {
      const a = Number(cell); const b = Number(f.value)
      return !Number.isNaN(a) && !Number.isNaN(b) ? a < b : cell < f.value
    }
  }
}

const filterPanelVisible = ref(false)
const colOptions = computed(() => (activeTab.value?.columns ?? []).map((c, i) => ({ label: c || `列${i + 1}`, value: i })))

function addFilter(): void {
  const tab = activeTab.value
  if (!tab) return
  if (tab.columns.length === 0) {
    ElMessage.warning('当前结果无列可筛选')
    return
  }
  tab.filters.push({ col: 0, op: 'include', value: '' })
  resetReplay()
}

function clearFilters(): void {
  const tab = activeTab.value
  if (!tab) return
  tab.filters = []
  resetReplay()
}

/** 有生效筛选时：全部内存首屏行先过滤，再分页（仅内存，不重放） */
const filteredAll = computed<string[][] | null>(() => {
  const tab = activeTab.value
  if (!tab || tab.kind !== 'query') return null
  const active = tab.filters.filter(filterActive)
  if (active.length === 0) return null
  let rows = tab.rows
  for (const f of active) rows = rows.filter((r) => matchFilter(r, f))
  return rows
})

/* ================= 分页（内存优先 → 重放端点） ================= */

const replayRows = ref<string[][] | null>(null)
const replayOffset = ref(-1)
const replayLoading = ref(false)
const replayUsed = ref(false)

function resetReplay(): void {
  replayRows.value = null
  replayOffset.value = -1
}

const PAGE_SIZES = [100, 200, 500, 1000]

const totalRows = computed(() => {
  const tab = activeTab.value
  if (!tab) return 0
  if (filteredAll.value) return filteredAll.value.length
  return tab.rowsTotal || tab.rows.length
})

const maxPage = computed(() => Math.max(1, Math.ceil(totalRows.value / (activeTab.value?.pageSize ?? 200))))

const displayRows = computed<string[][]>(() => {
  const tab = activeTab.value
  if (!tab || tab.kind !== 'query') return []
  const start = (tab.page - 1) * tab.pageSize
  if (filteredAll.value) return filteredAll.value.slice(start, start + tab.pageSize)
  if (replayRows.value && replayOffset.value === start) return replayRows.value
  return tab.rows.slice(start, start + tab.pageSize)
})

async function goPage(p: number): Promise<void> {
  const tab = activeTab.value
  if (!tab || tab.kind !== 'query') return
  const target = Math.min(Math.max(1, p), maxPage.value)
  if (filteredAll.value) {
    resetReplay()
    tab.page = target
    return
  }
  const start = (target - 1) * tab.pageSize
  const fullyInMem = tab.rowsTotal <= tab.rows.length || start + tab.pageSize <= tab.rows.length
  if (fullyInMem) {
    resetReplay()
    tab.page = target
    return
  }
  if (tab.historyId === null) {
    ElMessage.warning('仅首屏在内存中且结果尚未落历史，无法翻页（执行完成后重试）')
    return
  }
  replayLoading.value = true
  try {
    const resp = await fetchResultPage(tab.historyId, tab.stmtIndex, start, tab.pageSize)
    replayRows.value = resp.rows.map((r) => r.map((v) => (v === null || v === undefined ? '' : String(v))))
    replayOffset.value = start
    replayUsed.value = true
    tab.page = target
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '重放分页失败')
  } finally {
    replayLoading.value = false
  }
}

function onPageSizeChange(): void {
  resetReplay()
  const tab = activeTab.value
  if (tab) tab.page = 1
}

/** 切 Tab：重放页失效（页缓存属组件级，Tab 数据各自隔离在 store） */
watch(() => store.activeResultId, () => {
  resetReplay()
  replayUsed.value = false
  filterPanelVisible.value = false
})

/* ================= vxe-table（排序/列宽拖拽/虚拟滚动/单元格复制） ================= */

const tableData = computed(() => {
  const cols = activeTab.value?.columns ?? []
  return displayRows.value.map((r) => {
    const o: Record<string, string> = {}
    for (let i = 0; i < cols.length; i++) o[`c${i}`] = r[i] ?? ''
    return o
  })
})

function onCellClick(params: unknown): void {
  const p = params as { row?: Record<string, string>; column?: { field?: string | null } }
  const field = p.column?.field
  if (!field) return
  const val = p.row?.[field] ?? ''
  const show = () => ElMessage.success(`已复制单元格：${val.length > 60 ? val.slice(0, 60) + '…' : val}`)
  // http 非安全源下 navigator.clipboard 为 undefined（同步抛 TypeError），降级 execCommand
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(val).then(show).catch(() => fallbackCopy(val, show))
  } else {
    fallbackCopy(val, show)
  }
}

function fallbackCopy(val: string, ok: () => void): void {
  const ta = document.createElement('textarea')
  ta.value = val
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  let done = false
  try { done = document.execCommand('copy') } catch { done = false }
  document.body.removeChild(ta)
  if (done) ok()
  else ElMessage.warning(`复制失败，单元格值：${val.length > 60 ? val.slice(0, 60) + '…' : val}`)
}

/* 表格容器高度自适应（vxe 虚拟滚动需确定高度） */
const tableWrapRef = ref<HTMLElement | null>(null)
const tableHeight = ref(320)
let resizeObs: ResizeObserver | null = null

onMounted(() => {
  if (tableWrapRef.value) {
    resizeObs = new ResizeObserver((entries) => {
      for (const en of entries) tableHeight.value = Math.max(140, Math.floor(en.contentRect.height))
    })
    resizeObs.observe(tableWrapRef.value)
  }
})

onBeforeUnmount(() => {
  resizeObs?.disconnect()
  resizeObs = null
})

/* ================= 导出弹窗（G20） ================= */

const exportVisible = ref(false)
const exportScope = ref<'all' | 'subset'>('all')
const exportFormat = ref<IdeExportFormat>('csv')
const exporting = ref(false)

function openExport(): void {
  if (!activeTab.value) return
  exportScope.value = 'all'
  exportFormat.value = 'csv'
  exportVisible.value = true
}

watch(() => store.exportDialogN, (n) => {
  if (n <= 0) return
  if (!activeTab.value) return
  exportScope.value = 'all'
  exportFormat.value = 'csv'
  exportVisible.value = true
})

function csvCell(v: string): string {
  return `"${v.replace(/"/g, '""')}"`
}

function makeCsv(cols: string[], rows: string[][]): string {
  const lines = [cols.map(csvCell).join(',')]
  for (const r of rows) {
    const arr: string[] = []
    for (let i = 0; i < cols.length; i++) arr.push(csvCell(r[i] ?? ''))
    lines.push(arr.join(','))
  }
  return lines.join('\r\n')
}

function exportExt(fmt: IdeExportFormat): string {
  return fmt === 'csv' ? '.csv' : fmt === 'json' ? '.json' : '.xlsx'
}

async function doExport(): Promise<void> {
  const tab = activeTab.value
  if (!tab) return
  const fmt = exportFormat.value
  if (exportScope.value === 'all') {
    if (tab.historyId === null) {
      ElMessage.warning('该结果尚未关联执行历史（执行完成后自动落库），暂不能导出全部原始结果')
      return
    }
    exporting.value = true
    try {
      const blob = await exportIdeResult(tab.historyId, fmt)
      downloadBlob(blob, `结果#${tab.seq}_${dayjs().format('YYYYMMDD_HHmmss')}${exportExt(fmt)}`)
      exportVisible.value = false
      ElMessage.success('导出成功（后端重放全部原始结果）')
    } catch (err) {
      ElMessage.error(err instanceof Error ? err.message : '导出失败')
    } finally {
      exporting.value = false
    }
    return
  }
  if (fmt === 'xlsx') {
    ElMessage.info('筛选子集仅支持 CSV / JSON（前端内存生成）')
    return
  }
  const rows = filteredAll.value ?? tab.rows
  const cols = tab.columns
  let blob: Blob
  if (fmt === 'json') {
    const arr = rows.map((r) => {
      const o: Record<string, string> = {}
      cols.forEach((c, i) => { o[c] = r[i] ?? '' })
      return o
    })
    blob = new Blob([JSON.stringify(arr, null, 2)], { type: 'application/json;charset=utf-8' })
  } else {
    blob = new Blob(['\ufeff' + makeCsv(cols, rows)], { type: 'text/csv;charset=utf-8' })
  }
  downloadBlob(blob, `结果#${tab.seq}_筛选子集${rows.length}行_${dayjs().format('YYYYMMDD_HHmmss')}.${fmt}`)
  exportVisible.value = false
  ElMessage.success(`已导出筛选子集 ${rows.length} 行`)
}

/* ================= 执行日志（自动滚底） ================= */

const logBoxRef = ref<HTMLElement | null>(null)
const logVisible = ref(true)

watch(() => store.logs.length, () => {
  void nextTick(() => {
    if (logBoxRef.value) logBoxRef.value.scrollTop = logBoxRef.value.scrollHeight
  })
})

const LOG_ICONS: Record<string, string> = {
  start: '▶', end: '✔', error: '✗', vars: '$', txn: '⇄', info: '·',
}
</script>

<template>
  <div class="rpanel">
    <!-- 结果 Tab 组（区域顶部） -->
    <div class="rp-tabs">
      <div
        v-for="t in store.results"
        :key="t.id"
        class="rtab"
        :class="{ on: t.id === store.activeResultId, err: t.kind === 'error', exec: t.kind === 'exec' }"
        :title="t.sql"
        @click="store.setActiveResult(t.id)"
      >
        <span>{{ t.kind === 'query' ? `结果 #${t.seq}` : t.kind === 'exec' ? `DML #${t.seq}` : '错误' }}</span>
        <span class="rtab-x" title="关闭" @click.stop="store.closeResultTab(t.id)">×</span>
      </div>
      <button v-if="store.results.length" class="op-btn rp-clear" @click="store.clearResults()">一键清空</button>
    </div>

    <!-- 主体 -->
    <div class="rp-body">
      <template v-if="activeTab">
        <!-- 错误 Tab -->
        <div v-if="activeTab.kind === 'error'" class="rp-error">
          <div class="rp-error-title">语句 {{ activeTab.stmtIndex + 1 }} 执行失败（{{ activeTab.elapsedMs }}ms）</div>
          <pre class="rp-error-msg mono">{{ activeTab.error }}</pre>
          <div class="rp-sql mono">{{ activeTab.sql }}</div>
          <button class="op-btn" @click="store.requestFill(activeTab.sql)">回显 SQL 到编辑器</button>
        </div>

        <!-- DML/DDL Tab：只显受影响行数 -->
        <div v-else-if="activeTab.kind === 'exec'" class="rp-exec">
          <div class="exec-card">
            <div class="exec-num mono">{{ activeTab.affected }}</div>
            <div class="exec-label">受影响行数（{{ activeTab.elapsedMs }}ms）</div>
          </div>
          <div class="rp-sql mono">{{ activeTab.sql }}</div>
          <button class="op-btn" @click="store.requestFill(activeTab.sql)">回显 SQL 到编辑器</button>
        </div>

        <!-- 查询 Tab -->
        <template v-else>
          <div class="rp-toolbar">
            <span class="rp-stat mono">
              共 {{ totalRows }} 行 · 内存 {{ activeTab.rows.length }} 行 · {{ activeTab.elapsedMs }}ms
              <template v-if="filteredAll">（筛选后 {{ filteredAll.length }} 行）</template>
            </span>
            <span v-if="replayUsed" class="rp-warn">重放分页可能页间漂移</span>
            <span class="spacer" />
            <button class="op-btn" @click="filterPanelVisible = !filterPanelVisible">
              筛选{{ activeTab.filters.length ? `（${activeTab.filters.filter(filterActive).length}）` : '' }}
            </button>
            <button class="op-btn" @click="openExport()">导出</button>
          </div>

          <!-- 筛选面板 -->
          <div v-if="filterPanelVisible" class="rp-filters">
            <div v-for="(f, fi) in activeTab.filters" :key="fi" class="f-row">
              <select v-model="f.col" class="sel" @change="resetReplay()">
                <option v-for="c in colOptions" :key="c.value" :value="c.value">{{ c.label }}</option>
              </select>
              <select v-model="f.op" class="sel op" @change="resetReplay()">
                <option v-for="o in FILTER_OPS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
              <input
                v-model="f.value"
                class="kw"
                placeholder="筛选值（为空/非空时忽略）"
                :disabled="f.op === 'empty' || f.op === 'notEmpty'"
                @input="resetReplay()"
              />
              <button class="op-btn danger" @click="activeTab.filters.splice(fi, 1); resetReplay()">×</button>
            </div>
            <div class="f-foot">
              <button class="op-btn" @click="addFilter">＋ 加一列条件</button>
              <button class="op-btn" @click="clearFilters">清空筛选</button>
              <span class="f-hint">筛选仅作用于内存首屏（{{ activeTab.rows.length }} 行），不触发后端</span>
            </div>
          </div>

          <!-- 结果表 -->
          <div ref="tableWrapRef" class="rp-table-wrap">
            <div v-if="replayLoading" class="rp-loading">重放分页加载中…</div>
            <vxe-table
              v-else
              :data="tableData"
              :height="tableHeight"
              :scroll-y="{ enabled: true, gt: 60 }"
              :column-config="{ resizable: true }"
              :row-config="{ isHover: true }"
              stripe
              border
              show-overflow
              @cell-click="onCellClick"
            >
              <vxe-column type="seq" title="#" width="56" fixed="left" />
              <vxe-column
                v-for="(c, ci) in activeTab.columns"
                :key="c + ci"
                :field="'c' + ci"
                :title="c || `列${ci + 1}`"
                sortable
                min-width="120"
              />
            </vxe-table>
            <div v-if="tableData.length === 0 && !replayLoading" class="rp-empty">
              {{ store.running ? '执行中，等待结果返回…' : '无数据行' }}
            </div>
          </div>

          <!-- 分页条 -->
          <div class="rp-pager">
            <button class="op-btn" :disabled="activeTab.page <= 1" @click="goPage(activeTab.page - 1)">← 上一页</button>
            <span class="mono">第 {{ activeTab.page }} / {{ maxPage }} 页</span>
            <button class="op-btn" :disabled="activeTab.page >= maxPage" @click="goPage(activeTab.page + 1)">下一页 →</button>
            <select v-model="activeTab.pageSize" class="sel" @change="onPageSizeChange">
              <option v-for="n in PAGE_SIZES" :key="n" :value="n">{{ n }} 行/页</option>
            </select>
            <span v-if="activeTab.historyId === null && activeTab.rowsTotal > activeTab.rows.length" class="rp-warn">
              仅首屏 {{ activeTab.rows.length }}/{{ activeTab.rowsTotal }} 行在内存（历史未落库）
            </span>
          </div>
        </template>
      </template>
      <div v-else class="rp-empty big">暂无执行结果 —— 在编辑器运行 SQL 后，每条语句的结果将在此独立成 Tab</div>
    </div>

    <!-- 执行日志 -->
    <div class="rp-logs" :class="{ collapsed: !logVisible }">
      <button class="op-btn rp-log-toggle" @click="logVisible = !logVisible">
        {{ logVisible ? '▾ 执行日志' : '▸ 执行日志' }}（{{ store.logs.length }}）
      </button>
      <div v-show="logVisible" ref="logBoxRef" class="log-box">
        <div v-for="l in store.logs" :key="l.seq" class="log-line" :class="'k-' + l.kind">
          <span class="log-t mono">{{ l.time }}</span>
          <span class="log-i">{{ LOG_ICONS[l.kind] ?? '·' }}</span>
          <span class="log-x mono">{{ l.text }}</span>
        </div>
        <div v-if="store.logs.length === 0" class="log-empty">暂无日志</div>
      </div>
    </div>

    <!-- 导出弹窗（G20） -->
    <el-dialog v-model="exportVisible" title="导出执行结果" width="480px" append-to-body>
      <div class="exp-body">
        <div class="exp-sec">
          <div class="exp-k">范围</div>
          <el-radio-group v-model="exportScope">
            <el-radio value="all">全部原始结果（后端重放）</el-radio>
            <el-radio value="subset">筛选子集（当前内存{{ filteredAll ? ` ${filteredAll.length} 行` : '首屏' }}）</el-radio>
          </el-radio-group>
        </div>
        <div class="exp-sec">
          <div class="exp-k">格式</div>
          <el-radio-group v-model="exportFormat">
            <el-radio value="csv">CSV</el-radio>
            <el-radio value="json">JSON</el-radio>
            <el-radio v-if="exportScope === 'all'" value="xlsx">XLSX</el-radio>
          </el-radio-group>
        </div>
        <div class="exp-tip">
          全部原始=后端按 historyId 重放导出；筛选子集=仅导出当前内存（首屏）筛选结果。单元格值均按文本处理。
        </div>
      </div>
      <template #footer>
        <button class="op-btn" @click="exportVisible = false">取消</button>
        <button class="tb-new" :disabled="exporting" @click="doExport">{{ exporting ? '导出中…' : '导出' }}</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.rpanel{display:flex;flex-direction:column;height:100%;background:var(--ide-card);overflow:hidden}
.rp-tabs{display:flex;align-items:center;gap:2px;padding:5px 8px 0;border-bottom:1px solid var(--ide-border);overflow-x:auto;flex-shrink:0}
.rtab{display:inline-flex;align-items:center;gap:6px;padding:5px 8px;font-size:12px;cursor:pointer;color:var(--ide-text-2);border:1px solid transparent;border-bottom:none;border-radius:6px 6px 0 0;white-space:nowrap}
.rtab:hover{background:var(--ide-hover)}
.rtab.on{background:var(--ide-bg);border-color:var(--ide-border);color:var(--primary);font-weight:600}
.rtab.exec.on{color:var(--warn)}
.rtab.err.on{color:var(--danger)}
.rtab-x{border-radius:3px;padding:0 4px;color:var(--ide-text-3);font-size:13px}
.rtab-x:hover{background:var(--danger-bg);color:var(--danger)}
.rp-clear{margin:0 0 4px 8px;flex-shrink:0}
.rp-body{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}
.rp-toolbar{display:flex;align-items:center;gap:8px;padding:6px 10px;border-bottom:1px solid var(--ide-border);flex-wrap:wrap}
.rp-stat{font-size:11.5px;color:var(--ide-text-3)}
.rp-warn{font-size:11.5px;color:var(--ide-warn)}
.spacer{flex:1}
/* 筛选面板 */
.rp-filters{padding:8px 10px;border-bottom:1px solid var(--ide-border);background:var(--ide-bg);display:flex;flex-direction:column;gap:6px}
.f-row{display:flex;align-items:center;gap:6px}
.f-row .sel{width:150px}
.f-row .sel.op{width:96px}
.f-row .kw{flex:1;min-width:80px}
.f-foot{display:flex;align-items:center;gap:8px}
.f-hint{font-size:11px;color:var(--ide-text-3);margin-left:auto}
.sel{border:1px solid var(--ide-border-strong);border-radius:var(--radius-sm);padding:4px 6px;font-size:12px;background:var(--ide-input);color:var(--ide-text);outline:none}
.kw{border:1px solid var(--ide-border-strong);border-radius:var(--radius-sm);padding:4px 8px;font-size:12px;background:var(--ide-input);color:var(--ide-text);outline:none}
.op-btn.danger{color:var(--danger)}
/* 表格 */
.rp-table-wrap{flex:1;min-height:140px;position:relative;overflow:hidden}
.rp-loading{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--ide-text-3);font-size:12.5px;z-index:2;background:var(--ide-card)}
.rp-empty{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;color:var(--ide-text-3);font-size:12.5px;pointer-events:none}
.rp-empty.big{position:static;flex:1}
/* 分页条 */
.rp-pager{display:flex;align-items:center;gap:10px;padding:6px 10px;border-top:1px solid var(--ide-border);flex-wrap:wrap;font-size:12px;color:var(--ide-text-2)}
/* 错误 / DML */
.rp-error,.rp-exec{padding:16px;display:flex;flex-direction:column;gap:10px;overflow:auto}
.rp-error-title{font-weight:700;color:var(--danger);font-size:13px}
.rp-error-msg{margin:0;background:var(--danger-bg);color:var(--danger);padding:10px;border-radius:var(--radius-sm);white-space:pre-wrap;font-size:12px;max-height:180px;overflow:auto}
.rp-sql{background:var(--ide-bg);border:1px solid var(--ide-border);border-radius:var(--radius-sm);padding:8px 10px;font-size:12px;white-space:pre-wrap;word-break:break-all;max-height:140px;overflow:auto;color:var(--ide-text-2)}
.exec-card{align-self:flex-start;text-align:center;border:1px solid var(--ide-border);border-radius:var(--radius-sm);padding:14px 28px;background:var(--ide-bg)}
.exec-num{font-size:30px;font-weight:700;color:var(--warn)}
.exec-label{font-size:11.5px;color:var(--ide-text-3);margin-top:4px}
/* 日志 */
.rp-logs{border-top:1px solid var(--ide-border);flex-shrink:0;display:flex;flex-direction:column}
.rp-log-toggle{text-align:left;border-radius:0;padding:5px 10px;font-size:12px}
.log-box{height:150px;overflow:auto;padding:2px 10px 8px;background:var(--ide-bg)}
.rp-logs.collapsed .log-box{display:none}
.log-line{display:flex;gap:6px;font-size:11.5px;line-height:1.7}
.log-t{color:var(--ide-text-3);flex-shrink:0}
.log-i{width:14px;text-align:center;flex-shrink:0}
.log-x{word-break:break-all;white-space:pre-wrap}
.k-start .log-i,.k-start .log-x{color:var(--primary)}
.k-end .log-i,.k-end .log-x{color:var(--success)}
.k-error .log-i,.k-error .log-x{color:var(--danger)}
.k-vars .log-i,.k-vars .log-x{color:var(--purple)}
.k-txn .log-i,.k-txn .log-x{color:var(--warn)}
.k-info .log-i,.k-info .log-x{color:var(--ide-text-3)}
.log-empty{padding:16px;text-align:center;color:var(--ide-text-3);font-size:12px}
/* 导出弹窗 */
.exp-body{display:flex;flex-direction:column;gap:12px;font-size:12.5px}
.exp-sec{display:flex;flex-direction:column;gap:6px}
.exp-k{font-weight:600;color:var(--ide-text-2)}
.exp-tip{font-size:11.5px;color:var(--ide-text-3);background:var(--ide-bg);border-radius:var(--radius-sm);padding:8px}
</style>
