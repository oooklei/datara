<script setup lang="ts">
/**
 * M10 代码标准（/std/code）
 * 对齐 prototype/assets/pages/m10-standard.js L340-415：
 * 主从布局：左侧码表列表（stdCodes），右侧选中码表的码值维护（码值/含义 增删改）；
 * 顶部工具栏：新建代码标准；行操作：编辑 / 发布·停用 / 删除（被引用时禁止删除）。
 */
import { ref, computed, onMounted } from 'vue'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { localTime } from '../../services/mock/timeUtil'
import type { DbUser, StdApproval, StdCode, StdCodeValue } from '../../services/types'

const rows = ref<StdCode[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '' })
const user = ref<DbUser>({ name: '王工', role: '' })
const statusOptions = [
  { v: 'draft', t: '草稿' },
  { v: 'review', t: '评审中' },
  { v: 'published', t: '已发布' },
  { v: 'disabled', t: '已停用' },
]

/* ---- 左侧筛选面板 facets ---- */
const facets = computed<Facet[]>(() => [
  { key: 'status', label: '状态', options: statusOptions },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.id, r.name].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 当前选中码表（从侧） ---- */
const cur = ref<StdCode | null>(null)
const vals = ref<StdCodeValue[]>([])

function selectRow(r: StdCode | null) {
  cur.value = r
  vals.value = r ? r.values.map((v) => ({ ...v })) : []
}

async function reload(keepCur = true) {
  // 展开为新数组触发响应式更新（save 原地修改数组，list 返回同一引用）
  rows.value = [...((await dataStore.list<StdCode>('stdCodes')) ?? [])]
  const exist = keepCur && cur.value ? rows.value.find((r) => r.id === cur.value?.id) : null
  selectRow(exist ?? rows.value[0] ?? null)
}

onMounted(async () => {
  await reload(false)
  const u = await dataStore.get<DbUser>('user')
  if (u) user.value = u
})

/* ---- 时间 / HTML 工具 ---- */
function pad2(n: number): string {
  return String(n).padStart(2, '0')
}
/** yyyyMMdd（导出文件名 / 审批单号用） */
function dateStamp(d: Date): string {
  return `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}`
}
function escHtml(s: string): string {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

/* ---- ST 徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}

/* ---- 新建 / 编辑码表 ---- */
const formVisible = ref(false)
const editing = ref<StdCode | null>(null)
const formName = ref('')

function openCreate() {
  editing.value = null
  formName.value = ''
  formVisible.value = true
}

function openEdit(r: StdCode) {
  editing.value = r
  formName.value = r.name
  formVisible.value = true
}

async function saveForm() {
  const name = formName.value.trim()
  if (!name) {
    ElMessage.warning('请填写标准名称')
    return
  }
  if (editing.value) {
    editing.value.name = name
    await dataStore.save('stdCodes', editing.value)
    ElMessage.success('已保存')
  } else {
    const nextSeq = rows.value.reduce((m, r) => {
      const n = Number(r.id.slice(2))
      return Number.isFinite(n) && n > m ? n : m
    }, 0) + 1
    const row: StdCode = { id: 'C-' + String(nextSeq).padStart(3, '0'), name, values: [], status: 'draft', used: 0 }
    rows.value.push(row)
    await dataStore.save('stdCodes', row)
    ElMessage.success('代码标准已创建，请维护码值')
    selectRow(row)
  }
  formVisible.value = false
}

/* ---- 码值维护（从侧） ---- */
function addVal() {
  vals.value.push({ c: '', n: '' })
}
function delVal(i: number) {
  vals.value.splice(i, 1)
}
async function saveVals() {
  const d = cur.value
  if (!d) return
  const clean = vals.value
    .map((v) => ({ c: v.c.trim(), n: v.n.trim() }))
    .filter((v) => v.c)
  d.values = clean
  await dataStore.save('stdCodes', d)
  vals.value = clean.map((v) => ({ ...v }))
  ElMessage.success(`码值已保存（${clean.length} 项）`)
}

/* ---- 发布 / 停用 ---- */
async function toggleStatus(r: StdCode) {
  if (r.status === 'published') {
    r.status = 'disabled'
    await dataStore.save('stdCodes', r)
    ElMessage.info(`「${r.name}」已停用`)
  } else {
    if (!r.values.length) {
      ElMessage.warning('请先维护码值再发布')
      return
    }
    try {
      await ElMessageBox.confirm(`发布「${r.name}」？发布后可被建模与质量规则引用。`, '发布代码标准', {
        confirmButtonText: '发布', cancelButtonText: '取消', type: 'info',
      })
    } catch {
      return
    }
    r.status = 'published'
    await dataStore.save('stdCodes', r)
    ElMessage.success(`「${r.name}」已发布`)
  }
}

/* ---- 删除（被引用禁止） ---- */
async function removeRow(r: StdCode) {
  if (r.used > 0) {
    ElMessageBox.alert(`「${r.name}」已被 ${r.used} 处引用，请先解除引用后再删除。`, '无法删除', { confirmButtonText: '知道了' })
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除代码标准「${r.name}」？该操作不可恢复。`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await dataStore.remove('stdCodes', r.id)
  if (cur.value?.id === r.id) cur.value = null
  ElMessage.success('已删除')
  await reload()
}

/* ---- 导出 Excel（一行一个码值，HTML table + BOM，无新增依赖） ---- */
function exportExcel() {
  const head = '<tr><th>代码集编号</th><th>代码集名</th><th>编码</th><th>名称</th><th>状态</th></tr>'
  const lines: string[] = [head]
  for (const r of filtered.value) {
    const st = escHtml(stLabel(r.status))
    const id = escHtml(r.id)
    const name = escHtml(r.name)
    if (!r.values.length) {
      lines.push(`<tr><td>${id}</td><td>${name}</td><td></td><td></td><td>${st}</td></tr>`)
      continue
    }
    for (const v of r.values) {
      lines.push(`<tr><td>${id}</td><td>${name}</td><td>${escHtml(v.c)}</td><td>${escHtml(v.n)}</td><td>${st}</td></tr>`)
    }
  }
  const blob = new Blob(['\ufeff' + `<table>${lines.join('')}</table>`], { type: 'application/vnd.ms-excel' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `std_codes_${dateStamp(new Date())}.xls`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(`已导出 ${filtered.value.length} 个代码标准（码值明细）`)
}

/* ---- 导入 Excel / CSV（按代码集名分组聚合码值） ---- */
const importInput = ref<HTMLInputElement | null>(null)

function pickImport() {
  importInput.value?.click()
}

function parseImportRows(text: string): string[][] {
  if (text.includes('<table')) {
    // 本工具导出的 Excel（HTML 表格）：DOMParser 提取 tr/td
    const doc = new DOMParser().parseFromString(text, 'text/html')
    return Array.from(doc.querySelectorAll('tr')).map((tr) =>
      Array.from(tr.querySelectorAll('td,th')).map((td) => (td.textContent ?? '').trim()))
  }
  // CSV / TSV：按行拆分后以逗号或制表符分列
  return text.split(/\r?\n/).map((line) => line.split(/\t|,/).map((s) => s.trim()))
}

async function onImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // 允许重复选择同一文件
  if (!file) return
  const text = await new Promise<string>((resolve) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.readAsText(file, 'utf-8')
  })
  const dataRows = parseImportRows(text).filter((cells) => cells.some((c) => c !== '')).slice(1) // 首行为表头
  // 按「代码集名」分组聚合码值；首两列为空的行视为上一代码集的续行
  const groups: { id: string; name: string; values: StdCodeValue[] }[] = []
  let last: { id: string; name: string; values: StdCodeValue[] } | null = null
  for (const cells of dataRows) {
    let id = '', name = '', c = '', n = ''
    if (cells.length >= 4) { id = cells[0]; name = cells[1]; c = cells[2]; n = cells[3] }
    else if (cells.length === 3) { name = cells[0]; c = cells[1]; n = cells[2] }
    else continue
    if (!id && !name) {
      if (last && c) last.values.push({ c, n })
      continue
    }
    last = { id, name, values: c ? [{ c, n }] : [] }
    groups.push(last)
  }
  let maxSeq = rows.value.reduce((m, r) => {
    const n2 = Number(r.id.slice(2))
    return Number.isFinite(n2) && n2 > m ? n2 : m
  }, 0)
  const seenNames = new Set(rows.value.map((r) => r.name))
  let ok = 0, dup = 0, miss = 0
  for (const g of groups) {
    if (!g.name) { miss++; continue }
    if (seenNames.has(g.name) || (g.id && rows.value.some((r) => r.id === g.id))) { dup++; continue }
    const seenC = new Set<string>()
    const values = g.values.filter((v) => {
      if (!v.c || seenC.has(v.c)) return false
      seenC.add(v.c)
      return true
    })
    maxSeq++
    const row: StdCode = {
      id: 'C-' + String(maxSeq).padStart(3, '0'),
      name: g.name,
      values,
      status: 'draft',
      used: 0,
    }
    rows.value.push(row)
    seenNames.add(g.name)
    await dataStore.save('stdCodes', row)
    ok++
  }
  await reload()
  ElMessage.success(`导入成功 ${ok} 条，跳过 ${dup + miss} 条（重复 ${dup} / 缺失 ${miss}）`)
}

/* ---- 提交评审（草稿 → 评审中，生成 StdApproval 供标准审批跟踪） ---- */
async function nextApprovalId(): Promise<string> {
  const prefix = 'SA' + dateStamp(new Date()) + '-'
  const list = await dataStore.list<StdApproval>('stdApprovals')
  let maxSeq = 0
  for (const a of list) {
    if (!a.id.startsWith(prefix)) continue
    const n = Number(a.id.slice(prefix.length))
    if (Number.isFinite(n) && n > maxSeq) maxSeq = n
  }
  return prefix + String(maxSeq + 1).padStart(2, '0')
}

async function submitReview(r: StdCode) {
  try {
    await ElMessageBox.confirm(`确认提交「${r.name}（${r.id}）」进入评审？评审通过后自动发布。`, '提交评审', {
      confirmButtonText: '提交', cancelButtonText: '取消', type: 'info',
    })
  } catch {
    return
  }
  r.status = 'review'
  await dataStore.save('stdCodes', r)
  const approval: StdApproval = {
    id: await nextApprovalId(),
    type: '代码标准',
    target: `${r.id} ${r.name}（码值 ${r.values.length} 项）`,
    proposer: user.value.name,
    submitAt: localTime(),
    flow: ['起草', '评审', '发布'],
    current: 1,
    status: 'review',
    opinion: '',
  }
  await dataStore.save('stdApprovals', approval)
  ElMessage.success('已提交评审，可在标准审批中跟踪')
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索代码标准"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <div class="code-grid">
      <!-- 主：码表列表 -->
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar">
          <span class="sec-head">代码标准列表</span>
          <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
          <span class="spacer" />
          <button class="tb-new" @click="openCreate">＋ 新建代码标准</button>
          <button class="op-btn" @click="exportExcel">⇩ 导出Excel</button>
          <button class="op-btn" @click="pickImport">⇪ 导入Excel</button>
          <input ref="importInput" type="file" accept=".xls,.xlsx,.csv" style="display:none" @change="onImportFile" />
        </div>

        <table class="tbl">
          <thead>
            <tr>
              <th>标准</th><th>码值</th><th>引用</th><th>状态</th><th style="width:245px">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in filtered" :key="r.id" :class="{ on: cur?.id === r.id }">
              <td>
                <b>{{ r.name }}</b>
                <div class="mono" style="font-size:11px;color:var(--text-3)">{{ r.id }}</div>
              </td>
              <td>
                <span v-for="v in r.values" :key="v.c" class="pill info" style="margin:1px 4px 1px 0">{{ v.c }}={{ v.n }}</span>
                <span v-if="!r.values.length" style="color:var(--text-3)">未维护</span>
              </td>
              <td>
                <a v-if="r.used" class="mono">{{ r.used }} 处</a>
                <span v-else style="color:var(--text-3)">未引用</span>
              </td>
              <td>
                <span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span>
              </td>
              <td>
                <button class="op-btn primary" @click="selectRow(r)">码值维护</button>
                <button class="op-btn" @click="openEdit(r)">编辑</button>
                <button v-if="r.status === 'draft'" class="op-btn" @click="submitReview(r)">提交评审</button>
                <button class="op-btn" @click="toggleStatus(r)">{{ r.status === 'published' ? '停用' : '发布' }}</button>
                <button class="op-btn danger" @click="removeRow(r)">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-if="filtered.length === 0" class="empty">未找到匹配的代码标准，请调整筛选条件</div>
      </div>

      <!-- 从：码值维护 -->
      <div class="card" style="padding:16px">
        <div class="tbl-toolbar">
          <span class="sec-head">码值维护</span>
          <span v-if="cur" class="mono" style="font-size:12px;color:var(--text-3)">{{ cur.id }} · {{ cur.name }}</span>
          <span class="spacer" />
          <button v-if="cur" class="tb-new" @click="addVal">＋ 增加码值</button>
        </div>

        <template v-if="cur">
          <div v-for="(v, i) in vals" :key="i" class="val-line">
            <input v-model="v.c" class="kw" style="width:130px" placeholder="码值" />
            <input v-model="v.n" class="kw" style="flex:1" placeholder="含义" />
            <button class="op-btn danger" @click="delVal(i)">删</button>
          </div>
          <div v-if="vals.length === 0" class="empty" style="padding:20px 10px">
            暂无码值，点击「＋ 增加码值」添加
          </div>
          <div style="margin-top:12px">
            <button class="tb-new" @click="saveVals">保存码值（{{ vals.length }} 项）</button>
          </div>
          <div class="hint">码表编码遵循 C-XXX 编号规则；码值发布后方可被模型字段约束与质量枚举检核引用。</div>
        </template>
        <div v-else class="empty">请在左侧选择代码标准</div>
      </div>
    </div>

    <!-- 新建 / 编辑码表抽屉 -->
    <el-drawer v-model="formVisible" :title="editing ? '编辑代码标准 - ' + editing.name : '新建代码标准'" size="380px">
      <div class="form-grid">
        <label class="f-item">标准名称
          <input v-model="formName" placeholder="如：支付渠道" />
        </label>
      </div>
      <div v-if="!editing" class="hint">保存后生成草稿，请在右侧「码值维护」中补充码值后再发布。</div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveForm">保存{{ editing ? '' : '（草稿）' }}</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>
    </div>
  </div>
</template>

<style scoped>
.code-grid{display:grid;grid-template-columns:1.6fr 1fr;gap:16px;align-items:start}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.tbl tr.on td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:170px;outline:none;transition:all var(--dur-fast) var(--ease)}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2);transition:all var(--dur-fast) var(--ease)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2);transition:all var(--dur-fast) var(--ease)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.val-line{display:flex;gap:8px;margin-bottom:8px;align-items:center}
.val-line .kw{width:auto}
.hint{font-size:11.5px;color:var(--text-3);margin-top:12px;line-height:1.6}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.f-item input{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;outline:none;transition:all var(--dur-fast) var(--ease)}
.f-item input:focus{border-color:var(--primary)}
</style>
