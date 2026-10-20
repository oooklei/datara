/**
 * FE 侧 rebuild 域表结构类型定义（与后端 SQLAlchemy 模型对齐）。
 *
 * 用途：FE-14 门 2「数据模型冻结」验收——FE types ↔ 表结构类型契约 vitest 全绿。
 * 对齐基准：
 *   - datara-backend/rebuild/workflow/models.py（工作流域七模型）
 *   - datara-backend/rebuild/execution/models.py（运行表六张）
 *   - datara-backend/rebuild/stream/models.py（流表五张）
 *   - datara-backend/rebuild/trial/models.py（草稿快照）
 *   - datara-backend/rebuild/api/app.py L169-207（建表清单）
 *
 * 命名约定：
 *   - 后端 snake_case → FE camelCase（与 adapterKit §2.1 命名映射一致）
 *   - 后端 DateTime → FE string（ISO 8601）
 *   - 后端 nullable → FE `| null`
 *   - 后端 server_default 时间戳 → FE 只读（由 DB 生成，FE 不写入）
 *
 * 注意：本文件为纯类型定义，不含运行时逻辑。
 */

/* ======================================================================== */
/* 工作流域七模型（workflow/models.py）                                        */
/* ======================================================================== */

/** workflow_definition — 每项目工作流（编辑草稿元数据） */
export interface WorkflowDefinition {
  id: number
  projectId: number
  name: string
  description: string
  /** 最新已发布版本号；null = 从未发布 */
  currentVersion: number | null
  /** DB 生成（§9 时间戳约定） */
  createdAt: string
  updatedAt: string
}

/** workflow_version — 不可变发布快照 */
export interface WorkflowVersion {
  id: number
  definitionId: number
  version: number
  /** DRAFT | PUBLISHED | RUNNING | DISABLED | ARCHIVED */
  status: string
  remark: string
  /** sha256 over canonical snapshot node/edge JSON（不可变锚点） */
  snapshotDigest: string
  publishedAt: string
  publishedBy: number | null
  createdAt: string
  updatedAt: string
}

/** workflow_node — 草稿节点（versionId null）或发布快照副本 */
export interface WorkflowNode {
  id: number
  definitionId: number
  /** null = 编辑草稿行；有值 = 版本快照内的不可变副本 */
  versionId: number | null
  /** 定义内稳定节点编码（草稿 upsert 键） */
  nodeCode: string
  /** §3.2 首阶段 Palette（任务类型 + 流组件），repository 校验 VALID_NODE_TYPES */
  nodeType: string
  name: string
  /** 节点参数 verbatim（JSON 对象） */
  paramsJson: string
  positionX: number | null
  positionY: number | null
  createdAt: string
  updatedAt: string
}

/** workflow_edge — 节点间有向连接（草稿或快照副本） */
export interface WorkflowEdge {
  id: number
  definitionId: number
  versionId: number | null
  fromNode: string
  toNode: string
  /** 分支标签（如条件分支名称）；空串为普通边 */
  name: string
  createdAt: string
  updatedAt: string
}

/** workflow_schedule — 每定义调度绑定（仅建模） */
export interface WorkflowSchedule {
  id: number
  definitionId: number
  cronExpr: string
  startTime: string | null
  endTime: string | null
  enabled: boolean
  createdAt: string
  updatedAt: string
}

/** workflow_publish_record — 追加式发布事件日志（每次发布一行） */
export interface WorkflowPublishRecord {
  id: number
  definitionId: number
  versionId: number
  version: number
  publishedBy: number | null
  remark: string
  publishedAt: string
  createdAt: string
  updatedAt: string
}

/* ======================================================================== */
/* 草稿快照（trial/models.py）                                               */
/* ======================================================================== */

/** workflow_draft_snapshot — TRIAL 运行不可变输入（编辑草稿时点捕获） */
export interface WorkflowDraftSnapshot {
  id: number
  definitionId: number
  /** SHA256 over canonical snapshot node/edge JSON（不可变锚点） */
  snapshotDigest: string
  /** 完整草稿图载荷（nodes + edges JSON） */
  nodeSnapshotJson: string
  edgeSnapshotJson: string
  /** §4.1 快照生命周期：ACTIVE（可用于 trial）| STALE（被新 digest 取代） */
  status: string
  createdBy: number | null
  createdAt: string
  updatedAt: string
}

/* ======================================================================== */
/* 运行表六张（execution/models.py）                                         */
/* ======================================================================== */

/**
 * workflow_instance — 一次工作流运行（TRIAL / FORMAL / STREAM）。
 * 携带 §9 三契约时间戳 created_at/updated_at/generated_at（DB 生成，非空）。
 */
export interface WorkflowInstance {
  id: number
  workflowId: number
  /** 不可变工作流版本的纯整数引用（跨域解耦） */
  workflowVersionId: number
  /** TRIAL 运行绑定草稿快照；FORMAL 运行绑定 workflowVersionId */
  trialSnapshotId: number | null
  /** TRIAL | FORMAL | STREAM */
  instanceType: string
  status: string
  /** §13.3 触发类型（MANUAL/CRON/DEPENDENCY/EVENT/TRIAL） */
  triggerType: string | null
  startedAt: string | null
  finishedAt: string | null
  /** §9 契约时间戳（DB 生成，非空） */
  createdAt: string
  updatedAt: string
  generatedAt: string
}

/** task_instance — 工作流运行内单个任务；重试为 attempt */
export interface TaskInstance {
  id: number
  workflowInstanceId: number
  taskId: string
  status: string
  /** 最新 attempt 指针（0 = 尚无 attempt） */
  currentAttemptNo: number
  startedAt: string | null
  finishedAt: string | null
  createdAt: string
  updatedAt: string
  generatedAt: string
}

/** task_instance_attempt — 每次重试执行切片，attempt_no 隔离 */
export interface TaskAttempt {
  id: number
  taskInstanceId: number
  attemptNo: number
  status: string
  startedAt: string | null
  finishedAt: string | null
  createdAt: string
  updatedAt: string
  generatedAt: string
}

/** task_instance_log — 诊断日志行，attempt 作用域（非统计源） */
export interface RunLog {
  id: number
  taskInstanceId: number
  attemptNo: number
  level: string
  message: string
  createdAt: string
  updatedAt: string
  generatedAt: string
}

/** task_instance_output — 执行器输出载荷，attempt 作用域，verbatim */
export interface RunOutput {
  id: number
  taskInstanceId: number
  attemptNo: number
  /** 执行器输出 verbatim（JSON 透传，不推导） */
  outputJson: string
  createdAt: string
  updatedAt: string
  generatedAt: string
}

/** execution_event — 追加式运行事件流；兼作 §5.4 统计回执 */
export interface ExecutionEvent {
  id: number
  workflowInstanceId: number
  taskInstanceId: number | null
  attemptNo: number | null
  eventKind: string
  payloadJson: string | null
  /** 流时间读取用（DB 生成） */
  eventTime: string
  createdAt: string
  updatedAt: string
  generatedAt: string
}

/* ======================================================================== */
/* 流表五张（stream/models.py）                                              */
/* ======================================================================== */

/** stream_job — 流作业（独立于批工作流实例） */
export interface StreamJob {
  id: number
  name: string
  workflowId: number
  /** 显式 crosswalk 到 legacy common.models.StreamJob.id；null 保持新域独立 */
  legacyJobId: number | null
  mqTopic: string
  /** §8 生产者节点模式配置 verbatim（JSON） */
  runtimeConfig: string
  /** 八状态机（§13.7）：CREATED/STARTING/RUNNING/PAUSED/STOPPING/STOPPED/FAILED/RECOVERING */
  state: string
  attemptNo: number
  startedAt: string | null
  finishedAt: string | null
  createdAt: string
  updatedAt: string
}

/** stream_checkpoint — 每分区消费者位点（故障恢复用） */
export interface StreamCheckpoint {
  id: number
  jobId: number
  partitionId: string
  offsetValue: number
  /** 恢复载荷（消费者组/处理器状态）verbatim JSON */
  payload: string
  eventTime: string
  createdAt: string
  updatedAt: string
}

/** stream_metric_snapshot — 每作业一个观测快照（§8 指标） */
export interface StreamMetricSnapshot {
  id: number
  jobId: number
  attemptNo: number
  /** 速率（records/s）与累积计数 */
  produceRate: number
  consumeRate: number
  processRate: number
  inputCount: number
  outputCount: number
  successCount: number
  failureCount: number
  skippedCount: number
  duplicateCount: number
  backlog: number
  offsetValue: number
  /** 窗口聚合结果 verbatim JSON */
  windowResult: string
  capturedAt: string
  createdAt: string
  updatedAt: string
}

/** stream_failure_event — 错误样本行（观测页用） */
export interface StreamFailureEvent {
  id: number
  jobId: number
  attemptNo: number
  errorType: string
  sampleData: string
  eventTime: string
  createdAt: string
  updatedAt: string
}

/** stream_recovery_event — 恢复生命周期事件（流观测 API 暴露） */
export interface StreamRecoveryEvent {
  id: number
  jobId: number
  kind: string
  detail: string
  eventTime: string
  createdAt: string
  updatedAt: string
}

/* ======================================================================== */
/* 类型契约测试辅助（FE-14 门 2 验收用）                                      */
/* ======================================================================== */

/**
 * 表结构对齐核验辅助类型：
 * 确保 FE 类型与后端模型字段一一对应（编译期检查）。
 * 运行时由 vitest 契约测试验证。
 */
export interface RebuildTableContract {
  /** 工作流域七模型 */
  workflowDefinition: WorkflowDefinition
  workflowVersion: WorkflowVersion
  workflowNode: WorkflowNode
  workflowEdge: WorkflowEdge
  workflowSchedule: WorkflowSchedule
  workflowPublishRecord: WorkflowPublishRecord
  workflowDraftSnapshot: WorkflowDraftSnapshot
  /** 运行表六张 */
  workflowInstance: WorkflowInstance
  taskInstance: TaskInstance
  taskAttempt: TaskAttempt
  runLog: RunLog
  runOutput: RunOutput
  executionEvent: ExecutionEvent
  /** 流表五张 */
  streamJob: StreamJob
  streamCheckpoint: StreamCheckpoint
  streamMetricSnapshot: StreamMetricSnapshot
  streamFailureEvent: StreamFailureEvent
  streamRecoveryEvent: StreamRecoveryEvent
}
