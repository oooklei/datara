<script setup lang="ts">
/**
 * M10 标准审批（/std/approval）
 * 对齐 prototype/assets/pages/m10-standard.js L547-595：
 * 审批单列表（stdApprovals：单号/对象/发起人/提交时间/流程进度/状态）；
 * 顶部工具栏：搜索 + 状态筛选；行操作：评审通过 / 驳回（意见必填）/ 详情。
 */
import { ref, computed, onMounted } from 'vue'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import { useAuthStore } from '../../stores/auth'
import type { StdApproval, StdElement, StdCode } from '../../services/types'

const auth = useAuthStore()

const rows = ref<StdApproval[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ status: '' })
const statusOptions = [
  { v: 'review', t: '评审中' },
  { v: 'published', t: '已发布' },
  { v: 'reject', t: '已驳回' },
]

/* ---- 左侧筛选面板 facets ---- */
const facets = computed<Facet[]>(() => [
  { key: 'status', label: '状态', options: statusOptions },
])

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.status && r.status !== filters.value.status) return false
    if (!kw) return true
    return [r.id, r.target, r.proposer].some((s) => s.toLowerCase().includes(kw))
  })
})

async function reload() {
  // 展开为新数组触发响应式更新（save 原地修改数组，list 返回同一引用）
  rows.value = [...((await dataStore.list<StdApproval>('stdApprovals')) ?? [])]
}

onMounted(reload)

/* ---- ST 徽标 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}

/* ---- 流程节点样式 ---- */
function flowCls(a: StdApproval, i: number): string {
  if (i < a.current) return 'done'
  if (i === a.current) return 'cur'
  return 'todo'
}

/* ---- 评审通过 ---- */
async function approve(a: StdApproval) {
  try {
    await ElMessageBox.confirm(`确认通过「${a.target}」的评审？通过后进入发布环节。`, '评审通过', {
      confirmButtonText: '通过', cancelButtonText: '取消', type: 'info',
    })
  } catch {
    return
  }
  a.current = a.flow.length
  a.status = 'published'
  a.opinion = '评审通过，已发布执行'
  await dataStore.save('stdApprovals', a)
  // best-effort 同步：从 target 首个空格前取对象编号，联动发布数据元 / 代码标准
  try {
    const objId = a.target.split(' ')[0]?.trim()
    if (objId) {
      const el = (await dataStore.list<StdElement>('stdElements')).find((r) => r.id === objId)
      if (el) {
        el.status = 'published'
        await dataStore.save('stdElements', el)
      } else {
        const code = (await dataStore.list<StdCode>('stdCodes')).find((r) => r.id === objId)
        if (code) {
          code.status = 'published'
          await dataStore.save('stdCodes', code)
        }
      }
    }
  } catch {
    /* 未找到对应对象则静默跳过 */
  }
  ElMessage.success(`「${a.target}」已发布`)
}

/* ---- 驳回 ---- */
const rejectVisible = ref(false)
const rejectTarget = ref<StdApproval | null>(null)
const rejectOpinion = ref('')

function openReject(a: StdApproval) {
  rejectTarget.value = a
  rejectOpinion.value = ''
  rejectVisible.value = true
}

async function saveReject() {
  const a = rejectTarget.value
  if (!a) return
  const opinion = rejectOpinion.value.trim()
  if (!opinion) {
    ElMessage.warning('请填写驳回意见')
    return
  }
  a.status = 'reject'
  a.opinion = opinion
  await dataStore.save('stdApprovals', a)
  rejectVisible.value = false
  ElMessage.info('已驳回并通知发起人')
}

/* ---- 详情 ---- */
const detailVisible = ref(false)
const detailRow = ref<StdApproval | null>(null)

function openDetail(a: StdApproval) {
  detailRow.value = a
  detailVisible.value = true
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索单号/对象/发起人"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <div class="card" style="padding:16px">
      <div class="tbl-toolbar">
        <span class="sec-head">标准审批</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>审批单</th><th>变更对象</th><th>发起人</th><th>提交时间</th>
            <th>流程进度</th><th>状态</th><th style="width:200px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in filtered" :key="a.id">
            <td>
              <b class="mono">{{ a.id }}</b>
              <div style="font-size:11px;color:var(--text-3)">{{ a.type }}</div>
            </td>
            <td>{{ a.target }}</td>
            <td>{{ a.proposer }}</td>
            <td style="color:var(--text-2)">{{ a.submitAt }}</td>
            <td>
              <div class="flow">
                <template v-for="(f, i) in a.flow" :key="f">
                  <span class="fp" :class="flowCls(a, i)">{{ f }}</span>
                  <span v-if="i < a.flow.length - 1" class="arr">→</span>
                </template>
              </div>
            </td>
            <td>
              <span class="st" :class="stCls(a.status)"><span class="dot" />{{ stLabel(a.status) }}</span>
            </td>
            <td>
              <template v-if="a.status === 'review'">
                <button v-if="auth.can('approve:std')" class="op-btn primary" @click="approve(a)">评审通过</button>
                <button v-if="auth.can('approve:std')" class="op-btn danger" @click="openReject(a)">驳回</button>
                <span v-if="!auth.can('approve:std')" style="font-size:11px;color:var(--text-3)">只读</span>
              </template>
              <button class="op-btn" @click="openDetail(a)">详情</button>
            </td>
          </tr>
        </tbody>
      </table>

      <div v-if="filtered.length === 0" class="empty">未找到匹配的审批单，请调整筛选条件</div>
    </div>

    <!-- 驳回抽屉 -->
    <el-drawer v-model="rejectVisible" :title="rejectTarget ? '驳回 - ' + rejectTarget.target : ''" size="380px">
      <div class="form-grid">
        <label class="f-item">驳回意见（必填）
          <textarea v-model="rejectOpinion" rows="4" style="resize:vertical" placeholder="说明驳回原因" />
        </label>
      </div>
      <div style="margin-top:16px;display:flex;gap:8px">
        <button class="op-btn danger" @click="saveReject">确认驳回</button>
        <button class="op-btn" @click="rejectVisible = false">取消</button>
      </div>
    </el-drawer>

    <!-- 详情弹窗 -->
    <el-dialog v-model="detailVisible" :title="detailRow ? '审批详情 - ' + detailRow.id : ''" width="520px">
      <template v-if="detailRow">
        <div class="desc-grid">
          <span class="k">类型</span><span>{{ detailRow.type }}</span>
          <span class="k">对象</span><span>{{ detailRow.target }}</span>
          <span class="k">发起人</span><span>{{ detailRow.proposer }}</span>
          <span class="k">提交时间</span><span>{{ detailRow.submitAt }}</span>
          <span class="k">状态</span>
          <span>
            <span class="st" :class="stCls(detailRow.status)"><span class="dot" />{{ stLabel(detailRow.status) }}</span>
          </span>
          <span class="k">意见</span><span>{{ detailRow.opinion || '（无）' }}</span>
        </div>
        <div class="sec-title">流程进度</div>
        <div class="tl">
          <div
            v-for="(f, i) in detailRow.flow"
            :key="f"
            class="tl-item"
            :class="i < detailRow.current ? 'done' : i === detailRow.current ? 'cur' : ''"
          >
            <span class="tl-dot" />
            <div>
              <b style="font-size:12.5px">{{ f }}</b>
              <div style="font-size:11px;color:var(--text-3)">
                <template v-if="i < detailRow.current">已完成</template>
                <template v-else-if="i === 1">评审要点：类型/长度/格式约束合理性、下游影响面</template>
                <template v-else-if="i === 2">发布后自动通知映射方整改复检</template>
              </div>
            </div>
          </div>
        </div>
      </template>
      <template #footer>
        <button class="op-btn" @click="detailVisible = false">关闭</button>
      </template>
    </el-dialog>
    </div>
  </div>
</template>

<style scoped>
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn.danger{color:var(--danger);border-color:rgba(229,72,77,.35)}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.flow{display:flex;gap:4px;align-items:center;flex-wrap:wrap}
.flow .fp{padding:1px 8px;border-radius:9px;font-size:10.5px}
.flow .done{background:var(--success-bg);color:var(--success)}
.flow .cur{background:var(--info-bg);color:var(--info)}
.flow .todo{background:#eef1f6;color:var(--text-3)}
.flow .arr{color:var(--text-3);font-size:10px}
.desc-grid{display:grid;grid-template-columns:96px 1fr;gap:7px 10px;font-size:12.5px}
.desc-grid .k{color:var(--text-3)}
.sec-title{font-weight:700;font-size:13px;margin:16px 0 8px;color:var(--text)}
.tl{display:flex;flex-direction:column;gap:12px}
.tl-item{display:flex;gap:10px}
.tl-dot{width:8px;height:8px;border-radius:50%;background:#c9cfdd;margin-top:5px;flex-shrink:0}
.tl-item.done .tl-dot{background:var(--success)}
.tl-item.cur .tl-dot{background:var(--warn)}
.form-grid{display:flex;flex-direction:column;gap:12px}
.f-item{display:flex;flex-direction:column;gap:5px;font-size:12.5px;color:var(--text-2)}
.f-item textarea{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;outline:none;font-family:inherit}
.f-item textarea:focus{border-color:var(--primary)}
</style>
