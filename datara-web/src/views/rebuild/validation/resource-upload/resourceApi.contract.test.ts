/**
 * R4-RESOURCE 契约 RED 测试（node 环境，纯契约层无组件挂载）。
 * 断言：方法清单冻结、工厂实现统一抛 R4_RESOURCE_NOT_WIRED、
 * 本地预校验行为（扩展名白名单 + 大小上限）、绑定请求显式版本语义。
 * 语义源：客户要求 #4 + 纠偏设计 §5.3（资源身份/版本/禁隐式 latest）。
 */
import { describe, expect, it } from 'vitest'
import {
  R4_RESOURCE_CONTRACT_METHODS,
  R4_RESOURCE_NOT_WIRED,
  RESOURCE_MAX_SIZE_BYTES,
  createResourceContract,
  validateUploadDraft,
} from '../../../../services/rebuild/resourceApi'

describe('R4 resourceApi contract (RED)', () => {
  it('contract method list is frozen to the resource version subset', () => {
    expect(R4_RESOURCE_CONTRACT_METHODS).toHaveLength(5)
    expect(R4_RESOURCE_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'uploadResource',
        'listResources',
        'listResourceVersions',
        'getResourceVersion',
        'bindResourceVersion',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createResourceContract()
    for (const method of R4_RESOURCE_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('every I/O method refuses until resource backend is wired', async () => {
    const contract = createResourceContract()
    const cases: Promise<unknown>[] = [
      contract.uploadResource({ projectId: 1, kind: 'sql', filename: 'etl.sql', sizeBytes: 10 }),
      contract.listResources(1),
      contract.listResources(1, 'python'),
      contract.listResourceVersions(1, 1),
      contract.getResourceVersion(1, 2, 1),
      contract.bindResourceVersion({ projectId: 1, workflowId: 1, workflowVersion: 1, taskId: 't1', resourceId: 1, resourceVersion: 2 }),
    ]
    for (const p of cases) {
      await expect(p).rejects.toThrow(R4_RESOURCE_NOT_WIRED)
    }
  })

  it('validateUploadDraft enforces per-kind extension whitelist', () => {
    expect(validateUploadDraft('sql', 'job.sql', 100)).toEqual([])
    expect(validateUploadDraft('python', 'job.py', 100)).toEqual([])
    expect(validateUploadDraft('shell', 'job.sh', 100)).toEqual([])
    const wrong = validateUploadDraft('sql', 'job.py', 100)
    expect(wrong).toHaveLength(1)
    expect(wrong[0]).toMatchObject({ field: 'filename', code: 'TYPE_NOT_ALLOWED' })
    const noExt = validateUploadDraft('shell', 'job', 100)
    expect(noExt[0]).toMatchObject({ field: 'filename', code: 'TYPE_NOT_ALLOWED' })
  })

  it('validateUploadDraft enforces the size limit draft constant', () => {
    expect(RESOURCE_MAX_SIZE_BYTES).toBe(20 * 1024 * 1024)
    const exceeded = validateUploadDraft('sql', 'big.sql', RESOURCE_MAX_SIZE_BYTES + 1)
    expect(exceeded).toHaveLength(1)
    expect(exceeded[0]).toMatchObject({ field: 'sizeBytes', code: 'SIZE_EXCEEDED' })
    expect(validateUploadDraft('sql', 'ok.sql', RESOURCE_MAX_SIZE_BYTES)).toEqual([])
  })
})
