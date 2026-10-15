<!--
  R5-B：SQL IDE DDL 写路径验证页（RED/原型态）。
  权威范围：plan I6 + docs/increments/R5-IDE-开始前影响分析.md §4。
  UI 三区：定义查看/编辑（复用 R5-A SqlEditor）→ 管控结果（block/warn/info 三级）→ 确认闸（人工确认短语）+ 执行记录/回滚展示。
  红线：确认短语由用户在输入框亲自键入；block 级 finding 存在时确认按钮禁用（UI 层先行，服务端为准）。
-->
<template>
  <div class="r5b-page">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      data-testid="r5b-red-banner"
      title="R5-B RED 骨架（原型态）— rebuild/sql_ide/ddl（A5）契约未接入；确认/执行/回滚均需人工闸"
    />

    <splitpanes class="r5b-body" horizontal>
      <pane size="46" min-size="24">
        <div class="r5b-panel">
          <div class="r5b-panel-head">
            <span>DDL 定义查看 / 编辑</span>
            <span class="r5b-actions">
              <el-select v-model="objectKind" size="small" class="r5b-kind" data-testid="r5b-object-kind">
                <el-option v-for="k in KINDS" :key="k" :label="k" :value="k" />
              </el-select>
              <el-button size="small" @click="onLoad">载入定义</el-button>
              <el-button size="small" type="primary" :disabled="!ddlText" @click="onValidate">管控校验</el-button>
            </span>
          </div>
          <div class="r5b-panel-body">
            <SqlEditor v-model="ddlText" />
          </div>
        </div>
      </pane>
      <pane min-size="24">
        <div class="r5b-panel">
          <div class="r5b-panel-head">
            <span>管控结果</span>
            <el-tag v-if="report" :type="report.blocked ? 'danger' : 'success'" size="small">
              {{ report.blocked ? 'BLOCKED' : 'PASS' }}
            </el-tag>
          </div>
          <div class="r5b-panel-body r5b-findings">
            <el-empty v-if="!report" description="（未校验 — validatePolicy 契约 A5 未接入）" :image-size="56" />
            <el-alert
              v-for="(f, i) in report?.findings ?? []"
              :key="i"
              :type="levelType(f.level)"
              :closable="false"
              show-icon
              class="r5b-finding"
            >
              <template #title>[{{ f.level.toUpperCase() }}] {{ f.code }}</template>
              {{ f.message }}
              <div v-if="f.impacts.length" class="r5b-impacts">影响对象：{{ f.impacts.join('、') }}</div>
            </el-alert>
          </div>
          <div class="r5b-confirm" data-testid="r5b-confirm-gate">
            <el-input
              v-model="confirmPhrase"
              size="small"
              placeholder="输入人工确认短语（用户亲自键入）"
              clearable
              class="r5b-phrase"
            />
            <el-button
              size="small"
              type="danger"
              :disabled="!canConfirm"
              @click="onConfirm"
            >提交确认</el-button>
          </div>
        </div>
      </pane>
    </splitpanes>

    <div class="r5b-records">
      <div class="r5b-panel-head"><span>执行记录（含补偿/回滚脚本展示）</span></div>
      <el-empty v-if="!records.length" description="（无记录 — A5 契约未接入）" :image-size="48" />
      <el-table v-else :data="records" size="small" border max-height="220">
        <el-table-column prop="recordId" label="#" width="64" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column prop="ddlText" label="DDL" min-width="200" show-overflow-tooltip />
        <el-table-column prop="createdAt" label="时间" width="160" />
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Splitpanes, Pane } from 'splitpanes'
import 'splitpanes/dist/splitpanes.css'
import {
  createSqlIdeDdlContract,
  type DdlExecutionRecord,
  type DdlObjectKind,
  type DdlPolicyReport,
} from '../../../../services/rebuild/sqlIdeDdlApi'
import SqlEditor from '../sql-ide-readonly/components/SqlEditor.vue'

defineOptions({ name: 'SqlIdeDdlView' })

const KINDS: DdlObjectKind[] = ['table', 'view', 'function', 'procedure', 'trigger']
const contract = createSqlIdeDdlContract()

const objectKind = ref<DdlObjectKind>('table')
const ddlText = ref('')
const confirmPhrase = ref('')
const report = ref<DdlPolicyReport | null>(null)
const records = ref<DdlExecutionRecord[]>([])

/** block 级存在或无确认短语 → 确认闸关闭（UI 层先行，服务端仍为准） */
const canConfirm = computed(() => !!confirmPhrase.value && !!report.value && !report.value.blocked && !!ddlText.value)

const levelType = (level: string): 'error' | 'warning' | 'info' =>
  level === 'block' ? 'error' : level === 'warn' ? 'warning' : 'info'

const onLoad = () =>
  contract
    .getDefinition(0, objectKind.value, null, '')
    .then((d) => {
      ddlText.value = d.ddlText
    })
    .catch(() => {})

const onValidate = () =>
  contract
    .validatePolicy(0, ddlText.value)
    .then((r) => {
      report.value = r
    })
    .catch(() => {})

const onConfirm = () =>
  contract
    .submitConfirm({
      datasourceId: 0,
      definition: { objectKind: objectKind.value, schema: null, name: '', ddlText: '' },
      nextDdlText: ddlText.value,
      policyReport: report.value!,
      confirmPhrase: confirmPhrase.value,
    })
    .then((rec) => {
      records.value = [rec, ...records.value]
    })
    .catch(() => {})
</script>

<style scoped>
.r5b-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px;
  box-sizing: border-box;
}
.r5b-body {
  flex: 1;
  min-height: 0;
}
.r5b-panel,
.r5b-records {
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--el-border-color-light);
  border-radius: 4px;
  overflow: hidden;
}
.r5b-records {
  flex: none;
  height: auto;
  padding-bottom: 4px;
}
.r5b-panel-head {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  font-size: 13px;
}
.r5b-actions {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}
.r5b-kind {
  width: 120px;
}
.r5b-panel-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 4px;
}
.r5b-findings {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.r5b-finding {
  flex: none;
}
.r5b-impacts {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 2px;
}
.r5b-confirm {
  flex: none;
  display: flex;
  gap: 6px;
  padding: 6px 8px;
  border-top: 1px solid var(--el-border-color-lighter);
}
.r5b-phrase {
  flex: 1;
}
</style>
