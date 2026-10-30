<template>
  <component :is="entry.component" v-if="entry" :key="`${projectId}:${normalizedPath}`" v-bind="componentProps" />
  <section v-else class="segment-page" aria-label="未知项目功能">
    <span class="error-code">404</span>
    <h1>未找到项目功能</h1>
    <p>路径“{{ normalizedPath }}”不属于当前项目工作区。</p>
    <RouterLink :to="`/p/${projectId}`">返回项目工作台</RouterLink>
  </section>
</template>

<script setup lang="ts">
import { computed, type Component } from 'vue'
import TaskCenterView from './TaskCenterView.vue'
import ProjectTaskGroupView from './ProjectTaskGroupView.vue'
import ResourceManagementView from './resources/ResourceManagementView.vue'
import TagManagementView from './meta/TagManagementView.vue'
import StandardManagementView from './std/StandardManagementView.vue'
import IndicatorListView from './ind/IndicatorListView.vue'
import IndicatorBoardView from './ind/IndicatorBoardView.vue'
import ConsistencyCheckView from './ind/ConsistencyCheckView.vue'
import QualityRuleView from './qc/QualityRuleView.vue'
import QualityTaskView from './qc/QualityTaskView.vue'
import QualityExceptionView from './qc/QualityExceptionView.vue'
import QualityReportView from './qc/QualityReportView.vue'
import QualityAlarmView from './qc/QualityAlarmView.vue'

interface SegmentEntry {
  component: Component
  props?: Record<string, unknown>
}

const props = defineProps<{ projectId: number; segmentPath?: string; seg?: string }>()

const segmentViews: Record<string, SegmentEntry> = {
  dag: { component: TaskCenterView },
  // §10.10 R8：任务组管理（项目级，任务中心「任务组名称/组内优先级」下拉来源）
  'task-group': { component: ProjectTaskGroupView },
  resources: { component: ResourceManagementView },
  'meta/tag': { component: TagManagementView },
  'std/element': { component: StandardManagementView },
  'ind/list': { component: IndicatorListView },
  'ind/board': { component: IndicatorBoardView },
  'ind/consistency': { component: ConsistencyCheckView },
  'qc/rule': { component: QualityRuleView },
  'qc/task': { component: QualityTaskView },
  // E17/E18/E19：冻结表点名真实视图（B5-c 纠偏，同 routes.ts；三页自行从
  // route.params.projectId 承接项目上下文，无需 kind 聚合）
  'qc/exception': { component: QualityExceptionView },
  'qc/report': { component: QualityReportView },
  'qc/alarm': { component: QualityAlarmView },
}

const normalizedPath = computed(() => (props.segmentPath ?? props.seg ?? '').replace(/^\/+|\/+$/g, ''))
const entry = computed(() => segmentViews[normalizedPath.value])
const componentProps = computed(() => ({ projectId: props.projectId, ...entry.value?.props }))
</script>

<style scoped>
.segment-page{display:grid;place-items:start;align-content:center;min-height:100%;padding:64px;gap:8px;background:var(--bg)}
.segment-page h1{font-size:24px}.segment-page p{color:var(--text-2)}.error-code{color:var(--primary);font-size:12px;font-weight:800;letter-spacing:2px}
</style>
