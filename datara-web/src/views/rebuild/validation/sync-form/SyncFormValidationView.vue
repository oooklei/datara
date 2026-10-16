<!--
  R4-SYNC：同步组件表单验证页（RED/原型态）。
  权威范围：docs/increments/2026-10-16-纠偏重构实施计划-执行附录.md §6 R4 行
  + 客户要求 #2（选源/目标连接 → 探查表字段 → 生成初始映射 → 用户调整 → 随工作流版本保存 → 预览/运行）。
  契约语义源：docs/increments/R4-SYNC-API-contract-pending.md（Codex 草案）。
  边界：独立验证页，不进正式菜单；服务端契约全部经 services/rebuild/syncComponentApi
  （后端接入前抛 R4_SYNC_NOT_WIRED，UI 统一状态栏提示）；列建议等纯前端逻辑可真实运行。
-->
<template>
  <div class="r4-sync-page">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      data-testid="r4-sync-red-banner"
      title="R4 SYNC RED 骨架（原型态）— rebuild/sync 后端契约未接入，所有服务端 I/O 返回 R4_SYNC_NOT_WIRED"
    />

    <el-descriptions :column="3" size="small" border class="r4-sync-context">
      <el-descriptions-item label="客户要求">#2 同步组件表单（探查/映射/版本/预览运行）</el-descriptions-item>
      <el-descriptions-item label="契约语义源">R4-SYNC-API-contract-pending（Codex 草案）</el-descriptions-item>
      <el-descriptions-item label="契约方法">{{ contractMethodCount }} 项（全部未接线）</el-descriptions-item>
    </el-descriptions>

    <!-- ① 连接与对象选择 -->
    <div class="r4-sync-panel">
      <div class="r4-sync-panel-head"><span>① 连接与对象选择（datasource_id / schema / table 三元组）</span></div>
      <el-form inline size="small" class="r4-sync-form">
        <el-form-item label="项目ID"><el-input v-model.number="form.projectId" style="width: 90px" /></el-form-item>
        <el-form-item label="源连接"><el-input v-model.number="source.datasourceId" style="width: 90px" /></el-form-item>
        <el-form-item label="源 schema"><el-input v-model="source.schema" style="width: 120px" /></el-form-item>
        <el-form-item label="源表"><el-input v-model="source.table" style="width: 140px" /></el-form-item>
        <el-form-item>
          <el-button size="small" type="primary" data-testid="r4-sync-probe" @click="onProbe">探查表字段</el-button>
        </el-form-item>
      </el-form>
    </div>

    <!-- ② 列与映射 -->
    <div class="r4-sync-panel">
      <div class="r4-sync-panel-head">
        <span>② 字段映射（本地建议可真实运行；保存/预览走未接线契约）</span>
        <span>
          <el-button size="small" data-testid="r4-sync-load-sample" @click="onLoadSample">加载本地样例列集</el-button>
          <el-button size="small" type="primary" data-testid="r4-sync-suggest" :disabled="sourceColumns.length === 0 || targetColumns.length === 0" @click="onSuggest">生成初始映射</el-button>
        </span>
      </div>
      <el-alert type="info" :closable="false" show-icon title="样例列集仅驱动映射编辑演示，非后端数据；探查结果在后端接入前恒为空" />
      <el-row :gutter="12" class="r4-sync-cols">
        <el-col :span="12">
          <div class="r4-sync-sub-head">源列（探查）</div>
          <el-table :data="sourceColumns" size="small" empty-text="（未接线：探查被拒绝）" max-height="200">
            <el-table-column prop="ordinal" label="#" width="50" />
            <el-table-column prop="name" label="列名" />
            <el-table-column prop="type" label="类型" width="110" />
            <el-table-column prop="nullable" label="可空" width="60" />
          </el-table>
        </el-col>
        <el-col :span="12">
          <div class="r4-sync-sub-head">目标列（探查）</div>
          <el-table :data="targetColumns" size="small" empty-text="（未接线：探查被拒绝）" max-height="200">
            <el-table-column prop="ordinal" label="#" width="50" />
            <el-table-column prop="name" label="列名" />
            <el-table-column prop="type" label="类型" width="110" />
            <el-table-column prop="nullable" label="可空" width="60" />
          </el-table>
        </el-col>
      </el-row>
      <div class="r4-sync-sub-head">映射（用户调整）</div>
      <el-table :data="mapping" size="small" empty-text="（先探查/加载样例，再生成初始映射）" max-height="220">
        <el-table-column prop="targetOrdinal" label="目标序号" width="80" />
        <el-table-column label="操作" width="110">
          <template #default="{ row }">
            <el-select v-model="row.operation" size="small">
              <el-option label="map" value="map" />
              <el-option label="constant" value="constant" />
              <el-option label="ignore" value="ignore" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="源列" width="150">
          <template #default="{ row }"><el-input v-model="row.sourceColumn" size="small" :disabled="row.operation !== 'map'" /></template>
        </el-table-column>
        <el-table-column label="目标列" width="150">
          <template #default="{ row }"><el-input v-model="row.targetColumn" size="small" /></template>
        </el-table-column>
        <el-table-column label="常量值">
          <template #default="{ row }"><el-input v-model="row.constantValue" size="small" :disabled="row.operation !== 'constant'" /></template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ③ 保存/预览/运行 -->
    <div class="r4-sync-panel">
      <div class="r4-sync-panel-head"><span>③ 版本保存 / 预览 / 运行（服务端契约未接线）</span></div>
      <el-form inline size="small" class="r4-sync-form">
        <el-form-item label="策略">
          <el-select v-model="form.strategy" style="width: 120px">
            <el-option label="full" value="full" />
            <el-option label="incremental" value="incremental" />
          </el-select>
        </el-form-item>
        <el-form-item label="写模式">
          <el-select v-model="form.writeMode" style="width: 150px">
            <el-option label="append" value="append" />
            <el-option label="upsert" value="upsert" />
            <el-option label="replace_table" value="replace_table" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button size="small" data-testid="r4-sync-save" @click="onSavePlan">保存版本</el-button>
          <el-button size="small" data-testid="r4-sync-preview" @click="onPreview">预览</el-button>
          <el-button size="small" data-testid="r4-sync-run" @click="onRun">运行</el-button>
        </el-form-item>
      </el-form>
    </div>

    <el-alert type="info" :closable="false" show-icon data-testid="r4-sync-status-bar" :title="statusText" />
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import {
  R4_SYNC_CONTRACT_METHODS,
  R4_SYNC_NOT_WIRED,
  createSyncComponentContract,
  suggestInitialMapping,
  type SyncColumn,
  type SyncMappingItem,
  type SyncObjectIdentity,
  type SyncProbeRequest,
  type SyncStrategy,
  type SyncWriteMode,
} from '../../../../services/rebuild/syncComponentApi'

defineOptions({ name: 'SyncFormValidationView' })

const contract = createSyncComponentContract()
const contractMethodCount = R4_SYNC_CONTRACT_METHODS.length

const form = reactive({ projectId: 1, strategy: 'full' as SyncStrategy, writeMode: 'append' as SyncWriteMode })
const source = reactive<SyncObjectIdentity>({ datasourceId: 1, schema: 'public', table: '' })
const sourceColumns = ref<SyncColumn[]>([])
const targetColumns = ref<SyncColumn[]>([])
const mapping = ref<SyncMappingItem[]>([])

const statusText = ref('待操作')

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互 */
function guard<T>(fn: () => Promise<T>, label: string): Promise<void> {
  statusText.value = `${label}…`
  return fn()
    .then(() => {
      statusText.value = `${label} 完成`
    })
    .catch((err: unknown) => {
      statusText.value =
        err instanceof Error && err.message.startsWith(R4_SYNC_NOT_WIRED)
          ? `${label}：后端未接线（${R4_SYNC_NOT_WIRED.split(':')[0]}）`
          : `${label} 失败：${err instanceof Error ? err.message : String(err)}`
    })
}

function onProbe() {
  const request: SyncProbeRequest = { projectId: form.projectId, mode: 'source_table', source: { ...source } }
  return guard(() => contract.probe(request), '探查表字段')
}

/** 本地样例列集：仅驱动映射编辑演示（标注非后端数据） */
function onLoadSample() {
  sourceColumns.value = [
    { ordinal: 1, name: 'id', type: 'bigint', nullable: false },
    { ordinal: 2, name: 'name', type: 'varchar', nullable: true, precision: 64 },
    { ordinal: 3, name: 'amount', type: 'decimal', nullable: true, precision: 18, scale: 2 },
  ]
  targetColumns.value = [
    { ordinal: 1, name: 'ID', type: 'bigint', nullable: false },
    { ordinal: 2, name: 'NAME', type: 'varchar', nullable: true, precision: 64 },
    { ordinal: 3, name: 'AMOUNT', type: 'decimal', nullable: true, precision: 18, scale: 2 },
  ]
  statusText.value = '已加载本地样例列集（非后端数据）'
}

function onSuggest() {
  mapping.value = suggestInitialMapping(sourceColumns.value, targetColumns.value)
  statusText.value = `已生成初始映射建议 ${mapping.value.length} 行（可在表内调整）`
}

function onSavePlan() {
  return guard(
    () =>
      contract.savePlan({
        projectId: form.projectId,
        mode: 'source_table',
        source: { ...source },
        target: { datasourceId: source.datasourceId, schema: source.schema, table: source.table },
        strategy: form.strategy,
        writeMode: form.writeMode,
        targetPolicy: 'existing_only',
        mapping: mapping.value,
      }),
    '保存计划版本',
  )
}

function onPreview() {
  return guard(() => contract.previewPlan(0, 1, 'draft', form.projectId), '计划预览')
}

function onRun() {
  return guard(
    () => contract.runPlan({ projectId: form.projectId, planId: 0, planVersion: 1, planDigest: 'draft', idempotencyKey: `red-${Date.now()}` }),
    '创建运行',
  )
}
</script>

<style scoped>
.r4-sync-page {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.r4-sync-panel {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 8px;
}

.r4-sync-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.r4-sync-form {
  margin-bottom: 0;
}

.r4-sync-cols {
  margin-top: 8px;
}

.r4-sync-sub-head {
  font-size: 12px;
  font-weight: 600;
  margin: 8px 0 4px;
}
</style>
