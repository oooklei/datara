<!--
  R4-SYNC：同步组件表单验证页（RED/原型态）。
  权威范围：docs/increments/2026-10-16-纠偏重构实施计划-执行附录.md §6 R4 行
  + 客户要求 #2（选源/目标连接 → 探查表字段 → 生成初始映射 → 用户调整 → 随工作流版本保存 → 预览/运行）。
  契约语义源：docs/increments/R4-SYNC-API-contract-pending.md（Codex 草案）。
  边界：独立验证页，不进正式菜单；服务端契约全部经 services/rebuild/syncComponentApi
  （后端接入前抛 R4_SYNC_NOT_WIRED，UI 统一状态栏提示）；列建议等纯前端逻辑可真实运行。
  消费面：契约 11 方法（R4_SYNC_CONTRACT_METHODS）全部具备按钮 + 结果区；
  未接线结果区恒为空态（el-table empty-text / v-if 空提示），取值一律在 guard 回调内部完成。
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

    <!-- ① 连接与对象选择（源/目标三元组） -->
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
      <el-form inline size="small" class="r4-sync-form">
        <el-form-item label="目标连接"><el-input v-model.number="target.datasourceId" style="width: 90px" /></el-form-item>
        <el-form-item label="目标 schema"><el-input v-model="target.schema" style="width: 120px" /></el-form-item>
        <el-form-item label="目标表"><el-input v-model="target.table" style="width: 140px" /></el-form-item>
        <el-form-item label="候选 schema"><el-input v-model="targetCandidateSchemas" style="width: 120px" placeholder="逗号分隔" /></el-form-item>
        <el-form-item>
          <el-button size="small" data-testid="r4-sync-probe-target" @click="onProbeTarget">探查目标候选</el-button>
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
          <el-table :data="sourceColumns" size="small" empty-text="（未接线 — probe 后端接入前恒为空）" max-height="200">
            <el-table-column prop="ordinal" label="#" width="50" />
            <el-table-column prop="name" label="列名" />
            <el-table-column prop="type" label="类型" width="110" />
            <el-table-column prop="nullable" label="可空" width="60" />
          </el-table>
        </el-col>
        <el-col :span="12">
          <div class="r4-sync-sub-head">目标列（探查）</div>
          <el-table :data="targetColumns" size="small" empty-text="（未接线 — probe 后端接入前恒为空）" max-height="200">
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
        </el-form-item>
      </el-form>
      <el-form inline size="small" class="r4-sync-form">
        <el-form-item label="planId"><el-input v-model.number="planRef.planId" style="width: 90px" /></el-form-item>
        <el-form-item label="planVersion"><el-input v-model.number="planRef.planVersion" style="width: 80px" /></el-form-item>
        <el-form-item label="planDigest"><el-input v-model="planRef.planDigest" style="width: 140px" /></el-form-item>
        <el-form-item>
          <el-button size="small" data-testid="r4-sync-preview" @click="onPreview">预览</el-button>
          <el-button size="small" data-testid="r4-sync-run" @click="onRun">运行</el-button>
        </el-form-item>
      </el-form>
      <div class="r4-sync-note">保存版本结果（planId/version/digest/诊断）与预览结果渲染于 ⑤；运行结果渲染于 ⑥。</div>
    </div>

    <!-- ④ 能力矩阵（草案 §2 capabilities） -->
    <div class="r4-sync-panel">
      <div class="r4-sync-panel-head">
        <span>④ 能力矩阵（草案 §2 capabilities：允许的转换/写模式等服务端声明）</span>
        <span><el-button size="small" data-testid="r4-sync-capabilities" @click="onCapabilities">查询能力声明</el-button></span>
      </div>
      <el-table
        :data="capabilityRows"
        size="small"
        border
        max-height="200"
        empty-text="（未接线 — getCapabilities 后端接入前恒为空）"
        data-testid="r4-sync-capabilities-table"
      >
        <el-table-column prop="key" label="能力项" width="240" show-overflow-tooltip />
        <el-table-column prop="value" label="值" show-overflow-tooltip />
      </el-table>
    </div>

    <!-- ⑤ 计划读取 / 预览结果（草案 §2/§3.2 plans 与 preview） -->
    <div class="r4-sync-panel">
      <div class="r4-sync-panel-head">
        <span>⑤ 计划读取 / 预览结果（草案 §2/§3.2：GET 计划 · 预览仅返回列元数据与统计，禁止回传源数据样本值）</span>
        <span><el-button size="small" data-testid="r4-sync-get-plan" @click="onGetPlan">读取计划</el-button></span>
      </div>
      <template v-if="planDetail">
        <el-descriptions :column="4" size="small" border data-testid="r4-sync-plan-detail">
          <el-descriptions-item label="planId">{{ planDetail.planId }}</el-descriptions-item>
          <el-descriptions-item label="version">{{ planDetail.version }}</el-descriptions-item>
          <el-descriptions-item label="planDigest">{{ planDetail.planDigest }}</el-descriptions-item>
          <el-descriptions-item label="mode">{{ planDetail.mode }}</el-descriptions-item>
          <el-descriptions-item label="strategy">{{ planDetail.strategy }}</el-descriptions-item>
          <el-descriptions-item label="writeMode">{{ planDetail.writeMode }}</el-descriptions-item>
          <el-descriptions-item label="targetPolicy">{{ planDetail.targetPolicy }}</el-descriptions-item>
          <el-descriptions-item label="映射行数">{{ planDetail.mapping.length }}</el-descriptions-item>
        </el-descriptions>
        <div class="r4-sync-sub-head">服务端重验诊断（字段级稳定错误码）</div>
        <el-table
          :data="planDetail.diagnostics"
          size="small"
          border
          max-height="140"
          empty-text="（未接线 — getPlan 后端接入前恒为空）"
          data-testid="r4-sync-plan-diagnostics"
        >
          <el-table-column prop="field" label="字段" width="160" />
          <el-table-column prop="code" label="错误码" width="140" />
          <el-table-column prop="message" label="说明" show-overflow-tooltip />
        </el-table>
      </template>
      <div v-else class="r4-sync-note" data-testid="r4-sync-plan-empty">读取计划结果：恒为空（getPlan 后端接入前）。</div>

      <div class="r4-sync-sub-head">预览结果（来自 ③「预览」按钮）</div>
      <template v-if="previewResult">
        <el-descriptions :column="4" size="small" border data-testid="r4-sync-preview-detail">
          <el-descriptions-item label="planId">{{ previewResult.planId }}</el-descriptions-item>
          <el-descriptions-item label="planVersion">{{ previewResult.planVersion }}</el-descriptions-item>
          <el-descriptions-item label="planDigest">{{ previewResult.planDigest }}</el-descriptions-item>
          <el-descriptions-item label="rowCountEstimate">{{ previewResult.rowCountEstimate }}</el-descriptions-item>
        </el-descriptions>
        <el-row :gutter="12" class="r4-sync-cols">
          <el-col :span="12">
            <div class="r4-sync-sub-head">预览源列元数据</div>
            <el-table
              :data="previewResult.sourceColumns"
              size="small"
              border
              max-height="160"
              empty-text="（未接线 — previewPlan 后端接入前恒为空）"
              data-testid="r4-sync-preview-source-cols"
            >
              <el-table-column prop="ordinal" label="#" width="50" />
              <el-table-column prop="name" label="列名" />
              <el-table-column prop="type" label="类型" width="100" />
              <el-table-column prop="nullable" label="可空" width="60" />
            </el-table>
          </el-col>
          <el-col :span="12">
            <div class="r4-sync-sub-head">预览目标列元数据</div>
            <el-table
              :data="previewResult.targetColumns"
              size="small"
              border
              max-height="160"
              empty-text="（未接线 — previewPlan 后端接入前恒为空）"
              data-testid="r4-sync-preview-target-cols"
            >
              <el-table-column prop="ordinal" label="#" width="50" />
              <el-table-column prop="name" label="列名" />
              <el-table-column prop="type" label="类型" width="100" />
              <el-table-column prop="nullable" label="可空" width="60" />
            </el-table>
          </el-col>
        </el-row>
        <div class="r4-sync-sub-head">预览映射摘要</div>
        <el-table
          :data="previewResult.mappingSummary"
          size="small"
          border
          max-height="140"
          empty-text="（未接线 — previewPlan 后端接入前恒为空）"
          data-testid="r4-sync-preview-mapping"
        >
          <el-table-column prop="targetOrdinal" label="目标序号" width="90" />
          <el-table-column prop="operation" label="操作" width="90" />
          <el-table-column prop="sourceColumn" label="源列" width="140" />
          <el-table-column prop="targetColumn" label="目标列" width="140" />
          <el-table-column prop="constantValue" label="常量值" show-overflow-tooltip />
        </el-table>
      </template>
      <div v-else class="r4-sync-note" data-testid="r4-sync-preview-empty">预览结果：恒为空（previewPlan 后端接入前）。</div>
    </div>

    <!-- ⑥ 运行观测（草案 §2/§4 run / attempt / cancel） -->
    <div class="r4-sync-panel">
      <div class="r4-sync-panel-head">
        <span>⑥ 运行观测（草案 §2/§4：run 汇总 / attempt 明细 / 取消）</span>
        <span>
          <el-button size="small" data-testid="r4-sync-get-run" @click="onGetRun">查询运行</el-button>
          <el-button size="small" data-testid="r4-sync-get-attempt" @click="onGetAttempt">查询 attempt</el-button>
          <el-button size="small" type="danger" plain data-testid="r4-sync-cancel" @click="onCancelRun">取消运行</el-button>
        </span>
      </div>
      <el-form inline size="small" class="r4-sync-form">
        <el-form-item label="runId"><el-input v-model.number="runRef.runId" style="width: 100px" /></el-form-item>
        <el-form-item label="attemptId"><el-input v-model.number="runRef.attemptId" style="width: 90px" /></el-form-item>
      </el-form>
      <template v-if="runSummary">
        <el-descriptions :column="5" size="small" border data-testid="r4-sync-run-detail">
          <el-descriptions-item label="runId">{{ runSummary.runId }}</el-descriptions-item>
          <el-descriptions-item label="status">{{ runSummary.status }}</el-descriptions-item>
          <el-descriptions-item label="attemptId">{{ runSummary.attemptId }}</el-descriptions-item>
          <el-descriptions-item label="startedAt">{{ runSummary.startedAt ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="finishedAt">{{ runSummary.finishedAt ?? '—' }}</el-descriptions-item>
        </el-descriptions>
        <div class="r4-sync-sub-head">运行汇总六类行计数（runPlan 创建 / getRun 查询共用此区）</div>
        <el-table :data="countRows(runSummary.counts)" size="small" border max-height="180" data-testid="r4-sync-run-counts">
          <el-table-column prop="label" label="指标" width="220" />
          <el-table-column prop="value" label="行数" width="120" />
        </el-table>
      </template>
      <div v-else class="r4-sync-note" data-testid="r4-sync-run-empty">运行汇总：恒为空（runPlan/getRun 后端接入前）。</div>

      <template v-if="attemptDetail">
        <el-descriptions :column="4" size="small" border data-testid="r4-sync-attempt-detail">
          <el-descriptions-item label="runId">{{ attemptDetail.runId }}</el-descriptions-item>
          <el-descriptions-item label="attemptId">{{ attemptDetail.attemptId }}</el-descriptions-item>
          <el-descriptions-item label="status">{{ attemptDetail.status }}</el-descriptions-item>
          <el-descriptions-item label="checkpointRef">{{ attemptDetail.checkpointRef ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="errorCode">{{ attemptDetail.errorCode ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="createdAt">{{ attemptDetail.createdAt }}</el-descriptions-item>
          <el-descriptions-item label="finishedAt">{{ attemptDetail.finishedAt ?? '—' }}</el-descriptions-item>
        </el-descriptions>
        <div class="r4-sync-sub-head">attempt 明细行计数</div>
        <el-table :data="countRows(attemptDetail.counts)" size="small" border max-height="180" data-testid="r4-sync-attempt-counts">
          <el-table-column prop="label" label="指标" width="220" />
          <el-table-column prop="value" label="行数" width="120" />
        </el-table>
      </template>
      <div v-else class="r4-sync-note" data-testid="r4-sync-attempt-empty">attempt 明细：恒为空（getAttempt 后端接入前）。</div>

      <div v-if="cancelResult" class="r4-sync-note" data-testid="r4-sync-cancel-result">
        取消请求：accepted={{ cancelResult.accepted }}，status={{ cancelResult.status }}
      </div>
      <div v-else class="r4-sync-note" data-testid="r4-sync-cancel-empty">取消结果：恒为空（cancelRun 后端接入前）。</div>
    </div>

    <!-- ⑦ checkpoint 与恢复（草案 §2 checkpoint / resume） -->
    <div class="r4-sync-panel">
      <div class="r4-sync-panel-head">
        <span>⑦ checkpoint 与恢复（草案 §2：opaque checkpoint 不含凭据或源行 payload）</span>
        <span>
          <el-button size="small" data-testid="r4-sync-get-checkpoint" @click="onGetCheckpoint">读取 checkpoint</el-button>
          <el-button size="small" data-testid="r4-sync-resume" @click="onResumeRun">恢复运行</el-button>
        </span>
      </div>
      <el-form inline size="small" class="r4-sync-form">
        <el-form-item label="checkpointRef">
          <el-input v-model="resumeCheckpointRef" style="width: 220px" placeholder="恢复目标 checkpoint 引用" />
        </el-form-item>
      </el-form>
      <template v-if="checkpointDetail">
        <el-descriptions :column="3" size="small" border data-testid="r4-sync-checkpoint-detail">
          <el-descriptions-item label="runId">{{ checkpointDetail.runId }}</el-descriptions-item>
          <el-descriptions-item label="attemptId">{{ checkpointDetail.attemptId }}</el-descriptions-item>
          <el-descriptions-item label="planDigest">{{ checkpointDetail.planDigest }}</el-descriptions-item>
          <el-descriptions-item label="sourceIdentity">{{ formatIdentity(checkpointDetail.sourceIdentity) }}</el-descriptions-item>
          <el-descriptions-item label="checkpoint（opaque，截断展示）">{{ truncateOpaque(checkpointDetail.checkpoint) }}</el-descriptions-item>
        </el-descriptions>
        <div class="r4-sync-sub-head">watermarkRule（增量边界；首运行策略已固化进 plan digest）</div>
        <el-descriptions :column="3" size="small" border data-testid="r4-sync-checkpoint-watermark">
          <el-descriptions-item label="watermarkColumn">{{ checkpointDetail.watermarkRule.watermarkColumn }}</el-descriptions-item>
          <el-descriptions-item label="comparison">{{ checkpointDetail.watermarkRule.comparison }}</el-descriptions-item>
          <el-descriptions-item label="initialPolicy">{{ checkpointDetail.watermarkRule.initialPolicy }}</el-descriptions-item>
          <el-descriptions-item label="lowerBound">{{ checkpointDetail.watermarkRule.lowerBound ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="upperBound">{{ checkpointDetail.watermarkRule.upperBound ?? '—' }}</el-descriptions-item>
          <el-descriptions-item label="边界含等号">
            lowerInclusive={{ checkpointDetail.watermarkRule.lowerInclusive }}，upperInclusive={{ checkpointDetail.watermarkRule.upperInclusive }}
          </el-descriptions-item>
        </el-descriptions>
      </template>
      <div v-else class="r4-sync-note" data-testid="r4-sync-checkpoint-empty">checkpoint：恒为空（getCheckpoint 后端接入前）。</div>

      <template v-if="resumeSummary">
        <div class="r4-sync-sub-head">恢复运行结果（resumeRun 返回 run 汇总）</div>
        <el-descriptions :column="4" size="small" border data-testid="r4-sync-resume-detail">
          <el-descriptions-item label="runId">{{ resumeSummary.runId }}</el-descriptions-item>
          <el-descriptions-item label="status">{{ resumeSummary.status }}</el-descriptions-item>
          <el-descriptions-item label="attemptId">{{ resumeSummary.attemptId }}</el-descriptions-item>
          <el-descriptions-item label="finishedAt">{{ resumeSummary.finishedAt ?? '—' }}</el-descriptions-item>
        </el-descriptions>
        <el-table :data="countRows(resumeSummary.counts)" size="small" border max-height="160" data-testid="r4-sync-resume-counts">
          <el-table-column prop="label" label="指标" width="220" />
          <el-table-column prop="value" label="行数" width="120" />
        </el-table>
      </template>
      <div v-else class="r4-sync-note" data-testid="r4-sync-resume-empty">恢复结果：恒为空（resumeRun 后端接入前）。</div>
    </div>

    <el-alert type="info" :closable="false" show-icon data-testid="r4-sync-status-bar" :title="statusText" />
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import {
  R4_SYNC_CONTRACT_METHODS,
  R4_SYNC_NOT_WIRED,
  createSyncComponentContract,
  suggestInitialMapping,
  type SyncAttemptDetail,
  type SyncCheckpoint,
  type SyncColumn,
  type SyncMappingItem,
  type SyncObjectIdentity,
  type SyncPlanDraft,
  type SyncPlanVersion,
  type SyncPreviewResult,
  type SyncProbeRequest,
  type SyncRunCounts,
  type SyncRunStatus,
  type SyncRunSummary,
  type SyncStrategy,
  type SyncWriteMode,
} from '../../../../services/rebuild/syncComponentApi'

defineOptions({ name: 'SyncFormValidationView' })

const contract = createSyncComponentContract()
const contractMethodCount = R4_SYNC_CONTRACT_METHODS.length

const form = reactive({ projectId: 1, strategy: 'full' as SyncStrategy, writeMode: 'append' as SyncWriteMode })
const source = reactive<SyncObjectIdentity>({ datasourceId: 1, schema: 'public', table: '' })
/** 目标侧三元组（客户 #2 选源/目标连接；草案 §3.1 target-led 探查带显式候选 schema） */
const target = reactive<SyncObjectIdentity>({ datasourceId: 1, schema: 'public', table: '' })
const targetCandidateSchemas = ref('public')
const sourceColumns = ref<SyncColumn[]>([])
const targetColumns = ref<SyncColumn[]>([])
const mapping = ref<SyncMappingItem[]>([])

/** 计划标识（③ 预览/运行 与 ⑤ getPlan 共用；默认 draft 占位，后端接入后为真实 planId/version/digest） */
const planRef = reactive({ planId: 0, planVersion: 1, planDigest: 'draft' })
/** 运行标识（⑥ getRun/getAttempt/cancel 与 ⑦ resume 共用） */
const runRef = reactive({ runId: 1, attemptId: 1 })
const resumeCheckpointRef = ref('')

/* 消费面结果区：未接线契约恒为空态；本地样例/映射建议真实运行 */
const capabilities = ref<Record<string, unknown> | null>(null)
const planDetail = ref<(SyncPlanDraft & SyncPlanVersion) | null>(null)
const previewResult = ref<SyncPreviewResult | null>(null)
const runSummary = ref<SyncRunSummary | null>(null)
const attemptDetail = ref<SyncAttemptDetail | null>(null)
const cancelResult = ref<{ accepted: boolean; status: SyncRunStatus } | null>(null)
const checkpointDetail = ref<SyncCheckpoint | null>(null)
const resumeSummary = ref<SyncRunSummary | null>(null)

/** capabilities 简表行：扁平化 key/value（嵌套结构 JSON 序列化展示） */
const capabilityRows = computed(() =>
  Object.entries(capabilities.value ?? {}).map(([key, value]) => ({
    key,
    value: typeof value === 'string' ? value : JSON.stringify(value),
  })),
)

/** 六类行计数固定展示顺序（草案 §2/§4 run 汇总口径） */
const RUN_COUNT_FIELDS: Array<{ key: keyof SyncRunCounts; label: string }> = [
  { key: 'sourceRead', label: 'sourceRead（源读取）' },
  { key: 'targetWritten', label: 'targetWritten（目标写入）' },
  { key: 'inserted', label: 'inserted（插入）' },
  { key: 'updated', label: 'updated（更新）' },
  { key: 'skipped', label: 'skipped（跳过）' },
  { key: 'failed', label: 'failed（失败）' },
]

function countRows(counts: SyncRunCounts | null | undefined): Array<{ label: string; value: number }> {
  if (!counts) return []
  return RUN_COUNT_FIELDS.map((field) => ({ label: field.label, value: counts[field.key] }))
}

function formatIdentity(identity: SyncObjectIdentity | null | undefined): string {
  return identity ? `${identity.datasourceId} / ${identity.schema}.${identity.table}` : '—'
}

/** opaque checkpoint 只截断展示，避免整串长 token 撑爆布局 */
function truncateOpaque(value: string): string {
  return value.length > 32 ? `${value.slice(0, 32)}…（截断）` : value
}

const statusText = ref('待操作')

/** NOT_WIRED 统一落状态栏语义：提示 + 不中断交互；需要返回值的取值一律在 fn 回调内部完成 */
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
  return guard(async () => {
    const result = await contract.probe(request)
    sourceColumns.value = result.columns
  }, '探查表字段')
}

/** target-led 探查：按显式候选 schema 查目标列（草案 §3.1，同名跨 schema 返回全部候选不自动选中） */
function onProbeTarget() {
  const request: SyncProbeRequest = {
    projectId: form.projectId,
    mode: 'target_table',
    source: { ...source },
    candidateSchemas: targetCandidateSchemas.value.split(/[,\s]+/).filter(Boolean),
  }
  return guard(async () => {
    const result = await contract.probe(request)
    targetColumns.value = result.columns
  }, '探查目标候选')
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
  return guard(async () => {
    const saved = await contract.savePlan({
      projectId: form.projectId,
      mode: 'source_table',
      source: { ...source },
      target: { ...target },
      strategy: form.strategy,
      writeMode: form.writeMode,
      targetPolicy: 'existing_only',
      mapping: mapping.value,
    })
    planDetail.value = null
    planRef.planId = saved.planId
    planRef.planVersion = saved.version
    planRef.planDigest = saved.planDigest
  }, '保存计划版本')
}

function onPreview() {
  return guard(async () => {
    previewResult.value = await contract.previewPlan(planRef.planId, planRef.planVersion, planRef.planDigest, form.projectId)
  }, '计划预览')
}

function onRun() {
  return guard(async () => {
    runSummary.value = await contract.runPlan({
      projectId: form.projectId,
      planId: planRef.planId,
      planVersion: planRef.planVersion,
      planDigest: planRef.planDigest,
      idempotencyKey: `red-${Date.now()}`,
    })
  }, '创建运行')
}

function onCapabilities() {
  return guard(async () => {
    capabilities.value = await contract.getCapabilities(form.projectId)
  }, '查询能力声明')
}

function onGetPlan() {
  return guard(async () => {
    planDetail.value = await contract.getPlan(planRef.planId, form.projectId)
  }, '读取计划')
}

function onGetRun() {
  return guard(async () => {
    runSummary.value = await contract.getRun(runRef.runId, form.projectId)
  }, '查询运行')
}

function onGetAttempt() {
  return guard(async () => {
    attemptDetail.value = await contract.getAttempt(runRef.runId, runRef.attemptId, form.projectId)
  }, '查询 attempt')
}

function onCancelRun() {
  return guard(async () => {
    cancelResult.value = await contract.cancelRun(runRef.runId, form.projectId)
  }, '取消运行')
}

function onGetCheckpoint() {
  return guard(async () => {
    checkpointDetail.value = await contract.getCheckpoint(runRef.runId, form.projectId)
  }, '读取 checkpoint')
}

function onResumeRun() {
  return guard(async () => {
    resumeSummary.value = await contract.resumeRun(runRef.runId, form.projectId, {
      idempotencyKey: `red-resume-${Date.now()}`,
      checkpointRef: resumeCheckpointRef.value,
    })
  }, '恢复运行')
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

.r4-sync-note {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}
</style>
