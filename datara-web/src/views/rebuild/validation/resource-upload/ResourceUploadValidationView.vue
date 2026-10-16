<!--
  R4-RESOURCE：脚本/SQL 资源上传验证页（RED/原型态）。
  权威范围：docs/increments/2026-10-16-纠偏重构实施计划-执行附录.md §6 R4 行
  + 客户要求 #4（SQL 组件上传 SQL 文件；Python/Shell 上传脚本）
  + 纠偏设计 §5.3（资源有身份有版本、大小/类型校验、工作流版本绑定确定版本、禁隐式 latest）。
  边界：独立验证页，不进正式菜单；服务端契约全部经 services/rebuild/resourceApi
  （后端接入前抛 R4_RESOURCE_NOT_WIRED，UI 统一状态栏提示）；本地预校验真实运行。
-->
<template>
  <div class="r4-res-page">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      data-testid="r4-resource-red-banner"
      title="R4 RESOURCE RED 骨架（原型态）— rebuild/resources 后端契约未接入，所有服务端 I/O 返回 R4_RESOURCE_NOT_WIRED"
    />

    <el-descriptions :column="3" size="small" border class="r4-res-context">
      <el-descriptions-item label="客户要求">#4 SQL/Python/Shell 上传与确定版本绑定</el-descriptions-item>
      <el-descriptions-item label="硬约束">不可变版本；运行时禁止隐式 latest</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（全部未接线）</el-descriptions-item>
    </el-descriptions>

    <!-- ① 上传 -->
    <div class="r4-res-panel">
      <div class="r4-res-panel-head"><span>① 上传资源（本地预校验真实运行；服务端保存未接线）</span></div>
      <el-form inline size="small" class="r4-res-form">
        <el-form-item label="项目ID"><el-input v-model.number="form.projectId" style="width: 90px" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.kind" style="width: 100px">
            <el-option label="sql" value="sql" />
            <el-option label="python" value="python" />
            <el-option label="shell" value="shell" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <input type="file" :accept="acceptExtensions" data-testid="r4-resource-file" @change="onFilePicked" />
        </el-form-item>
        <el-form-item>
          <el-button size="small" type="primary" data-testid="r4-resource-upload" :disabled="!picked" @click="onUpload">上传</el-button>
        </el-form-item>
      </el-form>
      <el-alert
        v-if="precheckDiagnostics.length > 0"
        type="error"
        :closable="false"
        show-icon
        data-testid="r4-resource-precheck"
        :title="`预校验未通过：${precheckDiagnostics.map((d) => d.message).join('；')}`"
      />
      <div v-else-if="picked" class="r4-res-picked" data-testid="r4-resource-precheck-ok">
        已选：{{ picked?.filename }}（{{ picked?.sizeBytes }} 字节）— 预校验通过
      </div>
    </div>

    <!-- ② 版本与绑定 -->
    <div class="r4-res-panel">
      <div class="r4-res-panel-head"><span>② 资源版本 / 确定版本绑定（禁隐式 latest）</span></div>
      <el-form inline size="small" class="r4-res-form">
        <el-form-item label="资源ID"><el-input v-model.number="bind.resourceId" style="width: 90px" /></el-form-item>
        <el-form-item>
          <el-button size="small" data-testid="r4-resource-list" @click="onList">资源列表</el-button>
          <el-button size="small" data-testid="r4-resource-versions" @click="onVersions">版本列表</el-button>
        </el-form-item>
      </el-form>
      <el-form inline size="small" class="r4-res-form">
        <el-form-item label="工作流ID"><el-input v-model.number="bind.workflowId" style="width: 80px" /></el-form-item>
        <el-form-item label="工作流版本"><el-input v-model.number="bind.workflowVersion" style="width: 80px" /></el-form-item>
        <el-form-item label="任务编码"><el-input v-model="bind.taskId" style="width: 120px" /></el-form-item>
        <el-form-item label="资源版本">
          <!-- 显式数字版本；界面不提供 latest 选项（类型上亦排除） -->
          <el-input v-model.number="bind.resourceVersion" style="width: 90px" />
        </el-form-item>
        <el-form-item>
          <el-button size="small" type="primary" data-testid="r4-resource-bind" @click="onBind">绑定确定版本</el-button>
        </el-form-item>
      </el-form>
    </div>

    <el-alert type="info" :closable="false" show-icon data-testid="r4-resource-status-bar" :title="statusText" />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import {
  R4_RESOURCE_CONTRACT_METHODS,
  R4_RESOURCE_NOT_WIRED,
  RESOURCE_ALLOWED_EXTENSIONS,
  createResourceContract,
  validateUploadDraft,
  type ResourceDraftDiagnostic,
  type ResourceKind,
} from '../../../../services/rebuild/resourceApi'

defineOptions({ name: 'ResourceUploadValidationView' })

const contract = createResourceContract()
const contractMethodCount = R4_RESOURCE_CONTRACT_METHODS.length

const form = reactive({ projectId: 1, kind: 'sql' as ResourceKind })
const bind = reactive({ resourceId: 1, workflowId: 1, workflowVersion: 1, taskId: '', resourceVersion: 1 })
const picked = ref<{ filename: string; sizeBytes: number } | null>(null)
const precheckDiagnostics = ref<ResourceDraftDiagnostic[]>([])
const statusText = ref('待操作')

const acceptExtensions = computed(() => RESOURCE_ALLOWED_EXTENSIONS[form.kind].join(','))

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互 */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value =
        err instanceof Error && err.message.startsWith(R4_RESOURCE_NOT_WIRED)
          ? `${label}：后端未接线（${R4_RESOURCE_NOT_WIRED.split(':')[0]}）`
          : `${label} 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

function onFilePicked(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  picked.value = file ? { filename: file.name, sizeBytes: file.size } : null
  precheckDiagnostics.value = picked.value
    ? validateUploadDraft(form.kind, picked.value.filename, picked.value.sizeBytes)
    : []
  if (picked.value && precheckDiagnostics.value.length === 0) {
    statusText.value = `已选 ${picked.value.filename}（本地预校验通过；上传仍需后端接线）`
  }
}

function onUpload() {
  if (!picked.value) return
  return guard(
    () => contract.uploadResource({ projectId: form.projectId, kind: form.kind, filename: picked.value!.filename, sizeBytes: picked.value!.sizeBytes }),
    '上传资源',
  )
}

function onList() {
  return guard(() => contract.listResources(form.projectId, form.kind), '资源列表')
}

function onVersions() {
  return guard(() => contract.listResourceVersions(bind.resourceId, form.projectId), '版本列表')
}

function onBind() {
  return guard(
    () =>
      contract.bindResourceVersion({
        projectId: form.projectId,
        workflowId: bind.workflowId,
        workflowVersion: bind.workflowVersion,
        taskId: bind.taskId,
        resourceId: bind.resourceId,
        resourceVersion: bind.resourceVersion,
      }),
    '绑定确定版本',
  )
}
</script>

<style scoped>
.r4-res-page {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.r4-res-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}

.r4-res-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.r4-res-form {
  margin-bottom: 0;
}

.r4-res-picked {
  font-size: 12px;
  color: var(--el-color-success);
}
</style>
