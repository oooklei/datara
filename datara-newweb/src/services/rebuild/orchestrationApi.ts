/**
 * 编排网关契约 — 海豚（DolphinScheduler）embed 会话 + §10.10 部署运维资源 + §10.11 监控代理。
 *
 * 真源：datara-backend/rebuild/orchestration/api.py
 * （build_orchestration_router，prefix /api/v1/rebuild/orchestration；
 * envelope {code, msg, data}，http.ts 底座统一解包）。
 *
 * 海豚只承担「编排可视化 DAG 画布 + 运行后台底座」，门户外壳/身份/数据源/审计
 * 由 datara + dbx 承担（docs/designs/2026-10-29-dbx-unified-target-design.md §十）。
 * 本文件只暴露宿主/自建页面必需的契约；datasources/scripts 端点在 DS 侧经
 * 内部令牌直连 datara 后端，宿主不代转。
 *
 * wire 约定：请求体与响应体均为 camelCase（与 rebuild 域一致）；查询串键为
 * snake_case，http.ts 底座会做 camel→snake 幂等转换，故此处直接写 camelCase。
 */

import { BASE as HTTP_BASE, deleteJson, getJson, getToken, postJson, putJson, request, TOKEN_HEADER } from '../http'
import type { QueryParams } from '../http'
import { camelToSnakeKey, ContractApiError } from './adapterKit'

/* ---------- embed 会话（宿主 postMessage 下发） ---------- */

/** GET /rebuild/orchestration/session?project_id= → 宿主下发载荷 */
export interface OrchestrationSession {
  /** 短时 embed 令牌（宿主注入 DS 的 X-Datara-Embed-Token，HMAC 签名，15 分钟有效） */
  token: string
  /** 海豚用户名（embed 令牌 claims 内的 u，DS 侧解析为 SESSION_USER） */
  user: string
  /** datara 项目 id（DS 侧任务组等 datara 项目级资源的归属键） */
  projectId: number
  /** DS 项目编码（后端 ensure_project 生成，iframe 路由段） */
  projectCode: string
  projectName: string
  /** datara 后端基址（DS 侧回连用） */
  apiBaseUrl: string
  /** datara 会话令牌（DS 取脚本正文时回传） */
  userToken: string
  /** 当前项目选择的环境组：变量域使用 id，海豚使用 code。 */
  environmentGroupId?: number
  environmentCode?: string
}

/**
 * 取项目对应的编排会话。projectCode 由后端创建/复用 DS 项目后返回，
 * 因此 iframe src 必须等本调用返回后再设定。
 */
export function getOrchestrationSession(projectId: number): Promise<OrchestrationSession> {
  return getJson<OrchestrationSession>('/rebuild/orchestration/session', { projectId })
}

/* ---------- §10.5 B 工作流定义列表（datara 自建页，不进 iframe） ---------- */

/**
 * 工作流定义行。`code` 是海豚侧定义编码，宿主据此拼画布路由
 * `/projects/{projectCode}/workflow/definitions/{code}?embed=1`。
 */
export interface WorkflowDefinitionRow {
  code: number | null
  name: string | null
  /** 海豚运行态（如 `PAUSED`/`RUNNING_EXECUTION`）；定义未上线时为 null */
  state: string | null
  /** 上线态：`ONLINE` / `OFFLINE` */
  releaseState: string | null
  scheduleReleaseState: string | null
  createTime: string | null
  updateTime: string | null
  description: string | null
  userName: string | null
  projectName: string | null
  executionType: string | null
}

export interface WorkflowDefinitionListResult {
  list: WorkflowDefinitionRow[]
  total: number
  pageNo: number
  pageSize: number
}

export type WorkflowDefinitionReleaseState = 'ONLINE' | 'OFFLINE'

export interface WorkflowScheduleRow {
  id: number
  workflowDefinitionCode: number
  workflowDefinitionName: string | null
  crontab: string | null
  timezoneId: string | null
  startTime: string | null
  endTime: string | null
  releaseState: 'ONLINE' | 'OFFLINE' | null
}

/* ---------- §10.5 B 运行监控：工作流实例 / 任务实例 / 日志 ---------- */

/** 通用分页结果（后端把海豚 ``totalList``/``total`` 收敛为 ``list``/``total``）。 */
export interface OrchestrationPaged<T> {
  list: T[]
  total: number
  pageNo: number
  pageSize: number
}

/**
 * 工作流实例行（海豚 ``WorkflowInstance`` 原样透传，camelCase）。
 * 字段集合取自海豚实例列表页列定义，后端不裁剪。
 */
export interface WorkflowInstanceRow {
  id: number
  name: string
  /** 海豚运行态：`SUCCESS`/`RUNNING_EXECUTION`/`FAILURE`/`STOP`/`PAUSE`/`WAITING_THREAD`… */
  state: string | null
  /** 触发方式：`START_PROCESS`/`SCHEDULER`/`COMPLEMENT_DATA`/`REPEAT_RUNNING`… */
  commandType: string | null
  scheduleTime: string | null
  workflowDefinitionCode: number | null
  workflowDefinitionVersion: number | null
  startTime: string | null
  endTime: string | null
  duration: number | string | null
  runTimes: number | null
  recovery: string | null
  /** 试运行标记：1 = 试运行（§10.7 B1） */
  dryRun: number | null
  executorName: string | null
  host: string | null
}

/** 任务实例行（海豚 ``TaskInstance`` 原样透传）。 */
export interface TaskInstanceRow {
  id: number
  name: string
  taskType: string | null
  workflowInstanceId: number | null
  workflowInstanceName: string | null
  workflowDefinitionCode: number | null
  workflowDefinitionName: string | null
  taskCode: number | null
  taskDefinitionVersion: number | null
  state: string | null
  submitTime: string | null
  startTime: string | null
  endTime: string | null
  duration: number | string | null
  retryTimes: number | null
  dryRun: number | null
  executorName: string | null
  host: string | null
  appLink: string | null
}

/** 任务实例日志（海豚 ``LoggerController /log/detail`` 原样透传）。 */
export interface TaskInstanceLog {
  lineNum: number
  message: string
}

/** 甘特图单任务条（海豚 ``org.apache.dolphinscheduler.api.dto.gantt.Task``）。 */
export interface InstanceGanttTask {
  taskName: string | null
  /** 各次执行的开始时间（epoch millis，重跑会有多个元素） */
  startDate: number[] | null
  /** 各次执行的结束时间（epoch millis） */
  endDate: number[] | null
  executionDate: string | null
  isoStart: string | null
  isoEnd: string | null
  status: string | null
  duration: string | null
}

/** 甘特图结构（海豚 ``GanttDto``）。 */
export interface InstanceGantt {
  tasks: InstanceGanttTask[]
  /** 任务编码列表（与 ``tasks`` 顺序对应） */
  taskNames: number[] | null
  /** 任务状态映射（海豚 ``success`` 等键） */
  taskStatus: Record<string, string> | null
}

/** 实例变量（海豚 ``WorkflowInstanceVariablesDTO``，§10.7 D3 只读）。 */
export interface InstanceVariables {
  globalParams: { prop: string; value: string; direct?: string; type?: string }[]
  localParams: Record<string, Record<string, unknown>>
}

/** 实例控制动作：海豚 ``ExecuteType`` 白名单（后端同源校验）。 */
export type WorkflowInstanceExecuteType =
  | 'STOP'
  | 'PAUSE'
  | 'RECOVER_SUSPENDED_PROCESS'
  | 'START_FAILURE_TASK_PROCESS'
  | 'REPEAT_RUNNING'

export type WorkflowInstanceQuery = {
  projectId: number
  pageNo?: number
  pageSize?: number
  /** 0/undefined = 不按定义过滤 */
  workflowDefinitionCode?: number
  searchVal?: string
  stateType?: string
  host?: string
  executorName?: string
  startDate?: string
  endDate?: string
}

export type TaskInstanceQuery = {
  projectId: number
  pageNo?: number
  pageSize?: number
  /** 0/undefined = 不按实例过滤 */
  workflowInstanceId?: number
  searchVal?: string
  taskName?: string
  taskCode?: number
  stateType?: string
  host?: string
  executorName?: string
  startDate?: string
  endDate?: string
}

/**
 * 启动实例载荷（§10.7 B1：`dryRun: true` = 试运行）。
 * 后端补 `scheduleTime` 空串占位，宿主不传。
 */
export interface StartWorkflowInstanceDraft {
  projectId: number
  workflowDefinitionCode: number
  dryRun?: boolean
  failureStrategy?: 'CONTINUE' | 'END'
  warningType?: 'NONE' | 'SUCCESS' | 'FAILURE' | 'ALL'
  workerGroup?: string
  tenantCode?: string
  environmentCode?: number
  startParams?: Record<string, unknown>
  startNodeList?: string
}

/* ---------- §10.10 部署运维资源（R1–R4） ---------- */

export type OrchestrationResourceKind =
  | 'worker_group'
  | 'environment'
  | 'queue'
  | 'cluster'
  | 'task_group'
  | 'resource_file'

/** 海豚监控节点类型（后端 ``/monitor/{node_type}`` 接受值）。 */
export type OrchestrationNodeType = 'MASTER' | 'WORKER' | 'ALERT_SERVER'

/** 编排网关可读权限面：与 datara ``Permission`` 枚举同名，供页面自检门禁。 */
export type OrchestrationResourcePermission = 'VIEW_ALL' | 'EDIT_DEFINITION' | 'MANAGE_USER'

/**
 * 各资源写入门禁（读路径统一 VIEW_ALL）。
 * 队列/集群为全局资源配置：仅 admin（MANAGE_USER）可写，普通用户只在节点表单选用；
 * worker 分组/环境/任务组/资源文件按 owner 隔离，用 EDIT_DEFINITION。
 */
export const ORCHESTRATION_RESOURCE_PERMISSION_MATRIX = Object.freeze({
  worker_group: { list: 'VIEW_ALL', create: 'EDIT_DEFINITION', update: 'EDIT_DEFINITION', delete: 'EDIT_DEFINITION' },
  environment: { list: 'VIEW_ALL', create: 'EDIT_DEFINITION', update: 'EDIT_DEFINITION', delete: 'EDIT_DEFINITION' },
  queue: { list: 'VIEW_ALL', create: 'MANAGE_USER', update: 'MANAGE_USER', delete: 'MANAGE_USER' },
  cluster: { list: 'VIEW_ALL', create: 'MANAGE_USER', update: 'MANAGE_USER', delete: 'MANAGE_USER' },
  task_group: { list: 'VIEW_ALL', create: 'EDIT_DEFINITION', update: 'EDIT_DEFINITION', delete: 'EDIT_DEFINITION' },
  resource_file: { list: 'VIEW_ALL', create: 'EDIT_DEFINITION', update: 'EDIT_DEFINITION', delete: 'EDIT_DEFINITION' },
} as const satisfies Record<OrchestrationResourceKind, Record<'list' | 'create' | 'update' | 'delete', OrchestrationResourcePermission>>)

/** 编排网关错误码（经包络 code 透出，字符串形态）。 */
export const ORCHESTRATION_ERROR_CODES = Object.freeze({
  invalidToken: '1001',
  permissionDenied: '1003',
  dsApiError: 'DS_API_ERROR',
  kindInvalid: 'ORCH_RESOURCE_KIND_INVALID',
  shareForbidden: 'ORCH_SHARE_FORBIDDEN',
  shareUserNotFound: 'ORCH_SHARE_USER_NOT_FOUND',
  shareUsernameRequired: 'ORCH_SHARE_USERNAME_REQUIRED',
  workerGroupReadonly: 'ORCH_WORKER_GROUP_READONLY',
  workerGroupNotFound: 'ORCH_WORKER_GROUP_NOT_FOUND',
  workerGroupNameRequired: 'ORCH_WORKER_GROUP_NAME_REQUIRED',
  workerGroupOwned: 'ORCH_WORKER_GROUP_OWNED',
  environmentNameRequired: 'ORCH_ENVIRONMENT_NAME_REQUIRED',
  environmentOwned: 'ORCH_ENVIRONMENT_OWNED',
  queueFieldsRequired: 'ORCH_QUEUE_FIELDS_REQUIRED',
  queueOwned: 'ORCH_QUEUE_OWNED',
  clusterNameRequired: 'ORCH_CLUSTER_NAME_REQUIRED',
  clusterOwned: 'ORCH_CLUSTER_OWNED',
  taskGroupNameRequired: 'ORCH_TASK_GROUP_NAME_REQUIRED',
  taskGroupOwned: 'ORCH_TASK_GROUP_OWNED',
  taskGroupIdInvalid: 'ORCH_TASK_GROUP_ID_INVALID',
  taskGroupForbidden: 'ORCH_TASK_GROUP_FORBIDDEN',
  resourceFileNameRequired: 'ORCH_RESOURCE_FILE_NAME_REQUIRED',
  resourceFilePathRequired: 'ORCH_RESOURCE_FILE_PATH_REQUIRED',
  resourceFileOwned: 'ORCH_RESOURCE_FILE_OWNED',
  resourceFileForbidden: 'ORCH_RESOURCE_FILE_FORBIDDEN',
  projectNotFound: 'ORCH_PROJECT_NOT_FOUND',
  projectInvalid: 'DS_PROJECT_INVALID',
  monitorNodeTypeInvalid: 'ORCH_MONITOR_NODE_TYPE_INVALID',
  invalidPage: 'ORCH_INVALID_PAGE',
  invalidReleaseState: 'ORCH_INVALID_RELEASE_STATE',
  workflowDefinitionInvalid: 'DS_WORKFLOW_DEFINITION_INVALID',
  alarmTriggerInvalid: 'ORCH_ALARM_TRIGGER_INVALID',
  alarmChannelInvalid: 'ORCH_ALARM_CHANNEL_INVALID',
  alarmTimeoutRequired: 'ORCH_ALARM_TIMEOUT_REQUIRED',
  alarmTimeoutInvalid: 'ORCH_ALARM_TIMEOUT_INVALID',
  alarmRuleDuplicate: 'ORCH_ALARM_RULE_DUPLICATE',
  alarmRuleNotFound: 'ORCH_ALARM_RULE_NOT_FOUND',
  alarmDispatchFailed: 'ORCH_ALARM_DISPATCH_FAILED',
} as const)

/** 资源行通用归属标注（所有资源行都带这三个键）。 */
export interface OrchestrationResourceOwnership {
  /** 业务键：worker 分组用 name，环境/集群用 code，队列用 id 字符串 */
  resourceKey: string
  ownerId: number | null
  /** 当前登录用户是否可写（前端据此决定编辑/删除/共享按钮可见性） */
  canManage: boolean
}

export interface WorkerGroupRow extends OrchestrationResourceOwnership {
  id: number | null
  name: string
  addrList: string | null
  description: string | null
  /** CONFIG 来源的系统默认分组：只读，不可改名/删除 */
  systemDefault: boolean
  source: string | null
  createTime: string | null
  updateTime: string | null
}

export interface EnvironmentRow extends OrchestrationResourceOwnership {
  id: number | null
  /** 环境业务键（海豚 code） */
  code: string | null
  name: string
  config: string | null
  description: string | null
  /** 关联的 worker 分组名列表 */
  workerGroups: string[]
  createTime: string | null
  updateTime: string | null
}

export interface QueueRow extends OrchestrationResourceOwnership {
  /** 队列业务键（海豚 id 字符串） */
  id: string
  queue: string
  queueName: string
  createTime: string | null
  updateTime: string | null
}

export interface ClusterRow extends OrchestrationResourceOwnership {
  id: number | null
  /** 集群业务键（海豚 code） */
  code: string | null
  name: string
  config: string | null
  description: string | null
  createTime: string | null
  updateTime: string | null
}

export interface TaskGroupRow extends OrchestrationResourceOwnership {
  id: number | null
  /** 任务组业务键（海豚自增 id 字符串） */
  projectCode: string | null
  name: string
  description: string | null
  groupSize: number | null
  status: string | null
  createTime: string | null
  updateTime: string | null
}

export interface WorkerGroupDraft {
  name: string
  addrList?: string
  description?: string
}

export interface EnvironmentDraft {
  name: string
  config?: string
  description?: string
  workerGroups?: string[]
}

export interface QueueDraft {
  queue: string
  queueName: string
}

export interface ClusterDraft {
  name: string
  config?: string
  description?: string
}

/** 任务组创建载荷：``projectId`` 用于后端解析海豚 ``projectCode``（§10.10 R8）。 */
export interface TaskGroupDraft {
  projectId: number
  name: string
  description?: string
  groupSize?: number
}

/** 任务组更新载荷（不含 projectId：归属键是海豚 id）。 */
export interface TaskGroupUpdateDraft {
  name: string
  description?: string
  groupSize?: number
}

/* ---------- §10.10 R9 资源文件（全局文件树） ---------- */

/**
 * 资源文件节点（海豚 ``ResourceComponent`` 原样透传）。
 * 字段名沿用海豚线形态：``dirctory`` 是 DS 源码的拼写（``isDirctory`` 字段经
 * Jackson 命名后为 ``dirctory``），前端不改名。
 */
export interface ResourceFileNode {
  name: string
  currentDir: string
  /** 归属键：海豚相对路径 ``fullName``（节点表单 ``resourceList`` 回写值） */
  fullName: string
  description?: string | null
  /** 是否目录（海豚拼写 dirctory） */
  dirctory: boolean
  type: string | null
  children: ResourceFileNode[]
}

/** 资源文件重命名载荷：``fullName`` 定位，``name`` 为新名（无扩展名 = 目录）。 */
export interface ResourceFileRenamePayload {
  fullName: string
  name: string
}

export interface OrchestrationShareResult {
  kind: string
  resourceKey: string
  userId: number
}

/* ---------- §10.11 监控代理 ---------- */

export type OrchestrationHeartbeatState = 'online' | 'offline' | 'unknown'

/**
 * 单节点行（后端已把海豚 ``heartBeatInfo`` 私有 JSON 解析为结构化字段，
 * 前端只渲染，不再解析私有 JSON）。
 */
export interface OrchestrationServerRow {
  id: number | null
  host: string | null
  port: number | null
  serverDirectory: string | null
  createTime: string | null
  lastHeartbeatTime: string | null
  /** 心跳年龄（秒）；null 表示从未上报 */
  heartbeatAgeSeconds: number | null
  heartbeatState: OrchestrationHeartbeatState
  serverStatus: string | null
  cpuUsage: number | null
  memoryUsage: number | null
  diskUsage: number | null
  /** 海豚 3.4.3 ``BaseHeartBeat`` 不含 loadAverage，恒为 null（固定前端契约） */
  loadAverage: number | null
  jvmCpuUsage: number | null
  jvmMemoryUsage: number | null
  jvmHeapUsed: number | null
  jvmHeapMax: number | null
  jvmNonHeapUsed: number | null
  jvmNonHeapMax: number | null
  processId: number | null
  startTime: string | null
  reportTime: string | null
  workerGroup: string | null
  threadPoolUsage: number | null
  workerHostWeight: number | null
  /** 原始心跳负载（透传，供调试） */
  heartbeat: Record<string, unknown>
}

/** DB 连接池健康行（``monitor/databases`` 透传，state 已归一为大写）。 */
export interface OrchestrationDatabaseRow {
  dbType: string
  state: string
  maxConnections: number | null
  maxUsedConnections: number | null
  threadsConnections: number | null
  threadsRunningConnections: number | null
  date: string | null
}

export interface OrchestrationExecutorRow {
  [key: string]: unknown
}

export interface OrchestrationStateCountRow {
  state: string
  count: number
}

export interface OrchestrationTaskStateCount {
  totalCount: number
  taskInstanceStatusCounts: OrchestrationStateCountRow[]
}

export interface OrchestrationWorkflowStateCount {
  totalCount: number
  workflowInstanceStatusCounts: OrchestrationStateCountRow[]
}

export interface OrchestrationDefineUserCount {
  count: number
  userList: Record<string, unknown>[]
}

/* ---------- §10.10 R6 告警桥接（datara 项目级规则 + 触发记录） ---------- */

/**
 * 触发条件。海豚告警组/实例/插件一律不接入：失败由编排网关轮询实例状态感知；
 * 「失败重试耗尽」在海豚侧最终仍表现为实例 `FAILURE`，归入 `failure`，不单列。
 */
export type AlarmTrigger = 'failure' | 'timeout'

/** 告警通道：站内 / 邮件 / Webhook（短信未接供应商，契约不含）。 */
export type AlarmChannel = 'system' | 'email' | 'webhook'

/** 告警规则行；`workflowDefinitionCode = 0` 表示该项目全部工作流。 */
export interface AlarmRuleRow {
  id: number
  projectId: number
  workflowDefinitionCode: number
  trigger: AlarmTrigger
  channel: AlarmChannel
  /** 仅 `timeout` 触发使用；其余为 null */
  timeoutMinutes: number | null
  enabled: boolean
  ownerId: number | null
  createTime: string
  updateTime: string
}

/** 触发记录行：每次命中规则发送一条，`state` = `wait` / `sent` / `fail`。 */
export interface AlarmRecordRow {
  id: number
  ruleId: number
  projectId: number
  instanceId: number
  workflowDefinitionCode: number
  trigger: AlarmTrigger
  title: string
  content: string
  channel: AlarmChannel
  state: string
  createTime: string
}

export interface AlarmRuleDraft {
  projectId: number
  /** 0/undefined = 全部工作流 */
  workflowDefinitionCode?: number
  trigger: AlarmTrigger
  channel: AlarmChannel
  /** `trigger = 'timeout'` 时必填（正整数分钟） */
  timeoutMinutes?: number | null
  enabled?: boolean
}

export interface AlarmRuleUpdateDraft {
  channel?: AlarmChannel
  enabled?: boolean
  timeoutMinutes?: number | null
  workflowDefinitionCode?: number
}

/* ---------- 端点 ---------- */

const BASE = '/rebuild/orchestration'
const PRESERVE_ERROR = { preserveEnvelopeCode: true } as const

/** 路径段需转义：worker 分组名/环境 code/队列 id 均可能含特殊字符。 */
function segment(value: string | number): string {
  return encodeURIComponent(String(value))
}

/**
 * 查询串序列化（二进制下载专用）：与 `http.ts` 底座同口径 —— 剔除
 * undefined/null、键 camel→snake、值 encodeURIComponent。
 */
function queryText(query?: QueryParams): string {
  if (!query) return ''
  const qs = Object.entries(query)
    .filter(([, value]) => value !== undefined && value !== null)
    .map(([key, value]) => `${encodeURIComponent(camelToSnakeKey(key))}=${encodeURIComponent(String(value))}`)
    .join('&')
  return qs ? `?${qs}` : ''
}

/**
 * 二进制下载通道（`http.ts` 无 Blob 通道）：手动带 token 取原始响应，
 * 非 2xx 时解析包络保留 `code`/`msg` 后抛 `ContractApiError`。
 */
async function downloadResource(path: string, query?: QueryParams): Promise<Blob> {
  const token = getToken()
  const headers: Record<string, string> = token ? { [TOKEN_HEADER]: token } : {}
  const res = await fetch(`${HTTP_BASE}${path}${queryText(query)}`, { method: 'GET', headers })
  if (!res.ok) {
    const raw = await res.text().catch(() => '')
    let code: number | string = res.status
    let msg = `HTTP ${res.status} ${path}`
    try {
      const parsed = JSON.parse(raw) as { code?: number | string; msg?: string }
      if (parsed && parsed.code !== undefined) {
        code = parsed.code
        msg = parsed.msg ?? msg
      }
    } catch {
      /* 非 JSON 响应：保留 HTTP 状态码与默认文案 */
    }
    throw new ContractApiError({ httpStatus: res.status, code, msg })
  }
  return res.blob()
}

export const orchestrationApi = {
  /* ---------- §10.5 B 工作流定义列表 ---------- */
  listWorkflowDefinitions: (
    projectId: number,
    pageNo = 1,
    pageSize = 10,
    searchVal = '',
  ): Promise<WorkflowDefinitionListResult> =>
    getJson<WorkflowDefinitionListResult>(
      `${BASE}/workflow-definitions`,
      { projectId, pageNo, pageSize, searchVal },
      PRESERVE_ERROR,
    ),
  releaseWorkflowDefinition: (
    code: number,
    projectId: number,
    releaseState: WorkflowDefinitionReleaseState,
  ): Promise<Record<string, unknown>> =>
    postJson<Record<string, unknown>>(`${BASE}/workflow-definitions/${segment(code)}/release`, undefined, {
      ...PRESERVE_ERROR,
      query: { projectId, releaseState },
    }),
  deleteWorkflowDefinition: (code: number, projectId: number): Promise<Record<string, unknown>> =>
    deleteJson<Record<string, unknown>>(`${BASE}/workflow-definitions/${segment(code)}`, {
      ...PRESERVE_ERROR,
      query: { projectId },
    }),

  listWorkflowSchedules: (projectId: number, pageNo = 1, pageSize = 10): Promise<OrchestrationPaged<WorkflowScheduleRow>> =>
    getJson<OrchestrationPaged<WorkflowScheduleRow>>(
      `${BASE}/workflow-schedules`, { projectId, pageNo, pageSize }, PRESERVE_ERROR,
    ),
  setWorkflowScheduleOnline: (projectId: number, scheduleId: number, online: boolean): Promise<Record<string, unknown>> =>
    postJson<Record<string, unknown>>(
      `${BASE}/workflow-schedules/${segment(scheduleId)}/${online ? 'online' : 'offline'}`,
      undefined,
      { ...PRESERVE_ERROR, query: { projectId } },
    ),

  /* ---------- §10.10 R6 告警规则与触发记录 ---------- */

  /** 项目级告警规则列表（含停用规则；`workflowDefinitionCode = 0` = 全部工作流）。 */
  listAlarmRules: (projectId: number): Promise<AlarmRuleRow[]> =>
    getJson<AlarmRuleRow[]>(`${BASE}/alarm-rules`, { projectId }, PRESERVE_ERROR),
  createAlarmRule: (draft: AlarmRuleDraft): Promise<AlarmRuleRow> =>
    postJson<AlarmRuleRow>(`${BASE}/alarm-rules`, draft, PRESERVE_ERROR),
  updateAlarmRule: (ruleId: number, draft: AlarmRuleUpdateDraft): Promise<AlarmRuleRow> =>
    putJson<AlarmRuleRow>(`${BASE}/alarm-rules/${segment(ruleId)}`, draft, PRESERVE_ERROR),
  deleteAlarmRule: (ruleId: number): Promise<Record<string, unknown>> =>
    deleteJson<Record<string, unknown>>(`${BASE}/alarm-rules/${segment(ruleId)}`, PRESERVE_ERROR),
  /** 触发记录（最近优先；`limit` 1–500，默认 100）。 */
  listAlarmRecords: (projectId: number, limit = 100): Promise<AlarmRecordRow[]> =>
    getJson<AlarmRecordRow[]>(`${BASE}/alarm-records`, { projectId, limit }, PRESERVE_ERROR),

  /* ---------- §10.5 B 运行监控 ---------- */

  /** 工作流实例分页列表。query 键 camelCase，由 http.ts 转 snake_case。 */
  listWorkflowInstances: (query: WorkflowInstanceQuery): Promise<OrchestrationPaged<WorkflowInstanceRow>> =>
    getJson<OrchestrationPaged<WorkflowInstanceRow>>(`${BASE}/workflow-instances`, query, PRESERVE_ERROR),

  /** 单个实例详情（后端透传海豚 ``WorkflowInstance``）。 */
  getWorkflowInstance: (instanceId: number, projectId: number): Promise<Record<string, unknown>> =>
    getJson<Record<string, unknown>>(`${BASE}/workflow-instances/${segment(instanceId)}`, { projectId }, PRESERVE_ERROR),

  /** 实例任务树（海豚 ``.../{id}/tasks``）。 */
  listInstanceTasks: (instanceId: number, projectId: number): Promise<Record<string, unknown>[]> =>
    getJson<Record<string, unknown>[]>(`${BASE}/workflow-instances/${segment(instanceId)}/tasks`, { projectId }, PRESERVE_ERROR),

  /** 实例甘特图（海豚 ``GanttDto``）。 */
  getInstanceGantt: (instanceId: number, projectId: number): Promise<InstanceGantt> =>
    getJson<InstanceGantt>(`${BASE}/workflow-instances/${segment(instanceId)}/gantt`, { projectId }, PRESERVE_ERROR),

  /** 实例变量只读查看（§10.7 D3）。 */
  getInstanceVariables: (instanceId: number, projectId: number): Promise<InstanceVariables> =>
    getJson<InstanceVariables>(`${BASE}/workflow-instances/${segment(instanceId)}/variables`, { projectId }, PRESERVE_ERROR),

  /** 任务实例分页列表（跨实例维度，可按 ``workflowInstanceId`` 收敛）。 */
  listTaskInstances: (query: TaskInstanceQuery): Promise<OrchestrationPaged<TaskInstanceRow>> =>
    getJson<OrchestrationPaged<TaskInstanceRow>>(`${BASE}/task-instances`, query, PRESERVE_ERROR),

  /** 任务实例日志（海豚 ``LoggerController /log/detail``，``lineNum``/``message``）。 */
  getTaskInstanceLog: (
    taskInstanceId: number,
    projectId: number,
    skipLineNum = 0,
    limit = 200,
  ): Promise<TaskInstanceLog[]> =>
    getJson<TaskInstanceLog[]>(
      `${BASE}/task-instances/${segment(taskInstanceId)}/log`,
      { projectId, skipLineNum, limit },
      PRESERVE_ERROR,
    ),

  /** 启动实例（``dryRun: true`` = 试运行，§10.7 B1）。 */
  startWorkflowInstance: (draft: StartWorkflowInstanceDraft): Promise<Record<string, unknown>> =>
    postJson<Record<string, unknown>>(`${BASE}/workflow-instances/start`, draft, PRESERVE_ERROR),

  /** 实例控制：停止 / 暂停 / 恢复挂起 / 失败重试 / 重跑。 */
  controlWorkflowInstance: (
    instanceId: number,
    projectId: number,
    executeType: WorkflowInstanceExecuteType,
  ): Promise<Record<string, unknown>> =>
    postJson<Record<string, unknown>>(
      `${BASE}/workflow-instances/${segment(instanceId)}/control`,
      { projectId, executeType },
      PRESERVE_ERROR,
    ),

  /* ---------- §10.10 R1 Worker 分组 ---------- */
  listWorkerGroups: (): Promise<WorkerGroupRow[]> =>
    getJson<WorkerGroupRow[]>(`${BASE}/worker-groups`, undefined, PRESERVE_ERROR),
  createWorkerGroup: (draft: WorkerGroupDraft): Promise<Record<string, unknown>> =>
    postJson<Record<string, unknown>>(`${BASE}/worker-groups`, draft, PRESERVE_ERROR),
  updateWorkerGroup: (name: string, draft: WorkerGroupDraft): Promise<Record<string, unknown>> =>
    putJson<Record<string, unknown>>(`${BASE}/worker-groups/${segment(name)}`, draft, PRESERVE_ERROR),
  deleteWorkerGroup: (name: string): Promise<Record<string, unknown>> =>
    deleteJson<Record<string, unknown>>(`${BASE}/worker-groups/${segment(name)}`, PRESERVE_ERROR),

  /* ---------- §10.10 R2 环境管理 ---------- */
  listEnvironments: (): Promise<EnvironmentRow[]> =>
    getJson<EnvironmentRow[]>(`${BASE}/environments`, undefined, PRESERVE_ERROR),
  createEnvironment: (draft: EnvironmentDraft): Promise<Record<string, unknown>> =>
    postJson<Record<string, unknown>>(`${BASE}/environments`, draft, PRESERVE_ERROR),
  updateEnvironment: (code: string, draft: EnvironmentDraft): Promise<Record<string, unknown>> =>
    putJson<Record<string, unknown>>(`${BASE}/environments/${segment(code)}`, draft, PRESERVE_ERROR),
  deleteEnvironment: (code: string): Promise<Record<string, unknown>> =>
    deleteJson<Record<string, unknown>>(`${BASE}/environments/${segment(code)}`, PRESERVE_ERROR),

  /* ---------- §10.10 R3 Yarn 队列 ---------- */
  listQueues: (): Promise<QueueRow[]> => getJson<QueueRow[]>(`${BASE}/queues`, undefined, PRESERVE_ERROR),
  createQueue: (draft: QueueDraft): Promise<Record<string, unknown>> =>
    postJson<Record<string, unknown>>(`${BASE}/queues`, draft, PRESERVE_ERROR),
  updateQueue: (queueId: string | number, draft: QueueDraft): Promise<Record<string, unknown>> =>
    putJson<Record<string, unknown>>(`${BASE}/queues/${segment(queueId)}`, draft, PRESERVE_ERROR),
  deleteQueue: (queueId: string | number): Promise<Record<string, unknown>> =>
    deleteJson<Record<string, unknown>>(`${BASE}/queues/${segment(queueId)}`, PRESERVE_ERROR),

  /* ---------- §10.10 R4 集群管理 ---------- */
  listClusters: (): Promise<ClusterRow[]> => getJson<ClusterRow[]>(`${BASE}/clusters`, undefined, PRESERVE_ERROR),
  createCluster: (draft: ClusterDraft): Promise<Record<string, unknown>> =>
    postJson<Record<string, unknown>>(`${BASE}/clusters`, draft, PRESERVE_ERROR),
  updateCluster: (code: string, draft: ClusterDraft): Promise<Record<string, unknown>> =>
    putJson<Record<string, unknown>>(`${BASE}/clusters/${segment(code)}`, draft, PRESERVE_ERROR),
  deleteCluster: (code: string): Promise<Record<string, unknown>> =>
    deleteJson<Record<string, unknown>>(`${BASE}/clusters/${segment(code)}`, PRESERVE_ERROR),

  /* ---------- §10.10 R8 任务组（datara 项目级资源） ---------- */
  /** 任务组列表：projectId 用于后端解析海豚 projectCode 后按项目拉取。 */
  listTaskGroups: (projectId: number): Promise<TaskGroupRow[]> =>
    getJson<TaskGroupRow[]>(`${BASE}/task-groups`, { projectId }, PRESERVE_ERROR),
  createTaskGroup: (draft: TaskGroupDraft): Promise<Record<string, unknown>> =>
    postJson<Record<string, unknown>>(`${BASE}/task-groups`, draft, PRESERVE_ERROR),
  updateTaskGroup: (taskGroupId: string | number, draft: TaskGroupUpdateDraft): Promise<Record<string, unknown>> =>
    putJson<Record<string, unknown>>(`${BASE}/task-groups/${segment(taskGroupId)}`, draft, PRESERVE_ERROR),
  /**
   * 删除任务组：海豚 3.4.3 无物理删除端点，后端映射为 ``close-task-group``
   * （关闭后不再可被节点引用），并释放 datara 归属记录。
   */
  deleteTaskGroup: (taskGroupId: string | number): Promise<Record<string, unknown>> =>
    deleteJson<Record<string, unknown>>(`${BASE}/task-groups/${segment(taskGroupId)}`, PRESERVE_ERROR),

  /* ---------- §10.10 R9 资源文件（全局文件树） ---------- */
  /** 资源文件目录树（海豚 `/resources/list?type=FILE`，按 owner 裁剪）。 */
  listResourceFiles: (): Promise<ResourceFileNode[]> =>
    getJson<ResourceFileNode[]>(`${BASE}/resources`, undefined, PRESERVE_ERROR),
  /**
   * 上传/建目录：`FormData` 含 `name`（必填）、`currentDir`（可选）、`file`（可选）。
   * 无 `file` 字段时后端转 `POST /resources/directory` 建目录；multipart 由 fetch 自置
   * boundary，故**不设** `Content-Type`。
   */
  createResourceFile: (form: FormData): Promise<Record<string, unknown>> =>
    request<Record<string, unknown>>(`${BASE}/resources`, { method: 'POST', body: form, preserveEnvelopeCode: true }),
  /** 重命名：`fullName` 定位（目录或文件），`name` 为新名（无扩展名 = 目录）。 */
  renameResourceFile: (payload: ResourceFileRenamePayload): Promise<Record<string, unknown>> =>
    putJson<Record<string, unknown>>(`${BASE}/resources`, payload, PRESERVE_ERROR),
  /** 删除：递归删目录或单文件，`full_name` 为海豚相对路径。 */
  deleteResourceFile: (fullName: string): Promise<Record<string, unknown>> =>
    deleteJson<Record<string, unknown>>(`${BASE}/resources`, { ...PRESERVE_ERROR, query: { fullName } }),
  /** 下载：返回二进制 Blob（`http.ts` 无 Blob 通道，走本地 `downloadResource`）。 */
  downloadResourceFile: (fullName: string): Promise<Blob> =>
    downloadResource(`${BASE}/resources/download`, { fullName }),

  /* ---------- §10.10 显式共享 ---------- */
  share: (kind: OrchestrationResourceKind, resourceKey: string, username: string): Promise<OrchestrationShareResult> =>
    postJson<OrchestrationShareResult>(
      `${BASE}/resources/${kind}/${segment(resourceKey)}/share`,
      { username },
      PRESERVE_ERROR,
    ),
  unshare: (kind: OrchestrationResourceKind, resourceKey: string, username: string): Promise<OrchestrationShareResult> =>
    deleteJson<OrchestrationShareResult>(`${BASE}/resources/${kind}/${segment(resourceKey)}/share`, {
      ...PRESERVE_ERROR,
      query: { username },
    }),

  /* ---------- §10.11 监控代理 ---------- */
  fetchMonitorServers: (nodeType: OrchestrationNodeType): Promise<OrchestrationServerRow[]> =>
    getJson<OrchestrationServerRow[]>(`${BASE}/monitor/${nodeType}`, undefined, PRESERVE_ERROR),
  fetchMonitorDatabases: (): Promise<OrchestrationDatabaseRow[]> =>
    getJson<OrchestrationDatabaseRow[]>(`${BASE}/monitor/databases`, undefined, PRESERVE_ERROR),
  fetchMasterWorkflowExecutors: (masterAddress: string): Promise<OrchestrationExecutorRow[]> =>
    getJson<OrchestrationExecutorRow[]>(`${BASE}/monitor/masters/workflow-executors`, { masterAddress }, PRESERVE_ERROR),
  fetchWorkerTaskExecutors: (serverAddress: string): Promise<OrchestrationExecutorRow[]> =>
    getJson<OrchestrationExecutorRow[]>(`${BASE}/monitor/workers/task-executors`, { serverAddress }, PRESERVE_ERROR),
  fetchTaskStateCount: (projectId: number, startDate?: string, endDate?: string): Promise<OrchestrationTaskStateCount> =>
    getJson<OrchestrationTaskStateCount>(`${BASE}/monitor/task-state-count`, { projectId, startDate, endDate }, PRESERVE_ERROR),
  fetchWorkflowStateCount: (
    projectId: number,
    startDate?: string,
    endDate?: string,
  ): Promise<OrchestrationWorkflowStateCount> =>
    getJson<OrchestrationWorkflowStateCount>(
      `${BASE}/monitor/workflow-state-count`,
      { projectId, startDate, endDate },
      PRESERVE_ERROR,
    ),
  fetchDefineUserCount: (projectId: number): Promise<OrchestrationDefineUserCount> =>
    getJson<OrchestrationDefineUserCount>(`${BASE}/monitor/define-user-count`, { projectId }, PRESERVE_ERROR),
}
