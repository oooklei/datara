/**
 * INC4-FE-4 workflow 候选池契约 — 真实端点接线。
 * INC4-FE-6（WBS 4.4）：workflow 六模型（定义/版本/节点/边/调度/发布记录）
 * API 对接扩容 —— 定义 CRUD + draft 节点/边 upsert/delete + 发布/版本读取，
 * 共 10 方法新增；调度面不在此重复对接（scheduleCrudApi.ts 已备 CRUD 七方法，
 * 9-02 交付；六模型之「调度」= 引用既有契约）。
 *
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
 *
 * FE-6 扩容面（api.py / repository.py 实锚）：
 * - create：POST /rebuild/workflows body {project_id, name, description?} → definition payload；
 *   重名 → 409/WF_NAME_CONFLICT；
 * - get：GET /{definition_id}?project_id= → payload + draft{nodes[],edges[]}；
 * - update：POST /{definition_id}/updates body {project_id, name?, description?}
 *   （两项全缺 → 400/4001）→ definition payload；
 * - draft 节点 upsert：POST /{definition_id}/nodes body {project_id, node_code, node_type,
 *   name?, params?, position_x?, position_y?} → node payload（按 node_code upsert；
 *   node_type ∉ 白名单 → 400/WF_NODE_TYPE_UNKNOWN）；
 * - draft 节点删：POST /{definition_id}/nodes/delete body {project_id, node_code} →
 *   {deleted:true}（级联删触边；WF_NODE_NOT_FOUND 404）；
 * - draft 边 upsert：POST /{definition_id}/edges body {project_id, from_node, to_node, name?}
 *   → edge payload（按 (from,to) upsert；两端须为已有 draft 节点 → 400/WF_EDGE_INVALID）；
 * - draft 边删：POST /{definition_id}/edges/delete body {project_id, from_node, to_node} →
 *   {deleted:true}（WF_EDGE_NOT_FOUND 404）；
 * - publish：POST /{definition_id}/publish body {project_id, remark?} → version payload
 *   （+node_count/edge_count；空 draft → WF_DRAFT_EMPTY）；
 * - versions：GET /{definition_id}/versions?project_id= → version payload[]；
 * - version：GET /{definition_id}/versions/{version}?project_id= → payload + nodes + edges +
 *   publish_record（snapshot_digest tamper 校验不符 → 409/WF_VERSION_IMMUTABLE；
 *   版本内容不可变——published 冻结，无内容更新端点）。
 */

import { getJson, postJson, request } from '../http'

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

/* ---------- FE-6：节点类型白名单（repository.VALID_NODE_TYPES 冻结，门 2 对齐） ---------- */

export const WF_NODE_TYPES = [
  'FLOW', 'SYNC', 'SQL', 'PYTHON', 'SHELL', 'DEPENDENCY', 'START', 'END',
  'CONDITION', 'FORK', 'JOIN', 'WAIT', 'SUB_WORKFLOW',
] as const

export type WfNodeType = (typeof WF_NODE_TYPES)[number]

/* ---------- FE-6：六模型 wire 形状（repository payload 直映） ---------- */

/** draft 节点 wire（_node_payload：params 已 json.loads） */
export interface WorkflowDraftNodeWire {
  node_code: string
  node_type: string
  name: string | null
  params: Record<string, unknown> | null
  position_x: number | null
  position_y: number | null
}

/** draft 边 wire（_edge_payload） */
export interface WorkflowDraftEdgeWire {
  from_node: string
  to_node: string
  name: string | null
}

/** definition payload + draft（GET /{id} include_draft=True） */
export interface WorkflowDraftWire {
  nodes: WorkflowDraftNodeWire[]
  edges: WorkflowDraftEdgeWire[]
}

/** version payload（_version_payload；node_count/edge_count 仅 publish 与 version 详情面） */
export interface WorkflowVersionWire {
  definition_id: number
  version: number
  status: string
  remark: string | null
  snapshot_digest: string
  published_at: string | null
  published_by: string | null
  node_count?: number
  edge_count?: number
}

/** publish_record（WorkflowPublishRecord） */
export interface WorkflowPublishRecordWire {
  version_id: number
  version: number
  remark: string | null
  published_by: string | null
  published_at: string | null
}

/* ---------- FE-6：前端域类型（camelCase） ---------- */

export interface WorkflowDefinitionInfo {
  id: number
  projectId: number
  name: string
  description: string | null
  currentVersion: number | null
}

export interface WorkflowDraftNode {
  nodeCode: string
  nodeType: string
  name: string | null
  params: Record<string, unknown> | null
  positionX: number | null
  positionY: number | null
}

export interface WorkflowDraftEdge {
  fromNode: string
  toNode: string
  name: string | null
}

export interface WorkflowDraft {
  nodes: WorkflowDraftNode[]
  edges: WorkflowDraftEdge[]
}

export interface WorkflowVersion {
  definitionId: number
  version: number
  status: string
  remark: string | null
  snapshotDigest: string
  publishedAt: string | null
  publishedBy: string | null
  nodeCount?: number
  edgeCount?: number
}

export interface WorkflowPublishRecord {
  versionId: number
  version: number
  remark: string | null
  publishedBy: string | null
  publishedAt: string | null
}

export interface WorkflowVersionDetail extends WorkflowVersion {
  nodes: WorkflowDraftNode[]
  edges: WorkflowDraftEdge[]
  publishRecord: WorkflowPublishRecord | null
}

/* ---------- FE-6：wire → 域映射 ---------- */

function mapDefInfo(w: WorkflowDefinitionWire): WorkflowDefinitionInfo {
  return {
    id: w.definition_id,
    projectId: w.project_id,
    name: w.name,
    description: w.description,
    currentVersion: w.current_version,
  }
}

function mapNode(w: WorkflowDraftNodeWire): WorkflowDraftNode {
  return {
    nodeCode: w.node_code,
    nodeType: w.node_type,
    name: w.name ?? null,
    params: w.params ?? null,
    positionX: w.position_x ?? null,
    positionY: w.position_y ?? null,
  }
}

function mapEdge(w: WorkflowDraftEdgeWire): WorkflowDraftEdge {
  return { fromNode: w.from_node, toNode: w.to_node, name: w.name ?? null }
}

function mapDraft(w: WorkflowDraftWire | undefined): WorkflowDraft {
  return {
    nodes: (w?.nodes ?? []).map(mapNode),
    edges: (w?.edges ?? []).map(mapEdge),
  }
}

function mapVersion(w: WorkflowVersionWire): WorkflowVersion {
  return {
    definitionId: w.definition_id,
    version: w.version,
    status: w.status,
    remark: w.remark ?? null,
    snapshotDigest: w.snapshot_digest,
    publishedAt: w.published_at ?? null,
    publishedBy: w.published_by ?? null,
    nodeCount: w.node_count,
    edgeCount: w.edge_count,
  }
}

function mapPublishRecord(w: WorkflowPublishRecordWire): WorkflowPublishRecord {
  return {
    versionId: w.version_id,
    version: w.version,
    remark: w.remark ?? null,
    publishedBy: w.published_by ?? null,
    publishedAt: w.published_at ?? null,
  }
}

/* ---------- FE-6：定义 CRUD（list/delete 见上；create/get/update 此处） ---------- */

/** 创建工作流定义（POST /rebuild/workflows；重名 → 409/WF_NAME_CONFLICT） */
export async function createWorkflowDefinition(
  projectId: number,
  name: string,
  description?: string,
): Promise<WorkflowDefinitionInfo> {
  const wire = await postJson<WorkflowDefinitionWire>('/rebuild/workflows', {
    project_id: projectId,
    name,
    ...(description !== undefined ? { description } : {}),
  })
  return mapDefInfo(wire)
}

/** 读取定义 + draft（GET /{definition_id}?project_id=；draft 含 nodes/edges 全量） */
export async function getWorkflowDefinition(
  projectId: number,
  definitionId: number,
): Promise<WorkflowDefinitionInfo & { draft: WorkflowDraft }> {
  const wire = await getJson<WorkflowDefinitionWire & { draft?: WorkflowDraftWire }>(
    `/rebuild/workflows/${definitionId}`,
    { projectId },
  )
  return { ...mapDefInfo(wire), draft: mapDraft(wire.draft) }
}

/** 更新定义（POST /{definition_id}/updates；两项全缺 → 后端 400/4001，调用方至少传一项） */
export async function updateWorkflowDefinition(
  projectId: number,
  definitionId: number,
  patch: { name?: string; description?: string },
): Promise<WorkflowDefinitionInfo> {
  const wire = await postJson<WorkflowDefinitionWire>(`/rebuild/workflows/${definitionId}/updates`, {
    project_id: projectId,
    ...(patch.name !== undefined ? { name: patch.name } : {}),
    ...(patch.description !== undefined ? { description: patch.description } : {}),
  })
  return mapDefInfo(wire)
}

/* ---------- FE-6：draft 节点/边 upsert/delete ---------- */

/** 新增/更新 draft 节点（POST /{id}/nodes；按 node_code upsert） */
export async function upsertWorkflowDraftNode(
  projectId: number,
  definitionId: number,
  node: WorkflowDraftNode,
): Promise<WorkflowDraftNode> {
  const wire = await postJson<WorkflowDraftNodeWire>(`/rebuild/workflows/${definitionId}/nodes`, {
    project_id: projectId,
    node_code: node.nodeCode,
    node_type: node.nodeType,
    name: node.name,
    params: node.params,
    position_x: node.positionX,
    position_y: node.positionY,
  })
  return mapNode(wire)
}

/** 删除 draft 节点（POST /{id}/nodes/delete；级联删触边） */
export async function deleteWorkflowDraftNode(
  projectId: number,
  definitionId: number,
  nodeCode: string,
): Promise<void> {
  await postJson(`/rebuild/workflows/${definitionId}/nodes/delete`, {
    project_id: projectId,
    node_code: nodeCode,
  })
}

/** 新增/更新 draft 边（POST /{id}/edges；按 (from,to) upsert；两端须为已有 draft 节点） */
export async function upsertWorkflowDraftEdge(
  projectId: number,
  definitionId: number,
  edge: WorkflowDraftEdge,
): Promise<WorkflowDraftEdge> {
  const wire = await postJson<WorkflowDraftEdgeWire>(`/rebuild/workflows/${definitionId}/edges`, {
    project_id: projectId,
    from_node: edge.fromNode,
    to_node: edge.toNode,
    name: edge.name,
  })
  return mapEdge(wire)
}

/** 删除 draft 边（POST /{id}/edges/delete；按 (from,to) 定位） */
export async function deleteWorkflowDraftEdge(
  projectId: number,
  definitionId: number,
  fromNode: string,
  toNode: string,
): Promise<void> {
  await postJson(`/rebuild/workflows/${definitionId}/edges/delete`, {
    project_id: projectId,
    from_node: fromNode,
    to_node: toNode,
  })
}

/* ---------- FE-6：发布与版本读取 ---------- */

/** 发布 draft 为版本（POST /{id}/publish；空 draft → WF_DRAFT_EMPTY） */
export async function publishWorkflowDefinition(
  projectId: number,
  definitionId: number,
  remark?: string,
): Promise<WorkflowVersion> {
  const wire = await postJson<WorkflowVersionWire>(`/rebuild/workflows/${definitionId}/publish`, {
    project_id: projectId,
    ...(remark !== undefined ? { remark } : {}),
  })
  return mapVersion(wire)
}

/** 版本列表（GET /{id}/versions?project_id=） */
export async function listWorkflowVersions(
  projectId: number,
  definitionId: number,
): Promise<WorkflowVersion[]> {
  const items = await getJson<WorkflowVersionWire[]>(`/rebuild/workflows/${definitionId}/versions`, { projectId })
  return items.map(mapVersion)
}

/** 版本详情（GET /{id}/versions/{version}?project_id=；含 nodes/edges/publish_record） */
export async function getWorkflowVersion(
  projectId: number,
  definitionId: number,
  version: number,
): Promise<WorkflowVersionDetail> {
  const wire = await getJson<
    WorkflowVersionWire & {
      nodes?: WorkflowDraftNodeWire[]
      edges?: WorkflowDraftEdgeWire[]
      publish_record?: WorkflowPublishRecordWire
    }
  >(`/rebuild/workflows/${definitionId}/versions/${version}`, { projectId })
  return {
    ...mapVersion(wire),
    nodes: (wire.nodes ?? []).map(mapNode),
    edges: (wire.edges ?? []).map(mapEdge),
    publishRecord: wire.publish_record ? mapPublishRecord(wire.publish_record) : null,
  }
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
