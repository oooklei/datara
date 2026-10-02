<script setup lang="ts">
/**
 * F60 六区块框架（①输入 ②输出 ③参数 ④条件 ⑤限定约束 ⑥排除）——框架级标准，与业务表单正交。
 *
 * 依据《02-DAG组件清单与定义》§1.2：六区块为框架级标准，各组件只定义业务专属表单，六区块自动附加；
 * C1/C2/C6/C7 业务表单为「无（仅六区块）」，故本组件是这些组件在拖入弹窗中的**唯一**配置载体。
 *
 * 治理设计 §12.2「禁双实现漂移」：本组件由 Inspector（已落画布节点）与 DropConfigDialog
 * （未落画布虚拟节点）共用，两处渲染、判定、数据键完全同源。
 *
 * 数据键（I1-设计文档 §3）：node.data.inputs / outputs / params / condition / constraints / exclude；
 * 缺省懒初始化（首次编辑才落键），老节点无字段时显示默认空值，向后兼容。
 *
 * 上游联动：①输入 的「输入引用」候选来自 ctx.upstream 各节点的 ②输出 注册表
 * （outputs.params/tables），即上游实际登记的输出，与 probe schema 无关，故弹窗期同样可用。
 */
import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { GNode } from '../../model'
import type { FieldCtx } from './fieldCtx'
import RowsField from './RowsField.vue'

type KvRow = { k: string; v: string; note?: string }
type ParamRow = { key: string; value: string; source: string }
type Constraints = {
  timeoutMin?: number; timeoutPolicy?: string
  retryTimes?: number; retryInterval?: number
  failPolicy?: string; priority?: number; workerGroup?: string
}
type ExcludeDef = { skipCond?: string; disabled?: boolean }

const props = withDefaults(defineProps<{
  /** 目标节点（Inspector=画布选中节点；弹窗=未落画布虚拟节点） */
  node: GNode
  /** 共享候选上下文（upstream/upSchema/varOptions 由 fieldCtxFactory 统一供给） */
  ctx: FieldCtx
  /** 只读降级（M15：analyst/viewer） */
  readonly?: boolean
  /** 脏标记（弹窗期宿主传 no-op，确认落画布时由宿主统一标脏） */
  markDirty: () => void
  /** 折叠初值（弹窗可默认折叠噪声区块，拖入期只看①③） */
  initialFolds?: Record<string, boolean>
}>(), { readonly: false, markDirty: () => {}, initialFolds: undefined })

const { upstream, upSchema, upstreamOuts, varOptions } = props.ctx

/* ================= 折叠状态 ================= */
const folds = ref<Record<string, boolean>>({
  inputs: true, outputs: true, params: true, condition: true, constraints: true, exclude: true,
  ...(props.initialFolds ?? {}),
})
function toggleBlk(k: string) { folds.value[k] = !folds.value[k] }

/* ================= ① 输入：上游只读列表 + 输入引用 =================
   upstream/upSchema 来自 ctx 工厂；upstreamOuts（①输入候选）同样取自 ctx，
   使渲染与 domainViolations 的悬空引用判定同源（§12.2 禁双实现漂移） */
const inputRefs = computed<string[]>(() => {
  const v = props.node.data.inputs
  return Array.isArray(v) ? (v as string[]) : []
})
function addInputRef(ev: Event) {
  const sel = ev.target as HTMLSelectElement
  const v = sel.value
  if (!v) return
  if (!Array.isArray(props.node.data.inputs)) props.node.data.inputs = []
  const list = props.node.data.inputs as string[]
  if (!list.includes(v)) { list.push(v); props.markDirty() }
  sel.value = ''
}
function delInputRef(i: number) {
  const list = props.node.data.inputs as string[]
  if (!Array.isArray(list)) return
  list.splice(i, 1)
  props.markDirty()
}

/* ================= ② 输出：输出参数注册表 + 结果表注册表（kv-table） ================= */
function ensureOut(kind: 'params' | 'tables'): KvRow[] {
  const d = props.node.data
  if (typeof d.outputs !== 'object' || d.outputs === null || Array.isArray(d.outputs)) d.outputs = {}
  const o = d.outputs as { params?: KvRow[]; tables?: KvRow[] }
  if (!Array.isArray(o[kind])) o[kind] = []
  return o[kind]!
}
const outParams = computed<KvRow[]>(() => ensureOut('params'))
const outTables = computed<KvRow[]>(() => ensureOut('tables'))

/* ================= ③ 参数：params-table（键/值/来源五选一） ================= */
const nodeParams = computed<ParamRow[]>(() => {
  const d = props.node.data
  if (!Array.isArray(d.params)) d.params = []
  return d.params as ParamRow[]
})

/* ================= ④ 条件 / ⑥ 排除：表达式（expr + 变量引用弹窗） ================= */
function ensureExclude(): ExcludeDef {
  const d = props.node.data
  if (typeof d.exclude !== 'object' || d.exclude === null || Array.isArray(d.exclude)) d.exclude = {}
  return d.exclude as ExcludeDef
}
const excl = computed<ExcludeDef>(() => ensureExclude())
function setDisabled(ev: Event) {
  ensureExclude().disabled = (ev.target as HTMLInputElement).checked
  props.markDirty()
}

/** 表达式目标统一寻址：condition | exclude | f:{formKey} */
function exprOf(target: string): string {
  if (target === 'condition') return String(props.node.data.condition ?? '')
  if (target === 'exclude') return String(excl.value.skipCond ?? '')
  if (target.startsWith('f:')) return String(props.node.data[target.slice(2)] ?? '')
  return ''
}
function setExprValue(target: string, v: string) {
  if (target === 'condition') props.node.data.condition = v
  else if (target === 'exclude') ensureExclude().skipCond = v
  else props.node.data[target.slice(2)] = v
  props.markDirty()
}
function setExpr(target: string, ev: Event) {
  setExprValue(target, (ev.target as HTMLInputElement).value)
}

/* 变量引用弹窗：下拉已注册变量 + 插入 ${var}（解析引擎 I3；候选由 ctx 工厂提供） */
const varDlg = ref(false)
const varTarget = ref('condition')
const varPick = ref('')
const varPreview = computed(() => exprOf(varTarget.value))
function openVarDialog(target: string) {
  varTarget.value = target
  varPick.value = ''
  varDlg.value = true
}
function insertVar() {
  if (!varPick.value) { ElMessage.warning('请选择要引用的变量'); return }
  const cur = exprOf(varTarget.value)
  const token = '${' + varPick.value + '}'
  setExprValue(varTarget.value, cur ? `${cur} ${token}` : token)
  varDlg.value = false
  ElMessage.success(`已插入 ${token}`)
}
/* ================= F1 值域闸门：①输入引用悬空检测（供宿主 canConfirm 消费） ================= */
/** 已失效的输入引用（上游节点已删或其②输出被移除） */
const staleInputRefs = computed<string[]>(() => {
  const valid = new Set(upstreamOuts.value)
  return inputRefs.value.filter((r) => !valid.has(r))
})
/** 暴露：业务表单 `f:{key}` 变量引用转交本组件弹窗（保持弹窗唯一实例）+ 悬空引用供宿主闸门消费 */
defineExpose({ openVarDialog, staleInputRefs })

/* ================= ⑤ 限定约束：固定字段组（框架内置，对齐海豚任务定义通用参数） ================= */
const C_DEF: Constraints = {
  timeoutMin: 60, timeoutPolicy: 'fail', retryTimes: 0,
  retryInterval: 1, failPolicy: 'stop', priority: 5, workerGroup: '默认',
}
const cons = computed<Constraints>(() =>
  (props.node.data.constraints as Constraints | undefined) ?? C_DEF)
function setC(key: keyof Constraints, ev: Event) {
  const t = ev.target as HTMLInputElement | HTMLSelectElement
  let v: unknown = t.value
  if (t instanceof HTMLInputElement && t.type === 'number') {
    if (t.value === '') { v = undefined }
    else {
      let n = Number(t.value)
      if (!Number.isFinite(n)) return
      /* 值域校验（I3 §13）：超时/重试次数/重试间隔 ≥ 0，优先级收敛 1~5 */
      if (key === 'priority') n = Math.min(5, Math.max(1, Math.round(n)))
      else if (n < 0) n = 0
      v = n
    }
  }
  props.node.data.constraints = { ...cons.value, [key]: v }
  props.markDirty()
}

/* ---------- 六区块头部摘要 ---------- */
const condSummary = computed(() => (exprOf('condition') ? '已配置' : '未设置'))
const consSummary = computed(() =>
  `${cons.value.timeoutMin ?? 60}min · 重试${cons.value.retryTimes ?? 0} · ${cons.value.failPolicy === 'continue' ? '继续' : '终止'}`)
const exclSummary = computed(() =>
  excl.value.disabled ? '已禁用' : (excl.value.skipCond ? '有跳过条件' : '未设置'))
</script>

<template>
  <div class="sixblocks">
    <!-- ① 输入：上游依赖（只读）+ 输入引用（值域=上游②输出注册表） -->
    <div class="blk">
      <div class="blk-head" @click="toggleBlk('inputs')">
        <span class="blk-arrow" :class="{ open: !folds.inputs }">▼</span>① 输入
        <span class="blk-sum">{{ upstream.length }} 上游 · {{ inputRefs.length }} 引用</span>
      </div>
      <div v-show="!folds.inputs" class="blk-body">
        <div v-if="upstream.length" class="up-list">
          <div v-for="u in upstream" :key="u.id" class="up-item">
            <span class="up-ico" :style="{ background: upSchema(u).color }">{{ upSchema(u).icon }}</span>
            <span class="up-name">{{ u.data.name }}</span>
            <span class="up-type">{{ upSchema(u).label }}</span>
          </div>
        </div>
        <div v-else class="blk-empty">无上游节点（起始节点）</div>
        <label class="blk-cap">输入引用（上游输出参数 / 结果表）</label>
        <div class="ref-chips">
          <span v-for="(r, i) in inputRefs" :key="r" class="ref-chip">
            {{ r }}
            <button v-if="!readonly" @click="delInputRef(i)">×</button>
          </span>
          <span v-if="!inputRefs.length" class="blk-empty">未引用上游输出</span>
        </div>
        <select v-if="!readonly && upstreamOuts.length" class="ref-add" @change="addInputRef($event)">
          <option value="">＋ 选择上游输出引用…</option>
          <option v-for="o in upstreamOuts" :key="o" :value="o">{{ o }}</option>
        </select>
        <div v-if="staleInputRefs.length" class="blk-warn">
          引用已失效（上游输出已变更）：{{ staleInputRefs.join('、') }}
        </div>
      </div>
    </div>

    <!-- ② 输出：输出参数注册表 + 结果表注册表（供下游与跨节点引用） -->
    <div class="blk">
      <div class="blk-head" @click="toggleBlk('outputs')">
        <span class="blk-arrow" :class="{ open: !folds.outputs }">▼</span>② 输出
        <span class="blk-sum">{{ outParams.length }} 参数 · {{ outTables.length }} 结果表</span>
      </div>
      <div v-show="!folds.outputs" class="blk-body">
        <label class="blk-cap">输出参数注册表</label>
        <RowsField :rows="outParams" mode="kv" :disabled="readonly" @change="markDirty" />
        <label class="blk-cap" style="margin-top:8px">结果表注册表</label>
        <RowsField :rows="outTables" mode="kv" :disabled="readonly" @change="markDirty" />
      </div>
    </div>

    <!-- ③ 参数：params-table（键/值/来源五选一） -->
    <div class="blk">
      <div class="blk-head" @click="toggleBlk('params')">
        <span class="blk-arrow" :class="{ open: !folds.params }">▼</span>③ 参数
        <span class="blk-sum">{{ nodeParams.length }} 项</span>
      </div>
      <div v-show="!folds.params" class="blk-body">
        <RowsField :rows="nodeParams" mode="params" :disabled="readonly" @change="markDirty" />
        <div class="blk-hint">解析优先级：节点参数 &gt; 工作流变量 &gt; 环境组 &gt; 全局</div>
      </div>
    </div>

    <!-- ④ 条件：运行条件表达式 -->
    <div class="blk">
      <div class="blk-head" @click="toggleBlk('condition')">
        <span class="blk-arrow" :class="{ open: !folds.condition }">▼</span>④ 条件
        <span class="blk-sum">{{ condSummary }}</span>
      </div>
      <div v-show="!folds.condition" class="blk-body">
        <div class="expr-row">
          <input
            class="mono" :value="exprOf('condition')" placeholder="运行条件表达式，留空 = 总是执行"
            :disabled="readonly" @change="setExpr('condition', $event)"
          />
          <button class="var-btn" :disabled="readonly" title="引用变量" @click="openVarDialog('condition')">$</button>
        </div>
      </div>
    </div>

    <!-- ⑤ 限定约束：超时/重试/失败策略/优先级/worker分组（框架内置字段组） -->
    <div class="blk">
      <div class="blk-head" @click="toggleBlk('constraints')">
        <span class="blk-arrow" :class="{ open: !folds.constraints }">▼</span>⑤ 限定约束
        <span class="blk-sum">{{ consSummary }}</span>
      </div>
      <div v-show="!folds.constraints" class="blk-body blk-grid">
        <div class="field"><label>超时（分钟）</label><input type="number" :value="cons.timeoutMin ?? 60" :disabled="readonly" @change="setC('timeoutMin', $event)" /></div>
        <div class="field"><label>超时策略</label>
          <select :value="cons.timeoutPolicy ?? 'fail'" :disabled="readonly" @change="setC('timeoutPolicy', $event)">
            <option value="fail">失败</option>
            <option value="warn">告警</option>
          </select>
        </div>
        <div class="field"><label>重试次数</label><input type="number" :value="cons.retryTimes ?? 0" :disabled="readonly" @change="setC('retryTimes', $event)" /></div>
        <div class="field"><label>重试间隔（分）</label><input type="number" :value="cons.retryInterval ?? 1" :disabled="readonly" @change="setC('retryInterval', $event)" /></div>
        <div class="field"><label>失败策略</label>
          <select :value="cons.failPolicy ?? 'stop'" :disabled="readonly" @change="setC('failPolicy', $event)">
            <option value="stop">终止</option>
            <option value="continue">继续</option>
          </select>
        </div>
        <div class="field"><label>优先级</label><input type="number" :value="cons.priority ?? 5" :disabled="readonly" @change="setC('priority', $event)" /></div>
        <div class="field"><label>Worker 分组</label><input :value="String(cons.workerGroup ?? '默认')" :disabled="readonly" @change="setC('workerGroup', $event)" /></div>
      </div>
    </div>

    <!-- ⑥ 排除：跳过条件 + 禁用开关 -->
    <div class="blk">
      <div class="blk-head" @click="toggleBlk('exclude')">
        <span class="blk-arrow" :class="{ open: !folds.exclude }">▼</span>⑥ 排除
        <span class="blk-sum">{{ exclSummary }}</span>
      </div>
      <div v-show="!folds.exclude" class="blk-body">
        <label class="blk-cap">跳过条件（表达式）</label>
        <div class="expr-row">
          <input
            class="mono" :value="exprOf('exclude')" placeholder="满足则跳过本节点，留空 = 不跳过"
            :disabled="readonly" @change="setExpr('exclude', $event)"
          />
          <button class="var-btn" :disabled="readonly" title="引用变量" @click="openVarDialog('exclude')">$</button>
        </div>
        <label class="bool-row" style="margin-top:8px">
          <input type="checkbox" :checked="!!excl.disabled" :disabled="readonly" @change="setDisabled($event)" />
          <span>禁用本节点（调度时直接跳过）</span>
        </label>
      </div>
    </div>

    <!-- 变量引用弹窗（F60）：下拉已注册变量 + 插入 ${var} -->
    <el-dialog v-model="varDlg" title="引用变量" width="400px" append-to-body>
      <div class="var-body">
        <label class="blk-cap">选择变量（插入 ${'{'}var{'}'}）</label>
        <select v-model="varPick" style="width:100%">
          <option value="">请选择…</option>
          <option v-for="v in varOptions" :key="v" :value="v">${{ '{' + v + '}' }}</option>
        </select>
        <label class="blk-cap" style="margin-top:10px">当前表达式预览</label>
        <div class="var-preview mono">{{ varPreview || '（空）' }}</div>
        <div class="var-hint">解析优先级：节点参数 &gt; 工作流变量 &gt; 环境组 &gt; 全局（解析引擎 I3 落地）</div>
      </div>
      <template #footer>
        <el-button @click="varDlg = false">取消</el-button>
        <el-button type="primary" @click="insertVar">插入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
/* 六区块折叠面板 */
.blk{margin-top:8px;border:1px solid var(--border);border-radius:var(--radius-sm);overflow:hidden}
.blk-head{display:flex;align-items:center;gap:5px;padding:6px 8px;font-size:12px;font-weight:600;background:var(--bg);cursor:pointer;user-select:none;color:var(--text-2)}
.blk-head:hover{color:var(--primary)}
.blk-arrow{font-size:9px;transition:transform .15s}
.blk-arrow.open{transform:rotate(0)}
.blk-arrow:not(.open){transform:rotate(-90deg)}
.blk-sum{margin-left:auto;font-size:10px;font-weight:400;color:var(--text-3)}
.blk-body{padding:7px 8px;background:var(--card);display:flex;flex-direction:column;gap:4px}
.blk-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px}
.blk-grid .field{margin:0}
.blk-cap{font-size:10.5px;color:var(--text-3);font-weight:600}
.blk-hint{font-size:10px;color:var(--text-3)}
.blk-empty{font-size:10.5px;color:var(--text-3)}
.blk-warn{font-size:10.5px;color:#b45309;background:rgba(217,119,6,.08);border:1px solid rgba(217,119,6,.35);border-radius:4px;padding:3px 6px}
/* ① 上游只读列表 + 输入引用 */
.up-list{display:flex;flex-direction:column;gap:3px}
.up-item{display:flex;align-items:center;gap:6px;font-size:11.5px;padding:3px 5px;background:var(--bg);border-radius:var(--radius-sm)}
.up-ico{width:16px;height:16px;border-radius:4px;color:#fff;font-size:9px;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.up-name{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.up-type{margin-left:auto;font-size:10px;color:var(--text-3);flex-shrink:0}
.ref-chips{display:flex;flex-wrap:wrap;gap:4px}
.ref-chip{display:inline-flex;align-items:center;gap:3px;font-size:10.5px;background:var(--primary-light);color:var(--primary);border-radius:999px;padding:1px 4px 1px 8px;max-width:100%}
.ref-chip span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ref-chip button{border:none;background:transparent;color:inherit;cursor:pointer;font-size:11px;line-height:1;padding:0 2px}
.ref-add{margin-top:2px;width:100%}
/* 表达式 + 变量引用按钮 */
.expr-row{display:flex;gap:4px;align-items:center}
.expr-row input{flex:1;min-width:0}
.var-btn{width:26px;height:26px;flex-shrink:0;border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);color:var(--text-2);font-size:12px;cursor:pointer;font-weight:700}
.var-btn:hover:not(:disabled){border-color:var(--primary);color:var(--primary)}
.var-btn:disabled{opacity:.4;cursor:not-allowed}
.bool-row{display:flex;align-items:center;gap:6px;font-size:11.5px;color:var(--text-2);cursor:pointer}
/* 变量弹窗 */
.var-body{display:flex;flex-direction:column;gap:4px}
.var-body select{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;outline:none}
.var-preview{background:var(--bg);border:1px solid var(--border);border-radius:var(--radius-sm);padding:6px 8px;font-size:11.5px;min-height:32px;word-break:break-all}
.var-hint{font-size:10.5px;color:var(--text-3)}
</style>
