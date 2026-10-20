<template>
  <section class="home-projects" aria-label="项目列表">
    <header class="home-head">
      <h1>Datara</h1>
      <p class="home-sub">选择一个项目进入工作区</p>
    </header>

    <p v-if="loading" class="state state-loading" role="status">加载中…</p>
    <p v-else-if="error" class="state state-error" role="alert">{{ error }}</p>
    <p v-else-if="projects.length === 0" class="state state-empty">
      暂无项目：请先创建项目，或让项目拥有者将你添加为成员
    </p>

    <ul v-else class="project-grid">
      <li v-for="p in projects" :key="p.id">
        <button type="button" class="project-card" :data-project-id="p.id" @click="enter(p)">
          <span class="project-name">{{ p.name }}</span>
          <span v-if="p.ownOrJoined === 'owner'" class="project-badge">我拥有</span>
          <span v-else-if="p.ownOrJoined === 'joined'" class="project-badge joined">我参与</span>
        </button>
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
/**
 * L3-02 项目列表页（权威设计 §5A.11 方案 A）：登录后首页 = 项目卡片列表（我拥有/参与）。
 * 数据源 `GET /api/v1/rebuild/projects`（projectApi.listProjects）；三态：加载/错误/空。
 * 卡片点击 → `/p/:projectId`（项目工作区路由落地归 L3-03；未匹配时 vue-router 返回
 * failure 不 crash，本页先于路由就绪承接交互）。
 */
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { listProjects } from '../services/rebuild/projectApi'
import type { ProjectSummary } from '../services/rebuild/projectApi'

const router = useRouter()
const loading = ref(true)
const error = ref('')
const projects = ref<ProjectSummary[]>([])

function enter(p: ProjectSummary): void {
  router.push(`/p/${p.id}`)
}

onMounted(async () => {
  loading.value = true
  error.value = ''
  try {
    const page = await listProjects()
    projects.value = page.list
  } catch (err) {
    error.value = err instanceof Error ? err.message : '项目列表加载失败'
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.home-projects {
  max-width: 960px;
  margin: 0 auto;
  padding: 48px 24px;
}

.home-head {
  margin-bottom: 24px;
}

.home-head h1 {
  margin: 0 0 8px;
  font-size: 28px;
}

.home-sub {
  margin: 0;
  color: var(--text-secondary, #64748b);
}

.state {
  padding: 48px 0;
  text-align: center;
  color: var(--text-secondary, #64748b);
}

.state-error {
  color: #dc2626;
}

.project-grid {
  list-style: none;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
  margin: 0;
  padding: 0;
}

.project-card {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 20px 16px;
  border: 1px solid var(--border-color, #e2e8f0);
  border-radius: 10px;
  background: var(--bg-surface, #fff);
  cursor: pointer;
  text-align: left;
}

.project-card:hover {
  border-color: var(--primary-color, #2563eb);
}

.project-name {
  font-weight: 600;
}

.project-badge {
  flex: none;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  background: var(--primary-color, #2563eb);
  color: #fff;
}

.project-badge.joined {
  background: var(--text-secondary, #64748b);
}
</style>
