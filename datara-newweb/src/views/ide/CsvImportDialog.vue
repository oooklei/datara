<template>
  <div v-if="open" class="ide-dialog-mask" data-csv-dialog @click.self="close">
    <section class="ide-dialog ide-dialog-csv" role="dialog" aria-label="导入数据（CSV）">
      <header class="ide-dialog-head">
        <h3>导入数据（CSV）· {{ schema }}.{{ table }}</h3>
        <button type="button" data-dialog-close @click="close">×</button>
      </header>

      <p v-if="error" class="ide-err" data-dialog-error role="alert">{{ error }}</p>
      <p v-if="notice" class="ide-diag" data-dialog-notice role="status">{{ notice }}</p>

      <div class="ide-dialog-body">
        <label class="ide-csv-file">CSV 文件
          <input type="file" accept=".csv,text/csv" data-csv-file @change="onFileChange" />
        </label>
        <label class="ide-csv-option">
          <input type="checkbox" v-model="hasHeader" data-csv-header @change="reparse" /> 首行为表头
        </label>

        <p v-if="parseError" class="ide-err" data-csv-parse-error>{{ parseError }}</p>
        <p v-if="parsed" data-csv-stats class="ide-muted">
          共解析 {{ dataRows.length }} 行 × {{ csvColumnCount }} 列
          <span v-if="dataRows.length > MAX_IMPORT_ROWS" class="ide-err">（超过 {{ MAX_IMPORT_ROWS }} 行上限，无法导入）</span>
        </p>

        <section v-if="previewRows.length" class="ide-csv-preview">
          <h4>前 {{ previewRows.length }} 行预览</h4>
          <table class="ide-data-table" data-csv-preview-table>
            <thead>
              <tr><th v-for="(h, i) in previewHeader" :key="i">{{ h }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(row, r) in previewRows" :key="r">
                <td v-for="(cell, c) in row" :key="c">{{ cell }}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section v-if="tableColumns.length" class="ide-csv-mapping">
          <h4>列映射（表字段 → CSV 列，选「跳过」则不导入该字段）</h4>
          <p v-if="dataRows.length && mappedColumnCount === 0" class="ide-warn" data-mapping-missing>至少映射一个字段才能导入</p>
          <table class="ide-data-table" data-csv-mapping-table>
            <thead>
              <tr><th>表字段</th><th>CSV 列</th></tr>
            </thead>
            <tbody>
              <tr v-for="col in tableColumns" :key="col">
                <td><code>{{ col }}</code></td>
                <td>
                  <select v-model.number="mapping[col]" :data-mapping="col">
                    <option :value="-1">跳过</option>
                    <option v-for="(_, i) in csvColumnCount" :key="i" :value="i">
                      {{ previewHeader[i] ?? `列 ${i + 1}` }}
                    </option>
                  </select>
                </td>
              </tr>
            </tbody>
          </table>
        </section>
        <p v-else-if="parsed" class="ide-muted">表字段加载中…</p>
      </div>

      <footer class="ide-dialog-foot">
        <span v-if="parsed" class="ide-muted">将导入 {{ mappedColumnCount }} 字段 × {{ importableRows }} 行（事务提交）</span>
        <button type="button" data-csv-import :disabled="!canImport || importing" @click="runImport">
          {{ importing ? '导入中…' : '开始导入' }}
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * CSV 导入弹窗（对标审计-03 §6.5 / G24）。
 *
 * 旧版走 multipart；B4-d 契约统一 JSON body——前端 FileReader 解析 CSV
 * （引号转义感知）→ 列映射 → 整批 JSON 提交 importCsv（后端 10 万行硬上限、
 * 单事务、失败整体回滚）。>10 万行前端直接拦截不发请求。
 */
import { computed, ref, watch } from 'vue'
import type { SqlIdeContract } from '../../services/rebuild/sqlIdeApi'
import { parseCsv } from './csvParse'

const MAX_IMPORT_ROWS = 100_000

const props = defineProps<{
  open: boolean
  api: SqlIdeContract
  datasourceId: number | null
  schema: string
  table: string
}>()

const emit = defineEmits<{ (e: 'update:open', value: boolean): void; (e: 'imported', summary: string): void }>()

const hasHeader = ref(true)
const dataRows = ref<string[][]>([])
const headerRow = ref<string[]>([])
const parsed = ref(false)
const parseError = ref('')
const error = ref('')
const notice = ref('')
const tableColumns = ref<string[]>([])
const mapping = ref<Record<string, number>>({})
const importing = ref(false)
let rawText = ''

const csvColumnCount = computed(() => dataRows.value[0]?.length ?? headerRow.value.length ?? 0)
const previewHeader = computed(() => (hasHeader.value && headerRow.value.length ? headerRow.value : dataRows.value[0]?.map((_, i) => `列 ${i + 1}`) ?? []))
const previewRows = computed(() => (hasHeader.value ? dataRows.value : dataRows.value).slice(0, 3))
const mappedColumnCount = computed(() => Object.values(mapping.value).filter((i) => i >= 0).length)
const importableRows = computed(() => Math.min(dataRows.value.length, MAX_IMPORT_ROWS))
const overLimit = computed(() => dataRows.value.length > MAX_IMPORT_ROWS)
const canImport = computed(() => parsed.value && !overLimit.value && mappedColumnCount.value > 0 && importableRows.value > 0)

watch(() => props.open, (open) => {
  if (open) {
    resetState()
    void loadTableColumns()
  }
})

function resetState(): void {
  dataRows.value = []
  headerRow.value = []
  parsed.value = false
  parseError.value = ''
  error.value = ''
  notice.value = ''
  mapping.value = {}
  rawText = ''
}

async function loadTableColumns(): Promise<void> {
  tableColumns.value = []
  if (props.datasourceId === null) return
  try {
    const page = await props.api.listColumns(props.datasourceId, props.schema, props.table, null)
    tableColumns.value = page.items.map((c) => c.name)
    const next: Record<string, number> = {}
    for (const col of tableColumns.value) next[col] = -1
    mapping.value = next
  } catch (e) {
    error.value = e instanceof Error ? e.message : String(e)
  }
}

function onFileChange(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    rawText = String(reader.result ?? '')
    reparse()
  }
  reader.onerror = () => {
    parseError.value = '文件读取失败'
  }
  reader.readAsText(file, 'utf-8')
}

function reparse(): void {
  parseError.value = ''
  parsed.value = false
  dataRows.value = []
  headerRow.value = []
  if (!rawText) return
  try {
    const all = parseCsv(rawText)
    if (hasHeader.value) {
      headerRow.value = all[0] ?? []
      dataRows.value = all.slice(1)
    } else {
      dataRows.value = all
    }
    parsed.value = true
    if (dataRows.value.length > MAX_IMPORT_ROWS) {
      notice.value = `已解析 ${dataRows.value.length} 行，超过 ${MAX_IMPORT_ROWS} 行上限，请拆分文件`
    }
  } catch (e) {
    parseError.value = e instanceof Error ? e.message : String(e)
  }
}

async function runImport(): Promise<void> {
  if (props.datasourceId === null || !canImport.value) return
  error.value = ''
  const columns = tableColumns.value.filter((c) => (mapping.value[c] ?? -1) >= 0)
  const indexes = columns.map((c) => mapping.value[c])
  const rows = dataRows.value
    .slice(0, MAX_IMPORT_ROWS)
    .map((row) => indexes.map((idx) => row[idx] ?? ''))
  importing.value = true
  try {
    const result = await props.api.importCsv({
      datasourceId: props.datasourceId,
      schema: props.schema,
      table: props.table,
      columns,
      rows,
    })
    emit('imported', `导入成功：${result.imported} 行 × ${columns.length} 列（事务提交）`)
    close()
  } catch (e) {
    error.value = `导入失败，已整体回滚：${e instanceof Error ? e.message : String(e)}`
  } finally {
    importing.value = false
  }
}

function close(): void {
  emit('update:open', false)
}
</script>

<style scoped>
.ide-dialog-mask{position:fixed;inset:0;background:rgba(0,0,0,.45);z-index:60;display:flex;align-items:flex-start;justify-content:center}
.ide-dialog-csv{background:var(--card);color:var(--text);border:1px solid var(--border);border-radius:var(--radius);margin-top:6vh;width:720px;max-width:94vw;display:flex;flex-direction:column;max-height:86vh}
.ide-dialog-head{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--border)}
.ide-dialog-head h3{margin:0;font-size:15px}
.ide-dialog-head button{border:none;background:transparent;color:var(--text-2);font-size:18px;cursor:pointer}
.ide-dialog-body{padding:12px 16px;overflow:auto;flex:1;display:flex;flex-direction:column;gap:10px}
.ide-dialog-foot{display:flex;align-items:center;gap:10px;padding:12px 16px;border-top:1px solid var(--border)}
.ide-dialog-foot button{margin-left:auto}
.ide-csv-file{display:flex;align-items:center;gap:8px;font-size:13px}
.ide-csv-option{font-size:13px;display:flex;align-items:center;gap:6px}
.ide-csv-preview h4,.ide-csv-mapping h4{margin:0 0 6px;font-size:13px}
.ide-data-table{border-collapse:collapse;width:100%;font-size:12px}
.ide-data-table th,.ide-data-table td{border:1px solid var(--border);padding:4px 6px;text-align:left;white-space:nowrap;max-width:220px;overflow:hidden;text-overflow:ellipsis}
.ide-data-table th{background:var(--card-2,var(--card))}
.ide-warn{color:var(--warn);font-size:12px;margin:0}
.ide-err{color:var(--danger);font-size:12px;margin:0}
.ide-diag{color:var(--text-2);font-size:12px;margin:0}
.ide-muted{color:var(--text-2);font-size:12px;margin:0}
</style>
