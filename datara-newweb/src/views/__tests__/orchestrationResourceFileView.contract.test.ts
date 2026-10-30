/**
 * §10.10 R9 资源文件（全局文件树）页契约。
 *
 * 真源：docs/designs/2026-10-29-dbx-unified-target-design.md §10.10 R9。
 * 断言面：
 *  - 取数只经 `orchestrationApi.listResourceFiles()`（前端不直连海豚 API），手动刷新不轮询；
 *  - currentDir 契约：根为 `/`、子目录为目标目录 fullName（海豚要求非空，否则 ILLEGAL_RESOURCE_PATH）；
 *  - 写入门禁 EDIT_DEFINITION：operator 不出现任何写操作；树节点 `dirctory` 决定目录/文件分支；
 *  - 新建目录/上传/重命名/删除/下载/共享全部经编排网关；
 *  - 空态与错误态互斥，错误横幅透出编排网关字符串错误码。
 */
import { config, flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import OrchestrationResourceFileView from '../depops/OrchestrationResourceFileView.vue'
import { authAccount } from '../../services/rebuild/authApi'
import type { ResourceFileNode } from '../../services/rebuild/orchestrationApi'

const api = vi.hoisted(() => ({
  listResourceFiles: vi.fn(),
  createResourceFile: vi.fn(),
  renameResourceFile: vi.fn(),
  deleteResourceFile: vi.fn(),
  downloadResourceFile: vi.fn(),
  share: vi.fn(),
  unshare: vi.fn(),
}))

// 部分 mock：权限矩阵/错误码常量走真实实现，仅替换端点对象
vi.mock('../../services/rebuild/orchestrationApi', async () => {
  const actual = await vi.importActual<typeof import('../../services/rebuild/orchestrationApi')>(
    '../../services/rebuild/orchestrationApi',
  )
  return { ...actual, orchestrationApi: api }
})

const tree = (): ResourceFileNode[] => [
  {
    name: 'scripts',
    currentDir: 'scripts',
    fullName: 'scripts',
    dirctory: true,
    type: 'FILE',
    description: null,
    children: [
      {
        name: 'etl.sh',
        currentDir: 'scripts',
        fullName: 'scripts/etl.sh',
        dirctory: false,
        type: 'FILE',
        description: null,
        children: [],
      },
    ],
  },
  {
    name: 'readme.txt',
    currentDir: '',
    fullName: 'readme.txt',
    dirctory: false,
    type: 'FILE',
    description: null,
    children: [],
  },
]

function setRole(role: 'admin' | 'developer' | 'operator' | 'viewer'): void {
  authAccount.value = { id: 1, username: role, role }
}

/** 取最后一次 FormData 载荷字段（multipart 不经 http.ts 序列化，字段名须为 current_dir）。 */
function lastForm(): FormData {
  return api.createResourceFile.mock.calls.at(-1)![0] as FormData
}

beforeEach(() => {
  config.global.stubs = { RouterLink: { template: '<a><slot /></a>' } }
  api.listResourceFiles.mockResolvedValue(tree())
})

afterEach(() => {
  vi.clearAllMocks()
  authAccount.value = null
  vi.unstubAllGlobals()
})

describe('§10.10 R9 资源文件取数与树渲染', () => {
  it('一次装载不轮询，目录默认展开且 dirctory 决定分支', async () => {
    setRole('admin')
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    expect(api.listResourceFiles).toHaveBeenCalledTimes(1)
    expect(w.find('[data-resource-file-tree]').exists()).toBe(true)
    expect(w.find('[data-full-name="scripts"]').attributes('data-dir')).toBe('true')
    expect(w.find('[data-full-name="readme.txt"]').attributes('data-dir')).toBe('false')
    expect(w.find('[data-full-name="scripts/etl.sh"]').exists()).toBe(true)
    expect(w.find('[data-file-count]').text()).toBe('2')
  })

  it('折叠目录后隐藏子节点', async () => {
    setRole('admin')
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    await w.find('[data-toggle="scripts"]').trigger('click')
    expect(w.find('[data-full-name="scripts/etl.sh"]').exists()).toBe(false)
  })

  it('D13 搜索：关键字前端过滤，不触发后端', async () => {
    setRole('admin')
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    await w.find('[data-filter-keyword]').setValue('readme')
    expect(w.findAll('[data-full-name]').map((r) => r.attributes('data-full-name'))).toEqual(['readme.txt'])
    expect(api.listResourceFiles).toHaveBeenCalledTimes(1)
  })

  it('空态与错误态互斥；错误横幅透出字符串错误码', async () => {
    setRole('admin')
    api.listResourceFiles.mockResolvedValueOnce([])
    let w = mount(OrchestrationResourceFileView)
    await flushPromises()
    expect(w.find('[data-empty]').exists()).toBe(true)
    expect(w.find('[data-resource-file-tree]').exists()).toBe(false)

    api.listResourceFiles.mockRejectedValueOnce(Object.assign(new Error('resource denied'), { code: 1003 }))
    w = mount(OrchestrationResourceFileView)
    await flushPromises()
    expect(w.find('[data-error]').text()).toContain('code 1003')
    expect(w.find('[data-error]').text()).toContain('resource denied')
    expect(w.find('[data-empty]').exists()).toBe(false)
  })
})

describe('§10.10 R9 currentDir 契约与写操作', () => {
  it('根目录建目录：current_dir 为 `/`（非空，海豚要求）', async () => {
    setRole('admin')
    api.createResourceFile.mockResolvedValue({})
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    await w.find('[data-create-directory]').trigger('click')
    await w.find('[data-dialog-input]').setValue('jobs')
    await w.find('form').trigger('submit')
    await flushPromises()
    const form = lastForm()
    expect(form.get('name')).toBe('jobs')
    expect(form.get('current_dir')).toBe('/')
    expect(form.get('file')).toBeNull()
  })

  it('子目录建目录：current_dir 为该目录 fullName', async () => {
    setRole('admin')
    api.createResourceFile.mockResolvedValue({})
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    await w.find('[data-full-name="scripts"] [data-create-directory-in]').trigger('click')
    await w.find('[data-dialog-input]').setValue('archive')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(lastForm().get('current_dir')).toBe('scripts')
  })

  it('上传：multipart 含 name / current_dir / file', async () => {
    setRole('admin')
    api.createResourceFile.mockResolvedValue({})
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    const input = w.find('[data-upload-input]')
    Object.defineProperty(input.element, 'files', {
      value: [new File(['echo 1'], 'etl.sh')],
      configurable: true,
    })
    await input.trigger('change')
    await flushPromises()
    const form = lastForm()
    expect(form.get('name')).toBe('etl.sh')
    expect(form.get('current_dir')).toBe('/')
    expect((form.get('file') as File).name).toBe('etl.sh')
  })

  it('拖拽到目录行：落到该目录 fullName', async () => {
    setRole('admin')
    api.createResourceFile.mockResolvedValue({})
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    const row = w.find('[data-full-name="scripts"]')
    const event = new Event('drop', { bubbles: true, cancelable: true })
    Object.defineProperty(event, 'dataTransfer', { value: { files: [new File(['x'], 'a.sql')] } })
    row.element.dispatchEvent(event)
    await flushPromises()
    expect(lastForm().get('current_dir')).toBe('scripts')
  })

  it('重命名经 renameResourceFile(fullName, name)', async () => {
    setRole('admin')
    api.renameResourceFile.mockResolvedValue({})
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    await w.find('[data-full-name="readme.txt"] [data-rename]').trigger('click')
    await w.find('[data-dialog-input]').setValue('readme2.txt')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(api.renameResourceFile).toHaveBeenCalledWith({ fullName: 'readme.txt', name: 'readme2.txt' })
  })

  it('删除递归走 deleteResourceFile(fullName)', async () => {
    setRole('admin')
    api.deleteResourceFile.mockResolvedValue({})
    vi.stubGlobal('confirm', () => true)
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    await w.find('[data-full-name="scripts"] [data-delete]').trigger('click')
    await flushPromises()
    expect(api.deleteResourceFile).toHaveBeenCalledWith('scripts')
  })

  it('下载走 downloadResourceFile(fullName)', async () => {
    setRole('admin')
    api.downloadResourceFile.mockResolvedValue(new Blob(['echo 1']))
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    await w.find('[data-full-name="readme.txt"] [data-download]').trigger('click')
    await flushPromises()
    expect(api.downloadResourceFile).toHaveBeenCalledWith('readme.txt')
  })

  it('共享经 share(resource_file) 且失败不关闭弹窗', async () => {
    setRole('admin')
    api.share.mockRejectedValue(Object.assign(new Error('share failed'), { code: 1003 }))
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    await w.find('[data-full-name="readme.txt"] [data-share]').trigger('click')
    await w.find('[data-dialog-input]').setValue('lisi')
    await w.find('form').trigger('submit')
    await flushPromises()
    expect(api.share).toHaveBeenCalledWith('resource_file', 'readme.txt', 'lisi')
    expect(w.find('[data-dialog-error]').text()).toContain('share failed')
    expect(w.find('[data-dialog-input]').exists()).toBe(true)
  })

  it('EDIT_DEFINITION 未授予时不出现任何写操作', async () => {
    setRole('operator')
    const w = mount(OrchestrationResourceFileView)
    await flushPromises()
    expect(w.find('[data-create-directory]').exists()).toBe(false)
    expect(w.find('[data-upload]').exists()).toBe(false)
    expect(w.find('[data-rename]').exists()).toBe(false)
    expect(w.find('[data-delete]').exists()).toBe(false)
    expect(w.find('[data-share]').exists()).toBe(false)
    // 读路径仍可用：下载与刷新不受写门禁影响
    expect(w.find('[data-download]').exists()).toBe(true)
    expect(w.find('[data-refresh]').exists()).toBe(true)
  })
})
