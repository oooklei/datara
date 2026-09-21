<script setup lang="ts">
/**
 * HistoryDrawer（I10 G5）：执行历史抽屉。
 * - 分页列表（GET /ide/history，PageQuery: page_no/page_size，keyword/datasourceId 过滤）
 * - 行级四操作：查看（详情 logText 展开）/ 编辑（加载至编辑器新 Tab）/ 再执行 / 删除（二次确认）
 * - watch store.historyDirtyN：每次执行 done 后增量刷新当前页
 */
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useIdeStore } from '../../../stores/ideStore'
import {
  listIdeHistory, getIdeHistoryDetail, deleteIdeHistory,
  type IdeHistoryRow, type IdeHistoryDetail,
} from '../../../services/ideApi'

const store = useIdeStore()

const visible = defineModel<boolean>({ default: false })

const rows = ref<IdeHistoryRow[]>([])
const total = ref(0)
const page = ref(1)
const PAGE_SIZE = 20
const keyword = ref('')
const dsFilter = ref<number | ''>('')
const loading = ref(false)

async function load(): Promise<void> {
  loading.value = true
  try {
    const resp = await listIdeHistory({
      datasourceId: dsFilter.value === '' ? undefined : dsFilter.value,
      keyword: keyword.value.trim() || undefined,
      pageNo: page.value,
      pageSize: PAGE_SIZE,
    })
    rows.value = resp.list
    total.value = resp.total
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '执行历史加载失败')
  } finally {
    loading.value = false
  }
}

function doSearch(): void {
  page.value = 1
  void load()
}

const maxPage = () => Math.max(1, Math.ceil(total.value / PAGE_SIZE))

function goPage(p: number): void {
  page.value = Math.min(Math.max(1, p), maxPage())
  void load()
}

watch(visible, (v) => {
  if (v) void load()
})

/** 执行 done 后增量刷新（抽屉开着才刷） */
watch(() => store.historyDirtyN, () => {
  if (visible.value && page.value === 1) void load()
})

function statusClass(s: string): string {
  return s === 'success' ? 'ok' : s === 'canceled' ? 'cancel' : 'fail'
}

function fmtElapsed(ms: number): string {
  return ms >= 1000 ? `${(ms / 1000).toFixed(2)}s` : `${ms}ms`
}

/* ---- 查看：详情 logText 展开 ---- */

const detail = ref<IdeHistoryDetail | null>(null)
const detailLoading = ref(false)

async function viewDetail(row: IdeHistoryRow): Promise<void> {
  detailLoading.value = true
  detail.value = null
  try {
    detail.value = await getIdeHistoryDetail(row.id)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '历史详情加载失败')
  } finally {
    detailLoading.value = false
  }
}

function closeDetail(): void {
  detail.value = null
}

/* ---- 编辑：加载至编辑器新 Tab（先切实例再建 Tab） ---- */

async function loadToEditor(row: IdeHistoryRow): Promise<void> {
  if (row.datasourceId && store.activeDsId !== row.datasourceId) {
    const known = store.dsList.some((d) => d.id === row.datasourceId)
    if (!known) {
      ElMessage.warning('该历史所属实例当前不在线或不可用')
      return
    }
    await store.selectDs(row.datasourceId)
  }
  try {
    store.newUnnamedScript(row.sqlText)
    visible.value = false
    ElMessage.success('SQL 已载入新脚本 Tab')
  } catch { /* 未命名上限拦截已在 store 提示 */ }
}

/* ---- 再执行 ---- */

async function rerun(row: IdeHistoryRow): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `将按当前模式/env 再次执行该历史 SQL（${row.sqlText.slice(0, 80)}…）。确认执行？`,
      '再执行',
      { type: 'warning', confirmButtonText: '执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  if (row.datasourceId && store.activeDsId !== row.datasourceId) {
    const known = store.dsList.some((d) => d.id === row.datasourceId)
    if (!known) {
      ElMessage.warning('该历史所属实例当前不在线或不可用')
      return
    }
    await store.selectDs(row.datasourceId)
  }
  try {
    await store.runSql(row.sqlText)
    visible.value = false
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '执行提交失败')
  }
}

/* ---- 删除 ---- */

async function removeRow(row: IdeHistoryRow): Promise<void> {
  try {
    await ElMessageBox.confirm(`确认删除执行历史 #${row.id}？删除后不可恢复（不影响已导出文件）。`, '删除历史', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteIdeHistory(row.id)
    ElMessage.success('历史已删除')
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    await load()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '删除失败')
  }
}
</script>

<template>
  <el-drawer v-model="visible" title="执行历史" size="720px" append-to-body>
    <div class="hd-body">
      <!-- 过滤条（区域顶部） -->
      <div class="hd-filter">
        <select v-model="dsFilter" class="sel" @change="doSearch">
          <option value="">全部实例</option>
          <option v-for="d in store.dsList" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
        <input
          v-model="keyword"
          class="kw"
          placeholder="搜索 SQL 关键字，回车检索"
          @keyup.enter="doSearch"
        />
        <button class="op-btn" @click="doSearch">检索</button>
        <span class="spacer" />
        <button class="op-btn" title="刷新" @click="load">↻</button>
      </div>

      <!-- 列表 -->
      <div v-if="loading" class="hd-empty">加载中…</div>
      <div v-else-if="rows.length === 0" class="hd-empty">暂无执行历史</div>
      <div v-else class="hd-list">
        <div v-for="r in rows" :key="r.id" class="hd-row" @click="viewDetail(r)">
          <div class="hd-line">
            <span class="mono hd-id">#{{ r.id }}</span>
            <span class="hd-status" :class="statusClass(r.status)">{{ r.status }}</span>
            <span class="hd-meta mono">{{ r.dbName ?? '-' }}</span>
            <span class="hd-meta mono">{{ r.rowsTotal }} 行 · {{ r.affectedTotal }} 改 · {{ fmtElapsed(r.elapsedMs) }}</span>
            <span v-if="r.exported" class="hd-exp">已导出</span>
            <span class="hd-time">{{ r.createTime }}</span>
          </div>
          <div class="hd-sql mono">{{ r.sqlText }}</div>
          <div class="hd-acts" @click.stop>
            <button class="op-btn" @click="viewDetail(r)">查看</button>
            <button class="op-btn" @click="loadToEditor(r)">编辑</button>
            <button class="op-btn" @click="rerun(r)">再执行</button>
            <button class="op-btn danger" @click="removeRow(r)">删除</button>
          </div>
        </div>
      </div>

      <!-- 分页 -->
      <div class="hd-pager">
        <button class="op-btn" :disabled="page <= 1 || loading" @click="goPage(page - 1)">← 上一页</button>
        <span class="mono">第 {{ page }} / {{ maxPage() }} 页 · 共 {{ total }} 条</span>
        <button class="op-btn" :disabled="page >= maxPage() || loading" @click="goPage(page + 1)">下一页 →</button>
      </div>

      <!-- 详情（就地展开） -->
      <div v-if="detail || detailLoading" class="hd-detail">
        <div class="hd-dt-head">
          <b>历史 #{{ detail?.id ?? '…' }} 详情</b>
          <span class="spacer" />
          <button class="op-btn" @click="closeDetail">收起</button>
        </div>
        <div v-if="detailLoading" class="hd-empty">加载中…</div>
        <template v-else-if="detail">
          <div class="hd-dt-meta mono">
            实例 {{ detail.datasourceId }} · 库 {{ detail.dbName ?? '-' }} · 状态 {{ detail.status }} ·
            {{ detail.rowsTotal }} 行 / {{ detail.affectedTotal }} 改 · {{ fmtElapsed(detail.elapsedMs) }}
          </div>
          <div class="hd-dt-sql mono">{{ detail.sqlText }}</div>
          <div v-if="detail.error" class="hd-dt-err mono">{{ detail.error }}</div>
          <div v-for="(e, i) in detail.logText" :key="i" class="hd-dt-item">
            <div class="hd-dt-line">
              <b>语句 {{ (e.stmtIndex ?? i) + 1 }}</b>
              <span class="hd-status" :class="statusClass(e.status ?? '')">{{ e.status ?? '-' }}</span>
              <span class="hd-meta mono">{{ e.kind === 'exec' ? `${e.affected ?? 0} 行受影响` : `${e.rowsTotal ?? 0} 行` }} · {{ fmtElapsed(e.elapsedMs ?? 0) }}</span>
            </div>
            <div v-if="e.error" class="hd-dt-err mono">✗ {{ e.error }}</div>
            <div v-if="e.warnings && e.warnings.length" class="hd-dt-warn mono">⚠ {{ e.warnings.join('；') }}</div>
            <div v-if="e.varSnapshot && e.varSnapshot.length" class="hd-dt-vars mono">
              变量：{{ e.varSnapshot.map((v) => `${v.name}=${v.value}(${v.source})`).join('；') }}
            </div>
            <div v-if="e.rendered" class="hd-dt-rendered mono" :title="e.rendered">渲染后：{{ e.rendered }}</div>
          </div>
          <div v-if="detail.logText.length === 0" class="hd-empty">无逐语句日志</div>
        </template>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.hd-body{display:flex;flex-direction:column;gap:10px;font-size:12.5px}
.hd-filter{display:flex;align-items:center;gap:6px}
.sel{border:1px solid var(--ide-border-strong);border-radius:var(--radius-sm);padding:5px 8px;font-size:12.5px;background:var(--ide-input);color:var(--ide-text)}
.kw{flex:1;min-width:0;border:1px solid var(--ide-border-strong);border-radius:var(--radius-sm);padding:5px 9px;font-size:12.5px;background:var(--ide-input);color:var(--ide-text);outline:none}
.kw:focus{border-color:var(--primary)}
.spacer{flex:1}
.op-btn.danger{color:var(--danger)}
.hd-empty{padding:24px;text-align:center;color:var(--ide-text-3)}
.hd-list{display:flex;flex-direction:column;gap:8px;overflow:auto;max-height:46vh}
.hd-row{border:1px solid var(--ide-border);border-radius:var(--radius-sm);padding:8px 10px;cursor:pointer}
.hd-row:hover{border-color:var(--primary)}
.hd-line{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.hd-id{color:var(--ide-text-3);font-size:11px}
.hd-status{font-size:10.5px;border-radius:3px;padding:0 6px;line-height:17px}
.hd-status.ok{background:var(--success-bg);color:var(--success)}
.hd-status.fail{background:var(--danger-bg);color:var(--danger)}
.hd-status.cancel{background:var(--warn-bg);color:var(--warn)}
.hd-meta{font-size:11px;color:var(--ide-text-3)}
.hd-exp{font-size:10px;color:var(--primary);border:1px solid var(--primary);border-radius:3px;padding:0 4px}
.hd-time{margin-left:auto;font-size:11px;color:var(--ide-text-3)}
.hd-sql{margin-top:5px;background:var(--ide-bg);border-radius:4px;padding:5px 8px;font-size:11px;color:var(--ide-text-2);white-space:pre-wrap;word-break:break-all;max-height:64px;overflow:hidden}
.hd-acts{display:flex;gap:5px;margin-top:6px}
.hd-pager{display:flex;align-items:center;justify-content:center;gap:12px;color:var(--ide-text-2)}
/* 详情 */
.hd-detail{border:1px solid var(--ide-border-strong);border-radius:var(--radius-sm);padding:10px;display:flex;flex-direction:column;gap:8px}
.hd-dt-head{display:flex;align-items:center;gap:8px}
.hd-dt-meta{font-size:11px;color:var(--ide-text-3)}
.hd-dt-sql{background:var(--ide-bg);border-radius:4px;padding:6px 8px;font-size:11px;white-space:pre-wrap;word-break:break-all;max-height:120px;overflow:auto}
.hd-dt-item{border-top:1px dashed var(--ide-border);padding-top:6px;display:flex;flex-direction:column;gap:4px}
.hd-dt-line{display:flex;align-items:center;gap:8px}
.hd-dt-err{color:var(--danger);font-size:11px;white-space:pre-wrap;word-break:break-all}
.hd-dt-warn{color:var(--warn);font-size:11px}
.hd-dt-vars{color:var(--purple);font-size:11px;word-break:break-all}
.hd-dt-rendered{color:var(--ide-text-3);font-size:11px;white-space:pre-wrap;word-break:break-all;max-height:90px;overflow:auto}
</style>
