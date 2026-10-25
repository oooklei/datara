<template>
  <component :is="segmentView" v-if="segmentView" :project-id="projectId" />
  <section v-else class="segment-page" aria-label="项目功能段">
    <header class="seg-head">
      <h1>{{ heading }}</h1>
      <p class="seg-sub">{{ sub }}</p>
    </header>
  </section>
</template>

<script setup lang="ts">
/**
 * L3-03 项目功能段占位页（/p/:projectId/:seg 承载）：
 * 七段（dag/datasource/resources/ide/meta/dep/system）由 segmentViews 映射承载
 * 正式功能页，路由与 AppShell 项目模式侧栏保持同源。
 * 未知 seg（:seg 为单段动态匹配，无 catch-all——1.4 §7.3 判据保持）渲染
 * 「未知功能段」不 crash 不落首页。
 */
import { computed, type Component } from 'vue'
import { PROJECT_MENU_SECTIONS } from '../navigation/projectMenu'
import TaskCenterView from './TaskCenterView.vue'
import ResourceManagementView from './resources/ResourceManagementView.vue'
import SystemAdminView from './system/SystemAdminView.vue'
import DataSourceListView from './datasource/DataSourceListView.vue'
import IdeView from './ide/IdeView.vue'
import MetadataCatalogView from './meta/MetadataCatalogView.vue'
import MonitorView from './depops/MonitorView.vue'

const props = defineProps<{ projectId: number; seg: string }>()

const section = computed(() => PROJECT_MENU_SECTIONS.find((s) => s.key === props.seg))
const segmentViews: Record<string, Component> = {
  dag: TaskCenterView,
  datasource: DataSourceListView,
  resources: ResourceManagementView,
  ide: IdeView,
  meta: MetadataCatalogView,
  dep: MonitorView,
  system: SystemAdminView,
}
const segmentView = computed(() => segmentViews[props.seg])
const heading = computed(() => section.value?.label ?? '未知功能段')
const segmentDescriptions: Record<string, string> = {
  dag: '工作流编排、节点组件与运行实例',
  datasource: '数据源连接与元数据浏览',
  resources: '项目资源与执行环境管理',
  ide: 'SQL、Python 与 Shell 数据开发',
  meta: '元数据目录与资产检索',
  dep: '依赖运行节点与执行监控',
  system: '项目权限与安全配置',
}
const sub = computed(() =>
  section.value ? (segmentDescriptions[props.seg] ?? '项目功能') : `未知的段标识：${props.seg}`,
)
</script>

<style scoped>
.segment-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 48px 24px;
}

.seg-head {
  margin-bottom: 20px;
}

.seg-head h1 {
  margin: 0 0 8px;
  font-size: 24px;
}

.seg-sub {
  margin: 0;
  color: var(--text-secondary, #64748b);
}
</style>
