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
  getInstanceDetail, stopInstance, rerunInstance, rerunFailedTasks,
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
  DeleteLogsResult,
  TaskStateEvent, InstanceFinishedEvent, InstanceStreamHandlers,
} from './graphApi'