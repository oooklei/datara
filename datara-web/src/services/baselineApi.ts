/**
 * M-B0 组件基线化 API client（与后端 /components 基线化八端点契约同步实现，
 * 前端先行——后端同期在实现，联调时以此契约为准，不等接口）。
 *
 * 基线化 = 系统内置九组件的声明契约重建：八段 DSL（baselineSpec.ts）替代旧
 * NodeSchema.form 的不可序列化函数声明，走「底稿 → 10 项体检 → 认可发 vN →
 * 修订轮」的生命周期（status: pending/designing/testing/confirming/published）。
 * 复用 http.ts 封装（统一 {code,data} 解包 + err.code/err.data 透传）：
 * - saveDraft：409=乐观锁冲突（data.currentRev）、422=纯数据违规（data.violations）；
 * - publishBaseline：409=已发版且未开修订轮；
 * - redraftBaseline：published→designing（复制最新已发版 spec 为新底稿，registry 供给不变）；
 * - discardBaselineRevision：底稿重置回最新已发版（status 回 published）。
 */
import { http } from './http'
import { isMock } from './apiMode'
import {
  mockBaselineProgress, mockBaselineDraft, mockBaselineSave,
  mockBaselineCheck, mockBaselinePublish, mockBaselineLineage,
} from './mock/api'

/** 基线化状态（清单看板/设计区徽标共用） */
export type BaselineStatus = 'pending' | 'designing' | 'testing' | 'confirming' | 'published'

/** 清单看板行（GET /components/baseline/progress 的 items 项） */
export interface BaselineProgressRow {
  type: string
  code: string
  label: string
  categories: string[]
  /** 执行模型（对齐 componentApi.ExecutionModel；清单分组用，如含 worker 归 ETL/计算类） */
  executionModel: string
  /** 执行器标识（可空） */
  executor: string | null
  paletteVisible: boolean
  runtimeOnly: boolean
  status: BaselineStatus
  draftRev: number
  hasDraft: boolean
  /** 已发版本号（0=未发）；修订中 = status==='designing' && publishedVersion>0 */
  publishedVersion: number
  confirmedBy: string | null
  confirmedAt: string | null
  updatedAt: string
}

/** 基线化进度（items + 状态分布统计） */
export interface BaselineProgressResult {
  items: BaselineProgressRow[]
  stats: { total: number; byStatus: Record<string, number> }
}

/** 实测记录行（证据区只读渲染；新增记录暂存 spec.meta.testDrafts 随底稿保存） */
export interface BaselineTestRecord {
  batch: string
  dataflow: string
  result: string
  note?: string
}

/** 体检单项（10 项：pure_data/form_whitelist/drop_policy/contract/catalog_consistency/ */
export interface BaselineCheckItem {
  check: string
  ok: boolean
  msg: string
}

/** 底稿（GET /components/baseline/{type}/draft；spec 为服务端 JSON，编辑前需 normalizeBaselineSpec） */
export interface BaselineDraft {
  type: string
  status: BaselineStatus
  /** 乐观锁版本号（saveDraft 必传原值；409 冲突时 data.currentRev 为服务器最新） */
  draftRev: number
  spec: Record<string, unknown>
  specHash: string
  /** 最近一次体检报告（check 端点同结构） */
  checkReport: BaselineCheckItem[] | null
  testRecords: BaselineTestRecord[]
  updatedAt: string
}

/** 保存底稿返回（新 rev + 新哈希 + 状态） */
export interface BaselineSaveResult {
  draftRev: number
  specHash: string
  status: BaselineStatus
}

/** 体检报告（10 项逐项结果 + 时间戳；只报告不拦截） */
export interface BaselineCheckResult {
  items: BaselineCheckItem[]
  checkedAt: string
}

/** 认可发 v1 返回（publishedVersion 从 1 起） */
export interface BaselinePublishResult {
  type: string
  publishedVersion: number
  specHash: string
  checkItems: BaselineCheckItem[]
  confirmedAt: string
}

/** 血缘声明查询（目录血缘展示 + 基线状态标记） */
export interface LineageDeclResult {
  type: string
  /** published=已基线 / unbaseline=未基线 */
  baselineState: 'published' | 'unbaseline'
  lineage: unknown
}

/** 1/8 基线化进度（清单看板 + 目录页徽标共用；失败由调用方静默降级） */
export async function progress(): Promise<BaselineProgressResult> {
  if (isMock) return mockBaselineProgress()
  return http.get<BaselineProgressResult>('/components/baseline/progress')
}

/** 2/8 底稿读取（type 先 encodeURIComponent，如 'cdcDs'） */
export async function getDraft(type: string): Promise<BaselineDraft> {
  if (isMock) return mockBaselineDraft(type)
  return http.get<BaselineDraft>(`/components/baseline/${encodeURIComponent(type)}/draft`)
}

/** 3/8 保存底稿（乐观锁 draftRev 必传；409/422 语义见文件头注释） */
export async function saveDraft(
  type: string,
  body: { draftRev: number; spec: Record<string, unknown>; remark?: string },
): Promise<BaselineSaveResult> {
  if (isMock) return mockBaselineSave(type)
  return http.put<BaselineSaveResult>(`/components/baseline/${encodeURIComponent(type)}/draft`, {
    // 后端 BaselineDraftBody 为 snake_case：发 draft_rev，勿改回驼峰（会 422）
    draft_rev: body.draftRev,
    spec: body.spec,
    ...(body.remark !== undefined ? { remark: body.remark } : {}),
  })
}

/** 4/8 十项体检（只报告不拦截；结果作为「认可发版」评审证据） */
export async function runCheck(type: string): Promise<BaselineCheckResult> {
  if (isMock) return mockBaselineCheck(type)
  return http.post<BaselineCheckResult>(`/components/baseline/${encodeURIComponent(type)}/check`)
}

/** 5/8 认可发版（未发=发 v1，修订中=发下一版；二次确认由调用方 ElMessageBox 承担；409=已发版且未开修订轮） */
export async function publishBaseline(type: string, remark?: string): Promise<BaselinePublishResult> {
  if (isMock) return mockBaselinePublish(type)
  return http.post<BaselinePublishResult>(`/components/${encodeURIComponent(type)}/baseline/publish`, {
    remark,
  })
}

/** 开修订轮返回（复制最新已发版 spec 为新底稿，status 转 designing） */
export interface BaselineRedraftResult {
  draftRev: number
  status: BaselineStatus
  /** 复制来源的已发版本号 */
  fromVersion: number
  specHash: string
}

/** 放弃修订返回（底稿重置为最新已发版，status 回 published） */
export interface BaselineDiscardResult {
  status: BaselineStatus
  draftRev: number
  fromVersion: number
  specHash: string
}

/** 6/8 复制最新已发版 spec 开修订轮（published→designing）；修订期间 registry 供给已发版不变 */
export async function redraftBaseline(type: string, remark?: string): Promise<BaselineRedraftResult> {
  return http.post<BaselineRedraftResult>(`/components/${encodeURIComponent(type)}/baseline/redraft`, remark ? { remark } : {})
}

/** 7/8 放弃修订（底稿重置为最新已发版，status 回 published） */
export async function discardBaselineRevision(type: string): Promise<BaselineDiscardResult> {
  return http.post<BaselineDiscardResult>(`/components/${encodeURIComponent(type)}/baseline/discard_draft`, {})
}

/** 8/8 血缘声明查询（证据区血缘声明检查块） */
export async function lineageDecl(type: string): Promise<LineageDeclResult> {
  if (isMock) return mockBaselineLineage(type)
  return http.get<LineageDeclResult>(`/components/${encodeURIComponent(type)}/lineage-decl`)
}
