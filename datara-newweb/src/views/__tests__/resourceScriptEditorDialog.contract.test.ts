import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EditorView } from '@codemirror/view'
import type { ResourceMeta } from '../../services/rebuild/resourceApi'

const { getResourceVersionContent, checkResourceScript, appendResourceVersion, getScriptEnvironment } = vi.hoisted(() => ({
  getResourceVersionContent: vi.fn(),
  checkResourceScript: vi.fn(),
  appendResourceVersion: vi.fn(),
  getScriptEnvironment: vi.fn(),
}))
const { listConnections, listDatabases, listSchemas, listObjects, listColumns, executeSql } = vi.hoisted(() => ({
  listConnections: vi.fn(), listDatabases: vi.fn(), listSchemas: vi.fn(),
  listObjects: vi.fn(), listColumns: vi.fn(), executeSql: vi.fn(),
}))
const { trialCandidates } = vi.hoisted(() => ({ trialCandidates: vi.fn() }))

vi.mock('../../services/rebuild/dbxApi', () => ({
  createDbxContract: () => ({ listConnections, listDatabases, listSchemas, listObjects, listColumns, executeSql }),
}))

vi.mock('../../services/rebuild/sshNodeApi', () => ({
  sshNodeApi: { trialCandidates },
}))

vi.mock('../../services/rebuild/resourceApi', async (original) => {
  const actual = await original<typeof import('../../services/rebuild/resourceApi')>()
  return {
    ...actual,
    createResourceContract: () => ({ getResourceVersionContent, checkResourceScript, appendResourceVersion, getScriptEnvironment }),
  }
})

import ResourceScriptEditorDialog from '../resources/ResourceScriptEditorDialog.vue'

const resource: ResourceMeta = { resourceId: 8, name: 'job.sql', kind: 'sql', sizeBytes: 21, latestVersion: 3 }

function mountDialog() {
  return mount(ResourceScriptEditorDialog, { props: { projectId: 7, resource } })
}

function editorOf(wrapper: ReturnType<typeof mountDialog>): EditorView {
  const host = wrapper.find('[data-script-code-host]').element as HTMLElement
  const view = EditorView.findFromDOM(host)
  if (!view) throw new Error('CodeMirror 视图未挂载')
  return view
}

function typeInto(view: EditorView, text: string): void {
  view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text } })
}

const okResult = {
  kind: 'sql' as const,
  syntax: { status: 'ok' as const, diagnostics: [] },
  references: [],
  run: null,
}

const environment = {
  runLocation: {
    scope: 'api_process',
    label: '后端 API 服务进程（非 SSH 目标主机）',
    hostname: 'api-container',
    platform: 'Linux 6.1',
    containerized: true,
    workdir: '每次试运行创建独立临时目录',
  },
  python: { available: true, version: '3.11.9', executable: '/usr/local/bin/python3', packageCount: 42, packages: ['requests'] },
  shell: { available: true, path: '/bin/bash', kind: 'bash', version: 'GNU bash, version 5.2.15' },
  database: null,
  databaseNote: '资源未绑定数据源，SQL 不会在试运行中执行；请在 SQL IDE 选择数据源后执行。',
  output: { channel: 'run_log', label: '弹窗下方「试运行日志」区域' },
}

describe('资源脚本编辑弹窗', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getResourceVersionContent.mockResolvedValue({ resourceId: 8, version: 3, name: 'job.sql', content: 'select 1' })
    checkResourceScript.mockResolvedValue(okResult)
    appendResourceVersion.mockResolvedValue({ resourceId: 8, version: 4, sizeBytes: 21, digest: 'sha-4', uploadedAt: '2026-10-29T00:00:00Z' })
    getScriptEnvironment.mockResolvedValue(environment)
    listConnections.mockResolvedValue([{ id: 'dbx-1', name: '分析库', database: 'analytics' }])
    listDatabases.mockResolvedValue([{ name: 'analytics' }])
    listSchemas.mockResolvedValue(['public'])
    listObjects.mockResolvedValue([{ name: 'orders', object_type: 'TABLE' }])
    listColumns.mockResolvedValue([])
    executeSql.mockResolvedValue({ columns: ['value'], rows: [[1]] })
    trialCandidates.mockResolvedValue([])
  })

  it('标题下环境状态栏展示运行位置、语言环境与输出位置', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    expect(getScriptEnvironment).toHaveBeenCalledWith(7)
    const bar = wrapper.find('[data-env-bar]')
    expect(bar.exists()).toBe(true)
    expect(bar.find('[data-env-location]').text()).toContain('dbx SQL · 分析库 / analytics')
    expect(bar.find('[data-env-language]').text()).toContain('SQL 方言由 dbx 连接决定')
    expect(wrapper.find('[data-dbx-object-tree]').text()).toContain('orders')
    expect(bar.find('[data-env-output]').text()).toContain('试运行日志')
    wrapper.unmount()
  })

  it('环境探测失败时状态栏降级展示错误而不阻断编辑', async () => {
    getScriptEnvironment.mockRejectedValue(new Error('权限不足'))
    const wrapper = mountDialog()
    await flushPromises()
    expect(wrapper.find('[data-env-error]').text()).toContain('权限不足')
    expect(editorOf(wrapper).state.doc.toString()).toBe('select 1')
    wrapper.unmount()
  })

  it('挂载即读取最新版本正文，校验时把正文提交给服务端', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    expect(getResourceVersionContent).toHaveBeenCalledWith(8, 3, 7)
    expect(editorOf(wrapper).state.doc.toString()).toBe('select 1')

    await wrapper.find('[data-check-script]').trigger('click')
    await flushPromises()
    expect(checkResourceScript).toHaveBeenCalledWith({ projectId: 7, resourceId: 8, content: 'select 1', execute: false })
    expect(wrapper.find('[data-check-result]').text()).toContain('未发现语法或引用问题')
    wrapper.unmount()
  })

  it('SQL 试运行经 dbx 网关执行并渲染结果', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.find('[data-run-script]').trigger('click')
    await flushPromises()
    expect(checkResourceScript).toHaveBeenCalledWith(expect.objectContaining({ execute: false }))
    expect(executeSql).toHaveBeenCalledWith(expect.objectContaining({ connectionId: 'dbx-1', database: 'analytics', schemaName: 'public', sql: 'select 1' }))
    expect(wrapper.find('[data-run-stdout]').text()).toContain('columns')
    wrapper.unmount()
  })

  it('存在语法错误时阻断保存且不追加版本', async () => {
    checkResourceScript.mockResolvedValue({
      kind: 'sql',
      syntax: {
        status: 'error',
        diagnostics: [{ source: 'syntax', code: 'SQL_PARSE_ERROR', severity: 'error', line: 1, column: 1, message: '解析失败' }],
      },
      references: [],
      run: null,
    })
    const wrapper = mountDialog()
    await flushPromises()
    typeInto(editorOf(wrapper), 'select from')
    await wrapper.find('[data-save-version]').trigger('click')
    await flushPromises()
    expect(appendResourceVersion).not.toHaveBeenCalled()
    expect(wrapper.find('[data-editor-error]').text()).toContain('语法错误')
    wrapper.unmount()
  })

  it('校验通过后保存追加不可变版本并抛出 saved/close', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    typeInto(editorOf(wrapper), 'select 2')
    await wrapper.find('[data-save-version]').trigger('click')
    await flushPromises()
    expect(checkResourceScript).toHaveBeenCalledWith(expect.objectContaining({ content: 'select 2', execute: false }))
    expect(appendResourceVersion).toHaveBeenCalledWith({ projectId: 7, resourceId: 8, filename: 'job.sql', content: 'select 2' })
    expect(wrapper.emitted('saved')?.[0]?.[0]).toEqual(expect.objectContaining({ resourceId: 8, version: 4 }))
    expect(wrapper.emitted('close')).toHaveLength(1)
    wrapper.unmount()
  })

  it('内容未修改时拒绝保存', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    await wrapper.find('[data-save-version]').trigger('click')
    await flushPromises()
    expect(checkResourceScript).not.toHaveBeenCalled()
    expect(appendResourceVersion).not.toHaveBeenCalled()
    expect(wrapper.find('[data-editor-error]').text()).toContain('内容未修改')
    wrapper.unmount()
  })

  it('内容读取失败时展示后端错误', async () => {
    getResourceVersionContent.mockRejectedValue(new Error('资源版本不存在'))
    const wrapper = mountDialog()
    await flushPromises()
    expect(wrapper.find('[data-editor-error]').text()).toContain('资源版本不存在')
    wrapper.unmount()
  })

  it('Python 脚本无可用试运行节点时提示到部署运维开启允许试运行', async () => {
    const wrapper = mount(ResourceScriptEditorDialog, {
      props: { projectId: 7, resource: { resourceId: 9, name: 'job.py', kind: 'python', sizeBytes: 24, latestVersion: 1 } },
    })
    await flushPromises()
    expect(trialCandidates).toHaveBeenCalled()
    expect(wrapper.find('[data-trial-ssh-node]').findAll('option')).toHaveLength(1)
    expect(wrapper.find('[data-trial-empty-hint]').text()).toContain('允许脚本试运行')
    wrapper.unmount()
  })

  it('Python 脚本自动选中首个可试运行节点且不展示空态提示', async () => {
    trialCandidates.mockResolvedValue([
      { id: 5, name: 'node-1.9', host: '192.168.1.9', port: 22, sshUser: 'root', tags: [], enabled: true, allowTrial: true, hasCredential: true, ownerId: 3, heartbeatState: null, lastSeen: null, createTime: null },
    ])
    const wrapper = mount(ResourceScriptEditorDialog, {
      props: { projectId: 7, resource: { resourceId: 9, name: 'job.py', kind: 'python', sizeBytes: 24, latestVersion: 1 } },
    })
    await flushPromises()
    const select = wrapper.find('[data-trial-ssh-node]')
    expect(select.findAll('option')).toHaveLength(2)
    expect((select.element as HTMLSelectElement).value).toBe('5')
    expect(wrapper.find('[data-trial-empty-hint]').exists()).toBe(false)
    wrapper.unmount()
  })
})
