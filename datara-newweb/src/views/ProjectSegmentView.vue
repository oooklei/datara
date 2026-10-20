<template>
  <section class="segment-page" aria-label="项目功能段">
    <header class="seg-head">
      <h1>{{ heading }}</h1>
      <p class="seg-sub">{{ sub }}</p>
    </header>
  </section>
</template>

<script setup lang="ts">
/**
 * L3-03 项目功能段占位页（/p/:projectId/:seg 承载）：
 * 七段（dag/datasource/resources/ide/meta/dep/system）对应功能页属后续批次
 * （inc4 任务中心、inc10 数据源、inc11 SQL IDE 等），本票交付 = 路由可达 +
 * 菜单挂载（AppShell 项目模式侧栏）+ 占位呈现；正式功能页随各批次逐段替换本占位。
 * 未知 seg（:seg 为单段动态匹配，无 catch-all——1.4 §7.3 判据保持）渲染
 * 「未知功能段」不 crash 不落首页。
 */
import { computed } from 'vue'
import { PROJECT_MENU_SECTIONS } from '../navigation/projectMenu'

const props = defineProps<{ projectId: number; seg: string }>()

const section = computed(() => PROJECT_MENU_SECTIONS.find((s) => s.key === props.seg))
const heading = computed(() => section.value?.label ?? '未知功能段')
const sub = computed(() =>
  section.value ? '该功能段尚未开放：功能页随后续批次交付' : `未知的段标识：${props.seg}`,
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
