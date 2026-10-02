/**
 * F1/F0：FieldCtx 组装工厂（治理设计 §12.2 渲染复用约束——弹窗与 Inspector 共用同一套
 * 候选状态、动态联动与脚本库互通逻辑，禁止双实现漂移）。
 *
 * 节点差异完全参数化：Inspector 传「画布选中节点」，DropConfigDialog 传「未落画布的
 * 虚拟节点」（预生成 id，无边 → upstream 为空数组，即拖入期真实上下文）。
 * 必须在组件 setup 内调用（内部 watch 绑定当前实例，随宿主组件卸载自动清理）。
 */
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { ComputedRef, Ref } from 'vue'
import type { GNode } from '../../model'
import type { FieldSchema, NodeSchema } from '../../profiles/types'
import { clearOnConditionHide, condVisible, probeMatchTables, requiredMissing, resolveDataContext } from '../../profiles/formLinkage'
import type { DataContext, NodeOutputSchema } from '../../profiles/formLinkage'
import { pickCfg, resolveDsId, sortByCanvasX } from '../../profiles/pickerLogic'
import { useGraphStore } from '../../../stores/graph'
import { useAuthStore } from '../../../stores/auth'
import { builtinVars } from '../../../stores/ideStore'
import { dataStore } from '../../../services/mock/dataStore'
import { localTime } from '../../../services/mock/timeUtil'
import { isMock, listRuntimeNodes, listSshNodes, listVariables } from '../../../services'
import { getDataSourceTree, listDataSources, listKafkaTopics, listNodeDir } from '../../../services/datasourceApi'
import { listGlobalParams } from '../../../services/ideApi'
import type { DsRow, DsTree } from '../../../services/datasourceApi'
import type { Script } from '../../../services/types'
import type { DirNav, EpProbeState, FieldCtx, RuntimeNodeOpt } from './fieldCtx'

const FALLBACK_SCHEMA: NodeSchema = { type: 'unknown', label: '未知', icon: '?', color: '#94a3b8', form: [] }

/** 工厂入参：节点与宿主环境（其余全部内部自持） */
export interface FieldCtxHost {
  /** 目标节点（Inspector=画布选中节点 ref；弹窗=虚拟节点 ref） */
  node: Ref<GNode | null>
  /** 组件声明查找表（profile.nodeTypes） */
  nodeTypes: Record<string, NodeSchema>
  /** 脏标记（弹窗期传 no-op；确认落画布时由调用点统一 markDirty 一次） */
  markDirty: () => void
  /** token-insert 插入后聚焦目标 textarea 的容器（Inspector/弹窗各自持根元素引用） */
  rootEl: Ref<HTMLElement | null>
  /**
   * 上游覆盖（弹窗期专用）：虚拟节点未落画布 → doc.edges 中无指向它的边，
   * 若沿用画布口径则 upstream 恒空、①输入无候选、dataScope 上游两域恒禁用。
   * 宿主按 §11 划界语义传入「本次拖入的逻辑上游」（prefillFromUpstream 同一取法：
   * 当前选中节点优先，否则落点最近节点），使拖入期值域与落画布后一致。
   * 传 null/undefined = 走 doc.edges 画布口径（Inspector）。
   */
  upstreamOverride?: Ref<GNode[] | null>
}

/** 工厂产出：FieldCtx 本体 + 宿主渲染所需的派生态 */
export interface FieldCtxBundle {
  ctx: FieldCtx
  /** 当前节点 schema（Inspector 标题/页面入口等消费） */
  schema: ComputedRef<NodeSchema | null>
  /** showIf 过滤后的业务表单（弹窗与 Inspector 共用同一判定） */
  visibleForm: ComputedRef<FieldSchema[]>
  /** W1 必填缺失 label 清单（弹窗警示条/确认禁用与 Inspector 角标同判定） */
  missingLabels: ComputedRef<string[]>
  /** 业务字段写值（number 转数值存储）+ onChange 联动分发 */
  onSet: (f: FieldSchema, ev: Event) => void
  /** 通用字段写值（节点名称等宿主自有字段复用同一 number 转数值契约） */
  upd: (key: string, ev: Event) => void
  /** 已注册变量候选（变量引用弹窗 UI 壳由宿主自持） */
  varOptions: Ref<string[]>
  /** F3 数据驱动值域上下文（dataScope 字段候选来源；弹窗期宿主可直接消费） */
  dataCtx: ComputedRef<DataContext>
  /** F60 ①输入 的上游输出引用候选（`节点名.键（类型）`）；值域校验的悬空引用判定同源消费 */
  upstreamOuts: ComputedRef<string[]>
  /** 共享候选拉载（数据源/脚本库/运行时节点/SSH 标签；幂等） */
  loadShared: () => Promise<void>
  /** 单独预载上游选定表的库表树（值域域依赖；loadShared 已含，宿主切上游时可单独调） */
  ensureUpstreamTrees: () => Promise<void>
  /** token-insert 插入后聚焦目标字段（依 host.rootEl 定位） */
  focusTarget: (key: string) => void
}

export function createFieldCtx(host: FieldCtxHost): FieldCtxBundle {
  const graphStore = useGraphStore()
  const auth = useAuthStore()

  /* ================= 节点派生（schema/upstream/可见表单/W1） ================= */
  const node = host.node
  const schema = computed(() => (node.value ? host.nodeTypes[node.value.type] ?? null : null))

  const upstream = computed<GNode[]>(() => {
    const ov = host.upstreamOverride?.value
    if (ov) return ov
    const doc = graphStore.doc
    if (!doc || !node.value) return []
    return doc.edges
      .filter((e) => e.target === node.value!.id)
      .map((e) => doc.nodes.find((n) => n.id === e.source))
      .filter((n): n is GNode => !!n)
  })
  const upSchema = (n: GNode): NodeSchema => host.nodeTypes[n.type] ?? FALLBACK_SCHEMA

  /**
   * 上游输出 schema 供给（F2/F3 缺口闭合，2026-09-27 二次修正）：
   * `resolveDataContext` 一直支持 `upstreamSchemas` 入参，但此前无任何调用点提供 →
   * `dataScope` 的 `upstream-columns` / `upstream-tables` 两域结构性恒空，值域闸门形同虚设。
   *
   * 供给源按「真实性」分层，全部取自用户已在组件里选定/登记的事实，不依赖尚不存在的 probe / L2 服务：
   *  1. **上游已选定的库表**（主源）：扫上游节点的 dsKey/tableKey 配对（`srcDs`+`srcTable`、
   *     `tgtDs`+`tgtTable` 等，见 `resolveDsId`/`pickCfg` 既有口径），按已加载的 `pickTrees`
   *     解析出物理表名与列名——这正是 `field_map` 的 `columnMap` 取列走的同一条链路，故口径一致。
   *  2. **②输出登记的结果表**（补充源）：`node.data.outputs.tables[].v`（空则回退 `k`）。
   *     取 `v` 物理表名而非 DAG 内输出别名：dataScope 语义是「限死只能填上游真实存在的表」，
   *     填别名 `t1` 会被误判合法，实际并非可写入的表。
   * 并集去重保序由 resolveDataContext 负责；本 computed 声明在 ensureTree 之后，故可读 pickTrees。
   */
  /** 上游节点「数据源名 + 表名」配对扫描（dsKey/tableKey 同前缀约定，覆盖 src/tgt 与自定义命名） */
  function upstreamTablesOf(d: Record<string, unknown>): { ds: string; table: string }[] {
    const pairs: { ds: string; table: string }[] = []
    for (const [k, v] of Object.entries(d)) {
      if (!k.endsWith('Table') || typeof v !== 'string' || !v.trim()) continue
      const ds = d[k.replace(/Table$/, 'Ds')]
      pairs.push({ ds: typeof ds === 'string' ? ds : '', table: v.trim() })
    }
    return pairs
  }
  /** 从已加载的 pickTrees 解析物理表名与列名（connection 走库表树；file 走文件 schema） */
  function resolveTreeSchema(ds: string, table: string): { tables: string[]; columns: string[] } {
    const t = ds ? pickTrees.value[ds] : undefined
    if (!t) return { tables: [], columns: [] }
    if (t.kind === 'file') {
      return table && table !== t.file ? { tables: [], columns: [] } : { tables: [t.file], columns: t.schema.columns.map((c) => c.name) }
    }
    for (const db of t.databases) {
      const hit = db.tables.find((x) => x.name === table)
      if (hit) return { tables: [hit.name], columns: hit.columns.map((c) => c.name) }
    }
    return { tables: [], columns: [] }
  }
  const upstreamSchemas = computed<Record<string, NodeOutputSchema>>(() => {
    const out: Record<string, NodeOutputSchema> = {}
    for (const u of upstream.value) {
      const d = (u.data ?? {}) as Record<string, unknown>
      const tables: string[] = []
      const columns: string[] = []
      /* 1. 上游已选定的库表 → 真实表/列 */
      for (const p of upstreamTablesOf(d)) {
        const r = resolveTreeSchema(p.ds, p.table)
        tables.push(...r.tables)
        columns.push(...r.columns)
      }
      /* 2. ②输出登记的结果表（并入表集；列留给 L2/probe 阶段） */
      const outputs = d.outputs as { tables?: { k?: string; v?: string }[] } | undefined
      tables.push(...(outputs?.tables ?? []).map((t) => String(t?.v ?? '').trim() || String(t?.k ?? '').trim()).filter(Boolean))
      const uniqT = [...new Set(tables.filter(Boolean))]
      const uniqC = [...new Set(columns.filter(Boolean))]
      if (uniqT.length || uniqC.length) out[u.id] = { tables: uniqT, columns: uniqC }
    }
    return out
  })

  /** 上游选定表的数据源树预载（值域域依赖它；幂等、失败静默不阻断表单） */
  async function ensureUpstreamTrees(): Promise<void> {
    for (const u of upstream.value) {
      for (const p of upstreamTablesOf((u.data ?? {}) as Record<string, unknown>)) {
        if (p.ds) await ensureTree(p.ds)
      }
    }
  }


  /** 端点合一具名化输出枚举（有 outputs 按端口展开 `nodeId:port`） */
  const upstreamOpts = computed<{ value: string; label: string }[]>(() => upstream.value.flatMap((n) => {
    const ports = host.nodeTypes[n.type]?.outputs ?? []
    if (ports.length) {
      return ports.map((p) => ({ value: `${n.id}:${p.id}`, label: `${n.data?.name ?? n.type} · ${p.label}` }))
    }
    return [{ value: `${n.id}:`, label: `${n.data?.name ?? n.type} (${n.type})` }]
  }))

  function nodeData(): Record<string, unknown> {
    return node.value?.data ?? {}
  }

  /** 条件展示过滤（I4 表单联动，弹窗/Inspector 同一判定）：旧 showIf 函数 + M-B2 八段 conditions 声明双轨求值 */
  const visibleForm = computed<FieldSchema[]>(() => {
    const s = schema.value
    const d = node.value?.data ?? {}
    return (s?.form ?? []).filter((f) => (!f.showIf || f.showIf(d)) && condVisible(s?.conditions, f.key, d))
  })

  /** W1 必填完整性（画布角标/校验面板/保存闸门/弹窗确认闸门共用判定） */
  const missingLabels = computed(() =>
    node.value && schema.value ? requiredMissing(schema.value, node.value.data) : [])

  /** number 输入转数值存储（保持 data 类型契约） */
  function upd(key: string, ev: Event) {
    if (!node.value) return
    const t = ev.target as HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement
    if (t instanceof HTMLInputElement && t.type === 'number' && t.value !== '') {
      const n = Number(t.value)
      if (Number.isFinite(n)) {
        node.value.data[key] = n
        return
      }
    }
    node.value.data[key] = t.value
  }
  /** select/bool 值变更：写值 + 联动分发——M-B2 迁移组件按 conditions 声明清空随之隐藏的目标字段，旧组件走 onChange 函数钩子 */
  function onSet(f: FieldSchema, ev: Event) {
    upd(f.key, ev)
    if (!node.value) return
    const s = schema.value
    if (s?.conditions?.length) clearOnConditionHide(s, node.value.data, f.key)
    if (f.onChange) f.onChange(node.value.data, node.value.data[f.key])
  }

  /* ================= 共享候选状态（节点无关；弹窗与 Inspector 消费同一份缓存） ================= */
  const dsRows = ref<DsRow[]>([])
  const scripts = ref<Script[]>([])
  const runtimeNodes = ref<RuntimeNodeOpt[]>([])
  const sshNodes = ref<{ id: number; tags: string[] }[]>([])
  const tagOptions = computed(() => {
    const seen = new Set<string>()
    for (const n of sshNodes.value) for (const t of n.tags) if (t.trim()) seen.add(t.trim())
    return [...seen]
  })

  /** 已注册变量候选（F2 数据驱动三源组装）：引擎注入变量 + 内置时间参数 14 项（镜像 vars_render.py，
     常驻基线）+ API 全局参数（t_global_param）+ 工作流变量。远端两源并联拉取、任一失败降级保留其余。
     F3 分域口径：RUN_VARS→workflow-vars 域、TIME_PARAMS→time-params 域（varOptions 为合并全量，供变量引用弹窗） */
  const RUN_VARS = ['run.instanceId', 'run.loopIter']
  const TIME_PARAMS = builtinVars().map((b) => b.name)
  const BUILTIN_VARS = [...RUN_VARS, ...TIME_PARAMS]
  const varOptions = ref<string[]>([...BUILTIN_VARS])
  const remoteVars = ref<string[]>([])
  watch(() => graphStore.doc?.id, async (wf) => {
    if (!wf) return
    const [gp, wfv] = await Promise.allSettled([listGlobalParams(), listVariables(wf)])
    const names = [
      ...(gp.status === 'fulfilled' ? gp.value : []),
      ...(wfv.status === 'fulfilled' ? wfv.value : []),
    ].map((r) => String(r.name ?? '').trim()).filter(Boolean)
    const seen = new Set(BUILTIN_VARS)
    const extra: string[] = []
    for (const n of names) if (!seen.has(n)) { seen.add(n); extra.push(n) }
    remoteVars.value = extra
    varOptions.value = [...BUILTIN_VARS, ...extra]
  }, { immediate: true })

  /** F3 数据驱动值域上下文（dataScope 字段候选唯一来源）：resolveDataContext 接线，弹窗/Inspector 同源。
   *  - upstreamSchemas 由上方「上游②输出登记 + 上游 dataScope 声明」供给，弹窗虚拟节点同样可得上游列/表域
   *  - doc 口径：弹窗虚拟节点不在 doc 中 → 用 upstreamOverride 合成入边（id 复用上游真实 id，
   *    upstreamSchemas 键同源）使 BFS 拿到与落画布后等价的上游可达集 */
  const dataCtx = computed<DataContext>(() => {
    const doc = graphStore.doc ?? { nodes: [], edges: [] }
    const nid = node.value?.id ?? ''
    const ov = host.upstreamOverride?.value
    const effDoc = ov && ov.length
      ? {
          nodes: [...doc.nodes, ...(node.value && !doc.nodes.some((n) => n.id === nid) ? [node.value] : [])],
          edges: [
            ...doc.edges,
            ...ov.map((u) => ({ id: `${u.id}->${nid}`, source: u.id, target: nid })),
          ],
        }
      : doc
    return resolveDataContext(effDoc, nid, {
      upstreamSchemas: upstreamSchemas.value,
      vars: [...RUN_VARS, ...remoteVars.value],
      timeParams: [...TIME_PARAMS],
    })
  })

  /**
   * F60 ①输入 的上游输出引用候选（`节点名.键（参数｜结果表）`）：由上游节点自己②输出登记表汇总。
   * 收敛到 ctx 后，六区块渲染、值域校验（domainViolations 悬空引用判定）共用同一份（§12.2）。
   */
  const upstreamOuts = computed<string[]>(() => upstream.value.flatMap((u) => {
    const out = u.data.outputs as { params?: { k?: string }[]; tables?: { k?: string }[] } | undefined
    const name = String(u.data.name ?? u.id)
    return [
      ...((out?.params ?? []).filter((p) => p?.k).map((p) => `${name}.${p.k}（参数）`)),
      ...((out?.tables ?? []).filter((t) => t?.k).map((t) => `${name}.${t.k}（结果表）`)),
    ]
  }))

  /** 库表树缓存（ds 名 → 树；table/column/insert/map/probe 派生共用一次请求） */
  const pickTrees = ref<Record<string, DsTree>>({})
  const pickTreeErr = ref<Record<string, string>>({})
  const pickTreeBusy = ref<Record<string, boolean>>({})
  const topicOpts = ref<Record<string, string[]>>({})
  const topicErr = ref<Record<string, string>>({})
  const topicBusy = ref<Record<string, boolean>>({})
  /** 目录浏览导航状态（字段 key → 导航；节点/依赖切换时整体重置） */
  const dirNavs = ref<Record<string, DirNav>>({})

  function pickErrMsg(e: unknown): string {
    return e instanceof Error ? e.message : String(e)
  }

  async function ensureTree(dsName: string): Promise<DsTree | null> {
    const hit = pickTrees.value[dsName]
    if (hit) return hit
    const id = resolveDsId(dsName, dsRows.value)
    if (id == null) {
      if (dsName) pickTreeErr.value[dsName] = `数据源「${dsName}」未加载或已删除`
      return null
    }
    if (pickTreeBusy.value[dsName]) return null
    pickTreeBusy.value[dsName] = true
    pickTreeErr.value[dsName] = ''
    try {
      const t = await getDataSourceTree(id)
      pickTrees.value[dsName] = t
      return t
    } catch (e) {
      pickTreeErr.value[dsName] = `库表加载失败：${pickErrMsg(e)}`
      return null
    } finally {
      pickTreeBusy.value[dsName] = false
    }
  }

  async function ensureTopics(dsName: string, force = false): Promise<void> {
    if (!dsName) return
    if (!force && (topicOpts.value[dsName] || topicBusy.value[dsName])) return
    const id = resolveDsId(dsName, dsRows.value)
    if (id == null) {
      topicOpts.value[dsName] = []
      topicErr.value[dsName] = `流源「${dsName}」未加载或已删除`
      return
    }
    if (topicBusy.value[dsName]) return
    topicBusy.value[dsName] = true
    topicErr.value[dsName] = ''
    try {
      topicOpts.value[dsName] = await listKafkaTopics(id)
    } catch (e) {
      delete topicOpts.value[dsName]
      topicErr.value[dsName] = `topic 枚举失败：${pickErrMsg(e)}`
    } finally {
      topicBusy.value[dsName] = false
    }
  }

  /** 目录浏览懒加载：seq 防护（乱序/孤儿响应一律丢弃） */
  let dirSeq = 0
  async function lsDir(fKey: string, nodeId: number | string, path: string): Promise<void> {
    const st: DirNav = dirNavs.value[fKey] ?? { path: '', dirs: [], err: '', seq: 0 }
    dirNavs.value[fKey] = st
    const mySeq = ++dirSeq
    st.seq = mySeq
    const stale = () => dirNavs.value[fKey] !== st || st.seq !== mySeq
    try {
      const r = await listNodeDir(nodeId, path)
      if (stale()) return
      st.path = r.path
      st.dirs = r.entries.filter((e) => e.dir).map((e) => ({ name: e.name }))
      st.err = ''
    } catch (e) {
      if (stale()) return
      st.dirs = []
      st.err = `目录浏览失败：${pickErrMsg(e)}`
    }
  }

  function dirNodeIdOf(f: FieldSchema): number | string | null {
    const nodeName = String(nodeData()[pickCfg(f).nodeKey] ?? '')
    if (!nodeName) return null
    const hit = runtimeNodes.value.find((r) => r.name === nodeName)
    return hit ? hit.id : null
  }

  /* ================= C37 探测联动派生态（endpoint_select 特化渲染门） ================= */
  /** 目标表名归一：tgtTable 由 table-picker writeAs:'schemaTable' 写回对象，兼容纯表名字符串 */
  function epTgtTableName(v: unknown): string {
    if (v && typeof v === 'object') return String((v as { table?: unknown }).table ?? '')
    return String(v ?? '')
  }
  const epProbeState = computed<EpProbeState | null>(() => {
    if (node.value?.type !== 'endpoint_select') return null
    const d = nodeData()
    if (String(d.baseMode ?? 'src_base') !== 'tgt_base' || d.probe !== true) return null
    const srcDs = String(d.srcDs ?? '')
    const tgtName = epTgtTableName(d.tgtTable)
    const matchType = String(d.matchType ?? 'exact')
    const matchPrefix = String(d.matchPrefix ?? '')
    const pattern = matchType === 'prefix' ? matchPrefix || tgtName : tgtName
    const tree = srcDs ? pickTrees.value[srcDs] ?? null : null
    const treeMap: Record<string, string[]> = {}
    if (tree?.kind === 'connection') {
      for (const db of tree.databases) treeMap[db.name] = db.tables.map((t) => t.name)
    }
    return {
      loading: !!pickTreeBusy.value[srcDs],
      err: pickTreeErr.value[srcDs] ?? '',
      noTgt: !pattern,
      hits: pattern ? probeMatchTables(treeMap, tgtName, matchType, matchPrefix) : [],
      checked: String(d.probeResult ?? '').split(',').map((s) => s.trim()).filter(Boolean),
    }
  })

  /* ================= 按需拉取动态候选（弹窗/Inspector 同一实现，签名 watch 驱动） ================= */
  function syncDynamicOptions(): void {
    const d = nodeData()
    if (epProbeState.value) {
      const dsName = String(d.srcDs ?? '')
      if (dsName) void ensureTree(dsName)
    }
    for (const f of visibleForm.value) {
      if ((f.type === 'resource' && f.cap?.mode === 'table') || (f.type === 'mapEditor' && f.mapMode === 'insert')) {
        const dsName = String(d[pickCfg(f).dsKey] ?? '')
        if (dsName) void ensureTree(dsName)
      } else if (f.type === 'resource' && f.cap?.mode === 'column') {
        if (f.cap.src === 'upstream') {
          const up = sortByCanvasX(upstream.value)[f.cap.upstreamIndex ?? 0]
          const dsName = String(up?.data.cdcDs ?? '')
          if (dsName) void ensureTree(dsName)
        } else {
          const dsName = String(d[pickCfg(f).dsKey] ?? '')
          if (dsName) void ensureTree(dsName)
        }
      } else if (f.type === 'resource' && f.cap?.mode === 'topic') {
        void ensureTopics(String(d[pickCfg(f).dsKey] ?? ''))
      } else if (f.type === 'resource' && f.cap?.mode === 'dir') {
        const id = dirNodeIdOf(f)
        if (id != null && !dirNavs.value[f.key]) void lsDir(f.key, id, '')
      }
    }
  }

  watch(
    () => [
      node.value?.id ?? '',
      dsRows.value.length,
      runtimeNodes.value.length,
      epProbeState.value ? String(nodeData().srcDs ?? '') : '',
      ...visibleForm.value.flatMap((f) => {
        const d = nodeData()
        if (f.type === 'resource' && f.cap?.mode === 'column' && f.cap.src === 'upstream') {
          const up = sortByCanvasX(upstream.value)[f.cap.upstreamIndex ?? 0]
          return [String(up?.data.cdcDs ?? ''), String(up?.data.tablesText ?? '')]
        }
        if ((f.type === 'resource' && (f.cap?.mode === 'table' || f.cap?.mode === 'column' || f.cap?.mode === 'topic')) || (f.type === 'mapEditor' && f.mapMode === 'insert')) {
          return [String(d[pickCfg(f).dsKey] ?? '')]
        }
        if (f.type === 'resource' && f.cap?.mode === 'dir') return ['@' + String(d[pickCfg(f).nodeKey] ?? '')]
        return []
      }),
    ].join('\u0000'),
    () => {
      dirNavs.value = {} // 导航状态整体重置（及时释放旧节点残留）
      syncDynamicOptions()
    },
    { immediate: true },
  )

  /* ================= 共享候选拉载（Inspector onMounted / 弹窗挂载时调用，幂等） ================= */
  async function loadShared(): Promise<void> {
    // 必须展开为新数组：dataStore 内部数组原地修改，直接赋值不会触发 ref 更新（对齐 ScriptListView）
    scripts.value = [...((await dataStore.list<Script>('scripts')) ?? [])]
    try {
      runtimeNodes.value = isMock
        ? ((await dataStore.list<RuntimeNodeOpt>('runtimeNodes')) ?? [])
        : (await listRuntimeNodes()).map((r) => ({ id: r.id, name: r.name, host: r.host, port: r.port }))
    } catch { /* real 后端未就绪时下拉留空，不阻断表单 */ }
    try {
      sshNodes.value = isMock
        ? ((await dataStore.list<{ id: number; tags: string[] }>('sshNodes')) ?? [])
        : (await listSshNodes()).map((r) => ({ id: r.id, tags: r.tags }))
    } catch { /* SSH 节点未就绪时标签下拉留空，不阻断表单 */ }
    try {
      dsRows.value = isMock
        /* id 必须取种子真 id（DS001…）：库表树按 id 取，覆写成数组下标会让 resolveDsId 拿到错 id */
        ? ((await dataStore.list<{ id?: string | number; name: string; type: string }>('datasources')) ?? []).map((r, i) => ({
            id: r.id ?? i, name: r.name, type: r.type, host: null, port: null, db: null, user: null,
            pwd: '', env: null, group: null, tags: [], params: null, status: null,
            owner: '', createdAt: '', updateTime: '',
          }) as DsRow)
        : await listDataSources()
    } catch { /* 数据源中心未就绪时下拉留空，不阻断表单 */ }
    /* 上游选定表的树预载：值域域（upstream-tables/columns）依赖它，否则两域结构性为空 */
    await ensureUpstreamTrees()
  }

  /* ================= 脚本库互通（language 字段；作用于目标节点 data） ================= */
  /** 当前用户（F56d：取 auth store 登录账号，mock 演示态回退 current 身份） */
  const userName = computed(() => auth.account?.name ?? auth.current.name)

  function selectedScript(): Script | null {
    const sid = node.value ? String(node.value.data.scriptId ?? '') : ''
    if (!sid) {
      ElMessage.warning('未引用脚本库脚本，请先选择或「另存为新脚本」')
      return null
    }
    const s = scripts.value.find((x) => x.id === sid) ?? null
    if (!s) ElMessage.warning(`脚本库中未找到 ${sid}（可能已被删除）`)
    return s
  }
  function loadScriptCode() {
    if (!node.value) return
    const s = selectedScript()
    if (!s) return
    node.value.data.code = s.code
    node.value.data.lang = s.lang
    ElMessage.success('已载入脚本库代码')
  }
  async function saveToScript() {
    if (!node.value) return
    const s = selectedScript()
    if (!s) return
    s.code = String(node.value.data.code ?? '')
    s.lang = String(node.value.data.lang ?? '') || s.lang
    s.updated = localTime()
    await dataStore.save('scripts', s)
    const i = scripts.value.findIndex((x) => x.id === s.id)
    if (i >= 0) scripts.value.splice(i, 1, { ...s }) // 替换引用触发本地列表更新
    ElMessage.success(`已保存至脚本库（${s.id}）`)
  }
  async function saveAsNewScript() {
    if (!node.value) return
    const nextSeq = scripts.value.reduce((m, s) => {
      const n = Number(String(s.id).replace(/^\D+/, ''))
      return Number.isFinite(n) && n > m ? n : m
    }, 0) + 1
    const row: Script = {
      id: 'SC' + String(nextSeq).padStart(3, '0'),
      name: String(node.value.data.name ?? '') || '脚本节点',
      lang: String(node.value.data.lang ?? '') || 'SQL',
      status: 'draft',
      owner: userName.value,
      updated: localTime().slice(0, 10),
      code: String(node.value.data.code ?? ''),
    }
    scripts.value.push(row)
    await dataStore.save('scripts', row)
    node.value.data.scriptId = row.id
    ElMessage.success('已保存至脚本库')
  }

  /* ================= token-insert 插入点聚焦（I12 评审修） ================= */
  function focusTarget(key: string) {
    void nextTick(() => {
      const el = host.rootEl.value?.querySelector<HTMLTextAreaElement>(`textarea[data-fkey="${key}"]`)
      if (!el) return
      el.focus()
      const end = el.value.length
      el.setSelectionRange(end, end)
    })
  }

  const ctx: FieldCtx = {
    upstream, upSchema, upstreamOpts, upstreamOuts, epProbe: epProbeState,
    dsRows, scripts, runtimeNodes, tagOptions, varOptions, dataCtx,
    pickTrees, pickTreeErr, pickTreeBusy,
    topicOpts, topicErr, topicBusy, dirNavs,
    ensureTree, ensureTopics, lsDir, loadScriptCode, saveToScript, saveAsNewScript,
    markDirty: host.markDirty, schema,
  }

  return { ctx, schema, visibleForm, missingLabels, onSet, upd, varOptions, dataCtx, upstreamOuts, loadShared, ensureUpstreamTrees, focusTarget }
}
