<script setup lang="ts">
/**
 * 增量 15.6 / 权威设计 §5E.3：LLM 模型配置列表页（G 组 · 系统管理）。
 *
 * 后端事实源：`datara-backend/rebuild/llm/api.py` 六端点（挂载 `/api/v1/rebuild/llm-models`，
 * 见 `rebuild/api/app.py` L1128-1132，仅在 `LLM_ENCRYPTION_KEY` 注入时挂载）。
 *
 * §5E.1 功能六件套落点：
 *  #1 列表（名称/显示名称/Provider/API Base/模型 ID/默认 tag/启停 switch/操作）——另加
 *      「API Key（掩码）」列：§5E.1 回显纪律要求列表侧 api_key 恒掩码，该列为掩码唯一可视位，
 *      亦为红线 8「响应掩码断言」的 evidence 锚（对 §5E.1#1 列集为**追加**，非替换）。
 *  #2 新增/编辑 → LlmModelFormDialog.vue（api_key password + 编辑态留空不覆盖）。
 *  #3 连通性测试 → 行内按钮，loading 态，成功展示 elapsed_ms + reply 摘要，失败展示 detail。
 *  #4 默认模型单选 → 「设默认」按钮；后端 PUT /{id}/default 清全表既有默认位。
 *  #5 启停 switch 即时 PUT；停用模型不可设默认、默认模型不可停用（后端 409/4092）。
 *  #6 删除保护 → 默认模型行「删除」按钮**禁用**（前端双保险），后端 DELETE 兜底 409/4092；
 *      非默认删除走二次确认。
 *
 * 壳范式锚：表单模态沿 ScheduleDialog.vue 手工 Teleport+遮罩（禁 el-dialog，happy-dom 不可测）；
 * 瞬时反馈用 ElMessage / 二次确认用 ElMessageBox（§5E.3「与既有页面一致」）。
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  LLM_ERROR_CODES,
  llmApi,
  type LlmModelDraft,
  type LlmModelRecord,
  type LlmTestResult,
} from '../../../services/rebuild/llmApi'
import LlmModelFormDialog from './LlmModelFormDialog.vue'

/** 后端 list 上限 200（api.py Query le=200）：单页全量拉取，不做分页 UI（§5E 未定义分页交互）。 */
const LIST_LIMIT = 200

const rows = ref<LlmModelRecord[]>([])
const loading = ref(false)
const loadError = ref('')
const busyIds = ref<Set<number>>(new Set())
const formVisible = ref(false)
const editing = ref<LlmModelRecord | null>(null)

/** 连通性测试结果按行暂存（后端不持久化测试结果，仅会话内回显）。 */
const testResults = ref<Record<number, LlmTestResult>>({})

/** D13 列表搜索：前端过滤模型行，不触发后端。 */
const filterKeyword = ref('')
const filteredRows = computed(() => {
  const keyword = filterKeyword.value.toLowerCase()
  if (keyword === '') return rows.value
  return rows.value.filter(
    (row) =>
      row.name.toLowerCase().includes(keyword) ||
      row.displayName.toLowerCase().includes(keyword) ||
      row.provider.toLowerCase().includes(keyword) ||
      row.modelId.toLowerCase().includes(keyword),
  )
})

function isBusy(id: number): boolean {
  return busyIds.value.has(id)
}

async function reload(): Promise<void> {
  loading.value = true
  loadError.value = ''
  try {
    const page = await llmApi.list(0, LIST_LIMIT)
    rows.value = page.items
  } catch (error) {
    // 1xxx 段（含 1001/1003）已由 http 底座触发跳登录后继续抛出，此处仅呈现。
    loadError.value = error instanceof Error ? error.message : 'LLM 模型列表加载失败'
  } finally {
    loading.value = false
  }
}

function openCreate(): void {
  editing.value = null
  formVisible.value = true
}

function openEdit(row: LlmModelRecord): void {
  editing.value = row
  formVisible.value = true
}

async function onSaved(): Promise<void> {
  formVisible.value = false
  await reload()
}

/** #3 连通性测试：成功后展示 elapsed_ms + reply 摘要；失败展示 detail（§5E.1#3）。 */
async function runTest(row: LlmModelRecord): Promise<void> {
  if (isBusy(row.id)) return
  busyIds.value = new Set(busyIds.value).add(row.id)
  const next = { ...testResults.value }
  delete next[row.id]
  testResults.value = next
  try {
    const result = await llmApi.testModel(row.id)
    testResults.value = { ...testResults.value, [row.id]: result }
    if (result.status === 'success') {
      ElMessage.success(`连通性测试通过（${result.elapsedMs ?? '-'} ms）`)
    } else {
      ElMessage.error(`连通性测试失败：${result.message}`)
    }
  } catch (error) {
    // 502/5021 = 出站失败；404/4041 = 模型不存在
    const code = (error as { code?: number })?.code
    const detail = error instanceof Error ? error.message : '连通性测试失败'
    testResults.value = {
      ...testResults.value,
      [row.id]: { status: 'error', message: detail, detail: `code=${code ?? '-'}` },
    }
    ElMessage.error(`连通性测试失败：${detail}`)
  } finally {
    const rest = new Set(busyIds.value)
    rest.delete(row.id)
    busyIds.value = rest
  }
}

/** #4 设默认：后端清全表既有默认位，故本地需整表刷新以反映其他行的默认位清除。 */
async function setRowDefault(row: LlmModelRecord): Promise<void> {
  if (isBusy(row.id)) return
  busyIds.value = new Set(busyIds.value).add(row.id)
  try {
    await llmApi.setDefault(row.id)
    ElMessage.success(`已将「${row.displayName}」设为默认模型`)
    await reload()
  } catch (error) {
    const code = (error as { code?: number })?.code
    // 409/4092：停用模型不可设为默认（repository.set_default）
    ElMessage.error(code === LLM_ERROR_CODES.semanticConflict ? '停用模型不可设为默认' : '设默认失败')
  } finally {
    const rest = new Set(busyIds.value)
    rest.delete(row.id)
    busyIds.value = rest
  }
}

/** #5 启停即时 PUT。默认模型不可停用（后端 409/4092），前端先断避免无谓往返。 */
async function toggleActive(row: LlmModelRecord): Promise<void> {
  if (isBusy(row.id)) return
  if (row.isDefault && row.isActive) {
    ElMessage.warning('默认模型不可停用；请先设其他模型为默认')
    return
  }
  busyIds.value = new Set(busyIds.value).add(row.id)
  try {
    const draft: LlmModelDraft = {
      name: row.name,
      displayName: row.displayName,
      provider: row.provider,
      apiBase: row.apiBase,
      modelId: row.modelId,
      // 启停不改凭据：留空即不覆盖（api.py L98）
      maxTokens: row.maxTokens,
      temperature: row.temperature,
      isActive: !row.isActive,
      isDefault: row.isDefault,
      sortOrder: row.sortOrder,
    }
    const updated = await llmApi.update(row.id, draft)
    Object.assign(row, updated)
    ElMessage.success(updated.isActive ? '已启用' : '已停用')
  } catch (error) {
    const code = (error as { code?: number })?.code
    ElMessage.error(code === LLM_ERROR_CODES.semanticConflict ? '默认模型不可停用' : '启停切换失败')
  } finally {
    const rest = new Set(busyIds.value)
    rest.delete(row.id)
    busyIds.value = rest
  }
}

/** #6 删除保护：默认模型行按钮禁用（前端双保险）；非默认走二次确认，后端 409/4092 兜底。 */
async function remove(row: LlmModelRecord): Promise<void> {
  if (row.isDefault || isBusy(row.id)) return
  try {
    await ElMessageBox.confirm(`确认删除 LLM 模型「${row.displayName}」？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  busyIds.value = new Set(busyIds.value).add(row.id)
  try {
    await llmApi.remove(row.id)
    ElMessage.success('已删除')
    await reload()
  } catch (error) {
    const code = (error as { code?: number })?.code
    ElMessage.error(
      code === LLM_ERROR_CODES.semanticConflict
        ? '默认模型不可删除'
        : code === LLM_ERROR_CODES.notFound
          ? '模型不存在或已删除'
          : '删除失败',
    )
  } finally {
    const rest = new Set(busyIds.value)
    rest.delete(row.id)
    busyIds.value = rest
  }
}

onMounted(reload)
</script>

<template>
  <main class="llm-page" aria-label="LLM 模型配置" data-test="llm-page">
    <header class="llm-head">
      <div>
        <h1>LLM 模型配置</h1>
        <p>维护 AI 助手调用的 LLM 端点；全局唯一默认模型，api_key 密文入库、响应恒掩码。</p>
      </div>
      <button type="button" class="llm-btn llm-btn--primary" data-test="llm-create" @click="openCreate">新建模型</button>
    </header>

    <!-- D13 列表搜索：仅在已有数据时呈现 -->
    <div v-if="rows.length > 0" class="llm-toolbar">
      <input v-model.trim="filterKeyword" data-filter-keyword placeholder="搜索名称、显示名称、Provider 或模型 ID">
    </div>

    <p v-if="loading" role="status" data-test="llm-loading">正在加载…</p>
    <p v-else-if="loadError" role="alert" class="llm-alert" data-test="llm-error">{{ loadError }}</p>
    <p v-else-if="rows.length === 0" class="llm-empty" data-test="llm-empty">暂无 LLM 模型</p>

    <table v-else class="llm-table" data-test="llm-list">
      <thead>
        <tr>
          <th>名称</th>
          <th>显示名称</th>
          <th>Provider</th>
          <th>API Base</th>
          <th>模型 ID</th>
          <th>API Key（掩码）</th>
          <th>默认</th>
          <th>启停</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in filteredRows" :key="row.id" :data-llm-id="row.id" :data-llm-name="row.name" data-test="llm-row">
          <td data-test="llm-name">{{ row.name }}</td>
          <td data-test="llm-display-name">{{ row.displayName }}</td>
          <td data-test="llm-provider">{{ row.provider }}</td>
          <td class="llm-mono" data-test="llm-api-base">{{ row.apiBase }}</td>
          <td class="llm-mono" data-test="llm-model-id">{{ row.modelId }}</td>
          <!-- 掩码回显：仅消费后端掩码值，不解掩码、不重构完整 key（红线 8） -->
          <td class="llm-mono" data-test="llm-api-key">{{ row.apiKey || '—' }}</td>
          <td>
            <span
              v-if="row.isDefault"
              class="llm-tag"
              data-test="llm-default-tag"
            >默认</span>
            <span v-else class="llm-tag llm-tag--muted">—</span>
          </td>
          <td>
            <label class="llm-switch">
              <!-- @click.prevent：阻断原生勾选态翻转，选中态唯由 row.isActive 驱动，
                   避免「默认模型不可停用」前端先断后 checkbox 与数据态漂移 -->
              <input
                type="checkbox"
                :checked="row.isActive"
                :disabled="isBusy(row.id)"
                data-test="llm-toggle-active"
                @click.prevent="toggleActive(row)"
              />
              <span>{{ row.isActive ? '启用' : '停用' }}</span>
            </label>
          </td>
          <td class="llm-actions">
            <button type="button" class="llm-link" :disabled="isBusy(row.id)" data-test="llm-test" @click="runTest(row)">
              {{ isBusy(row.id) ? '测试中…' : '测试' }}
            </button>
            <button
              type="button"
              class="llm-link"
              :disabled="row.isDefault || isBusy(row.id)"
              :title="row.isDefault ? '该模型已是默认' : '设为默认模型'"
              data-test="llm-set-default"
              @click="setRowDefault(row)"
            >设默认</button>
            <button type="button" class="llm-link" data-test="llm-edit" @click="openEdit(row)">编辑</button>
            <!-- 删除保护（前端双保险）：默认模型行禁用，后端 409/4092 兜底 -->
            <button
              type="button"
              class="llm-link llm-link--danger"
              :disabled="row.isDefault || isBusy(row.id)"
              :title="row.isDefault ? '默认模型不可删除' : '删除'"
              data-test="llm-delete"
              @click="remove(row)"
            >删除</button>
          </td>
        </tr>
        <tr v-if="filteredRows.length === 0"><td colspan="9">无匹配模型</td></tr>
      </tbody>
    </table>

    <!-- 连通性测试结果：成功含 elapsed_ms 与模型返回摘要，失败含 detail（§5E.1#3） -->
    <template v-for="row in rows" :key="`t-${row.id}`">
      <p
        v-if="testResults[row.id]"
        class="llm-test-result"
      :class="testResults[row.id]?.status === 'success' ? 'llm-test-result--ok' : 'llm-test-result--err'"
      role="status"
      :data-test="`llm-test-result-${row.id}`"
    >
      <template v-if="testResults[row.id]?.status === 'success'">
        {{ row.name }}：连通性测试通过，耗时 {{ testResults[row.id]?.elapsedMs ?? '-' }} ms，模型返回
        「{{ testResults[row.id]?.reply ?? '-' }}」
      </template>
      <template v-else>
        {{ row.name }}：连通性测试失败 —— {{ testResults[row.id]?.message ?? '-' }}
        {{ testResults[row.id]?.detail ?? '' }}
      </template>
      </p>
    </template>

    <LlmModelFormDialog v-model="formVisible" :record="editing" @saved="onSaved" />
  </main>
</template>

<style scoped>
/* 设计令牌：由全局 styles/theme.css 的 :root 提供（§4.4.3 风格统一），本文件不再就地重复定义。 */
.llm-page {
  max-width: 1400px;
  margin: auto;
  padding: 32px 24px;
  color: var(--text);
}
.llm-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.llm-head h1 {
  margin: 0;
}
.llm-head p {
  margin: 6px 0 0;
  color: var(--text-3);
  font-size: 13px;
}
.llm-toolbar {
  margin-top: 18px;
  display: flex;
}
.llm-table {
  width: 100%;
  border-collapse: collapse;
  background: var(--card);
  margin-top: 18px;
}
.llm-table th,
.llm-table td {
  text-align: left;
  padding: 11px 10px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  vertical-align: middle;
}
.llm-table th {
  background: var(--bg);
  color: var(--text-2);
  font-weight: 500;
}
.llm-mono {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  word-break: break-all;
}
.llm-tag {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 999px;
  font-size: 12px;
  background: var(--success-bg);
  color: var(--success);
}
.llm-tag--muted {
  background: transparent;
  color: var(--text-3);
}
.llm-switch {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 13px;
}
.llm-actions {
  white-space: nowrap;
}
.llm-link {
  border: none;
  background: none;
  color: var(--primary);
  cursor: pointer;
  font-size: 13px;
  padding: 0 6px;
}
.llm-link--danger {
  color: var(--danger);
}
.llm-link:disabled {
  color: var(--border-strong);
  cursor: not-allowed;
}
.llm-btn {
  height: 34px;
  padding: 0 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-strong);
  background: var(--card);
  color: var(--text);
  font-size: 13px;
  cursor: pointer;
}
.llm-btn--primary {
  background: var(--primary);
  border-color: var(--primary);
  color: var(--card);
}
.llm-empty,
.llm-alert {
  margin: 24px 0 0;
  font-size: 13px;
}
.llm-empty {
  color: var(--text-3);
  text-align: center;
  padding: 24px 0;
}
.llm-alert {
  color: var(--danger);
}
.llm-test-result {
  margin: 10px 0 0;
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
}
/* 令牌层无独立边框色阶，状态块改为「底色 + 文字色」两档（对齐全局 .pill.ok/.err）。 */
.llm-test-result--ok {
  background: var(--success-bg);
  color: var(--success);
}
.llm-test-result--err {
  background: var(--danger-bg);
  color: var(--danger);
}
</style>
