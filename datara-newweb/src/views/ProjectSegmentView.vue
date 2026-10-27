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
import ResourceManagementView from './resources/ResourceManagementView.vue'
import DataSourceListView from './datasource/DataSourceListView.vue'
import IdeView from './ide/IdeView.vue'
import ModelListView from './dwmodel/ModelListView.vue'
import ModelDesignView from './dwmodel/ModelDesignView.vue'
import ModelVersionView from './dwmodel/ModelVersionView.vue'
import ModelLineageView from './dwmodel/ModelLineageView.vue'
import ErCanvasView from './dwmodel/ErCanvasView.vue'
import LineageAnalysisView from './meta/LineageAnalysisView.vue'
import AssetMapView from './meta/AssetMapView.vue'
import MetadataCatalogView from './meta/MetadataCatalogView.vue'
import TagManagementView from './meta/TagManagementView.vue'
import StandardManagementView from './std/StandardManagementView.vue'
import IndicatorListView from './ind/IndicatorListView.vue'
import IndicatorBoardView from './ind/IndicatorBoardView.vue'
import ConsistencyCheckView from './ind/ConsistencyCheckView.vue'
import QualityRuleView from './qc/QualityRuleView.vue'
import QualityTaskView from './qc/QualityTaskView.vue'
import QualityReadOnlyView from './qc/QualityReadOnlyView.vue'

interface SegmentEntry {
  component: Component
  props?: Record<string, unknown>
}

const props = defineProps<{ projectId: number; segmentPath?: string; seg?: string }>()

const segmentViews: Record<string, SegmentEntry> = {
  dag: { component: TaskCenterView },
  'ds/list': { component: DataSourceListView },
  resources: { component: ResourceManagementView },
  ide: { component: IdeView },
  'model/list': { component: ModelListView },
  'model/design': { component: ModelDesignView },
  'model/version': { component: ModelVersionView },
  'model/lineage': { component: ModelLineageView },
  'model/er': { component: ErCanvasView },
  'meta/lineage': { component: LineageAnalysisView },
  'meta/map': { component: AssetMapView },
  'meta/catalog': { component: MetadataCatalogView },
  'meta/tag': { component: TagManagementView },
  'std/element': { component: StandardManagementView },
  'ind/list': { component: IndicatorListView },
  'ind/board': { component: IndicatorBoardView },
  'ind/consistency': { component: ConsistencyCheckView },
  'qc/rule': { component: QualityRuleView },
  'qc/task': { component: QualityTaskView },
  'qc/exception': { component: QualityReadOnlyView, props: { kind: 'exceptions' } },
  'qc/report': { component: QualityReadOnlyView, props: { kind: 'reports' } },
  'qc/alarm': { component: QualityReadOnlyView, props: { kind: 'alarms' } },
}

const normalizedPath = computed(() => (props.segmentPath ?? props.seg ?? '').replace(/^\/+|\/+$/g, ''))
const entry = computed(() => segmentViews[normalizedPath.value])
const componentProps = computed(() => ({ projectId: props.projectId, ...entry.value?.props }))
</script>

<style scoped>
.segment-page{display:grid;place-items:start;align-content:center;min-height:100%;padding:64px;gap:8px;background:var(--bg)}
.segment-page h1{font-size:24px}.segment-page p{color:var(--text-2)}.error-code{color:var(--primary);font-size:12px;font-weight:800;letter-spacing:2px}
</style>
