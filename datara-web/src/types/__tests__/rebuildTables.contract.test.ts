/**
 * FE 类型 ↔ 后端表结构对齐契约测试（FE-14 门 2 验收）。
 *
 * 验证：rebuildTables.ts 定义的 TypeScript 接口与后端 SQLAlchemy 模型字段一一对应。
 * 对齐基准：
 *   - datara-backend/rebuild/workflow/models.py
 *   - datara-backend/rebuild/execution/models.py
 *   - datara-backend/rebuild/stream/models.py
 *   - datara-backend/rebuild/trial/models.py
 *
 * 测试策略：
 *   1. 编译期：TypeScript 编译器检查接口字段类型
 *   2. 运行时：vitest 验证字段存在性与类型契约
 */
import { describe, expect, it } from 'vitest'
import type {
  WorkflowDefinition,
  WorkflowVersion,
  WorkflowNode,
  WorkflowEdge,
  WorkflowSchedule,
  WorkflowPublishRecord,
  WorkflowDraftSnapshot,
  WorkflowInstance,
  TaskInstance,
  TaskAttempt,
  RunLog,
  RunOutput,
  ExecutionEvent,
  StreamJob,
  StreamCheckpoint,
  StreamMetricSnapshot,
  StreamFailureEvent,
  StreamRecoveryEvent,
} from '../rebuildTables'

/* ---------- 工作流域七模型字段存在性 ---------- */

describe('WorkflowDefinition ↔ workflow_definition 表字段对齐', () => {
  it('has all 7 fields matching backend model', () => {
    const sample: WorkflowDefinition = {
      id: 1,
      projectId: 1,
      name: 'test-workflow',
      description: '',
      currentVersion: null,
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'projectId', 'name', 'description', 'currentVersion', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

describe('WorkflowVersion ↔ workflow_version 表字段对齐', () => {
  it('has all 10 fields matching backend model', () => {
    const sample: WorkflowVersion = {
      id: 1,
      definitionId: 1,
      version: 1,
      status: 'PUBLISHED',
      remark: '',
      snapshotDigest: 'abc123',
      publishedAt: '2026-10-19T00:00:00Z',
      publishedBy: null,
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'definitionId', 'version', 'status', 'remark', 'snapshotDigest', 'publishedAt', 'publishedBy', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

describe('WorkflowNode ↔ workflow_node 表字段对齐', () => {
  it('has all 11 fields matching backend model', () => {
    const sample: WorkflowNode = {
      id: 1,
      definitionId: 1,
      versionId: null,
      nodeCode: 'node-1',
      nodeType: 'SQL',
      name: 'Test Node',
      paramsJson: '{}',
      positionX: null,
      positionY: null,
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'definitionId', 'versionId', 'nodeCode', 'nodeType', 'name', 'paramsJson', 'positionX', 'positionY', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

describe('WorkflowEdge ↔ workflow_edge 表字段对齐', () => {
  it('has all 8 fields matching backend model', () => {
    const sample: WorkflowEdge = {
      id: 1,
      definitionId: 1,
      versionId: null,
      fromNode: 'node-1',
      toNode: 'node-2',
      name: '',
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'definitionId', 'versionId', 'fromNode', 'toNode', 'name', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

describe('WorkflowSchedule ↔ workflow_schedule 表字段对齐', () => {
  it('has all 8 fields matching backend model', () => {
    const sample: WorkflowSchedule = {
      id: 1,
      definitionId: 1,
      cronExpr: '0 0 * * *',
      startTime: null,
      endTime: null,
      enabled: true,
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'definitionId', 'cronExpr', 'startTime', 'endTime', 'enabled', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

describe('WorkflowPublishRecord ↔ workflow_publish_record 表字段对齐', () => {
  it('has all 9 fields matching backend model', () => {
    const sample: WorkflowPublishRecord = {
      id: 1,
      definitionId: 1,
      versionId: 1,
      version: 1,
      publishedBy: null,
      remark: '',
      publishedAt: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'definitionId', 'versionId', 'version', 'publishedBy', 'remark', 'publishedAt', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

describe('WorkflowDraftSnapshot ↔ workflow_draft_snapshot 表字段对齐', () => {
  it('has all 9 fields matching backend model', () => {
    const sample: WorkflowDraftSnapshot = {
      id: 1,
      definitionId: 1,
      snapshotDigest: 'abc123',
      nodeSnapshotJson: '{}',
      edgeSnapshotJson: '{}',
      status: 'ACTIVE',
      createdBy: null,
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'definitionId', 'snapshotDigest', 'nodeSnapshotJson', 'edgeSnapshotJson', 'status', 'createdBy', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

/* ---------- 运行表六张字段存在性 ---------- */

describe('WorkflowInstance ↔ workflow_instance 表字段对齐', () => {
  it('has all 13 fields matching backend model (含 §9 三契约时间戳)', () => {
    const sample: WorkflowInstance = {
      id: 1,
      workflowId: 1,
      workflowVersionId: 1,
      trialSnapshotId: null,
      instanceType: 'FORMAL',
      status: 'RUNNING',
      triggerType: null,
      startedAt: null,
      finishedAt: null,
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
      generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'workflowId', 'workflowVersionId', 'trialSnapshotId', 'instanceType', 'status', 'triggerType', 'startedAt', 'finishedAt', 'createdAt', 'updatedAt', 'generatedAt'].sort(),
    )
  })
})

describe('TaskInstance ↔ task_instance 表字段对齐', () => {
  it('has all 10 fields matching backend model', () => {
    const sample: TaskInstance = {
      id: 1,
      workflowInstanceId: 1,
      taskId: 'task-1',
      status: 'RUNNING',
      currentAttemptNo: 0,
      startedAt: null,
      finishedAt: null,
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
      generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'workflowInstanceId', 'taskId', 'status', 'currentAttemptNo', 'startedAt', 'finishedAt', 'createdAt', 'updatedAt', 'generatedAt'].sort(),
    )
  })
})

describe('TaskAttempt ↔ task_instance_attempt 表字段对齐', () => {
  it('has all 9 fields matching backend model', () => {
    const sample: TaskAttempt = {
      id: 1,
      taskInstanceId: 1,
      attemptNo: 1,
      status: 'RUNNING',
      startedAt: null,
      finishedAt: null,
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
      generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'taskInstanceId', 'attemptNo', 'status', 'startedAt', 'finishedAt', 'createdAt', 'updatedAt', 'generatedAt'].sort(),
    )
  })
})

describe('RunLog ↔ task_instance_log 表字段对齐', () => {
  it('has all 8 fields matching backend model', () => {
    const sample: RunLog = {
      id: 1,
      taskInstanceId: 1,
      attemptNo: 1,
      level: 'INFO',
      message: 'test',
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
      generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'taskInstanceId', 'attemptNo', 'level', 'message', 'createdAt', 'updatedAt', 'generatedAt'].sort(),
    )
  })
})

describe('RunOutput ↔ task_instance_output 表字段对齐', () => {
  it('has all 7 fields matching backend model', () => {
    const sample: RunOutput = {
      id: 1,
      taskInstanceId: 1,
      attemptNo: 1,
      outputJson: '{}',
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
      generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'taskInstanceId', 'attemptNo', 'outputJson', 'createdAt', 'updatedAt', 'generatedAt'].sort(),
    )
  })
})

describe('ExecutionEvent ↔ execution_event 表字段对齐', () => {
  it('has all 10 fields matching backend model', () => {
    const sample: ExecutionEvent = {
      id: 1,
      workflowInstanceId: 1,
      taskInstanceId: null,
      attemptNo: null,
      eventKind: 'DISPATCH',
      payloadJson: null,
      eventTime: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
      generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'workflowInstanceId', 'taskInstanceId', 'attemptNo', 'eventKind', 'payloadJson', 'eventTime', 'createdAt', 'updatedAt', 'generatedAt'].sort(),
    )
  })
})

/* ---------- 流表五张字段存在性 ---------- */

describe('StreamJob ↔ stream_job 表字段对齐', () => {
  it('has all 12 fields matching backend model', () => {
    const sample: StreamJob = {
      id: 1,
      name: 'test-job',
      workflowId: 1,
      legacyJobId: null,
      mqTopic: 'test-topic',
      runtimeConfig: '{}',
      state: 'CREATED',
      attemptNo: 0,
      startedAt: null,
      finishedAt: null,
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'name', 'workflowId', 'legacyJobId', 'mqTopic', 'runtimeConfig', 'state', 'attemptNo', 'startedAt', 'finishedAt', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

describe('StreamCheckpoint ↔ stream_checkpoint 表字段对齐', () => {
  it('has all 8 fields matching backend model', () => {
    const sample: StreamCheckpoint = {
      id: 1,
      jobId: 1,
      partitionId: 'partition-0',
      offsetValue: 0,
      payload: '{}',
      eventTime: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'jobId', 'partitionId', 'offsetValue', 'payload', 'eventTime', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

describe('StreamMetricSnapshot ↔ stream_metric_snapshot 表字段对齐', () => {
  it('has all 18 fields matching backend model', () => {
    const sample: StreamMetricSnapshot = {
      id: 1,
      jobId: 1,
      attemptNo: 0,
      produceRate: 0,
      consumeRate: 0,
      processRate: 0,
      inputCount: 0,
      outputCount: 0,
      successCount: 0,
      failureCount: 0,
      skippedCount: 0,
      duplicateCount: 0,
      backlog: 0,
      offsetValue: 0,
      windowResult: '{}',
      capturedAt: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'jobId', 'attemptNo', 'produceRate', 'consumeRate', 'processRate', 'inputCount', 'outputCount', 'successCount', 'failureCount', 'skippedCount', 'duplicateCount', 'backlog', 'offsetValue', 'windowResult', 'capturedAt', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

describe('StreamFailureEvent ↔ stream_failure_event 表字段对齐', () => {
  it('has all 8 fields matching backend model', () => {
    const sample: StreamFailureEvent = {
      id: 1,
      jobId: 1,
      attemptNo: 0,
      errorType: 'TIMEOUT',
      sampleData: 'error',
      eventTime: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'jobId', 'attemptNo', 'errorType', 'sampleData', 'eventTime', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

describe('StreamRecoveryEvent ↔ stream_recovery_event 表字段对齐', () => {
  it('has all 7 fields matching backend model', () => {
    const sample: StreamRecoveryEvent = {
      id: 1,
      jobId: 1,
      kind: 'RECOVERY',
      detail: 'recovered',
      eventTime: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z',
      updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(Object.keys(sample).sort()).toEqual(
      ['id', 'jobId', 'kind', 'detail', 'eventTime', 'createdAt', 'updatedAt'].sort(),
    )
  })
})

/* ---------- §9 时间戳契约（R2-13 模式延伸） ---------- */

describe('§9 时间戳契约：运行表六张携带三契约时间戳', () => {
  it('WorkflowInstance has createdAt/updatedAt/generatedAt (DB-generated non-null)', () => {
    const sample: WorkflowInstance = {
      id: 1, workflowId: 1, workflowVersionId: 1, trialSnapshotId: null,
      instanceType: 'FORMAL', status: 'RUNNING', triggerType: null,
      startedAt: null, finishedAt: null,
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z', generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
    expect(sample.generatedAt).toBeTruthy()
  })

  it('TaskInstance has createdAt/updatedAt/generatedAt', () => {
    const sample: TaskInstance = {
      id: 1, workflowInstanceId: 1, taskId: 't1', status: 'RUNNING',
      currentAttemptNo: 0, startedAt: null, finishedAt: null,
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z', generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
    expect(sample.generatedAt).toBeTruthy()
  })

  it('TaskAttempt has createdAt/updatedAt/generatedAt', () => {
    const sample: TaskAttempt = {
      id: 1, taskInstanceId: 1, attemptNo: 1, status: 'RUNNING',
      startedAt: null, finishedAt: null,
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z', generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
    expect(sample.generatedAt).toBeTruthy()
  })

  it('RunLog has createdAt/updatedAt/generatedAt', () => {
    const sample: RunLog = {
      id: 1, taskInstanceId: 1, attemptNo: 1, level: 'INFO', message: 'm',
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z', generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
    expect(sample.generatedAt).toBeTruthy()
  })

  it('RunOutput has createdAt/updatedAt/generatedAt', () => {
    const sample: RunOutput = {
      id: 1, taskInstanceId: 1, attemptNo: 1, outputJson: '{}',
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z', generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
    expect(sample.generatedAt).toBeTruthy()
  })

  it('ExecutionEvent has createdAt/updatedAt/generatedAt + eventTime', () => {
    const sample: ExecutionEvent = {
      id: 1, workflowInstanceId: 1, taskInstanceId: null, attemptNo: null,
      eventKind: 'DISPATCH', payloadJson: null, eventTime: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z', generatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
    expect(sample.generatedAt).toBeTruthy()
    expect(sample.eventTime).toBeTruthy()
  })
})

/* ---------- §13.13 流表时间戳契约 ---------- */

describe('§13.13 流表时间戳契约：created_at/updated_at DB 生成非空', () => {
  it('StreamJob has createdAt/updatedAt (DB-generated non-null)', () => {
    const sample: StreamJob = {
      id: 1, name: 'j', workflowId: 1, legacyJobId: null, mqTopic: 't',
      runtimeConfig: '{}', state: 'CREATED', attemptNo: 0,
      startedAt: null, finishedAt: null,
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
  })

  it('StreamCheckpoint has createdAt/updatedAt + eventTime', () => {
    const sample: StreamCheckpoint = {
      id: 1, jobId: 1, partitionId: 'p0', offsetValue: 0,
      payload: '{}', eventTime: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
    expect(sample.eventTime).toBeTruthy()
  })

  it('StreamMetricSnapshot has createdAt/updatedAt + capturedAt', () => {
    const sample: StreamMetricSnapshot = {
      id: 1, jobId: 1, attemptNo: 0,
      produceRate: 0, consumeRate: 0, processRate: 0,
      inputCount: 0, outputCount: 0, successCount: 0,
      failureCount: 0, skippedCount: 0, duplicateCount: 0,
      backlog: 0, offsetValue: 0, windowResult: '{}',
      capturedAt: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
    expect(sample.capturedAt).toBeTruthy()
  })

  it('StreamFailureEvent has createdAt/updatedAt + eventTime', () => {
    const sample: StreamFailureEvent = {
      id: 1, jobId: 1, attemptNo: 0, errorType: 'E', sampleData: 's',
      eventTime: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
    expect(sample.eventTime).toBeTruthy()
  })

  it('StreamRecoveryEvent has createdAt/updatedAt + eventTime', () => {
    const sample: StreamRecoveryEvent = {
      id: 1, jobId: 1, kind: 'R', detail: 'd',
      eventTime: '2026-10-19T00:00:00Z',
      createdAt: '2026-10-19T00:00:00Z', updatedAt: '2026-10-19T00:00:00Z',
    }
    expect(sample.createdAt).toBeTruthy()
    expect(sample.updatedAt).toBeTruthy()
    expect(sample.eventTime).toBeTruthy()
  })
})
