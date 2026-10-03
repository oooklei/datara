/**
 * I4 表单联动纯函数（§9）：C22 来源模式切换清空对方参数 + ${tmp.*} 前端侧引用提示。
 * 与组件解耦（不引 .vue），供 dag.ts 表单 schema 与 vitest 直接复用；
 * TMP_NAME_OK 对齐 worker 侧 common/tmpdata.TMP_NAME_RE（^[a-z][a-z0-9_]{2,31}$）。
 * 同步编排端点合一扩展（设计 §3.1/§3.3）：拖边即引用（onEdgeCreated/onEdgeRemoved）+ 目标表基准探测（probeMatchTables）。
 * M-B2 八段 DSL 迁移收口（运行时消费真源）：conditions 显隐（condVisible）/ 条件清空（clearOnConditionHide）/
 * 副标题模板（renderSummary）——旧 showIf/onChange/summary 函数的声明化求值，旧函数双轨保留（未迁移组件不受影响）。
 */
import type { ConditionDef, DataScope, FieldSchema, NodeSchema } from './types'

/** 临时数据名合法规则（与后端 TMP_NAME_RE 同口径） */
export const TMP_NAME_OK = /^[a-z][a-z0-9_]{2,31}$/

/* ================= 八段 DSL conditions 求值（M-B2 迁移收口：showIf/onChange/summary 函数 → 声明求值） ================= */

/** 单条 when 是否满足（op 口径对齐 baselineSpec.SPEC_OPS 与 dag.ts 迁移声明：eq/ne/notEq/in/notIn/empty/notEmpty/gt/lt；未知 op 恒 false） */
function whenMet(when: ConditionDef['when'], d: Record<string, unknown>): boolean {
  const v = d[when.field]
  const empty = v === undefined || v === null || String(v) === ''
  switch (when.op) {
    case 'eq': return v === when.value
    case 'ne':
    case 'notEq': return v !== when.value
    case 'in': return Array.isArray(when.value) && (when.value as unknown[]).includes(v)
    case 'notIn': return Array.isArray(when.value) && !(when.value as unknown[]).includes(v)
    case 'empty': return empty
    case 'notEmpty': return !empty
    case 'gt':
    case 'lt': {
      const a = Number(v)
      const b = Number(when.value)
      return Number.isFinite(a) && Number.isFinite(b) && (when.op === 'gt' ? a > b : a < b)
    }
    default: return false
  }
}

/**
 * 按 conditions 段求值字段可见性：同字段被多条条件引用时取 AND 交集（与迁移前多条件 showIf 复合语义一致），
 * 未被任何条件引用的字段恒显示。M-B2 迁移组件（sql/ssh/http/file/assert/notify 等）的显隐真源。
 */
export function condVisible(conditions: ConditionDef[] | undefined, key: string, d: Record<string, unknown>): boolean {
  if (!conditions?.length) return true
  for (const c of conditions) {
    if (c.show.includes(key) && !whenMet(c.when, d)) return false
  }
  return true
}

/**
 * 条件联动清空（M-B2：onChange 函数 → conditions 声明求值）：字段写入后，以该字段为 when 轴的条件失满足
 * （其 show 目标字段随之隐藏）→ 清空目标字段存量值，防隐藏残留值静默参与校验/执行。
 * 清空口径对齐 c22OnModeChange：bool 字段清为 false，其余清为 ''；联动钩子挂在分型轴字段上，仅轴字段变化时触发。
 */
export function clearOnConditionHide(schema: NodeSchema, data: Record<string, unknown>, changedKey: string): void {
  const conds = schema.conditions
  if (!conds?.length) return
  const boolKeys = new Set<string>()
  for (const f of schema.form ?? []) if (f.type === 'bool') boolKeys.add(f.key)
  for (const c of conds) {
    if (c.when.field !== changedKey || whenMet(c.when, data)) continue
    for (const k of c.show) data[k] = boolKeys.has(k) ? false : ''
  }
}

/** ${key} 模板插值正则（module 级复用，避免逐节点重复编译） */
const SUMMARY_TPL_RE = /\$\{([^}]+)\}/g

/**
 * 节点副标题渲染（M-B2 决策 2：summary 函数 → render.summaryRules 分型模板声明化）：
 * 1) render.summaryRules 按声明序取第一条命中（when 满足，或 when=null/缺省 兜底）的 template，
 *    ${key} 以节点 data 同名值插值（缺失置空）；
 * 2) 无规则/无命中 → render.summary 常量兜底（M-B2 迁移组件的通用文案）；
 * 3) 再回退旧 schema.summary（字符串原样 / 函数求值）——未迁移组件行为不变。
 */
export function renderSummary(schema: Pick<NodeSchema, 'summary' | 'render'>, data: Record<string, unknown>): string {
  const rules = schema.render?.summaryRules
  if (rules?.length) {
    for (const r of rules) {
      if (!r.template) continue
      if (r.when == null || whenMet(r.when, data)) {
        return r.template.replace(SUMMARY_TPL_RE, (_m, k: string) => {
          const v = data[k.trim()]
          return v === undefined || v === null ? '' : String(v)
        })
      }
    }
  }
  const rs = schema.render?.summary
  if (typeof rs === 'string' && rs) return rs
  const s = schema.summary
  if (!s) return ''
  return typeof s === 'function' ? s(data) : s
}

/* ================= F1 configure-first 拖入闸门（治理设计 §11/§12，纯函数供单测） ================= */

/** 拖入裁决（§12.1 三段式）：intercept = 直接 toast 不弹窗；dialog = 必弹配置弹窗 */
export type DropDecision =
  | { action: 'intercept'; reason: string }
  | { action: 'dialog' }

/**
 * 拖入前置裁决：maxInstances 超限 / 灰置或运行态组件拦截；其余一律弹配置弹窗。
 * - 灰置（palette disabled）与 runtimeOnly 组件正常拖不进来，此处为防御层（dataTransfer 伪造）
 * - template 组件由调用点先行分流（模式物化弹窗，F63 既有链路），不经此裁决
 * - **不再有 direct-add 旁路**：`form: []`（C1/C2/C6/C7「无业务表单，仅六区块」）不代表无配置面——
 *   六区块（①输入 ②输出 ③参数 ④条件 ⑤限定约束 ⑥排除）是框架级必填配置面，
 *   绕过弹窗即产生无②输出/无③参数的裸节点，违反「每个组件必编表单模板」与数据驱动原则。
 */
export function decideDrop(
  schema: NodeSchema,
  opts: { sameTypeCount: number; paletteDisabled?: boolean },
): DropDecision {
  if (opts.paletteDisabled || schema.runtimeOnly) {
    return { action: 'intercept', reason: `「${schema.label}」当前不可用（灰置或运行态组件），无法拖入画布` }
  }
  const max = schema.dropPolicy?.maxInstances ?? 0
  if (max > 0 && opts.sameTypeCount >= max) {
    return { action: 'intercept', reason: `「${schema.label}」单个工作流最多 ${max} 个实例（当前已有 ${opts.sameTypeCount} 个），已拒绝拖入` }
  }
  return { action: 'dialog' }
}

/**
 * M5 组件 initTemplate 落图消费（页面设计器 Task 14 的 UI 消费点）：拖入设计器时把组件创作的
 * 单节点默认形态 props 浅合入节点 data（types.ComponentInitTemplate：「拖入设计器的单节点默认形态」）。
 * 落图默认值优先级链（低 → 高）：defaults（通用默认）< initTemplate.props（组件创作模板，更具体）
 * < prefillFromUpstream（上游快照，最具体）——本函数只承载前两级，调用点先以 defaults 构造初始 data，
 * 经本函数合入模板后，再交 prefillFromUpstream 应用上游快照完成整链。
 * 纯函数：浅合并、不修改传入 data（恒返回新对象）；initTemplate 缺省时返回等价副本（行为零变化）。
 * 与 F63 template（聚合多节点链展开，含 build 函数）正交：模板组件在 onDrop 先行 materializeTemplate
 * 分流，不进入本链路。
 */
export function applyInitTemplate(data: Record<string, unknown>, schema: NodeSchema): Record<string, unknown> {
  return { ...data, ...schema.initTemplate?.props }
}

/**
 * prefillFromUpstream 快照预填（§11）：取逻辑上游节点 data 中同名**非空**值写入本节点 data。
 * - 快照语义：drop 时一次性取值，之后上游变化不回写（与 Inspector pick 实时联动划界）
 * - 上游值与 defaults 同为空时保持 defaults；上游非空才覆盖（''/null/undefined/空数组视为空）
 * - 键不存在于上游 data 时不写（保留 defaults 原值）
 */
export function prefillFromUpstream(
  data: Record<string, unknown>,
  upData: Record<string, unknown> | null | undefined,
  keys: string[] | undefined,
): void {
  if (!upData || !keys?.length) return
  for (const k of keys) {
    const v = upData[k]
    if (Array.isArray(v)) { if (v.length) data[k] = [...v]; continue }
    if (v === undefined || v === null || v === '') continue
    data[k] = v
  }
}

/**
 * C22 来源模式切换联动：清空对方侧参数（设计 §9 表单控件联动）。
 * - 切到 manual（手动参数）→ 清空数据源引用
 * - 切到 datasource（数据源中心文件源）→ 清空路径/格式/编码/分隔符/表头/sheet
 */
export function c22OnModeChange(data: Record<string, unknown>, mode: unknown): void {
  if (mode === 'manual') {
    data.datasource = ''
  } else {
    data.path = ''
    data.format = ''
    data.encoding = ''
    data.delimiter = ''
    data.header = false
    data.sheet = ''
  }
}

/** ${tmp.<name>} 引用是否可用：已勾选注册且命名合法（键为 tmpName，避免与节点显示名 data.name 冲突） */
export function tmpRefUsable(data: Record<string, unknown>): boolean {
  return !!data.register && TMP_NAME_OK.test(String(data.tmpName ?? ''))
}

/** ${tmp.*} 引用提示文案：可用返回空串，否则给出不可用原因 */
export function tmpRefHint(data: Record<string, unknown>): string {
  if (!data.register) return '未注册临时数据：下游 ${tmp.*} 引用不可用，仅产出行数统计'
  const name = String(data.tmpName ?? '')
  if (!TMP_NAME_OK.test(name)) return '临时数据名未配置或不合法（需小写字母开头，3~32 位 a-z0-9_）：${tmp.*} 引用暂不可用'
  return ''
}

/**
 * 必填完整性检查（W1 流节点配置闭环）：返回当前分型下缺失的必填字段 label 清单。
 * 判定口径：required 且当前可见且值为空（''/null/undefined/空数组）。
 * 可见性双轨求值：旧 showIf 函数（未迁移组件）+ 八段 conditions 声明（M-B2 迁移组件，
 * 同字段多条条件 AND 交集）——任一侧判定隐藏即不计缺失。
 * 三处共用同一判定：画布节点「未配置」角标 / 校验面板 / Inspector 必填红星。
 */
export function requiredMissing(schema: NodeSchema, data: Record<string, unknown>): string[] {
  return (schema.form ?? [])
    .filter((f) => f.required && f.type !== 'hint'
      && (!f.showIf || f.showIf(data)) && condVisible(schema.conditions, f.key, data))
    .filter((f) => {
      const v = data[f.key]
      if (Array.isArray(v)) return v.length === 0
      return v === undefined || v === null || v === ''
    })
    .map((f) => f.label || f.key)
}

/** 值域/引用有效性违规项（F4 落地形态：configure-first 闸门与画布校验面板共用同一判定） */
export interface DomainViolation {
  /** 业务表单字段 key（f:{key} 寻址：f:{key}）或六区块 ①输入的引用串 */
  key: string
  /** 展示用标签 */
  label: string
  /** 违规原因（中文，可直接展示给用户） */
  reason: string
}

/**
 * F4 值域外 + 悬空引用校验：返回当前「不可确认/不合规」的项清单，空数组 = 合规。
 *
 * 判定口径（F4 设计）：
 *  1. 域外取值：声明了 `dataScope` 的字段，若已填值但不在该域候选集内 → 违规。
 *     - 域空时字段本身被 `dataScopeState` 禁用（不可能产生新域外值），但存量值仍按域外计，
 *       避免「禁用但留着非法值」静默通过；
 *     - 域非空时用 BFS 去重保序后的完整候选集比对（大小写敏感，与候选展示同源）。
 *  2. 悬空引用：六区块 ①输入 的引用串若不在上游 ②输出 注册表候选内 → 违规
 *     （上游节点被删或其输出被移除后，存量引用不自动清理，必须显式确认）。
 *
 * 纯函数：ctx/form/data 全由调用点注入，无 IO 无组件依赖（与 dataScopeState 同层）。
 */
export function domainViolations(
  form: FieldSchema[],
  data: Record<string, unknown>,
  ctx: DataContext,
  /** 六区块 ①输入 的存量引用串（弹窗/Inspector 从 node.data.inputs 取） */
  inputRefs: readonly string[] = [],
  /** 上游 ②输出 注册表候选（「节点名.键（类型）」，由 SixBlocks/ctx 供给） */
  upstreamOuts: readonly string[] = [],
): DomainViolation[] {
  const out: DomainViolation[] = []

  for (const f of form) {
    if (f.type === 'hint' || (!f.showIf || f.showIf(data))) {
      /* 1. 域外取值 */
      if (f.dataScope) {
        const v = data[f.key]
        const has = Array.isArray(v) ? v.length > 0 : v !== undefined && v !== null && v !== ''
        if (has) {
          const { options } = dataScopeState(ctx, f.dataScope)
          const vals = Array.isArray(v) ? v.map((x) => String(x)) : [String(v)]
          const bad = options.length ? vals.filter((x) => !options.includes(x)) : vals
          for (const b of bad) {
            out.push({
              key: `f:${f.key}`,
              label: f.label || f.key,
              reason: options.length
                ? `取值「${b}」不在 ${f.dataScope} 值域内`
                : `${f.dataScope} 值域当前无可用候选（${SCOPE_EMPTY_WHY[f.dataScope]}）`,
            })
          }
        }
      }
    }
  }

  /* 2. 悬空上游引用（仅在有上游候选可比时判定；无上游 = 起始节点，不算违规） */
  if (upstreamOuts.length) {
    const valid = new Set(upstreamOuts)
    for (const r of inputRefs) {
      if (!valid.has(r)) {
        out.push({ key: `i:${r}`, label: r, reason: '引用已失效：上游节点已删除或该输出已被移除' })
      }
    }
  }

  return out
}

/** 拖边填充所用最小结构节点（与 model.GNode 结构兼容；不 import 模型层，保持纯函数可独立单测） */
export interface GNodeLike {
  id: string
  /** data 可缺省：无 inputs 字段的节点（无 upstream-refs 输入）不做联动 */
  data?: Record<string, unknown>
}

/** 拖边填充所用最小结构边（与 model.GEdge 结构兼容，仅保留引用拼接所需字段） */
export interface EdgeLike {
  source: string
  target: string
  /** 具名输出端口 id（endpoint_select 的 sourceRef/targetRef；普通连线缺省 → 引用后缀为空串） */
  sourceHandle?: string
}

/**
 * 拖边即引用（端点合一设计 §3.3）：连边 → target 节点 data.inputs 追加 `${source}:${sourceHandle ?? ''}` 引用。
 * - inputs 字段不存在（或非数组）→ 不处理（该节点无 upstream-refs 输入）
 * - 已存在同引用 → 不重复追加（includes 防重）
 * - doc.edges 暂未消费，保留形参以对齐调用点约定
 */
export function onEdgeCreated(doc: { nodes: GNodeLike[]; edges: EdgeLike[] }, edge: EdgeLike): void {
  const tgt = doc.nodes.find((n) => n.id === edge.target)
  if (!tgt || !Array.isArray(tgt.data?.inputs)) return
  const ref = `${edge.source}:${edge.sourceHandle ?? ''}`
  if (!tgt.data.inputs.includes(ref)) tgt.data.inputs.push(ref)
}

/**
 * 删边移除引用（端点合一设计 §3.3）：与 onEdgeCreated 对偶，按同一 ref 口径过滤。
 * 生成新数组赋回（保持响应式替换语义）；inputs 字段不存在（或非数组）→ 不处理。
 * doc.edges 暂未消费，保留形参以对齐调用点约定。
 */
export function onEdgeRemoved(doc: { nodes: GNodeLike[]; edges: EdgeLike[] }, edge: EdgeLike): void {
  const tgt = doc.nodes.find((n) => n.id === edge.target)
  if (!tgt || !Array.isArray(tgt.data?.inputs)) return
  const ref = `${edge.source}:${edge.sourceHandle ?? ''}`
  if (!tgt.data.inputs.includes(ref)) return
  tgt.data.inputs = tgt.data.inputs.filter((r: string) => r !== ref)
}

/**
 * 目标表基准探测（端点合一设计 §3.1）：库表树 { [schema]: string[] } 按匹配规则过滤候选 [{schema, table}]。
 * - matchType='prefix'：表名前缀匹配（matchPrefix 留空时用目标表名作为前缀）
 * - 其他（exact）：表名与目标表名完全一致
 * schema 按字典序稳定排序；tgtTable 为空串时 exact 永不命中（自然返回空候选，不需特判）。
 * matchPrefix 与 tgtTable 均空时 startsWith('') 恒真，返回全库候选（有意为之：无目标表名约束时开放全选）。
 */
export function probeMatchTables(
  tree: Record<string, string[]>, tgtTable: string, matchType: string, matchPrefix: string,
): { schema: string; table: string }[] {
  const pattern = matchType === 'prefix' ? (matchPrefix || tgtTable) : tgtTable
  const out: { schema: string; table: string }[] = []
  for (const schema of Object.keys(tree).sort()) {
    for (const t of tree[schema] ?? []) {
      if (matchType === 'prefix' ? t.startsWith(pattern) : t === pattern) out.push({ schema, table: t })
    }
  }
  return out
}

/* ================= F2 数据驱动上下文解析（实施计划 F2，纯函数供单测与 F3/F4 复用） ================= */

/** 单节点输出 schema（C17 probe 泛化提供起步；L2 后端登记服务为增强项——均由调用点注入，纯函数无 IO） */
export interface NodeOutputSchema {
  columns?: string[]
  tables?: string[]
}

/** resolveDataContext 外部输入：探测结果与变量候选由调用点组装注入 */
export interface DataContextInput {
  /** 上游节点输出 schema（nodeId → 列/表集；未登记节点跳过——F3 据此对值域字段禁用并说明原因） */
  upstreamSchemas?: Record<string, NodeOutputSchema>
  /** workflow-vars 域候选（F3 起与时间参数分域）：run.* 引擎注入 + 全局参数（t_global_param）+ 工作流变量 */
  vars?: string[]
  /** time-params 域候选：内置时间参数 14 项（镜像 vars_render.py，常驻基线） */
  timeParams?: string[]
}

/** 数据驱动值域上下文（F3 dataScope 四值域的候选来源；F4 引用有效性校验的存在域） */
export interface DataContext {
  /** 多级上游可引用列集（BFS 就近优先去重保序；空上游 → 空数组） */
  upstreamColumns: string[]
  /** 多级上游可引用表集（同上口径） */
  upstreamTables: string[]
  /** workflow-vars 域候选（去重保序） */
  vars: string[]
  /** time-params 域候选（去重保序；与 vars 分域——dataScope 声明决定消费哪一域） */
  timeParams: string[]
  /** 下游反向需求：可达下游节点 data.inputs 显式引用条目（`${source}:${handle}` 原样去重保序；消费方按 source 前缀自行区分直接/间接需求） */
  downstreamNeeds: string[]
}

/**
 * resolveDataContext 上下文解析器（数据驱动核心，实施计划 F2）：
 * 沿边递归多级上游收集可引用数据集 + 变量候选去重 + 下游反向需求收集。
 * - 多级上游：BFS 就近优先（直接上游先并入）；环安全（visited 集合，环回到已访节点即止；起点自身不算自己的上游）
 * - 空上游降级：无边 / 上游无输出 schema 登记 / 节点不存在 → 对应集合为空数组，不抛错
 * - 下游反向：对称 BFS 收集可达下游节点 data.inputs 引用条目（同为环安全；inputs 缺失的节点静默跳过）
 */
export function resolveDataContext(
  doc: { nodes: GNodeLike[]; edges: EdgeLike[] },
  nodeId: string,
  input?: DataContextInput,
): DataContext {
  const ctx: DataContext = { upstreamColumns: [], upstreamTables: [], vars: [], timeParams: [], downstreamNeeds: [] }
  const cols = new Set<string>()
  const tabs = new Set<string>()
  const vars = new Set<string>()
  const tps = new Set<string>()
  const needs = new Set<string>()

  /** 去重保序并入：跳过非数组/空串（数组浅遍历，不递归展开） */
  const merge = (set: Set<string>, out: string[], vals: unknown): void => {
    if (!Array.isArray(vals)) return
    for (const v of vals) {
      const s = String(v ?? '')
      if (s && !set.has(s)) { set.add(s); out.push(s) }
    }
  }

  merge(vars, ctx.vars, input?.vars)
  merge(tps, ctx.timeParams, input?.timeParams)

  /* 多级上游 BFS：target===cur 的 source 为上游；visited 防环且排除起点自身 */
  const upSeen = new Set<string>([nodeId])
  const upQueue = [nodeId]
  while (upQueue.length) {
    const cur = upQueue.shift()!
    for (const e of doc.edges) {
      if (e.target !== cur || upSeen.has(e.source)) continue
      upSeen.add(e.source)
      upQueue.push(e.source)
      const os = input?.upstreamSchemas?.[e.source]
      if (os) {
        merge(cols, ctx.upstreamColumns, os.columns)
        merge(tabs, ctx.upstreamTables, os.tables)
      }
    }
  }

  /* 下游反向需求 BFS：source===cur 的 target 为下游；收集其 data.inputs 引用条目 */
  const downSeen = new Set<string>([nodeId])
  const downQueue = [nodeId]
  while (downQueue.length) {
    const cur = downQueue.shift()!
    for (const e of doc.edges) {
      if (e.source !== cur || downSeen.has(e.target)) continue
      downSeen.add(e.target)
      downQueue.push(e.target)
      const dn = doc.nodes.find((n) => n.id === e.target)
      merge(needs, ctx.downstreamNeeds, dn?.data?.inputs)
    }
  }

  return ctx
}

/* ================= F3 dataScope 值域过滤（UI 裁定 2 数据驱动表单落地，纯函数供单测与 FieldRenderer 消费） ================= */

/** dataScope 四域 → DataContext 候选提取器 */
const SCOPE_GETTERS: Record<DataScope, (c: DataContext) => string[]> = {
  'upstream-columns': (c) => c.upstreamColumns,
  'upstream-tables': (c) => c.upstreamTables,
  'workflow-vars': (c) => c.vars,
  'time-params': (c) => c.timeParams,
}

/** 域空禁用原因（「禁用必说明」，交互约定：原因随字段行内提示展示） */
const SCOPE_EMPTY_WHY: Record<DataScope, string> = {
  'upstream-columns': '上游无可引用列：无上游连线，或上游组件未登记输出 schema',
  'upstream-tables': '上游无可引用表：无上游连线，或上游组件未登记输出 schema',
  'workflow-vars': '暂无可引用变量：未注册全局参数，且本工作流未定义变量',
  'time-params': '内置时间参数不可用（基线常驻，出现即为装配缺陷，请检查变量候选装配）',
}

/**
 * dataScope 值域状态（F3 核心判定，Inspector/弹窗共用）：候选只来自 DataContext 对应域。
 * - 域非空 → options 全量候选（已按 resolveDataContext 去重保序），可正常选择
 * - 域空 → options 空 + disabledReason 非空（字段禁用并说明原因；值域外存量值由渲染层兜底展示不静默丢值）
 * 纯函数：ctx 由调用点注入（fieldCtxFactory 的 dataCtx computed），无 IO 无组件依赖。
 */
export function dataScopeState(ctx: DataContext, scope: DataScope): { options: string[]; disabledReason: string } {
  const options = SCOPE_GETTERS[scope](ctx)
  return options.length ? { options, disabledReason: '' } : { options, disabledReason: SCOPE_EMPTY_WHY[scope] }
}
