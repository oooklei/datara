<script setup lang="ts">
/**
 * WfDependPanel：DAG 工作台「依赖」页签 —— 依赖配置（R4 换绑，FE-06）。
 * - 数据源：dependencyApi（/api/v1/rebuild/dependency），流内视角单入口
 * - 九类源选择器（A2 v2.1 冻结：workflow|task|file|table_state|external_task）
 * - 组内 AND/OR 策略 + 组间 group_relation（AND|OR）
 * - 失败策略（policy）选择（fail|waiting|timeout，后端 PERSISTABLE 默认）
 * - 预览/保存/预演走服务端契约
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  composeExpressionDraft,
  createDependencyContract,
  type DependencyCondition,
  type DependencyGroup,
} from '../../../services/rebuild/dependencyApi'

const props = defineProps<{ docId: string }>()

const contract = createDependencyContract()
const DEFAULT_PROJECT_ID = 1
const DEFAULT_WORKFLOW_VERSION = 1

/** A2 v2.1 冻结 kind 枚举（九类源）；dependencyApi.ts 当前实现 workflow/task */
const ALL_KINDS = ['workflow', 'task', 'file', 'table_state', 'external_task'] as const
type DependencyKind = (typeof ALL_KINDS)[number]
const IMPLEMENTED_KINDS: readonly DependencyKind[] = ['workflow', 'task']

/** 组间关系（group_relation，A2 §7.8） */
const GROUP_RELATIONS = ['AND', 'OR'] as const

/** 失败策略（policy.failure_policy，A2 §7.3） */
const FAILURE_POLICIES = ['fail', 'waiting', 'timeout'] as const
type FailurePolicy = (typeof FAILURE_POLICIES)[number]

/** 依赖配置表单 */
const form = ref({
  projectId: DEFAULT_PROJECT_ID,
  workflowId: 0,
  workflowVersion: DEFAULT_WORKFLOW_VERSION,
  taskId: '',
  kind: 'workflow' as DependencyKind,
  groupRelation: 'AND' as typeof GROUP_RELATIONS[number],
  failurePolicy: 'fail' as FailurePolicy,
})

/** 条件组 */
const groups = ref<DependencyGroup[]>([])

/** 候选工作流 / 任务 */
const candidateWorkflows = ref<Array<{ workflowId: number; name: string; latestVersion: number }>>([])
const workflowTasks = ref<Array<{ taskCode: string; name: string }>>([])

/** 预览结果 */
const previewExpression = ref('')
const previewVerdict = ref('')
const previewResolved = ref<Array<{ upstreamWorkflowId: number; upstreamTaskCode?: string; windowStart: string; windowEnd: string; verdict: string }>>([])

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

function newCondition(): DependencyCondition {
  return { upstreamWorkflowId: 1, dateRange: { periodType: 'day', beginOffset: -1, endOffset: -1 } }
}

function newGroup(): DependencyGroup {
  return { join: 'AND', conditions: [newCondition()] }
}

function addGroup() {
  groups.value.push(newGroup())
}

function addCondition(group: DependencyGroup) {
  group.conditions.push(newCondition())
}

function removeGroup(index: number) {
  if (groups.value.length > 1) groups.value.splice(index, 1)
}

function removeCondition(group: DependencyGroup, index: number) {
  if (group.conditions.length > 1) group.conditions.splice(index, 1)
}

/** 本地表达式草稿（终判走服务端） */
const draft = computed(() => {
  if (groups.value.length === 0) return ''
  return composeExpressionDraft(groups.value)
})

/** 加载候选工作流 */
async function loadWorkflows() {
  try {
    candidateWorkflows.value = await contract.listCandidateWorkflows(form.value.projectId)
  } catch (e) {
    ElMessage.error('候选工作流加载失败：' + errMsg(e))
  }
}

/** 加载工作流任务 */
async function loadTasks() {
  try {
    workflowTasks.value = await contract.listWorkflowTasks(form.value.projectId, form.value.workflowId, form.value.workflowVersion)
  } catch (e) {
    ElMessage.error('任务加载失败：' + errMsg(e))
  }
}

/** 预览最终表达式 */
async function onPreview() {
  if (groups.value.length === 0) {
    ElMessage.warning('请先添加条件组')
    return
  }
  try {
    const result = await contract.previewExpression(
      form.value.projectId,
      form.value.workflowId,
      form.value.workflowVersion,
      form.value.taskId,
      groups.value,
    )
    previewExpression.value = result.expression
    previewVerdict.value = result.verdict
    previewResolved.value = result.resolved.map((r) => ({
      upstreamWorkflowId: r.upstreamWorkflowId,
      upstreamTaskCode: r.upstreamTaskCode,
      windowStart: r.windowStart,
      windowEnd: r.windowEnd,
      verdict: r.verdict,
    }))
  } catch (e) {
    ElMessage.error('预览失败：' + errMsg(e))
  }
}

/** 保存依赖配置 */
async function onSave() {
  if (groups.value.length === 0) {
    ElMessage.warning('请先添加条件组')
    return
  }
  try {
    await contract.saveDependency({
      projectId: form.value.projectId,
      workflowId: form.value.workflowId,
      workflowVersion: form.value.workflowVersion,
      taskId: form.value.taskId,
      groups: groups.value,
    })
    ElMessage.success('依赖配置已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + errMsg(e))
  }
}

/** 预演判定 */
async function onEvaluate() {
  if (groups.value.length === 0) {
    ElMessage.warning('请先添加条件组')
    return
  }
  try {
    const result = await contract.evaluateDependency({
      projectId: form.value.projectId,
      workflowId: form.value.workflowId,
      workflowVersion: form.value.workflowVersion,
      taskId: form.value.taskId,
      groups: groups.value,
    })
    previewExpression.value = result.expression
    previewVerdict.value = result.verdict
    previewResolved.value = result.resolved.map((r) => ({
      upstreamWorkflowId: r.upstreamWorkflowId,
      upstreamTaskCode: r.upstreamTaskCode,
      windowStart: r.windowStart,
      windowEnd: r.windowEnd,
      verdict: r.verdict,
    }))
  } catch (e) {
    ElMessage.error('预演失败：' + errMsg(e))
  }
}

onMounted(() => {
  // 初始化一个空条件组
  if (groups.value.length === 0) groups.value.push(newGroup())
})
</script>

<template>
  <div class="wdp">
    <div class="wdp-bar">
      <span class="wdp-title">依赖配置</span>
      <span class="wdp-hint">流内视角：配置当前工作流任务的上游依赖条件</span>
    </div>

    <!-- 九类源选择器 -->
    <div class="wdp-section">
      <div class="wdp-section-title">依赖源类型（A2 v2.1 冻结九类）</div>
      <div class="wdp-kinds">
        <label v-for="kind in ALL_KINDS" :key="kind" class="wdp-kind" :class="{ implemented: IMPLEMENTED_KINDS.includes(kind) }">
          <input type="radio" :value="kind" v-model="form.kind" :disabled="!IMPLEMENTED_KINDS.includes(kind)" />
          <span class="wdp-kind-label">{{ kind }}</span>
          <span v-if="!IMPLEMENTED_KINDS.includes(kind)" class="wdp-kind-status">待接线</span>
        </label>
      </div>
    </div>

    <!-- 依赖目标 -->
    <div class="wdp-section">
      <div class="wdp-section-title">依赖目标</div>
      <div class="wdp-form-row">
        <label class="wdp-label">项目ID</label>
        <input v-model.number="form.projectId" class="wdp-input" style="width: 80px" />
        <label class="wdp-label">工作流ID</label>
        <input v-model.number="form.workflowId" class="wdp-input" style="width: 80px" />
        <label class="wdp-label">版本</label>
        <input v-model.number="form.workflowVersion" class="wdp-input" style="width: 60px" />
        <label class="wdp-label">任务编码</label>
        <input v-model="form.taskId" class="wdp-input" style="width: 120px" placeholder="task_xxx" />
      </div>
    </div>

    <!-- 条件组编辑 -->
    <div class="wdp-section">
      <div class="wdp-section-title">
        条件组（组内 AND/OR；组间 {{ form.groupRelation }}）
        <button class="wdp-btn" @click="addGroup">加条件组</button>
      </div>
      <div v-for="(group, gi) in groups" :key="gi" class="wdp-group">
        <div class="wdp-group-head">
          <span>组 {{ gi + 1 }}</span>
          <select v-model="group.join" class="wdp-select" style="width: 80px">
            <option value="AND">AND</option>
            <option value="OR">OR</option>
          </select>
          <button class="wdp-btn" @click="addCondition(group)">加条件</button>
          <button class="wdp-btn danger" :disabled="groups.length <= 1" @click="removeGroup(gi)">删组</button>
        </div>
        <table class="wdp-tbl">
          <thead>
            <tr>
              <th>上游工作流ID</th>
              <th>上游任务编码</th>
              <th>周期</th>
              <th>起始偏移</th>
              <th>结束偏移</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(cond, ci) in group.conditions" :key="ci">
              <td><input v-model.number="cond.upstreamWorkflowId" class="wdp-input" style="width: 100px" /></td>
              <td>
                <input v-model="cond.upstreamTaskCode" class="wdp-input" style="width: 120px" placeholder="0=整工作流" />
              </td>
              <td>
                <select v-model="cond.dateRange.periodType" class="wdp-select" style="width: 90px">
                  <option value="hour">hour</option>
                  <option value="day">day</option>
                  <option value="week">week</option>
                  <option value="month">month</option>
                </select>
              </td>
              <td><input v-model.number="cond.dateRange.beginOffset" class="wdp-input" style="width: 80px" /></td>
              <td><input v-model.number="cond.dateRange.endOffset" class="wdp-input" style="width: 80px" /></td>
              <td>
                <button class="wdp-btn danger" :disabled="group.conditions.length <= 1" @click="removeCondition(group, ci)">删</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 组间关系 + 失败策略 -->
    <div class="wdp-section">
      <div class="wdp-section-title">组间关系与失败策略</div>
      <div class="wdp-form-row">
        <label class="wdp-label">组间关系</label>
        <select v-model="form.groupRelation" class="wdp-select" style="width: 100px">
          <option v-for="r in GROUP_RELATIONS" :key="r" :value="r">{{ r }}</option>
        </select>
        <label class="wdp-label">失败策略</label>
        <select v-model="form.failurePolicy" class="wdp-select" style="width: 100px">
          <option v-for="p in FAILURE_POLICIES" :key="p" :value="p">{{ p }}</option>
        </select>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="wdp-section">
      <div class="wdp-actions">
        <button class="wdp-btn primary" @click="onPreview">预览最终表达式</button>
        <button class="wdp-btn primary" @click="onSave">保存依赖</button>
        <button class="wdp-btn" @click="onEvaluate">预演判定</button>
        <button class="wdp-btn" @click="loadWorkflows">加载候选工作流</button>
        <button class="wdp-btn" @click="loadTasks">加载任务</button>
      </div>
    </div>

    <!-- 表达式草稿 -->
    <div v-if="draft" class="wdp-section">
      <div class="wdp-section-title">表达式草稿（本地）</div>
      <div class="wdp-draft">{{ draft }}</div>
    </div>

    <!-- 预览结果 -->
    <div v-if="previewExpression" class="wdp-section">
      <div class="wdp-section-title">预览结果</div>
      <div class="wdp-preview">
        <div><strong>表达式：</strong>{{ previewExpression }}</div>
        <div><strong>判定：</strong>{{ previewVerdict }}</div>
        <table v-if="previewResolved.length" class="wdp-tbl">
          <thead>
            <tr><th>上游工作流</th><th>上游任务</th><th>窗口开始</th><th>窗口结束</th><th>判定</th></tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in previewResolved" :key="i">
              <td>{{ r.upstreamWorkflowId }}</td>
              <td>{{ r.upstreamTaskCode ?? '-' }}</td>
              <td>{{ r.windowStart }}</td>
              <td>{{ r.windowEnd }}</td>
              <td>{{ r.verdict }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- 候选工作流 / 任务 -->
    <div v-if="candidateWorkflows.length || workflowTasks.length" class="wdp-section">
      <div class="wdp-section-title">候选工作流 / 任务</div>
      <div class="wdp-candidates">
        <div v-if="candidateWorkflows.length" class="wdp-candidate-col">
          <div class="wdp-candidate-title">候选工作流</div>
          <table class="wdp-tbl">
            <thead><tr><th>ID</th><th>名称</th><th>最新版本</th></tr></thead>
            <tbody>
              <tr v-for="w in candidateWorkflows" :key="w.workflowId">
                <td>{{ w.workflowId }}</td>
                <td>{{ w.name }}</td>
                <td>{{ w.latestVersion }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div v-if="workflowTasks.length" class="wdp-candidate-col">
          <div class="wdp-candidate-title">任务</div>
          <table class="wdp-tbl">
            <thead><tr><th>编码</th><th>名称</th></tr></thead>
            <tbody>
              <tr v-for="t in workflowTasks" :key="t.taskCode">
                <td>{{ t.taskCode }}</td>
                <td>{{ t.name }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wdp{padding:14px 16px}
.wdp-bar{display:flex;align-items:center;gap:10px;margin-bottom:12px}
.wdp-title{font-weight:700;font-size:14px}
.wdp-hint{font-size:11px;color:var(--text-3)}
.wdp-section{margin-bottom:14px;padding:10px;border:1px solid var(--border);border-radius:var(--radius-sm)}
.wdp-section-title{font-weight:600;font-size:12.5px;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.wdp-kinds{display:flex;gap:8px;flex-wrap:wrap}
.wdp-kind{display:flex;align-items:center;gap:4px;padding:4px 10px;border:1px solid var(--border-strong);border-radius:var(--radius-sm);cursor:pointer}
.wdp-kind.implemented{border-color:var(--primary);color:var(--primary)}
.wdp-kind input{accent-color:var(--primary)}
.wdp-kind-label{font-size:12px}
.wdp-kind-status{font-size:10px;color:var(--text-3);background:var(--bg);padding:1px 4px;border-radius:var(--radius-sm)}
.wdp-form-row{display:flex;align-items:center;gap:8px;margin-bottom:8px;flex-wrap:wrap}
.wdp-label{font-size:12px;color:var(--text-2)}
.wdp-input{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:5px 8px;font-size:12px;outline:none;background:#fff;color:var(--text)}
.wdp-input:focus{border-color:var(--primary)}
.wdp-select{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:5px 8px;font-size:12px;background:#fff;color:var(--text)}
.wdp-group{border:1px dashed var(--border-strong);border-radius:var(--radius-sm);padding:8px;margin-bottom:8px}
.wdp-group-head{display:flex;align-items:center;gap:8px;margin-bottom:6px;font-size:12px}
.wdp-tbl{width:100%;border-collapse:collapse;font-size:12px}
.wdp-tbl th{text-align:left;font-weight:600;color:var(--text-3);font-size:11px;padding:5px 6px;border-bottom:1px solid var(--border)}
.wdp-tbl td{padding:5px 6px;border-bottom:1px solid var(--border)}
.wdp-tbl tbody tr:hover{background:var(--bg)}
.wdp-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 10px;font-size:12px;cursor:pointer;color:var(--text-2)}
.wdp-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.wdp-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.4)}
.wdp-btn:hover{border-color:var(--primary);color:var(--primary)}
.wdp-btn:disabled{opacity:0.5;cursor:not-allowed}
.wdp-actions{display:flex;gap:8px;flex-wrap:wrap}
.wdp-draft{font-family:ui-monospace,Consolas,monospace;font-size:12px;padding:8px;background:var(--bg);border-radius:var(--radius-sm);white-space:pre-wrap}
.wdp-preview{font-size:12px}
.wdp-candidates{display:flex;gap:12px}
.wdp-candidate-col{flex:1}
.wdp-candidate-title{font-weight:600;font-size:12px;margin-bottom:4px}
</style>
