<!--
  R4-DEPENDENCY：依赖组件表单验证页（GREEN 已接线，FE-01 修订 2026-10-19）。
  权威范围：docs/increments/2026-10-16-纠偏重构实施计划-执行附录.md §6 R4 行
  + 客户要求 #5（参考 DolphinScheduler：选工作流/任务、周期/日期范围、AND/OR 条件、
  执行前预览最终表达式）+ 纠偏设计 §5.3（执行前显示最终依赖表达式和解析结果）。
  边界：独立验证页，不进正式菜单；服务端契约全部经 services/rebuild/dependencyApi
  （P1 冻结词形 R4_DEPENDENCY_CONTRACT_METHODS，5 方法接线，包络 {code,msg,data}）；
  表达式草稿为本地纯前端逻辑。横幅状态词表见 services/rebuild/bannerStatus.ts。
-->
<template>
  <div class="r4-dep-page">
    <el-alert
      :type="bannerType"
      :closable="false"
      show-icon
      data-testid="r4-dependency-green-banner"
      :title="bannerTitle"
    />

    <el-descriptions :column="3" size="small" border class="r4-dep-context">
      <el-descriptions-item label="客户要求">#5 依赖表单参考 DolphinScheduler</el-descriptions-item>
      <el-descriptions-item label="判定面">满足 / 失败 / 超时 / 等待</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（已接线）</el-descriptions-item>
    </el-descriptions>

    <!-- ① 依赖目标（本工作流/任务） -->
    <div class="r4-dep-panel">
      <div class="r4-dep-panel-head"><span>① 本工作流 / 任务（依赖配置随工作流版本保存）</span></div>
      <el-form inline size="small" class="r4-dep-form">
        <el-form-item label="项目ID"><el-input v-model.number="form.projectId" style="width: 90px" /></el-form-item>
        <el-form-item label="工作流ID"><el-input v-model.number="form.workflowId" style="width: 90px" /></el-form-item>
        <el-form-item label="版本"><el-input v-model.number="form.workflowVersion" style="width: 80px" /></el-form-item>
        <el-form-item label="任务编码"><el-input v-model="form.taskId" style="width: 140px" /></el-form-item>
      </el-form>
    </div>

    <!-- ② 条件组编辑（AND/OR） -->
    <div class="r4-dep-panel">
      <div class="r4-dep-panel-head">
        <span>② 依赖条件组（组间 AND；组内按所选 AND/OR 连接）</span>
        <el-button size="small" data-testid="r4-dependency-add-group" @click="addGroup">加条件组</el-button>
      </div>
      <div v-for="(group, gi) in groups" :key="gi" class="r4-dep-group">
        <div class="r4-dep-group-head">
          <span>组 {{ gi + 1 }}</span>
          <el-select v-model="group.join" size="small" style="width: 90px">
            <el-option label="AND" value="AND" />
            <el-option label="OR" value="OR" />
          </el-select>
          <el-button size="small" @click="addCondition(group)">加条件</el-button>
          <el-button size="small" type="danger" plain :disabled="groups.length <= 1" @click="groups.splice(gi, 1)">删组</el-button>
        </div>
        <el-table :data="group.conditions" size="small">
          <el-table-column label="上游工作流ID" width="130">
            <template #default="{ row }"><el-input v-model.number="row.upstreamWorkflowId" size="small" /></template>
          </el-table-column>
          <el-table-column label="上游任务(可选)" width="140">
            <template #default="{ row }"><el-input v-model="row.upstreamTaskCode" size="small" placeholder="整工作流" /></template>
          </el-table-column>
          <el-table-column label="周期" width="110">
            <template #default="{ row }">
              <el-select v-model="row.dateRange.periodType" size="small">
                <el-option label="hour" value="hour" />
                <el-option label="day" value="day" />
                <el-option label="week" value="week" />
                <el-option label="month" value="month" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="起始偏移" width="100">
            <template #default="{ row }"><el-input v-model.number="row.dateRange.beginOffset" size="small" /></template>
          </el-table-column>
          <el-table-column label="结束偏移" width="100">
            <template #default="{ row }"><el-input v-model.number="row.dateRange.endOffset" size="small" /></template>
          </el-table-column>
          <el-table-column width="70">
            <template #default="{ row }">
              <el-button size="small" type="danger" plain :disabled="group.conditions.length <= 1" @click="group.conditions.splice(group.conditions.indexOf(row), 1)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- ③ 预览与判定 -->
    <div class="r4-dep-panel">
      <div class="r4-dep-panel-head"><span>③ 执行前预览 / 保存 / 预演（表达式草稿为本地逻辑，终判走服务端）</span></div>
      <el-form inline size="small" class="r4-dep-form">
        <el-form-item>
          <el-button size="small" data-testid="r4-dependency-draft" @click="onDraft">生成表达式草稿（本地）</el-button>
          <el-button size="small" type="primary" data-testid="r4-dependency-preview" @click="onPreview">预览最终表达式</el-button>
          <el-button size="small" data-testid="r4-dependency-save" @click="onSave">保存依赖</el-button>
          <el-button size="small" data-testid="r4-dependency-evaluate" @click="onEvaluate">预演判定</el-button>
        </el-form-item>
      </el-form>
      <div v-if="draft" class="r4-dep-draft" data-testid="r4-dependency-draft-text">{{ draft }}</div>
    </div>

    <!-- ④ 候选工作流 / 任务（listCandidateWorkflows / listWorkflowTasks，复用①输入参数） -->
    <div class="r4-dep-panel">
      <div class="r4-dep-panel-head">
        <span>④ 候选工作流 / 任务（listCandidateWorkflows / listWorkflowTasks）</span>
        <span>
          <el-button size="small" data-testid="r4-dependency-load-workflows" @click="onLoadWorkflows">候选工作流加载</el-button>
          <el-button size="small" data-testid="r4-dependency-load-tasks" @click="onLoadTasks">任务加载</el-button>
        </span>
      </div>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-table :data="candidateWorkflows" size="small" empty-text="（未接线 — listCandidateWorkflows 后端接入前恒为空）" data-testid="r4-dependency-workflows-table">
            <el-table-column prop="workflowId" label="工作流ID" width="110" />
            <el-table-column prop="name" label="工作流名称" />
            <el-table-column prop="latestVersion" label="最新版本" width="100" />
          </el-table>
        </el-col>
        <el-col :span="12">
          <el-table :data="workflowTasks" size="small" empty-text="（未接线 — listWorkflowTasks 后端接入前恒为空）" data-testid="r4-dependency-tasks-table">
            <el-table-column prop="taskCode" label="任务编码" width="160" />
            <el-table-column prop="name" label="任务名称" />
          </el-table>
        </el-col>
      </el-row>
    </div>

    <el-alert type="info" :closable="false" show-icon data-testid="r4-dependency-status-bar" :title="statusText" />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import {
  R4_DEPENDENCY_CONTRACT_METHODS,
  R4_DEPENDENCY_NOT_WIRED,
  composeExpressionDraft,
  createDependencyContract,
  type DependencyCondition,
  type DependencyGroup,
} from '../../../../services/rebuild/dependencyApi'
import { bannerAlertType, bannerTitleFor } from '../../../../services/rebuild/bannerStatus'

defineOptions({ name: 'DependencyFormValidationView' })

const contract = createDependencyContract()
const contractMethodCount = R4_DEPENDENCY_CONTRACT_METHODS.length

/* 横幅状态词表（FE-01 单一事实源）：GREEN 已接线 */
const bannerTitle = bannerTitleFor(
  { code: 'R4', contractName: 'dependency', methodCount: contractMethodCount },
  'GREEN',
)
const bannerType = bannerAlertType('GREEN')

const form = reactive({ projectId: 1, workflowId: 1, workflowVersion: 1, taskId: '' })
const groups = ref<DependencyGroup[]>([])
const draft = ref('')
const statusText = ref('待操作')

/* 候选工作流 / 任务（字段按 listCandidateWorkflows / listWorkflowTasks 返回类型；后端接入前恒为空） */
interface CandidateWorkflow {
  workflowId: number
  name: string
  latestVersion: number
}

interface WorkflowTask {
  taskCode: string
  name: string
}

const candidateWorkflows = ref<CandidateWorkflow[]>([])
const workflowTasks = ref<WorkflowTask[]>([])

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

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互 */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value =
        err instanceof Error && err.message.startsWith(R4_DEPENDENCY_NOT_WIRED)
          ? `${label}：后端未接线（${R4_DEPENDENCY_NOT_WIRED.split(':')[0]}）`
          : `${label} 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

function onDraft() {
  draft.value = composeExpressionDraft(groups.value)
  statusText.value = '已生成本地表达式草稿（最终表达式以服务端 previewExpression 为准）'
}

function onPreview() {
  return guard(
    () => contract.previewExpression(form.projectId, form.workflowId, form.workflowVersion, form.taskId, groups.value),
    '预览最终表达式',
  )
}

function onSave() {
  return guard(
    () => contract.saveDependency({ projectId: form.projectId, workflowId: form.workflowId, workflowVersion: form.workflowVersion, taskId: form.taskId, groups: groups.value }),
    '保存依赖配置',
  )
}

function onEvaluate() {
  return guard(
    () => contract.evaluateDependency({ projectId: form.projectId, workflowId: form.workflowId, workflowVersion: form.workflowVersion, taskId: form.taskId, groups: groups.value }),
    '预演判定',
  )
}

function onLoadWorkflows() {
  return guard(async () => {
    candidateWorkflows.value = await contract.listCandidateWorkflows(form.projectId)
  }, '加载候选工作流')
}

function onLoadTasks() {
  return guard(async () => {
    workflowTasks.value = await contract.listWorkflowTasks(form.projectId, form.workflowId, form.workflowVersion)
  }, '加载工作流任务')
}
</script>

<style scoped>
.r4-dep-page {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.r4-dep-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}

.r4-dep-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.r4-dep-form {
  margin-bottom: 0;
}

.r4-dep-group {
  border: 1px dashed var(--el-border-color);
  border-radius: 4px;
  padding: 6px;
  margin-bottom: 8px;
}

.r4-dep-group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  font-size: 12px;
}

.r4-dep-draft {
  font-family: monospace;
  font-size: 12px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  padding: 8px;
  word-break: break-all;
}
</style>
