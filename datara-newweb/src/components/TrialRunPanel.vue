<script setup lang="ts">
/**
 * INC4-FE-7（WBS 4.5 / s269 派令）：trial 试运行面板（八能力 UI 承接）。
 *
 * 三段布局（data-part）：snapshot（草稿快照）→ options（六选项 WF-15~WF-20）→ result（运行+输出+转正式）。
 * - 草稿快照：生成/刷新（POST snapshot，幂等同 digest 直返）；无快照禁跑；
 * - 六选项：nodeCodes 逗号分隔（空=不限）/ startNode（空=不限）/ testVariables JSON /
 *   dependencyMock JSON / dryRun / sqlPrecheck；JSON 文本本地编辑，提交时解析
 *   （非法 JSON → ElMessage.warning 且不触发 run）；
 * - 结果：instance_id/status/taskCount + plan（DRY_RUN 仅计划）；输出面 stats/logs/variables
 *   （DRY_RUN instance_id=0 无输出面——刷新入口不渲染）；转正式 remark → promoteResult。
 *
 * store：trialRun（loadSeq 时序守卫 + options 归一化均由 store 承接，面板只做表单语义）。
 * 挂接说明：本组件为独立面板，宿主接驳（WorkflowGraphWorkbench 侧栏）留 FE-6 验收后
 * 补丁票；禁碰约束（FE-6 候验收面）——本文件不 import 画布件。
 */
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { useTrialRunStore } from '../stores/trialRun'
import type { TrialDependencyMockStatus } from '../services/rebuild/trialApi'

const props = defineProps<{ projectId: number; definitionId: number }>()

const store = useTrialRunStore()

/** JSON 文本本地编辑态（换 definition/项目时随 open 重置；提交时解析落地 store.options） */
const testVariablesText = ref('{}')
const dependencyMockText = ref('{}')
const remarkText = ref('')

watch(
  () => [props.projectId, props.definitionId] as const,
  () => {
    testVariablesText.value = '{}'
    dependencyMockText.value = '{}'
    remarkText.value = ''
    store.open(props.projectId, props.definitionId)
  },
  { immediate: true },
)

/** WF-15：nodeCodes 逗号分隔文本 ↔ 数组（空 = 不限） */
const nodeCodesText = computed<string>({
  get: () => store.options.nodeCodes.join(','),
  set: (v) => {
    store.options.nodeCodes = v
      .split(/[,,]/)
      .map((s) => s.trim())
      .filter(Boolean)
  },
})

/** JSON 文本 → 对象；空文本视为 {}；非对象/非法 JSON → 提示并返回 null（阻止 run） */
function parseObject<T extends Record<string, unknown>>(text: string, label: string): T | null {
  const t = text.trim()
  if (t === '') return {} as T
  try {
    const v = JSON.parse(t) as unknown
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) return v as T
    ElMessage.warning(`${label}需为 JSON 对象（{"键": 值}）`)
    return null
  } catch {
    ElMessage.warning(`${label}不是合法 JSON`)
    return null
  }
}

async function onRun(): Promise<void> {
  const tv = parseObject<Record<string, unknown>>(testVariablesText.value, '测试变量')
  if (tv === null) return
  const dm = parseObject<Record<string, TrialDependencyMockStatus>>(dependencyMockText.value, '依赖模拟')
  if (dm === null) return
  store.options.testVariables = tv
  store.options.dependencyMock = dm
  await store.run()
}

async function onPromote(): Promise<void> {
  const remark = remarkText.value.trim()
  await store.promote(remark === '' ? undefined : remark)
}

/** DRY_RUN（instance_id=0）无输出面：输出刷新入口与空态提示均跳过 */
const canRefreshOutput = computed(() => store.runResult !== null && store.runResult.status !== 'DRY_RUN')
</script>

<template>
  <section class="trp" data-part="trial-panel">
    <header class="trp-head">
      <h3 class="trp-title">试运行</h3>
      <span class="trp-def">定义 #{{ props.definitionId }}</span>
    </header>

    <div v-if="store.lastError" class="trp-err" data-test="err-bar">{{ store.lastError }}</div>

    <!-- ① 草稿快照 -->
    <div class="trp-part" data-part="snapshot">
      <div class="trp-part-head">
        <span>草稿快照</span>
        <button class="trp-btn" data-test="snapshot-btn" :disabled="store.running" @click="store.createSnapshot()">
          {{ store.snapshot ? '刷新快照' : '生成快照' }}
        </button>
      </div>
      <p v-if="store.snapshot === null" class="trp-hint" data-test="no-snap">
        尚未生成快照：快照锚定当前草稿节点/边，运行前必须生成。
      </p>
      <div v-else class="trp-snap" data-test="snap-info">
        <span>snap={{ store.snapshot.snapshotId }}</span>
        <span class="mono">{{ store.snapshot.snapshotDigest }}</span>
        <span :class="['trp-status', store.snapshot.status.toLowerCase()]">{{ store.snapshot.status }}</span>
      </div>
    </div>

    <!-- ② 六选项（WF-15~WF-20） -->
    <div class="trp-part" data-part="options">
      <div class="trp-grid">
        <label class="trp-field">
          <span>指定节点（逗号分隔，空=不限）</span>
          <input v-model="nodeCodesText" data-test="nodecodes" placeholder="如 n1,n2" />
        </label>
        <label class="trp-field">
          <span>起始节点（空=不限）</span>
          <input v-model="store.options.startNode" data-test="start-node" placeholder="从该节点正向可达" />
        </label>
        <label class="trp-field trp-field-wide">
          <span>测试变量覆盖（JSON，{} = 不覆盖）</span>
          <textarea v-model="testVariablesText" data-test="test-vars" rows="2"></textarea>
        </label>
        <label class="trp-field trp-field-wide">
          <span>依赖模拟（JSON：dependency_id → SUCCEEDED/FAILED）</span>
          <textarea v-model="dependencyMockText" data-test="dep-mock" rows="2"></textarea>
        </label>
      </div>
      <label class="trp-check">
        <input v-model="store.options.dryRun" type="checkbox" data-test="dry-run" />
        <span>Dry Run（仅出执行计划，不落副作用）</span>
      </label>
      <label class="trp-check">
        <input v-model="store.options.sqlPrecheck" type="checkbox" data-test="sql-precheck" />
        <span>SQL 预检查（执行前校验表/字段可访问性）</span>
      </label>
    </div>

    <!-- ③ 运行 + 结果 + 输出 + 转正式 -->
    <div class="trp-part" data-part="result">
      <div class="trp-actions">
        <button
          class="trp-btn primary"
          data-test="run-btn"
          :disabled="store.running || store.snapshot === null"
          @click="onRun"
        >
          {{ store.running ? '运行中…' : '运行' }}
        </button>
        <button
          v-if="canRefreshOutput"
          class="trp-btn"
          data-test="refresh-btn"
          :disabled="store.running"
          @click="store.refreshOutput()"
        >
          刷新输出
        </button>
      </div>

      <p v-if="store.runResult === null" class="trp-hint" data-test="no-result">尚未运行：生成快照后点击「运行」。</p>
      <div v-else class="trp-run" data-test="run-info">
        <span>instance_id={{ store.runResult.instanceId }}</span>
        <span :class="['trp-status', store.runResult.status.toLowerCase()]">{{ store.runResult.status }}</span>
        <span>任务 {{ store.runResult.taskCount }}</span>
      </div>
      <div v-if="store.runResult !== null && store.runResult.plan" class="trp-plan" data-test="plan-list">
        <span class="trp-hint">执行计划（{{ store.runResult.plan.length }} 节点）：</span>
        <span class="mono">{{ store.runResult.plan.join(' → ') }}</span>
      </div>

      <div v-if="store.output !== null" class="trp-out" data-test="out-panel">
        <div class="trp-stats" data-test="out-stats">
          <span>成功 {{ store.output.stats.successCount }}</span>
          <span>失败 {{ store.output.stats.failedCount }}</span>
          <span>跳过 {{ store.output.stats.skippedCount }}</span>
        </div>
        <p v-if="store.output.logs.length === 0" class="trp-hint" data-test="out-empty">暂无日志输出</p>
        <ul v-else class="trp-logs" data-test="out-logs">
          <li v-for="log in store.output.logs" :key="log.taskId">{{ log.taskCode }}（{{ log.logs.length }} 条日志）</li>
        </ul>
        <ul v-if="store.output.variables.length > 0" class="trp-vars" data-test="out-vars">
          <li v-for="v in store.output.variables" :key="v.name">{{ v.name }} = {{ String(v.resolvedValue) }}</li>
        </ul>
      </div>
      <p v-else-if="canRefreshOutput" class="trp-hint" data-test="no-output">点击「刷新输出」拉取日志/变量/统计。</p>

      <div class="trp-promote">
        <input v-model="remarkText" data-test="remark" placeholder="转正式备注（可选）" />
        <button
          class="trp-btn primary"
          data-test="promote-btn"
          :disabled="store.running || store.runResult === null"
          @click="onPromote"
        >
          转正式
        </button>
      </div>
      <div v-if="store.promoteResult !== null" class="trp-promote-info" data-test="promote-info">
        已转正式：version={{ store.promoteResult.version }}（{{ store.promoteResult.status }}）
        <template v-if="store.promoteResult.idempotent">（幂等命中，直返既有版本）</template>
      </div>
    </div>
  </section>
</template>

<style scoped>
.trp {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 12.5px;
  color: var(--text-1, #1f2937);
}
.trp-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
}
.trp-title {
  font-size: 13.5px;
  font-weight: 600;
  margin: 0;
}
.trp-def {
  font-size: 11px;
  color: var(--text-3, #9ca3af);
}
.trp-err {
  border: 1px solid #fecaca;
  background: #fef2f2;
  color: #b91c1c;
  border-radius: 4px;
  padding: 6px 8px;
  font-size: 11.5px;
}
.trp-part {
  border: 1px solid var(--border, #e5e7eb);
  border-radius: 6px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.trp-part-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.trp-btn {
  border: 1px solid var(--border-strong, #d1d5db);
  background: #fff;
  border-radius: 4px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
}
.trp-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.trp-btn.primary {
  border-color: var(--primary-color, #2563eb);
  background: var(--primary-color, #2563eb);
  color: #fff;
}
.trp-hint {
  font-size: 11px;
  color: var(--text-3, #9ca3af);
  margin: 0;
  line-height: 1.6;
}
.trp-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.trp-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11.5px;
  color: var(--text-2, #4b5563);
}
.trp-field-wide {
  grid-column: 1 / -1;
}
.trp-field input,
.trp-field textarea,
.trp-promote input {
  border: 1px solid var(--border-strong, #d1d5db);
  border-radius: 4px;
  padding: 5px 8px;
  font-size: 12px;
  outline: none;
}
.trp-field input:focus,
.trp-field textarea:focus {
  border-color: var(--primary-color, #2563eb);
}
.mono {
  font-family: ui-monospace, Menlo, Consolas, monospace;
  font-size: 11px;
}
.trp-check {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--text-2, #4b5563);
  cursor: pointer;
}
.trp-snap,
.trp-run {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 11.5px;
  flex-wrap: wrap;
}
.trp-status {
  padding: 0 6px;
  border-radius: 3px;
  font-size: 11px;
}
.trp-status.active {
  background: #fef3c7;
  color: #92400e;
}
.trp-status.succeeded {
  background: #dcfce7;
  color: #166534;
}
.trp-status.failed {
  background: #fee2e2;
  color: #991b1b;
}
.trp-status.dry_run {
  background: #e0e7ff;
  color: #3730a3;
}
.trp-plan {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.trp-actions {
  display: flex;
  gap: 8px;
}
.trp-stats {
  display: flex;
  gap: 12px;
  font-size: 11.5px;
}
.trp-logs,
.trp-vars {
  margin: 0;
  padding-left: 16px;
  font-size: 11.5px;
  line-height: 1.7;
}
.trp-promote {
  display: flex;
  gap: 8px;
}
.trp-promote input {
  flex: 1;
}
.trp-promote-info {
  font-size: 11.5px;
  color: var(--text-2, #4b5563);
}
</style>
