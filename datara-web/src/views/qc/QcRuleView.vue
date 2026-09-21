<script setup lang="ts">
/**
 * M07 质量规则（/qc/rule）
 * 原型对齐：prototype/assets/pages/m07-quality.js L37-152（#/qc/rule + A.qr* 系列）
 * 六维统计卡（点击筛选）+ 规则表格（搜索/维度/级别/状态/结果筛选）+ 顶部工具栏：
 * 新建规则 / 从模板创建；行操作：详情 / 试跑 / 编辑 / 启停用 / 删除（被任务编排时阻断）。
 * 数据：qcRules（读写）/ qcDims / metaTables / user。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { QcRule, QcDim, MetaTable, DbUser } from '../../services/types'

const rules = ref<QcRule[]>([])
const dims = ref<QcDim[]>([])
const tables = ref<MetaTable[]>([])
const owner = ref('王工')

onMounted(async () => {
  await reload()
  dims.value = [...((await dataStore.list<QcDim>('qcDims')) ?? [])]
  tables.value = [...((await dataStore.list<MetaTable>('metaTables')) ?? [])]
  owner.value = (await dataStore.get<DbUser>('user'))?.name ?? '王工'
})

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发响应式更新。
  rules.value = [...((await dataStore.list<QcRule>('qcRules')) ?? [])]
}

/* ---- 搜索 / 筛选（左侧 ListFilterPanel） ---- */
const keyword = ref('')
const filters = ref<Record<string, string>>({ dim: '', level: '', status: '', lastResult: '' })

const facets = computed<Facet[]>(() => [
  { key: 'dim', label: '质量维度', options: dims.value.map((d) => ({ v: d.code, t: d.name })) },
  { key: 'level', label: '规则级别', options: [{ v: '强规则', t: '强规则' }, { v: '弱规则', t: '弱规则' }] },
  { key: 'status', label: '状态', options: [{ v: 'enabled', t: '启用' }, { v: 'disabled', t: '停用' }] },
  { key: 'lastResult', label: '最近结果', options: [{ v: 'pass', t: '通过' }, { v: 'fail', t: '失败' }] },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rules.value.filter((r) => {
    if (filters.value.dim && r.dim !== filters.value.dim) return false
    if (filters.value.level && r.level !== filters.value.level) return false
    if (filters.value.status && r.status !== filters.value.status) return false
    if (filters.value.lastResult && r.lastResult !== filters.value.lastResult) return false
    if (!kw) return true
    return [r.id, r.name, r.table, r.field].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 维度辅助 ---- */
function dimOf(code: string): QcDim | undefined {
  return dims.value.find((d) => d.code === code)
}
function dimCnt(code: string): number {
  return rules.value.filter((r) => r.dim === code).length
}
function toggleDim(code: string) {
  filters.value.dim = filters.value.dim === code ? '' : code
}
function objOf(r: QcRule): string {
  return r.field && r.field !== '-' ? `${r.table}.${r.field}` : r.table
}
function dimTagStyle(code: string): Record<string, string> {
  const d = dimOf(code)
  const c = d?.color ?? '#1668dc'
  return { background: c + '18', color: c }
}

/* ---- 状态徽标 ---- */
const EXTRA_ST: Record<string, { label: string; cls: string }> = {
  fail: { label: '失败', cls: 'st-red' },
}
function stCls(s: string): string {
  return ST[s]?.cls ?? EXTRA_ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? EXTRA_ST[s]?.label ?? s
}
function levelCls(level: string): string {
  return level === '强规则' ? 'err' : 'warn'
}

/* ---- 规则详情 ---- */
const detailVisible = ref(false)
const detail = ref<QcRule | null>(null)

function openDetail(r: QcRule) {
  detail.value = r
  detailVisible.value = true
}

/* ---- 试跑（抽样，不写结果） ---- */
const testVisible = ref(false)
const testInfo = ref<{ name: string; pass: boolean; rows: number } | null>(null)

function runTest(r: QcRule) {
  ElMessage.info(`正在试跑规则「${r.name}」...`)
  window.setTimeout(() => {
    const pass = r.lastResult !== 'fail'
    testInfo.value = { name: r.name, pass, rows: pass ? 0 : Math.floor(2 + Math.random() * 10) }
    testVisible.value = true
  }, 900)
}

/* ---- 新建 / 编辑 ---- */
const formVisible = ref(false)
const editing = ref<QcRule | null>(null)
const drawerTitle = computed(() => (editing.value ? `编辑规则 - ${editing.value.name}` : '新建质量规则'))
const form = ref({ name: '', table: '', field: '', dim: 'COMPLETENESS', type: '', threshold: '', level: '强规则' })

function openCreate() {
  editing.value = null
  form.value = { name: '', table: tables.value[0]?.name ?? '', field: '', dim: 'COMPLETENESS', type: '', threshold: '', level: '强规则' }
  formVisible.value = true
}

function openEdit(r: QcRule) {
  editing.value = r
  form.value = { name: r.name, table: r.table, field: r.field, dim: r.dim, type: r.type, threshold: r.threshold, level: r.level }
  formVisible.value = true
}

function nextRuleId(): string {
  let max = 40
  for (const r of rules.value) {
    const n = Number(r.id.replace(/\D/g, ''))
    if (Number.isFinite(n) && n > max) max = n
  }
  return 'QC-R-0' + (max + 1)
}

async function saveForm() {
  const name = form.value.name.trim()
  const threshold = form.value.threshold.trim()
  if (!name || !threshold) {
    ElMessage.warning('请填写规则名称与阈值')
    return
  }
  if (editing.value) {
    Object.assign(editing.value, {
      name, table: form.value.table, field: form.value.field || '-', dim: form.value.dim,
      type: form.value.type, threshold, level: form.value.level,
    })
    await dataStore.save('qcRules', editing.value)
    ElMessage.success('规则已保存')
  } else {
    const rule: QcRule = {
      id: nextRuleId(), name, table: form.value.table, field: form.value.field || '-',
      dim: form.value.dim, type: form.value.type || '自定义', threshold, level: form.value.level,
      status: 'enabled', owner: owner.value, lastResult: 'pass', linkTask: '-',
    }
    await dataStore.save('qcRules', rule)
    ElMessage.success('规则已创建并启用')
  }
  formVisible.value = false
  await reload()
}

/* ---- 从模板创建 ---- */
interface QcTpl {
  name: string
  dim: string
  desc: string
}
const TEMPLATES: QcTpl[] = [
  { name: '空值检查', dim: 'COMPLETENESS', desc: '字段空值率 ≤ 阈值' },
  { name: '行数波动', dim: 'COMPLETENESS', desc: '日环比波动 ≤ ±30%' },
  { name: '记录数比对', dim: 'COMPLETENESS', desc: '与源表行数差 = 0' },
  { name: '范围检查', dim: 'ACCURACY', desc: '值域 [min, max]' },
  { name: '业务规则', dim: 'ACCURACY', desc: 'SQL表达式校验' },
  { name: '精度比对', dim: 'ACCURACY', desc: '与源聚合值差 ≤ ε' },
  { name: '跨表一致性', dim: 'CONSISTENCY', desc: '两表聚合差 ≤ ε' },
  { name: '枚举值比对', dim: 'CONSISTENCY', desc: '值域集合一致' },
  { name: 'SLA检查', dim: 'TIMELINESS', desc: 'DDL 时间内产出' },
  { name: '主键唯一', dim: 'UNIQUENESS', desc: '重复数 = 0' },
  { name: '联合唯一', dim: 'UNIQUENESS', desc: '组合键重复 = 0' },
  { name: '格式正则', dim: 'VALIDITY', desc: '匹配 ^regex$' },
  { name: '枚举检查', dim: 'VALIDITY', desc: '值域 ∈ {…}' },
  { name: '长度检查', dim: 'VALIDITY', desc: '长度 ≤ max' },
  { name: '引用完整性', dim: 'VALIDITY', desc: '外键值存在于维表' },
]
const tplVisible = ref(false)

function openFromTpl(tpl: QcTpl) {
  tplVisible.value = false
  editing.value = null
  form.value = {
    name: `${tables.value[0]?.name ?? ''} ${tpl.name}`,
    table: tables.value[0]?.name ?? '',
    field: '',
    dim: tpl.dim,
    type: tpl.name,
    threshold: '',
    level: '强规则',
  }
  formVisible.value = true
}

/* ---- 启停用 / 删除 ---- */
async function toggleStatus(r: QcRule) {
  r.status = r.status === 'enabled' ? 'disabled' : 'enabled'
  await dataStore.save('qcRules', r)
  ElMessage.success(r.status === 'enabled' ? `规则「${r.name}」已启用` : `规则「${r.name}」已停用`)
}

async function removeRule(r: QcRule) {
  if (r.builtin) {
    ElMessage.warning('预制规则为系统内置，不可删除；如需停用请使用「停用」')
    return
  }
  if (r.linkTask && r.linkTask !== '-') {
    ElMessageBox.alert(`规则「${r.name}」已被检查任务 ${r.linkTask} 编排，请先在检查任务中移除该规则。`, '无法删除', {
      confirmButtonText: '知道了', type: 'warning',
    })
    return
  }
  try {
    await ElMessageBox.confirm(`确认删除规则「${r.name}」？该操作不可恢复。`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  await dataStore.remove('qcRules', r.id)
  ElMessage.success('规则已删除')
  await reload()
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索规则/表/字段"
      :result-count="filtered.length"
      :total-count="rules.length"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部工具栏按钮 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">质量规则</div>
        <div class="ph-desc">六维规则模板建规则：完整性/准确性/一致性/及时性/唯一性/有效性；强规则失败阻断下游，弱规则告警不阻断</div>
      </div>
      <div class="ph-acts">
        <button class="tb-new" @click="openCreate">+ 新建规则</button>
        <button class="op-btn" @click="tplVisible = true">从模板创建</button>
      </div>
    </div>

    <!-- 六维统计卡（点击筛选） -->
    <div class="dim-cards">
      <button v-for="d in dims" :key="d.code" class="card stat-card" :class="{ on: filters.dim === d.code }" @click="toggleDim(d.code)">
        <span class="sc-icon" :style="{ background: d.color }">{{ d.icon }}</span>
        <div>
          <div class="stat-num">{{ dimCnt(d.code) }}</div>
          <div class="stat-label">{{ d.name }}</div>
        </div>
      </button>
    </div>

    <!-- 规则列表 -->
    <div class="card panel">
      <div class="tbl-toolbar">
        <span class="sec-head">规则列表</span>
        <span class="pill info">{{ filtered.length }} / {{ rules.length }}</span>
        <span class="spacer" />
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>规则</th><th>检核对象</th><th>阈值</th><th>级别</th><th>最近结果</th><th>状态</th><th>负责人</th>
            <th style="width:250px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td>
              <a @click="openDetail(r)"><b>{{ r.name }}</b></a>
              <span v-if="r.builtin" class="pill purple" style="margin-left:6px;font-size:10px">预制</span>
              <div style="font-size:11px;color:var(--text-3)">{{ r.id }} · {{ dimOf(r.dim)?.name ?? r.dim }} · {{ r.type }}</div>
            </td>
            <td><span class="mono" style="font-size:11.5px">{{ objOf(r) }}</span></td>
            <td style="font-size:11.5px">{{ r.threshold }}</td>
            <td>
              <span class="pill" :class="levelCls(r.level)">{{ r.level }}</span>
            </td>
            <td><span class="st" :class="stCls(r.lastResult)"><span class="dot" />{{ stLabel(r.lastResult) }}</span></td>
            <td><span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span></td>
            <td>{{ r.owner }}</td>
            <td>
              <button class="op-btn primary" @click="openDetail(r)">详情</button>
              <button class="op-btn" @click="runTest(r)">试跑</button>
              <button class="op-btn" @click="openEdit(r)">编辑</button>
              <button class="op-btn" @click="toggleStatus(r)">{{ r.status === 'enabled' ? '停用' : '启用' }}</button>
              <button class="op-btn danger" :disabled="r.builtin" :title="r.builtin ? '预制规则不可删除' : ''" @click="removeRule(r)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的质量规则，请调整筛选条件</div>
    </div>

    <!-- 规则详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detail ? `规则详情 - ${detail.name}` : ''" width="560px">
      <template v-if="detail">
        <div class="desc-grid">
          <div class="d-row"><span class="d-k">编号</span><span class="mono">{{ detail.id }}</span></div>
          <div class="d-row"><span class="d-k">维度</span>
            <span><span class="tag" :style="dimTagStyle(detail.dim)">{{ dimOf(detail.dim)?.name ?? detail.dim }}</span></span>
          </div>
          <div class="d-row"><span class="d-k">检查类型</span><span>{{ detail.type }}</span></div>
          <div class="d-row"><span class="d-k">检核对象</span><span class="mono">{{ objOf(detail) }}</span></div>
          <div class="d-row"><span class="d-k">阈值</span><span>{{ detail.threshold }}</span></div>
          <div v-if="detail.pattern" class="d-row"><span class="d-k">校验正则</span><span class="mono">{{ detail.pattern }}</span></div>
          <div class="d-row"><span class="d-k">来源</span><span>{{ detail.builtin ? '系统预制（可停用不可删除）' : '用户自定义' }}</span></div>
          <div class="d-row"><span class="d-k">级别</span>
            <span><span class="pill" :class="levelCls(detail.level)">{{ detail.level }}</span></span>
          </div>
          <div class="d-row"><span class="d-k">状态</span>
            <span><span class="st" :class="stCls(detail.status)"><span class="dot" />{{ stLabel(detail.status) }}</span></span>
          </div>
          <div class="d-row"><span class="d-k">最近结果</span>
            <span><span class="st" :class="stCls(detail.lastResult)"><span class="dot" />{{ stLabel(detail.lastResult) }}</span></span>
          </div>
          <div class="d-row"><span class="d-k">联动检查任务</span><span class="mono">{{ detail.linkTask }}</span></div>
          <div class="d-row"><span class="d-k">负责人</span><span>{{ detail.owner }}</span></div>
        </div>
        <div class="lock-tip">强规则失败将阻断 ETL 下游节点并即时告警；弱规则失败仅生成异常单。</div>
      </template>
    </el-dialog>

    <!-- 试跑结果弹窗 -->
    <el-dialog v-model="testVisible" :title="testInfo ? `试跑结果 - ${testInfo.name}` : ''" width="420px">
      <template v-if="testInfo">
        <div class="checker-line" :class="testInfo.pass ? 'ok' : 'err'">
          <span>{{ testInfo.pass ? '✓' : '✗' }}</span>
          <b>{{ testInfo.pass ? '校验通过' : '校验失败' }}</b>
          <span style="margin-left:auto">{{ testInfo.pass ? '0 行异常' : `异常 ${testInfo.rows} 行` }}</span>
        </div>
        <div class="lock-tip">试跑仅抽样当前分区，不写入结果与异常单；正式检查由检查任务调度执行。</div>
      </template>
    </el-dialog>

    <!-- 规则模板库 -->
    <el-dialog v-model="tplVisible" title="规则模板库（六维）" width="720px">
      <div class="tpl-grid">
        <button v-for="t in TEMPLATES" :key="t.name" class="card tpl-card" @click="openFromTpl(t)">
          <span class="sc-icon" :style="{ background: dimOf(t.dim)?.color ?? '#1668dc' }">{{ dimOf(t.dim)?.icon ?? '✓' }}</span>
          <div style="text-align:left">
            <b style="font-size:12.5px">{{ t.name }}</b>
            <div style="font-size:11px;color:var(--text-3)">{{ t.desc }}</div>
          </div>
        </button>
      </div>
    </el-dialog>

    <!-- 新建 / 编辑抽屉 -->
    <el-drawer v-model="formVisible" :title="drawerTitle" size="460px">
      <div class="form-grid">
        <label class="f-item">规则名称 *
          <input v-model="form.name" class="kw" style="width:100%" placeholder="如：用户表主键唯一性" />
        </label>
        <label class="f-item">检核表
          <select v-model="form.table" class="kw" style="width:100%">
            <option v-for="t in tables" :key="t.id" :value="t.name">{{ t.name }}</option>
          </select>
        </label>
        <label class="f-item">检核字段
          <input v-model="form.field" class="kw" style="width:100%" placeholder="及时性/行数类可留空，默认 -" />
        </label>
        <label class="f-item">质量维度
          <select v-model="form.dim" class="kw" style="width:100%">
            <option v-for="d in dims" :key="d.code" :value="d.code">{{ d.name }}</option>
          </select>
        </label>
        <label class="f-item">检查类型
          <input v-model="form.type" class="kw" style="width:100%" placeholder="如：唯一性检查 / 空值检查" />
        </label>
        <label class="f-item">阈值 *
          <input v-model="form.threshold" class="kw" style="width:100%" placeholder="如：空值率 ≤ 1%" />
        </label>
        <div class="f-item">规则级别
          <div class="radio-col">
            <label class="radio-line"><input v-model="form.level" type="radio" value="强规则" />强规则（失败阻断下游）</label>
            <label class="radio-line"><input v-model="form.level" type="radio" value="弱规则" />弱规则（告警不阻断）</label>
          </div>
        </div>
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
.page-head{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;margin-bottom:14px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-2);margin-top:3px}
.ph-acts{margin-left:auto;display:flex;gap:8px;flex-shrink:0}
.dim-cards{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:14px}
.stat-card{display:flex;align-items:center;gap:10px;padding:12px 13px;cursor:pointer;text-align:left;font:inherit;color:inherit}
.stat-card.on{border-color:var(--primary);box-shadow:0 0 0 2px rgba(22,104,220,.12)}
.sc-icon{width:30px;height:30px;border-radius:var(--radius);color:#fff;font-size:14px;display:inline-flex;align-items:center;justify-content:center;flex-shrink:0}
.stat-num{font-size:19px;font-weight:700;line-height:1.2}
.stat-label{font-size:11.5px;color:var(--text-3)}
.panel{padding:14px 16px}
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.tbl-toolbar .spacer{flex:1}
.pill{display:inline-flex;align-items:center;gap:5px;padding:1px 9px;border-radius:var(--radius-lg);font-size:11px;font-weight:500}
.pill.err{background:var(--danger-bg);color:var(--danger)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.info{background:var(--info-bg);color:var(--info)}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.tag{display:inline-block;border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600}
.lock-tip{margin-top:12px;border-left:3px solid var(--warn);background:var(--warn-bg);color:var(--warn);font-size:11.5px;padding:7px 10px;border-radius:0 7px 7px 0}
.desc-grid{display:flex;flex-direction:column}
.d-row{display:flex;gap:12px;padding:6px 0;border-bottom:1px dashed var(--border);font-size:12.5px}
.d-k{width:96px;color:var(--text-3);flex-shrink:0}
.checker-line{display:flex;align-items:center;gap:10px;border:1px solid var(--border);border-radius:var(--radius);padding:10px 12px;font-size:12.5px}
.checker-line.ok{border-color:rgba(22,163,74,.4);color:var(--success)}
.checker-line.err{border-color:rgba(229,72,77,.4);color:var(--danger)}
.tpl-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.tpl-card{display:flex;align-items:center;gap:10px;padding:10px 12px;cursor:pointer;font:inherit;color:inherit}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.radio-col{display:flex;flex-direction:column;gap:6px}
.radio-line{display:flex;gap:7px;align-items:center;font-size:12.5px;color:var(--text);cursor:pointer}
</style>
