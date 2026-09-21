<script setup lang="ts">
/**
 * ExplorerTree（I10 G7~G11 + G23/G24）：
 * - 懒加载树：实例→库→Tables/Views→表/视图→字段（el-tree lazy，展开才请求）
 * - 搜索：输入防抖 300ms；后端 search 端点 + 已加载节点本地匹配合并展示
 * - 字段 hover Tooltip（类型/长度/主键/非空/注释 + 复制按钮）
 * - 表/视图悬浮菜单 11 项：全部生成 SQL 填充编辑器、绝不自动执行（G10）
 * - Schema 单击写 ideStore.currentDb（G11）
 * - 编辑数据弹窗（G23）：分页加载 + 单元格编辑/追加行/删行 → rows/apply（失败整体回滚提示）
 * - CSV 导入弹窗（G24）：上传 + 首行预览 + 列映射；>10 万行前端拦截
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { debounce } from 'lodash-es'
import { useIdeStore } from '../../../stores/ideStore'
import {
  listDsDatabases, listDsTables, listDsColumns, searchDsTables,
  getTableDdl, auditTable, getTableRows, applyTableRows, importCsv,
  type DsColumnMeta, type DsSearchItem, type AuditCheck,
} from '../../../services/ideApi'

const store = useIdeStore()

/* ================= 懒加载树 ================= */

type NodeType = 'db' | 'folder-table' | 'folder-view' | 'table' | 'view' | 'column'

interface TreeNode {
  key: string
  name: string
  ntype: NodeType
  db: string
  tb: string
  leaf: boolean
  col?: DsColumnMeta
}

const treeKey = ref(0) // 重建树（切实例/刷新）

function colNode(db: string, tb: string, c: DsColumnMeta): TreeNode {
  return { key: `${db}::${tb}::c::${c.name}`, name: c.name, ntype: 'column', db, tb, leaf: true, col: c }
}

async function loadNode(node: { level: number; data: TreeNode | null }, resolve: (children: TreeNode[]) => void): Promise<void> {
  const dsId = store.activeDsId
  if (dsId === null) {
    resolve([])
    return
  }
  if (node.level === 0) {
    // 顶层=库列表（实例节点由 InstanceBar 承担）
    try {
      const dbs = await listDsDatabases(dsId)
      resolve(dbs.map((d) => ({ key: `db::${d}`, name: d, ntype: 'db', db: d, tb: '', leaf: false } as TreeNode)))
    } catch (err) {
      ElMessage.error(err instanceof Error ? err.message : '库列表加载失败')
      resolve([])
    }
    return
  }
  const data = node.data as TreeNode
  try {
    if (data.ntype === 'db') {
      resolve([
        { key: `${data.db}::ft`, name: 'Tables', ntype: 'folder-table', db: data.db, tb: '', leaf: false },
        { key: `${data.db}::fv`, name: 'Views', ntype: 'folder-view', db: data.db, tb: '', leaf: false },
      ])
    } else if (data.ntype === 'folder-table' || data.ntype === 'folder-view') {
      const kind = data.ntype === 'folder-table' ? 'table' as const : 'view' as const
      const items = await listDsTables(dsId, data.db, kind)
      resolve(items.map((t) => ({
        key: `${data.db}::${t.name}`, name: t.name, ntype: t.kind, db: data.db, tb: t.name, leaf: false,
      } as TreeNode)))
    } else if (data.ntype === 'table' || data.ntype === 'view') {
      const cols = await listDsColumns(dsId, data.db, data.tb)
      store.cacheColumns(data.db, data.tb, cols.map((x) => x.name))
      resolve(cols.map((c) => colNode(data.db, data.tb, c)))
    } else {
      resolve([])
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '节点加载失败')
    resolve([])
  }
}

function onNodeClick(data: TreeNode): void {
  if (data.ntype === 'db') {
    // Schema 点击切换默认命名空间（G11）
    store.setCurrentDb(data.db)
    ElMessage.success(`当前命名空间已切换为 ${data.db}`)
  }
}

/* ================= 搜索（G8：已加载本地匹配 + 后端检索） ================= */

const searchQ = ref('')
const searching = ref(false)
const searchHits = ref<DsSearchItem[]>([])
const searchLocalHits = ref<{ db: string; name: string; ntype: 'table' | 'view' }[]>([])

const doSearch = debounce(async () => {
  const q = searchQ.value.trim()
  if (!q || store.activeDsId === null) {
    searchHits.value = []
    searchLocalHits.value = []
    return
  }
  searching.value = true
  try {
    searchHits.value = await searchDsTables(store.activeDsId, q, 50)
  } catch (err) {
    searchHits.value = []
    ElMessage.error(err instanceof Error ? err.message : '检索失败')
  } finally {
    searching.value = false
  }
  // 已加载节点本地匹配（补全缓存中的 db/table 名）
  const lq = q.toLowerCase()
  const local: { db: string; name: string; ntype: 'table' | 'view' }[] = []
  for (const db of Object.keys(store.schemaCache)) {
    if (db.toLowerCase().includes(lq)) {
      for (const tb of Object.keys(store.schemaCache[db])) {
        local.push({ db, name: tb, ntype: 'table' })
      }
      continue
    }
    for (const tb of Object.keys(store.schemaCache[db])) {
      if (tb.toLowerCase().includes(lq)) local.push({ db, name: tb, ntype: 'table' })
    }
  }
  searchLocalHits.value = local.slice(0, 50)
}, 300)

watch(searchQ, () => {
  const q = searchQ.value.trim()
  if (!q) {
    doSearch.cancel()
    searchHits.value = []
    searchLocalHits.value = []
  } else {
    void doSearch()
  }
})

function pickSearchHit(db: string, name: string): void {
  store.setCurrentDb(db)
  store.requestFill(`SELECT * FROM ${db}.${name} LIMIT 100;`)
}

/* 切实例 → 重建树 + 清搜索 */
watch(() => store.activeDsId, () => {
  searchQ.value = ''
  searchHits.value = []
  searchLocalHits.value = []
  treeKey.value += 1
})

function refreshTree(): void {
  treeKey.value += 1
}

/* ================= 字段 Tooltip 复制（G9） ================= */

async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success(`已复制: ${text}`)
  } catch {
    ElMessage.error('剪贴板不可用')
  }
}

/* ================= 表/视图悬浮菜单（G10，11 项全部只生成 SQL） ================= */

interface HoverMenu {
  db: string
  tb: string
  kind: 'table' | 'view'
  x: number
  y: number
}

const hover = ref<HoverMenu | null>(null)
let hideTimer: ReturnType<typeof setTimeout> | null = null

function onTblEnter(evt: MouseEvent, data: TreeNode): void {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
  hover.value = { db: data.db, tb: data.tb, kind: data.ntype === 'view' ? 'view' : 'table', x: evt.clientX, y: evt.clientY }
}

function scheduleHide(): void {
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => { hover.value = null }, 260)
}

function keepMenu(): void {
  if (hideTimer) {
    clearTimeout(hideTimer)
    hideTimer = null
  }
}

function closeMenu(): void {
  hover.value = null
}

const MENU_ITEMS = [
  { id: 'select', label: '查询数据（可限定行数）' },
  { id: 'edit', label: '编辑数据' },
  { id: 'ddl', label: '结构（DDL）' },
  { id: 'count', label: '行数统计' },
  { id: 'addcol', label: '创建列' },
  { id: 'addidx', label: '创建索引' },
  { id: 'import', label: '导入数据（CSV）' },
  { id: 'drop', label: '删除表（无条件删除）' },
  { id: 'drop-audit', label: '删除表（稽核校验）' },
  { id: 'truncate', label: '截断表（无条件截断）' },
  { id: 'truncate-audit', label: '截断表（稽核校验）' },
] as const

type MenuId = (typeof MENU_ITEMS)[number]['id']

function onMenuClick(id: MenuId): void {
  const h = hover.value
  closeMenu()
  if (!h) return
  const qtb = `\`${h.db}\`.\`${h.tb}\``
  switch (id) {
    case 'select':
      void ElMessageBox.prompt('查询行数上限', '查询数据', {
        inputValue: '100', inputPattern: /^\d+$/, inputErrorMessage: '请输入非负整数',
      }).then(({ value }) => {
        store.requestFill(`SELECT * FROM ${qtb} LIMIT ${Number(value)};`)
      }).catch(() => undefined)
      break
    case 'edit':
      void openEditData(h.db, h.tb)
      break
    case 'ddl':
      void (async () => {
        if (store.activeDsId === null) return
        try {
          const resp = await getTableDdl(store.activeDsId, h.db, h.tb)
          store.requestFill(`-- ${h.db}.${h.tb} ${resp.kind === 'view' ? '视图' : '表'}结构\n${resp.ddl};`)
        } catch (err) {
          ElMessage.error(err instanceof Error ? err.message : 'DDL 获取失败')
        }
      })()
      break
    case 'count':
      store.requestFill(`SELECT COUNT(*) AS cnt FROM ${qtb};`)
      break
    case 'addcol':
      openAddColumn(h.db, h.tb)
      break
    case 'addidx':
      openAddIndex(h.db, h.tb)
      break
    case 'import':
      void openCsvImport(h.db, h.tb)
      break
    case 'drop':
      void dropTruncate(h.db, h.tb, 'drop', false)
      break
    case 'drop-audit':
      void dropTruncate(h.db, h.tb, 'drop', true)
      break
    case 'truncate':
      void dropTruncate(h.db, h.tb, 'truncate', false)
      break
    case 'truncate-audit':
      void dropTruncate(h.db, h.tb, 'truncate', true)
      break
  }
}

/** 删除/截断（无条件 or 稽核校验）：先 audit 展示 {pass, checks[]}，pass=false 硬阻断；通过后仅生成 SQL 填充 */
async function dropTruncate(db: string, tb: string, op: 'drop' | 'truncate', audited: boolean): Promise<void> {
  if (store.activeDsId === null) return
  let result: { pass: boolean; checks: AuditCheck[] }
  try {
    result = await auditTable(store.activeDsId, db, tb, op)
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '稽核请求失败')
    return
  }
  const qtb = `\`${db}\`.\`${tb}\``
  const sql = op === 'drop' ? `DROP TABLE ${qtb};` : `TRUNCATE TABLE ${qtb};`
  const opText = op === 'drop' ? '删除' : '截断'
  if (!result.pass) {
    const blocks = result.checks.filter((c) => c.level === 'block').map((c) => `✗ ${c.message}`).join('\n')
    const others = result.checks.filter((c) => c.level !== 'block').map((c) => `• ${c.message}`).join('\n')
    await ElMessageBox.alert(`${others ? `${others}\n\n` : ''}${blocks}`, `稽核未通过，已硬阻断 ${opText}操作`, {
      type: 'error', confirmButtonText: '知道了',
    }).catch(() => undefined)
    return
  }
  const checkLines = result.checks.length
    ? `\n稽核结果：\n${result.checks.map((c) => `${c.level === 'warn' ? '⚠' : '•'} ${c.message}`).join('\n')}`
    : '\n稽核结果：无风险项'
  try {
    await ElMessageBox.confirm(
      `将生成${opText}表 SQL：\n${sql}${audited ? checkLines : ''}\n\n确认后仅填充编辑器（不自动执行）。`,
      `高危操作：${opText}表 ${db}.${tb}`,
      { type: 'warning', confirmButtonText: `确认${opText}（填充SQL）`, cancelButtonText: '取消' },
    )
    store.requestFill(sql)
  } catch { /* 用户取消 */ }
}

/* ================= 创建列 / 创建索引（生成 ALTER/CREATE，仅填充） ================= */

const colFormVisible = ref(false)
const colForm = ref({ db: '', tb: '', name: '', dataType: 'VARCHAR', length: '64', defaultValue: '', nullable: true })
const COL_TYPES = ['INT', 'BIGINT', 'DECIMAL', 'VARCHAR', 'CHAR', 'TEXT', 'DATE', 'DATETIME', 'TIMESTAMP', 'TINYINT']

function openAddColumn(db: string, tb: string): void {
  colForm.value = { db, tb, name: '', dataType: 'VARCHAR', length: '64', defaultValue: '', nullable: true }
  colFormVisible.value = true
}

function genColumnSql(): void {
  const f = colForm.value
  if (!f.name.trim()) {
    ElMessage.warning('字段名不能为空')
    return
  }
  const hasLen = ['VARCHAR', 'CHAR', 'DECIMAL'].includes(f.dataType)
  let type = f.dataType
  if (hasLen && f.length.trim()) type = `${f.dataType}(${f.length.trim()})`
  const nullable = f.nullable ? 'NULL' : 'NOT NULL'
  const def = f.defaultValue.trim() ? ` DEFAULT '${f.defaultValue.trim()}'` : ''
  store.requestFill(`ALTER TABLE \`${f.db}\`.\`${f.tb}\` ADD COLUMN \`${f.name.trim()}\` ${type} ${nullable}${def};`)
  colFormVisible.value = false
}

const idxFormVisible = ref(false)
const idxForm = ref({ db: '', tb: '', name: '', cols: '', unique: false })

function openAddIndex(db: string, tb: string): void {
  idxForm.value = { db, tb, name: `idx_${tb}`, cols: '', unique: false }
  idxFormVisible.value = true
}

function genIndexSql(): void {
  const f = idxForm.value
  const cols = f.cols.split(/[,，\s]+/).filter((s) => s)
  if (!f.name.trim() || cols.length === 0) {
    ElMessage.warning('索引名与字段（逗号分隔）均必填')
    return
  }
  const colPart = cols.map((c) => `\`${c}\``).join(', ')
  const unique = f.unique ? 'UNIQUE ' : ''
  store.requestFill(`CREATE ${unique}INDEX \`${f.name.trim()}\` ON \`${f.db}\`.\`${f.tb}\` (${colPart});`)
  idxFormVisible.value = false
}

/* ================= 编辑数据弹窗（G23） ================= */

interface EditRow {
  vals: string[]
  orig: string[] | null // null=追加行
  deleted: boolean
}

const editVisible = ref(false)
const editLoading = ref(false)
const editDb = ref('')
const editTb = ref('')
const editCols = ref<string[]>([])
const editPks = ref<string[]>([])
const editRows = ref<EditRow[]>([])
const editTotal = ref(0)
const editPage = ref(1)
const EDIT_PAGE_SIZE = 200

async function openEditData(db: string, tb: string): Promise<void> {
  editDb.value = db
  editTb.value = tb
  editPage.value = 1
  editVisible.value = true
  await loadEditRows()
}

async function loadEditRows(): Promise<void> {
  if (store.activeDsId === null) return
  editLoading.value = true
  try {
    const resp = await getTableRows(
      store.activeDsId, editDb.value, editTb.value,
      (editPage.value - 1) * EDIT_PAGE_SIZE, EDIT_PAGE_SIZE,
    )
    editCols.value = resp.columns
    editPks.value = resp.pks
    editRows.value = resp.rows.map((r) => ({ vals: r.map((v) => (v === null ? '' : String(v))), orig: r.map((v) => (v === null ? '' : String(v))), deleted: false }))
    editTotal.value = resp.total
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '行加载失败')
  } finally {
    editLoading.value = false
  }
}

function appendEditRow(): void {
  editRows.value.push({ vals: editCols.value.map(() => ''), orig: null, deleted: false })
}

function pkVals(row: EditRow): Record<string, string> | null {
  if (!row.orig) return null
  const idx = editPks.value.map((pk) => editCols.value.indexOf(pk)).filter((i) => i >= 0)
  if (idx.length === 0) return null
  const keys: Record<string, string> = {}
  for (const i of idx) keys[editCols.value[i]] = row.orig[i]
  return keys
}

async function applyEdits(): Promise<void> {
  if (store.activeDsId === null) return
  const inserts: Record<string, string>[] = []
  const updates: { keys: Record<string, string>; data: Record<string, string> }[] = []
  const deletes: Record<string, string>[] = []
  for (const row of editRows.value) {
    if (row.orig === null) {
      const item: Record<string, string> = {}
      editCols.value.forEach((c, i) => {
        if (row.vals[i].trim() !== '') item[c] = row.vals[i]
      })
      if (Object.keys(item).length > 0) inserts.push(item)
      continue
    }
    if (row.deleted) {
      const keys = pkVals(row)
      if (keys) deletes.push(keys)
      continue
    }
    const keys = pkVals(row)
    if (!keys) continue
    const data: Record<string, string> = {}
    editCols.value.forEach((c, i) => {
      if (row.vals[i] !== row.orig?.[i]) data[c] = row.vals[i]
    })
    if (Object.keys(data).length > 0) updates.push({ keys, data })
  }
  const total = inserts.length + updates.length + deletes.length
  if (total === 0) {
    ElMessage.info('无变更')
    return
  }
  if (total > 1000) {
    ElMessage.warning('单次变更行数超过上限 1000，请分批应用')
    return
  }
  try {
    const resp = await applyTableRows(store.activeDsId, editDb.value, editTb.value, { inserts, updates, deletes })
    if (resp.status === 'success') {
      ElMessage.success(`应用成功：增/改/删 ${inserts.length}/${updates.length}/${deletes.length} 条`)
      await loadEditRows()
    } else {
      // 失败整体回滚提示（裁定③）
      ElMessage.error(`应用失败已整体回滚：${resp.error ?? '未知错误'}`)
    }
  } catch (err) {
    ElMessage.error(`应用失败已整体回滚：${err instanceof Error ? err.message : '未知错误'}`)
  }
}

/* ================= CSV 导入弹窗（G24） ================= */

const csvVisible = ref(false)
const csvDb = ref('')
const csvTb = ref('')
const csvFile = ref<File | null>(null)
const csvHasHeader = ref(true)
const csvHeader = ref<string[]>([])
const csvPreview = ref<string[][]>([])
const csvDataRowCount = ref(0)
const csvTargetCols = ref<DsColumnMeta[]>([])
const csvMapping = ref<Record<string, string>>({}) // 表字段 → CSV 列名
const csvUploading = ref(false)

function parseCsvLines(text: string, maxLines: number): string[][] {
  const lines = text.split(/\r?\n/).filter((l) => l.trim().length > 0)
  const out: string[][] = []
  for (const line of lines.slice(0, maxLines)) {
    out.push(parseCsvLine(line))
  }
  return out
}

function parseCsvLine(line: string): string[] {
  const cells: string[] = []
  let cur = ''
  let inQuote = false
  for (let i = 0; i < line.length; i++) {
    const ch = line[i]
    if (inQuote) {
      if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++ } else if (ch === '"') inQuote = false
      else cur += ch
    } else if (ch === '"') inQuote = true
    else if (ch === ',') { cells.push(cur.trim()); cur = '' }
    else cur += ch
  }
  cells.push(cur.trim())
  return cells
}

function onCsvFileChange(file: File | null): void {
  csvFile.value = file
  csvHeader.value = []
  csvPreview.value = []
  csvDataRowCount.value = 0
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    const text = String(reader.result ?? '')
    const parsed = parseCsvLines(text, 100001)
    if (parsed.length === 0) return
    if (csvHasHeader.value) {
      csvHeader.value = parsed[0]
      csvPreview.value = parsed.slice(1, 4)
      csvDataRowCount.value = parsed.length - 1
    } else {
      const width = parsed[0].length
      csvHeader.value = Array.from({ length: width }, (_, i) => `c${i + 1}`)
      csvPreview.value = parsed.slice(0, 3)
      csvDataRowCount.value = parsed.length
    }
  }
  reader.readAsText(file, 'utf-8')
}

watch(csvHasHeader, () => {
  if (csvFile.value) onCsvFileChange(csvFile.value)
})

async function openCsvImport(db: string, tb: string): Promise<void> {
  csvDb.value = db
  csvTb.value = tb
  csvFile.value = null
  csvHeader.value = []
  csvPreview.value = []
  csvDataRowCount.value = 0
  csvMapping.value = {}
  csvVisible.value = true
  if (store.activeDsId !== null) {
    try {
      csvTargetCols.value = await listDsColumns(store.activeDsId, db, tb)
    } catch {
      csvTargetCols.value = []
    }
  }
}

async function submitCsvImport(): Promise<void> {
  if (store.activeDsId === null) return
  if (!csvFile.value) {
    ElMessage.warning('请先选择 CSV 文件')
    return
  }
  if (csvDataRowCount.value > 100_000) {
    ElMessage.warning(`数据行 ${csvDataRowCount.value} 超过导入上限 10 万行，已拦截`)
    return
  }
  const mapping: Record<string, string> = {}
  for (const [tbCol, csvCol] of Object.entries(csvMapping.value)) {
    if (csvCol) mapping[csvCol] = tbCol
  }
  if (Object.keys(mapping).length === 0) {
    ElMessage.warning('请至少配置一列映射')
    return
  }
  csvUploading.value = true
  try {
    const resp = await importCsv(store.activeDsId, csvDb.value, csvTb.value, mapping, csvHasHeader.value, csvFile.value)
    ElMessage.success(`导入成功：${resp.imported} 行 × ${resp.columns.length} 列（事务提交）`)
    csvVisible.value = false
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '导入失败')
  } finally {
    csvUploading.value = false
  }
}

/* ================= 生命周期 ================= */

onBeforeUnmount(() => {
  doSearch.cancel()
  if (hideTimer) clearTimeout(hideTimer)
})

const currentDbLabel = computed(() => store.currentDb || '未选择 Schema')
</script>

<template>
  <div class="etree">
    <div class="etree-head">
      <input v-model="searchQ" class="etree-search" placeholder="搜索表（本地 + 后端检索）" />
      <button class="op-btn" title="刷新树" @click="refreshTree">↻</button>
    </div>
    <div class="etree-db">{{ currentDbLabel }}</div>

    <!-- 搜索态：本地已加载 + 后端检索结果 -->
    <div v-if="searchQ.trim()" class="etree-search-body">
      <div v-if="searching" class="etree-empty">检索中…</div>
      <template v-else>
        <div v-if="searchHits.length === 0 && searchLocalHits.length === 0" class="etree-empty">无匹配结果</div>
        <div v-for="h in searchHits" :key="h.db + '.' + h.name" class="hit-row" @click="pickSearchHit(h.db, h.name)">
          <span class="hit-ico">{{ h.kind === 'view' ? '◱' : '▤' }}</span>
          <span class="mono">{{ h.name }}</span>
          <span class="hit-db">{{ h.db }}</span>
        </div>
        <div v-for="h in searchLocalHits" :key="'L' + h.db + '.' + h.name" class="hit-row local" @click="pickSearchHit(h.db, h.name)">
          <span class="hit-ico">▤</span>
          <span class="mono">{{ h.name }}</span>
          <span class="hit-db">{{ h.db }}（已加载）</span>
        </div>
      </template>
    </div>

    <!-- 树态：懒加载 -->
    <div v-else class="etree-tree">
      <el-tree
        :key="treeKey"
        lazy
        :load="loadNode"
        :props="{ label: 'name', isLeaf: 'leaf' }"
        :node-key="'key'"
        highlight-current
        :expand-on-click-node="false"
        @node-click="onNodeClick"
      >
        <template #default="{ data }">
          <div
            v-if="data.ntype === 'table' || data.ntype === 'view'"
            class="tn tbl-node"
            @mouseenter="(ev: MouseEvent) => onTblEnter(ev, data as TreeNode)"
            @mouseleave="scheduleHide"
          >
            <span class="tn-ico">{{ data.ntype === 'view' ? '◱' : '▤' }}</span>
            <span class="mono">{{ data.name }}</span>
          </div>
          <div v-else-if="data.ntype === 'column' && data.col" class="tn col-node">
            <el-tooltip placement="right" :show-after="250" :hide-after="0">
              <template #content>
                <div class="col-tip">
                  <div class="ct-row"><b>{{ data.col.name }}</b></div>
                  <div class="ct-row">类型：{{ data.col.columnType || data.col.dataType }}<template v-if="data.col.length">（{{ data.col.length }}）</template></div>
                  <div class="ct-row">{{ data.col.key === 'PRI' ? '主键' : '非主键' }} · {{ data.col.nullable ? '可空' : '非空' }}<template v-if="data.col.extra"> · {{ data.col.extra }}</template></div>
                  <div class="ct-row">注释：{{ data.col.comment || '-' }}</div>
                  <div class="ct-row" style="margin-top:4px">
                    <button class="op-btn" @click.stop="copyText(data.col!.name)">复制字段名</button>
                  </div>
                </div>
              </template>
              <span class="tn mono">{{ data.name }}<i class="col-t">{{ data.col.dataType }}</i></span>
            </el-tooltip>
          </div>
          <div v-else class="tn" :class="{ db: data.ntype === 'db' }">
            <span class="tn-ico">{{ data.ntype === 'db' ? '⛁' : '▸' }}</span>
            <b v-if="data.ntype === 'db'" class="mono">{{ data.name }}</b>
            <span v-else>{{ data.name }}</span>
          </div>
        </template>
      </el-tree>
      <div v-if="store.activeDsId === null" class="etree-empty">请先在顶部选择实例</div>
    </div>

    <!-- 表/视图悬浮菜单（fixed 定位，绝不自动执行） -->
    <teleport to="body">
      <div
        v-if="hover"
        class="hover-menu"
        :style="{ left: hover.x + 'px', top: hover.y + 'px' }"
        @mouseenter="keepMenu"
        @mouseleave="scheduleHide"
      >
        <div class="hm-title mono">{{ hover.db }}.{{ hover.tb }}（{{ hover.kind === 'view' ? '视图' : '表' }}）</div>
        <button v-for="m in MENU_ITEMS" :key="m.id" class="hm-item" @click="onMenuClick(m.id)">{{ m.label }}</button>
        <div class="hm-foot">预制 SQL 仅填充编辑器，不自动执行</div>
      </div>
    </teleport>

    <!-- 创建列弹窗 -->
    <el-dialog v-model="colFormVisible" title="创建列（生成 ALTER，仅填充编辑器）" width="440px" append-to-body>
      <div class="form-grid">
        <span class="fg-k">目标表</span><span class="mono">{{ colForm.db }}.{{ colForm.tb }}</span>
        <span class="fg-k">字段名</span><input v-model="colForm.name" class="kw" />
        <span class="fg-k">类型</span>
        <select v-model="colForm.dataType" class="sel">
          <option v-for="t in COL_TYPES" :key="t" :value="t">{{ t }}</option>
        </select>
        <span class="fg-k">长度/精度</span><input v-model="colForm.length" class="kw" :disabled="!['VARCHAR', 'CHAR', 'DECIMAL'].includes(colForm.dataType)" />
        <span class="fg-k">默认值</span><input v-model="colForm.defaultValue" class="kw" />
        <span class="fg-k">可空</span><input v-model="colForm.nullable" type="checkbox" />
      </div>
      <template #footer>
        <button class="op-btn" @click="colFormVisible = false">取消</button>
        <button class="tb-new" @click="genColumnSql">生成 SQL</button>
      </template>
    </el-dialog>

    <!-- 创建索引弹窗 -->
    <el-dialog v-model="idxFormVisible" title="创建索引（生成 CREATE INDEX，仅填充编辑器）" width="440px" append-to-body>
      <div class="form-grid">
        <span class="fg-k">目标表</span><span class="mono">{{ idxForm.db }}.{{ idxForm.tb }}</span>
        <span class="fg-k">索引名</span><input v-model="idxForm.name" class="kw" />
        <span class="fg-k">字段</span><input v-model="idxForm.cols" class="kw" placeholder="多字段逗号分隔，如 col1, col2" />
        <span class="fg-k">唯一索引</span><input v-model="idxForm.unique" type="checkbox" />
      </div>
      <template #footer>
        <button class="op-btn" @click="idxFormVisible = false">取消</button>
        <button class="tb-new" @click="genIndexSql">生成 SQL</button>
      </template>
    </el-dialog>

    <!-- 编辑数据弹窗（G23） -->
    <el-dialog v-model="editVisible" :title="`编辑数据：${editDb}.${editTb}（事务内应用，失败整体回滚）`" width="86%" top="5vh" append-to-body>
      <div class="edit-toolbar">
        <span v-if="editPks.length === 0" class="edit-warn">该表无主键：仅支持追加行（分页可能漂移）</span>
        <span v-else class="edit-hint">主键：{{ editPks.join(', ') }} · 共 {{ editTotal }} 行</span>
        <span class="spacer" />
        <button class="op-btn" @click="appendEditRow">＋ 追加行</button>
        <button class="tb-new" :disabled="editLoading" @click="applyEdits">应用变更（事务）</button>
      </div>
      <div class="edit-wrap">
        <div v-if="editLoading" class="etree-empty">加载中…</div>
        <table v-else class="edit-tbl">
          <thead>
            <tr>
              <th style="width:52px">操作</th>
              <th v-for="c in editCols" :key="c" class="mono">
                {{ c }}<el-tag v-if="editPks.includes(c)" size="small" type="warning" effect="plain">PK</el-tag>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(row, ri) in editRows" :key="ri" :class="{ del: row.deleted, ins: row.orig === null }">
              <td>
                <button v-if="row.orig !== null" class="op-btn danger" @click="row.deleted = !row.deleted">
                  {{ row.deleted ? '恢复' : '删行' }}
                </button>
                <button v-else class="op-btn danger" @click="editRows.splice(ri, 1)">移除</button>
              </td>
              <td v-for="(c, ci) in editCols" :key="c">
                <input v-model="row.vals[ci]" class="kw cell" :class="{ changed: row.orig !== null && row.vals[ci] !== row.orig![ci] }" />
              </td>
            </tr>
            <tr v-if="editRows.length === 0">
              <td colspan="99" class="etree-empty">无数据行</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="edit-pager">
        <button class="op-btn" :disabled="editPage <= 1 || editLoading" @click="editPage--; loadEditRows()">← 上一页</button>
        <span>第 {{ editPage }} 页 / 共 {{ Math.max(1, Math.ceil(editTotal / EDIT_PAGE_SIZE)) }} 页（{{ editTotal }} 行）</span>
        <button
          class="op-btn"
          :disabled="editPage >= Math.ceil(editTotal / EDIT_PAGE_SIZE) || editLoading"
          @click="editPage++; loadEditRows()"
        >下一页 →</button>
      </div>
    </el-dialog>

    <!-- CSV 导入弹窗（G24） -->
    <el-dialog v-model="csvVisible" :title="`CSV 导入：${csvDb}.${csvTb}（≤10 万行，失败整体回滚）`" width="720px" append-to-body>
      <div class="csv-body">
        <div class="csv-row">
          <input type="file" accept=".csv,text/csv" @change="(e: Event) => onCsvFileChange((e.target as HTMLInputElement).files?.[0] ?? null)" />
          <label><input v-model="csvHasHeader" type="checkbox" /> 首行为表头</label>
        </div>
        <div v-if="csvFile" class="csv-meta">
          已选 {{ csvFile.name }} · 数据行约 {{ csvDataRowCount }} 行
          <span v-if="csvDataRowCount > 100_000" class="edit-warn">（超过 10 万行上限，将被拦截）</span>
        </div>
        <div v-if="csvPreview.length" class="csv-preview">
          <div class="csv-pt">首行预览：</div>
          <table class="edit-tbl">
            <thead>
              <tr><th v-for="h in csvHeader" :key="h" class="mono">{{ h }}</th></tr>
            </thead>
            <tbody>
              <tr v-for="(r, ri) in csvPreview" :key="ri">
                <td v-for="(cell, ci) in r" :key="ci" class="mono">{{ cell }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="csvTargetCols.length" class="csv-mapping">
          <div class="csv-pt">列映射（CSV 列 → 表字段；留空跳过）：</div>
          <div class="map-grid">
            <template v-for="c in csvTargetCols" :key="c.name">
              <span class="mono">{{ c.name }}<i class="col-t">{{ c.dataType }}</i></span>
              <select v-model="csvMapping[c.name]" class="sel">
                <option value="">（跳过）</option>
                <option v-for="h in csvHeader" :key="h" :value="h">{{ h }}</option>
              </select>
            </template>
          </div>
        </div>
      </div>
      <template #footer>
        <button class="op-btn" @click="csvVisible = false">取消</button>
        <button class="tb-new" :disabled="csvUploading" @click="submitCsvImport">
          {{ csvUploading ? '导入中…' : '执行导入' }}
        </button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.etree{display:flex;flex-direction:column;height:100%;background:var(--ide-card);overflow:hidden}
.etree-head{display:flex;gap:6px;padding:8px}
.etree-search{flex:1;border:1px solid var(--ide-border-strong);border-radius:var(--radius-sm);padding:5px 9px;font-size:12px;background:var(--ide-input);color:var(--ide-text);outline:none;min-width:0}
.etree-search:focus{border-color:var(--primary)}
.etree-db{padding:4px 10px;font-size:11.5px;color:var(--ide-text-3);border-bottom:1px solid var(--ide-border)}
.etree-tree{flex:1;overflow:auto;padding:4px 2px}
.etree-search-body{flex:1;overflow:auto;padding:6px}
.hit-row{display:flex;align-items:center;gap:6px;padding:5px 8px;font-size:12px;cursor:pointer;border-radius:var(--radius-sm);color:var(--ide-text-2)}
.hit-row:hover{background:var(--ide-hover);color:var(--primary)}
.hit-row.local .hit-db{color:var(--success)}
.hit-ico{font-size:11px;color:var(--ide-text-3)}
.hit-db{margin-left:auto;font-size:10.5px;color:var(--ide-text-3)}
.etree-empty{padding:20px 10px;text-align:center;color:var(--ide-text-3);font-size:12px}
.tn{display:inline-flex;align-items:center;gap:5px;font-size:12.5px;color:var(--ide-text-2);min-height:22px}
.tn.db{color:var(--ide-text)}
.tn-ico{font-size:11px;color:var(--ide-text-3)}
.col-t{font-style:normal;font-size:10px;color:var(--ide-text-3);margin-left:5px}
.col-tip{font-size:12px;line-height:1.7}
.ct-row{word-break:break-all}
.hover-menu{position:fixed;z-index:3000;display:flex;flex-direction:column;min-width:212px;background:var(--ide-card);border:1px solid var(--ide-border);border-radius:var(--radius-sm);box-shadow:var(--shadow-lg);padding:6px}
.hm-title{font-size:11.5px;color:var(--ide-text-3);padding:2px 6px 6px;border-bottom:1px solid var(--ide-border);margin-bottom:4px}
.hm-item{border:none;background:transparent;text-align:left;padding:5px 8px;font-size:12px;border-radius:4px;cursor:pointer;color:var(--ide-text-2)}
.hm-item:hover{background:var(--primary-light);color:var(--primary)}
.hm-foot{font-size:10px;color:var(--ide-text-3);padding:5px 6px 2px;border-top:1px solid var(--ide-border);margin-top:4px}
/* 表单 */
.form-grid{display:grid;grid-template-columns:82px 1fr;gap:8px 10px;align-items:center;font-size:12.5px}
.fg-k{color:var(--ide-text-3)}
.sel{border:1px solid var(--ide-border-strong);border-radius:var(--radius-sm);padding:5px 8px;font-size:12.5px;background:var(--ide-input);color:var(--ide-text)}
.kw{border:1px solid var(--ide-border-strong);border-radius:var(--radius-sm);padding:5px 9px;font-size:12.5px;background:var(--ide-input);color:var(--ide-text);outline:none}
/* 编辑数据 */
.edit-toolbar{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
.edit-hint{font-size:12px;color:var(--ide-text-3)}
.edit-warn{font-size:12px;color:var(--ide-warn)}
.spacer{flex:1}
.edit-wrap{max-height:56vh;overflow:auto;border:1px solid var(--ide-border);border-radius:var(--radius-sm)}
.edit-tbl{width:100%;border-collapse:collapse;font-size:12px}
.edit-tbl th{text-align:left;padding:6px 8px;background:var(--ide-bg);color:var(--ide-text-2);border-bottom:1px solid var(--ide-border);white-space:nowrap;position:sticky;top:0}
.edit-tbl td{padding:3px 6px;border-bottom:1px solid var(--ide-border)}
.edit-tbl tr.ins td{background:var(--success-bg)}
.edit-tbl tr.del td{background:var(--danger-bg);text-decoration:line-through}
.cell{width:100%;min-width:80px;border:1px solid transparent;background:transparent;border-radius:3px;padding:3px 5px;font-size:12px;color:var(--ide-text);font-family:ui-monospace,Consolas,monospace}
.cell:focus{border-color:var(--primary);background:var(--ide-input)}
.cell.changed{border-color:var(--warn);background:var(--ide-warn-bg)}
.edit-pager{display:flex;align-items:center;justify-content:center;gap:12px;margin-top:10px;font-size:12px;color:var(--ide-text-3)}
.op-btn.danger{color:var(--danger)}
/* CSV 导入 */
.csv-body{display:flex;flex-direction:column;gap:10px;font-size:12.5px}
.csv-row{display:flex;align-items:center;gap:14px}
.csv-meta{color:var(--ide-text-3)}
.csv-pt{font-weight:600;margin-bottom:6px;color:var(--ide-text-2)}
.csv-preview{border:1px solid var(--ide-border);border-radius:var(--radius-sm);overflow:auto;max-height:160px}
.csv-mapping{border:1px solid var(--ide-border);border-radius:var(--radius-sm);padding:8px;max-height:220px;overflow:auto}
.map-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 12px;align-items:center}
</style>
