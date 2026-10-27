/**
 * T4/G07 Inspector 六区块框架层（①输入~⑥排除）：单一属性区按活体 spec 渲染
 * inputs/outputs/params/conditions/constraints/exclusions 六区块；③参数区块
 * 以插槽承载业务表单叠加（NodeConfigPanel/ScriptResourceEditor/SyncMappingEditor
 * 等既有编辑器原样接入），其余区块为 spec 声明的只读描述层。
 *
 * ①输入区块双源：spec.form.inputs 声明 + node.params.inputs 实际具名引用
 * （T3 拖边即引用产物 nodeId:port）；spec 缺失（START/END 等流程节点）时空态呈现。
 */
<script setup lang="ts">
import { computed } from 'vue'
import type { WorkflowDraftNode } from '../services/rebuild/workflowApi'
import type { ComponentSpecItem } from '../services/rebuild/componentSpecApi'
import { fieldDefsOf, conditionsOf, constraintsOf, sectionOf } from '../services/rebuild/specForm'
import type { SpecWhen } from '../services/rebuild/specForm'

const props = defineProps<{
  node: WorkflowDraftNode
  spec: ComponentSpecItem | null
}>()

const SIX_BLOCKS = [
  { id: 'inputs', index: '①', label: '输入' },
  { id: 'outputs', index: '②', label: '输出' },
  { id: 'params', index: '③', label: '参数' },
  { id: 'conditions', index: '④', label: '条件' },
  { id: 'constraints', index: '⑤', label: '约束' },
  { id: 'exclusions', index: '⑥', label: '排除' },
] as const
type BlockId = (typeof SIX_BLOCKS)[number]['id']

const specInputs = computed(() => fieldDefsOf(props.spec, 'inputs'))
const specOutputs = computed(() => fieldDefsOf(props.spec, 'outputs'))
const specParams = computed(() => fieldDefsOf(props.spec, 'params'))
const specConditions = computed(() => conditionsOf(props.spec))
const specConstraints = computed(() => constraintsOf(props.spec))
const specExclusions = computed(() => sectionOf(props.spec, 'exclusions'))

/** T3 拖边即引用：params.inputs 具名引用 { in: 'node:port' } */
const inputRefs = computed<[string, string][]>(() => {
  const inputs = props.node.params?.inputs
  if (inputs === null || inputs === undefined || typeof inputs !== 'object' || Array.isArray(inputs)) return []
  return Object.entries(inputs as Record<string, unknown>)
    .filter(([, v]) => typeof v === 'string' && v !== '')
    .map(([k, v]) => [k, String(v)])
})

const blockCount = (id: BlockId): number => {
  if (id === 'inputs') return specInputs.value.length + inputRefs.value.length
  if (id === 'outputs') return specOutputs.value.length
  if (id === 'params') return specParams.value.length
  if (id === 'conditions') return specConditions.value.length
  if (id === 'constraints') return specConstraints.value.length
  return specExclusions.value.length
}

function whenText(when: SpecWhen | undefined): string {
  if (!when) return ''
  const op = when.op === 'ne' ? '≠' : when.op === 'eq' ? '=' : String(when.op)
  return `${when.field} ${op} ${String(when.value ?? '')}`
}
</script>

<template>
  <div class="spec-blocks" data-testid="spec-blocks">
    <section
      v-for="block in SIX_BLOCKS"
      :key="block.id"
      class="spec-block"
      :data-testid="`spec-block-${block.id}`"
    >
      <header class="spec-block-head">
        <span class="spec-block-index">{{ block.index }}</span>
        <strong>{{ block.label }}</strong>
        <small>{{ blockCount(block.id) }} 项</small>
      </header>

      <!-- ① 输入：spec 声明 + T3 具名引用 -->
      <template v-if="block.id === 'inputs'">
        <ul v-if="inputRefs.length" class="spec-input-refs" data-testid="spec-input-refs">
          <li v-for="[k, v] in inputRefs" :key="k" data-testid="spec-input-ref">
            <code>{{ k }}</code><span>←</span><code>{{ v }}</code>
          </li>
        </ul>
        <ul v-if="specInputs.length" class="spec-rows">
          <li v-for="field in specInputs" :key="field.key" class="spec-row">
            <code>{{ field.key }}</code>
            <span class="spec-row-label">{{ field.label ?? field.key }}</span>
            <em v-if="field.required" class="spec-req">必填</em>
            <small v-if="field.uiType" class="spec-ui">{{ field.uiType }}</small>
          </li>
        </ul>
        <p v-if="!inputRefs.length && !specInputs.length" class="spec-empty">未声明输入（连线即引用，或 spec 未定义）</p>
      </template>

      <!-- ② 输出 -->
      <template v-else-if="block.id === 'outputs'">
        <ul v-if="specOutputs.length" class="spec-rows">
          <li v-for="field in specOutputs" :key="field.key" class="spec-row">
            <code>{{ field.key }}</code>
            <span class="spec-row-label">{{ field.label ?? field.key }}</span>
            <em v-if="field.required" class="spec-req">必填</em>
            <small v-if="field.uiType" class="spec-ui">{{ field.uiType }}</small>
          </li>
        </ul>
        <p v-else class="spec-empty">spec 未声明输出</p>
      </template>

      <!-- ③ 参数：业务表单叠加插槽；无插槽内容时呈现 spec 声明 -->
      <template v-else-if="block.id === 'params'">
        <slot name="params">
          <ul v-if="specParams.length" class="spec-rows">
            <li v-for="field in specParams" :key="field.key" class="spec-row">
              <code>{{ field.key }}</code>
              <span class="spec-row-label">{{ field.label ?? field.key }}</span>
              <em v-if="field.required" class="spec-req">必填</em>
              <small v-if="field.uiType" class="spec-ui">{{ field.uiType }}</small>
            </li>
          </ul>
          <p v-else class="spec-empty">spec 未声明参数</p>
        </slot>
      </template>

      <!-- ④ 条件（显隐规则，只读） -->
      <template v-else-if="block.id === 'conditions'">
        <ul v-if="specConditions.length" class="spec-rows">
          <li v-for="(rule, i) in specConditions" :key="rule.id ?? i" class="spec-row">
            <span class="spec-row-label">当 <code>{{ whenText(rule.when) }}</code> 时显示</span>
            <code>{{ (rule.show ?? []).join('、') }}</code>
          </li>
        </ul>
        <p v-else class="spec-empty">spec 未声明条件</p>
      </template>

      <!-- ⑤ 约束（值域规则，只读） -->
      <template v-else-if="block.id === 'constraints'">
        <ul v-if="specConstraints.length" class="spec-rows">
          <li v-for="(rule, i) in specConstraints" :key="i" class="spec-row">
            <code>{{ rule.field }}</code>
            <span class="spec-row-label">{{ rule.type }}</span>
            <small class="spec-ui">{{ whenText(rule.value) }}</small>
            <span v-if="rule.msg" class="spec-row-label">{{ rule.msg }}</span>
          </li>
        </ul>
        <p v-else class="spec-empty">spec 未声明约束</p>
      </template>

      <!-- ⑥ 排除 -->
      <template v-else>
        <ul v-if="specExclusions.length" class="spec-rows">
          <li v-for="(item, i) in specExclusions" :key="i" class="spec-row">
            <code>{{ (item as Record<string, unknown>).key ?? i }}</code>
          </li>
        </ul>
        <p v-else class="spec-empty">spec 未声明排除</p>
      </template>
    </section>
  </div>
</template>

<style scoped>
.spec-blocks {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.spec-block {
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
  border-radius: 6px;
  padding: 6px 8px;
}
.spec-block-head {
  display: flex;
  align-items: baseline;
  gap: 6px;
  margin-bottom: 4px;
}
.spec-block-index {
  color: var(--el-text-color-secondary, #909399);
  font-size: 12px;
}
.spec-block-head small {
  color: var(--el-text-color-secondary, #909399);
  margin-left: auto;
}
.spec-rows,
.spec-input-refs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.spec-row,
.spec-input-refs li {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  line-height: 1.6;
}
.spec-row code,
.spec-input-refs code {
  color: var(--el-color-primary, #409eff);
  background: var(--el-fill-color-light, #f5f7fa);
  border-radius: 3px;
  padding: 0 4px;
}
.spec-row-label {
  color: var(--el-text-color-regular, #606266);
}
.spec-req {
  color: var(--el-color-danger, #f56c6c);
  font-style: normal;
  font-size: 11px;
}
.spec-ui {
  color: var(--el-text-color-secondary, #909399);
}
.spec-empty {
  color: var(--el-text-color-secondary, #909399);
  font-size: 12px;
  margin: 0;
}
.spec-input-refs span {
  color: var(--el-text-color-secondary, #909399);
}
</style>
