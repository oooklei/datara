<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from './stores/auth'
import { dataStore } from './services/mock/dataStore'
import { isMock } from './services'
import { listAlertNotifications } from './services/alertApi'
import { ROLE_LABELS } from './stores/auth'
import { R8A_TOOL_VERSION, type R8ARunSqlResult, type R8AToolCallError } from './services/rebuild/aiToolsApi'
import { createMockAgent, generateSqlMock, type MockAuditRecord } from './views/rebuild/validation/ai-assistant/mockAgent'
import type { User } from './services/types'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
onMounted(() => { auth.init(); loadNotifs() })

/* 登录页独立壳：不带侧栏/顶栏 */
const isLoginRoute = computed(() => route.path === '/login')
const loggedIn = computed(() => !!auth.token)
/* 顶栏用户区：已登录显示账号+角色徽标+退出；mock 未登录保留演示态切换；real 未登录隐藏（守卫强制登录） */
const showAccountChip = computed(() => loggedIn.value || (isMock && !!auth.account))
const showDemoChip = computed(() => isMock && !auth.token)

async function onLogout() {
  auth.logout()
  router.replace('/login')
}

const userMenu = ref(false)
function pick(u: User) {
  auth.switchUser(u)
  userMenu.value = false
}

/* ---------- 站内消息中心（notifications 集合） ----------
 * 消息形成：任务/质量/部署告警规则触发、审批待办、渠道测试回执（DeployAlarmView 测试发送写入）
 * 消息流转：铃铛下拉展示 → 点击置为已读（localStorage 持久化）并跳转关联页面 */
interface NotifRow { id: number; icon: string; cls: string; title: string; desc: string; time: string; target?: string }
const notifOpen = ref(false)
const notifs = ref<NotifRow[]>([])
const readIds = ref<Set<number>>(new Set(JSON.parse(localStorage.getItem('datara_read_notif') || '[]') as number[]))
const unread = computed(() => notifs.value.filter((n) => !readIds.value.has(n.id)).length)
async function loadNotifs() {
  try {
    notifs.value = isMock
      ? await dataStore.list<NotifRow>('notifications')
      : await listAlertNotifications()
  } catch { notifs.value = [] }
}
/* 消息 → 关联页面跳转映射（I6：同步进度看板下线，类型 2 落同步任务列表；F56d：类型 1 落真实运行实例页，/dag/runs 已删除） */
const NOTIF_ROUTE: Record<number, string> = { 1: '/dag/instances', 2: '/sync/list', 3: '/qc/exception' }
function openNotif(n: NotifRow) {
  if (!readIds.value.has(n.id)) {
    readIds.value = new Set(readIds.value).add(n.id)
    localStorage.setItem('datara_read_notif', JSON.stringify([...readIds.value]))
  }
  const target = n.target || NOTIF_ROUTE[n.id]
  if (target) { notifOpen.value = false; router.push(target) }
}

interface MenuItem { label: string; path: string; icon?: string; children?: MenuItem[] }
interface MenuGroup { group: string; items: MenuItem[]; demo?: boolean; foldable?: boolean }

/* F56a IA 收敛（裁定 2A/3B）：任务中心一级直达；真实域菜单瘦身（数据集成/数据开发/数据治理/部署运维）；
 * 全部演示态模块折叠进「扩展（演示）」分组（默认收起，组头挂演示标识）；路由全保留，仅菜单归组 */
const menus: MenuGroup[] = [
  { group: '总览', items: [
    { label: '工作台', path: '/', icon: '◆' },
  ]},
  // 一级直达（裁定 2A）：任务中心提为一级菜单（画布直达 6 页签不变）
  { group: '', items: [
    { label: '任务中心', path: '/dag', icon: '⑃' },
  ]},
  { group: '数据集成', items: [
    { label: '数据源管理', path: '/ds/list', icon: '⛁' },
    { label: '同步任务', path: '/sync/list', icon: '⇄' },
  ]},
  { group: '数据开发', items: [
    { label: '数据开发IDE', path: '/ide', icon: '⌨' },
    { label: '数仓建模', path: '/model/list', icon: '▤' },
  ]},
  { group: '数据治理', items: [
    { label: '血缘分析', path: '/meta/lineage', icon: '⇶' },
    { label: '资产地图', path: '/meta/map', icon: '◉' },
    { label: '元数据目录', path: '/meta/catalog', icon: '☰' },
    { label: '标签管理', path: '/meta/tag', icon: '⌗' },
    { label: '标准管理', path: '/std/element', icon: '⌇' },
    { label: '指标目录', path: '/ind/list', icon: '✦' },
    { label: '指标看板', path: '/ind/board', icon: '▦' },
    { label: '一致性检查', path: '/ind/consistency', icon: '✓' },
  ]},
  { group: '部署运维', items: [
    { label: '运行时节点', path: '/dep/runtime', icon: '⌂' },
    { label: '集群监控', path: '/dep/monitor', icon: '◈' },
  ]},
  // 扩展（演示）（裁定 3B）：本期范围外演示模块收纳，默认折叠；组头挂「演示」标识
  { group: '扩展（演示）', demo: true, foldable: true, items: [
    { label: '脚本任务', path: '/script/list', icon: '⌘' },
    { label: '参数配置', path: '/param/global', icon: '⚑' },
    { label: '质量规则', path: '/qc/rule', icon: '☑' },
    { label: '检查任务', path: '/qc/task', icon: '⏱' },
    { label: '异常数据核查', path: '/qc/exception', icon: '✖' },
    { label: '质量报告', path: '/qc/report', icon: '▣' },
    { label: '质量告警', path: '/qc/alarm', icon: '⚡' },
    { label: '评分总览', path: '/qc/score', icon: '★' },
    { label: '权限管理', path: '/sec/perm', icon: '⛨' },
    { label: '脱敏规则', path: '/sec/mask', icon: '✳' },
    { label: '访问审计', path: '/sec/audit', icon: '⧉' },
    { label: 'API管理', path: '/open/api', icon: '⇋' },
    { label: 'API-Key管理', path: '/open/key', icon: '⚿' },
    { label: '调用日志', path: '/open/log', icon: '⇢' },
    { label: '部署中心', path: '/dep/center', icon: '⛅' },
    { label: '组件日志', path: '/dep/log', icon: '≣' },
    { label: '告警管理', path: '/dep/alarm', icon: '⚠' },
    { label: '运维操作', path: '/dep/ops', icon: '⚙' },
  ]},
]

/* 菜单项子树（无 children 使用场景已下线，保留结构兼容）；扩展（演示）组默认折叠 */
const groupFolded = ref<Record<string, boolean>>({ '扩展（演示）': true })
function toggleGroup(name: string) { groupFolded.value = { ...groupFolded.value, [name]: !groupFolded.value[name] } }

const pageTitle = computed(() => (route.meta.title as string) || '')
const isActive = (item: MenuItem) =>
  item.path === '/' ? route.path === '/' : route.path === item.path || route.path.startsWith(item.path + '/')

/* ---------- FE-11a AI 悬浮入口（mock 契约面，无 LLM） ---------- */
const mockAgent = createMockAgent()
const aiDrawerVisible = ref(false)
const aiContextType = ref('SQL')
const aiContextRef = ref('{"project_id": 1, "table_name": "dw.dim_customer"}')
const aiNlInput = ref('')
const aiGeneratedSql = ref('')
const aiGeneratedExplanation = ref('')
const aiConfirmed = ref(false)
const aiRunResult = ref<R8ARunSqlResult | null>(null)
const aiLastError = ref<R8AToolCallError | null>(null)
const aiAuditRows = ref<MockAuditRecord[]>([])

function openAiDrawer(): void {
  aiDrawerVisible.value = true
  refreshAiAudit()
}

function refreshAiAudit(): void {
  aiAuditRows.value = [...mockAgent.auditRecords()].reverse()
}

function parseAiContext(): Record<string, unknown> | null {
  const text = aiContextRef.value.trim()
  if (!text) return null
  try {
    const parsed = JSON.parse(text) as unknown
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : null
  } catch {
    return null
  }
}

function onAiGenerate(): void {
  aiLastError.value = null
  aiRunResult.value = null
  aiConfirmed.value = false
  aiGeneratedSql.value = ''
  aiGeneratedExplanation.value = ''
  const contextRef = parseAiContext()
  try {
    const generated = generateSqlMock(aiNlInput.value.trim(), { contextType: aiContextType.value as never, contextRef }, 'user-trae')
    aiGeneratedSql.value = generated.sql
    aiGeneratedExplanation.value = generated.explanation
  } catch (e) {
    aiLastError.value = {
      code: 'MOCK_SOVEREIGNTY_CONTEXT_MISSING',
      message: e instanceof Error ? e.message : String(e),
      retryable: false,
    }
  }
}

async function onAiRunSql(): Promise<void> {
  aiLastError.value = null
  aiRunResult.value = null
  const contextRef = parseAiContext()
  try {
    const res = await mockAgent.call(
      {
        toolCallId: `tc-ai-${Date.now()}`,
        tool: 'run_sql',
        toolVersion: R8A_TOOL_VERSION,
        params: { project_id: 1, datasource_id: 'ds-1', sql: aiGeneratedSql.value },
        pageContext: { contextType: aiContextType.value as never, contextRef },
      },
      { userId: 'user-trae', roles: ['DEVELOPER'] },
    )
    refreshAiAudit()
    if (res.status === 'SUCCESS' && res.result) {
      aiRunResult.value = res.result as unknown as R8ARunSqlResult
    } else if (res.error) {
      aiLastError.value = res.error
    }
  } catch (e) {
    aiLastError.value = { code: 'INTERNAL_ERROR', message: e instanceof Error ? e.message : String(e), retryable: false }
  }
}

const aiResultRows = computed(() => {
  if (!aiRunResult.value) return []
  return aiRunResult.value.rows.map((row) => {
    const record: Record<string, unknown> = {}
    row.forEach((cell, i) => {
      record[String(i)] = cell
    })
    return record
  })
})
</script>

<template>
  <!-- 登录页独立壳（无侧栏/顶栏） -->
  <router-view v-if="isLoginRoute" />
  <div v-else class="layout">
    <aside class="sidebar">
      <div class="logo"><span class="mark">D</span>Datara</div>
      <nav class="menu">
        <template v-for="grp in menus" :key="grp.group">
          <!-- 组标题：空组名（任务中心一级直达）不渲染；可折叠组（扩展演示）点击标题收展 -->
          <div
            v-if="grp.group"
            class="menu-group-title"
            :class="{ clickable: grp.foldable }"
            @click="grp.foldable && toggleGroup(grp.group)"
          >
            {{ grp.group }}
            <span v-if="grp.demo" class="grp-demo-tag" title="本期范围外模块，数据为演示样例">演示</span>
            <span v-if="grp.foldable" class="grp-caret" :class="{ open: !groupFolded[grp.group] }">▾</span>
          </div>
          <template v-if="!grp.foldable || !groupFolded[grp.group]">
            <template v-for="item in grp.items" :key="item.path">
              <div
                class="menu-item" :class="{ active: isActive(item) }"
                @click="$router.push(item.path)"
              >
                <span class="ico">{{ item.icon }}</span><span class="lbl">{{ item.label }}</span>
              </div>
            </template>
          </template>
        </template>
      </nav>
    </aside>
    <div class="main">
      <header class="topbar">
        <span class="crumb">Datara / <b>{{ pageTitle }}</b></span>
        <!-- F56e：演示模块标识（路由 meta.demo），低饱和描边不做警告色，悬停提示说明 -->
        <span v-if="route.meta.demo" class="demo-tag" title="本期范围外模块，数据为演示样例">演示数据</span>
        <span class="spacer" />
        <div class="bell" @click="notifOpen = !notifOpen">
          <svg class="bell-ico" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>
          <span v-if="unread" class="bell-badge">{{ unread }}</span>
          <div v-if="notifOpen" class="notif-pop" @click.stop>
            <div class="pop-title">消息中心 · 未读 {{ unread }}</div>
            <div
              v-for="n in notifs" :key="n.id"
              class="notif-item" :class="[n.cls, { read: readIds.has(n.id) }]"
              @click="openNotif(n)"
            >
              <span class="n-ico">{{ n.icon }}</span>
              <div class="n-meta"><b>{{ n.title }}</b><span>{{ n.desc }}</span></div>
              <span class="n-time">{{ n.time }}</span>
            </div>
            <div v-if="!notifs.length" class="notif-empty">暂无消息</div>
          </div>
        </div>
        <!-- 顶栏用户区：F5 登录态（用户名+角色徽标+退出）；未登录隐藏 -->
        <div v-if="showAccountChip" class="user-chip" @click="userMenu = !userMenu">
          <div class="avatar">{{ (auth.account?.name ?? auth.current.name).slice(0, 1) }}</div>
          <div class="user-meta">
            <b>{{ auth.account?.name ?? auth.current.name }}</b>
            <span class="role-badge" :class="'role-' + (auth.account?.role ?? 'viewer')">{{ ROLE_LABELS[auth.account?.role ?? ''] ?? auth.current.role }}</span>
          </div>
          <span class="caret" :class="{ open: userMenu }">▾</span>
          <div v-if="userMenu" class="user-pop" @click.stop>
            <div class="pop-title">当前登录</div>
            <div class="pop-item on">
              <b>{{ auth.account?.name }}</b>
              <span>{{ ROLE_LABELS[auth.account?.role ?? ''] ?? auth.account?.role }}</span>
            </div>
            <div class="pop-logout" @click="onLogout">退出登录</div>
          </div>
        </div>
        <!-- mock 未登录：M15 演示态身份切换（纯前端本地测试用） -->
        <div v-else-if="showDemoChip" class="user-chip" @click="userMenu = !userMenu">
          <div class="avatar">{{ auth.current.name.slice(0, 1) }}</div>
          <div class="user-meta">
            <b>{{ auth.current.name }}</b>
            <span>{{ auth.current.role }} · 许可 {{ auth.current.clearance ?? '内部' }}</span>
          </div>
          <span class="caret" :class="{ open: userMenu }">▾</span>
          <div v-if="userMenu" class="user-pop" @click.stop>
            <div class="pop-title">切换身份（演示）</div>
            <div
              v-for="u in auth.users" :key="u.id"
              class="pop-item" :class="{ on: u.name === auth.current.name }"
              @click="pick(u)"
            >
              <b>{{ u.name }}</b>
              <span>{{ u.roleName }} · {{ u.clearance }}</span>
            </div>
          </div>
        </div>
      </header>
      <router-view v-slot="{ Component }">
        <transition name="route-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </div>

    <!-- FE-11a AI 悬浮入口（mock 契约面，无 LLM） -->
    <div
      v-if="!isLoginRoute"
      class="ai-fab"
      data-testid="ai-fab"
      title="AI 助手（mock）"
      @click="openAiDrawer"
    >
      <span>AI</span>
    </div>
    <el-drawer
      v-model="aiDrawerVisible"
      title="AI 助手（mock 契约面）"
      size="46%"
      data-testid="ai-drawer"
    >
      <div class="ai-drawer-body">
        <el-form label-width="110px" size="small">
          <el-form-item label="page_context">
            <el-select v-model="aiContextType" style="width: 180px">
              <el-option label="SQL" value="SQL" />
              <el-option label="DDL" value="DDL" />
              <el-option label="DML" value="DML" />
            </el-select>
            <el-input
              v-model="aiContextRef"
              style="width: 300px; margin-left: 8px"
              placeholder='{"project_id":1,"table_name":"dw.dim_customer"}'
            />
          </el-form-item>
          <el-form-item label="自然语言">
            <el-input
              v-model="aiNlInput"
              type="textarea"
              :rows="2"
              placeholder="例：客户表有多少行数据 / 查询客户表的数据"
            />
          </el-form-item>
          <el-form-item label="">
            <el-button type="primary" size="small" :disabled="!aiNlInput.trim()" @click="onAiGenerate">
              生成 SQL（mock 假 Agent）
            </el-button>
          </el-form-item>
          <el-form-item v-if="aiGeneratedSql" label="生成 SQL">
            <el-input :model-value="aiGeneratedSql" type="textarea" :rows="2" readonly />
          </el-form-item>
          <el-form-item v-if="aiGeneratedExplanation" label="生成解释">
            <span class="ai-explanation">{{ aiGeneratedExplanation }}</span>
          </el-form-item>
          <el-form-item v-if="aiGeneratedSql" label="授权确认">
            <el-checkbox v-model="aiConfirmed">
              我确认经 R8-A 授权通道执行该 SQL
            </el-checkbox>
            <el-button
              type="danger"
              size="small"
              :disabled="!aiConfirmed"
              style="margin-left: 12px"
              @click="onAiRunSql"
            >
              执行 run_sql
            </el-button>
          </el-form-item>
        </el-form>

        <template v-if="aiRunResult">
          <div class="ai-panel">
            <div class="ai-panel-head">
              <span>执行结果（run_sql）</span>
              <span class="ai-meta">
                execution_id={{ aiRunResult.executionId }} / row_count={{ aiRunResult.rowCount }} / {{ aiRunResult.durationMs }}ms
              </span>
            </div>
            <el-table :data="aiResultRows" size="small" max-height="240">
              <el-table-column
                v-for="(col, i) in aiRunResult.columns"
                :key="col.name"
                :prop="String(i)"
                :label="`${col.name} (${col.type})`"
              />
            </el-table>
          </div>
          <el-alert
            type="success"
            :closable="false"
            show-icon
            :title="`结果解释：${aiGeneratedExplanation}（共 ${aiRunResult.rowCount} 行）`"
            class="ai-status"
          />
        </template>

        <el-alert
          v-if="aiLastError"
          type="error"
          :closable="false"
          show-icon
          :title="`错误：${aiLastError.code}（retryable=${aiLastError.retryable}）${aiLastError.message}`"
          class="ai-status"
        />
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
/* F56a：扩展（演示）组级标识与折叠指示 */
.menu-group-title.clickable{cursor:pointer;user-select:none}
.menu-group-title.clickable:hover{color:var(--text)}
.grp-demo-tag{display:inline-flex;align-items:center;margin-left:5px;padding:0 5px;border:1px solid var(--border);border-radius:var(--radius-lg);font-size:9.5px;font-weight:400;color:var(--text-3);line-height:1.5;cursor:help}
.grp-caret{margin-left:auto;font-size:9px;opacity:.6;transition:transform .15s}
.grp-caret.open{transform:rotate(180deg)}
.role-badge{display:inline-flex;align-items:center;padding:0 7px;border-radius:var(--radius-lg);font-size:10px;font-weight:600;background:var(--primary-light);color:var(--primary)}
.role-badge.role-admin{background:var(--danger-bg);color:var(--danger)}
.role-badge.role-dev{background:var(--info-bg);color:var(--info)}
.role-badge.role-analyst{background:var(--warn-bg);color:var(--warn)}
.role-badge.role-viewer{background:var(--bg);color:var(--text-3)}
.pop-logout{border-top:1px solid var(--border);margin-top:4px;padding:8px 12px;font-size:12px;color:var(--danger);cursor:pointer;text-align:center}
.pop-logout:hover{background:var(--danger-bg)}
/* F56e：顶栏演示数据标识（低饱和描边 tag，与整体风格一致） */
.demo-tag{display:inline-flex;align-items:center;padding:1px 8px;border:1px solid var(--border);border-radius:var(--radius-lg);font-size:11px;color:var(--text-3);cursor:help;white-space:nowrap}
/* FE-11a AI 悬浮入口 */
.ai-fab{position:fixed;right:32px;bottom:48px;width:48px;height:48px;border-radius:50%;background:var(--el-color-primary);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:700;cursor:pointer;box-shadow:var(--el-box-shadow-light);z-index:2000;transition:transform .15s}
.ai-fab:hover{transform:scale(1.08)}
.ai-drawer-body{display:flex;flex-direction:column;gap:12px}
.ai-panel{border:1px solid var(--el-border-color-light);border-radius:4px;padding:8px}
.ai-panel-head{display:flex;align-items:center;gap:8px;margin-bottom:8px;font-weight:600;font-size:13px}
.ai-meta{font-weight:400;font-size:12px;color:var(--el-text-color-secondary)}
.ai-explanation{font-size:12px;color:var(--el-text-color-regular)}
.ai-status{width:100%}
</style>
