<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const title = computed(() => (route.meta.title as string) || '模块')
</script>

<template>
  <div class="page placeholder">
    <div class="ph-card">
      <div class="ph-icon">◌</div>
      <h2>{{ title }}</h2>
      <p>建设中 · 后续 wave 填充</p>
    </div>
  </div>
</template>

<style scoped>
.placeholder { display: flex; align-items: center; justify-content: center; }
.ph-card { text-align: center; padding: 60px 40px; }
.ph-icon { font-size: 44px; color: var(--text-3); margin-bottom: 12px; }
.ph-card h2 { font-size: 18px; color: var(--text); margin-bottom: 6px; }
.ph-card p { font-size: 13px; color: var(--text-3); }
</style>