<script setup lang="ts">
/**
 * 工作流定义列表 —— 双模式：
 * 1. 常规列表页（独立路由用法，保留兼容）；
 * 2. embed=true：任务中心「看列表」弹窗内嵌，点「可视化编排」不跳路由，
 *    emit('open', id) 由任务中心切换内嵌画布（可视化直达，弹窗即关）。
 * I1 F9：real 模式列表/新建/删除走后端 /api/v1/workflow-definitions；mock 保留 seed 演示。
 */
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { seedWorkflows, newWorkflowDoc } from '../services/mock/seed'
import { graphService, isMock, listDefinitions, createDefinition, deleteDefinition } from '../services'
import { localTime } from '../services/mock/timeUtil'
import { useAuthStore } from '../stores/auth'
import ScheduleDialog from './dag/ScheduleDialog.vue'

/** 统一行形状（mock WorkflowMeta 与 real DefinitionMeta 归一化） */
interface Row {
  id: string; name: string; cron: string; nodes: number
  owner: string; status: string; version: number; updatedAt: string
}

const props = defineProps<{ embed?: boolean }>()
const emit = defineEmits<{ (e: 'open', id: string): void }>()
const router = useRouter()
const auth = useAuthStore()
const rows = ref<Row[]>([])
const loading = ref(false)

function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e)
}

onMounted(async () => {
  if (isMock) {
    rows.value = seedWorkflows.map((w) => ({ ...w, nodes: w.nodes ?? 0 }))
    return
  }
  loading.value = true
  try {
    const defs = await listDefinitions()
    rows.value = defs.map((d) => ({
      id: d.id, name: d.name, cron: d.cron ?? '-', nodes: d.nodeCount ?? 0,
      owner: d.owner ?? '-', status: d.status ?? 'offline', version: d.version, updatedAt: d.updatedAt,
    }))
  } catch (e) {
    ElMessage.error('工作流列表加载失败：' + errMsg(e) + '（检查后端服务与登录态）')
  } finally {
    loading.value = false
  }
})

async function onCreate() {
  if (!auth.canEdit) { ElMessage.warning('当前角色为只读，无权创建工作流'); return }
  const { value } = await ElMessageBox.prompt('工作流名称', '新建工作流', {
    confirmButtonText: '创建并编排', cancelButtonText: '取消',
    inputPattern: /\S+/, inputErrorMessage: '名称不能为空',
  })
  let newId: string
  if (isMock) {
    newId = `wf_${Date.now().toString(36)}`
    await graphService.save(newWorkflowDoc(newId, value))
    rows.value.unshift({ id: newId, name: value, cron: '0 0 0 * * ?', owner: '王工', status: 'offline', version: 1, updatedAt: localTime(), nodes: 2 })
    ElMessage.success('已创建，进入可视化编排')
  } else {
    const created = await createDefinition(value)
    newId = created.id
    rows.value.unshift({ id: newId, name: value, cron: '-', nodes: 0, owner: '-', status: 'offline', version: 0, updatedAt: localTime() })
    ElMessage.success('已创建（后端落库），进入可视化编排')
  }
  open(newId)
}

async function onDelete(r: Row) {
  if (isMock) { ElMessage.info('mock 模式保留演示数据，不支持删除'); return }
  try {
    await ElMessageBox.confirm(`删除工作流「${r.name}」？其版本历史将一并删除。`, '删除工作流', {
      confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning',
    })
  } catch { return }
  try {
    await deleteDefinition(r.id)
    rows.value = rows.value.filter((x) => x.id !== r.id)
    ElMessage.success(`工作流「${r.name}」已删除`)
  } catch (e) {
    ElMessage.error('删除失败：' + errMsg(e))
  }
}

function design(r: Row) {
  open(r.id)
}

/* ---------- I3 定时调度（real 模式；mock 提示后端能力） ---------- */
const scheduleVisible = ref(false)
const scheduleWf = ref('')
const scheduleWfName = ref('')
function openSchedule(r: Row) {
  if (isMock) { ElMessage.info('定时调度为 real 后端能力（I3），mock 模式仅示意'); return }
  scheduleWf.value = r.id
  scheduleWfName.value = r.name
  scheduleVisible.value = true
}

/* 运行实例：I3 起跳转真实实例视图（F56d：mock 演示页 /dag/runs 已删除，引擎实时数据不提供 mock 演示） */
function openRuns() {
  if (isMock) { ElMessage.info('运行实例为引擎实时数据，mock 演示模式不提供'); return }
  router.push('/dag/instances')
}

function open(id: string) {
  if (props.embed) {
    emit('open', id)
  } else {
    router.push(`/dag/design/${id}`)
  }
}
</script>

<template>
  <div class="page">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">工作流定义</span>
        <span class="pill info">dag profile</span>
        <span class="spacer" />
        <button class="tb-new" @click="onCreate">+ 新建工作流</button>
      </div>
      <table class="tbl">
        <thead>
          <tr><th>工作流</th><th>调度周期</th><th>节点数</th><th>负责人</th><th>状态</th><th>版本</th><th>更新时间</th><th style="width:200px">操作</th></tr>
        </thead>
        <tbody>
          <tr v-if="loading"><td colspan="8" style="text-align:center;color:var(--text-3);padding:18px">加载中…</td></tr>
          <tr v-for="r in rows" :key="r.id">
            <td style="font-weight:600">{{ r.name }}</td>
            <td class="mono" style="font-size:11.5px">{{ r.cron }}</td>
            <td>{{ r.nodes }}</td>
            <td>{{ r.owner }}</td>
            <td><span class="pill" :class="r.status === 'online' ? 'ok' : 'off'">{{ r.status === 'online' ? '已上线' : '已下线' }}</span></td>
            <td class="mono">v{{ r.version }}</td>
            <td style="color:var(--text-3)">{{ r.updatedAt.slice(0, 16).replace('T', ' ') }}</td>
            <td>
              <button class="op-btn primary" @click="design(r)">可视化编排</button>
              <button class="op-btn" @click="openRuns">运行实例</button>
              <button v-if="!isMock" class="op-btn" @click="openSchedule(r)">定时</button>
              <button v-if="!isMock" class="op-btn" @click="onDelete(r)">删除</button>
            </td>
          </tr>
          <tr v-if="!loading && rows.length === 0"><td colspan="8" style="text-align:center;color:var(--text-3);padding:18px">暂无工作流，点击「+ 新建工作流」创建</td></tr>
        </tbody>
      </table>
      <div style="margin-top:10px;font-size:11px;color:var(--text-3)">
        「运行实例 / 告警 SLA」等任务流视角已整合至任务中心顶部页签；依赖配置在工作流编排的「依赖」页签。
      </div>
    </div>
    <!-- I3 定时调度对话框（F46：crontab 编辑 + 预览 + 上线/下线 + 重试参数） -->
    <ScheduleDialog v-model="scheduleVisible" :wf="scheduleWf" :wf-name="scheduleWfName" />
  </div>
</template>

<style scoped>
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.tbl tbody tr{transition:background var(--dur-fast) var(--ease)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2);transition:all var(--dur-fast) var(--ease)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary);background:var(--primary-light)}
</style>
