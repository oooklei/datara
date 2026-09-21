<script setup lang="ts">
/**
 * WfVarPanel：DAG 工作台「变量」页签 —— 工作流变量管理（管理与使用分离）。
 * - 增删改查当前工作流（docId）的局部变量；类型：日期/文本/数值/加密/下拉（加密值脱敏存储）。
 * - 复制到其他工作流：仅复制值、不跨工作流共享引用；同名冲突三选一（跳过/覆盖/重命名）；
 *   加密变量复制时必须重新输入明文；目标工作流下拉 = 真实工作流清单（seed + graphService 持久化）。
 * - Inspector 侧仅支持 ${var} 引用，不在此重复。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore } from '../../../services/mock/dataStore'
import { listSeedWfDocs } from '../../../services/mock/seed'
import { isMock, listVariables, saveVariable, deleteVariable, listDefinitions } from '../../../services'
import type { WfVariable } from '../../../services/types'
import { useAuthStore } from '../../../stores/auth'

const props = defineProps<{ docId: string }>()
const auth = useAuthStore()

const vars = ref<WfVariable[]>([])
const targetVars = ref<WfVariable[]>([])

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

async function reload() {
  if (isMock) {
    const all = (await dataStore.list<WfVariable>('wfVariables')) ?? []
    vars.value = all.filter((v) => v.wf === props.docId)
  } else {
    try {
      vars.value = await listVariables(props.docId)
    } catch (e) {
      ElMessage.error('变量加载失败：' + errMsg(e) + '（检查后端服务与登录态）')
    }
  }
}

onMounted(reload)

/* ---- 类型徽标 ---- */
const typeCls: Record<WfVariable['type'], string> = {
  日期: 'info', 文本: 'info', 数值: 'purple', 加密: 'deny', 下拉: 'warn',
}

/** 变量在节点参数中的引用写法（提示用） */
function refOf(v: WfVariable): string {
  return `\${${v.name}}`
}

/* ---- 新建 / 编辑 ---- */
const editVisible = ref(false)
const editing = ref<WfVariable | null>(null)
const form = ref({ name: '', type: '文本' as WfVariable['type'], value: '', options: '', desc: '' })

function nextId(rows: WfVariable[]): string {
  const max = rows.reduce((m, r) => Math.max(m, Number(r.id.replace(/\D/g, '')) || 0), 0)
  return 'WFV' + String(max + 1).padStart(3, '0')
}

function openCreate() {
  editing.value = null
  form.value = { name: '', type: '文本', value: '', options: '', desc: '' }
  editVisible.value = true
}

function openEdit(v: WfVariable) {
  editing.value = v
  form.value = { name: v.name, type: v.type, value: v.encrypted ? '' : v.value, options: v.options.join(','), desc: v.desc }
  editVisible.value = true
}

async function saveEdit() {
  const name = form.value.name.trim()
  if (!name) {
    ElMessage.warning('请填写变量名')
    return
  }
  const dup = vars.value.some((v) => v.name === name && v.id !== editing.value?.id)
  if (dup) {
    ElMessage.warning(`变量名「${name}」已存在`)
    return
  }
  const options = form.value.type === '下拉'
    ? form.value.options.split(/[,，]/).map((s) => s.trim()).filter(Boolean)
    : []
  if (form.value.type === '下拉' && options.length === 0) {
    ElMessage.warning('下拉类型需至少一个候选项（逗号分隔）')
    return
  }
  const encrypted = form.value.type === '加密'
  if (editing.value) {
    const value = encrypted
      ? (form.value.value ? '******' : editing.value.value)
      : form.value.value
    const row: WfVariable = { ...editing.value, name, type: form.value.type, value, encrypted, options, desc: form.value.desc.trim() }
    if (isMock) await dataStore.save('wfVariables', row)
    else await saveVariable(row)
    ElMessage.success(`变量「${name}」已保存`)
  } else {
    if (encrypted && !form.value.value) {
      ElMessage.warning('加密变量需填写初始值（将以脱敏形式存储）')
      return
    }
    const value = encrypted ? '******' : form.value.value
    if (isMock) {
      const all = (await dataStore.list<WfVariable>('wfVariables')) ?? []
      await dataStore.save('wfVariables', {
        id: nextId(all), wf: props.docId, name, type: form.value.type,
        value, encrypted, options, desc: form.value.desc.trim(),
      })
    } else {
      await saveVariable({
        id: '', wf: props.docId, name, type: form.value.type,
        value, encrypted, options, desc: form.value.desc.trim(),
      })
    }
    ElMessage.success(`变量「${name}」已创建，节点参数中用 ${refOf({ id: '', wf: props.docId, encrypted, ...form.value, name, options: [] } as WfVariable)} 引用`)
  }
  editVisible.value = false
  await reload()
}

async function removeVar(v: WfVariable) {
  try {
    await ElMessageBox.confirm(`删除变量「${v.name}」？引用它的节点参数将解析失败。`, '删除变量', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch {
    return
  }
  if (isMock) await dataStore.remove('wfVariables', v.id)
  else await deleteVariable(v.id)
  await reload()
  ElMessage.success(`变量「${v.name}」已删除`)
}

/* ---- 复制到其他工作流（仅复制不共享引用） ---- */
const copyVisible = ref(false)
const copyTarget = ref('')
const copyStrategy = ref<'skip' | 'overwrite' | 'rename'>('skip')
/** 加密变量复制时的明文重输（key=变量id） */
const encInputs = ref<Record<string, string>>({})

interface WfOpt { id: string; name: string }
const wfOptions = ref<WfOpt[]>([])

/** 真实工作流清单：seed dag 文档 + graphService 持久化文档（localStorage datara.graph.*） */
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
  if (vars.value.length === 0) {
    ElMessage.warning('当前工作流暂无变量可复制')
    return
  }
  if (isMock) {
    const seen = new Map<string, string>()
    for (const o of [...listSeedWfDocs(), ...scanPersistedWfDocs()]) {
      if (!seen.has(o.id)) seen.set(o.id, o.name)
    }
    wfOptions.value = [...seen.entries()]
      .filter(([id]) => id !== props.docId)
      .map(([id, name]) => ({ id, name }))
  } else {
    /* real：目标工作流清单 = 后端工作流定义列表 */
    try {
      const defs = await listDefinitions()
      wfOptions.value = defs.filter((d) => d.id !== props.docId).map((d) => ({ id: d.id, name: d.name }))
    } catch (e) {
      ElMessage.error('工作流清单加载失败：' + errMsg(e))
      return
    }
  }
  if (wfOptions.value.length === 0) {
    ElMessage.info('暂无其他工作流')
    return
  }
  copyTarget.value = wfOptions.value[0]!.id
  copyStrategy.value = 'skip'
  encInputs.value = {}
  copyVisible.value = true
  await loadTargetVars()
}

async function loadTargetVars() {
  if (isMock) {
    const all = (await dataStore.list<WfVariable>('wfVariables')) ?? []
    targetVars.value = all.filter((v) => v.wf === copyTarget.value)
  } else {
    try {
      targetVars.value = await listVariables(copyTarget.value)
    } catch {
      targetVars.value = []
    }
  }
}

/* 目标工作流切换由模板 @change="loadTargetVars" 触发加载 */

/** 复制预览：按冲突策略归类 */
const copyPreview = computed(() => {
  const targetNames = new Set(targetVars.value.map((v) => v.name))
  return vars.value.map((v) => {
    const conflict = targetNames.has(v.name)
    const action = !conflict ? '新增' : copyStrategy.value === 'skip' ? '跳过' : copyStrategy.value === 'overwrite' ? '覆盖' : '重命名'
    const newName = !conflict ? v.name : copyStrategy.value === 'rename' ? `${v.name}_${copyTarget.value.replace(/^wf_/, '')}` : v.name
    return { v, conflict, action, newName }
  })
})

const encToFill = computed(() => vars.value.filter((v) => v.encrypted))

async function doCopy() {
  const target = copyTarget.value
  if (!target) return
  const missing = encToFill.value.filter((v) => !(encInputs.value[v.id] ?? '').trim())
  if (encToFill.value.length > 0 && missing.length > 0) {
    ElMessage.warning(`加密变量需重新输入明文：${missing.map((v) => v.name).join('、')}`)
    return
  }
  let copied = 0
  let skipped = 0
  for (const p of copyPreview.value) {
    if (p.action === '跳过') { skipped++; continue }
    const value = p.v.encrypted ? '******' : p.v.value
    if (p.action === '覆盖') {
      const exist = targetVars.value.find((t) => t.name === p.v.name)
      if (exist) {
        const row: WfVariable = { ...exist, type: p.v.type, value, encrypted: p.v.encrypted, options: [...p.v.options], desc: p.v.desc }
        if (isMock) await dataStore.save('wfVariables', row)
        else await saveVariable(row)
        copied++
      }
      continue
    }
    if (p.action === '重命名' && p.newName === p.v.name) { skipped++; continue }
    if (isMock) {
      const all = (await dataStore.list<WfVariable>('wfVariables')) ?? []
      await dataStore.save('wfVariables', {
        id: nextId(all), wf: target, name: p.newName, type: p.v.type,
        value, encrypted: p.v.encrypted, options: [...p.v.options], desc: p.v.desc,
      })
    } else {
      await saveVariable({
        id: '', wf: target, name: p.newName, type: p.v.type,
        value, encrypted: p.v.encrypted, options: [...p.v.options], desc: p.v.desc,
      })
    }
    copied++
  }
  copyVisible.value = false
  ElMessage.success(`已复制 ${copied} 个变量到「${wfOptions.value.find((w) => w.id === target)?.name ?? target}」${skipped ? `（跳过 ${skipped} 个冲突）` : ''}；仅复制值，不跨工作流共享引用`)
}
</script>

<template>
  <div class="wvp">
    <div class="wvp-bar">
      <span class="wvp-title">工作流变量</span>
      <span class="pill info">{{ vars.length }} 个</span>
      <span class="wvp-hint">节点参数中以 <span class="mono">${var}</span> 引用；优先级：节点参数 &gt; 工作流变量 &gt; 环境组 &gt; 全局</span>
      <span class="spacer" />
      <template v-if="auth.canEdit">
        <button class="op-btn" @click="openCopy">⧉ 复制到其他工作流</button>
        <button class="tb-new" @click="openCreate">+ 新建变量</button>
      </template>
      <span v-else class="pill off">只读</span>
    </div>

    <table class="tbl">
      <thead>
        <tr><th>变量名</th><th>引用</th><th>类型</th><th>值</th><th>候选项</th><th>说明</th><th v-if="auth.canEdit" style="width:110px">操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="v in vars" :key="v.id">
          <td><b class="mono">{{ v.name }}</b></td>
          <td><code class="mono ref">{{ refOf(v) }}</code></td>
          <td><span class="pill" :class="typeCls[v.type]">{{ v.type }}</span></td>
          <td><span class="mono" :class="{ mask: v.encrypted }">{{ v.value }}</span></td>
          <td>
            <span v-if="v.options.length" class="mono" style="font-size:11px">{{ v.options.join(' / ') }}</span>
            <span v-else style="color:var(--text-3)">-</span>
          </td>
          <td style="color:var(--text-2)">{{ v.desc }}</td>
          <td v-if="auth.canEdit">
            <button class="op-btn primary" @click="openEdit(v)">编辑</button>
            <button class="op-btn danger" @click="removeVar(v)">删除</button>
          </td>
        </tr>
      </tbody>
    </table>
    <div v-if="vars.length === 0" class="empty">当前工作流暂无变量，点击「+ 新建变量」创建（如 biz_date、db_pwd 等）</div>

    <!-- 新建/编辑变量 -->
    <el-dialog v-model="editVisible" :title="editing ? `编辑变量 — ${editing.name}` : '新建变量'" width="480px">
      <div class="form-row">
        <label class="f-label">变量名<i>*</i></label>
        <input v-model="form.name" class="f-input" placeholder="如 biz_date（字母/数字/下划线）" />
      </div>
      <div class="form-row">
        <label class="f-label">类型</label>
        <select v-model="form.type" class="f-input">
          <option v-for="t in (['日期', '文本', '数值', '加密', '下拉'] as const)" :key="t" :value="t">{{ t }}</option>
        </select>
      </div>
      <div class="form-row">
        <label class="f-label">值</label>
        <input
          v-model="form.value"
          class="f-input"
          :type="form.type === '加密' ? 'password' : 'text'"
          :placeholder="form.type === '加密' ? (editing ? '留空保持原值' : '初始值（脱敏存储）') : '如 ${date(-1)} 或 prod'"
        />
      </div>
      <div v-if="form.type === '下拉'" class="form-row">
        <label class="f-label">候选项</label>
        <input v-model="form.options" class="f-input" placeholder="逗号分隔，如 prod,staging,dev" />
      </div>
      <div class="form-row">
        <label class="f-label">说明</label>
        <input v-model="form.desc" class="f-input" placeholder="变量用途说明（可选）" />
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
        <select v-model="copyTarget" class="f-input" @change="loadTargetVars">
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
      <div v-if="encToFill.length" class="enc-block">
        <div class="enc-title">加密变量需重新输入明文（不随复制传输）：</div>
        <div v-for="v in encToFill" :key="v.id" class="form-row" style="margin-bottom:8px">
          <label class="f-label mono">{{ v.name }}</label>
          <input v-model="encInputs[v.id]" type="password" class="f-input" placeholder="输入目标工作流中的明文值" />
        </div>
      </div>
      <div class="sec-title">复制预览</div>
      <table class="tbl">
        <thead><tr><th>变量</th><th>类型</th><th>冲突</th><th>动作</th><th>目标名</th></tr></thead>
        <tbody>
          <tr v-for="p in copyPreview" :key="p.v.id">
            <td class="mono">{{ p.v.name }}</td>
            <td><span class="pill" :class="typeCls[p.v.type]">{{ p.v.type }}</span></td>
            <td><span class="pill" :class="p.conflict ? 'warn' : 'ok'">{{ p.conflict ? '同名' : '无' }}</span></td>
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
.pill.ok{background:var(--success-bg);color:var(--success)}
.pill.off{background:var(--bg);color:var(--text-3)}
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
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.4)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:6px 13px;font-size:12px;cursor:pointer}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.form-row{display:flex;gap:10px;margin-bottom:12px;align-items:center}
.f-label{width:86px;flex-shrink:0;font-size:12.5px;color:var(--text-2);text-align:right}
.f-label i{color:var(--danger);font-style:normal;margin-left:2px}
.f-input{flex:1;border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:7px 10px;font-size:12.5px;outline:none;background:#fff;color:var(--text)}
.f-input:focus{border-color:var(--primary)}
.copy-tip{background:var(--info-bg);color:var(--info);border-radius:var(--radius-sm);padding:8px 10px;font-size:11.5px;margin-bottom:12px}
.strategy{display:flex;gap:14px;font-size:12.5px;color:var(--text-2);flex-wrap:wrap}
.enc-block{border:1px dashed var(--warn);border-radius:var(--radius-sm);padding:10px;margin-bottom:12px;background:var(--warn-bg)}
.enc-title{font-size:12px;color:var(--warn);font-weight:600;margin-bottom:8px}
.sec-title{font-weight:700;font-size:13px;margin:4px 0 8px;color:var(--text)}
</style>
