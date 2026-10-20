<script setup lang="ts">
/**
 * 应用根（增量 2 / 票 2-05 改造）：
 * - 认证业务壳走 AppShell（三段式+菜单消费+AI 全局挂载点，0.8 §6）；
 * - 登录页等非业务壳不挂载 AppShell（0.8 §6 规则 1）——AI 挂载点随 AppShell 保证单实例；
 * - 会话判定读 http 底座 token（1.2 交付）；会话流程归登录域，本组件只做壳切换。
 */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import AppShell from './layouts/AppShell.vue'
import { getToken } from './services/http'

const route = useRoute()
const shellActive = computed(() => route.path !== '/login' && getToken() !== '')
</script>

<template>
  <AppShell v-if="shellActive" />
  <RouterView v-else />
</template>
