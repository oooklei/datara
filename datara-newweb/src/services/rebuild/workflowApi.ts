/**
 * INC4-FE-4 workflow 候选池契约 — 真实端点接线。
 * 真源：datara-backend/rebuild/workflow/api.py（Base path /api/v1/rebuild/workflows，
 * 挂载点 rebuild/api/app.py include_router prefix="/api/v1/rebuild/workflows"；
 * envelope {code, msg, data}，http.ts 底座统一解包）。
 * - list：GET /rebuild/workflows?project_id=（必填，缺省 400/4001）→ data 为纯数组；
 *   项形状 = repository._definition_payload(include_draft=False)：
 *   {definition_id, project_id, name, description, current_version}。
 *   候裁披露：wire 暂无 code/tags 字段——前端容错（tags ?? []、code undefined），后端补字段即活。
 * - delete：POST /{definition_id}/delete body {project_id} → data {deleted:true}（draft-only 定义可删）。
 * - categories 系（list/create/delete/setTags）：新后端端点缺位，RED 哨兵
 *   WF_CATEGORIES_NOT_WIRED（沿 scheduleApi notWired 异步 helper 先例）；
 *   旧蓝本端点真源：GET·POST /workflow-definitions/categories、DELETE /{numeric}、PUT /{id}/tags。
 */

import { getJson, request } from '../http'

/* ---------- 列表与删除（真实接线） ---------- */

export interface WorkflowDefSummary {
  id: number
  name: string
  /** 目录标签（根目录 = 空数组）；后端补字段即活，当前恒 [] */
  tags: string[]
  /** 定义序号徽标；后端补字段即活，当前 undefined */
  code?: number
}

interface WorkflowDefinitionWire {
  definition_id: number
  project_id: number
  name: string
  description: string | null
  current_version: number | null
  tags?: string[] | null
  code?: number
}

export async function listWorkflowDefinitions(projectId: number): Promise<WorkflowDefSummary[]> {
  const items = await getJson<WorkflowDefinitionWire[]>('/rebuild/workflows', { projectId })
  return items.map((w) => ({ id: w.definition_id, name: w.name, tags: w.tags ?? [], code: w.code }))
}

export async function deleteWorkflowDefinition(projectId: number, definitionId: number): Promise<void> {
  await request<void>(`/rebuild/workflows/${definitionId}/delete`, {
    method: 'POST',
    json: { project_id: projectId },
  })
}

/* ---------- 分类目录系（RED：端点缺位） ---------- */

export interface WorkflowCategoryRow {
  name: string
  builtin: boolean
}

export const WF_CATEGORIES_NOT_WIRED =
  'WF_CATEGORIES_NOT_WIRED: rebuild/workflow categories contract not connected yet'

const notWired = async (): Promise<never> => {
  throw new Error(WF_CATEGORIES_NOT_WIRED)
}

export const workflowCategories = {
  listCategories: (): Promise<WorkflowCategoryRow[]> => notWired(),
  createCategory: (_name: string): Promise<WorkflowCategoryRow> => notWired(),
  deleteCategory: (_name: string): Promise<void> => notWired(),
  setWfTags: (_definitionId: number, _tags: string[]): Promise<void> => notWired(),
}
