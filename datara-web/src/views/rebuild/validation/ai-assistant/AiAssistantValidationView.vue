<!--
  R8-B：AI 悬浮助手契约验证页（GREEN 前证据，P1-0 步骤 4）。
  权威范围：R8-A 八工具契约 v1 §2-§7（docs/increments/2026-10-17-R8-A八工具契约.md）
  + P1-0 实施计划步骤 4（自然语言→generate_sql→（授权确认）→run_sql→结果展示+解释）。
  边界：独立验证页，不进正式菜单（I11 融合）；mock 模式（无 LLM，隔离于 K1）走本目录
  mockAgent.ts 假 Agent；真实链路（R8-A 统一端点 + vanna_adapter）BE 接线（P1-3）后
  GREEN 横幅；授权确认为 UI 闸（勾选前不调用 run_sql），不改契约参数面。
-->
<template>
  <div class="r8a-page">
    <el-alert
      :type="bannerType"
      :closable="false"
      show-icon
      data-testid="r8a-red-banner"
      :title="bannerTitle"
    />

    <el-descriptions :column="3" size="small" border class="r8a-context">
      <el-descriptions-item label="流程链（P1-0 步骤 4）">自然语言 → generate_sql → 授权确认 → run_sql → 结果展示+解释</el-descriptions-item>
      <el-descriptions-item label="模式">
        <el-tag size="small" type="success" data-testid="r8a-mode-tag">MOCK（无 LLM）</el-tag>
        <el-tag size="small" type="info">LIVE（P1-5 后启用）</el-tag>
      </el-descriptions-item>
      <el-descriptions-item label="契约面">八工具 / 十类 page_context / §5 错误码 / §6 预算 / §4 审计回链</el-descriptions-item>
    </el-descriptions>

    <el-row :gutter="12">
      <el-col :span="12">
        <div class="r8a-panel">
          <div class="r8a-panel-head">
            <span>工具注册表（GET /api/rebuild/ai/tools，§2.4）</span>
            <el-button size="small" data-testid="r8a-registry-refresh" @click="refreshRegistry">刷新</el-button>
          </div>
          <el-table :data="registry" size="small" empty-text="（未加载）" max-height="320">
            <el-table-column prop="name" label="工具" width="170" />
            <el-table-column label="启用" width="70">
              <template #default="{ row }">
                <el-tag size="small" :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? 'enabled' : 'disabled' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="timeoutMs" label="超时ms" width="80" />
            <el-table-column label="重试" width="90">
              <template #default="{ row }">{{ row.retryPolicy.maxAttempts }}×{{ row.retryPolicy.backoffMs }}</template>
            </el-table-column>
            <el-table-column prop="description" label="说明" />
          </el-table>
        </div>
      </el-col>
      <el-col :span="12">
        <div class="r8a-panel">
          <div class="r8a-panel-head">
            <span>调用审计（§4：成功与失败均落，audit_id 回链）</span>
            <el-button size="small" data-testid="r8a-audit-clear" @click="clearAudit">清空</el-button>
          </div>
          <el-table :data="auditRows" size="small" empty-text="（暂无调用）" max-height="320">
            <el-table-column prop="auditId" label="audit_id" width="150" />
            <el-table-column prop="tool" label="工具" width="130" />
            <el-table-column label="结果" width="80">
              <template #default="{ row }">
                <el-tag size="small" :type="row.outcome === 'SUCCESS' ? 'success' : 'danger'">{{ row.outcome }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="errorCode" label="错误码" width="150" />
            <el-table-column prop="toolCallId" label="tool_call_id" />
          </el-table>
        </div>
      </el-col>
    </el-row>

    <el-alert type="info" :closable="false" show-icon data-testid="r8a-status-bar" :title="statusText" class="r8a-status" />

    <!-- 悬浮入口（R8-B 测试页内模拟悬浮助手入口） -->
    <div class="r8a-fab" data-testid="r8a-fab" title="悬浮助手（R8-B 测试入口）" @click="drawerVisible = true">
      <span>AI</span>
    </div>

    <!-- 悬浮助手抽屉：NL → generate_sql → 授权确认 → run_sql → 结果+解释 -->
    <el-drawer v-model="drawerVisible" title="R8-B 悬浮助手（mock 契约面）" size="46%" data-testid="r8a-drawer">
      <div class="r8a-drawer-body">
        <el-form label-width="110px" size="small">
          <el-form-item label="page_context">
            <el-select v-model="contextType" data-testid="r8a-context-type" style="width: 180px">
              <el-option v-for="t in R8A_CONTEXT_TYPES" :key="t" :label="t" :value="t" />
            </el-select>
            <el-input
              v-model="contextRefText"
              data-testid="r8a-context-ref"
              style="width: 300px; margin-left: 8px"
              placeholder='{"project_id":1,"table_name":"dw.dim_customer"}'
            />
          </el-form-item>
          <el-form-item label="自然语言">
            <el-input
              v-model="nlInput"
              data-testid="r8a-nl-input"
              type="textarea"
              :rows="2"
              placeholder="例：客户表有多少行数据 / 查询客户表的数据 / 最近的前 10 条订单表记录"
            />
          </el-form-item>
          <el-form-item label="">
            <el-button type="primary" size="small" data-testid="r8a-generate-btn" :disabled="!nlInput.trim()" @click="onGenerate">
              生成 SQL（mock 假 Agent）
            </el-button>
          </el-form-item>
          <el-form-item v-if="generatedSql" label="生成 SQL">
            <el-input :model-value="generatedSql" data-testid="r8a-generated-sql" type="textarea" :rows="2" readonly />
          </el-form-item>
          <el-form-item v-if="generatedExplanation" label="生成解释">
            <span class="r8a-explanation" data-testid="r8a-generated-explanation">{{ generatedExplanation }}</span>
          </el-form-item>
          <el-form-item v-if="generatedSql" label="授权确认">
            <el-checkbox v-model="confirmed" data-testid="r8a-confirm-checkbox">
              我确认经 R8-A 授权通道执行该 SQL（主权第二条：执行入口只接受授权通道）
            </el-checkbox>
            <el-button
              type="danger"
              size="small"
              data-testid="r8a-run-btn"
              :disabled="!confirmed"
              style="margin-left: 12px"
              @click="onRunSql"
            >
              执行 run_sql
            </el-button>
          </el-form-item>
        </el-form>

        <template v-if="runResult">
          <div class="r8a-panel">
            <div class="r8a-panel-head">
              <span>执行结果（run_sql §7.3）</span>
              <span class="r8a-meta" data-testid="r8a-run-meta">
                execution_id={{ runResult.executionId }} / row_count={{ runResult.rowCount }} / truncated={{ runResult.truncated }} / {{ runResult.durationMs }}ms
              </span>
            </div>
            <el-table :data="resultRows" size="small" max-height="240" data-testid="r8a-result-grid">
              <el-table-column
                v-for="(col, i) in runResult.columns"
                :key="col.name"
                :prop="String(i)"
                :label="`${col.name} (${col.type})`"
              />
            </el-table>
          </div>
          <el-alert
            type="success"
            :closable="false"
            show-icon
            data-testid="r8a-result-explanation"
            :title="`结果解释：${generatedExplanation}（共 ${runResult.rowCount} 行${runResult.truncated ? '，已按 row_limit 截断' : ''}）`"
            class="r8a-status"
          />
        </template>

        <el-alert
          v-if="lastError"
          type="error"
          :closable="false"
          show-icon
          data-testid="r8a-error-bar"
          :title="`信封错误：${lastError.code}（retryable=${lastError.retryable}）${lastError.message}`"
          class="r8a-status"
        />
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  R8A_CONTRACT_METHODS,
  R8A_CONTEXT_TYPES,
  R8A_TOOL_VERSION,
  type R8AContextType,
  type R8ARegistryEntry,
  type R8ARunSqlResult,
  type R8AToolCallError,
} from '../../../../services/rebuild/aiToolsApi'
import { createMockAgent, generateSqlMock, type MockAuditRecord } from './mockAgent'
import { bannerAlertType, bannerTitleFor } from '../../../../services/rebuild/bannerStatus'

/* GREEN 锚点（BE P1-3 桥接后接线；真实 API 调用由 createAiToolsContract 发起） */

const mockAgent = createMockAgent()

/* 横幅状态词表（FE-01 单一事实源）：GREEN 已接线 */
const bannerTitle = bannerTitleFor(
  {
    code: 'R8-A',
    contractName: 'ai',
    methodCount: R8A_CONTRACT_METHODS.length,
    sentinel: 'GREEN',
    extra: '本页为 GREEN 证据：八工具统一调用链路已接线，真实 LLM 联调归 P1-5',
  },
  'GREEN',
)
const bannerType = bannerAlertType('GREEN')

const drawerVisible = ref(false)
const contextType = ref<R8AContextType>('SQL')
const contextRefText = ref('{"project_id": 1, "table_name": "dw.dim_customer"}')
const nlInput = ref('')
const generatedSql = ref('')
const generatedExplanation = ref('')
const confirmed = ref(false)
const runResult = ref<R8ARunSqlResult | null>(null)
const lastError = ref<R8AToolCallError | null>(null)
const registry = ref<R8ARegistryEntry[]>([])
const auditRows = ref<MockAuditRecord[]>([])

const resultRows = computed(() => {
  if (!runResult.value) return []
  return runResult.value.rows.map((row) => {
    const record: Record<string, unknown> = {}
    row.forEach((cell, i) => {
      record[String(i)] = cell
    })
    return record
  })
})

const statusText = computed(() =>
  lastError.value
    ? `流程链状态：NL → generate_sql OK → run_sql 失败（${lastError.value.code}）— 按错误码与 retryable 决策重试/修正`
    : runResult.value
      ? `流程链状态：NL → generate_sql → 授权确认 → run_sql → 结果展示+解释 全链路完成（mock，无 LLM）`
      : '流程链状态：待输入自然语言（mock 模式全链路隔离于 K1）',
)

function parseContextRef(): Record<string, unknown> | null {
  const text = contextRefText.value.trim()
  if (!text) return null
  try {
    const parsed = JSON.parse(text) as unknown
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

function refreshAudit(): void {
  auditRows.value = [...mockAgent.auditRecords()].reverse()
}

function refreshRegistry(): void {
  registry.value = mockAgent.registry()
}

onMounted(() => {
  refreshRegistry()
  refreshAudit()
})

function clearAudit(): void {
  mockAgent.auditRecords().splice(0, mockAgent.auditRecords().length)
  refreshAudit()
}

function onGenerate(): void {
  lastError.value = null
  runResult.value = null
  confirmed.value = false
  generatedSql.value = ''
  generatedExplanation.value = ''
  const contextRef = parseContextRef()
  try {
    const generated = generateSqlMock(nlInput.value.trim(), { contextType: contextType.value, contextRef }, 'user-trae')
    generatedSql.value = generated.sql
    generatedExplanation.value = generated.explanation
  } catch (e) {
    lastError.value = {
      code: 'MOCK_SOVEREIGNTY_CONTEXT_MISSING',
      message: e instanceof Error ? e.message : String(e),
      retryable: false,
    }
  }
}

async function onRunSql(): Promise<void> {
  lastError.value = null
  runResult.value = null
  const contextRef = parseContextRef()
  try {
    const res = await mockAgent.call(
      {
        toolCallId: `tc-r8a-${Date.now()}`,
        tool: 'run_sql',
        toolVersion: R8A_TOOL_VERSION,
        params: { project_id: 1, datasource_id: 'ds-1', sql: generatedSql.value },
        pageContext: { contextType: contextType.value, contextRef },
      },
      { userId: 'user-trae', roles: ['DEVELOPER'] },
    )
    refreshAudit()
    if (res.status === 'SUCCESS' && res.result) {
      runResult.value = res.result as unknown as R8ARunSqlResult
    } else if (res.error) {
      lastError.value = res.error
    }
  } catch (e) {
    lastError.value = { code: 'INTERNAL_ERROR', message: e instanceof Error ? e.message : String(e), retryable: false }
  }
}
</script>

<style scoped>
.r8a-page {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.r8a-context {
  width: 100%;
}
.r8a-panel {
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  padding: 8px;
}
.r8a-panel-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  font-weight: 600;
  font-size: 13px;
}
.r8a-meta {
  font-weight: 400;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.r8a-status {
  width: 100%;
}
.r8a-explanation {
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.r8a-fab {
  position: fixed;
  right: 32px;
  bottom: 48px;
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--el-color-primary);
  color: #fff;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  cursor: pointer;
  box-shadow: var(--el-box-shadow-light);
  z-index: 2000;
}
.r8a-drawer-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
