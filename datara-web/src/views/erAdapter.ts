/**
 * I18 Task 13b：ER 画布真实联调适配器。
 * real 模式下由 ErCanvasView 壳层安装：把 graphStore.load/save 接管到 /models/er
 * （ViewProfile 契约无 load/save 扩展点，故在壳层以动作替换方式接入，不改 GraphWorkbench 共享基建）；
 * mock 模式不安装本适配器，原 dataStore 种子路径完全不变。
 * - load：GET /models/er → GraphDocument（实体节点=模型，边=模型关系）；
 *   erPos 缺失的节点按 ER 分层列布局补位，已有 erPos 的保持服务端坐标。
 * - save：对 load 基线做 diff，单次 PUT /models/er（positions 变更集 + relations added/updated/removed）；
 *   成功后全量重载（新建边获得后端数字 id，防二次保存重复落库；重载失败退回发送时刻快照基线）。
 */
import { ElMessage } from 'element-plus'
import type { GEdge, GEdgeKind, GNode, GraphDocument } from '../graph/model'
import { erGridLayout } from '../graph/layout/er'
import { erProfile } from '../graph/profiles'
import { getEr, saveEr, type ErEdge, type ErResp } from '../services/modelApi'
import type { useGraphStore } from '../stores/graph'

type GraphStore = ReturnType<typeof useGraphStore>

const ER_DOC_ID = 'er_dw'

/** 后端关系基数 ↔ 画布边 kind（rel_type 取值域：1:1/1:N/N:1/M:N，历史 N:N 归并 M:N） */
const REL_TO_KIND: Record<string, GEdgeKind> = {
  '1:N': 'rel_1n', 'N:1': 'rel_n1', '1:1': 'rel_11', 'M:N': 'rel_nm', 'N:N': 'rel_nm',
}
const KIND_TO_REL: Record<string, string> = {
  rel_1n: '1:N', rel_n1: 'N:1', rel_11: '1:1', rel_nm: 'M:N',
}

/** 后端模型/关系 id 为整数；画布新建边 id 为 uid('e') 非数字串，以此区分新增关系 */
const NUM_ID = /^\d+$/

interface RelSnap {
  source: string
  target: string
  relType: string
}

interface ErBaseline {
  positions: Map<string, { x: number; y: number }>
  relations: Map<string, RelSnap>
}

/* 基线与代际为模块级单例：/model/er 单页单画布，重进页面 install 时整体重置 */
let baseline: ErBaseline | null = null
let loadGen = 0

/** 边标注：基数 + 关联字段 + 关联描述（GEdge 无自由 data 槽，label 为 profile 现有最小承载） */
function edgeLabel(e: ErEdge): string {
  const parts = [e.relType || '1:N']
  if (e.srcFields && e.tgtFields) parts.push(`${e.srcFields} → ${e.tgtFields}`)
  if (e.joinDesc) parts.push(e.joinDesc)
  return parts.join(' · ')
}

/** ErResp → GraphDocument：实体卡类型按分层映射（未知分层回退 ent_ods 渲染骨架） */
export function buildErDoc(resp: ErResp): GraphDocument {
  const noPos = new Set<string>()
  const nodes: GNode[] = resp.nodes.map((n) => {
    const layer = (n.model.layer || 'ODS').toUpperCase()
    const type = `ent_${layer.toLowerCase()}`
    const ex = n.erPos?.x
    const ey = n.erPos?.y
    const hasPos = typeof ex === 'number' && typeof ey === 'number'
    if (!hasPos) noPos.add(n.id)
    return {
      id: n.id,
      type: erProfile.nodeTypes[type] ? type : 'ent_ods',
      position: hasPos ? { x: ex as number, y: ey as number } : { x: 0, y: 0 },
      data: {
        name: n.model.code || n.model.name || n.id,
        layer,
        domain: n.model.bizDomain || '',
        comment: n.model.name || '',
        /* /models/er 不返回字段清单（按模型逐个拉取属 N+1，禁），实体卡字段区留空 */
        fields: [],
      },
    }
  })
  const edges: GEdge[] = resp.edges.map((e) => ({
    id: String(e.id),
    source: e.source,
    target: e.target,
    kind: REL_TO_KIND[e.relType] ?? 'rel_1n',
    label: edgeLabel(e),
  }))
  /* erPos 缺失节点交给 ER 分层列布局补位（仅缺位子图，不覆盖服务端已存坐标） */
  if (noPos.size) {
    const laid = erGridLayout(
      { id: ER_DOC_ID, name: '', version: 1, meta: { profile: 'er' }, nodes: nodes.filter((n) => noPos.has(n.id)), edges: [] },
      {},
    )
    const posMap = new Map(laid.nodes.map((n) => [n.id, n.position]))
    nodes.forEach((n) => {
      const p = posMap.get(n.id)
      if (p) n.position = p
    })
  }
  return {
    id: ER_DOC_ID,
    name: '数仓模型 ER 关系图',
    version: 1,
    meta: { profile: 'er', updatedAt: new Date().toISOString() },
    nodes,
    edges,
  }
}

function snapBaseline(doc: GraphDocument): ErBaseline {
  const positions = new Map<string, { x: number; y: number }>()
  doc.nodes.forEach((n) => {
    if (NUM_ID.test(n.id)) positions.set(n.id, { x: n.position.x, y: n.position.y })
  })
  const relations = new Map<string, RelSnap>()
  doc.edges.forEach((e) => {
    if (NUM_ID.test(e.id)) relations.set(e.id, { source: e.source, target: e.target, relType: KIND_TO_REL[e.kind ?? 'rel_1n'] ?? '1:N' })
  })
  return { positions, relations }
}

/** graphStore.load 接管：拉真实 ER 数据落 store（失败 toast 用户可见 + 不落档，画布保持空态可重试） */
async function loadErIntoStore(store: GraphStore): Promise<boolean> {
  const gen = ++loadGen
  try {
    const resp = await getEr()
    if (gen !== loadGen) return false // 代际守卫：重进页面/卸载后迟到的旧响应丢弃
    const doc = buildErDoc(resp)
    baseline = snapBaseline(doc)
    store.doc = doc
    store.dirty = false
    store.resetHistory()
    return true
  } catch (e) {
    if (gen !== loadGen) return false
    ElMessage.error('ER 模型加载失败：' + (e instanceof Error ? e.message : String(e)))
    return false
  }
}

/** graphStore.save 接管：diff 基线单次 PUT /models/er（positions 变更集 + relations 增/改/删） */
async function saveErFromStore(store: GraphStore): Promise<number> {
  const doc = store.doc
  if (!doc) return 0
  const base = baseline ?? { positions: new Map<string, { x: number; y: number }>(), relations: new Map<string, RelSnap>() }
  /* 发送时刻快照：PUT 整体提交成功 ⇒ 服务端终态=快照（重载失败回退路径的基线依据） */
  const positions: Record<string, { x: number; y: number }> = {}
  const sentPos = new Map(base.positions)
  doc.nodes.forEach((n) => {
    if (!NUM_ID.test(n.id)) return // 画布拖入的占位实体无后端模型对应，跳过持久化
    const prev = base.positions.get(n.id)
    if (!prev || prev.x !== n.position.x || prev.y !== n.position.y) {
      positions[n.id] = { x: n.position.x, y: n.position.y }
      sentPos.set(n.id, positions[n.id]!)
    }
  })
  const added: Record<string, unknown>[] = []
  const updated: Record<string, unknown>[] = []
  const removed: number[] = []
  const sentRel = new Map<string, RelSnap>()
  doc.edges.forEach((e) => {
    if (!NUM_ID.test(e.source) || !NUM_ID.test(e.target)) return
    const relType = KIND_TO_REL[e.kind ?? 'rel_1n'] ?? '1:N'
    sentRel.set(e.id, { source: e.source, target: e.target, relType })
    if (!NUM_ID.test(e.id)) added.push({ source: Number(e.source), target: Number(e.target), relType })
    else if (base.relations.get(e.id)?.relType !== relType) updated.push({ id: Number(e.id), relType })
  })
  /* P2 兜底：removed 一律过 NUM_ID 过滤（uid 边进基线后被删 → Number(uid)=NaN → JSON null → 后端 int(None) 500） */
  base.relations.forEach((_rel, id) => {
    if (NUM_ID.test(id) && !sentRel.has(id)) removed.push(Number(id))
  })
  store.saving = true
  try {
    await saveEr({ positions, relations: { added, updated, removed } })
    /* P1：保存成功后全量重载——新建边获得后端数字 id（否则 doc 不重载，该边下次 save 仍命中 added
       重复落库）；基线与画布同刷为服务端已存态，后续 diff 永远以真实服务端态为基。
       取舍：保存 await 期间的未保存画布改动被重载覆盖（保存成功即最新已保存态，窗口毫秒级，
       且 saving 旗标挡住并发保存；语义可预期，优于维护脆弱的 uid↔数字 id 映射回写）。 */
    try {
      const fresh = buildErDoc(await getEr())
      baseline = snapBaseline(fresh)
      store.doc = fresh
      store.dirty = false
      store.resetHistory()
    } catch {
      /* 重载失败：保存本身已成功，退回发送时刻快照基线（P2 过滤兜底下行为仍正确） */
      baseline = { positions: sentPos, relations: sentRel }
      store.dirty = false
      store.lastSnap = JSON.stringify(store.doc)
      store.lastDoc = JSON.parse(store.lastSnap)
      ElMessage.warning('已保存，但画布数据重载失败，请手动刷新')
    }
    return doc.version
  } finally {
    store.saving = false
  }
}

/**
 * ErCanvasView 壳层安装（仅 real 模式调用）：替换 graphStore.load/save 为 ER 适配实现，
 * 返回恢复函数（视图卸载时还原，/dag 等其他 GraphWorkbench 使用方语义零影响）。
 */
export function installErAdapter(store: GraphStore): () => void {
  const origLoad = store.load
  const origSave = store.save
  loadGen++ // 使此前在途响应失效
  baseline = null
  store.load = async (id: string) => (id === ER_DOC_ID ? loadErIntoStore(store) : origLoad(id))
  store.save = () => saveErFromStore(store)
  return () => {
    loadGen++
    store.load = origLoad
    store.save = origSave
  }
}
