<script setup lang="ts">
/**
 * M07 质量报告（/qc/report）—— 三级报告体系之「总体报告（系统级）」
 * 原型对齐：prototype/assets/pages/m07-quality.js L305-349（#/qc/report + A.qrGen/qrepView/qrepExport）
 * 报告表格（类型筛选/搜索，含专项/细项报告）+ 顶部工具栏「+ 生成报告」；
 * 行操作：查看（评分/六维得分条/时间线弹窗）、导出（txt 下载）。
 * 交叉入口：专项报告（/qc/report-dag）、细项报告（/qc/report-table）、评分总览（/qc/score）。
 * 数据：qcReports（读写）/ qcDimScore / qcExceptions。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { dataStore, ST } from '../../services/mock/dataStore'
import ListFilterPanel from '../../components/ListFilterPanel.vue'
import type { Facet } from '../../components/ListFilterPanel.vue'
import type { QcReport, QcDimScore, QcException } from '../../services/types'

const router = useRouter()

const rows = ref<QcReport[]>([])
const dimScores = ref<QcDimScore[]>([])
const exceptions = ref<QcException[]>([])
const keyword = ref('')
const filters = ref<Record<string, string>>({ type: '', period: '' })

const facets = computed<Facet[]>(() => {
  const periods = [...new Set(rows.value.map((r) => r.period).filter(Boolean))]
  return [
    { key: 'type', label: '报告类型', options: [{ v: '日报', t: '日报' }, { v: '周报', t: '周报' }, { v: '月报', t: '月报' }, { v: '专项', t: '专项报告（DAG）' }, { v: '细项', t: '细项报告（表级）' }] },
    { key: 'period', label: '统计周期', options: periods.map((p) => ({ v: p, t: p })) },
  ]
})

onMounted(async () => {
  await reload()
  dimScores.value = [...((await dataStore.list<QcDimScore>('qcDimScore')) ?? [])]
  exceptions.value = [...((await dataStore.list<QcException>('qcExceptions')) ?? [])]
})

async function reload() {
  // 必须展开为新数组：dataStore.save 原地修改数组，直接赋值不会触发响应式更新。
  rows.value = [...((await dataStore.list<QcReport>('qcReports')) ?? [])]
}

const filtered = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return rows.value.filter((r) => {
    if (filters.value.type && r.type !== filters.value.type) return false
    if (filters.value.period && r.period !== filters.value.period) return false
    if (!kw) return true
    return [r.id, r.name].some((s) => s.toLowerCase().includes(kw))
  })
})

/* ---- 状态徽标 / 样式辅助 ---- */
function stCls(s: string): string {
  return ST[s]?.cls ?? 'st-gray'
}
function stLabel(s: string): string {
  return ST[s]?.label ?? s
}
function typeCls(t: string): string {
  return t === '日报' ? 'info' : t === '周报' ? 'purple' : t === '专项' ? 'warn' : t === '细项' ? 'info' : 'ok'
}
function scoreColor(score: number): string {
  return score >= 95 ? 'var(--success)' : score >= 90 ? 'var(--warn)' : 'var(--danger)'
}

function today(): string {
  const d = new Date()
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

/* ---- 生成报告 ---- */
async function genReport() {
  try {
    await ElMessageBox.confirm(
      '基于最近检查结果生成新的质量日报？将汇总今日检查任务结果、异常单闭环情况与评分。',
      '生成质量报告',
      { confirmButtonText: '生成', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  const pending = exceptions.value.filter((e) => e.status === 'pending').length
  const id = `QR-${today().replace(/-/g, '')}-X`
  const report: QcReport = {
    id, name: `数据质量日报 ${today()}`, type: '日报', period: today(),
    score: 95 - pending, problems: pending + 2, fixed: 1, status: 'published',
  }
  await dataStore.save('qcReports', report)
  ElMessage.success(`报告已生成：${id}`)
  await reload()
}

/* ---- 查看报告 ---- */
const viewVisible = ref(false)
const viewTarget = ref<QcReport | null>(null)

function openView(r: QcReport) {
  viewTarget.value = r
  viewVisible.value = true
}

/* ---- 导出报告（txt 下载） ---- */
function exportReport(r: QcReport) {
  const lines = [
    'Datara 质量报告',
    r.name,
    `评分：${r.score}`,
    `问题：${r.problems} / 已修复：${r.fixed}`,
    `六维得分：${dimScores.value.map((d) => `${d.name}=${d.score}`).join('， ')}`,
  ]
  const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${r.name}.txt`
  a.click()
  window.setTimeout(() => URL.revokeObjectURL(url), 0)
  ElMessage.success(`报告已导出：${r.name}.txt`)
}
</script>

<template>
  <div class="page" style="display:flex;gap:14px;align-items:flex-start">
    <ListFilterPanel
      v-model:keyword="keyword"
      v-model:filters="filters"
      :facets="facets"
      placeholder="搜索报告"
      :result-count="filtered.length"
      :total-count="rows.length"
    />
    <div style="flex:1;min-width:0">
    <!-- 页头 + 顶部工具栏按钮 -->
    <div class="card page-head">
      <div>
        <div class="ph-title">质量报告（总体 · 系统级）</div>
        <div class="ph-desc">三级报告体系：总体（本页，系统级汇总）/ 专项（DAG工作流级）/ 细项（表级）；日报/周报/月报自动生成，支持导出归档</div>
      </div>
      <div class="ph-acts">
        <button class="tb-new" @click="genReport">+ 生成报告</button>
        <button class="op-btn" @click="router.push('/qc/report-dag')">专项报告</button>
        <button class="op-btn" @click="router.push('/qc/report-table')">细项报告</button>
        <button class="op-btn" @click="router.push('/qc/score')">评分总览</button>
      </div>
    </div>

    <!-- 报告列表 -->
    <div class="card panel">
      <div class="tbl-toolbar">
        <span class="sec-head">报告列表</span>
        <span class="pill info">{{ filtered.length }} / {{ rows.length }}</span>
        <span class="spacer" />
      </div>

      <table class="tbl">
        <thead>
          <tr>
            <th>报告</th><th>类型</th><th>周期</th><th>评分</th><th>问题数</th><th>已修复</th><th>状态</th>
            <th style="width:120px">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in filtered" :key="r.id">
            <td><a @click="openView(r)"><b>{{ r.name }}</b></a></td>
            <td><span class="pill" :class="typeCls(r.type)">{{ r.type }}</span></td>
            <td style="color:var(--text-2)">{{ r.period }}</td>
            <td><b :style="{ color: scoreColor(r.score) }">{{ r.score }}</b></td>
            <td>{{ r.problems }}</td>
            <td>{{ r.fixed }}</td>
            <td><span class="st" :class="stCls(r.status)"><span class="dot" />{{ stLabel(r.status) }}</span></td>
            <td>
              <button class="op-btn primary" @click="openView(r)">查看</button>
              <button class="op-btn" @click="exportReport(r)">导出</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="filtered.length === 0" class="empty">未找到匹配的质量报告</div>
    </div>

    <!-- 查看报告弹窗 -->
    <el-dialog v-model="viewVisible" :title="viewTarget ? `质量报告 - ${viewTarget.name}` : ''" width="640px">
      <template v-if="viewTarget">
        <div class="desc-grid">
          <div class="d-row"><span class="d-k">报告编号</span><span class="mono">{{ viewTarget.id }}</span></div>
          <div class="d-row"><span class="d-k">类型</span><span><span class="pill" :class="typeCls(viewTarget.type)">{{ viewTarget.type }}</span></span></div>
          <div class="d-row"><span class="d-k">统计周期</span><span>{{ viewTarget.period }}</span></div>
          <div class="d-row"><span class="d-k">综合评分</span><span><b style="font-size:16px" :style="{ color: scoreColor(viewTarget.score) }">{{ viewTarget.score }}</b></span></div>
          <div class="d-row"><span class="d-k">发现问题</span><span>{{ viewTarget.problems }} 个</span></div>
          <div class="d-row"><span class="d-k">已修复闭环</span><span>{{ viewTarget.fixed }} 个</span></div>
        </div>

        <div class="sec-title">六维得分</div>
        <div class="bars">
          <div v-for="d in dimScores" :key="d.name" class="bar-row">
            <span class="bar-label">{{ d.name }}</span>
            <div class="bar-track"><div class="bar-fill" :style="{ width: d.score + '%', background: scoreColor(d.score) }" /></div>
            <span class="bar-val">{{ d.score }}</span>
          </div>
        </div>

        <div class="sec-title">报告时间线</div>
        <div class="tl">
          <div class="tl-item">
            <span class="tl-dot ok" />
            <div class="tl-body">
              <b>检查执行</b><span class="tl-time">{{ viewTarget.period }} 04:00</span>
              <div>3 个检查任务 / 7 条规则全部调度执行</div>
            </div>
          </div>
          <div class="tl-item">
            <span class="tl-dot err" />
            <div class="tl-body">
              <b>问题发现</b><span class="tl-time">{{ viewTarget.period }} 04:01</span>
              <div>QC-R-012 支付金额范围检查失败（12 行异常）等 {{ viewTarget.problems }} 个问题</div>
            </div>
          </div>
          <div class="tl-item">
            <span class="tl-dot warn" />
            <div class="tl-body">
              <b>异常核查</b><span class="tl-time">{{ viewTarget.period }} 09:00</span>
              <div>生成异常单并通知负责人，已修复 {{ viewTarget.fixed }} 个，待处理 {{ viewTarget.problems - viewTarget.fixed }} 个</div>
            </div>
          </div>
          <div class="tl-item">
            <span class="tl-dot ok" />
            <div class="tl-body">
              <b>报告归档</b><span class="tl-time">{{ viewTarget.period }} 09:10</span>
              <div>报告发布并推送订阅人</div>
            </div>
          </div>
        </div>
      </template>
      <template #footer>
        <button class="op-btn" @click="viewVisible = false">关闭</button>
        <button v-if="viewTarget" class="tb-new" @click="exportReport(viewTarget)">导出PDF</button>
      </template>
    </el-dialog>
    </div>
  </div>
</template>

<style scoped>
.page-head{display:flex;align-items:flex-start;gap:12px;padding:14px 16px;margin-bottom:14px}
.ph-title{font-weight:700;font-size:15px}
.ph-desc{font-size:12px;color:var(--text-2);margin-top:3px}
.ph-acts{margin-left:auto;display:flex;gap:8px;flex-shrink:0}
.panel{padding:14px 16px}
.tbl-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:12px;flex-wrap:wrap}
.tbl-toolbar .spacer{flex:1}
.pill{display:inline-flex;align-items:center;padding:1px 9px;border-radius:var(--radius-lg);font-size:11px;font-weight:500}
.pill.info{background:var(--info-bg);color:var(--info)}
.pill.purple{background:#f1eaff;color:var(--purple)}
.pill.ok{background:var(--success-bg);color:var(--success)}
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:left;padding:9px 10px;background:var(--bg);color:var(--text-2);font-weight:600;border-bottom:1px solid var(--border)}
.tbl td{padding:9px 10px;border-bottom:1px solid var(--border)}
.tbl tr:hover td{background:var(--primary-light)}
.kw{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 10px;font-size:12.5px;width:200px;outline:none}
.kw:focus{border-color:var(--primary)}
.sel{border:1px solid var(--border-strong);border-radius:var(--radius-sm);padding:6px 8px;font-size:12.5px;background:#fff;outline:none;color:var(--text-2)}
.tb-new{border:none;background:var(--primary);color:#fff;border-radius:var(--radius-sm);padding:7px 14px;font-size:12.5px;font-weight:500;cursor:pointer;transition:all var(--dur-base) var(--ease)}
.tb-new:hover{background:var(--primary-hover);box-shadow:var(--shadow-primary)}
.op-btn{border:1px solid var(--border-strong);background:#fff;border-radius:var(--radius-sm);padding:4px 9px;font-size:11.5px;cursor:pointer;margin-right:4px;color:var(--text-2)}
.op-btn.primary{color:var(--primary);border-color:rgba(22,104,220,.4);font-weight:600}
.op-btn:hover{border-color:var(--primary);color:var(--primary)}
.empty{padding:36px 16px;text-align:center;color:var(--text-3);font-size:12.5px}
.desc-grid{display:flex;flex-direction:column;margin-bottom:10px}
.d-row{display:flex;gap:12px;padding:6px 0;border-bottom:1px dashed var(--border);font-size:12.5px}
.d-k{width:88px;color:var(--text-3);flex-shrink:0}
.sec-title{font-weight:700;font-size:13px;margin:14px 0 8px;color:var(--text)}
.bars{display:flex;flex-direction:column;gap:8px}
.bar-row{display:flex;align-items:center;gap:10px}
.bar-label{width:52px;font-size:12px;color:var(--text-2);text-align:right;flex-shrink:0}
.bar-track{flex:1;height:10px;background:var(--bg);border-radius:var(--radius-sm);overflow:hidden}
.bar-fill{height:100%;border-radius:var(--radius-sm)}
.bar-val{width:30px;font-size:12px;font-weight:600}
.tl{display:flex;flex-direction:column}
.tl-item{display:flex;gap:10px;padding:7px 0}
.tl-dot{width:9px;height:9px;border-radius:50%;background:var(--border-strong);margin-top:6px;flex-shrink:0}
.tl-dot.ok{background:var(--success)}
.tl-dot.err{background:var(--danger)}
.tl-dot.warn{background:var(--warn)}
.tl-body{font-size:12.5px;color:var(--text-2);border-bottom:1px dashed var(--border);padding-bottom:7px;flex:1}
.tl-body b{color:var(--text)}
.tl-time{margin-left:8px;font-size:11px;color:var(--text-3)}
</style>
