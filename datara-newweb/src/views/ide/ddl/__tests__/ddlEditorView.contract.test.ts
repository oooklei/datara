/**
 * 16.1 波3 DdlEditorView 契约测试（双轨互斥 + 八步管控面 + 三重闸 fail-closed）。
 *
 * 契约经 props DI 注入 stub（wire 断言归 sqlIdeDdlApi.contract.test.ts，不重复）。
 * 票4 验收锚：13 变体走源码轨 / table 走结构化轨互斥断言 + 八步逐步走查 +
 * preview 不回传样本值断言 + capability 拒写负断言。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { SqlIdeDdlApiError } from '../../../../services/rebuild/sqlIdeDdlApi'
import type {
  DdlDefinitionSnapshot,
  DdlExecutionOutcome,
  DdlExecutionRecordPage,
  DdlImpactReport,
  DdlObjectRef,
  DdlPolicyReport,
  SqlIdeDdlContract,
} from '../../../../services/rebuild/sqlIdeDdlApi'
import { roleHasPermission } from '../../../../services/rebuild/rolePermissions'
import type { Role } from '../../../../services/rebuild/rolePermissions'
import DdlEditorView from '../DdlEditorView.vue'
import { DDL_KIND_OPTIONS, OBJECT_SOURCE_KINDS, isSourceTrack, isStructuredTrack, toApiKind } from '../objectSourceKinds'

const OBJECT_REF: DdlObjectRef = { datasourceId: 1, database: 'db', catalog: null, schema: null, kind: 'view', name: 'v1', parent: null }

const SNAPSHOT: DdlDefinitionSnapshot = {
  objectRef: OBJECT_REF,
  definition: 'CREATE VIEW v1 AS SELECT 1',
  sourceVersion: 'sv-1',
  capability: 'supported',
  constraints: [],
}

const POLICY_REPORT: DdlPolicyReport = {
  snapshotId: 'ps-1',
  findings: [{ level: 'warn', code: 'WARN_INDEX', message: 'DROP 前请确认依赖', impacts: [] }],
  blocked: false,
}

const IMPACT_REPORT: DdlImpactReport = {
  snapshotId: 'is-1',
  impacts: [{ objectRef: OBJECT_REF, relationType: 'dependent', detail: '视图 v2 依赖 v1' }],
  unknownReasons: ['表 t3 血缘未知'],
}

const OUTCOME: DdlExecutionOutcome = { recordId: 'rec-1', status: 'success' }

const RECORD_PAGE: DdlExecutionRecordPage = {
  items: [{
    recordId: 'rec-1',
    actorId: 7,
    action: 'ddl.execute',
    scriptHash: 'sha256:abc',
    executedAt: '2026-10-21T00:00:00Z',
    status: 'success',
    failureSummary: null,
  }],
  page: { nextCursor: null, hasMore: false },
}

function stubContract(overrides: Partial<SqlIdeDdlContract> = {}): SqlIdeDdlContract {
  return {
    getDefinition: vi.fn(async () => ({ ...SNAPSHOT, objectRef: { ...SNAPSHOT.objectRef } })),
    validatePolicy: vi.fn(async () => ({ ...POLICY_REPORT, findings: POLICY_REPORT.findings.map((f) => ({ ...f })) })),
    previewImpact: vi.fn(async () => ({
      ...IMPACT_REPORT,
      impacts: IMPACT_REPORT.impacts.map((item) => ({ ...item })),
      unknownReasons: [...IMPACT_REPORT.unknownReasons],
    })),
    submitConfirm: vi.fn(async () => ({ ...OUTCOME })),
    listExecutionRecords: vi.fn(async () => ({ ...RECORD_PAGE, items: RECORD_PAGE.items.map((r) => ({ ...r })) })),
    ...overrides,
  }
}

function mountView(contract: SqlIdeDdlContract = stubContract(), role: Role = 'developer') {
  return mount(DdlEditorView, { props: { role, contract } })
}

type ViewWrapper = ReturnType<typeof mountView>

async function loadSnapshot(wrapper: ViewWrapper, kind = 'view'): Promise<void> {
  await wrapper.find('[data-kind-select]').setValue(kind)
  await wrapper.find('[data-datasource-id]').setValue(1)
  await wrapper.find('[data-database]').setValue('db')
  await wrapper.find('[data-object-name]').setValue('v1')
  await wrapper.find('[data-load-definition]').trigger('click')
  await flushPromises()
}

describe('DdlEditorView 契约（16.1 波3 双轨编辑器 + 八步管控面）', () => {
  it('双轨互斥：14 类别逐一走查，源码轨/结构化轨恰现其一', async () => {
    const wrapper = mountView()
    for (const k of DDL_KIND_OPTIONS) {
      await wrapper.find('[data-kind-select]').setValue(k)
      await flushPromises()
      const source = wrapper.find('[data-track="source"]')
      const structured = wrapper.find('[data-track="structured"]')
      expect(source.exists() !== structured.exists()).toBe(true)
      if (isStructuredTrack(k)) {
        expect(structured.exists()).toBe(true)
        expect(wrapper.find('[data-op-select]').exists()).toBe(true)
      } else {
        expect(source.exists()).toBe(true)
        expect(isSourceTrack(k)).toBe(true)
        expect(wrapper.find('[data-source-input]').exists()).toBe(true)
      }
    }
  })

  it('table 走结构化轨：派生 ALTER TABLE，禁自由源码输入', async () => {
    const contract = stubContract({
      getDefinition: vi.fn(async () => ({
        ...SNAPSHOT,
        objectRef: { ...OBJECT_REF, kind: 'table' as const, name: 't1' },
        definition: 'CREATE TABLE t1 (id INT)',
      })),
    })
    const wrapper = mountView(contract)
    await loadSnapshot(wrapper, 'table')
    expect(wrapper.find('[data-source-input]').exists()).toBe(false)
    expect(wrapper.find('[data-op-select]').exists()).toBe(true)
    await wrapper.find('[data-column-name]').setValue('remark')
    await wrapper.find('[data-column-type]').setValue('VARCHAR(64)')
    await flushPromises()
    const generated = wrapper.find('[data-generated-ddl]').element as HTMLTextAreaElement
    expect(generated.value).toBe('ALTER TABLE t1 ADD COLUMN remark VARCHAR(64)')
    expect(wrapper.find('[data-step="2"]').attributes('data-step-state')).toBe('active')
    expect((wrapper.find('[data-validate-policy]').element as HTMLButtonElement).disabled).toBe(false)
    await wrapper.find('[data-op-select]').setValue('drop_column')
    await flushPromises()
    expect(((wrapper.find('[data-generated-ddl]').element) as HTMLTextAreaElement).value).toBe('ALTER TABLE t1 DROP COLUMN remark')
  })

  it('八步管控面 happy path：view 全链从载入到执行记录', async () => {
    const contract = stubContract()
    const wrapper = mountView(contract)
    await loadSnapshot(wrapper)
    expect(wrapper.find('[data-step="1"]').attributes('data-step-state')).toBe('done')
    expect(wrapper.find('[data-step="2"]').attributes('data-step-state')).toBe('pending')
    await wrapper.find('[data-source-input]').setValue('ALTER VIEW v1 AS SELECT 2')
    await flushPromises()
    expect(wrapper.find('[data-step="2"]').attributes('data-step-state')).toBe('active')
    // 步2 依赖检查
    await wrapper.find('[data-validate-policy]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-step="2"]').attributes('data-step-state')).toBe('done')
    expect(wrapper.find('[data-finding-level="warn"]').exists()).toBe(true)
    expect(wrapper.find('[data-policy-blocked]').attributes('data-blocked')).toBe('no')
    expect(vi.mocked(contract.validatePolicy).mock.calls[0]?.[0]).toMatchObject({ sourceVersion: 'sv-1', nextDdlText: 'ALTER VIEW v1 AS SELECT 2' })
    // 步3 影响预览
    await wrapper.find('[data-preview-impact]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-step="3"]').attributes('data-step-state')).toBe('done')
    expect(wrapper.findAll('[data-impact]')).toHaveLength(1)
    expect(wrapper.find('[data-impact-relation]').text()).toBe('dependent')
    // 步4 双快照
    expect(wrapper.find('[data-step="4"]').attributes('data-step-state')).toBe('done')
    expect(wrapper.find('[data-policy-snapshot-id]').text()).toContain('ps-1')
    expect(wrapper.find('[data-impact-snapshot-id]').text()).toContain('is-1')
    // 步5 确认：空短语禁用 → 填短语放行
    expect((wrapper.find('[data-submit-confirm]').element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.find('[data-confirm-phrase]').setValue('确认执行 DDL')
    expect((wrapper.find('[data-submit-confirm]').element as HTMLButtonElement).disabled).toBe(false)
    await wrapper.find('[data-submit-confirm]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-step="5"]').attributes('data-step-state')).toBe('done')
    // 步6 执行
    expect(wrapper.find('[data-step="6"]').attributes('data-step-state')).toBe('done')
    expect(wrapper.find('[data-outcome-record-id]').text()).toBe('rec-1')
    expect(wrapper.find('[data-outcome-status]').text()).toBe('success')
    expect(vi.mocked(contract.submitConfirm).mock.calls[0]?.[0]).toMatchObject({ confirmPhrase: '确认执行 DDL', policySnapshotId: 'ps-1', impactSnapshotId: 'is-1' })
    // 步7 结果记录
    expect(wrapper.find('[data-step="7"]').attributes('data-step-state')).toBe('active')
    await wrapper.find('[data-refresh-records]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-step="7"]').attributes('data-step-state')).toBe('done')
    expect(wrapper.find('[data-record="rec-1"]').attributes('data-record-status')).toBe('success')
    // 步8 五态呈现 + 当前态标记
    expect(wrapper.findAll('[data-exec-status]')).toHaveLength(5)
    expect(wrapper.find('[data-current="yes"]').attributes('data-exec-status')).toBe('success')
  })

  it('A7 红线：空白确认短语禁提交且契约层拒发', async () => {
    const contract = stubContract()
    const wrapper = mountView(contract)
    await loadSnapshot(wrapper)
    await wrapper.find('[data-source-input]').setValue('ALTER VIEW v1 AS SELECT 2')
    await wrapper.find('[data-validate-policy]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-preview-impact]').trigger('click')
    await flushPromises()
    const submit = wrapper.find('[data-submit-confirm]')
    expect((submit.element as HTMLButtonElement).disabled).toBe(true)
    await wrapper.find('[data-confirm-phrase]').setValue('   ')
    expect((submit.element as HTMLButtonElement).disabled).toBe(true)
    await submit.trigger('click')
    await flushPromises()
    expect(contract.submitConfirm).not.toHaveBeenCalled()
  })

  it('策略阻断：blocked=true 时确认链禁止', async () => {
    const contract = stubContract({
      validatePolicy: vi.fn(async () => ({ ...POLICY_REPORT, blocked: true })),
    })
    const wrapper = mountView(contract)
    await loadSnapshot(wrapper)
    await wrapper.find('[data-source-input]').setValue('DROP VIEW v1')
    await wrapper.find('[data-validate-policy]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-policy-blocked]').attributes('data-blocked')).toBe('yes')
    expect(wrapper.find('[data-step="5"]').attributes('data-step-state')).toBe('blocked')
    await wrapper.find('[data-confirm-phrase]').setValue('确认执行 DDL')
    expect((wrapper.find('[data-submit-confirm]').element as HTMLButtonElement).disabled).toBe(true)
  })

  it.each(['unsupported', 'unknown'] as const)('capability=%s 拒写：写链 fail-closed', async (capability) => {
    const contract = stubContract({
      getDefinition: vi.fn(async () => ({ ...SNAPSHOT, capability, constraints: ['需 DBA 会话'] })),
    })
    const wrapper = mountView(contract)
    await loadSnapshot(wrapper)
    expect(wrapper.find('[data-write-allowed]').attributes('data-write-allowed')).toBe('no')
    expect(wrapper.find('[data-step="2"]').attributes('data-step-state')).toBe('blocked')
    expect((wrapper.find('[data-validate-policy]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.text()).toContain('需 DBA 会话')
    expect(contract.validatePolicy).not.toHaveBeenCalled()
  })

  it('capability=conditional 放行并呈现 constraints', async () => {
    const contract = stubContract({
      getDefinition: vi.fn(async () => ({ ...SNAPSHOT, capability: 'conditional', constraints: ['需在维护窗口执行'] })),
    })
    const wrapper = mountView(contract)
    await loadSnapshot(wrapper)
    expect(wrapper.find('[data-write-allowed]').attributes('data-write-allowed')).toBe('yes')
    expect(wrapper.text()).toContain('需在维护窗口执行')
  })

  it('A7 红线：影响预览仅关系与元数据，不回传样本值', async () => {
    const wrapper = mountView()
    await loadSnapshot(wrapper)
    await wrapper.find('[data-source-input]').setValue('ALTER VIEW v1 AS SELECT 2')
    await wrapper.find('[data-validate-policy]').trigger('click')
    await flushPromises()
    await wrapper.find('[data-preview-impact]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-sample-value]').exists()).toBe(false)
    expect(wrapper.html()).not.toContain('sampleValue')
    const unknown = wrapper.find('[data-impact-unknown]')
    expect(unknown.exists()).toBe(true)
    expect(unknown.text()).toContain('血缘未知')
  })

  it('viewer 默认拒写：角色闸阻断写链（读不拦，getDefinition 属 VIEW_ALL）', async () => {
    const contract = stubContract()
    const wrapper = mountView(contract, 'viewer')
    await loadSnapshot(wrapper)
    expect(wrapper.find('[data-perm-gate]').attributes('data-granted')).toBe('no')
    expect(wrapper.find('[data-step="1"]').attributes('data-step-state')).toBe('blocked')
    expect(wrapper.find('[data-step="2"]').attributes('data-step-state')).toBe('blocked')
    expect((wrapper.find('[data-load-definition]').element as HTMLButtonElement).disabled).toBe(false)
    expect(vi.mocked(contract.getDefinition)).toHaveBeenCalledTimes(1)
    expect((wrapper.find('[data-validate-policy]').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('非 API kind（sequence）：源码轨呈现但写链禁用', async () => {
    const contract = stubContract()
    const wrapper = mountView(contract)
    await wrapper.find('[data-kind-select]').setValue('sequence')
    await wrapper.find('[data-database]').setValue('db')
    await wrapper.find('[data-object-name]').setValue('seq1')
    await flushPromises()
    expect(wrapper.find('[data-track="source"]').exists()).toBe(true)
    expect(wrapper.find('[data-kind-unavailable]').exists()).toBe(true)
    expect((wrapper.find('[data-load-definition]').element as HTMLButtonElement).disabled).toBe(true)
    expect(wrapper.find('[data-step="2"]').attributes('data-step-state')).toBe('blocked')
    await wrapper.find('[data-load-definition]').trigger('click')
    await flushPromises()
    expect(contract.getDefinition).not.toHaveBeenCalled()
  })

  it('SOURCE_VERSION_UNAVAILABLE fail-closed：错误呈现且快照拒入写链', async () => {
    const contract = stubContract({
      getDefinition: vi.fn(async () => {
        throw new SqlIdeDdlApiError('定义响应缺少 sourceVersion，DDL 写链 fail-closed', 502, 'SOURCE_VERSION_UNAVAILABLE')
      }),
    })
    const wrapper = mountView(contract)
    await loadSnapshot(wrapper)
    const errorEl = wrapper.find('[data-error]')
    expect(errorEl.exists()).toBe(true)
    expect(errorEl.attributes('role')).toBe('alert')
    expect(errorEl.text()).toContain('SOURCE_VERSION_UNAVAILABLE')
    expect(((wrapper.find('[data-source-input]').element) as HTMLTextAreaElement).disabled).toBe(true)
    expect(wrapper.find('[data-step="2"]').attributes('data-step-state')).toBe('pending')
  })

  it('objectSourceKinds 单元：枚举/映射/权限锚', () => {
    expect(OBJECT_SOURCE_KINDS).toHaveLength(13)
    expect(DDL_KIND_OPTIONS).toHaveLength(14)
    expect(DDL_KIND_OPTIONS[0]).toBe('table')
    expect(new Set<string>(DDL_KIND_OPTIONS).size).toBe(14)
    expect(toApiKind('table')).toBe('table')
    expect(toApiKind('view')).toBe('view')
    expect(toApiKind('function')).toBe('function')
    expect(toApiKind('procedure')).toBe('procedure')
    expect(toApiKind('trigger')).toBe('trigger')
    expect(OBJECT_SOURCE_KINDS.filter((k) => toApiKind(k) === null)).toHaveLength(9)
    expect(roleHasPermission('admin', 'edit_definition')).toBe(true)
    expect(roleHasPermission('developer', 'edit_definition')).toBe(true)
    expect(roleHasPermission('operator', 'edit_definition')).toBe(false)
    expect(roleHasPermission('viewer', 'edit_definition')).toBe(false)
    expect(isStructuredTrack('table')).toBe(true)
    expect(isSourceTrack('table')).toBe(false)
  })
})
