<script setup lang="ts">
/**
 * 组件治理三页整合宿主（组件目录 / 基线化工作台 / 组件设计器）——单一入口模式
 * （对齐任务中心 DAG、血缘分析的同壳页签结构）。
 *
 * 页签流转：switchTab + router.replace({query:{tab}})（TaskCenterView 同款），
 * query 只在挂载时一次性读入、切页签单向 replace 同步（防 query ↔ 组件双源互踩）。
 * 深链分派：?tab=baseline&type=xxx 定位基线化设计区；?tab=designer&designType=xxx
 * 深链加载组件（6001 自动建稿 / 6002 自动开修订）。
 *
 * 三视图以 props 回调互联：目录「修改/组件设计器」、基线化「组件设计器」→ 切设计器页签；
 * 设计器「← 目录」/ 删除成功 → 切回目录页签；新建组件成功 → designTypeChange 同步深链。
 * v-show 保活：设计器编辑态（草稿/撤销栈）跨页签切换不丢失。
 */
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ComponentCatalogView from './ComponentCatalogView.vue'
import BaselineWorkbenchView from './BaselineWorkbenchView.vue'
import PageDesignerView from './pageDesigner/PageDesignerView.vue'

type TabKey = 'catalog' | 'baseline' | 'designer'
const tabs: { k: TabKey; label: string }[] = [
  { k: 'catalog', label: '组件目录' },
  { k: 'baseline', label: '基线化工作台' },
  { k: 'designer', label: '组件设计器' },
]

const route = useRoute()
const router = useRouter()

/* 挂载时一次性读入（深链分派） */
const qtab = String(route.query.tab ?? '')
const tab = ref<TabKey>(tabs.some((t) => t.k === qtab) ? (qtab as TabKey) : 'catalog')
const designType = ref(String(route.query.designType ?? ''))

/** 切页签：query 单向 replace 同步（仅保留 tab 与设计器深链 designType，防旧参数残留互踩） */
function switchTab(k: TabKey, nextDesignType?: string): void {
  tab.value = k
  if (nextDesignType !== undefined) designType.value = nextDesignType
  router.replace({
    query: { tab: k, ...(k === 'designer' && designType.value ? { designType: designType.value } : {}) },
  }).catch(() => {})
}

/** 目录/基线化 → 设计器（type 缺省 = 新建态） */
function openDesigner(type?: string): void {
  switchTab('designer', type ?? '')
}
/** 设计器 → 目录 */
function goCatalog(): void {
  switchTab('catalog')
}
/** 设计器新建组件成功：宿主深链同步（/meta/components?tab=designer&designType=xxx） */
function onDesignTypeChange(type: string): void {
  designType.value = type
  router.replace({ query: { tab: 'designer', designType: type } }).catch(() => {})
}
</script>

<template>
  <div class="hub">
    <nav class="hub-tabs">
      <button
        v-for="t in tabs" :key="t.k" type="button" class="hub-tab"
        :class="{ on: tab === t.k }" @click="switchTab(t.k)"
      >{{ t.label }}</button>
    </nav>
    <div class="hub-body">
      <ComponentCatalogView v-show="tab === 'catalog'" :open-designer="openDesigner" />
      <BaselineWorkbenchView v-show="tab === 'baseline'" :open-designer="openDesigner" />
      <PageDesignerView
        v-show="tab === 'designer'"
        :design-type="designType"
        :go-catalog="goCatalog"
        @design-type-change="onDesignTypeChange"
      />
    </div>
  </div>
</template>

<style scoped>
.hub {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}
.hub-tabs {
  display: flex;
  gap: 4px;
  padding: 8px 14px 0;
  background: var(--card);
  border-bottom: 1px solid var(--border);
  flex: none;
}
.hub-tab {
  appearance: none;
  border: 1px solid transparent;
  border-bottom: none;
  background: transparent;
  color: var(--text-2);
  font-size: 13px;
  padding: 6px 14px;
  border-radius: var(--radius-sm) var(--radius-sm) 0 0;
  cursor: pointer;
  transition: color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease);
}
.hub-tab:hover {
  color: var(--text);
}
.hub-tab.on {
  color: var(--primary);
  background: var(--bg);
  border-color: var(--border);
  font-weight: 600;
}
.hub-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.hub-body > * {
  flex: 1;
  min-height: 0;
}
/* 目录/基线化页根（.page）自身无滚动容器（原独立路由依赖 .main 自然流），宿主内补滚动；
   设计器 .pd-view 为 height:100% 三区域布局，自带内部滚动，不加 */
.hub-body > .page {
  overflow: auto;
}
</style>
