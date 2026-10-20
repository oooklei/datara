<script setup lang="ts">
/**
 * IdeView（FE-07a 换绑）：可视化数据开发 IDE 完整版布局根。
 * - 顶部：左侧资源树收缩开关 + InstanceBar（实例/属性卡/env/模式/全局参数/历史/主题/快捷键）
 * - splitpanes 左右分割（左=MetaTree 可收缩，右=上下分割 SqlEditorR5A / ResultGrid）
 * - 契约层：createSqlIdeContract（R5-A GREEN），支持服务端分页 + SSE 事件流
 * - HistoryDrawerR5A / GlobalParamDrawer / 快捷键帮助弹窗
 * - 主题：ideStore.theme 驱动 .ide-dark / .ide-light 局部 CSS 变量
 */
import { computed, onMounted, ref } from 'vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import { ElMessage } from 'element-plus'
import { useIdeStore } from '../../stores/ideStore'
import {
  createSqlIdeContract,
  type HistoryEntry,
  type SqlDiagnostic,
  type SqlResultEvent,
  type SqlDoneEvent,
} from '../../services/rebuild/sqlIdeApi'
import InstanceBar from './components/InstanceBar.vue'
import MetaTree from './components/MetaTree.vue'
import SqlEditorR5A from './components/SqlEditorR5A.vue'
import ResultGrid from './components/ResultGrid.vue'
import GlobalParamDrawer from './components/GlobalParamDrawer.vue'
import HistoryDrawerR5A from './components/HistoryDrawerR5A.vue'

const store = useIdeStore()

const leftCollapsed = ref(false)
const paramsVisible = ref(false)
const historyVisible = ref(false)
const shortcutsVisible = ref(false)

/* FE-07a 契约层：createSqlIdeContract（R5-A GREEN）
 * 异步执行流：executeSql → taskId → openEventStream(taskId) → SSE 事件
 *  → SqlResultEvent（列/行）→ SqlDoneEvent（historyId）→ fetchResultPage 分页 */
const contract = createSqlIdeContract()
const sqlText = ref('')
const resultColumns = ref<string[]>([])
const resultRows = ref<unknown[][]>([])
const resultTotal = ref(0)
const resultPage = ref(1)
const resultPageSize = ref(50)
const resultTruncated = ref(false)
const executing = ref(false)
const contractError = ref('')
const diagnostics = ref<SqlDiagnostic[]>([])
const historyEntries = ref<HistoryEntry[]>([])
const lastHistoryId = ref<number | null>(null)
const lastResultSetId = ref('')
const datasourceId = computed(() => store.activeDsId ?? 1)

/* 缺陷3 修复：IDE 挂载即预加载全局参数与执行历史 */
onMounted(async () => {
  await store.loadGlobalParams()
  await loadHistory()
})

async function loadHistory(): Promise<void> {
  if (datasourceId.value === null) return
  try {
    historyEntries.value = await contract.listHistory(datasourceId.value)
  } catch {
    /* 历史加载失败静默（非关键路径） */
  }
}

function toggleLeft(): void {
  leftCollapsed.value = !leftCollapsed.value
}

async function executeSql(): Promise<void> {
  const dsId = datasourceId.value
  if (dsId === null) {
    ElMessage.warning('请先选择数据源实例')
    return
  }
  const sql = sqlText.value.trim()
  if (!sql) {
    ElMessage.warning('请先输入 SQL')
    return
  }
  executing.value = true
  contractError.value = ''
  diagnostics.value = []
  resultColumns.value = []
  resultRows.value = []
  resultTotal.value = 0
  resultTruncated.value = false
  lastHistoryId.value = null
  lastResultSetId.value = ''
  try {
    const { taskId } = await contract.executeSql({
      datasourceId: dsId,
      sql,
      mode: 'auto',
      sessionId: `ide-${Date.now()}`,
      clientRequestId: `req-${Date.now()}`,
    })
    const es = contract.openEventStream(taskId)
    es.addEventListener('result', (ev: MessageEvent) => {
      const data = JSON.parse(ev.data) as SqlResultEvent
      resultColumns.value = data.columns
      resultRows.value = data.rows
      resultTotal.value = data.rowsTotal
      resultTruncated.value = data.rows.length < data.rowsTotal
      lastResultSetId.value = data.resultSetId
    })
    es.addEventListener('done', (ev: MessageEvent) => {
      es.close()
      executing.value = false
      const data = JSON.parse(ev.data) as SqlDoneEvent
      if (data.status === 'succeeded') {
        resultTruncated.value = resultRows.value.length < resultTotal.value
        if (data.historyId) {
          lastHistoryId.value = data.historyId
          void loadHistory()
        }
      } else {
        contractError.value = `执行${data.status === 'failed' ? '失败' : '已取消'}（elapsedMs=${data.elapsedMs}）`
      }
    })
    es.addEventListener('error', () => {
      es.close()
      executing.value = false
      contractError.value = 'SSE 事件流异常断开'
    })
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err)
    contractError.value = message
    diagnostics.value = [{
      code: 'CONTRACT_ERROR',
      message,
      severity: 'error',
      line: 0,
      col: 0,
      stmtIndex: 0,
    }]
    executing.value = false
  }
}

async function onPageChange(page: number, pageSize: number): Promise<void> {
  resultPage.value = page
  resultPageSize.value = pageSize
  if (!lastHistoryId.value || !lastResultSetId.value) return
  try {
    const result = await contract.fetchResultPage(
      lastHistoryId.value,
      lastResultSetId.value,
      (page - 1) * pageSize,
      pageSize,
    )
    resultColumns.value = result.columns
    resultRows.value = result.rows
    resultTotal.value = result.rowsTotal
    resultTruncated.value = result.rows.length < result.rowsTotal
  } catch (err) {
    contractError.value = err instanceof Error ? err.message : String(err)
  }
}

function onSelectHistory(entry: HistoryEntry): void {
  sqlText.value = entry.sqlText
  historyVisible.value = false
}

const SHORTCUTS = [
  { keys: 'Ctrl + Enter', desc: '运行 SQL（选中片段则仅执行片段）' },
  { keys: 'Ctrl + S', desc: '保存脚本（未命名则提示命名）' },
  { keys: 'Ctrl + Shift + F', desc: '格式化 SQL' },
  { keys: '——', desc: '悬浮表/视图可展开操作菜单（仅生成 SQL，不自动执行）' },
  { keys: '——', desc: '点击结果 Tab 回显原始 SQL；单元格点击复制值' },
]
</script>

<template>
  <div class="ide-root" :class="store.theme === 'datara-light' ? 'ide-light' : 'ide-dark'">
    <!-- 顶部操作条（按钮置顶） -->
    <div class="ide-topline">
      <button
        class="op-btn"
        :title="leftCollapsed ? '展开资源树' : '收起资源树'"
        @click="toggleLeft"
      >{{ leftCollapsed ? '⇥ 资源树' : '⇤ 收起' }}</button>
      <InstanceBar
        @open-params="paramsVisible = true"
        @open-history="historyVisible = true"
        @show-shortcuts="shortcutsVisible = true"
      />
    </div>

    <!-- 主区：左右分割 -->
    <splitpanes class="ide-split ide-main" :push-other-panes="false">
      <pane v-if="!leftCollapsed" :size="24" min-size="10" max-size="45">
        <MetaTree
          :datasource-id="datasourceId"
          @contract-error="(msg: string) => { contractError = msg; ElMessage.error(msg) }"
        />
      </pane>
      <pane>
        <!-- 右区：上下分割 -->
        <splitpanes class="ide-split ide-right" horizontal>
          <pane :size="56" min-size="20">
            <SqlEditorR5A v-model="sqlText" :diagnostics="diagnostics" />
          </pane>
          <pane :size="44" min-size="20">
            <ResultGrid
              :columns="resultColumns"
              :rows="resultRows"
              :rows-total="resultTotal"
              :page="resultPage"
              :page-size="resultPageSize"
              :truncated="resultTruncated"
              @page-change="onPageChange"
            />
          </pane>
        </splitpanes>
      </pane>
    </splitpanes>

    <GlobalParamDrawer v-model="paramsVisible" />
    <HistoryDrawerR5A
      v-model:visible="historyVisible"
      :entries="historyEntries"
      @select="onSelectHistory"
    />

    <!-- 快捷键帮助 -->
    <el-dialog v-model="shortcutsVisible" title="快捷键与操作提示" width="460px" append-to-body>
      <div class="sc-list">
        <div v-for="s in SHORTCUTS" :key="s.keys + s.desc" class="sc-row">
          <kbd v-if="s.keys !== '——'" class="mono">{{ s.keys }}</kbd>
          <span class="sc-desc">{{ s.desc }}</span>
        </div>
      </div>
    </el-dialog>

    <!-- 执行按钮（右下角悬浮） -->
    <button
      class="ide-exec-btn"
      :disabled="executing"
      @click="executeSql"
    >{{ executing ? '执行中…' : '▶ 执行 SQL' }}</button>

    <!-- 契约错误提示 -->
    <el-alert
      v-if="contractError"
      type="error"
      :closable="true"
      show-icon
      class="ide-error-bar"
      :title="contractError"
      @close="contractError = ''"
    />
  </div>
</template>

<style scoped>
/* ===== IDE 局部主题变量（深色默认，延续原 IDE 视觉；不影响 IDE 之外页面） ===== */
.ide-root{
  /* 深色（默认） */
  --ide-card:#12161d;
  --ide-bg:#0e1116;
  --ide-border:#242b37;
  --ide-border-strong:#333d4e;
  --ide-text:#e6ebf4;
  --ide-text-2:#b8c2d4;
  --ide-text-3:#7e889d;
  --ide-hover:#1b2330;
  --ide-input:#0e1116;
  --ide-warn:#e8a33d;
  --ide-warn-bg:rgba(232,163,61,.12);

  height:100%;
  min-height:520px;
  display:flex;
  flex-direction:column;
  background:var(--ide-bg);
  color:var(--ide-text);
  overflow:hidden;
}
.ide-root.ide-light{
  --ide-card:#ffffff;
  --ide-bg:#f5f7fa;
  --ide-border:#e7eaf0;
  --ide-border-strong:#d3d9e3;
  --ide-text:#1f2430;
  --ide-text-2:#5b6478;
  --ide-text-3:#8c94a6;
  --ide-hover:#f0f3f8;
  --ide-input:#ffffff;
  --ide-warn:#d97706;
  --ide-warn-bg:#fdf3e0;
}

.ide-topline{display:flex;align-items:flex-start;flex-shrink:0}
.ide-topline > .op-btn{margin:8px 0 0 10px;flex-shrink:0}
.ide-topline > :last-child{flex:1;min-width:0}

.ide-main{flex:1;min-height:0}

/* 分割条（窄条 + 悬停高亮） */
.ide-split > .splitpanes__splitter{background:var(--ide-border);position:relative;z-index:5}
.ide-split.splitpanes--vertical > .splitpanes__splitter{width:5px}
.ide-split.splitpanes--horizontal > .splitpanes__splitter{height:5px}
.ide-split > .splitpanes__splitter:hover,
.ide-split > .splitpanes__splitter.is-dragging{background:var(--primary)}

/* 快捷键弹窗 */
.sc-list{display:flex;flex-direction:column;gap:9px;font-size:12.5px}
.sc-row{display:flex;align-items:center;gap:10px}
.sc-row kbd{border:1px solid var(--ide-border-strong);background:var(--ide-bg);border-radius:4px;padding:2px 8px;font-size:11.5px;color:var(--ide-text);min-width:110px;text-align:center}
.sc-desc{color:var(--ide-text-2)}

/* 执行按钮 */
.ide-exec-btn{
  position:fixed;
  right:32px;
  bottom:48px;
  z-index:2000;
  border:none;
  background:var(--el-color-primary);
  color:#fff;
  border-radius:24px;
  padding:10px 20px;
  font-size:13px;
  font-weight:600;
  cursor:pointer;
  box-shadow:var(--el-box-shadow-light);
  transition:opacity .15s;
}
.ide-exec-btn:disabled{opacity:.6;cursor:not-allowed}
.ide-exec-btn:not(:disabled):hover{background:var(--el-color-primary-light-3)}

/* 契约错误条 */
.ide-error-bar{
  position:fixed;
  left:50%;
  transform:translateX(-50%);
  bottom:100px;
  z-index:2001;
  width:80%;
  max-width:600px;
}
</style>
