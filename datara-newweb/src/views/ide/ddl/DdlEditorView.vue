<template>
  <main class="ddl-editor" data-ddl-editor aria-label="DDL 编辑器">
    <header class="view-head">
      <h1>DDL 编辑器（双轨）</h1>
      <p>table → 结构化编辑轨；其余 13 源码型变体 → 源码文本轨（互斥）。写链全程走八步管控面：权限校验 → 依赖检查 → 影响对象预览 → DDL 脚本快照 → 用户确认 → 执行 → 结果记录 → 失败回滚或补偿脚本。</p>
    </header>

    <section class="locator" data-locator aria-label="目标定位">
      <label class="field"><span>对象类别（kind）</span>
        <select data-kind-select v-model="kind">
          <option :value="null" disabled>请选择对象类别</option>
          <option v-for="k in DDL_KIND_OPTIONS" :key="k" :value="k">{{ k }}</option>
        </select>
      </label>
      <label class="field"><span>数据源 ID</span>
        <input data-datasource-id type="number" min="1" v-model.number="datasourceId" />
      </label>
      <label class="field"><span>数据库（database）</span>
        <input data-database v-model="database" placeholder="例如 db" />
      </label>
      <label class="field"><span>Schema（可空）</span>
        <input data-schema v-model="schema" placeholder="可空" />
      </label>
      <label class="field"><span>对象名（name）</span>
        <input data-object-name v-model="objectName" placeholder="例如 v1" />
      </label>
      <div class="field actions">
        <button data-load-definition :disabled="!objectRefReady || busy !== null" @click="loadDefinition">载入定义快照（#21）</button>
      </div>
      <p v-if="kind !== null && apiKind === null" class="note" data-kind-unavailable role="note">
        类别 {{ kind }} 暂不可达 DDL 写链（源码轨仅呈现；候后端 kind 扩展，禁私设近似映射）。
      </p>
    </section>

    <p class="note" data-perm-gate role="note" :data-granted="permissionGranted ? 'yes' : 'no'">
      写链权限（edit_definition）：{{ permissionGranted ? '已授予' : '未授予（角色闸阻断）' }}
    </p>

    <p v-if="error" class="error" data-error role="alert">{{ errorText }}</p>

    <SourceDdlEditor v-if="isSourceTrack(kind)" :snapshot="snapshot" v-model="nextDdlText" />
    <StructuredDdlEditor v-else-if="isStructuredTrack(kind)" :snapshot="snapshot" v-model="nextDdlText" />
    <p v-else class="empty-hint" role="status">选择对象类别后开始。</p>

    <section class="control-panel" data-control-panel aria-label="八步管控面">
      <h2>八步管控面</h2>
      <ol class="steps">
        <li :data-step="1" :data-step-state="step1.state">
          <div class="step-head"><span class="step-title">1 权限校验</span><span class="step-state">{{ stateLabel[step1.state] }}</span></div>
          <p class="step-detail">{{ step1.detail }}</p>
        </li>
        <li :data-step="2" :data-step-state="step2.state">
          <div class="step-head"><span class="step-title">2 依赖检查</span><span class="step-state">{{ stateLabel[step2.state] }}</span></div>
          <p class="step-detail">{{ step2.detail }}</p>
          <button data-validate-policy :disabled="!canValidate || busy !== null" @click="runValidate">校验策略（#22）</button>
          <ul class="findings" data-findings>
            <li v-for="(finding, index) in policyReport?.findings ?? []" :key="index" :data-finding-level="finding.level">
              <code>{{ finding.code }}</code><span>{{ finding.message }}</span>
            </li>
          </ul>
          <p v-if="policyReport" data-policy-blocked :data-blocked="policyReport.blocked ? 'yes' : 'no'">
            策略闸：{{ policyReport.blocked ? '阻断（禁止确认）' : '放行' }}
          </p>
        </li>
        <li :data-step="3" :data-step-state="step3.state">
          <div class="step-head"><span class="step-title">3 影响对象预览</span><span class="step-state">{{ stateLabel[step3.state] }}</span></div>
          <p class="step-detail">{{ step3.detail }}</p>
          <button data-preview-impact :disabled="!canPreview || busy !== null" @click="runPreview">预览影响（#23）</button>
          <ul class="impacts" data-impacts>
            <li v-for="(item, index) in impactReport?.impacts ?? []" :key="index" data-impact>
              <span data-impact-relation>{{ item.relationType }}</span>
              <span data-impact-object>{{ item.objectRef.kind }} {{ item.objectRef.database }}.{{ item.objectRef.name }}</span>
              <span data-impact-detail>{{ item.detail }}</span>
            </li>
          </ul>
          <p v-if="impactReport !== null && impactReport.unknownReasons.length > 0" data-impact-unknown class="note">
            血缘未知：<span v-for="(reason, index) in impactReport.unknownReasons" :key="index">{{ reason }}。</span>
          </p>
        </li>
        <li :data-step="4" :data-step-state="step4.state">
          <div class="step-head"><span class="step-title">4 DDL 脚本快照</span><span class="step-state">{{ stateLabel[step4.state] }}</span></div>
          <p class="step-detail">{{ step4.detail }}</p>
          <p v-if="policyReport" data-policy-snapshot-id>策略快照：{{ policyReport.snapshotId }}</p>
          <p v-if="impactReport" data-impact-snapshot-id>影响快照：{{ impactReport.snapshotId }}</p>
        </li>
        <li :data-step="5" :data-step-state="step5.state">
          <div class="step-head"><span class="step-title">5 用户确认</span><span class="step-state">{{ stateLabel[step5.state] }}</span></div>
          <p class="step-detail">{{ step5.detail }}</p>
          <label class="field"><span>确认短语</span>
            <input data-confirm-phrase v-model="confirmPhrase" :disabled="!confirmInputEnabled" placeholder="输入确认短语以放行写链" />
          </label>
          <button data-submit-confirm :disabled="!confirmReady" @click="runConfirm">提交确认并执行（#24）</button>
          <p class="guard" role="note">确认短语空/空白时契约层拒发（CONFIRM_PHRASE_INVALID）；服务端 ConfirmGate 另做哈希绑定校验。</p>
        </li>
        <li :data-step="6" :data-step-state="step6.state">
          <div class="step-head"><span class="step-title">6 执行</span><span class="step-state">{{ stateLabel[step6.state] }}</span></div>
          <p class="step-detail">{{ step6.detail }}</p>
          <p v-if="outcome" class="outcome">
            <span data-outcome-record-id>{{ outcome.recordId }}</span>
            <span data-outcome-status>{{ outcome.status }}</span>
          </p>
        </li>
        <li :data-step="7" :data-step-state="step7.state">
          <div class="step-head"><span class="step-title">7 结果记录</span><span class="step-state">{{ stateLabel[step7.state] }}</span></div>
          <p class="step-detail">{{ step7.detail }}</p>
          <button data-refresh-records :disabled="busy !== null || datasourceId <= 0" @click="refreshRecords">刷新执行记录（#25）</button>
          <table v-if="records" data-records>
            <thead><tr><th>记录ID</th><th>操作者</th><th>动作</th><th>脚本哈希</th><th>执行时间</th><th>状态</th><th>失败摘要</th></tr></thead>
            <tbody>
              <tr v-for="record in records.items" :key="record.recordId" :data-record="record.recordId" :data-record-status="record.status">
                <td>{{ record.recordId }}</td>
                <td>{{ record.actorId }}</td>
                <td>{{ record.action }}</td>
                <td><code>{{ record.scriptHash }}</code></td>
                <td>{{ record.executedAt }}</td>
                <td>{{ record.status }}</td>
                <td>{{ record.failureSummary ?? '—' }}</td>
              </tr>
            </tbody>
          </table>
        </li>
        <li :data-step="8" :data-step-state="step8.state">
          <div class="step-head"><span class="step-title">8 失败回滚或补偿脚本</span><span class="step-state">{{ stateLabel[step8.state] }}</span></div>
          <p class="step-detail">{{ step8.detail }}</p>
          <ul class="exec-status" data-exec-status-list>
            <li v-for="semantic in EXEC_STATUS_SEMANTICS" :key="semantic.status" :data-exec-status="semantic.status" :data-current="outcome?.status === semantic.status ? 'yes' : 'no'">
              <code>{{ semantic.status }}</code><span>{{ semantic.label }}</span>
            </li>
          </ul>
        </li>
      </ol>
    </section>
  </main>
</template>

<script setup lang="ts">
/**
 * 16.1 波3 DDL 编辑器容器（双轨分派 + 八步管控面）。
 *
 * 八步步序（GOV §四 标题逐字）：1 权限校验 / 2 依赖检查 / 3 影响对象预览 /
 * 4 DDL 脚本快照 / 5 用户确认 / 6 执行 / 7 结果记录 / 8 失败回滚或补偿脚本。
 *
 * 三重闸（序）：
 *  1. 角色闸——edit_definition（R5B_PERMISSION_MATRIX 写链语义；getDefinition 属
 *     VIEW_ALL，读不拦）；
 *  2. kind 闸——非 R5-B 5 值类别禁链（fail-closed，禁私设近似映射）；
 *  3. capability 闸——unsupported/unknown 及未知值拒写（BE capability.py 同域，
 *     supported/conditional 放行）。
 *
 * 快照绑定链：kind/定位输入任一变化即 resetChain（陈旧快照不入写链）；载入动作
 * 不触发该 watch。契约经 props DI 注入（测试用），缺省 createSqlIdeDdlContract()。
 */
import { computed, ref, watch } from 'vue'
import { createSqlIdeDdlContract, SqlIdeDdlApiError } from '../../../services/rebuild/sqlIdeDdlApi'
import type {
  DdlDefinitionSnapshot,
  DdlExecutionOutcome,
  DdlExecutionRecordPage,
  DdlExecutionStatus,
  DdlImpactReport,
  DdlObjectKind,
  DdlObjectRef,
  DdlPolicyReport,
  SqlIdeDdlContract,
} from '../../../services/rebuild/sqlIdeDdlApi'
import { roleHasPermission } from '../../../services/rebuild/rolePermissions'
import type { Role } from '../../../services/rebuild/rolePermissions'
import { DDL_KIND_OPTIONS, isSourceTrack, isStructuredTrack, toApiKind } from './objectSourceKinds'
import type { DdlKindOption } from './objectSourceKinds'
import SourceDdlEditor from './SourceDdlEditor.vue'
import StructuredDdlEditor from './StructuredDdlEditor.vue'

const props = withDefaults(defineProps<{ role?: Role; contract?: SqlIdeDdlContract }>(), { role: 'viewer' })

const ddl = props.contract ?? createSqlIdeDdlContract()

// ---------- 定位输入 ----------
const kind = ref<DdlKindOption | null>(null)
const datasourceId = ref(1)
const database = ref('')
const schema = ref('')
const objectName = ref('')

// ---------- 快照绑定链状态 ----------
const snapshot = ref<DdlDefinitionSnapshot | null>(null)
const nextDdlText = ref('')
const policyReport = ref<DdlPolicyReport | null>(null)
const impactReport = ref<DdlImpactReport | null>(null)
const outcome = ref<DdlExecutionOutcome | null>(null)
const records = ref<DdlExecutionRecordPage | null>(null)
const confirmPhrase = ref('')
const error = ref<{ message: string; code: number; errorCode?: string } | null>(null)
const busy = ref<'define' | 'validate' | 'preview' | 'confirm' | 'records' | null>(null)

// ---------- 三重闸 ----------
const permissionGranted = computed(() => roleHasPermission(props.role, 'edit_definition'))
const apiKind = computed<DdlObjectKind | null>(() => (kind.value === null ? null : toApiKind(kind.value)))
const objectRefReady = computed(() =>
  apiKind.value !== null && datasourceId.value > 0 && database.value.trim() !== '' && objectName.value.trim() !== '',
)
const capabilityWritable = computed(() =>
  snapshot.value !== null && (snapshot.value.capability === 'supported' || snapshot.value.capability === 'conditional'),
)
const chainBlockReason = computed<string | null>(() => {
  if (!permissionGranted.value) return '权限不足：需要 edit_definition'
  if (kind.value !== null && apiKind.value === null) return `类别 ${kind.value} 暂不可达 DDL 写链`
  if (snapshot.value !== null && !capabilityWritable.value) return `capability=${snapshot.value.capability} 拒写（fail-closed）`
  return null
})
const chainAllowed = computed(() => chainBlockReason.value === null)

// ---------- 管控面使能 ----------
const canValidate = computed(() => chainAllowed.value && snapshot.value !== null && nextDdlText.value.trim() !== '')
const canPreview = computed(() => chainAllowed.value && policyReport.value !== null)
const policyBlocked = computed(() => policyReport.value?.blocked === true)
const confirmInputEnabled = computed(() => chainAllowed.value && policyReport.value !== null && impactReport.value !== null && !policyBlocked.value)
const confirmReady = computed(() => confirmInputEnabled.value && confirmPhrase.value.trim() !== '' && busy.value === null)

// ---------- 八步步序（GOV §四 标题逐字） ----------
type StepState = 'pending' | 'active' | 'done' | 'blocked'
interface StepInfo { state: StepState; detail: string }
const stateLabel: Record<StepState, string> = { pending: '待触发', active: '可执行', done: '已通过', blocked: '已阻断' }

const step1 = computed<StepInfo>(() => ({
  state: permissionGranted.value ? 'done' : 'blocked',
  detail: permissionGranted.value ? 'edit_definition 已授予' : '需要 edit_definition 权限',
}))
const step2 = computed<StepInfo>(() => {
  if (chainBlockReason.value !== null) return { state: 'blocked', detail: chainBlockReason.value }
  if (policyReport.value !== null) return { state: 'done', detail: `策略快照 ${policyReport.value.snapshotId}` }
  if (canValidate.value) return { state: 'active', detail: '待校验' }
  return { state: 'pending', detail: snapshot.value === null ? '待载入定义快照' : '待编辑 DDL 文本' }
})
const step3 = computed<StepInfo>(() => {
  if (chainBlockReason.value !== null) return { state: 'blocked', detail: chainBlockReason.value }
  if (impactReport.value !== null) return { state: 'done', detail: `影响快照 ${impactReport.value.snapshotId}` }
  if (policyReport.value !== null) return { state: 'active', detail: '待预览影响' }
  return { state: 'pending', detail: '待依赖检查' }
})
const step4 = computed<StepInfo>(() => {
  if (chainBlockReason.value !== null) return { state: 'blocked', detail: chainBlockReason.value }
  if (policyReport.value !== null && impactReport.value !== null) return { state: 'done', detail: '双快照已绑定' }
  if (policyReport.value !== null) return { state: 'active', detail: '待影响快照' }
  return { state: 'pending', detail: '待策略快照' }
})
const step5 = computed<StepInfo>(() => {
  if (chainBlockReason.value !== null) return { state: 'blocked', detail: chainBlockReason.value }
  if (policyBlocked.value) return { state: 'blocked', detail: '策略阻断，禁止确认' }
  if (outcome.value !== null) return { state: 'done', detail: '确认已完成' }
  if (confirmInputEnabled.value) return { state: 'active', detail: '待输入确认短语' }
  return { state: 'pending', detail: '待前置步骤完成' }
})
const step6 = computed<StepInfo>(() => {
  if (chainBlockReason.value !== null) return { state: 'blocked', detail: chainBlockReason.value }
  if (busy.value === 'confirm') return { state: 'active', detail: '执行中' }
  if (outcome.value !== null) return { state: 'done', detail: `执行记录 ${outcome.value.recordId}` }
  return { state: 'pending', detail: '待确认提交' }
})
const step7 = computed<StepInfo>(() => {
  if (chainBlockReason.value !== null) return { state: 'blocked', detail: chainBlockReason.value }
  if (records.value !== null) return { state: 'done', detail: `已载入 ${records.value.items.length} 条记录` }
  if (outcome.value !== null) return { state: 'active', detail: '待查询' }
  return { state: 'pending', detail: '待执行' }
})
const step8 = computed<StepInfo>(() => {
  if (chainBlockReason.value !== null) return { state: 'blocked', detail: chainBlockReason.value }
  if (outcome.value !== null) return { state: 'done', detail: `当前态：${outcome.value.status}` }
  return { state: 'pending', detail: '待执行' }
})

/** 执行五态语义（BE ExecutionRecord.status；recovery-failed 进入人工恢复）。 */
const EXEC_STATUS_SEMANTICS: ReadonlyArray<{ status: DdlExecutionStatus; label: string }> = [
  { status: 'success', label: '执行成功' },
  { status: 'failure', label: '执行失败' },
  { status: 'rolled-back', label: '已回滚' },
  { status: 'compensated', label: '已补偿' },
  { status: 'recovery-failed', label: '补偿失败——进入人工恢复' },
]

// ---------- 动作 ----------
const errorText = computed(() => {
  if (error.value === null) return ''
  const suffix = error.value.errorCode ? `，errorCode=${error.value.errorCode}` : ''
  return `${error.value.message}（code=${error.value.code}${suffix}）`
})

function buildObjectRef(): DdlObjectRef {
  return {
    datasourceId: datasourceId.value,
    database: database.value.trim(),
    catalog: null,
    schema: schema.value.trim() === '' ? null : schema.value.trim(),
    kind: apiKind.value as DdlObjectKind,
    name: objectName.value.trim(),
    parent: null,
  }
}

function setError(err: unknown): void {
  if (err instanceof SqlIdeDdlApiError) {
    error.value = { message: err.message, code: err.code, errorCode: err.errorCode }
  } else {
    error.value = { message: err instanceof Error ? err.message : String(err), code: 0 }
  }
}

/** 清空快照绑定链（不清 error）；定位输入 watch 与载入动作调用。 */
function resetChain(): void {
  snapshot.value = null
  policyReport.value = null
  impactReport.value = null
  outcome.value = null
  records.value = null
  nextDdlText.value = ''
  confirmPhrase.value = ''
}

async function loadDefinition(): Promise<void> {
  if (!objectRefReady.value || busy.value !== null) return
  resetChain()
  error.value = null
  busy.value = 'define'
  try {
    snapshot.value = await ddl.getDefinition(datasourceId.value, buildObjectRef())
  } catch (err) {
    setError(err)
  } finally {
    busy.value = null
  }
}

async function runValidate(): Promise<void> {
  if (!canValidate.value || busy.value !== null || snapshot.value === null) return
  busy.value = 'validate'
  try {
    policyReport.value = await ddl.validatePolicy({
      datasourceId: datasourceId.value,
      objectRef: buildObjectRef(),
      sourceVersion: snapshot.value.sourceVersion,
      nextDdlText: nextDdlText.value,
    })
  } catch (err) {
    setError(err)
  } finally {
    busy.value = null
  }
}

async function runPreview(): Promise<void> {
  if (!canPreview.value || busy.value !== null || snapshot.value === null) return
  busy.value = 'preview'
  try {
    impactReport.value = await ddl.previewImpact({
      datasourceId: datasourceId.value,
      objectRef: buildObjectRef(),
      sourceVersion: snapshot.value.sourceVersion,
      nextDdlText: nextDdlText.value,
    })
  } catch (err) {
    setError(err)
  } finally {
    busy.value = null
  }
}

async function runConfirm(): Promise<void> {
  if (!confirmReady.value || busy.value !== null || snapshot.value === null || policyReport.value === null || impactReport.value === null) return
  busy.value = 'confirm'
  try {
    outcome.value = await ddl.submitConfirm({
      datasourceId: datasourceId.value,
      objectRef: buildObjectRef(),
      sourceVersion: snapshot.value.sourceVersion,
      nextDdlText: nextDdlText.value,
      policySnapshotId: policyReport.value.snapshotId,
      impactSnapshotId: impactReport.value.snapshotId,
      confirmPhrase: confirmPhrase.value,
    })
  } catch (err) {
    setError(err)
  } finally {
    busy.value = null
  }
}

async function refreshRecords(): Promise<void> {
  if (busy.value !== null || datasourceId.value <= 0) return
  busy.value = 'records'
  try {
    records.value = await ddl.listExecutionRecords({ datasourceId: datasourceId.value })
  } catch (err) {
    setError(err)
  } finally {
    busy.value = null
  }
}

// 定位输入任一变化 → 清链（陈旧快照不入写链；载入动作不触发本 watch）。
watch([kind, datasourceId, database, schema, objectName], () => { resetChain() })
</script>

<style scoped>
.ddl-editor{max-width:980px;margin:0 auto;padding:20px 16px 48px;color:#172033;font-size:14px}
.view-head h1{margin:0 0 6px;font-size:20px}
.view-head p{margin:0 0 16px;color:#64748b;font-size:13px;line-height:1.6}
.locator{display:flex;gap:12px;flex-wrap:wrap;align-items:flex-end;border:1px solid #e2e8f0;border-radius:8px;padding:12px 14px;margin-bottom:10px;background:#fff}
.locator .field{margin:0}
.locator .field.actions{margin-left:auto}
.field{display:flex;flex-direction:column;gap:4px;font-size:13px;margin:0 0 10px}
.field span{color:#475569}
input,select{padding:6px 8px;border:1px solid #cbd5e1;border-radius:6px;font-size:13px;color:#172033;background:#fff;min-width:140px}
button{padding:7px 14px;border:1px solid #cbd5e1;border-radius:6px;background:#f1f5f9;color:#172033;font-size:13px;cursor:pointer}
button:hover:not(:disabled){background:#e2e8f0}
button:disabled{color:#94a3b8;cursor:not-allowed}
.note{margin:8px 0;color:#92400e;font-size:13px}
.error{margin:8px 0;padding:8px 12px;border:1px solid #fecaca;border-radius:6px;background:#fef2f2;color:#b91c1c;font-size:13px}
.empty-hint{color:#94a3b8;font-size:13px}
.control-panel{margin-top:18px;border:1px solid #e2e8f0;border-radius:8px;padding:14px 16px;background:#fff}
.control-panel h2{margin:0 0 12px;font-size:16px}
.steps{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:10px}
.steps li{border:1px solid #e2e8f0;border-left-width:4px;border-radius:6px;padding:10px 12px}
.steps li[data-step-state="done"]{border-left-color:#15803d}
.steps li[data-step-state="active"]{border-left-color:#2563eb}
.steps li[data-step-state="pending"]{border-left-color:#cbd5e1}
.steps li[data-step-state="blocked"]{border-left-color:#b91c1c}
.step-head{display:flex;gap:10px;align-items:baseline}
.step-title{font-size:14px;font-weight:600}
.step-state{font-size:12px;color:#64748b}
.step-detail{margin:4px 0 8px;color:#64748b;font-size:12.5px}
.findings,.impacts,.exec-status{list-style:none;margin:0 0 8px;padding:0;display:flex;flex-direction:column;gap:4px;font-size:13px}
.findings li,.impacts li,.exec-status li{display:flex;gap:10px;flex-wrap:wrap;align-items:baseline}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px;background:#eef2f7;padding:1px 5px;border-radius:3px}
[data-finding-level="block"]{color:#b91c1c}
[data-finding-level="warn"]{color:#92400e}
[data-finding-level="info"]{color:#475569}
[data-impact-relation]{color:#2563eb}
[data-impact-object]{font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
[data-impact-detail]{color:#64748b}
[data-policy-blocked="yes"]{color:#b91c1c}
[data-policy-blocked="no"]{color:#15803d}
.outcome{display:flex;gap:12px;margin:0 0 8px;font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px}
th,td{border:1px solid #e2e8f0;padding:5px 8px;text-align:left}
th{background:#f1f5f9;color:#475569;font-weight:600}
.guard{margin:8px 0 0;color:#64748b;font-size:12px}
</style>
