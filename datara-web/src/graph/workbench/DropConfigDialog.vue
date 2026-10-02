<script setup lang="ts">
/**
 * F1 configure-first 拖入配置弹窗（治理设计 §12.1 三段式：顶部操作条 + 缺失项警示条 + 表单）。
 * - 常驻挂载（GraphWorkbench 持 dropNode/dropSchema 状态），ctx 工厂单实例化 → 库表树/topic 等
 *   候选缓存跨拖入复用（内存优化：避免每次拖入重建缓存重复拉载）
 * - 六区块与业务表单同用 SixBlocks + FieldRenderer + 同一 ctx 工厂（§12.2 禁双实现漂移）：
 *   弹窗期同样呈现 ①输入~⑥排除，业务表单仅在 schema.form 非空时追加
 * - 上游联动：父层传 `upstream`（虚拟节点无 doc.edges 入边），①输入候选与 dataScope 上游两域同源
 * - 闸门 = 必填完整 ∧ 无值域外/悬空引用；确认 → 父层落画布；取消/ESC → 节点不落画布
 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { GNode } from '../model'
import type { NodeSchema, ViewProfile } from '../profiles/types'
import { domainViolations } from '../profiles/formLinkage'
import type { DomainViolation } from '../profiles/formLinkage'
import FormSections from './fields/FormSections.vue'
import SixBlocks from './fields/SixBlocks.vue'
import { createFieldCtx } from './fields/fieldCtxFactory'

const props = defineProps<{
  /** 弹窗可见（父层 v-model 语义：false 触发 cancel） */
  visible: boolean
  /** 未落画布的虚拟节点（预生成 id + defaults + prefill 快照） */
  node: GNode | null
  schema: NodeSchema | null
  profile: ViewProfile
  /**
   * 本次拖入的逻辑上游（§11 划界语义：prefillFromUpstream 同一取法——选中节点优先，否则落点最近节点）。
   * 虚拟节点未落画布 → doc.edges 无入边，必须由父层显式传入，
   * 否则 ①输入无候选、dataScope 上游两域恒空、悬空引用判定失效（弹窗期配置上下文与落画布后不一致）。
   */
  upstream?: GNode[] | null
  /**
   * 模板向导步骤（可选）：模板展开为「暂存 → 逐节点配置 → 原子提交」时由父层传入。
   * 缺省=普通拖入单节点，标题/按钮文案与改造前一致。
   */
  step?: { index: number; total: number; chainLabel: string } | null
  /** 确认按钮文案（缺省「确认添加」；向导末步为「完成展开」） */
  confirmText?: string
}>()

const emit = defineEmits<{
  (e: 'confirm'): void
  (e: 'cancel'): void
}>()

/** 弹窗期为编辑态（拖入入口仅在 edit 模式可达）；脏标记 no-op——确认落画布时由父层统一 markDirty */
const rootEl = ref<HTMLElement | null>(null)
/** 上游覆盖 ref：随 props.upstream 更新，ctx 工厂据此走弹窗口径而非画布 doc.edges 口径 */
const upstreamOv = computed<GNode[] | null>(() => props.upstream ?? null)
const bundle = createFieldCtx({
  node: computed(() => props.node),
  nodeTypes: props.profile.nodeTypes,
  markDirty: () => {},
  rootEl,
  upstreamOverride: upstreamOv,
})
const { schema, visibleForm, missingLabels, onSet, upd, focusTarget, dataCtx, upstreamOuts } = bundle
const fieldCtx = bundle.ctx

/**
 * 闸门 = 必填完整 ∧ 无值域外/悬空引用（F1 + F4 落地）。
 * 六区块经 SixBlocks 暴露 staleInputRefs（①输入悬空），业务表单域外值由 domainViolations 同源判定。
 */
const six = ref<InstanceType<typeof SixBlocks> | null>(null)
const violations = computed<DomainViolation[]>(() => {
  if (!props.node || !schema.value) return []
  return domainViolations(
    visibleForm.value,
    props.node.data,
    dataCtx.value,
    Array.isArray(props.node.data.inputs) ? (props.node.data.inputs as string[]) : [],
    upstreamOuts.value,
  )
})
const staleRefs = computed<string[]>(() => six.value?.staleInputRefs ?? [])
const canConfirm = computed(() => missingLabels.value.length === 0 && violations.value.length === 0 && staleRefs.value.length === 0)
const blockReason = computed(() => {
  const r: string[] = []
  if (missingLabels.value.length) r.push(`必填未配置：${missingLabels.value.join('、')}`)
  if (staleRefs.value.length) r.push(`输入引用已失效：${staleRefs.value.join('、')}`)
  for (const v of violations.value) r.push(`${v.label}：${v.reason}`)
  return r.join('；')
})

/** 确认前纵深复校（弹窗数据可能被外部改动/默认值回填绕过 canConfirm 的时序） */
function confirm() {
  if (!canConfirm.value) { ElMessage.warning(blockReason.value || '配置未完成，无法添加'); return }
  emit('confirm')
}

/* 变量引用弹窗：业务表单 FieldRenderer 的 `f:{key}` 请求转交 SixBlocks 内部弹窗（保持弹窗唯一实例） */
function openVarDialog(target: string) { six.value?.openVarDialog(target) }

onMounted(() => { void bundle.loadShared() })
</script>

<template>
  <el-dialog
    :model-value="visible && !!node && !!schema" width="600px" append-to-body
    :close-on-click-modal="false" :close-on-press-escape="true"
    @update:model-value="(v: boolean) => { if (!v) emit('cancel') }"
  >
    <template #header>
      <!-- 三段式①：顶部操作条（确认/取消置顶，§12.1） -->
      <div v-if="schema" class="dc-head">
        <span class="dc-ico" :style="{ background: schema.color }">{{ schema.icon }}</span>
        <span class="dc-title">配置「{{ schema.label }}」</span>
        <span v-if="schema.code" class="dc-code">{{ schema.code }}</span>
        <span v-if="step" class="dc-step" :title="`模板「${step.chainLabel}」展开 ${step.total} 个待配置节点`">
          第 {{ step.index + 1 }} / {{ step.total }} 步
        </span>
        <span class="dc-spacer" />
        <button class="dc-btn dc-cancel" @click="emit('cancel')">{{ step ? '放弃展开' : '取消' }}</button>
        <button class="dc-btn dc-ok" :disabled="!canConfirm" :title="blockReason || ''" @click="confirm">
          {{ confirmText ?? (step ? '下一步' : '确认添加') }}
        </button>
      </div>
    </template>

    <div v-if="node && schema" ref="rootEl" class="dc-body">
      <!-- 三段式②：缺失项/值域违规警示条（与 Inspector 角标、画布校验面板同一判定源） -->
      <div v-if="blockReason" class="dc-miss">{{ blockReason }}</div>
      <div v-else class="dc-miss dc-ready">必填已完整且取值在值域内，可确认添加</div>

      <!-- 三段式③：表单（与 Inspector 同一 SixBlocks + FieldRenderer + 同一 ctx） -->
      <div class="field">
        <label>节点名称</label>
        <input :value="String(node.data.name ?? '')" @change="upd('name', $event)" />
      </div>

      <!-- F60 六区块：与业务表单正交的框架级标准块（schema.form 为空的 C1/C2/C6/C7 靠它构成完整配置面） -->
      <SixBlocks
        ref="six"
        :node="node"
        :ctx="fieldCtx"
        :readonly="false"
        :mark-dirty="() => {}"
      />

      <FormSections
        :form="visibleForm" :data="node.data" mode="edit" :node-id="node.id"
        :ctx="fieldCtx" :profile="profile"
        @set="onSet" @dirty="() => {}" @open-var-dialog="openVarDialog" @focus-target="focusTarget"
      />
      <div style="font-size:10.5px;color:var(--text-3);margin-top:10px">确认后节点落画布；后续修改在右侧属性面板进行。</div>
    </div>
  </el-dialog>
</template>

<style scoped>
.dc-head{display:flex;align-items:center;gap:8px;padding-right:8px}
.dc-ico{width:22px;height:22px;border-radius:5px;display:flex;align-items:center;justify-content:center;color:#fff;font-size:11px}
.dc-title{font-weight:600;font-size:13.5px}
.dc-code{font-size:10px;color:var(--text-3);border:1px solid var(--border);border-radius:4px;padding:0 4px}
.dc-step{font-size:10.5px;color:var(--primary);background:var(--primary-light,#eff6ff);border:1px solid var(--primary);border-radius:999px;padding:1px 8px;white-space:nowrap}
.dc-spacer{flex:1}
.dc-btn{border:1px solid var(--border);background:var(--bg,#fff);border-radius:6px;padding:4px 12px;font-size:12px;cursor:pointer}
.dc-btn:hover{border-color:var(--primary);color:var(--primary)}
.dc-ok{background:var(--primary);border-color:var(--primary);color:#fff}
.dc-ok:hover{color:#fff;opacity:.9}
.dc-ok:disabled{opacity:.45;cursor:not-allowed}
.dc-body{max-height:62vh;overflow:auto;padding-right:4px}
.dc-miss{font-size:11.5px;padding:6px 10px;border-radius:6px;margin-bottom:10px;background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;line-height:1.6}
.dc-ready{background:#f0fdf4;color:#15803d;border-color:#bbf7d0}
.field{margin-bottom:10px}
.field label{display:block;font-size:11.5px;color:var(--text-2,#475569);margin-bottom:3px}
.field input,.field select{width:100%;box-sizing:border-box;border:1px solid var(--border);border-radius:6px;padding:5px 8px;font-size:12px}
.req-star{color:var(--primary);margin-left:2px}
</style>
