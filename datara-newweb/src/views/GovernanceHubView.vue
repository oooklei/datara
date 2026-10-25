<script setup lang="ts">
/**
 * 数据治理域页签枢纽（项目工作区 `/p/:projectId/meta` 承载）。
 *
 * 背景：项目工作区七段中 `meta`（数据治理）段原落 ProjectSegmentView 占位分支，
 * 呈现「该功能段尚未开放」——而治理域 8 页（血缘/资产地图/元数据目录/标签/标准/
 * 指标目录/指标看板/一致性）已随 inc14 交付并注册于顶层路由（routes.ts）。
 * 本枢纽把 8 页以页签形式接入项目段，消除占位、保持项目上下文（route.params.projectId
 * 由 `/p/:projectId/meta` 供给，8 页既有的 routeProjectId 兜底链原样可用）。
 *
 * 纪律：
 *  - 复用既有 TabsView 页签范式（增量 2 / 票 2-07），不自造第二套页签样式；
 *  - KeepAlive 缓存已激活页签（切页不丢筛选/滚动状态），未激活页签不挂载（按需加载）；
 *  - 页签集合与全局菜单「数据治理」组 8 项一一对应（0.4 §4.2 菜单语义归类表），
 *    顺序沿用菜单序，保证两入口心智一致。
 */
import { computed, ref } from 'vue'
import TabsView from '../components/TabsView.vue'
import LineageAnalysisView from './meta/LineageAnalysisView.vue'
import AssetMapView from './meta/AssetMapView.vue'
import MetadataCatalogView from './meta/MetadataCatalogView.vue'
import TagManagementView from './meta/TagManagementView.vue'
import StandardManagementView from './std/StandardManagementView.vue'
import IndicatorListView from './ind/IndicatorListView.vue'
import IndicatorBoardView from './ind/IndicatorBoardView.vue'
import ConsistencyCheckView from './ind/ConsistencyCheckView.vue'

interface HubTab {
  id: string
  label: string
  component: typeof LineageAnalysisView
}

/** 治理域 8 页签（顺序 = 全局菜单「数据治理」组序，0.4 §4.2） */
const TABS: readonly HubTab[] = [
  { id: 'lineage', label: '血缘分析', component: LineageAnalysisView },
  { id: 'map', label: '资产地图', component: AssetMapView },
  { id: 'catalog', label: '元数据目录', component: MetadataCatalogView },
  { id: 'tag', label: '标签管理', component: TagManagementView },
  { id: 'std', label: '标准管理', component: StandardManagementView },
  { id: 'ind-list', label: '指标目录', component: IndicatorListView },
  { id: 'ind-board', label: '指标看板', component: IndicatorBoardView },
  { id: 'ind-consistency', label: '一致性检查', component: ConsistencyCheckView },
] as const

const active = ref<string>(TABS[0].id)
const current = computed(() => TABS.find((t) => t.id === active.value)?.component ?? TABS[0].component)

function onActivate(id: string): void {
  active.value = id
}
</script>

<template>
  <section class="gov-hub" aria-label="数据治理">
    <TabsView :tabs="TABS" :model-value="active" @update:model-value="onActivate">
      <KeepAlive>
        <component :is="current" />
      </KeepAlive>
    </TabsView>
  </section>
</template>

<style scoped>
.gov-hub {
  min-height: 0;
}
</style>
