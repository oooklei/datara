<script setup lang="ts">
/**
 * M05 批处理 ETL 任务（todo 15）
 * 对齐 prototype/assets/pages/m05-batch.js `#/etl/list`（L316-367）：
 * 任务表格（关键字 + 类型/状态筛选）；顶部工具栏：搜索 + 筛选 + 新建ETL任务；
 * 行操作：设计(/etl/design/:id) / 运行 / 发布·下线 / 删除（dataStore.save/remove 持久化 + ElMessage 反馈）。
 * 新建表单的目标产出表取自 dataStore.models。
 * F56d 双态：real 走 listDefinitions({ tag: ETL_TAG })（保存自动打「ETL」标签的定义）；
 * 行缺失字段显示 '-'，删除/新建按 DagListView real 同款接后端，运行/发布为 mock 演示动作 real 下禁用。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { isMock, listDefinitions, createDefinition, deleteDefinition, ETL_TAG } from '../../services'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { DbUser, EtlTask, Model } from '../../services/types'

const router = useRouter()

const props = defineProps<{ embed?: boolean }>()
const emit = defineEmits<{ (e: 'open', id: string): void }>()
const rows = ref<EtlTask[]>([])
const models = ref<Model[]>([])
const user = ref<DbUser | null>(null)

const keyword = ref('')
const filters = ref<Record<string, string>>({ type: '', status: '' })

const typeOptions = ['可视化ETL', 'SQL任务', '脚本任务']
/* F56d：状态筛选随双态 —— mock 为草稿/发布，real 为定义上线态（releaseState） */
const statusOptions = isMock
  ? [
      { v: 'published', t: '已发布' },
      { v: 'draft', t: '草稿' },
    ]
  : [
      { v: 'online', t: '已上线' },
      { v: 'offline', t: '已下线' },
    ]

const facets = [
  { key: 'type', label: '类型', options: typeOptions.map((t) => ({ v: t, t })) },
  { key: 'status', label: '状态', options: statusOptions },
]

const filtered = computed<EtlTask[]>(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.type && r.type !== filters.value.type) return false
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.name, r.code, r.type, r.owner].some((s) => s.toLowerCase().includes(kw))
  })
})

async function reload() {
  if (isMock) {
    // 必须展开为新数组：dataStore.save 原地修改数组，list 返回同一引用，
    // 直接赋值不会触发 ref 更新（filtered 计算属性会停留在旧值）。
    rows.value = [...((await dataStore.list<EtlTask>('etlTasks')) ?? [])]
    return
  }
  /* F56d real：打「ETL」标签的工作流定义（画布 meta.profile==='etl' 保存自动打标）；
     编码/最近运行为 mock 专有字段，缺失显示 '-'；上线态原样展示（ST 徽标） */
  try {
    const defs = await listDefinitions({ tag: ETL_TAG })
    rows.value = defs.map((d) => ({
      id: d.id,
      name: d.name,
      code: '-',
      type: '可视化ETL',
      status: d.status ?? 'offline',
      owner: d.owner ?? '-',
      cron: d.cron && d.cron !== '-' ? d.cron : '',
      lastRun: '-',
      updatedAt: d.updatedAt,
    }))
  } catch (e) {
    ElMessage.error('ETL任务列表加载失败：' + errMsg(e) + '（检查后端服务与登录态）')
  }
}

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

onMounted(async () => {
  await reload()
  if (!isMock) return
  models.value = (await dataStore.list<Model>('models')) ?? []
  user.value = await dataStore.get<DbUser>('user')
})

/* ---- ST 徽标 / 类型配色 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
const typeColors: Record<string, string> = { 可视化ETL: '#1668dc', SQL任务: '#0891b2', 脚本任务: '#7c3aed' }
function typeStyle(t: string): { background: string; color: string } {
  const c = typeColors[t] ?? '#64748b'
  return { background: c + '22', color: c }
}

/* ---- 行操作 ---- */
function goDesign(r: EtlTask) {
  /* embed（任务中心「看列表」弹窗）：行内「可视化编排」不跳路由，emit 由任务中心切换内嵌画布 */
  if (props.embed) { emit('open', r.id); return }
  /* /etl/design/:id 路由已移除（I1 意见③）：独立入口统一落任务中心 ETL 视角 */
  router.push('/dag?tab=etl')
}

const running = ref(false)
function runTask(r: EtlTask) {
  /* F56d：演示运行为 mock 专有动作，real 由工作流引擎执行（运行实例见 /dag/instances） */
  if (!isMock) { ElMessage.info('任务运行由工作流引擎执行，real 模式不提供演示运行'); return }
  if (running.value) return
  running.value = true
  ElMessage.info(`任务「${r.name}」提交运行 ...`)
  setTimeout(async () => {
    r.lastRun = 'success'
    await dataStore.save<EtlTask>('etlTasks', r)
    await reload()
    running.value = false
    ElMessage.success('任务运行成功，产出表已注册血缘')
  }, 1200)
}

async function togglePub(r: EtlTask) {
  /* F56d：发布/下线为 mock 演示动作，real 无对应后端动作，禁用 */
  if (!isMock) { ElMessage.info('发布/下线为 mock 演示动作，real 模式不提供'); return }
  if (r.status === 'published') {
    r.status = 'draft'
    await dataStore.save<EtlTask>('etlTasks', r)
    await reload()
    ElMessage.info('任务已下线（草稿态）')
  } else {
    r.status = 'published'
    await dataStore.save<EtlTask>('etlTasks', r)
    await reload()
    ElMessage.success('任务已发布，可被DAG工作流引用')
  }
}

async function removeRow(r: EtlTask) {
  try {
    await ElMessageBox.confirm(`确认删除任务「${r.name}」？该操作不可恢复。`, '删除确认', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  /* F56d real：删除走后端（对齐 DagListView real 分支）；版本历史一并删除 */
  if (!isMock) {
    try {
      await deleteDefinition(r.id)
      rows.value = rows.value.filter((x) => x.id !== r.id)
      ElMessage.success(`ETL任务「${r.name}」已删除`)
    } catch (e) {
      ElMessage.error('删除失败：' + errMsg(e))
    }
    return
  }
  await dataStore.remove('etlTasks', r.id)
  ElMessage.success('已删除')
  await reload()
}

/* ---- 新建 ETL 任务 ---- */
const createVisible = ref(false)
const cName = ref('')
const cCode = ref('etl_')
const cType = ref('sql')
const cOut = ref('dwd_order_pay_detail')

function openCreate() {
  cName.value = ''
  cCode.value = 'etl_'
  cType.value = 'sql'
  cOut.value = models.value[0]?.code ?? 'dwd_order_pay_detail'
  createVisible.value = true
}

function nowMinute(): string {
  const d = new Date()
  const p = (x: number) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

async function saveCreate() {
  if (!cName.value.trim()) {
    ElMessage.warning('请填写任务名称')
    return
  }
  /* F56d real：对齐 DagListView real 分支 —— createDefinition 落库（编码/类型/产出表为 mock 专有字段） */
  if (!isMock) {
    try {
      const created = await createDefinition(cName.value.trim())
      createVisible.value = false
      ElMessage.success('ETL任务已创建（后端落库），进入画布编排后保存自动打「ETL」标签')
      await reload()
      if (props.embed) emit('open', created.id)
      else router.push('/dag?tab=etl')
    } catch (e) {
      ElMessage.error('创建失败：' + errMsg(e))
    }
    return
  }
  if (!cCode.value.trim()) {
    ElMessage.warning('请填写任务编码')
    return
  }
  const all = (await dataStore.list<EtlTask>('etlTasks')) ?? []
  const maxN = all.reduce((m, r) => {
    const n = parseInt(r.id.replace(/\D/g, ''), 10)
    return Number.isFinite(n) && n > m ? n : m
  }, 0)
  const task: EtlTask = {
    id: `ETL${String(maxN + 1).padStart(3, '0')}`,
    name: cName.value.trim(),
    code: cCode.value.trim(),
    type: cType.value === 'etl' ? '可视化ETL' : cType.value === 'sql' ? 'SQL任务' : '脚本任务',
    status: 'draft',
    owner: user.value?.name ?? '王工',
    cron: '',
    lastRun: '-',
    updatedAt: nowMinute(),
    sql: cType.value === 'sql' ? '-- 编写SQL\nSELECT 1;' : undefined,
    scriptLang: cType.value === 'script' ? 'Python' : undefined,
  }
  await dataStore.save<EtlTask>('etlTasks', task)
  createVisible.value = false
  ElMessage.success('ETL任务已创建（草稿），可进入设计器编排')
  await reload()
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      :result-count="filtered.length"
      :total-count="rows.length"
      placeholder="搜索任务名称/编码"
    />
    <div style="flex:1;min-width:0">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">批处理 ETL 任务</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
        <button class="tb-new" @click="openCreate">＋ 新建ETL任务</button>
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>任务</th><th>类型</th><th>调度</th><th>最近运行</th><th>负责人</th><th>状态</th><th style="width:220px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td>
              <a @click="goDesign(r)"><b>{{ r.name }}</b></a>
              <div class="mono" style="font-size:11px;color:var(--text-3)">{{ r.code }}</div>
            </td>
            <td><span class="tag" :style="typeStyle(r.type)">{{ r.type }}</span></td>
            <td>
              <span v-if="r.cron" class="mono">{{ r.cron }}</span>
              <span v-else style="color:var(--text-3)">未配置</span>
            </td>
            <td>
              <span v-if="r.lastRun === '-'" style="color:var(--text-3)">-</span>
              <span v-else class="st" :class="stCls(r.lastRun)"><span class="dot" />{{ stLabel(r.lastRun) }}</span>
            </td>
            <td>{{ r.owner }}</td>
            <td><span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span></td>
            <td>
              <button class="op-btn primary" @click="goDesign(r)">可视化编排</button>
              <button class="op-btn" @click="runTask(r)">运行</button>
              <button class="op-btn" @click="togglePub(r)">{{ r.status === 'published' ? '下线' : '发布' }}</button>
              <button class="op-btn danger" @click="removeRow(r)">删除</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="filtered.length === 0" class="empty">未找到匹配的 ETL 任务，请调整筛选条件</div>
    </div>
    </div>

    <!-- 新建 ETL 任务 -->
    <el-dialog v-model="createVisible" title="新建ETL任务" width="520px">
      <div class="form-grid">
        <div class="field">
          <label>任务名称 <i class="req">*</i></label>
          <input v-model="cName" placeholder="如：清洗支付明细" />
        </div>
        <div class="field">
          <label>任务编码 <i class="req">*</i></label>
          <input v-model="cCode" />
          <div class="f-help">命名规范 NR-06：etl_[目标表]_[动作]</div>
        </div>
        <div class="field">
          <label>任务类型</label>
          <div class="radio-row">
            <label class="radio-item"><input v-model="cType" type="radio" value="etl" />可视化ETL</label>
            <label class="radio-item"><input v-model="cType" type="radio" value="sql" />SQL任务</label>
            <label class="radio-item"><input v-model="cType" type="radio" value="script" />脚本任务（Python/Shell）</label>
          </div>
        </div>
        <div class="field">
          <label>目标产出表</label>
          <select v-model="cOut">
            <option v-for="m in models" :key="m.code" :value="m.code">{{ m.code }}</option>
          </select>
        </div>
      </div>
      <template #footer>
        <button class="op-btn" @click="createVisible = false">取消</button>
        <button class="tb-new" @click="saveCreate">创建</button>
      </template>
    </el-dialog>
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
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.tag{display:inline-block;border-radius:4px;padding:1px 8px;font-size:11.5px;font-weight:600}
.form-grid{display:flex;flex-direction:column;gap:12px}
.field label{display:block;font-size:12px;color:var(--text-2);margin-bottom:4px;font-weight:600}
.field input,.field select{width:100%;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:7px 10px;font-size:12.5px;outline:none;background:#fff;color:var(--text)}
.field input:focus,.field select:focus{border-color:var(--primary)}
.f-help{font-size:11px;color:var(--text-3);margin-top:4px}
.req{color:var(--danger);font-style:normal}
.radio-row{display:flex;gap:16px;flex-wrap:wrap}
.radio-item{display:flex;gap:5px;align-items:center;font-size:12.5px;color:var(--text);font-weight:400;cursor:pointer}
</style>
