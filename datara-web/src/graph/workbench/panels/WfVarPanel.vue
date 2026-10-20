<script setup lang="ts">
/**
 * WfVarPanel：DAG 工作台「变量」页签 —— 统一变量体系（R2 换绑，FE-05）。
 * - 七级优先级链 UI（run > task > workflow > project > global > env > builtin，设计真源，收窄须用户批准）
 * - 数据源：variableApi（/api/v1/rebuild/variables），替换旧协议 /workflow-variables
 * - 可持久化 scope：global/project/tmp（后端 PERSISTABLE_SCOPES）；workflow scope 只读展示
 * - 复制到其他工作流：用 variableApi.saveVariable 实现（仅复制值、不跨工作流共享引用）
 * - 无删除功能（后端 variables 域无 delete 端点）
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { createVariableContract, VARIABLE_SCOPE_PRIORITY } from '../../../services/rebuild/variableApi'
import type { VariableDefinition, VariableScope, VariableValueType } from '../../../services/rebuild/variableApi'
import { useAuthStore } from '../../../stores/auth'

const props = defineProps<{ docId: string }>()
const auth = useAuthStore()

const contract = createVariableContract()
const DEFAULT_PROJECT_ID = 1

/** 七级优先级链（设计真源，收窄须用户批准） */
const scopePriority = VARIABLE_SCOPE_PRIORITY

/** 可持久化 scope（后端 PERSISTABLE_SCOPES） */
const PERSISTABLE_SCOPES: readonly VariableScope[] = ['global', 'project', 'tmp']

/** 变量列表 */
const allVars = ref<VariableDefinition[]>([])

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

async function reload() {
  try {
    allVars.value = await contract.listVariables(DEFAULT_PROJECT_ID)
  } catch (e) {
    ElMessage.error('变量加载失败：' + errMsg(e) + '（检查后端服务与登录态）')
  }
}

onMounted(reload)

/* ---- 按 scope 分组 ---- */
const varsByScope = computed(() => {
  const map = new Map<VariableScope, VariableDefinition[]>()
  for (const scope of scopePriority) {
    map.set(scope, [])
  }
  for (const v of allVars.value) {
    const list = map.get(v.scope)
    if (list) list.push(v)
  }
  return map
})

/* ---- 类型徽标 ---- */
const typeCls: Record<VariableValueType, string> = {
  string: 'info', integer: 'purple', decimal: 'purple', boolean: 'warn',
  date: 'deny', datetime: 'deny', json: 'deny', array: 'deny',
}

/** 变量引用写法（统一语法 ${scope.name}） */
function refOf(v: VariableDefinition): string {
  return `\${${v.scope}.${v.name}}`
}

/** scope 是否可编辑（可持久化） */
function isEditable(scope: VariableScope): boolean {
  return PERSISTABLE_SCOPES.includes(scope)
}

/* ---- 新建 / 编辑 ---- */
const editVisible = ref(false)
const editing = ref<VariableDefinition | null>(null)
const form = ref({
  scope: 'global' as VariableScope,
  name: '',
  valueType: 'string' as VariableValueType,
  value: '',
  sensitive: false,
  description: '',
})

function openCreate() {
  editing.value = null
  form.value = { scope: 'global', name: '', valueType: 'string', value: '', sensitive: false, description: '' }
  editVisible.value = true
}

function openEdit(v: VariableDefinition) {
  editing.value = v
  form.value = {
    scope: v.scope,
    name: v.name,
    valueType: v.valueType,
    value: v.value,
    sensitive: !!v.sensitive,
    description: v.description ?? '',
  }
  editVisible.value = true
}

async function saveEdit() {
  const name = form.value.name.trim()
  if (!name) {
    ElMessage.warning('请填写变量名')
    return
  }
  const dup = allVars.value.some((v) => v.name === name && v.scope === form.value.scope && v !== editing.value)
  if (dup) {
    ElMessage.warning(`变量名「${name}」在 ${form.value.scope} 作用域已存在`)
    return
  }
  try {
    await contract.saveVariable(DEFAULT_PROJECT_ID, {
      scope: form.value.scope,
      name,
      valueType: form.value.valueType,
      value: form.value.value,
      sensitive: form.value.sensitive,
      description: form.value.description.trim() || undefined,
    })
    ElMessage.success(`变量「${name}」已保存`)
  } catch (e) {
    ElMessage.error('保存失败：' + errMsg(e))
    return
  }
  editVisible.value = false
  await reload()
}

/* ---- 复制到其他工作流（仅复制值、不跨工作流共享引用） ---- */
const copyVisible = ref(false)
const copyTarget = ref('')
const copyStrategy = ref<'skip' | 'overwrite' | 'rename'>('skip')

interface WfOpt { id: string; name: string }
const wfOptions = ref<WfOpt[]>([])

/** 真实工作流清单：localStorage datara.graph.* 持久化文档 */
function scanPersistedWfDocs(): WfOpt[] {
  const out: WfOpt[] = []
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const k = localStorage.key(i)
      const m = k ? /^datara\.graph\.([^.]+)$/.exec(k) : null
      if (!k || !m) continue
      const raw = localStorage.getItem(k)
      if (!raw) continue
      const doc = JSON.parse(raw) as { id?: string; name?: string; meta?: { profile?: string } }
      if (doc?.id && doc?.meta?.profile === 'dag') out.push({ id: doc.id, name: doc.name ?? doc.id })
    }
  } catch { /* 私有模式等忽略 */ }
  return out
}

async function openCopy() {
  if (allVars.value.length === 0) {
    ElMessage.warning('当前暂无变量可复制')
    return
  }
  /* real：目标工作流清单 = localStorage 持久化文档 */
  const seen = new Map<string, string>()
  for (const o of scanPersistedWfDocs()) {
    if (!seen.has(o.id)) seen.set(o.id, o.name)
  }
  wfOptions.value = [...seen.entries()]
    .filter(([id]) => id !== props.docId)
    .map(([id, name]) => ({ id, name }))
  if (wfOptions.value.length === 0) {
    ElMessage.info('暂无其他工作流')
    return
  }
  copyTarget.value = wfOptions.value[0]!.id
  copyStrategy.value = 'skip'
  copyVisible.value = true
}

/** 复制预览：按冲突策略归类 */
const copyPreview = computed(() => {
  return allVars.value.map((v) => {
    const action = copyStrategy.value === 'skip' ? '跳过' : copyStrategy.value === 'overwrite' ? '覆盖' : '重命名'
    const newName = copyStrategy.value === 'rename' ? `${v.name}_${copyTarget.value.replace(/^wf_/, '')}` : v.name
    return { v, action, newName }
  })
})

async function doCopy() {
  const target = copyTarget.value
  if (!target) return
  let copied = 0
  let skipped = 0
  for (const p of copyPreview.value) {
    if (p.action === '跳过') { skipped++; continue }
    try {
      await contract.saveVariable(DEFAULT_PROJECT_ID, {
        scope: p.v.scope,
        name: p.newName,
        valueType: p.v.valueType,
        value: p.v.value,
        sensitive: p.v.sensitive,
        description: p.v.description,
      })
      copied++
    } catch (e) {
      ElMessage.error(`复制「${p.v.name}」失败：` + errMsg(e))
      return
    }
  }
  copyVisible.value = false
  ElMessage.success(`已复制 ${copied} 个变量${skipped ? `（跳过 ${skipped} 个冲突）` : ''}；仅复制值，不跨工作流共享引用`)
}
</script>

<template>
  <div class="wvp">
    <div class="wvp-bar">
      <span class="wvp-title">统一变量</span>
      <span class="pill info">{{ allVars.length }} 个</span>
      <span class="wvp-hint">节点参数中以 <span class="mono">${scope.name}</span> 引用；七级优先级：run &gt; task &gt; workflow &gt; project &gt; global &gt; env &gt; builtin</span>
      <span class="spacer" />
      <template v-if="auth.canEdit">
        <button class="op-btn" @click="openCopy">⧉ 复制到其他工作流</button>
        <button class="tb-new" @click="openCreate">+ 新建变量</button>
      </template>
      <span v-else class="pill off">只读</span>
    </div>

    <!-- 七级优先级链展示 -->
    <div class="scope-chain">
      <span v-for="(scope, i) in scopePriority" :key="scope" class="scope-node">
        <span class="scope-name" :class="{ editable: isEditable(scope) }">{{ scope }}</span>
        <span v-if="i < scopePriority.length - 1" class="scope-arrow">&gt;</span>
      </span>
    </div>

    <!-- 按 scope 分组显示变量 -->
    <div v-for="scope in scopePriority" :key="scope" class="scope-group">
      <div class="scope-header">
        <span class="scope-badge" :class="{ editable: isEditable(scope) }">{{ scope }}</span>
        <span class="scope-count">{{ varsByScope.get(scope)?.length ?? 0 }} 个</span>
        <span v-if="isEditable(scope)" class="scope-action">可编辑</span>
        <span v-else class="scope-readonly">只读</span>
      </div>
      <table v-if="varsByScope.get(scope)?.length" class="tbl">
        <thead>
          <tr><th>变量名</th><th>引用</th><th>类型</th><th>值</th><th>说明</th><th v-if="auth.canEdit && isEditable(scope)" style="width:110px">操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="v in varsByScope.get(scope)" :key="v.name">
            <td><b class="mono">{{ v.name }}</b></td>
            <td><code class="mono ref">{{ refOf(v) }}</code></td>
            <td><span class="pill" :class="typeCls[v.valueType]">{{ v.valueType }}</span></td>
            <td><span class="mono" :class="{ mask: v.sensitive }">{{ v.sensitive ? '******' : v.value }}</span></td>
            <td style="color:var(--text-2)">{{ v.description || '-' }}</td>
            <td v-if="auth.canEdit && isEditable(scope)">
              <button class="op-btn primary" @click="openEdit(v)">编辑</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-if="allVars.length === 0" class="empty">当前暂无变量，点击「+ 新建变量」创建（如 region、db_pwd 等）</div>

    <!-- 新建/编辑变量 -->
    <el-dialog v-model="editVisible" :title="editing ? `编辑变量 — ${editing.name}` : '新建变量'" width="480px">
      <div class="form-row">
        <label class="f-label">作用域<i>*</i></label>
        <select v-model="form.scope" class="f-input">
          <option v-for="s in PERSISTABLE_SCOPES" :key="s" :value="s">{{ s }}</option>
        </select>
      </div>
      <div class="form-row">
        <label class="f-label">变量名<i>*</i></label>
        <input v-model="form.name" class="f-input" placeholder="如 region（字母/数字/下划线）" />
      </div>
      <div class="form-row">
        <label class="f-label">值类型</label>
        <select v-model="form.valueType" class="f-input">
          <option v-for="t in (['string', 'integer', 'decimal', 'boolean', 'date', 'datetime', 'json', 'array'] as const)" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>
      <div class="form-row">
        <label class="f-label">值</label>
        <input v-model="form.value" class="f-input" placeholder="变量值" />
      </div>
      <div class="form-row">
        <label class="f-label">敏感</label>
        <label class="check-label"><input v-model="form.sensitive" type="checkbox" /> 敏感变量（值脱敏显示）</label>
      </div>
      <div class="form-row">
        <label class="f-label">说明</label>
        <input v-model="form.description" class="f-input" placeholder="变量用途说明（可选）" />
      </div>
      <template #footer>
        <button class="op-btn" @click="editVisible = false">取消</button>
        <button class="tb-new" @click="saveEdit">保存</button>
      </template>
    </el-dialog>

    <!-- 复制到其他工作流 -->
    <el-dialog v-model="copyVisible" title="复制变量到其他工作流" width="560px">
      <div class="copy-tip">仅复制变量值（快照），不跨工作流共享引用；目标工作流后续修改不影响源。</div>
      <div class="form-row">
        <label class="f-label">目标工作流<i>*</i></label>
        <select v-model="copyTarget" class="f-input">
          <option v-for="w in wfOptions" :key="w.id" :value="w.id">{{ w.name }}（{{ w.id }}）</option>
        </select>
      </div>
      <div class="form-row">
        <label class="f-label">同名冲突</label>
        <div class="strategy">
          <label><input v-model="copyStrategy" type="radio" value="skip" /> 跳过（保留目标值）</label>
          <label><input v-model="copyStrategy" type="radio" value="overwrite" /> 覆盖（用源值替换）</label>
          <label><input v-model="copyStrategy" type="radio" value="rename" /> 重命名后新增</label>
        </div>
      </div>
      <div class="sec-title">复制预览</div>
      <table class="tbl">
        <thead><tr><th>变量</th><th>作用域</th><th>类型</th><th>动作</th><th>目标名</th></tr></thead>
        <tbody>
          <tr v-for="p in copyPreview" :key="p.v.name">
            <td class="mono">{{ p.v.name }}</td>
            <td><span class="pill" :class="typeCls[p.v.valueType]">{{ p.v.scope }}</span></td>
            <td>{{ p.v.valueType }}</td>
            <td>{{ p.action }}</td>
            <td class="mono">{{ p.newName }}</td>
          </tr>
        </tbody>
      </table>
      <template #footer>
        <button class="op-btn" @click="copyVisible = false">取消</button>
        <button class="tb-new" @click="doCopy">确认复制</button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.wvp{padding:14px 16px}
.wvp-bar{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.wvp-title{font-weight:700;font-size:14px}
.wvp-hint{font-size:11px;color:var(--text-3)}
.spacer{flex:1}
.pill{display:inline-flex;align-items:center;padding:1px 9px;border-radius:var(--radius-lg);font-size:11px;font-weight:500}
.pill.info{background:var(--info-bg);color:var(--info)}
.pill.purple{background:#f1eaff;color:var(--purple)}
.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.deny{background:rgba(229,72,77,.1);color:var(--danger)}
.pill.off{background:var(--bg);color:var(--text-3)}
.scope-chain{display:flex;align-items:center;gap:4px;margin-bottom:12px;padding:8px 10px;background:var(--bg);border-radius:var(--radius-sm);flex-wrap:wrap}
.scope-node{display:flex;align-items:center;gap:4px}
.scope-name{font-size:11.5px;padding:2px 8px;border-radius:var(--radius-sm);background:var(--bg);border:1px solid var(--border-strong);color:var(--text-3)}
.scope-name.editable{color:var(--primary);border-color:rgba(22,104,220,.4);background:var(--primary-light)}
.scope-arrow{font-size:11px;color:var(--text-3)}
.scope-group{margin-bottom:14px}
.scope-header{display:flex;align-items:center;gap:8px;margin-bottom:4px}
.scope-badge{font-size:11.5px;font-weight:600;padding:2px 8px;border-radius:var(--radius-sm);background:var(--bg);border:1px solid var(--border-strong);color:var(--text-3)}
.scope-badge.editable{color:var(--primary);border-color:rgba(22,104,220,.4);background:var(--primary-light)}
.scope-count{font-size:11px;color:var(--text-3)}
.scope-action{font-size:10.5px;color:var(--success);background:var(--success-bg);padding:1px 6px;border-radius:var(--radius-sm)}
.scope-readonly{font-size:10.5px;color:var(--text-3);background:var(--bg);padding:1px 6px;border-radius:var(--radius-sm)}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;font-weight:600;color:var(--text-3);font-size:11.5px;padding:6px 8px;border-bottom:1px solid var(--border);white-space:nowrap}
.tbl td{padding:7px 8px;border-bottom:1px solid var(--border);vertical-align:middle}
.tbl tbody tr:hover{background:var(--bg)}
.empty{padding:28px;text-align:center;color:var(--text-3);font-size:12.5px}
.mono{font-family:ui-monospace,Consolas,monospace}
.ref{background:var(--bg);border-radius:4px;padding:1px 6px;font-size:11px;color:var(--primary)}
.mask{color:var(--text-3)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:6px 13px;font-size:12px;cursor:pointer}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.form-row{display:flex;gap:10px;margin-bottom:12px;align-items:center}
.f-label{width:86px;flex-shrink:0;font-size:12.5px;color:var(--text-2);text-align:right}
.f-label i{color:var(--danger);font-style:normal;margin-left:2px}
.f-input{flex:1;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:7px 10px;font-size:12.5px;outline:none;background:#fff;color:var(--text)}
.f-input:focus{border-color:var(--primary)}
.check-label{display:flex;align-items:center;gap:6px;font-size:12.5px;color:var(--text-2)}
.copy-tip{background:var(--info-bg);color:var(--info);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px;margin-bottom:12px}
.strategy{display:flex;gap:14px;font-size:12.5px;color:var(--text-2);flex-wrap:wrap}
.sec-title{font-weight:700;font-size:13px;margin:4px 0 8px;color:var(--text)}
</style>
