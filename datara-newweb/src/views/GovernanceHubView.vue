<script setup lang="ts">
/**
 * 数据治理域页签枢纽（项目工作区 `/p/:projectId/meta` 承载）。
 *
 * 背景：项目工作区七段中 `meta`（数据治理）段原落 ProjectSegmentView 占位分支，
 * 呈现「该功能段尚未开放」——而治理域 13 页（元数据/指标 8 页 + 质量 5 页）
 * 已随 inc14 交付并注册于顶层路由（routes.ts）。本枢纽把 13 页以页签形式接入项目段，
 * 消除占位、保持项目上下文（route.params.projectId 由 `/p/:projectId/meta` 供给，
 * 各页既有的 routeProjectId 兜底链原样可用）。
 *
 * 纪律：
 *  - 复用既有 TabsView 页签范式（增量 2 / 票 2-07），不自造第二套页签样式；
 *  - KeepAlive 缓存已激活页签（切页不丢筛选/滚动状态），未激活页签不挂载（按需加载）；
 *  - 页签集合与全局菜单「数据治理」组正式项一一对应（0.4 §4.2 菜单语义归类表），
 *    顺序沿用菜单序，保证两入口心智一致。
 */
import { computed, ref, type Component } from 'vue'
import TabsView from '../components/TabsView.vue'
import TagManagementView from './meta/TagManagementView.vue'
import StandardManagementView from './std/StandardManagementView.vue'
import IndicatorListView from './ind/IndicatorListView.vue'
import IndicatorBoardView from './ind/IndicatorBoardView.vue'
import ConsistencyCheckView from './ind/ConsistencyCheckView.vue'
import QualityRuleView from './qc/QualityRuleView.vue'
import QualityTaskView from './qc/QualityTaskView.vue'
import QualityReadOnlyView from './qc/QualityReadOnlyView.vue'

interface HubTab {
  id: string
  label: string
  component: Component
  props?: Record<string, string>
}

/** 治理域 13 页签（顺序 = 全局菜单「数据治理」组序，0.4 §4.2） */
const TABS: readonly HubTab[] = [
  { id: 'tag', label: '标签管理', component: TagManagementView },
  { id: 'std', label: '标准管理', component: StandardManagementView },
  { id: 'ind-list', label: '指标目录', component: IndicatorListView },
  { id: 'ind-board', label: '指标看板', component: IndicatorBoardView },
  { id: 'ind-consistency', label: '一致性检查', component: ConsistencyCheckView },
  { id: 'qc-rule', label: '质量规则', component: QualityRuleView },
  { id: 'qc-task', label: '检查任务', component: QualityTaskView },
  { id: 'qc-exception', label: '异常数据核查', component: QualityReadOnlyView, props: { kind: 'exceptions' } },
  { id: 'qc-report', label: '质量报告', component: QualityReadOnlyView, props: { kind: 'reports' } },
  { id: 'qc-alarm', label: '质量告警', component: QualityReadOnlyView, props: { kind: 'alarms' } },
] as const

const active = ref<string>(TABS[0].id)
const current = computed(() => TABS.find((t) => t.id === active.value) ?? TABS[0])

function onActivate(id: string): void {
  active.value = id
}
</script>

<template>
  <section class="gov-hub" aria-label="数据治理">
    <TabsView :tabs="TABS" :model-value="active" @update:model-value="onActivate">
      <KeepAlive>
        <component :is="current.component" :key="current.id" v-bind="current.props" />
      </KeepAlive>
    </TabsView>
  </section>
</template>

<style scoped>
.gov-hub {
  min-height: 0;
}
</style>
