<script setup lang="ts">
/**
 * M1 B4 组件设计器（治理设计 §12 表单设计器交互 / §18.2 五端点）。
 *
 * 布局：顶部工具条（保存/冻结/预览）+ 左侧版本列表（草稿/冻结，B5）+ 中部声明编辑
 * （Tab：基本信息/端口/表单字段/dropPolicy）+ 右侧实时预览（B3 F0 FieldRenderer
 * 吃声明数据——所见即所得，§12.3 覆盖验收自动成立）。
 *
 * 路由 /meta/components/design/:type?：:type 缺省 = 新建组件草稿（创建后 replace 进编辑态）。
 * 打字即校验：validateSpecPureData（componentSpec.ts，红线 2 前端镜像）违规行内红标，
 * 后端 422(6008) 为第二道兜底；showIf 初版 JSON 编辑 + 语法校验（运行时 DSL 判定属 M3 降级项）。
 * 身份字段（type/name/profile/executionModel…）创建后只读（主表，无更新端点）；
 * spec 级内容（icon/color/summary/ports/fields/dropPolicy）随草稿保存。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { TableInstance } from 'element-plus'
import {
  createComponentDraft, freezeComponentVersion, getComponent, getComponentDraft, getImpactedWorkflows,
  listComponentVersions, offlineComponent, publishComponentVersion,
  rollbackComponent, saveComponentDraft,
  type ComponentCreateBody, type ComponentDraft, type ComponentVersionRow, type ComponentVersionsResult,
  type GateItem, type ImpactedWorkflow, type PublishResult,
} from '../../services/componentApi'
import { graphService, offlineWorkflow, publishWorkflow } from '../../services'
import { normalizeSpec, SPEC_UI_TYPES, validateSpecPureData, type ComponentSpec, type SpecField, type SpecUiType } from '../../services/componentSpec'
import FieldRenderer from '../../graph/workbench/fields/FieldRenderer.vue'
import type { FieldCtx } from '../../graph/workbench/fields/fieldCtx'
import type { FieldKind, FieldSchema, NodeSchema } from '../../graph/profiles/types'
import type { GNode, GraphDocument } from '../../graph/model'
import type { DataContext } from '../../graph/profiles/formLinkage'

const route = useRoute()
const router = useRouter()

/* ================= 路由态与加载 ================= */
const typeParam = computed(() => {
  const t = route.params.type
  return typeof t === 'string' && t ? t : ''
})
const isCreate = computed(() => !typeParam.value)

const draft = ref<ComponentDraft | null>(null)
const versions = ref<ComponentVersionRow[]>([])
const spec = ref<ComponentSpec>(normalizeSpec({}))
const loading = ref(false)
const loadErr = ref('')
/** R2：409(6002) 且该 type 为内置组件 → 引导至基线化工作台（内置组件走基线化治理链，无 M1 草稿行） */
const builtinGuide = ref<{ type: string } | null>(null)
const saving = ref(false)
const freezing = ref(false)
const previewOn = ref(true)

const EMPTY_SCHEMA: NodeSchema = { type: 'stub', label: '桩', icon: '?', color: '#000', form: [] }
const EMPTY_DC: DataContext = { upstreamColumns: [], upstreamTables: [], vars: [], timeParams: [], downstreamNeeds: [] }

/** 预览用最小 FieldCtx 桩（设计器无画布上下文；声明只含 9 基元，动态候选通道不触达） */
function makePreviewCtx(): FieldCtx {
  return {
    upstream: computed(() => [] as GNode[]),
    upSchema: () => EMPTY_SCHEMA,
    upstreamOpts: computed(() => []),
    upstreamOuts: computed(() => []),
    epProbe: computed(() => null),
    dsRows: ref([]),
    scripts: ref([]),
    runtimeNodes: ref([]),
    tagOptions: computed(() => []),
    varOptions: ref([]),
    dataCtx: computed(() => EMPTY_DC),
    pickTrees: ref({}),
    pickTreeErr: ref({}),
    pickTreeBusy: ref({}),
    topicOpts: ref({}),
    topicErr: ref({}),
    topicBusy: ref({}),
    dirNavs: ref({}),
    ensureTree: async () => null,
    ensureTopics: async () => {},
    lsDir: () => {},
    loadScriptCode: () => {},
    saveToScript: () => {},
    saveAsNewScript: async () => {},
    markDirty: () => {},
    schema: computed(() => null),
  }
}
const previewCtx = makePreviewCtx()

/** showIf JSON 文本与语法错误（按字段 key 索引；空文本 = 恒显示） */
const showIfText = ref<Record<string, string>>({})
const showIfErr = ref<Record<string, string>>({})

async function loadDraft(t: string): Promise<void> {
  loading.value = true
  loadErr.value = ''
  try {
    builtinGuide.value = null
    const [d, v] = await Promise.all([getComponentDraft(t), listComponentVersions(t)])
    draft.value = d
    versions.value = (v as ComponentVersionsResult).items
    spec.value = normalizeSpec(d.spec)
    syncShowIfText()
    seedPreview()
  } catch (e) {
    const code = (e as { code?: number }).code
    loadErr.value = e instanceof Error ? e.message : String(e)
    draft.value = null
    versions.value = []
    if (code === 6002) {
      // R2：内置组件无 M1 草稿链，draft 必 409(6002)——改引导而非死路报错。
      // 判定依据：GET /components/{type} 详情仅服务内置目录快照（用户组件 404），详情能取到即内置。
      try {
        await getComponent(t)
        builtinGuide.value = { type: t }
      } catch { /* 详情失败则维持原报错展示 */ }
    }
  } finally {
    loading.value = false
  }
}

watch(() => route.params.type, (t) => {
  const s = typeof t === 'string' ? t : ''
  if (s) void loadDraft(s)
}, { immediate: true })

/* ================= 纯数据打字即校验（行内红标） ================= */
const violations = computed(() => validateSpecPureData(spec.value))

function pathMsgs(path: string): string[] {
  return violations.value.filter((v) => v.path === path).map((v) => v.msg)
}
/** 字段行违规：spec 扫描（fields[i].* 含 showIf 内容）+ showIf JSON 语法错误 */
function fieldMsgs(i: number): string[] {
  const tag = `fields[${i}]`
  const out = violations.value
    .filter((v) => v.path === tag || v.path.startsWith(`${tag}.`))
    .map((v) => v.msg)
  const key = spec.value.fields[i]?.key
  const si = key ? showIfErr.value[key] : ''
  return si ? [...out, si] : out
}
const autoNameMsgs = computed(() => pathMsgs('dropPolicy.autoName'))
const iconMsgs = computed(() => pathMsgs('icon'))
const colorMsgs = computed(() => pathMsgs('color'))
const summaryMsgs = computed(() => pathMsgs('summary'))

function onShowIfInput(f: SpecField, v: string | number | null | undefined): void {
  showIfText.value[f.key] = String(v ?? '')
  const txt = String(v ?? '').trim()
  if (!txt) {
    delete f.showIf
    delete showIfErr.value[f.key]
    return
  }
  try {
    const parsed: unknown = JSON.parse(txt)
    if (parsed === null || typeof parsed !== 'object' || Array.isArray(parsed)) {
      showIfErr.value[f.key] = 'showIf 须为 JSON 对象（声明式条件 DSL 位）'
      return
    }
    f.showIf = parsed
    delete showIfErr.value[f.key]
  } catch (e) {
    showIfErr.value[f.key] = `JSON 语法错误：${e instanceof Error ? e.message : String(e)}`
  }
}

function syncShowIfText(): void {
  const m: Record<string, string> = {}
  spec.value.fields.forEach((f) => {
    m[f.key] = f.showIf === undefined ? '' : JSON.stringify(f.showIf, null, 2)
  })
  showIfText.value = m
  showIfErr.value = {}
}

/* ================= 端口 / 字段 / 选项编辑 ================= */
function addPort(side: 'inputs' | 'outputs'): void {
  spec.value.ports[side].push({ name: '', type: 'dataset' })
}
function removePort(side: 'inputs' | 'outputs', i: number): void {
  spec.value.ports[side].splice(i, 1)
}

function addField(): void {
  spec.value.fields.push({ key: '', label: '', uiType: 'text', required: false, desc: '', options: [] })
}
function removeField(i: number): void {
  const f = spec.value.fields[i]
  if (f?.key) {
    delete showIfText.value[f.key]
    delete showIfErr.value[f.key]
  }
  spec.value.fields.splice(i, 1)
}
function addFieldOption(f: SpecField): void {
  ;(f.options ??= []).push({ label: '', value: '' })
}
/** 默认值编辑：非字符串存量值原样保留，编辑后才落字符串 */
function setFieldDefault(f: SpecField, v: string | number | null | undefined): void {
  f.default = v == null || v === '' ? undefined : v
}
function defaultText(v: unknown): string {
  return v === undefined || v === null ? '' : String(v)
}

/* ================= dropPolicy 复合绑定 ================= */
const prefillText = computed(() => spec.value.dropPolicy.prefillFromUpstream.join(','))
function onPrefillInput(v: string | number | null | undefined): void {
  spec.value.dropPolicy.prefillFromUpstream = String(v ?? '')
    .split(',').map((s) => s.trim()).filter(Boolean)
}
function onMaxInstancesInput(v: string | number | null | undefined): void {
  const n = Number(v)
  spec.value.dropPolicy.maxInstances = Number.isFinite(n) && n > 0 ? Math.floor(n) : 0
}
function setAutoConnect(side: 'upstream' | 'downstream', ev: Event): void {
  const v = (ev.target as HTMLSelectElement).value
  spec.value.dropPolicy.autoConnect[side] = v === 'none' ? 'none' : 'nearest'
}

/* ================= 实时预览（F0 FieldRenderer 吃声明数据） ================= */
const previewData = ref<Record<string, unknown>>({})
/** 依赖运行时上下文的控件预览略（画布期真实渲染），其余 6 基元所见即所得 */
const PREVIEWABLE = new Set<string>(['text', 'number', 'bool', 'select', 'expr', 'hint'])

interface PreviewItem { f: SpecField; key: string; schema: FieldSchema }
const previewFields = computed<PreviewItem[]>(() =>
  spec.value.fields
    .map((f, i) => ({ f, key: f.key || `__f${i}` }))
    .filter(({ f }) => PREVIEWABLE.has(f.uiType))
    .map(({ f, key }) => ({
      f,
      key,
      schema: {
        key,
        label: f.label || f.key,
        type: f.uiType as FieldKind,
        required: f.required,
        placeholder: f.desc || undefined,
        options: f.uiType === 'select'
          ? (f.options ?? []).map((o) => ({ label: o.label || String(o.value), value: String(o.value) }))
          : undefined,
      } as FieldSchema,
    })))

function seedPreview(): void {
  const d: Record<string, unknown> = {}
  spec.value.fields.forEach((f, i) => {
    const k = f.key || `__f${i}`
    if (f.uiType === 'bool') d[k] = f.default === true
    else if (f.uiType === 'number') {
      const n = Number(f.default)
      if (Number.isFinite(n)) d[k] = n
    } else d[k] = f.default ?? ''
  })
  previewData.value = d
}

/** 预览写值（number 转数值存储，与 fieldCtxFactory.upd 同契约） */
function onPreviewSet(f: FieldSchema, ev: Event): void {
  const t = ev.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
  if (t instanceof HTMLInputElement && t.type === 'number' && t.value !== '') {
    const n = Number(t.value)
    if (Number.isFinite(n)) {
      previewData.value[f.key] = n
      return
    }
  }
  previewData.value[f.key] = t.value
}

/* ================= 保存 / 冻结 / 新建 ================= */
async function onSave(): Promise<void> {
  const d = draft.value
  if (!d || saving.value) return
  saving.value = true
  try {
    const r = await saveComponentDraft(d.type, { draftRev: d.draftRev, spec: spec.value })
    d.draftRev = r.draftRev
    d.specHash = r.specHash
    ElMessage.success(`已保存（rev ${r.draftRev}）`)
  } catch (e) {
    const err = e as Error & { code?: number }
    if (err.code === 6007) {
      // COMP_LOCK_CONFLICT：http 层丢弃 data.currentRev → 重拉最新草稿，本地未保存改动不覆盖
      ElMessage.warning('草稿已被他人修改（rev 冲突），已重新加载最新草稿，请合并后重试')
      await loadDraft(d.type)
    } else {
      ElMessage.error(err.message)
    }
  } finally {
    saving.value = false
  }
}

async function onFreeze(): Promise<void> {
  const d = draft.value
  if (!d || freezing.value) return
  try {
    await ElMessageBox.confirm(
      '冻结以服务器上已保存的草稿内容为准（本地未保存的修改不会包含）。冻结后当前草稿版本不可变，并自动开启新草稿继续迭代。确认冻结？',
      '冻结版本',
      { type: 'warning', confirmButtonText: '冻结', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  freezing.value = true
  try {
    const r = await freezeComponentVersion(d.type)
    ElMessage.success(`已冻结 v${r.frozenVersion}，新草稿 v${r.draftVersion}`)
    await loadDraft(d.type)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    freezing.value = false
  }
}

/* ================= D3 发布治理（§8 生命周期 / §13 闸门 / §9.4 影响面） ================= */
const activeTab = ref('basic')
const pubVersion = ref<number | null>(null)
const pubRemark = ref('')
const publishing = ref(false)
const toggling = ref(false)
const gateItems = ref<GateItem[] | null>(null)
const publishResult = ref<PublishResult | null>(null)

const frozenVersions = computed(() => versions.value.filter((v) => v.state === 'frozen'))

/** 闸门 key → 中文名（与后端 run_gates 六项一一对应） */
const GATE_LABELS: Record<string, string> = {
  pure_data: '纯数据',
  whitelist: '字段白名单',
  drop_policy: 'dropPolicy',
  contract: '执行契约',
  hash_consistency: '同名一致',
  references: '引用完整性',
}
function gateLabel(g: string): string {
  return GATE_LABELS[g] ?? g
}

async function onPublish(): Promise<void> {
  const d = draft.value
  if (!d || !pubVersion.value || publishing.value) return
  publishing.value = true
  gateItems.value = null
  publishResult.value = null
  try {
    publishResult.value = await publishComponentVersion(d.type, {
      version: pubVersion.value, draftRev: d.draftRev, remark: pubRemark.value || undefined,
    })
    ElMessage.success(`已发布 v${publishResult.value.publishedVersion}`)
    pubVersion.value = null
    await loadDraft(d.type)
  } catch (e) {
    const err = e as Error & { code?: number; data?: unknown }
    if (err.code === 6003) {
      // 闸门未过：422 data.items 逐项渲染（§13 闸门不可绕过，无 force/豁免）
      gateItems.value = (err.data as { items?: GateItem[] } | null)?.items ?? []
      ElMessage.error('发布闸门未通过，请逐项整改后重试')
    } else {
      ElMessage.error(err.message)
    }
  } finally {
    publishing.value = false
  }
}

async function onOffline(): Promise<void> {
  const d = draft.value
  if (!d || toggling.value) return
  try {
    await ElMessageBox.confirm(
      '下线后组件不再供给新引用（画布注入停止），既有工作流引用照常运行（published_version 保留）。确认下线？',
      '下线组件',
      { type: 'warning', confirmButtonText: '下线', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  toggling.value = true
  try {
    await offlineComponent(d.type)
    ElMessage.success('已下线')
    await loadDraft(d.type)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    toggling.value = false
  }
}

/** 回滚目标须「曾发布后下线」（state=offline 且 publishedAt 非空，§8；不重跑闸门） */
async function onRollback(v: ComponentVersionRow): Promise<void> {
  const d = draft.value
  if (!d || toggling.value) return
  try {
    await ElMessageBox.confirm(
      `回滚到 v${v.version}：当前 published 版本自动让位下线，既有引用下次保存时对齐到 v${v.version}。确认回滚？`,
      '回滚版本',
      { type: 'warning', confirmButtonText: '回滚', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  toggling.value = true
  try {
    await rollbackComponent(d.type, v.version)
    ElMessage.success(`已回滚到 v${v.version}`)
    await loadDraft(d.type)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : String(e))
  } finally {
    toggling.value = false
  }
}

/* ---- 影响面 + 批量升级向导（§9.4，懒加载） ---- */
const impacted = ref<ImpactedWorkflow[]>([])
const impactedMeta = ref<{ publishedVersion: number | null; state: string } | null>(null)
const impactedLoading = ref(false)
const impactedLoaded = ref(false)
const upgradeSel = ref<ImpactedWorkflow[]>([])
const upgrading = ref(false)
const upgradeReport = ref<{ name: string; ok: boolean; msg: string }[]>([])
const impTable = ref<TableInstance | null>(null)

function selectableRow(row: ImpactedWorkflow): boolean {
  return !row.aligned // 已对齐行不可选（无可升级内容）
}
function onImpactedSel(rows: ImpactedWorkflow[]): void {
  upgradeSel.value = rows.filter((w) => !w.aligned)
}

async function loadImpacted(): Promise<void> {
  const d = draft.value
  if (!d) return
  impactedLoading.value = true
  try {
    const r = await getImpactedWorkflows(d.type)
    impacted.value = r.items
    impactedMeta.value = { publishedVersion: r.publishedVersion ?? null, state: r.state ?? '' }
    impactedLoaded.value = true
    // 落后行默认勾选（upgrade 向导目标集；nextTick 等表格渲染后回填勾选态）
    await nextTick()
    const tb = impTable.value
    if (tb) r.items.filter((w) => w.behind).forEach((w) => tb.toggleRowSelection(w, true))
  } catch (e) {
    ElMessage.error(`影响面加载失败：${e instanceof Error ? e.message : String(e)}`)
  } finally {
    impactedLoading.value = false
  }
}

function onTabChange(name: string | number): void {
  if (name === 'release' && !impactedLoaded.value) void loadImpacted()
}

/** 单个工作流升级：online 先下线 → patch 引用版本 → 保存（base_version CAS）→ 重新上线（§9.3） */
async function upgradeOne(w: ImpactedWorkflow, pv: number): Promise<{ ok: boolean; msg: string }> {
  const compType = draft.value?.type ?? ''
  const wasOnline = w.releaseState === 'online'
  try {
    if (wasOnline) await offlineWorkflow(w.id) // online 定义保存被拒（WF_RELEASED_LOCKED）
    const doc: GraphDocument | null = await graphService.get(w.id)
    if (!doc) return { ok: false, msg: '定义不存在或已删除' }
    let patched = 0
    for (const n of doc.nodes) {
      const data = (n.data ?? {}) as Record<string, unknown>
      const ref = data.componentRef as { type?: string; version?: number } | undefined
      if (ref && ref.type === compType && ref.version !== pv) {
        ref.version = pv
        patched++
      }
    }
    if (!patched) {
      if (wasOnline) await publishWorkflow(w.id)
      return { ok: true, msg: '引用已对齐，无需升级' }
    }
    await graphService.save(doc, `组件升级：${compType} 引用对齐 v${pv}`)
    if (wasOnline) await publishWorkflow(w.id)
    return { ok: true, msg: `升级 ${patched} 个节点引用${wasOnline ? '，已重新上线' : ''}` }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    if (wasOnline) {
      // 补偿：失败行恢复上线，避免把工作流留在 offline；恢复失败则保留现场提示
      try { await publishWorkflow(w.id) } catch { /* 保留 offline，msg 已含失败原因 */ }
    }
    return { ok: false, msg }
  }
}

async function onUpgradeBatch(): Promise<void> {
  const pv = impactedMeta.value?.publishedVersion
  if (!pv || upgrading.value || !upgradeSel.value.length) return
  upgrading.value = true
  upgradeReport.value = []
  try {
    for (const w of upgradeSel.value) {
      const r = await upgradeOne(w, pv)
      upgradeReport.value.push({ name: `${w.name}（${w.id}）`, ok: r.ok, msg: r.msg })
    }
    ElMessage.success('批量升级执行完毕')
    await loadImpacted()
  } finally {
    upgrading.value = false
  }
}

/* ---- 新建组件草稿（:type 缺省态） ---- */
const c = ref({ type: '', name: '', profile: 'dag', executionModel: 'dag-engine', executor: '', category: '', description: '' })
const cErr = ref('')
const creating = ref(false)
const TYPE_RE = /^[a-z][a-z0-9_]{1,63}$/

const profileOptions = [
  { v: 'dag', t: 'DAG 编排' },
  { v: 'etl', t: 'ETL 管道' },
  { v: 'stream', t: '流处理' },
  { v: 'topo', t: '集群拓扑' },
]
const execOptions = [
  { v: 'dag-engine', t: 'DAG 引擎执行' },
  { v: 'canvas-device', t: '画布元件（不执行）' },
  { v: 'demo-only', t: '仅演示' },
  { v: 'runtime-only', t: '仅运行时' },
]

async function onCreate(): Promise<void> {
  cErr.value = ''
  const type = c.value.type.trim()
  if (!TYPE_RE.test(type)) {
    cErr.value = 'type 须为小写字母开头的 [a-z0-9_]（2~64 位）'
    return
  }
  if (!c.value.name.trim()) {
    cErr.value = '组件名称不能为空'
    return
  }
  creating.value = true
  try {
    const body: ComponentCreateBody = {
      type,
      name: c.value.name.trim(),
      profile: c.value.profile as ComponentCreateBody['profile'],
      executionModel: c.value.executionModel as ComponentCreateBody['executionModel'],
      category: c.value.category || undefined,
      executor: c.value.executor || undefined,
      description: c.value.description || undefined,
      spec: {},
    }
    await createComponentDraft(body)
    ElMessage.success('草稿已创建')
    router.replace(`/meta/components/design/${type}`)
  } catch (e) {
    cErr.value = e instanceof Error ? e.message : String(e)
  } finally {
    creating.value = false
  }
}

/* ================= 展示辅助 ================= */
const stateMeta: Record<string, { t: string; cls: string }> = {
  draft: { t: '草稿', cls: 'st-draft' },
  frozen: { t: '冻结', cls: 'st-frozen' },
  published: { t: '已发布', cls: 'st-pub' },
  offline: { t: '已下线', cls: 'st-off' },
}
function stateText(s: string): string {
  return stateMeta[s]?.t ?? s
}
function uiTypeLabel(v: SpecUiType): string {
  return SPEC_UI_TYPES.find((t) => t.value === v)?.label ?? v
}
</script>

<template>
  <div class="page">
    <header class="head">
      <div class="head-l">
        <el-button size="small" @click="router.push('/meta/components')">← 目录</el-button>
        <h2>{{ isCreate ? '新建组件草稿' : (draft ? `${draft.name}（${draft.type}）` : typeParam) }}</h2>
        <template v-if="draft">
          <span class="badge" :class="stateMeta[draft.state]?.cls">{{ stateText(draft.state) }}</span>
          <span class="muted">v{{ draft.draftVersion }} · rev {{ draft.draftRev }} · {{ draft.scope === 'user' ? '用户组件' : draft.scope }}</span>
        </template>
      </div>
      <div v-if="!isCreate" class="head-r">
        <el-button size="small" :type="previewOn ? 'primary' : 'default'" plain @click="previewOn = !previewOn">
          {{ previewOn ? '隐藏预览' : '预览' }}
        </el-button>
        <el-button size="small" type="warning" :loading="freezing" :disabled="!draft" @click="onFreeze">冻结版本</el-button>
        <el-button size="small" type="primary" :loading="saving" :disabled="!draft" @click="onSave">保存</el-button>
      </div>
    </header>

    <el-alert v-if="builtinGuide" type="warning" :closable="false" show-icon class="err-alert"
      title="内置组件请到基线化工作台修订（支持复制上版开修订轮）">
      <template #default>
        「{{ builtinGuide.type }}」为基线化内置组件（已发版留档，无用户草稿链）。
        <el-button link type="primary"
          @click="router.push({ path: '/meta/baseline', query: { type: builtinGuide.type } })">
          前往基线化工作台</el-button>
      </template>
    </el-alert>
    <el-alert v-else-if="loadErr" type="error" :closable="false" :title="`草稿加载失败：${loadErr}`" show-icon class="err-alert" />

    <div class="layout">
      <!-- 左侧：版本列表（草稿/冻结；B5 versions 端点） -->
      <aside v-if="!isCreate" class="side">
        <div class="side-t">版本（{{ versions.length }}）</div>
        <div
          v-for="v in versions" :key="v.version" class="vrow"
          :class="{ cur: draft && v.version === draft.draftVersion && v.state === 'draft' }"
        >
          <div class="v-head">
            <span class="v-n">v{{ v.version }}</span>
            <span class="badge" :class="stateMeta[v.state]?.cls">{{ stateText(v.state) }}</span>
          </div>
          <div class="v-sub">{{ v.remark || '—' }}</div>
          <div class="v-hash">{{ v.specHash.slice(0, 12) }}</div>
        </div>
        <el-button size="small" class="new-btn" @click="router.push('/meta/components/design')">＋ 新建组件</el-button>
        <p class="side-note">版本不可变：冻结后内容随行固化（B5）；发布属 M2（frozen→published）。</p>
      </aside>

      <!-- 中部：声明编辑 -->
      <main class="center" v-loading="loading">
        <!-- 新建表单 -->
        <section v-if="isCreate" class="create">
          <el-alert v-if="cErr" type="error" :closable="false" :title="cErr" show-icon />
          <div class="form-grid">
            <label>type<i>*</i></label>
            <el-input v-model="c.type" placeholder="小写字母开头的 [a-z0-9_]（2~64 位），如 dag_transform_sql" />
            <label>组件名称<i>*</i></label>
            <el-input v-model="c.name" placeholder="如 SQL 转换" />
            <label>Profile</label>
            <select class="native" v-model="c.profile">
              <option v-for="o in profileOptions" :key="o.v" :value="o.v">{{ o.t }}</option>
            </select>
            <label>执行模型</label>
            <select class="native" v-model="c.executionModel">
              <option v-for="o in execOptions" :key="o.v" :value="o.v">{{ o.t }}</option>
            </select>
            <label>executor</label>
            <el-input v-model="c.executor" placeholder="executor 注册名（发布闸门校验，可后补）" />
            <label>分类</label>
            <el-input v-model="c.category" placeholder="如 transform（可空）" />
            <label>描述</label>
            <el-input v-model="c.description" placeholder="组件用途说明（可空）" />
          </div>
          <el-button type="primary" :loading="creating" @click="onCreate">创建草稿</el-button>
          <p class="hint">创建后进入声明编辑（基本信息 / 端口 / 表单字段 / dropPolicy），身份字段创建后不可改。</p>
        </section>

        <!-- 编辑态 Tabs（D3：发布治理 Tab 懒加载影响面） -->
        <el-tabs v-else-if="draft" v-model="activeTab" class="tabs" @tab-change="onTabChange">
          <el-tab-pane label="基本信息" name="basic">
            <div class="ident">
              <div><span class="k">type</span>{{ draft.type }}</div>
              <div><span class="k">名称</span>{{ draft.name }}</div>
              <div><span class="k">Profile</span>{{ draft.profile }}</div>
              <div><span class="k">执行模型</span>{{ draft.executionModel }}</div>
              <div><span class="k">executor</span>{{ draft.executor || '—' }}</div>
              <div><span class="k">分类</span>{{ draft.category || '—' }}</div>
              <div class="wide"><span class="k">描述</span>{{ draft.description || '—' }}</div>
              <div><span class="k">已发布版本</span>{{ draft.publishedVersion ?? '未发布' }}</div>
            </div>
            <p class="hint">身份字段创建后只读（主表，无更新端点）；以下为声明（spec）级外观，随草稿保存。</p>
            <div class="form-grid">
              <label>图标</label>
              <div>
                <el-input v-model="spec.icon" placeholder="字符图标，如 ⚙" style="width: 200px" :class="{ badinput: iconMsgs.length }" />
                <div v-for="(m, i) in iconMsgs" :key="i" class="err-line">{{ m }}</div>
              </div>
              <label>颜色</label>
              <div>
                <el-input v-model="spec.color" placeholder="#4C7CF0" style="width: 200px" :class="{ badinput: colorMsgs.length }" />
                <div v-for="(m, i) in colorMsgs" :key="i" class="err-line">{{ m }}</div>
              </div>
              <label>摘要</label>
              <div>
                <el-input v-model="spec.summary" placeholder="节点副标题（纯文本声明）" style="width: 420px" :class="{ badinput: summaryMsgs.length }" />
                <div v-for="(m, i) in summaryMsgs" :key="i" class="err-line">{{ m }}</div>
              </div>
              <label>面板可见</label>
              <div>
                <el-switch v-model="spec.paletteVisible" />
                <span class="hint" style="margin: 0 0 0 8px">仅装载物化消费的 runtime-only 组件须关闭（发布闸门 §13-5 强制）</span>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane label="端口" name="ports">
            <div class="ports">
              <div v-for="side in (['inputs', 'outputs'] as const)" :key="side" class="port-col">
                <div class="side-t">{{ side === 'inputs' ? '输入端口' : '输出端口' }}</div>
                <div v-for="(p, i) in spec.ports[side]" :key="i" class="port-row">
                  <el-input v-model="p.name" placeholder="端口名" size="small" style="width: 140px" />
                  <el-input v-model="p.type" placeholder="类型（如 dataset）" size="small" style="width: 160px" />
                  <el-button link type="danger" size="small" @click="removePort(side, i)">删除</el-button>
                </div>
                <el-button size="small" @click="addPort(side)">＋ 添加{{ side === 'inputs' ? '输入' : '输出' }}端口</el-button>
                <p class="hint">动态条件端口（conditionalPorts DSL）为遗留决策 D7，此处仅静态端口声明。</p>
              </div>
            </div>
          </el-tab-pane>

          <el-tab-pane :label="`表单字段（${spec.fields.length}）`" name="fields">
            <el-button size="small" type="primary" plain @click="addField">＋ 添加字段</el-button>
            <div
              v-for="(f, i) in spec.fields" :key="i" class="frow"
              :class="{ bad: fieldMsgs(i).length }"
            >
              <div class="frow-grid">
                <el-input v-model="f.key" placeholder="key（英文标识）" size="small" style="width: 150px" />
                <el-input v-model="f.label" placeholder="字段名" size="small" style="width: 130px" />
                <select class="native" v-model="f.uiType" title="控件类型（B3 收敛 9 基元）">
                  <option v-for="t in SPEC_UI_TYPES" :key="t.value" :value="t.value">{{ t.label }}</option>
                </select>
                <label class="req-c"><input v-model="f.required" type="checkbox" />必填</label>
                <el-input :model-value="defaultText(f.default)" placeholder="默认值" size="small" style="width: 120px" @update:model-value="setFieldDefault(f, $event)" />
                <el-input v-model="f.desc" placeholder="说明（渲染为 placeholder）" size="small" style="width: 200px" />
                <span class="muted">{{ uiTypeLabel(f.uiType) }}</span>
                <el-button link type="danger" size="small" @click="removeField(i)">删除</el-button>
              </div>
              <div v-if="f.uiType === 'select'" class="frow-sub">
                <span class="sf-t">静态候选</span>
                <div v-for="(o, oi) in f.options" :key="oi" class="opt-row">
                  <el-input v-model="o.label" placeholder="显示名" size="small" style="width: 140px" />
                  <el-input v-model="o.value" placeholder="值" size="small" style="width: 140px" />
                  <el-button link type="danger" size="small" @click="f.options?.splice(oi, 1)">✕</el-button>
                </div>
                <el-button link size="small" @click="addFieldOption(f)">＋ 选项</el-button>
              </div>
              <div class="frow-sub">
                <span class="sf-t">showIf（JSON 条件，初版语法校验；空 = 恒显示）</span>
                <el-input
                  :model-value="showIfText[f.key]" type="textarea" :rows="2" size="small"
                  placeholder='如 {"field":"mode","in":["a","b"]}'
                  @update:model-value="onShowIfInput(f, $event)"
                />
              </div>
              <div v-for="(m, mi) in fieldMsgs(i)" :key="mi" class="err-line">{{ m }}</div>
            </div>
            <p v-if="!spec.fields.length" class="hint">暂无字段声明。uiType 白名单为 B3 收敛的 9 基元；禁用片段（函数/代码/模板语法）打字即红标。</p>
          </el-tab-pane>

          <el-tab-pane label="dropPolicy" name="drop">
            <div class="form-grid">
              <label>自动命名模板</label>
              <div>
                <el-input v-model="spec.dropPolicy.autoName" placeholder="如 {type}_{n}（占位符仅允许 {type}/{n}）" style="width: 320px" :class="{ badinput: autoNameMsgs.length }" />
                <div v-for="(m, i) in autoNameMsgs" :key="i" class="err-line">{{ m }}</div>
              </div>
              <label>吸附网格</label>
              <label class="req-c"><input v-model="spec.dropPolicy.snapToGrid" type="checkbox" />落点吸附网格</label>
              <label>实例数上限</label>
              <el-input :model-value="String(spec.dropPolicy.maxInstances ?? 0)" style="width: 140px" placeholder="0 = 不限" @update:model-value="onMaxInstancesInput" />
              <label>上游预填字段</label>
              <el-input :model-value="prefillText" style="width: 420px" placeholder="逗号分隔的字段 key（drop 时从上游节点一次性快照预填）" @update:model-value="onPrefillInput" />
              <label>自动连边</label>
              <div class="ac-row">
                上游
                <select class="native" :value="spec.dropPolicy.autoConnect.upstream" @change="setAutoConnect('upstream', $event)">
                  <option value="nearest">最近节点</option>
                  <option value="none">不自动连</option>
                </select>
                下游
                <select class="native" :value="spec.dropPolicy.autoConnect.downstream" @change="setAutoConnect('downstream', $event)">
                  <option value="nearest">最近节点</option>
                  <option value="none">不自动连</option>
                </select>
              </div>
            </div>
            <p class="hint">纯数据 DSL（治理设计 §11）：禁函数/表达式字符串；拖入必弹窗（configure-first）为全局默认行为，不再声明。</p>
          </el-tab-pane>

          <!-- D3 发布治理：闸门逐项面板 / 版本时间线（下线·回滚）/ 影响面 + 批量升级向导 -->
          <el-tab-pane label="发布治理" name="release">
            <section class="rel-sec">
              <div class="rel-t">
                发布
                <span class="muted">§13 闸门全部通过才落 published，不可绕过（无 force / 无豁免）</span>
                <el-button
                  v-if="draft && draft.state === 'published'" size="small" type="warning" plain
                  :loading="toggling" @click="onOffline"
                >下线组件</el-button>
              </div>
              <div class="pub-row">
                <el-select v-model="pubVersion" placeholder="选择 frozen 版本" size="small" style="width: 210px">
                  <el-option
                    v-for="v in frozenVersions" :key="v.version" :value="v.version"
                    :label="`v${v.version} · ${v.specHash.slice(0, 12)}`"
                  />
                </el-select>
                <el-input v-model="pubRemark" placeholder="发布备注（可空）" size="small" style="width: 240px" />
                <el-button type="primary" size="small" :loading="publishing" :disabled="!pubVersion" @click="onPublish">
                  发布
                </el-button>
                <span v-if="!frozenVersions.length" class="muted">暂无 frozen 版本——先在左侧「冻结版本」</span>
              </div>
              <div v-if="gateItems" class="gate-panel">
                <div class="gate-t">
                  闸门结果（{{ gateItems.filter((g) => g.ok).length }}/{{ gateItems.length }} 通过）
                </div>
                <div v-for="g in gateItems" :key="g.gate" class="gate-row" :class="g.ok ? 'ok' : 'bad'">
                  <span class="g-ic">{{ g.ok ? '✓' : '✕' }}</span>
                  <span class="g-n">{{ gateLabel(g.gate) }}</span>
                  <span class="g-m">{{ g.msg }}</span>
                </div>
              </div>
              <div v-if="publishResult" class="pub-ok">
                已发布 v{{ publishResult.publishedVersion }}（spec {{ publishResult.specHash.slice(0, 12) }}，{{ publishResult.publishedAt }}）
                <template v-if="publishResult.supersededVersion">，旧版 v{{ publishResult.supersededVersion }} 已让位下线</template>
              </div>
            </section>

            <section class="rel-sec">
              <div class="rel-t">版本时间线</div>
              <el-table :data="versions" size="small" border>
                <el-table-column label="版本" width="130">
                  <template #default="{ row }">
                    v{{ row.version }}
                    <span v-if="draft && row.version === draft.publishedVersion" class="curtag">当前供给</span>
                  </template>
                </el-table-column>
                <el-table-column label="状态" width="86">
                  <template #default="{ row }">
                    <span class="badge" :class="stateMeta[row.state as string]?.cls">{{ stateText(row.state as string) }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="specHash" width="120">
                  <template #default="{ row }"><code class="hsh">{{ row.specHash.slice(0, 12) }}</code></template>
                </el-table-column>
                <el-table-column label="备注" min-width="130">
                  <template #default="{ row }">{{ row.remark || '—' }}</template>
                </el-table-column>
                <el-table-column label="发布人" width="90">
                  <template #default="{ row }">{{ row.publishedBy || '—' }}</template>
                </el-table-column>
                <el-table-column label="发布时间" width="150">
                  <template #default="{ row }">{{ row.publishedAt || '—' }}</template>
                </el-table-column>
                <el-table-column label="操作" width="110" fixed="right">
                  <template #default="{ row }">
                    <el-button
                      v-if="row.state === 'frozen'" link type="primary" size="small"
                      @click="pubVersion = row.version"
                    >选为发布目标</el-button>
                    <el-button
                      v-else-if="draft && draft.state === 'published' && row.version === draft.publishedVersion"
                      link type="warning" size="small" :loading="toggling" @click="onOffline"
                    >下线</el-button>
                    <el-button
                      v-else-if="row.state === 'offline' && row.publishedAt"
                      link type="primary" size="small" :loading="toggling" @click="onRollback(row)"
                    >回滚到此版</el-button>
                    <span v-else class="muted">—</span>
                  </template>
                </el-table-column>
              </el-table>
              <p class="hint">
                下线不阻断既有运行（published_version 保留，仅停止新引用供给）；回滚仅限「曾发布后下线」的版本，
                不重跑闸门（版本行不可变，内容与过闸时一致）；首次发布归属（发布人/时间）不随回滚改写。
              </p>
            </section>

            <section class="rel-sec">
              <div class="rel-t">
                影响面
                <span v-if="impactedMeta" class="muted">
                  组件 {{ impactedMeta.state }} · 供给 v{{ impactedMeta.publishedVersion ?? '—' }}
                </span>
                <el-button size="small" link type="primary" @click="loadImpacted">刷新</el-button>
                <el-button
                  size="small" type="primary" :loading="upgrading"
                  :disabled="!upgradeSel.length || !impactedMeta?.publishedVersion" @click="onUpgradeBatch"
                >批量升级选中（{{ upgradeSel.length }}）</el-button>
              </div>
              <el-table
                ref="impTable" :data="impacted" v-loading="impactedLoading" size="small" border
                @selection-change="onImpactedSel"
              >
                <el-table-column type="selection" width="42" :selectable="selectableRow" />
                <el-table-column label="工作流" min-width="170">
                  <template #default="{ row }">{{ row.name }} <code class="hsh">{{ row.id }}</code></template>
                </el-table-column>
                <el-table-column label="定义版本" width="80">
                  <template #default="{ row }">v{{ row.version }}</template>
                </el-table-column>
                <el-table-column label="状态" width="84">
                  <template #default="{ row }">
                    <span :class="row.releaseState === 'online' ? 'onl' : 'muted'">{{ row.releaseState }}</span>
                  </template>
                </el-table-column>
                <el-table-column label="引用版本" min-width="110">
                  <template #default="{ row }">
                    {{ (row.refVersions as number[]).length ? (row.refVersions as number[]).map((v) => `v${v}`).join('、') : '—' }}
                  </template>
                </el-table-column>
                <el-table-column label="对齐" width="110">
                  <template #default="{ row }">
                    <span v-if="row.aligned" class="oktag">已对齐</span>
                    <span v-else-if="row.behind" class="badtag">落后于供给</span>
                    <span v-else class="warntag">高于供给</span>
                  </template>
                </el-table-column>
              </el-table>
              <div v-if="upgradeReport.length" class="up-report">
                <div v-for="(r, i) in upgradeReport" :key="i" :class="r.ok ? 'ok' : 'bad'">
                  {{ r.ok ? '✓' : '✕' }} {{ r.name }}<template v-if="r.msg">：{{ r.msg }}</template>
                </div>
              </div>
              <p class="hint">
                升级链路（§9.3）：online 定义先下线 → 改引用版本 → 保存（base_version CAS）→ 重新上线；逐行汇报结果，失败行恢复原状态保留现场。
              </p>
            </section>
          </el-tab-pane>
        </el-tabs>
      </main>

      <!-- 右侧：实时预览 -->
      <aside v-if="previewOn && !isCreate && draft" class="preview">
        <div class="side-t">实时预览 <span class="muted">F0 渲染器吃声明数据</span></div>
        <p class="hint">showIf 为运行时判定，预览恒显示；rows/mapEditor/resource 依赖画布上下文，预览略。</p>
        <div v-if="!previewFields.length" class="hint">暂无可预览字段</div>
        <div v-for="p in previewFields" :key="p.key" class="pv-field">
          <label class="pv-label">{{ p.schema.label }}<i v-if="p.f.required">*</i></label>
          <FieldRenderer
            :field="p.schema" :data="previewData" mode="edit" node-id="preview" :ctx="previewCtx"
            @set="onPreviewSet" @dirty="() => {}" @open-var-dialog="() => {}" @focus-target="() => {}"
          />
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.page { padding: 16px; }
.head { display: flex; justify-content: space-between; align-items: center; gap: 16px; }
.head-l { display: flex; align-items: center; gap: 10px; }
h2 { margin: 0; font-size: 17px; }
.muted { color: #94a3b8; font-size: 11px; }
.badge { font-size: 11px; padding: 1px 7px; border-radius: 3px; background: #f1f5f9; color: #475569; }
.badge.st-draft { background: #fef9c3; color: #a16207; }
.badge.st-frozen { background: #dbeafe; color: #1d4ed8; }
.badge.st-pub { background: #dcfce7; color: #15803d; }
.badge.st-off { background: #f1f5f9; color: #94a3b8; }
.err-alert { margin-top: 12px; }
.layout { display: flex; gap: 14px; margin-top: 14px; align-items: flex-start; }
.side { width: 220px; flex-shrink: 0; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; background: #fff; }
.side-t { font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 8px; }
.vrow { border: 1px solid #f1f5f9; border-radius: 5px; padding: 6px 8px; margin-bottom: 6px; font-size: 11px; }
.vrow.cur { border-color: #93c5fd; background: #eff6ff; }
.v-head { display: flex; gap: 6px; align-items: center; }
.v-n { font-weight: 600; }
.v-sub { color: #64748b; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.v-hash { color: #cbd5e1; font-family: monospace; margin-top: 1px; }
.new-btn { margin-top: 4px; width: 100%; }
.side-note { font-size: 10px; color: #cbd5e1; line-height: 1.6; margin: 8px 0 0; }
.center { flex: 1; min-width: 0; }
.create { max-width: 640px; }
.form-grid { display: grid; grid-template-columns: 110px 1fr; gap: 8px 10px; align-items: center; margin: 12px 0; }
.form-grid > label { font-size: 12px; color: #475569; text-align: right; }
.form-grid > label i, .pv-label i { color: #ef4444; font-style: normal; margin-left: 2px; }
.hint { font-size: 11px; color: #94a3b8; line-height: 1.7; margin: 8px 0 0; }
.native { border: 1px solid #dcdfe6; border-radius: 4px; padding: 5px 8px; font-size: 12px; background: #fff; color: #606266; }
.ident { display: flex; flex-wrap: wrap; gap: 6px 18px; font-size: 12px; color: #334155; margin-bottom: 4px; }
.ident .k { display: inline-block; min-width: 72px; color: #94a3b8; }
.ident .wide { width: 100%; }
.ports { display: flex; gap: 24px; }
.port-col { flex: 1; }
.port-row { display: flex; gap: 6px; align-items: center; margin-bottom: 6px; }
.frow { border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 10px; margin-top: 8px; }
.frow.bad { border-color: #fca5a5; background: #fef2f2; }
.frow-grid { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.req-c { display: flex; align-items: center; gap: 4px; font-size: 12px; color: #475569; }
.frow-sub { margin-top: 6px; padding-top: 6px; border-top: 1px dashed #f1f5f9; }
.sf-t { display: block; font-size: 10.5px; color: #94a3b8; margin-bottom: 4px; }
.opt-row { display: flex; gap: 6px; align-items: center; margin-bottom: 4px; }
.err-line { font-size: 11px; color: #dc2626; margin-top: 4px; word-break: break-all; }
.badinput :deep(input) { border-color: #f87171 !important; background: #fef2f2; }
.ac-row { display: flex; gap: 6px; align-items: center; font-size: 12px; color: #475569; }
.preview { width: 300px; flex-shrink: 0; border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px; background: #fff; }
.pv-field { margin-bottom: 12px; }
.pv-label { display: block; font-size: 11.5px; color: #475569; margin-bottom: 3px; }
.preview :deep(input), .preview :deep(select), .preview :deep(textarea) { font-size: 12px; }
/* ---- D3 发布治理 ---- */
.rel-sec { border: 1px solid #e2e8f0; border-radius: 6px; padding: 10px 12px; margin-bottom: 12px; background: #fff; }
.rel-t { display: flex; align-items: center; gap: 10px; font-size: 13px; font-weight: 600; color: #334155; margin-bottom: 8px; }
.pub-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gate-panel { margin-top: 10px; border: 1px solid #fde68a; background: #fffbeb; border-radius: 6px; padding: 8px 10px; }
.gate-t { font-size: 11.5px; font-weight: 600; color: #92400e; margin-bottom: 6px; }
.gate-row { display: flex; gap: 8px; align-items: baseline; font-size: 11.5px; line-height: 1.8; }
.gate-row.ok .g-ic { color: #16a34a; }
.gate-row.bad .g-ic { color: #dc2626; }
.g-ic { width: 14px; flex-shrink: 0; font-weight: 700; }
.g-n { width: 88px; flex-shrink: 0; font-weight: 500; color: #475569; }
.g-m { color: #64748b; word-break: break-all; }
.pub-ok { margin-top: 10px; font-size: 12px; color: #15803d; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 6px 10px; }
.curtag { font-size: 10px; color: #15803d; background: #dcfce7; border-radius: 3px; padding: 0 5px; margin-left: 4px; }
.hsh { font-size: 10.5px; color: #64748b; font-family: monospace; }
.onl { color: #15803d; font-size: 11.5px; }
.oktag, .badtag, .warntag { font-size: 11px; padding: 1px 7px; border-radius: 3px; }
.oktag { background: #dcfce7; color: #15803d; }
.badtag { background: #fee2e2; color: #b91c1c; }
.warntag { background: #fef9c3; color: #a16207; }
.up-report { margin-top: 8px; border-top: 1px dashed #e2e8f0; padding-top: 6px; font-size: 11.5px; line-height: 1.9; }
.up-report .ok { color: #15803d; }
.up-report .bad { color: #dc2626; word-break: break-all; }
</style>
