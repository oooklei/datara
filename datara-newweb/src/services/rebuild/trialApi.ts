/**
 * INC4-FE-7 trial 试运行域契约 — 真实端点接线（WBS 4.5 / s269 派令）。
 *
 * 票面口径注记：WBS 4.5 原文「trial 域 2 端点」为 WF-12 快照对（snapshot 创建+读取）
 * 旧口径；后端现态已扩至 7 端点（WF-12 快照对 2 + WF-14 run 1 + WF-21 promote 1 +
 * WF-26 runs 面 3），沿 FE-6「逐端点映射现态真源」先例全量接线。
 *
 * 真源：datara-backend/rebuild/trial/api.py（Base path /api/v1/rebuild/trial，
 * 挂载点 rebuild/api/app.py include_router prefix="/api/v1/rebuild/trial"；
 * envelope {code, msg, data}，http.ts 底座统一解包）：
 * - snapshot：POST /definitions/{definition_id}/snapshot body {project_id}
 *   → 快照 payload（EDIT_DEFINITION；幂等——同 digest 返回既有行，旧行 ACTIVE 降 STALE）；
 * - snapshot get：GET /snapshots/{snapshot_id}?project_id=（必填，缺省 400/4001；VIEW_ALL）；
 * - run：POST /definitions/{definition_id}/run body {project_id, snapshot_id, options?}
 *   → 运行结果（EDIT_DEFINITION）；
 * - promote：POST /definitions/{definition_id}/promote body {project_id, instance_id, remark?}
 *   → promote payload（EDIT_DEFINITION）；
 * - WF-26 runs：POST /runs body {project_id, definition_id, snapshot_id, options?} → 运行结果；
 * - WF-26 output：GET /runs/{run_id}?project_id=（VIEW_ALL；实例缺属 → 404/4404）；
 * - WF-26 promote：POST /runs/{run_id}/promote body {project_id, remark?} → promote payload。
 *
 * 试运行八能力 → options 映射（runner.TrialRunOptions WF-15~WF-20 + promote WF-21）：
 *   草稿快照→POST snapshot；指定节点→options.node_codes；单节点→options.start_node
 *   （正向可达子图）；变量覆盖→options.test_variables（名→值）；依赖模拟→options.dependency_mock
 *   （dependency_id → 'SUCCEEDED'|'FAILED'）；DryRun→options.dry_run（仅出 plan，
 *   status=DRY_RUN、instance_id=0）；SQL 预检→options.sql_precheck；转正式→promote。
 *
 * wire 形状（repository/runner/promote/output 实锚）：
 * - 快照 payload：{snapshot_id, definition_id, snapshot_digest, node_snapshot_json（已解析
 *   节点数组）, edge_snapshot_json（已解析边数组）, status: ACTIVE|STALE, created_by, created_at}；
 * - 运行结果：{instance_id, status: SUCCEEDED|FAILED|DRY_RUN, task_count,
 *   tasks: [{task_instance_id, task_id, node_code, status}]（skipped 补录 SKIPPED）,
 *   plan?: string[]（仅 dry_run 拓扑序，非 dry_run 为 null）}；
 * - promote payload：{version, status: PUBLISHED, snapshot_digest, idempotent}（幂等：同
 *   digest 已有 PUBLISHED 版本直接返回）；
 * - 输出面：{logs: [{task_id, task_code, logs: [{attempt_no, level, message}]}],
 *   variables: [{name, expression, scope, resolved_value, value_type, source, attempt_no}],
 *   stats: {success_count, failed_count, skipped_count}, found, instance_type?, status?}
 *   （空运行返空数组不 404）。
 *
 * 错误码：MalformedRequest 400/4001；WF_SNAPSHOT_NOT_FOUND 404；WF_TRIAL_INVALID /
 * WF_TRIAL_DEPENDENCY_FAILED（TrialRunnerError）；WF_INSTANCE_NOT_FOUND 404 /
 * WF_PROMOTE_NOT_TRIAL / WF_PROMOTE_NO_SNAPSHOT / WF_PROMOTE_DIGEST_MISMATCH 409
 * （PromoteError）；ExecutionDomainError 400；401/1001 无效 token。
 */

import { getJson, postJson } from '../http'

const TRIAL_BASE = '/rebuild/trial'

/* ---------- 试运行八能力 options（前端域类型，camelCase） ---------- */

/** WF-18 依赖模拟结果（dependency_id → 状态） */
export type TrialDependencyMockStatus = 'SUCCEEDED' | 'FAILED'

/** 试运行扩展维度（runner.TrialRunOptions WF-15~WF-20；缺省键不携带） */
export interface TrialRunOptions {
  /** WF-15：仅执行指定节点子集 */
  nodeCodes?: string[]
  /** WF-16：从指定节点执行正向可达子图 */
  startNode?: string
  /** WF-17：运行时变量覆盖（变量名 → 覆盖值） */
  testVariables?: Record<string, unknown>
  /** WF-18：DEPENDENCY 节点模拟（dependency_id → 模拟结果） */
  dependencyMock?: Record<string, TrialDependencyMockStatus>
  /** WF-19：仅出执行计划不落副作用（status=DRY_RUN、instance_id=0） */
  dryRun?: boolean
  /** WF-20：执行前 SQL 预检 */
  sqlPrecheck?: boolean
}

/* ---------- wire 形状（snake_case，后端 payload 直映） ---------- */

/** 快照节点项（repository._node_payload：params 已 json.loads） */
export interface TrialSnapshotNodeWire {
  node_code: string
  node_type: string
  name: string | null
  params: Record<string, unknown>
  position_x: number | null
  position_y: number | null
}

/** 快照边项（repository._edge_payload） */
export interface TrialSnapshotEdgeWire {
  from_node: string
  to_node: string
  name: string | null
}

/** 快照 payload（repository._snapshot_payload） */
export interface TrialSnapshotWire {
  snapshot_id: number
  definition_id: number
  snapshot_digest: string
  node_snapshot_json: TrialSnapshotNodeWire[]
  edge_snapshot_json: TrialSnapshotEdgeWire[]
  status: string
  created_by: number | null
  created_at: string | null
}

/** 任务项（runner.tasks_payload；task_id=node_code，WF-29） */
export interface TrialRunTaskWire {
  task_instance_id: number
  task_id: string
  node_code: string
  status: string
}

/** 运行结果（api.py data；plan 仅 dry_run 为拓扑序数组，否则 null） */
export interface TrialRunResultWire {
  instance_id: number
  status: string
  task_count: number
  tasks: TrialRunTaskWire[]
  plan: string[] | null
}

/** promote payload（promote.py；幂等返回既有 PUBLISHED 版本） */
export interface TrialPromoteWire {
  version: number
  status: string
  snapshot_digest: string
  idempotent: boolean
}

/** 单任务日志组（output._collect_logs） */
export interface TrialTaskLogsWire {
  task_id: number
  task_code: string
  logs: { attempt_no: number; level: string; message: string }[]
}

/** 终态变量快照（output._collect_variables：每变量名取最后值） */
export interface TrialVariableWire {
  name: string
  expression: string | null
  scope: string | null
  resolved_value: unknown
  value_type: string | null
  source: string | null
  attempt_no: number
}

/** 输出面（output.aggregate；实例缺属分支无 instance_type/status，stats 为空对象） */
export interface TrialRunOutputWire {
  logs: TrialTaskLogsWire[]
  variables: TrialVariableWire[]
  stats: { success_count?: number; failed_count?: number; skipped_count?: number }
  found: boolean
  instance_type?: string
  status?: string
}

/* ---------- 前端域类型（camelCase） ---------- */

export type TrialSnapshotStatus = 'ACTIVE' | 'STALE'
export type TrialRunStatus = 'SUCCEEDED' | 'FAILED' | 'DRY_RUN'
export type TrialTaskStatus = 'SUCCEEDED' | 'FAILED' | 'SKIPPED'

export interface TrialSnapshotNode {
  nodeCode: string
  nodeType: string
  name: string | null
  params: Record<string, unknown>
  positionX: number | null
  positionY: number | null
}

export interface TrialSnapshotEdge {
  fromNode: string
  toNode: string
  name: string | null
}

export interface TrialSnapshot {
  snapshotId: number
  definitionId: number
  snapshotDigest: string
  nodes: TrialSnapshotNode[]
  edges: TrialSnapshotEdge[]
  status: TrialSnapshotStatus
  createdBy: number | null
  createdAt: string | null
}

export interface TrialRunTask {
  taskInstanceId: number
  taskId: string
  nodeCode: string
  status: TrialTaskStatus
}

export interface TrialRunResult {
  instanceId: number
  status: TrialRunStatus
  taskCount: number
  tasks: TrialRunTask[]
  /** 仅 dry_run：拓扑序执行计划 */
  plan: string[] | null
}

export interface TrialPromoteResult {
  version: number
  status: string
  snapshotDigest: string
  /** true = 同 digest 已有 PUBLISHED 版本，幂等直返 */
  idempotent: boolean
}

export interface TrialRunLogEntry {
  attemptNo: number
  level: string
  message: string
}

export interface TrialTaskLogs {
  taskId: number
  taskCode: string
  logs: TrialRunLogEntry[]
}

export interface TrialRunVariable {
  name: string
  expression: string | null
  scope: string | null
  resolvedValue: unknown
  valueType: string | null
  source: string | null
  attemptNo: number
}

export interface TrialRunStats {
  successCount: number
  failedCount: number
  skippedCount: number
}

export interface TrialRunOutput {
  logs: TrialTaskLogs[]
  variables: TrialRunVariable[]
  stats: TrialRunStats
  found: boolean
  instanceType: string | null
  status: string | null
}

/* ---------- wire → 域映射 ---------- */

function mapSnapshotNode(w: TrialSnapshotNodeWire): TrialSnapshotNode {
  return {
    nodeCode: w.node_code,
    nodeType: w.node_type,
    name: w.name ?? null,
    params: w.params ?? {},
    positionX: w.position_x ?? null,
    positionY: w.position_y ?? null,
  }
}

function mapSnapshotEdge(w: TrialSnapshotEdgeWire): TrialSnapshotEdge {
  return { fromNode: w.from_node, toNode: w.to_node, name: w.name ?? null }
}

function mapSnapshot(w: TrialSnapshotWire): TrialSnapshot {
  return {
    snapshotId: w.snapshot_id,
    definitionId: w.definition_id,
    snapshotDigest: w.snapshot_digest,
    nodes: (w.node_snapshot_json ?? []).map(mapSnapshotNode),
    edges: (w.edge_snapshot_json ?? []).map(mapSnapshotEdge),
    status: (w.status ?? 'ACTIVE') as TrialSnapshotStatus,
    createdBy: w.created_by ?? null,
    createdAt: w.created_at ?? null,
  }
}

function mapTask(w: TrialRunTaskWire): TrialRunTask {
  return {
    taskInstanceId: w.task_instance_id,
    taskId: w.task_id,
    nodeCode: w.node_code,
    status: w.status as TrialTaskStatus,
  }
}

function mapRunResult(w: TrialRunResultWire): TrialRunResult {
  return {
    instanceId: w.instance_id,
    status: w.status as TrialRunStatus,
    taskCount: w.task_count,
    tasks: (w.tasks ?? []).map(mapTask),
    plan: w.plan ?? null,
  }
}

function mapPromote(w: TrialPromoteWire): TrialPromoteResult {
  return {
    version: w.version,
    status: w.status,
    snapshotDigest: w.snapshot_digest,
    idempotent: w.idempotent,
  }
}

function mapOutput(w: TrialRunOutputWire): TrialRunOutput {
  return {
    logs: (w.logs ?? []).map((t) => ({
      taskId: t.task_id,
      taskCode: t.task_code,
      logs: (t.logs ?? []).map((e) => ({
        attemptNo: e.attempt_no,
        level: e.level,
        message: e.message,
      })),
    })),
    variables: (w.variables ?? []).map((v) => ({
      name: v.name,
      expression: v.expression ?? null,
      scope: v.scope ?? null,
      resolvedValue: v.resolved_value,
      valueType: v.value_type ?? null,
      source: v.source ?? null,
      attemptNo: v.attempt_no,
    })),
    stats: {
      successCount: w.stats?.success_count ?? 0,
      failedCount: w.stats?.failed_count ?? 0,
      skippedCount: w.stats?.skipped_count ?? 0,
    },
    found: w.found,
    instanceType: w.instance_type ?? null,
    status: w.status ?? null,
  }
}

/** options 域 → wire 序列化（snake 词形；全空 → undefined，body 不携带 options 键） */
function trialOptionsWire(options?: TrialRunOptions): Record<string, unknown> | undefined {
  if (!options) return undefined
  const wire: Record<string, unknown> = {}
  if (options.nodeCodes !== undefined) wire.node_codes = options.nodeCodes
  if (options.startNode !== undefined) wire.start_node = options.startNode
  if (options.testVariables !== undefined) wire.test_variables = options.testVariables
  if (options.dependencyMock !== undefined) wire.dependency_mock = options.dependencyMock
  if (options.dryRun !== undefined) wire.dry_run = options.dryRun
  if (options.sqlPrecheck !== undefined) wire.sql_precheck = options.sqlPrecheck
  return Object.keys(wire).length > 0 ? wire : undefined
}

/* ---------- 端点函数（7 端点全接线） ---------- */

/** 生成/刷新草稿快照（POST /definitions/{id}/snapshot；幂等同 digest 直返既有行） */
export async function createTrialSnapshot(projectId: number, definitionId: number): Promise<TrialSnapshot> {
  const wire = await postJson<TrialSnapshotWire>(`${TRIAL_BASE}/definitions/${definitionId}/snapshot`, {
    project_id: projectId,
  })
  return mapSnapshot(wire)
}

/** 读取快照（GET /snapshots/{id}?project_id=；缺 project_id → 400/4001） */
export async function getTrialSnapshot(projectId: number, snapshotId: number): Promise<TrialSnapshot> {
  const wire = await getJson<TrialSnapshotWire>(`${TRIAL_BASE}/snapshots/${snapshotId}`, { projectId })
  return mapSnapshot(wire)
}

/** 试运行（POST /definitions/{id}/run；八能力 options 走此端点，缺省键不携带） */
export async function runTrial(
  projectId: number,
  definitionId: number,
  snapshotId: number,
  options?: TrialRunOptions,
): Promise<TrialRunResult> {
  const optionsWire = trialOptionsWire(options)
  const wire = await postJson<TrialRunResultWire>(`${TRIAL_BASE}/definitions/${definitionId}/run`, {
    project_id: projectId,
    snapshot_id: snapshotId,
    ...(optionsWire !== undefined ? { options: optionsWire } : {}),
  })
  return mapRunResult(wire)
}

/** 转正式（POST /definitions/{id}/promote；WF-21，幂等同 digest 直返既有版本） */
export async function promoteTrialRun(
  projectId: number,
  definitionId: number,
  instanceId: number,
  remark?: string,
): Promise<TrialPromoteResult> {
  const wire = await postJson<TrialPromoteWire>(`${TRIAL_BASE}/definitions/${definitionId}/promote`, {
    project_id: projectId,
    instance_id: instanceId,
    ...(remark !== undefined ? { remark } : {}),
  })
  return mapPromote(wire)
}

/** WF-26：按 runs 面发起试运行（POST /runs；definition_id 进 body） */
export async function createTrialRun(
  projectId: number,
  definitionId: number,
  snapshotId: number,
  options?: TrialRunOptions,
): Promise<TrialRunResult> {
  const optionsWire = trialOptionsWire(options)
  const wire = await postJson<TrialRunResultWire>(`${TRIAL_BASE}/runs`, {
    project_id: projectId,
    definition_id: definitionId,
    snapshot_id: snapshotId,
    ...(optionsWire !== undefined ? { options: optionsWire } : {}),
  })
  return mapRunResult(wire)
}

/** WF-26：试运行输出面（GET /runs/{id}?project_id=；logs/variables/stats 聚合） */
export async function getTrialRunOutput(projectId: number, runId: number): Promise<TrialRunOutput> {
  const wire = await getJson<TrialRunOutputWire>(`${TRIAL_BASE}/runs/${runId}`, { projectId })
  return mapOutput(wire)
}

/** WF-26：按 run_id 转正式（POST /runs/{id}/promote；definition 由后端自实例解析） */
export async function promoteRunById(
  projectId: number,
  runId: number,
  remark?: string,
): Promise<TrialPromoteResult> {
  const wire = await postJson<TrialPromoteWire>(`${TRIAL_BASE}/runs/${runId}/promote`, {
    project_id: projectId,
    ...(remark !== undefined ? { remark } : {}),
  })
  return mapPromote(wire)
}
