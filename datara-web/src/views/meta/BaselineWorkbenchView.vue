<script setup lang="ts">
/**
 * M-B0 组件基线化工作台（三区布局：左清单看板 / 中设计区 / 右证据区）。
 *
 * 左「清单看板」：拉 progress()，按优先级分组（同步类 → ETL/计算类 → 流处理类 →
 * 逻辑控制类），组内 type+code+label+状态徽标（未开始/设计中/待实测/待认可/已发 v1），
 * 顶部进度条 = published 数 / 总数。
 * 中「设计区」：选中 type 后拉 getDraft → normalizeBaselineSpec → EightSectionEditor
 * 编辑；信息条（label/type/executionModel/executor/status）+「与旧声明 diff」折叠块
 * （从目录详情取旧 formFields，diffSummary 展示迁移/待定）+「保存底稿」按钮
 * （乐观锁：409 冲突提示并重拉 currentRev 合并）。
 * 右「证据区」：10 项体检报告（只报告不拦截）、血缘声明检查块（lineage.assets 数量
 * 与执行类必填提示）、实测记录（后端 testRecords 只读渲染 + 本地草稿随底稿保存——
 * 后端契约暂无独立写入端点，暂存 spec.meta.testDrafts，见 baselineSpec.ts 注释）、
 * 「申请认可」说明块 +「认可发 vN」按钮（ElMessageBox 二次确认 → publishBaseline）。
 *
 * 修订轮次：published 态底稿锁定（R3 409），保存栏切「复制 vN 开修订」入口
 * （redraftBaseline）；修订中（designing + publishedVersion>0）可保存/「放弃修订」
 * （discardBaselineRevision），认可发下一版（上一版留档，registry 供给切换至新版）。
 *
 * 页面挂载拉一次 progress，保存/发布后刷新。
 */
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  progress, getDraft, saveDraft, runCheck, publishBaseline, lineageDecl,
  redraftBaseline, discardBaselineRevision,
  type BaselineCheckItem, type BaselineDraft, type BaselineProgressRow,
  type BaselineStatus, type BaselineTestRecord, type LineageDeclResult,
} from '../../services/baselineApi'
import { getComponent } from '../../services/componentApi'
import { normalizeBaselineSpec, diffSummary, type BaselineSpec } from '../../services/baselineSpec'
import EightSectionEditor from '../../components/baseline/EightSectionEditor.vue'

/* 组件治理三页整合（ComponentHub 宿主）：openDesigner 回调优先（页签流转），
 * 缺省回退独立路由深链（/meta/components/page-designer/:type）。 */
const props = defineProps<{ openDesigner?: (type: string) => void }>()

/* ---------------- 清单看板（progress 分组） ---------------- */

const progressRows = ref<BaselineProgressRow[]>([])
const progressTotal = ref(0)
const loadingList = ref(false)
const listErr = ref('')

/** 状态徽标（中文 ↔ BaselineStatus，样式色分五档；已发版动态带版本号——pubV 不可得兜底「已发版」） */
const STATUS_META: Record<BaselineStatus, { t: string; cls: string }> = {
  pending: { t: '未开始', cls: 'st-pending' },
  designing: { t: '设计中', cls: 'st-designing' },
  testing: { t: '待实测', cls: 'st-testing' },
  confirming: { t: '待认可', cls: 'st-confirming' },
  published: { t: '已发版', cls: 'st-published' },
}
function statusText(s: string, pubV = 0): string {
  if (s === 'published') return pubV > 0 ? `已发 v${pubV}` : '已发版'
  return STATUS_META[s as BaselineStatus]?.t ?? s
}

/** 清单分组（优先级：sync > etl|worker > stream > 其余 general；组内保持返回顺序） */
const GROUPS = [
  { key: 'sync', t: '同步类' },
  { key: 'etl', t: 'ETL / 计算类' },
  { key: 'stream', t: '流处理类' },
  { key: 'general', t: '逻辑控制类' },
] as const
function groupOf(r: BaselineProgressRow): string {
  const cats = r.categories ?? []
  if (cats.includes('sync')) return 'sync'
  if (cats.includes('etl') || String(r.executionModel ?? '').toLowerCase().includes('worker')) return 'etl'
  if (cats.includes('stream')) return 'stream'
  return 'general'
}
const grouped = computed(() =>
  GROUPS.map((g) => ({ ...g, items: progressRows.value.filter((r) => groupOf(r) === g.key) })))

const publishedCount = computed(() => progressRows.value.filter((r) => r.status === 'published').length)
const progressPct = computed(() =>
  progressTotal.value > 0 ? Math.round((publishedCount.value / progressTotal.value) * 100) : 0)

async function refreshProgress(): Promise<void> {
  loadingList.value = true
  listErr.value = ''
  try {
    const r = await progress()
    progressRows.value = r.items ?? []
    progressTotal.value = r.stats?.total ?? progressRows.value.length
  } catch (e) {
    listErr.value = e instanceof Error ? e.message : String(e)
  } finally {
    loadingList.value = false
  }
}

/* ---------------- 设计区（底稿 + 八段编辑器 + diff） ---------------- */

const route = useRoute()
const router = useRouter()
const selectedType = ref('')
const draft = ref<BaselineDraft | null>(null)
const spec = ref<BaselineSpec>(normalizeBaselineSpec({}))
const loadingDraft = ref(false)
const saving = ref(false)
const oldFormFields = ref<unknown[] | null>(null)

const curRow = computed(() => progressRows.value.find((r) => r.type === selectedType.value))
const diff = computed(() =>
  oldFormFields.value ? diffSummary(oldFormFields.value, spec.value) : null)

/** 已发版本号（0=未发）；修订中 = designing + publishedVersion>0 */
const publishedVersion = computed(() => curRow.value?.publishedVersion ?? 0)
const isRevising = computed(() => draft.value?.status === 'designing' && publishedVersion.value > 0)

async function loadOldDetail(t: string): Promise<void> {
  try {
    const d = await getComponent(t)
    oldFormFields.value = d?.formFields ?? []
  } catch {
    // 目录详情缺该 type / 接口异常 → diff 静默降级为不可得
    oldFormFields.value = null
  }
}

async function loadDraft(t: string): Promise<void> {
  loadingDraft.value = true
  try {
    const d = await getDraft(t)
    draft.value = d
    spec.value = normalizeBaselineSpec(d.spec)
    // 实测草稿回填（暂存 spec.meta.testDrafts 随底稿保存，见 baselineSpec.ts 注释）
    testDrafts.value = ((spec.value.meta?.testDrafts ?? []) as BaselineTestRecord[]).map((x: BaselineTestRecord) => ({ ...x }))
    void loadOldDetail(t)
    void loadLineage(t)
  } catch (e) {
    draft.value = null
    ElMessage.error(e instanceof Error ? `底稿加载失败：${e.message}` : '底稿加载失败')
  } finally {
    loadingDraft.value = false
  }
}

async function select(t: string): Promise<void> {
  selectedType.value = t
  checkItems.value = null
  await loadDraft(t)
}

/** 保存底稿（乐观锁：409 冲突提示并重拉最新底稿；422 纯数据违规透出违规数） */
async function onSave(): Promise<void> {
  const d = draft.value
  if (!d || saving.value) return
  saving.value = true
  try {
    // 实测草稿随底稿保存（后端契约暂无独立端点 → 合入 spec.meta.testDrafts）
    const meta = { ...(spec.value.meta ?? {}), testDrafts: testDrafts.value }
    spec.value = { ...spec.value, meta }
    const r = await saveDraft(d.type, { draftRev: d.draftRev, spec: spec.value })
    d.draftRev = r.draftRev
    d.specHash = r.specHash
    d.status = r.status
    ElMessage.success(`底稿已保存（rev ${r.draftRev}）`)
    void refreshProgress()
  } catch (e) {
    const err = e as Error & { code?: number; data?: unknown }
    if (err.code === 409) {
      // 乐观锁冲突：data.currentRev 为服务器最新版本 → 重拉底稿合并
      ElMessage.warning('底稿已被他人修改（rev 冲突），已重新加载最新底稿，请合并后重试')
      await loadDraft(d.type)
    } else if (err.code === 422) {
      const vs = (err.data as { violations?: { msg: string }[] } | null)?.violations ?? []
      ElMessage.error(`底稿纯数据违规（${vs.length} 项）：${vs[0]?.msg ?? err.message}`)
    } else {
      ElMessage.error(err.message)
    }
  } finally {
    saving.value = false
  }
}

/** 复制最新已发版 spec 开修订轮（published→designing；修订期间 registry 供给已发版不变） */
const redrafting = ref(false)

async function onRedraft(): Promise<void> {
  const t = selectedType.value
  if (!t || redrafting.value) return
  try {
    await ElMessageBox.confirm(
      `复制已发 v${publishedVersion.value} 底稿开修订轮：底稿转为可编辑，registry 继续供给 v${publishedVersion.value}。确认开修订？`,
      '开修订轮',
      { type: 'info', confirmButtonText: `复制 v${publishedVersion.value} 开修订`, cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  redrafting.value = true
  try {
    const r = await redraftBaseline(t)
    ElMessage.success(`已复制 v${r.fromVersion} 开修订（rev=${r.draftRev}）`)
    await loadDraft(t)
    await refreshProgress()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    redrafting.value = false
  }
}

/** 放弃修订：底稿重置回最新已发版（修订改动丢弃，status 回 published） */
const discarding = ref(false)

async function onDiscard(): Promise<void> {
  const t = selectedType.value
  if (!t || discarding.value) return
  try {
    await ElMessageBox.confirm(
      '放弃修订：底稿将重置为最新已发版内容（修订改动丢弃）。确认放弃？',
      '放弃修订',
      { type: 'warning', confirmButtonText: '放弃修订', cancelButtonText: '继续编辑' },
    )
  } catch {
    return // 用户取消
  }
  discarding.value = true
  try {
    await discardBaselineRevision(t)
    ElMessage.success('已放弃修订，底稿回到已发版')
    await loadDraft(t)
    await refreshProgress()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    discarding.value = false
  }
}

/* ---------------- 证据区：体检 / 血缘 / 实测 / 认可 ---------------- */

const checking = ref(false)
const checkItems = ref<BaselineCheckItem[] | null>(null)
const checkedAt = ref('')

/** 10 项体检 key → 中文名（与后端 run_baseline_checks 一一对应） */
const CHECK_LABELS: Record<string, string> = {
  pure_data: '纯数据',
  form_whitelist: '表单白名单',
  drop_policy: '拖入策略',
  contract: '执行契约',
  catalog_consistency: '目录一致',
  references: '引用完整性',
  lineage_decl: '血缘声明',
  exports_consistency: '输出变量一致',
  permission: '权限',
  draft_lock: '底稿锁',
}
function checkLabel(k: string): string {
  return CHECK_LABELS[k] ?? k
}

async function onCheck(): Promise<void> {
  const t = selectedType.value
  if (!t || checking.value) return
  checking.value = true
  checkItems.value = null
  try {
    const r = await runCheck(t)
    checkItems.value = r.items ?? []
    checkedAt.value = r.checkedAt ?? ''
  } catch (e) {
    ElMessage.error(e instanceof Error ? `体检失败：${e.message}` : '体检失败')
  } finally {
    checking.value = false
  }
}

/* 血缘声明检查块 */

const lineageInfo = ref<LineageDeclResult | null>(null)
const assetCount = computed(() => spec.value.lineage.assets.length)
/** 执行类组件（executionModel 含 canvas 的画布元件除外）：血缘资产为空即提示必填 */
const execComp = computed(() => {
  const em = String(curRow.value?.executionModel ?? '').toLowerCase()
  return !!em && !em.includes('canvas')
})

async function loadLineage(t: string): Promise<void> {
  try {
    lineageInfo.value = await lineageDecl(t)
  } catch {
    lineageInfo.value = null // 静默降级：血缘端点异常不影响编辑主链路
  }
}

/* 实测记录（后端 testRecords 只读 + 本地草稿随底稿保存） */

const testDrafts = ref<BaselineTestRecord[]>([])
const testForm = ref({ batch: '', dataflow: '', result: 'pass', note: '' })

function addTestDraft(): void {
  const f = testForm.value
  if (!f.batch.trim() || !f.dataflow.trim()) {
    ElMessage.warning('批次与数据流必填')
    return
  }
  testDrafts.value.push({
    batch: f.batch.trim(),
    dataflow: f.dataflow.trim(),
    result: f.result,
    ...(f.note.trim() ? { note: f.note.trim() } : {}),
  })
  testForm.value = { batch: '', dataflow: '', result: 'pass', note: '' }
}

/* 申请认可 → 认可发 vN（未发=发 v1；修订中=以当前底稿发下一版，上一版留档） */

const publishing = ref(false)

async function onPublish(): Promise<void> {
  const t = selectedType.value
  const d = draft.value
  if (!t || !d || publishing.value) return
  const nextV = publishedVersion.value + 1
  try {
    await ElMessageBox.confirm(
      isRevising.value
        ? `以当前底稿发布 v${nextV}，v${publishedVersion.value} 留档，registry 供给切换至新版。发布前请确认 10 项体检与实测记录就绪。确认发布？`
        : '认可发 v1 以服务器已保存底稿为准：发布即基线 v1 固化（目录页挂「已发 v1」徽标），声明不可变。发布前请确认 10 项体检与实测记录就绪。确认发布？',
      `认可发 v${nextV}`,
      { type: 'warning', confirmButtonText: `认可发 v${nextV}`, cancelButtonText: '取消' },
    )
  } catch {
    return // 用户取消
  }
  publishing.value = true
  const prevV = publishedVersion.value
  try {
    const r = await publishBaseline(t)
    ElMessage.success(isRevising.value
      ? `已发 v${r.publishedVersion}（v${prevV} 留档，registry 供给已切换）`
      : `已发 v${r.publishedVersion}（基线化完成）`)
    d.status = 'published'
    await loadDraft(t)
    await refreshProgress()
  } catch (e) {
    const err = e as Error & { code?: number }
    if (err.code === 409) ElMessage.warning('该组件已发版且未开修订轮（如需修改请先「复制上版开修订」）')
    else ElMessage.error(err.message)
  } finally {
    publishing.value = false
  }
}

/** 调用组件设计器（统一入口语义不变，三页整合下走页签流转） */
function openDesigner_(t: string): void {
  if (props.openDesigner) props.openDesigner(t)
  else void router.push(`/meta/components/page-designer/${t}`)
}

onMounted(async () => {
  await refreshProgress()
  // 组件目录「修改/查看」经 /meta/baseline?type=xxx 深链定位设计区（清单加载完成后再选中）
  const q = String(route.query.type ?? '')
  if (q && progressRows.value.some((r) => r.type === q)) await select(q)
})
</script>

<template>
  <div class="page">
    <header class="head">
      <h2>组件基线化工作台</h2>
      <p class="sub">
        M-B0：九系统组件八段 DSL 声明重建——底稿编辑 → 10 项体检 → 实测记录 → 认可发 v1
      </p>
    </header>

    <div class="layout">
      <!-- 左：清单看板 -->
      <aside class="board">
        <div class="bd-t">
          清单看板
          <span class="muted">{{ progressTotal ? `${publishedCount}/${progressTotal} 已发 v1` : '加载中…' }}</span>
        </div>
        <el-progress :percentage="progressPct" :stroke-width="8" class="bd-bar" />
        <div v-if="listErr" class="list-err">进度加载失败：{{ listErr }}</div>
        <div v-for="g in grouped" :key="g.key" class="grp">
          <div class="grp-t">{{ g.t }}（{{ g.items.length }}）</div>
          <div
            v-for="r in g.items" :key="r.type"
            class="crow" :class="{ on: selectedType === r.type }"
            @click="select(r.type)"
          >
            <span class="cnm">{{ r.label }}</span>
            <code class="cty">{{ r.type }}</code>
            <span class="badge" :class="STATUS_META[r.status as BaselineStatus]?.cls">{{ statusText(r.status, r.publishedVersion) }}</span>
          </div>
        </div>
      </aside>

      <!-- 中：设计区 -->
      <main class="center">
        <div v-if="!selectedType" class="empty">← 从清单选择组件开始基线化</div>
        <template v-else>
          <div class="info-bar">
            <span class="il">{{ curRow?.label ?? draft?.type }}</span>
            <code class="ity">{{ draft?.type }}</code>
            <span class="muted">
              {{ curRow?.executionModel ?? '—' }}<template v-if="curRow?.executor"> · {{ curRow.executor }}</template>
            </span>
            <span class="badge" :class="STATUS_META[draft?.status as BaselineStatus]?.cls">{{ statusText(draft?.status ?? '', publishedVersion) }}</span>
            <span v-if="isRevising" class="badge st-revising">修订中（当前供给 v{{ publishedVersion }}）</span>
            <span class="muted">rev {{ draft?.draftRev ?? 0 }}</span>
            <!-- 组件设计器统一入口（Task 15）：跳转组件页面设计器并深链当前组件 -->
            <el-button
              link type="primary" size="small" style="margin-left: auto"
              @click="openDesigner_(selectedType)"
            >组件设计器</el-button>
          </div>

          <!-- 与旧声明 diff（dag_catalog.formFields → 八段 DSL） -->
          <details class="diff-box" open>
            <summary>与旧声明 diff（dag_catalog.formFields → 八段 DSL）</summary>
            <div v-if="diff" class="diff-body">
              旧字段 <strong>{{ diff.oldCount }}</strong> → 新字段 <strong>{{ diff.newCount }}</strong>；
              已迁移 <strong class="okc">{{ diff.migrated.length }}</strong>
              <span class="muted">（{{ diff.migrated.join('、') || '—' }}）</span>；
              待语义分析 <strong class="warnc">{{ diff.pending.length }}</strong>
              <span class="muted">（{{ diff.pending.join('、') || '—' }}）</span>
              <p class="diff-note">待语义分析项不允许静默丢弃，须逐个人工裁决后落位八段。</p>
            </div>
            <span v-else class="muted">旧声明加载中或目录快照无此 type</span>
          </details>

          <!-- 八段低代码表单编辑器（纯受控）；published 态底稿锁定 → 只读（spec §5） -->
          <EightSectionEditor v-model:spec="spec" :readonly="draft?.status === 'published'" />

          <!-- 保存栏三态：published 底稿锁定（R3 409）→ 开修订入口；未发/修订中 → 可编辑保存 -->
          <div class="save-bar">
            <template v-if="draft?.status === 'published'">
              <el-button type="primary" :loading="redrafting" @click="onRedraft">复制 v{{ publishedVersion }} 开修订</el-button>
              <span class="muted">已发版底稿锁定（不可直接修改）：开修订后底稿转为可编辑，registry 继续供给当前已发版</span>
            </template>
            <template v-else>
              <el-button type="primary" :loading="saving" @click="onSave">保存底稿</el-button>
              <el-button v-if="isRevising" :loading="discarding" @click="onDiscard">放弃修订</el-button>
              <span class="muted">乐观锁保护：rev 冲突（409）时自动重拉最新底稿，请合并后重试</span>
            </template>
          </div>
        </template>
      </main>

      <!-- 右：证据区 -->
      <aside class="evidence">
        <div class="ev-t">证据区</div>

        <!-- 10 项体检（只报告不拦截） -->
        <section class="ev-sec">
          <div class="ev-st">
            10 项体检
            <el-button size="small" :loading="checking" :disabled="!selectedType" @click="onCheck">体检报告</el-button>
          </div>
          <p class="ev-note">体检只报告不拦截——结果作为「认可发 v1」的评审证据，不阻塞底稿保存。</p>
          <div v-if="checkItems" class="ck-list">
            <div class="ck-sum">
              共 {{ checkItems.length }} 项 · 通过 {{ checkItems.filter((x) => x.ok).length }}
              <template v-if="checkedAt"> · {{ checkedAt }}</template>
            </div>
            <div v-for="it in checkItems" :key="it.check" class="ck-row" :class="it.ok ? 'ok' : 'bad'">
              <span class="ic">{{ it.ok ? '✓' : '✕' }}</span>
              <span class="cn">{{ checkLabel(it.check) }}</span>
              <span class="ms">{{ it.msg }}</span>
            </div>
          </div>
        </section>

        <!-- 血缘声明检查块 -->
        <section class="ev-sec">
          <div class="ev-st">血缘声明</div>
          <div class="ln-row">
            血缘资产 <strong>{{ assetCount }}</strong> 项
            <span v-if="lineageInfo" class="badge" :class="lineageInfo.baselineState === 'published' ? 'st-published' : 'st-pending'">
              {{ lineageInfo.baselineState === 'published' ? '已基线' : '未基线' }}
            </span>
          </div>
          <p v-if="execComp && !assetCount" class="warn-line">
            执行类组件必须声明血缘资产（lineage.assets，source/target），体检 lineage_decl 项将不通过。
          </p>
          <p v-else class="ev-note">血缘声明随底稿保存（lineage.assets），发 v1 后供给血缘分析。</p>
        </section>

        <!-- 实测记录 -->
        <section class="ev-sec">
          <div class="ev-st">实测记录 <span class="muted">后端 {{ draft?.testRecords?.length ?? 0 }} 条</span></div>
          <div v-for="(t, i) in draft?.testRecords ?? []" :key="i" class="tr-row">
            <span class="tr-b">{{ t.batch }}</span> · {{ t.dataflow }} ·
            <span :class="t.result === 'pass' ? 'okc' : 'badc'">{{ t.result }}</span>
            <span v-if="t.note" class="muted">{{ t.note }}</span>
          </div>
          <div class="tr-form">
            <el-input v-model="testForm.batch" placeholder="批次（如 2026-09-28）" size="small" />
            <el-input v-model="testForm.dataflow" placeholder="数据流（如 上游ds→目标表）" size="small" />
            <select v-model="testForm.result" class="native">
              <option value="pass">pass</option>
              <option value="fail">fail</option>
              <option value="blocked">blocked</option>
            </select>
            <el-input v-model="testForm.note" placeholder="备注（可空）" size="small" />
            <el-button size="small" :disabled="!selectedType" @click="addTestDraft">＋ 添加</el-button>
          </div>
          <div v-if="testDrafts.length" class="tr-drafts">
            <div class="tr-dt">待保存（{{ testDrafts.length }}）——随「保存底稿」写入 spec.meta.testDrafts</div>
            <div v-for="(t, i) in testDrafts" :key="i" class="tr-row">
              {{ t.batch }} · {{ t.dataflow }} · {{ t.result }}
              <el-button link type="danger" size="small" @click="testDrafts.splice(i, 1)">✕</el-button>
            </div>
          </div>
        </section>

        <!-- 申请认可说明块 + 认可发 vN（published 未开修订时后端必 409 → 隐藏按钮） -->
        <section class="ev-sec">
          <div class="ev-st">申请认可</div>
          <p class="ev-note">
            流程：底稿保存 → 10 项体检 → 实测记录 → 申请认可（线下评审）→ 认可发版。
            发版后组件进入基线（目录页挂「已发」徽标），声明固化不可变；修改需开修订轮。
          </p>
          <el-button
            v-if="draft?.status !== 'published'"
            type="primary" :loading="publishing"
            :disabled="!selectedType"
            @click="onPublish"
          >
            认可发 v{{ publishedVersion + 1 }}
          </el-button>
          <span v-else class="pub-ok">已发 v{{ publishedVersion }}（published）· 如需修改请「复制 v{{ publishedVersion }} 开修订」</span>
        </section>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.page { padding: 16px 18px; }
.head h2 { margin: 0 0 4px; font-size: 18px; }
.sub { margin: 0 0 14px; font-size: 12px; color: #64748b; }

/* 三区布局：320 / 自适应 / 360 */
.layout { display: flex; gap: 14px; align-items: flex-start; }
.board { width: 320px; flex: none; }
.center { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; }
.evidence { width: 360px; flex: none; }

/* 左清单看板 */
.bd-t { font-weight: 600; font-size: 14px; margin-bottom: 6px; }
.bd-bar { margin-bottom: 10px; }
.list-err { font-size: 12px; color: #dc2626; margin-bottom: 8px; }
.grp { margin-bottom: 12px; }
.grp-t {
  font-size: 12px; font-weight: 600; color: #475569;
  border-bottom: 1px solid var(--line, #e2e8f0); padding-bottom: 4px; margin-bottom: 4px;
}
.crow {
  display: flex; align-items: center; gap: 6px; padding: 6px 8px;
  border-radius: 6px; cursor: pointer; font-size: 12px;
}
.crow:hover { background: #f1f5f9; }
.crow.on { background: #e2e8f0; }
.cnm { font-size: 13px; }
.cty { font-size: 11px; color: #64748b; }

/* 状态徽标（五档色） */
.badge { font-size: 10px; padding: 1px 6px; border-radius: 3px; white-space: nowrap; }
.st-pending { background: #f1f5f9; color: #94a3b8; }
.st-designing { background: #dbeafe; color: #1d4ed8; }
.st-testing { background: #fef3c7; color: #b45309; }
.st-confirming { background: #ede9fe; color: #6d28d9; }
.st-published { background: #dcfce7; color: #15803d; }
.st-revising { background: #ede9fe; color: #6d28d9; }

/* 中设计区 */
.empty { color: #94a3b8; font-size: 13px; padding: 40px 0; text-align: center; }
.info-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  border: 1px solid var(--line, #e2e8f0); border-radius: 8px; padding: 8px 12px; background: #fff;
}
.il { font-size: 15px; font-weight: 600; }
.ity { font-size: 12px; color: #64748b; }
.diff-box {
  border: 1px dashed var(--line, #cbd5e1); border-radius: 8px;
  padding: 8px 12px; background: #f8fafc; font-size: 12px;
}
.diff-box summary { cursor: pointer; font-weight: 600; color: #475569; user-select: none; }
.diff-body { margin-top: 6px; }
.diff-note { margin: 4px 0 0; color: #94a3b8; }
.save-bar { display: flex; align-items: center; gap: 10px; }
.pub-ok { font-size: 12px; color: #15803d; }

/* 右证据区 */
.ev-t { font-weight: 600; font-size: 14px; margin-bottom: 6px; }
.ev-sec {
  border: 1px solid var(--line, #e2e8f0); border-radius: 8px;
  padding: 10px 12px; margin-bottom: 12px; background: #fff;
  display: flex; flex-direction: column; gap: 6px;
}
.ev-st { font-weight: 600; font-size: 13px; display: flex; align-items: center; gap: 8px; }
.ev-note { font-size: 12px; color: #94a3b8; margin: 0; }
.warn-line { font-size: 12px; color: #b45309; margin: 0; }
.ck-list { display: flex; flex-direction: column; gap: 4px; }
.ck-sum { font-size: 12px; color: #475569; }
.ck-row { display: flex; align-items: baseline; gap: 6px; font-size: 12px; }
.ck-row .ic { width: 14px; text-align: center; }
.ck-row.ok .ic { color: #16a34a; }
.ck-row.bad .ic { color: #dc2626; }
.ck-row .cn { font-weight: 500; white-space: nowrap; }
.ck-row .ms { color: #64748b; min-width: 0; }
.ln-row { display: flex; align-items: center; gap: 8px; font-size: 12px; }
.tr-row { font-size: 12px; color: #334155; }
.tr-b { font-weight: 500; }
.tr-form { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.tr-form .native { height: 24px; border: 1px solid var(--line, #cbd5e1); border-radius: 4px; font-size: 12px; }
.tr-drafts { margin-top: 6px; }
.tr-dt { font-size: 12px; color: #b45309; margin-bottom: 4px; }
.okc { color: #15803d; }
.badc { color: #dc2626; }
.muted { font-size: 12px; color: #94a3b8; }
</style>
