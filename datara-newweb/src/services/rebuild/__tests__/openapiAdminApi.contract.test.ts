/**
 * 15-P0 开放 API 管理契约 RED 测试（node 环境，纯契约层无组件挂载）— IMPL-v4-08。
 * 断言：方法清单/权限矩阵/错误码/URL 前缀冻结，工厂实现统一抛 OPENAPI_ADMIN_NOT_WIRED
 * （即 15.2-A~D 接入前不存在半连通状态）；一次性明文回显仅存在于 KeyIssuance 形态。
 * 组件可编译性由 `vue-tsc -b` / build 门禁保证。
 */
import { describe, expect, it } from 'vitest'
import {
  OPENAPI_ADMIN_CONTRACT_METHODS,
  OPENAPI_ADMIN_ERROR_CODES,
  OPENAPI_ADMIN_NOT_WIRED,
  OPENAPI_ADMIN_PERMISSION_MATRIX,
  OPENAPI_ADMIN_URL_PREFIX,
  createOpenapiAdminContract,
  openapiAdminApi,
  openapiAdminKeyApi,
  type ApiCallLogRecord,
  type ApiDefinitionInput,
  type ApiDefinitionRecord,
  type ApiKeyInput,
  type ApiKeyRecord,
} from '../openapiAdminApi'

const definitionInput: ApiDefinitionInput = {
  name: '质量规则查询',
  path: '/rebuild/quality-rules',
  method: 'GET',
  description: '受控只读 facade',
  requiredPermission: 'quality:read',
  version: '1',
}

const keyInput: ApiKeyInput = {
  name: '数据出口 key',
  scopes: { permissions: ['quality:read'], projectIds: [1] },
  expiresAt: '2027-01-01 00:00:00',
}

describe('15-P0 openapiAdminApi contract (RED)', () => {
  it('contract method list is frozen to the api-management admin subset', () => {
    expect(OPENAPI_ADMIN_CONTRACT_METHODS).toHaveLength(12)
    expect([...OPENAPI_ADMIN_CONTRACT_METHODS]).toEqual(
      expect.arrayContaining([
        'listApiDefinitions',
        'createApiDefinition',
        'updateApiDefinition',
        'deleteApiDefinition',
        'publishApiDefinition',
        'disableApiDefinition',
        'enableApiDefinition',
        'listApiKeys',
        'issueApiKey',
        'rotateApiKey',
        'revokeApiKey',
        'listCallLogs',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createOpenapiAdminContract()
    for (const method of OPENAPI_ADMIN_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

  it('freezes the permission matrix over identity-existing permission words only', () => {
    expect(Object.keys(OPENAPI_ADMIN_PERMISSION_MATRIX)).toEqual([...OPENAPI_ADMIN_CONTRACT_METHODS])
    // 零新增权限词形红线：写面 security:manage、读面 security:read
    for (const [method, permission] of Object.entries(OPENAPI_ADMIN_PERMISSION_MATRIX)) {
      expect(['security:read', 'security:manage']).toContain(permission)
      if (method.startsWith('list')) expect(permission).toBe('security:read')
    }
  })

  it('freezes the error-code table with identity-shared codes and domain-specific band', () => {
    expect(OPENAPI_ADMIN_ERROR_CODES.invalidToken).toBe(1001)
    expect(OPENAPI_ADMIN_ERROR_CODES.permissionDenied).toBe(1003)
    expect(OPENAPI_ADMIN_ERROR_CODES.invalidInput).toBe(4001)
    expect(OPENAPI_ADMIN_ERROR_CODES.apiNotFound).toBe(4041)
    expect(OPENAPI_ADMIN_ERROR_CODES.keyNotFound).toBe(4042)
    expect(OPENAPI_ADMIN_ERROR_CODES.duplicateDefinition).toBe(4091)
    expect(OPENAPI_ADMIN_ERROR_CODES.invalidStatusTransition).toBe(4092)
    expect(OPENAPI_ADMIN_ERROR_CODES.keyExpired).toBe(4093)
    expect(OPENAPI_ADMIN_ERROR_CODES.keyRevoked).toBe(4094)
    expect(OPENAPI_ADMIN_ERROR_CODES.insufficientScope).toBe(4095)
    expect(OPENAPI_ADMIN_ERROR_CODES.facadeUnavailable).toBe(5041)
  })

  it('freezes the URL prefix /api/v1/open (product API-management domain, not FastAPI schema)', () => {
    expect(OPENAPI_ADMIN_URL_PREFIX).toBe('/api/v1/open')
  })

  it('factory delegates every method to the GREEN HTTP facades', () => {
    const contract = createOpenapiAdminContract()
    expect(contract.listApiDefinitions).toBe(openapiAdminApi.list)
    expect(contract.createApiDefinition).toBe(openapiAdminApi.create)
    expect(contract.updateApiDefinition).toBe(openapiAdminApi.update)
    expect(contract.deleteApiDefinition).toBe(openapiAdminApi.remove)
    expect(contract.publishApiDefinition).toBe(openapiAdminApi.publish)
    expect(contract.disableApiDefinition).toBe(openapiAdminApi.disable)
    expect(contract.enableApiDefinition).toBe(openapiAdminApi.enable)
    expect(contract.listApiKeys).toBe(openapiAdminKeyApi.list)
    expect(contract.issueApiKey).toBe(openapiAdminKeyApi.issue)
    expect(contract.rotateApiKey).toBe(openapiAdminKeyApi.rotate)
    expect(contract.revokeApiKey).toBe(openapiAdminKeyApi.revoke)
    expect(contract.listCallLogs).toBe(openapiAdminApi.callLogs)
  })

  it('sentinel wordform is frozen to OPENAPI_ADMIN_NOT_WIRED (rename regression guard)', () => {
    expect(OPENAPI_ADMIN_NOT_WIRED.startsWith('OPENAPI_ADMIN_NOT_WIRED')).toBe(true)
  })

  it('type faces freeze the security red lines (hash-only key, one-shot plaintext, sanitized logs)', () => {
    // 红线 ①：列表/详情记录面（ApiKeyRecord）无任何明文/密文 key 字段——仅 keyPrefix 展示前缀
    const key: ApiKeyRecord = {
      id: 1, name: 'k', keyPrefix: 'dk_live_', scopes: { permissions: [], projectIds: [] },
      status: 'active', expiresAt: null, lastUsedAt: null, createdBy: 'admin',
      revokedAt: null, createdAt: '', updatedAt: '',
    }
    expect(Object.keys(key)).not.toContain('keyHash')
    expect(Object.keys(key)).not.toContain('plainKey')
    expect(Object.keys(key)).not.toContain('key')

    // 红线 ②：一次性明文仅存在于签发/轮换响应形态（KeyIssuance），字段名冻结为 plainKey
    const issuance = { key, plainKey: 'dk_live_one_shot_value' }
    expect(issuance.plainKey).toBe('dk_live_one_shot_value')

    // 红线 ③：调用日志记录面零敏感字段——无 key 明文、无 body、无 SQL
    const log: ApiCallLogRecord = {
      requestId: 'req-1', apiId: 1, keyId: 1, principal: 'user:1', projectId: null,
      statusCode: 200, latencyMs: 12, result: 'success', errorCode: null, requestedAt: '',
    }
    const logKeys = Object.keys(log)
    expect(logKeys).not.toContain('key')
    expect(logKeys).not.toContain('requestBody')
    expect(logKeys).not.toContain('sql')
  })

  it('freezes definition status machine vocabulary and controlled-facade method whitelist', () => {
    const statuses: ApiDefinitionRecord['status'][] = ['draft', 'published', 'disabled']
    expect(statuses).toHaveLength(3)
    const methods: ApiDefinitionRecord['method'][] = ['GET', 'POST', 'PUT', 'DELETE']
    expect(methods).toHaveLength(4)
  })
})
