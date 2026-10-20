<script setup lang="ts">
/**
 * 表格页范式组件（增量 2 / 票 2-06）
 *
 * 蓝本：权威设计 §4.1（L304 页面布局骨架=§4 抄袭范畴；§5D 三层调和——复刻筛选区+表格+
 * 分页三段布局语义，不复制旧业务组件实现代码）；旧前端实锚（datara-web 各列表页
 * 筛选区/表格/分页纵向布局）。WBS 2.3 验收方式之一；WBS 退出标准 3：供增量 3/10 实际消费。
 * 纪律：纯插槽化布局壳，零业务逻辑零数据获取；页面内容经插槽注入。
 */
</script>

<template>
  <section class="table-page-layout">
    <div class="filter-section" data-part="filters"><slot name="filters" /></div>
    <div class="table-section" data-part="table"><slot name="table" /></div>
    <div class="pagination-section" data-part="pagination"><slot name="pagination" /></div>
  </section>
</template>

<style scoped>
.table-page-layout{display:flex;flex-direction:column;gap:12px;padding:16px}
.filter-section{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.table-section{min-height:0}
.pagination-section{display:flex;justify-content:flex-end}
</style>
