<!-- 部署运维顶栏入口（hero 右上角 ☁）的子导航：运行时节点 / 集群监控 / SSH 节点。
     口径来源：docs/increments/2026-10-28-旧前端对标审计-04其余业务域.md §2.1
     「SSH 节点管理在『运行时节点』页」——旧前端把 SSH 节点注册/凭据维护挂在部署运维下，
     新前端 SSH 节点页（/dep/ssh）功能已完备但无入口可达，本组件补齐该入口。
     样式复用全局 `.seg` 分段控件语义（灰底容器 + 白底浮起 active），不新造视觉。 -->
<template>
  <nav class="seg dep-ops-subnav" aria-label="部署运维子导航" data-sub-nav>
    <RouterLink to="/dep/runtime" data-sub-nav-item="runtime">运行时节点</RouterLink>
    <RouterLink v-if="canReadMonitor" to="/dep/monitor" data-sub-nav-item="monitor">集群监控</RouterLink>
    <RouterLink to="/dep/ssh" data-sub-nav-item="ssh">SSH 节点</RouterLink>
    <RouterLink to="/dep/worker-group" data-sub-nav-item="worker-group">Worker 分组</RouterLink>
    <RouterLink to="/dep/environment" data-sub-nav-item="environment">环境管理</RouterLink>
    <RouterLink to="/dep/queue" data-sub-nav-item="queue">Yarn 队列</RouterLink>
    <RouterLink to="/dep/cluster" data-sub-nav-item="cluster">集群管理</RouterLink>
    <RouterLink to="/dep/resource-file" data-sub-nav-item="resource-file">资源文件</RouterLink>
  </nav>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { authAccount } from '../services/rebuild/authApi'
import { roleHasPermission } from '../services/rebuild/rolePermissions'

const canReadMonitor = computed(() =>
  authAccount.value !== null && roleHasPermission(authAccount.value.role, 'monitor:read'),
)
/**
 * 部署运维子导航（纯展示 + 路由跳转，无状态、无契约取数）。
 *
 * 与 TabsView 的差异：TabsView 是受控内容页签壳（内容切换，非导航），
 * 本组件是路由级子导航，用于打通顶栏部署运维图标到 /dep/ssh 凭据维护面。
 */
</script>

<style scoped>
/* 复用全局 .seg 的分段控件语义（theme.css §.seg）；仅修正为链接元素（a）的可用态着色。 */
.dep-ops-subnav { display: inline-flex; }
.dep-ops-subnav a {
  text-decoration: none;
  border: none;
  background: transparent;
  padding: 5px 14px;
  font-size: 12px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-2);
  min-height: 28px;
  line-height: 18px;
  transition: all var(--dur-base) var(--ease);
}
.dep-ops-subnav a:hover { color: var(--text); }
/* RouterLink 当前路由命中时注入 router-link-active */
.dep-ops-subnav a.router-link-active {
  background: var(--card);
  color: var(--primary);
  font-weight: 600;
  box-shadow: 0 1px 3px rgba(16, 24, 40, .14);
}
</style>
