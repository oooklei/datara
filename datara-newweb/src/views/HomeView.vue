<template>
  <section class="home-projects" aria-label="数据治理工作台">
    <header class="home-head">
      <div><h1>数据治理工作台</h1><p class="home-sub">统一查看治理空间，并快速进入核心业务能力</p></div>
      <button class="primary-action" type="button" data-create-project @click="openCreate">＋ 新建项目</button>
    </header>

    <div class="stat-grid" aria-label="工作台统计">
      <article v-for="stat in dashboardStats" :key="stat.key" class="dashboard-card stat" data-dashboard-stat :data-stat-projects="stat.key === 'projects' ? '' : undefined">
        <div class="stat-top"><span class="stat-icon" :style="{ background: stat.iconBg, color: stat.iconColor }">{{ stat.icon }}</span><span>{{ stat.label }}</span></div>
        <strong>{{ stat.value }}</strong><small>{{ stat.description }}</small>
      </article>
    </div>

    <section class="dashboard-card quick-panel" aria-label="快捷入口">
      <div class="section-title">快捷入口</div>
      <p>从工作台直达数据开发、任务编排、数据源与集群监控。</p>
      <div class="entry-grid">
        <button v-for="entry in quickEntries" :key="entry.path" class="entry-card" type="button" :data-quick-entry="entry.path" @click="router.push(entry.path)">
          <span><b>{{ entry.title }}</b><small>{{ entry.description }}</small></span><i>→</i>
        </button>
      </div>
    </section>

    <div class="project-section-title"><div><h2>项目空间</h2><p>选择一个项目进入专属治理工作区</p></div></div>

    <p v-if="loading" class="state state-loading" role="status">加载中…</p>
    <p v-else-if="error" class="state state-error" role="alert">{{ error }}</p>
    <p v-else-if="projects.length === 0" class="state state-empty">
      暂无项目：请先创建项目，或让项目拥有者将你添加为成员
    </p>

    <ul v-else class="project-grid">
      <li v-for="p in projects" :key="p.id">
        <article
          class="project-card"
          :data-project-id="p.id"
          role="button"
          tabindex="0"
          @click="enter(p)"
          @keydown.enter.prevent="enter(p)"
          @keydown.space.prevent="enter(p)"
        >
          <span class="project-name">{{ p.name }}</span>
          <span v-if="p.ownOrJoined === 'owner'" class="project-badge">我拥有</span>
          <span v-else-if="p.ownOrJoined === 'joined'" class="project-badge joined">我参与</span>
          <span class="project-actions">
            <button type="button" data-edit-project @click.stop="openEdit(p)">编辑</button>
            <button type="button" data-delete-project @click.stop="remove(p)">删除</button>
          </span>
        </article>
      </li>
    </ul>
    <div v-if="editing" class="project-modal"><form ref="projectFormRef" :style="projectDragStyle" @submit.prevent="save"><h2 ref="projectHdRef" @pointerdown="onProjectDragStart">{{ editingId ? '编辑项目' : '新建项目' }}</h2><label>名称<input v-model.trim="draft.name" required data-project-name></label><label>说明<textarea v-model="draft.description" data-project-description /></label><p v-if="formError" role="alert">{{ formError }}</p><footer><button type="button" @click="editing=false">取消</button><button type="submit" data-save-project>保存</button></footer></form></div>
  </section>
</template>

<script setup lang="ts">
/**
 * L3-02 项目列表页（权威设计 §5A.11 方案 A）：登录后首页 = 项目卡片列表（我拥有/参与）。
 * 数据源 `GET /api/v1/rebuild/projects`（projectApi.listProjects）；三态：加载/错误/空。
 * 卡片点击 → `/p/:projectId`（项目工作区路由落地归 L3-03；未匹配时 vue-router 返回
 * failure 不 crash，本页先于路由就绪承接交互）。
 */
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useDraggable } from '../composables/useDraggable'
import { createProject, deleteProject, listProjects, updateProject, type ProjectInput } from '../services/rebuild/projectApi'
import type { ProjectSummary } from '../services/rebuild/projectApi'

const router = useRouter()
const loading = ref(true)
const error = ref('')
const projects = ref<ProjectSummary[]>([])
const editing = ref(false), editingId = ref<number>(), formError = ref('')
const draft = ref<ProjectInput>({ name: '', description: '' })
/* G14 §2.2：弹窗默认可拖动 + 视口钳制 + 位置记忆（把手=h2 标题） */
const projectFormRef = ref<HTMLFormElement | null>(null)
const projectHdRef = ref<HTMLElement | null>(null)
const { dragStyle: projectDragStyle, onHandlePointerdown: onProjectDragStart } = useDraggable(projectFormRef, projectHdRef, { storageKey: 'project.edit' })
const quickEntries = [
  { title: '数据开发 IDE', description: 'SQL 开发、资源管理与执行观测', path: '/ide' },
  { title: '任务中心', description: '工作流、同步、ETL 与流处理统一编排', path: '/dag' },
  { title: '数据源管理', description: '管理业务库、数仓与消息连接', path: '/ds/list' },
  { title: '集群监控', description: '查看运行时节点与集群运行状态', path: '/dep/monitor' },
]
const dashboardStats = computed(() => [
  { key: 'projects', label: '项目空间', value: String(projects.value.length), description: '当前账号可访问项目', icon: '▦', iconBg: 'var(--primary-light)', iconColor: 'var(--primary)' },
  { key: 'owned', label: '我拥有', value: String(projects.value.filter(item => item.ownOrJoined === 'owner').length), description: '由当前账号负责', icon: '◆', iconBg: 'var(--primary-light)', iconColor: 'var(--purple)' },
  { key: 'joined', label: '我参与', value: String(projects.value.filter(item => item.ownOrJoined === 'joined').length), description: '作为成员参与', icon: '◎', iconBg: 'var(--success-bg)', iconColor: 'var(--success)' },
  { key: 'entries', label: '核心入口', value: String(quickEntries.length), description: '高优先级业务入口', icon: '⌘', iconBg: 'var(--warn-bg)', iconColor: 'var(--warn)' },
])

function enter(p: ProjectSummary): void {
  router.push(`/p/${p.id}`)
}
function openCreate() { editingId.value = undefined; draft.value = { name: '', description: '' }; formError.value = ''; editing.value = true }
function openEdit(p: ProjectSummary) { editingId.value = p.id; draft.value = { name: p.name, description: '' }; formError.value = ''; editing.value = true }
async function save() { try { const p = editingId.value ? await updateProject(editingId.value, draft.value) : await createProject(draft.value); editing.value = false; if (editingId.value) projects.value = projects.value.map(x => x.id === p.id ? { ...x, ...p } : x); else projects.value = [...projects.value, p] } catch (err) { formError.value = err instanceof Error ? err.message : '项目保存失败' } }
async function remove(p: ProjectSummary) { if (!globalThis.confirm(`删除项目“${p.name}”？`)) return; try { await deleteProject(p.id); projects.value = projects.value.filter(x => x.id !== p.id) } catch (err) { error.value = err instanceof Error ? err.message : '项目删除失败' } }

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
  max-width: 1180px;
  margin: 0 auto;
  padding: 48px 24px;
}

.home-head {
  display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:20px;
}

.home-head h1 {
  margin: 0 0 8px;
  font-size: 28px;
}

.home-sub {
  margin: 0;
  color: var(--text-secondary, var(--text-2));
}
.primary-action{border:0;border-radius:var(--radius);background:var(--primary);color:var(--card);padding:10px 16px;font-weight:700;cursor:pointer;box-shadow:var(--shadow-primary)}
.stat-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-bottom:16px}.dashboard-card{background:var(--card);border:1px solid var(--border);border-radius:var(--radius-lg);box-shadow:var(--shadow)}.stat{padding:16px}.stat-top{display:flex;align-items:center;gap:8px;color:var(--text-2);font-size:12.5px;margin-bottom:10px}.stat-icon{width:28px;height:28px;border-radius:var(--radius);display:grid;place-items:center}.stat strong{display:block;font-size:24px;line-height:1.2}.stat small{display:block;color:var(--text-3);font-size:11.5px;margin-top:3px}.quick-panel{padding:16px;margin-bottom:24px}.section-title{font-size:14px;font-weight:700}.section-title::before{content:'';display:inline-block;width:3px;height:14px;margin-right:8px;vertical-align:-2px;border-radius:2px;background:linear-gradient(180deg,var(--primary),var(--purple))}.quick-panel>p{margin:5px 0 12px;color:var(--text-3);font-size:12px}.entry-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.entry-card{display:flex;align-items:center;justify-content:space-between;text-align:left;border:1px solid var(--border);border-radius:var(--radius);padding:13px;background:var(--card);cursor:pointer;transition:var(--dur-base) var(--ease)}.entry-card:hover{border-color:var(--primary);box-shadow:var(--shadow-primary);transform:translateY(-1px)}.entry-card span,.entry-card small{display:block}.entry-card b{font-size:13px}.entry-card small{margin-top:5px;color:var(--text-2);line-height:1.4}.entry-card i{font-style:normal;color:var(--primary);font-size:18px}.project-section-title{display:flex;align-items:end;justify-content:space-between;margin:0 0 14px}.project-section-title h2{font-size:18px;margin:0}.project-section-title p{font-size:12px;color:var(--text-3);margin:4px 0 0}

.state {
  padding: 48px 0;
  text-align: center;
  color: var(--text-secondary, var(--text-2));
}

.state-error {
  color: var(--danger);
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
  border: 1px solid var(--border-color, var(--border));
  border-radius: 10px;
  background: var(--bg-surface, var(--card));
  cursor: pointer;
  text-align: left;
}

.project-card:hover {
  border-color: var(--primary-color, var(--primary));
}
.project-actions{display:flex;gap:6px;margin-left:auto}.project-actions button{border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--card);color:var(--text-2);padding:4px 8px;cursor:pointer}.project-actions button:hover{border-color:var(--primary);color:var(--primary)}.project-modal{position:fixed;inset:0;z-index:50;display:grid;place-items:center;background:rgba(15,23,42,.38);backdrop-filter:blur(2px)}.project-modal form{display:grid;gap:14px;width:min(440px,calc(100vw - 32px));padding:24px;border:1px solid var(--border);border-radius:var(--radius-xl);background:var(--card);box-shadow:var(--shadow-xl)}.project-modal h2{margin:0;cursor:grab;user-select:none}
.project-modal h2:active{cursor:grabbing}.project-modal label{display:grid;gap:6px;color:var(--text-2);font-size:13px}.project-modal input,.project-modal textarea{box-sizing:border-box;width:100%;border:1px solid var(--border);border-radius:var(--radius-sm);padding:9px 10px;font:inherit}.project-modal textarea{min-height:88px;resize:vertical}.project-modal footer{display:flex;justify-content:flex-end;gap:8px}.project-modal footer button{border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--card);padding:8px 14px;cursor:pointer}.project-modal footer button:last-child{border-color:var(--primary);background:var(--primary);color:var(--card)}

.project-name {
  font-weight: 600;
}

.project-badge {
  flex: none;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  background: var(--primary-color, var(--primary));
  color: var(--card);
}

.project-badge.joined {
  background: var(--text-secondary, var(--text-2));
}
@media (max-width:900px){.stat-grid,.entry-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media (max-width:560px){.home-projects{padding:24px 14px}.home-head{align-items:flex-start;flex-direction:column}.stat-grid,.entry-grid{grid-template-columns:1fr}}
</style>
