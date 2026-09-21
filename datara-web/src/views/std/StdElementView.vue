<script setup lang="ts">
/**
 * M10 数据元标准（/std/element）
 * 对齐 prototype/assets/pages/m10-standard.js L233-337：
 * 数据元表格（stdElements）+ 新建/编辑抽屉（中英文名/类型/长度/格式约束/主题域/描述）；
 * 顶部工具栏：新建数据元、查看映射合规；行操作：编辑 / 删除。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { localTime } from '../../services/mock/timeUtil'
import type { BizDomain, DbUser, StdApproval, StdElement } from '../../services/types'

const router = useRouter()

const rows = ref<StdElement[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '', domain: '' })

const statusOptions = [
  { v: 'draft', t: '草稿' },
  { v: 'review', t: '评审中' },
  { v: 'published', t: '已发布' },
]
const typeOptions = ['BIGINT', 'DECIMAL', 'VARCHAR', 'CHAR', 'DATE', 'DATETIME', 'TINYINT', 'TEXT']
const domainNames = ref<string[]>(['交易域', '经营域', '商品域', '财务域', '公共'])
const user = ref<DbUser>({ name: '王工', role: '' })

/* ---- 左侧筛选面板 facets ---- */
const facets = computed<Facet[]>(() => [
  { key: 'status', label: '状态', options: statusOptions },
  { key: 'domain', label: '主题域', options: domainNames.value.map((d) => ({ v: d, t: d })) },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.status && r.status !== filters.value.status) return false
    if (filters.value.domain && r.domain !== filters.value.domain) return false
    if (!kw) return true
    return [r.id, r.cn, r.en].some((s) => s.toLowerCase().includes(kw))
  })
})

async function reload() {
  // 展开为新数组触发响应式更新（save 原地修改数组，list 返回同一引用）
  rows.value = [...((await dataStore.list<StdElement>('stdElements')) ?? [])]
}

onMounted(async () => {
  await reload()
  const [domains, u] = await Promise.all([
    dataStore.list<BizDomain>('bizDomains'),
    dataStore.get<DbUser>('user'),
  ])
  if (domains.length) domainNames.value = domains.map((d) => d.name)
  if (u) user.value = u
})

/* ---- ST 徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}

/* ---- 时间 ---- */
function todayStr(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function pad2(n: number): string {
  return String(n).padStart(2, '0')
}
/** yyyyMMdd（导出文件名 / 审批单号用） */
function dateStamp(d: Date): string {
  return `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}`
}

/* ---- 新建 / 编辑（对齐原型 A.deFormFields） ---- */
const formVisible = ref(false)
const editing = ref<StdElement | null>(null)
const form = ref({ cn: '', en: '', type: 'VARCHAR', len: '', format: '', domain: '公共', desc: '' })

function openCreate() {
  editing.value = null
  form.value = { cn: '', en: '', type: 'VARCHAR', len: '', format: '', domain: '公共', desc: '' }
  formVisible.value = true
}

function openEdit(r: StdElement) {
  editing.value = r
  form.value = { cn: r.cn, en: r.en, type: r.type, len: String(r.len ?? '-'), format: r.format, domain: r.domain, desc: r.desc }
  formVisible.value = true
}

async function saveForm() {
  const cn = form.value.cn.trim()
  const en = form.value.en.trim()
  if (!cn || !en) {
    ElMessage.warning('请填写中英文名')
    return
  }
  if (editing.value) {
    Object.assign(editing.value, {
      cn, en,
      type: form.value.type,
      len: form.value.len.trim() || '-',
      format: form.value.format.trim(),
      domain: form.value.domain,
      desc: form.value.desc.trim(),
      updatedAt: todayStr(),
    })
    await dataStore.save('stdElements', editing.value)
    ElMessage.success('规范已保存（变更需重新提交评审）')
  } else {
    const nextSeq = rows.value.reduce((m, r) => {
      const n = Number(r.id.slice(3))
      return Number.isFinite(n) && n > m ? n : m
    }, 0) + 1
    const row: StdElement = {
      id: 'DE-' + String(nextSeq).padStart(3, '0'),
      cn, en,
      type: form.value.type,
      len: form.value.len.trim() || '-',
      format: form.value.format.trim(),
      domain: form.value.domain,
      desc: form.value.desc.trim(),
      status: 'draft',
      v: 1,
      owner: user.value.name,
      updatedAt: todayStr(),
    }
    rows.value.push(row)
    await dataStore.save('stdElements', row)
    ElMessage.success('数据元已创建（草稿），可在列表查看')
  }
  formVisible.value = false
}

/* ---- 删除（二次确认） ---- */
async function removeRow(r: StdElement) {
  try {
    await ElMessageBox.confirm(`确认删除数据元「${r.cn}（${r.id}）」？该操作不可恢复。`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await dataStore.remove('stdElements', r.id)
  ElMessage.success('已删除')
  await reload()
}

/* ---- 导出 Excel（HTML table + BOM，无需额外依赖） ---- */
function escHtml(s: string): string {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function exportExcel() {
  const head = '<tr><th>编号</th><th>中文名</th><th>英文名</th><th>类型</th><th>长度</th><th>格式约束</th><th>主题域</th><th>状态</th><th>版本</th><th>负责人</th><th>更新时间</th></tr>'
  const body = filtered.value
    .map((r) =>
      '<tr>' + [r.id, r.cn, r.en, r.type, String(r.len ?? '-'), r.format, r.domain, stLabel(r.status), `v${r.v}`, r.owner, r.updatedAt]
        .map((c) => `<td>${escHtml(c)}</td>`).join('') + '</tr>')
    .join('')
  const blob = new Blob(['\ufeff' + `<table>${head}${body}</table>`], { type: 'application/vnd.ms-excel' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `std_elements_${dateStamp(new Date())}.xls`
  a.click()
  URL.revokeObjectURL(url)
  ElMessage.success(`已导出 ${filtered.value.length} 条数据元`)
}

/* ---- 导入 Excel / CSV（宽容解析，无新增依赖） ---- */
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
  const all = parseImportRows(text).filter((cells) => cells.some((c) => c !== ''))
  if (all.length === 0) {
    ElMessage.warning('导入文件为空')
    return
  }
  const dataRows = all.slice(1) // 首行为表头，跳过
  // 宽容列序：本工具导出的首列为编号（DE-XXX）自动跳过；否则取前 6 列 cn,en,type,len,format,domain
  const start = /^DE-\d+$/i.test(dataRows[0]?.[0] ?? '') ? 1 : 0
  let maxSeq = rows.value.reduce((m, r) => {
    const n = Number(r.id.slice(3))
    return Number.isFinite(n) && n > m ? n : m
  }, 0)
  const seenEn = new Set(rows.value.map((r) => r.en.toLowerCase()))
  let ok = 0, dup = 0, miss = 0
  for (const cells of dataRows) {
    const cn = (cells[start] ?? '').trim()
    const en = (cells[start + 1] ?? '').trim()
    if (!cn || !en) { miss++; continue }
    if (seenEn.has(en.toLowerCase())) { dup++; continue }
    const rawType = (cells[start + 2] ?? '').trim()
    maxSeq++
    const row: StdElement = {
      id: 'DE-' + String(maxSeq).padStart(3, '0'),
      cn, en,
      type: typeOptions.includes(rawType) ? rawType : 'VARCHAR',
      len: (cells[start + 3] ?? '').trim() || '-',
      format: (cells[start + 4] ?? '').trim(),
      domain: (cells[start + 5] ?? '').trim() || '公共',
      desc: '',
      status: 'draft',
      v: 1,
      owner: user.value.name,
      updatedAt: localTime(),
    }
    rows.value.push(row)
    seenEn.add(en.toLowerCase())
    await dataStore.save('stdElements', row)
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

async function submitReview(r: StdElement) {
  try {
    await ElMessageBox.confirm(`确认提交「${r.cn}（${r.id}）」进入评审？评审通过后自动发布。`, '提交评审', {
      confirmButtonText: '提交', cancelButtonText: '取消', type: 'info',
    })
  } catch {
    return
  }
  r.status = 'review'
  await dataStore.save('stdElements', r)
  const approval: StdApproval = {
    id: await nextApprovalId(),
    type: '数据元标准',
    target: `${r.id} ${r.cn}（v${r.v}）`,
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

function goMapping() {
  router.push('/std/mapping')
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索编码/中英文名"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">数据元标准</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
        <button class="tb-new" @click="openCreate">＋ 新建数据元</button>
        <button class="op-btn" @click="exportExcel">⇩ 导出Excel</button>
        <button class="op-btn" @click="pickImport">⇪ 导入Excel</button>
        <input ref="importInput" type="file" accept=".xls,.xlsx,.csv" style="display:none" @change="onImportFile" />
        <button class="op-btn" @click="goMapping">查看映射合规</button>
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>数据元</th><th>类型 / 长度</th><th>格式约束</th><th>主题域</th>
            <th>状态</th><th>版本</th><th>负责人</th><th>更新时间</th><th style="width:160px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td>
              <b>{{ r.cn }}</b>
              <div class="mono" style="color:var(--text-3);font-size:11px">{{ r.id }} · {{ r.en }}</div>
            </td>
            <td>
              <span class="mono">{{ r.type }}</span>
              <span v-if="r.len && r.len !== '-'" class="mono" style="color:var(--text-3)">({{ r.len }})</span>
            </td>
            <td style="font-size:11.5px;color:var(--text-2)">{{ r.format }}</td>
            <td><span class="pill info">{{ r.domain }}</span></td>
            <td>
              <span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span>
            </td>
            <td>v{{ r.v }}</td>
            <td>{{ r.owner }}</td>
            <td style="color:var(--text-2)">{{ r.updatedAt }}</td>
            <td>
              <button v-if="r.status === 'draft'" class="op-btn" @click="submitReview(r)">提交评审</button>
              <button class="op-btn primary" @click="openEdit(r)">编辑</button>
              <button class="op-btn danger" @click="removeRow(r)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="filtered.length === 0" class="empty">
        未找到匹配的数据元，请调整筛选条件
      </div>
    </div>

    <!-- 新建 / 编辑抽屉 -->
    <el-drawer v-model="formVisible" :title="editing ? '编辑规范 - ' + editing.cn : '新建数据元'" size="480px">
      <div class="form-grid">
        <label class="f-item">中文名
          <input v-model="form.cn" placeholder="如：支付金额" />
        </label>
        <label class="f-item">英文名（snake_case）
          <input v-model="form.en" placeholder="如：pay_amount" />
        </label>
        <label class="f-item">数据类型
          <select v-model="form.type">
            <option v-for="t in typeOptions" :key="t" :value="t">{{ t }}</option>
          </select>
        </label>
        <label class="f-item">长度 / 精度
          <input v-model="form.len" placeholder="如：(18,2) 或 20" />
        </label>
        <label class="f-item">格式约束
          <input v-model="form.format" placeholder="如：≥0，单位元" />
        </label>
        <label class="f-item">主题域
          <select v-model="form.domain">
            <option v-for="d in domainNames" :key="d" :value="d">{{ d }}</option>
          </select>
        </label>
        <label class="f-item">业务描述
          <textarea v-model="form.desc" rows="2" style="resize:vertical" placeholder="数据元业务含义说明" />
        </label>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="tb-new" @click="saveForm">保存</button>
        <button class="op-btn" @click="formVisible = false">取消</button>
      </div>
    </el-drawer>
    </div>
  </div>
</template>

<style scoped>
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none;transition:all var(--dur-fast) var(--ease)}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2);transition:all var(--dur-fast) var(--ease)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2);transition:all var(--dur-fast) var(--ease)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.f-item input,.f-item select,.f-item textarea{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;outline:none;font-family:inherit;background:#fff;color:var(--text);transition:all var(--dur-fast) var(--ease)}
.f-item input:focus,.f-item select:focus,.f-item textarea:focus{border-color:var(--primary)}
</style>
