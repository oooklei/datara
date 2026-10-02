/**
 * 组件目录服务（M0 · 只读系统组件清单）。
 *
 * 背景：系统组件注册表此前只存在于 `graph/profiles/*.ts`，被编译进 Vue bundle，
 * 后端无法校验、无法版本化、无法服务给其他客户端。M0 由
 * `scripts/export_dag_catalog.py` 从 profile 源码导出为 `common/dag_catalog.json`，
 * 经 `/api/v1/components` 只读下发，本页消费之。
 *
 * M0 只读：不接受任何写操作。用户自建组件（草稿/发布/版本）属 M1+，
 * 届时新增 `t_component` 表与 POST/PUT 接口。
 */
import { http } from './http'
import { isMock } from './apiMode'
import { mockComponentDetail, mockComponentDraft, mockComponentVersions } from './mock/api'

/** 组件派发方式（与后端 master.py 派发点、dag.py WORKER_TYPES 一一对应） */
export type ComponentRoute =
  | 'master'        // Master 进程内 Python 处理器
  | 'worker'        // 下发 Worker，由 executor 执行
  | 'template'      // 流程模板，不参与单节点派发
  | 'nonExecutable' // 画布辅助节点（page_board），不落库不派发
  | 'UNROUTED'      // **无派发实现**（当前 3 个 stream_* 硬缺口）

/** 表单字段联动/校验标记（不可序列化，序列化时转布尔） */
export interface FormFieldFlags {
  /** showIf：条件显隐 */
  showIf?: boolean
  /** onChange：联动副作用 */
  onChange?: boolean
  /** pick：CapabilityRef 白名单 */
  pick?: boolean
  /** text：动态文案（富文本/HTML），M0 尚未统计 */
  text?: boolean
}

export interface FormField {
  key: string
  label?: string
  /** 控件类型（当前 22 种），与组件 type 无关。收敛目标 27 → 9 */
  type: string
  required?: boolean
  placeholder?: string
  options?: Array<{ label: string; value: string | number }>
  dsTypes?: string[]
  defaultValue?: unknown
  flags: FormFieldFlags
}

/** 组件由谁执行（M1「发布必须绑定执行契约」的前置事实，不可由 route 反推） */
export type ExecutionModel =
  | 'dag-engine'     // Master 派发点 / Worker executor
  | 'demo-only'      // **无任何执行实现**（后端全文检索无该 type）
  | 'canvas-device'  // 画布装饰元件（shape=device, form=[]），设计上不执行
  | 'page'           // 页面设计器产出的 UI 组件（不可执行）

export interface ComponentRow {
  type: string
  /** 所属 ViewProfile：dag / etl / stream / topo */
  profile: string
  /** 是否属于 DAG 画布语义（仅 dag 为 true） */
  dagRelevant: boolean
  executionModel: ExecutionModel
  /** executionModel 的人类可读依据 */
  executionNote: string
  /** 后端组件编码（如 C01），无则空串 */
  code: string
  label: string
  icon: string
  color: string
  desc: string
  categories: string[]
  shape: string
  /** 仅运行时节点：随作业实例持久化，不进入用户定义 DAG */
  runtimeOnly: boolean
  route: ComponentRoute
  /** worker 组件绑定的 executor 注册名 */
  executor: string | null
  paletteVisible: boolean
  paletteGroup: string | null
  formFieldCount: number
  requiredFieldCount: number
  flags: FormFieldFlags
}

export interface ComponentDetail extends ComponentRow {
  formFields: FormField[]
}

export interface ComponentListResult {
  total: number
  catalogHash: string
  schemaVersion: number
  items: ComponentRow[]
}

export interface ProfileRow {
  profile: string
  source: string
  nodeTypes: number
  dagRelevant: boolean
  /** palette 容器格式：items | types | null —— 跨 profile 并不统一 */
  paletteFormat: string | null
  paletteGroups: number
  paletteItems: number
  /** 形如 [...dagProfile.palette] 的展开继承 */
  paletteSpreads: string[]
  hidden: number
}

export interface ComponentStats {
  catalogHash: string
  generatedAt: string
  source: Record<string, string>
  stats: Record<string, unknown> & {
    total: number
    paletteVisible: number
    routable: number
    template: number
    nonExecutable: number
    runtimeOnly: number
    /** dag 画布无派发实现的 type（DAG 引擎口径，C17/I6 收口对象） */
    unrouted: number
    unroutedTypes: string[]
    /** 全系统无任何执行实现的 type 总数（含 etl/stream 演示态组件） */
    unroutedTotal: number
    unroutedByProfile: Record<string, string[]>
    /** 有后端路由但无前端 NodeSchema 的 type（smoke/src_select/tgt_select） */
    backendOnlyTypes: string[]
    routeByProfile: Record<string, Record<string, number>>
    consistencyErrors: string[]
    crossProfileDuplicateTypes: string[]
  }
  profiles: ProfileRow[]
}

function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const q = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') q.set(k, String(v))
  }
  const s = q.toString()
  return s ? `?${s}` : ''
}

/** 组件清单（可按 profile / route / paletteVisible / 关键词过滤） */
export async function listComponents(params: {
  profile?: string
  route?: string
  paletteVisible?: boolean
  q?: string
} = {}): Promise<ComponentListResult> {
  return http.get<ComponentListResult>(
    `/components${qs({ ...params, paletteVisible: params.paletteVisible })}`)
}

/** 组件目录统计（含注册表漂移指标） */
export async function getComponentStats(): Promise<ComponentStats> {
  return http.get<ComponentStats>('/components/stats')
}

/** 单组件详情（含逐字段表单定义） */
export async function getComponent(type: string): Promise<ComponentDetail> {
  if (isMock) return mockComponentDetail(type)
  return http.get<ComponentDetail>(`/components/${encodeURIComponent(type)}`)
}

/** 目录原始快照（M1 设计器与服务端校验复用） */
export async function getComponentCatalog(): Promise<Record<string, unknown>> {
  return http.get<Record<string, unknown>>('/components/catalog')
}

/* ================= M1 组件设计（治理设计 §18.2 五端点；B2 草稿 + B5 冻结） ================= */

/** 组件草稿（主表身份 + 草稿 spec + draftRev；spec 存 t_component_version 草稿行，§16） */
export interface ComponentDraft {
  type: string
  name: string
  category: string | null
  profile: string
  scope: string
  executionModel: string
  executor: string | null
  executable: boolean
  state: string
  publishedVersion: number | null
  draftRev: number
  draftVersion: number
  description: string | null
  tags: string[]
  spec: Record<string, unknown>
  specHash: string
  updatedAt: string
}

export interface ComponentVersionRow {
  version: number
  state: string
  specHash: string
  remark: string | null
  publishedBy: string | null
  publishedAt: string | null
  createdAt: string | null
}

export interface ComponentVersionsResult {
  type: string
  publishedVersion: number | null
  items: ComponentVersionRow[]
}

export interface ComponentCreateBody {
  type: string
  name: string
  profile: 'dag' | 'etl' | 'stream' | 'topo'
  /* 'page'：页面设计器产出的 UI 组件（后端 ComponentCreateBody execution_model 同名枚举成员） */
  executionModel: 'dag-engine' | 'canvas-device' | 'demo-only' | 'runtime-only' | 'page'
  category?: string
  executor?: string
  executable?: boolean
  description?: string
  tags?: string[]
  spec?: Record<string, unknown>
}

/** 创建组件草稿（type 全局唯一，重复 409/6005；初始 spec 纯数据违规 422/6008） */
export async function createComponentDraft(
  body: ComponentCreateBody,
): Promise<{ type: string; draftRev: number; draftVersion: number }> {
  /* 后端 pydantic 契约为 snake_case（execution_model），响应才是 camelCase */
  return http.post('/components', {
    type: body.type,
    name: body.name,
    profile: body.profile,
    execution_model: body.executionModel,
    category: body.category,
    executor: body.executor,
    executable: body.executable,
    description: body.description,
    tags: body.tags,
    spec: body.spec,
  })
}

/** 读取草稿（无进行中草稿 409/6002；type 不存在 404/6001） */
export async function getComponentDraft(type: string): Promise<ComponentDraft> {
  if (isMock) return mockComponentDraft(type)
  return http.get<ComponentDraft>(`/components/${encodeURIComponent(type)}/draft`)
}

/** 创建页面组件草稿（页面设计器 Task 13）：execution_model=page 红线 executable=false，
 *  spec 仅含 { page }（page DSL 结构由后端 _validate_page_spec 校验）。
 *  profile 暂挂 dag（四选一约束下最通用归属，页面组件不参与任何执行视角）。 */
export async function createPageDraft(body: {
  type: string
  name: string
  page: unknown
  description?: string
}): Promise<{ type: string; draftRev: number; draftVersion: number }> {
  return http.post('/components', {
    type: body.type,
    name: body.name,
    profile: 'dag',
    execution_model: 'page',
    executable: false,
    description: body.description,
    spec: { page: body.page },
  })
}

/** 保存草稿（乐观锁：rev 不匹配 409/6007，data.currentRev 随错误码丢失 → 调用方重拉草稿） */
export async function saveComponentDraft(
  type: string,
  body: { draftRev: number; spec: Record<string, unknown>; remark?: string },
): Promise<{ draftRev: number; specHash: string; savedAt: string }> {
  if (isMock) return { draftRev: body.draftRev + 1, specHash: 'mock1', savedAt: new Date().toISOString() }
  return http.put(`/components/${encodeURIComponent(type)}/draft`, {
    draft_rev: body.draftRev,
    spec: body.spec,
    remark: body.remark,
  })
}

/** 冻结草稿为不可变版本（B5：草稿行 frozen + 自动开启 v+1 空草稿；无草稿 409/6002） */
export async function freezeComponentVersion(
  type: string,
  remark?: string,
): Promise<{ frozenVersion: number; draftVersion: number; draftRev: number }> {
  return http.post(`/components/${encodeURIComponent(type)}/versions`, { remark })
}

/** 版本列表（version 倒序，不回 spec 全文） */
export async function listComponentVersions(type: string): Promise<ComponentVersionsResult> {
  if (isMock) return mockComponentVersions(type)
  return http.get<ComponentVersionsResult>(`/components/${encodeURIComponent(type)}/versions`)
}

/* ================= M2 发布治理（治理设计 §18.3；D1 发布闸门） ================= */

export interface GateItem {
  gate: string
  ok: boolean
  msg: string
}

/** §9 发布即刷新结果（publish 成功后端自动执行并挂载在响应 data.refresh） */
export interface PublishRefresh {
  refreshed: number
  publishedVersion: number
  items: { wfId: string; wfName: string }[]
}

export interface PublishResult {
  type: string
  publishedVersion: number
  specHash: string
  supersededVersion: number | null
  publishedAt: string
  /* 旧后端响应无此字段 → 客户端须判空并兜底调 refresh-refs（页面设计器 §9 发布链） */
  refresh?: PublishRefresh
}

/** 发布指定 frozen 版本（跑 §13 八项闸门；422/6003 data.items 逐项结果，409/6007 乐观锁）。
 * 闸门不可绕过：无 force / 无豁免（§13 设计决策）。 */
export async function publishComponentVersion(
  type: string,
  body: { version: number; draftRev: number; remark?: string },
): Promise<PublishResult> {
  return http.post<PublishResult>(`/components/${encodeURIComponent(type)}/publish`, {
    version: body.version,
    draft_rev: body.draftRev,
    remark: body.remark,
  })
}

/* ================= M2 发布治理（D3：下线/回滚/影响面/注册表） ================= */

/** 下线组件（§8 published→offline，幂等）。publishedVersion 保留：既有工作流引用照常运行。 */
export async function offlineComponent(
  type: string,
  remark?: string,
): Promise<{ type: string; state: string; publishedVersion: number | null }> {
  return http.post(`/components/${encodeURIComponent(type)}/offline`, { remark })
}

/** 回滚到「曾发布后下线」的历史版本（§8 offline→published；当前 published 行自动让位）。 */
export async function rollbackComponent(
  type: string,
  version: number,
  remark?: string,
): Promise<{ type: string; publishedVersion: number; supersededVersion: number | null }> {
  return http.post(`/components/${encodeURIComponent(type)}/rollback`, {
    version, remark,
  })
}

/** 影响面行（§9.4：引用该组件的工作流 + 版本对齐标记） */
export interface ImpactedWorkflow {
  id: string
  code: number
  name: string
  /** 定义当前版本号（t_wf_definition.version） */
  version: number
  releaseState: string
  /** 该工作流内引用此组件的 componentRef.version 全集（升序） */
  refVersions: number[]
  /** 任一引用版本落后于组件 published_version（批量升级向导目标集） */
  behind: boolean
  /** 全部引用版本恰等于 published_version（回滚降版后高版本引用为不对齐） */
  aligned: boolean
}

export interface ImpactedResult {
  type: string
  publishedVersion: number | null
  state: string
  items: ImpactedWorkflow[]
}

/** 影响面查询（§9.4）：扫描全部工作流 graph_json 的 componentRef.type 命中清单。 */
export async function getImpactedWorkflows(type: string): Promise<ImpactedResult> {
  return http.get<ImpactedResult>(`/components/${encodeURIComponent(type)}/impacted`)
}

/** 用户组件注册表行（t_component 轻量元数据，不含 spec 全文） */
export interface CompRegistryRow {
  type: string
  name: string
  profile: string
  scope: string
  /** §8 生命周期：draft/published/offline */
  state: string
  publishedVersion: number | null
  executionModel: string
  category: string | null
}

/** 用户组件注册表（画布序列化注入 componentRef 的 version 供给 + 目录页生命周期标签区）。 */
export async function getComponentRegistry(): Promise<CompRegistryRow[]> {
  const r = await http.get<{ items: CompRegistryRow[] }>('/components/registry')
  return r.items
}
