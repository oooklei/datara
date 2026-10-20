<script setup lang="ts">
/**
 * instance_type 三态枚举 UI 骨架（FE-08 / B3 批次，可先行骨架）。
 * 枚举语义对齐后端 rebuild/execution/models.py §4.1/§4.2（INSTANCE_TYPES 三元组）：
 *  - TRIAL  试运行：绑定草稿快照（trial_snapshot_id），trigger_type=TRIAL（trial/runner.py 实锚）；
 *  - FORMAL 正式运行：绑定发布版本（workflow_version_id，不可变）；
 *  - STREAM 流处理：长运行流实例（STREAM_JOB），无批完成语义（§13.3：无 SUCCEEDED 终态，
 *          仅 PENDING/RUNNING/STOPPED/FAILED 迁移）。
 * 边界：新域契约（大盘 #15）后端建模未交付，本组件为展示层枚举 UI 骨架——
 * 不接数据通道、不伪造统计数据；未来 /dag/instances 实例列表绑定数据源时复用本枚举与徽标样式。
 */
import { computed } from 'vue'

defineOptions({ name: 'InstanceTypeFilter' })

/** instance_type 三态（单源：后端 INSTANCE_TYPES 元组的前端枚举骨架） */
export const INSTANCE_TYPES = ['TRIAL', 'FORMAL', 'STREAM'] as const
export type InstanceType = (typeof INSTANCE_TYPES)[number]

/** 单态元数据（标签 + 语义说明 + 徽标样式类；展示层骨架，不承载统计数据） */
export const INSTANCE_TYPE_META: Record<InstanceType, { label: string; desc: string; badgeCls: string }> = {
  TRIAL: { label: '试运行', desc: '绑定草稿快照（trial_snapshot_id），trigger_type=TRIAL', badgeCls: 'itf-badge--trial' },
  FORMAL: { label: '正式运行', desc: '绑定发布版本（workflow_version_id，不可变）', badgeCls: 'itf-badge--formal' },
  STREAM: { label: '流处理', desc: '长运行流实例（STREAM_JOB），无批完成语义（§13.3）', badgeCls: 'itf-badge--stream' },
}

const props = withDefaults(
  defineProps<{
    /** 当前筛选值；'' = 全部（不筛选） */
    modelValue?: string
    /** 各态数量（可选；新域契约交付后由实例列表数据源绑定，骨架阶段允许不传） */
    counts?: Partial<Record<InstanceType, number>>
  }>(),
  { modelValue: '', counts: () => ({}) },
)

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const selected = computed({
  get: () => props.modelValue,
  set: (v: string) => emit('update:modelValue', v),
})

/** 徽标渲染（供实例列表行复用：三态枚举的展示面） */
function badgeCls(t: string): string {
  return INSTANCE_TYPE_META[t as InstanceType]?.badgeCls ?? 'itf-badge--unknown'
}
function badgeLabel(t: string): string {
  return INSTANCE_TYPE_META[t as InstanceType]?.label ?? t
}
defineExpose({ badgeCls, badgeLabel })
</script>

<template>
  <div class="itf" data-testid="instance-type-filter">
    <el-radio-group v-model="selected" size="small">
      <el-radio-button value="" data-testid="itf-all">全部</el-radio-button>
      <el-radio-button
        v-for="t in INSTANCE_TYPES"
        :key="t"
        :value="t"
        :data-testid="`itf-${t.toLowerCase()}`"
        :title="INSTANCE_TYPE_META[t].desc"
      >
        {{ INSTANCE_TYPE_META[t].label }}
        <span v-if="counts[t]" class="itf-count">{{ counts[t] }}</span>
      </el-radio-button>
    </el-radio-group>
    <div class="itf-hint">TRIAL=试运行（草稿快照）/ FORMAL=正式运行（发布版本）/ STREAM=流处理（长运行，§13.3）</div>
  </div>
</template>

<style scoped>
.itf {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.itf-count {
  margin-left: 4px;
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.itf-hint {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.itf-badge--trial {
  color: #7c3aed;
  border-color: rgba(124, 58, 237, 0.4);
}
.itf-badge--formal {
  color: #1668dc;
  border-color: rgba(22, 104, 220, 0.4);
}
.itf-badge--stream {
  color: #d97706;
  border-color: rgba(217, 119, 6, 0.4);
}
.itf-badge--unknown {
  color: var(--el-text-color-secondary);
  border-color: var(--el-border-color);
}
</style>
