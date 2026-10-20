/**
 * 服务出口：按 VITE_API_MODE 切换真实后端 / mock（F9，§7.1）。
 * - 'real'（默认）→ graphApi.realGraphService
 * - 'mock' → localStorage mock 实现（纯前端测试保留）
 * 既有 import 路径（各视图）统一改引此处；mock 模块保留供单测直接引用。
 * 其余视图依赖的 dataStore/seed 等 mock 数据 I1 不切换（01 §6 适配清单分摊各增量）。
 */
import type { IGraphService } from './types'
import { realGraphService } from './graphApi'
import { graphService as mockGraphService } from './mock/graphService'
import { isMock } from './apiMode'

export { apiMode, isMock } from './apiMode'

export const graphService: IGraphService = isMock ? mockGraphService : realGraphService

export {
  listDefinitions, createDefinition, deleteDefinition,
  listVariables, saveVariable, deleteVariable, listInstances, listInstancesPage,
  /* I3 调度执行（§13） */
  listSchedules, createSchedule, updateSchedule, deleteSchedule,
  onlineSchedule, offlineSchedule, previewCrontab,
  runWorkflow, complementWorkflow, publishWorkflow, offlineWorkflow,
  /* 实例/任务操作 */
  getInstanceDetail, stopInstance, rerunInstance, rerunFailedTasks, resumeFromNodes,
  getTaskLog, listRuntimeNodes,
  /* I7 F53 SSH 运行节点 */
  listSshNodes,
  /* F56d 任务标签（保存打标与候选池过滤共用） */
  SYNC_TAG, ETL_TAG, STREAM_TAG,
  /* I11 分类目录 + 删除实例日志（I14：批量删除） */
  listCategories, createCategory, deleteCategory, setWfTags, deleteInstanceLogs, deleteInstanceLogsBatch,
  /* 实例状态 SSE 流 */
  streamInstanceEvents,
} from './graphApi'

export {
  /* I8 流任务（F40/F41） */
  listStreamJobs, getStreamJob, startStreamJob, stopStreamJob, deleteStreamJob, getStreamLogs, pollStreamData,
  streamSseUrl, streamWsUrl,
} from './streamApi'

export type { StreamJobRow, StreamDataPage } from './streamApi'
export { listAlertNotifications } from './alertApi'
export type { AlertNotification } from './alertApi'

export type {
  DefinitionMeta, InstanceRow,
  ScheduleRow, ScheduleBody, RuntimeNodeRow,
  SshNodeRow,
  CategoryRow,
  CreateDefinitionOpts,
  DeleteLogsResult,
  TaskStateEvent, InstanceFinishedEvent, InstanceStreamHandlers,
} from './graphApi'

/* ---------- rebuild/* 契约出口登记（FE-01 修订 2026-10-19） ----------
 * 统一登记 10 契约工厂 + 契约接口类型，消除验证页/正式页双轨 import。
 * 契约文件位于 services/rebuild/，工厂模式 createXxxContract() 统一。
 * 接线状态：GREEN 8 项（variable/dependency/resource/syncComponent/sqlIde/metrics/stream/adapterKit）；
 *           RED 3 项（schedule/sqlIdeDdl/aiTools，后端接入前抛 *_NOT_WIRED）。
 * 横幅状态词表见 services/rebuild/bannerStatus.ts。
 */
export {
  createVariableContract,
  type VariableContract,
  type VariableContext,
  type VariableDefinition,
  type VariableScope,
  R2_VARIABLE_CONTRACT_METHODS,
  R2_VARIABLE_NOT_WIRED,
  VARIABLE_SCOPE_PRIORITY,
} from './rebuild/variableApi'

export {
  createDependencyContract,
  type DependencyContract,
  type DependencyGroup,
  type DependencyCondition,
  type DependencyVerdict,
  R4_DEPENDENCY_CONTRACT_METHODS,
  R4_DEPENDENCY_NOT_WIRED,
} from './rebuild/dependencyApi'

export {
  createResourceContract,
  type ResourceContract,
  type ResourceKind,
  type ResourceVersion,
  type ResourceMeta,
  R4_RESOURCE_CONTRACT_METHODS,
  R4_RESOURCE_NOT_WIRED,
  RESOURCE_MAX_SIZE_BYTES,
  RESOURCE_ALLOWED_EXTENSIONS,
} from './rebuild/resourceApi'

export {
  createSyncComponentContract,
  type SyncContract,
  type SyncPlanInput,
  type SyncCapabilities,
  type SyncMapping,
  type SyncColumn,
} from './rebuild/syncComponentApi'

export {
  createSqlIdeContract,
  type SqlIdeContract,
  type SqlResultPage,
  type HistoryEntry,
  type ScriptEntry,
  R5A_CONTRACT_METHODS,
} from './rebuild/sqlIdeApi'

export {
  createSqlIdeDdlContract,
  type SqlIdeDdlContract,
  type DdlPolicyReport,
  type DdlExecutionRecord,
  R5B_CONTRACT_METHODS,
  R5B_BACKEND_NOT_WIRED,
} from './rebuild/sqlIdeDdlApi'

export {
  createScheduleContract,
  type ScheduleContract,
  type TriggerKind,
  type ScheduleAlert,
  R6_CONTRACT_METHODS,
  R6_SCHEDULER_NOT_WIRED,
} from './rebuild/scheduleApi'

export {
  createMetricsContract,
  type MetricsContract,
  type MetricValue,
  type TimeWindowQuery,
  R7_CONTRACT_METHODS,
  R7_METRICS_NOT_WIRED,
} from './rebuild/metricsApi'

export {
  createStreamContract,
  type StreamContract,
  I8_CONTRACT_METHODS,
  I8_STREAM_NOT_WIRED,
} from './rebuild/streamApi'

export {
  createAiToolsContract,
  type R8AToolsContract,
  type R8ATool,
  R8A_CONTRACT_METHODS,
  R8A_TOOLS,
} from './rebuild/aiToolsApi'

export {
  unwrapEnvelope,
  ContractApiError,
  snakeToCamel,
  camelToSnake,
  wireIdToString,
  numberToWireId,
  ID_NORMALIZATION_FAILED,
} from './rebuild/adapterKit'
