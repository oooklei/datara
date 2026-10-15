<!--
  R5-A：SQL IDE 只读能力验证页（RED/原型态）。
  权威范围：plan I5（docs/superpowers/plans/2026-10-14-datara-platform-rebuild.md）
  + docs/increments/R5-IDE-开始前影响分析.md §3/§6。
  边界：独立验证页，不改造正式 /ide SPA；契约全部经 services/rebuild/sqlIdeApi（A5 接入前抛
  R5A_BACKEND_NOT_WIRED，UI 统一横幅提示）；不触发 R5 GREEN（真实控件验收待 A5 后端 + 人工闸）。
-->
<template>
  <div class="r5a-page">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      data-testid="r5a-red-banner"
      title="R5-A RED 骨架（原型态）— rebuild/sql_ide（A5）后端契约未接入，所有 I/O 返回 R5A_BACKEND_NOT_WIRED"
    />

    <el-descriptions :column="4" size="small" border class="r5a-context">
      <el-descriptions-item label="数据源">{{ datasourceName }}</el-descriptions-item>
      <el-descriptions-item label="数据库">{{ databaseName || '—' }}</el-descriptions-item>
      <el-descriptions-item label="跨 Schema">{{ crossSchema ? '支持' : '不支持' }}</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（全部未接线）</el-descriptions-item>
    </el-descriptions>

    <splitpanes class="r5a-body">
      <pane size="24" min-size="16">
        <div class="r5a-panel">
          <div class="r5a-panel-head">
            <span>元数据（9 类对象）</span>
            <el-input v-model="keyword" size="small" placeholder="检索对象" clearable @change="onSearch" />
          </div>
          <div class="r5a-panel-body">
            <MetaTree @contract-error="onContractError" />
          </div>
        </div>
      </pane>
      <pane size="76">
        <splitpanes horizontal>
          <pane size="42" min-size="20">
            <div class="r5a-panel">
              <div class="r5a-panel-head">
                <span>SQL（只读执行）</span>
                <span class="r5a-actions">
                  <el-button size="small" @click="onLint">预检</el-button>
                  <el-button size="small" type="primary" :disabled="running" @click="onExecute">执行</el-button>
                  <el-button size="small" :disabled="!running" @click="onCancel">取消</el-button>
                  <el-button size="small" text @click="historyVisible = true">历史</el-button>
                </span>
              </div>
              <div class="r5a-panel-body">
                <SqlEditor v-model="sqlText" />
              </div>
            </div>
          </pane>
          <pane min-size="20">
            <div class="r5a-panel">
              <div class="r5a-panel-head">
                <span>结果</span>
                <span class="r5a-status">{{ statusText }}</span>
              </div>
              <div class="r5a-panel-body">
                <ResultGrid
                  :columns="result.columns"
                  :rows="result.rows"
                  :rows-total="result.rowsTotal"
                  :page="page"
                  :page-size="pageSize"
                  truncated
                  @page-change="onPageChange"
                />
              </div>
            </div>
          </pane>
        </splitpanes>
      </pane>
    </splitpanes>

    <HistoryDrawer v-model:visible="historyVisible" :entries="history" />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import {
  R5A_CONTRACT_METHODS,
  createSqlIdeContract,
  type HistoryEntry,
  type SqlResultEvent,
} from '../../../../services/rebuild/sqlIdeApi'
import MetaTree from './components/MetaTree.vue'
import SqlEditor from './components/SqlEditor.vue'
import ResultGrid from './components/ResultGrid.vue'
import HistoryDrawer from './components/HistoryDrawer.vue'

defineOptions({ name: 'SqlIdeReadonlyView' })

const contract = createSqlIdeContract()
const contractMethodCount = R5A_CONTRACT_METHODS.length

/* 上下文（A5 就绪前为占位值；数据源选择接 rebuild governance catalog） */
const datasourceName = ref('（未接入）')
const databaseName = ref('')
const crossSchema = ref(false)
const keyword = ref('')

/* 编辑与执行状态 */
const sqlText = ref('SELECT 1;')
const running = ref(false)
const taskId = ref('')
const statusText = ref('待执行')
const historyVisible = ref(false)
const history = ref<HistoryEntry[]>([])
const page = ref(1)
const pageSize = ref(50)
const result = reactive<SqlResultEvent>({ stmtIndex: 0, columns: [], rows: [], rowsTotal: 0, elapsedMs: 0 })

/** NOT_WIRED 统一落横幅语义：状态栏提示 + 不中断交互 */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value = err instanceof Error && err.message.startsWith('R5A_BACKEND_NOT_WIRED') ? 'A5 契约未接入' : `${label} 失败`
      throw err
    })
}

const onExecute = () => guard(() => contract.executeSql({ datasourceId: 0, db: null, sql: sqlText.value, mode: 'auto' }), '执行')
const onCancel = () => guard(() => contract.cancelExecution(taskId.value), '取消')
const onLint = () => guard(() => contract.lintSql(0, sqlText.value), '预检')
const onSearch = () => guard(() => contract.searchObjects(0, keyword.value), '检索')
const onPageChange = (p: number, s: number) => {
  page.value = p
  pageSize.value = s
}
</script>

<style scoped>
.r5a-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  box-sizing: border-box;
}
.r5a-context {
  flex: none;
}
.r5a-body {
  flex: 1;
  min-height: 0;
}
.r5a-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  overflow: hidden;
}
.r5a-panel-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  font-size: 13px;
}
.r5a-actions {
  display: inline-flex;
  gap: 4px;
}
.r5a-status {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}
.r5a-panel-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px;
}
.splitpanes__pane {
  transition: none;
}
</style>
