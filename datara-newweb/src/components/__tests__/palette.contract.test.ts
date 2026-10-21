/**
 * INC4-FE-3（4.2c）+ INC4-FE-4（4.2d）验收测试：Palette 双 Tab（组件库 / 工作流目录树）。
 *
 * FE-3 覆盖（蓝本 datara-web/src/graph/workbench/Palette.vue 双 Tab 框架照抄语义
 * + §5A.3 组件规格一源零私设）：
 *  1. 双 Tab 渲染（顺序 组件/工作流 + 缺省激活「组件」+ 搜索框在位）；
 *  2. defaultTab='wf' 初始激活工作流 + 无项目上下文空态降级文案；
 *  3. 分组渲染：description.category 路径末段组名 / 空类别归「通用」/
 *     .cnt 计数 / .p-ico color+icon / .p-code（identity.code 字符串探测）；
 *  4. paletteVisible===false 过滤（normalizeSpec 契约，D1 闸门 §13-5）；
 *  5. 搜索三通道：displayName(label) / summary(desc) / type；
 *  6. 分组折叠 toggle（.fold class）；
 *  7. 拖拽契约：setData('datara/node-type', type) + effectAllowed='copy'；
 *  8. 规格加载失败：console.warn + 空态「无匹配组件」（首载 fail-closed 不阻断宿主）；
 *  9. identity.code 非字符串不渲染 .p-code（badge 结构陷阱规避）；
 * 10. 规格未加载完成前不闪空态（loaded 门控）。
 *
 * FE-4 覆盖（蓝本 L74-258 逻辑 / L307-388 模板照抄 + §5A.2 三分类收窄）：
 *  11. 无 projectId（/dag 过渡路由）：空态「候选池待项目上下文接驳」，候选池 API 不调用；
 *  12. 目录树渲染：同步/流内置目录 + 根目录平铺（无标签/存量 ETL 降级）、
 *      .fold 默认收起 toggle、行 #code 徽标（d.code != null 门控）；
 *  13. 三分类 typeOf：tags['同步']→sync / ['流']→stream / []→wf（ETL 无分支落 wf）；
 *  14. kw 过滤：命中过滤行 + 无命中「无匹配任务」；
 *  15. 勾选/全选/载入：togglePick + toggleAll + onLoad emit load-tasks
 *      （wire id number → DagPickItem.id string 桥接 + typeOf 推导 + code 直通）；
 *  16. 行操作 RED：moveTo/newCategory → setWfTags/createCategory reject 哨兵 →
 *      候裁降级提示（deleteRow 走 confirm → deleteWorkflowDefinition → 重拉）。
 *
 * 依赖 mock：componentSpecApi（specLoad hoisted——组件一源 API 不进网络层）、
 * workflowApi（poolLoad/catsLoad/catsSetTags/poolDelete——候选池真端点不进网络层）、
 * element-plus（ElMessage / ElMessageBox——行操作弹窗不进 DOM，断言调用参数）。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const {
  specLoad,
  poolLoad,
  poolDelete,
  catsLoad,
  catsSetTags,
  catsCreate,
  msgInfo,
  msgSuccess,
  msgWarning,
  msgError,
  boxConfirm,
  boxPrompt,
} = vi.hoisted(() => ({
  specLoad: vi.fn(),
  poolLoad: vi.fn(),
  poolDelete: vi.fn(),
  catsLoad: vi.fn(),
  catsSetTags: vi.fn(),
  catsCreate: vi.fn(),
  msgInfo: vi.fn(),
  msgSuccess: vi.fn(),
  msgWarning: vi.fn(),
  msgError: vi.fn(),
  boxConfirm: vi.fn(),
  boxPrompt: vi.fn(),
}))

vi.mock('../../services/rebuild/componentSpecApi', () => ({
  loadComponentSpecs: specLoad,
  resetComponentSpecCache: vi.fn(),
}))

vi.mock('../../services/rebuild/workflowApi', () => ({
  listWorkflowDefinitions: poolLoad,
  deleteWorkflowDefinition: poolDelete,
  WF_CATEGORIES_NOT_WIRED: 'WF_CATEGORIES_NOT_WIRED: rebuild/workflow categories contract not connected yet',
  workflowCategories: {
    listCategories: catsLoad,
    createCategory: catsCreate,
    deleteCategory: vi.fn(),
    setWfTags: catsSetTags,
  },
}))

vi.mock('element-plus', () => ({
  ElMessage: { info: msgInfo, success: msgSuccess, warning: msgWarning, error: msgError },
  ElMessageBox: { confirm: boxConfirm, prompt: boxPrompt },
}))

import Palette from '../Palette.vue'
import type { ComponentSpecItem } from '../../services/rebuild/componentSpecApi'

/** 构造 ComponentSpecItem 形状快照项（仅 identity/description/visual 参与渲染映射） */
function item(over: {
  type: string
  identity?: Record<string, unknown>
  description?: Record<string, unknown>
  visual?: Record<string, unknown>
}): ComponentSpecItem {
  return {
    type: over.type,
    publishedVersion: 1,
    identity: over.identity ?? {},
    description: over.description ?? {},
    inputs: [],
    outputs: [],
    visual: over.visual ?? {},
    behaviors: [],
    dropPolicy: null,
    extensions: {},
    specVersion: 1,
    ports: {},
  }
}

function mountPalette(props: { defaultTab?: 'palette' | 'wf'; projectId?: number } = {}) {
  return mount(Palette, { props })
}

beforeEach(() => {
  specLoad.mockReset()
  specLoad.mockResolvedValue({ items: [], etag: '"00"', source: 'network' })
  poolLoad.mockReset()
  poolLoad.mockResolvedValue([])
  poolDelete.mockReset()
  poolDelete.mockResolvedValue(undefined)
  catsLoad.mockReset()
  catsLoad.mockRejectedValue(new Error('WF_CATEGORIES_NOT_WIRED: rebuild/workflow categories contract not connected yet'))
  catsSetTags.mockReset()
  catsCreate.mockReset()
  msgInfo.mockClear()
  msgSuccess.mockClear()
  msgWarning.mockClear()
  msgError.mockClear()
  boxConfirm.mockReset()
  boxConfirm.mockImplementation(() => Promise.resolve())
  boxPrompt.mockReset()
})

describe('INC4-FE-3 Palette 双 Tab（组件库 / 工作流）', () => {
  it('双 Tab 顺序照抄（组件/工作流），缺省激活「组件」且搜索框在位', async () => {
    const w = mountPalette()
    await flushPromises()
    const tabs = w.findAll('.pal-tab')
    expect(tabs).toHaveLength(2)
    expect(tabs[0].text()).toBe('组件')
    expect(tabs[1].text()).toBe('工作流')
    expect(tabs[0].classes()).toContain('on')
    expect(tabs[1].classes()).not.toContain('on')
    // 缺省 Tab = 组件库：搜索框 + 分组列表在位，FE-4 占位不存在
    expect(w.find('.pal-search input').exists()).toBe(true)
    expect(w.find('.pal-empty').exists()).toBe(false)
  })

  it("defaultTab='wf' 初始激活工作流 Tab + 无项目上下文空态降级（目录树归候选池接线）", async () => {
    const w = mountPalette({ defaultTab: 'wf' })
    await flushPromises()
    const tabs = w.findAll('.pal-tab')
    expect(tabs[1].classes()).toContain('on')
    expect(tabs[0].classes()).not.toContain('on')
    // FE-4：wf 分支自带工作任务搜索框（空态降级也在位）
    expect(w.find('.pal-search input').exists()).toBe(true)
    // FE-4 空态三分支：kw 空 + 无 projectId → 「候选池待项目上下文接驳」
    expect(w.find('.pal-empty').text()).toContain('候选池待项目上下文接驳')
    // 无项目上下文：候选池 API 不调用（buildPool hasProject=false 直接置空池）
    expect(poolLoad).not.toHaveBeenCalled()
    expect(catsLoad).not.toHaveBeenCalled()
    // 点击切回组件库：占位消失、搜索框出现
    await tabs[0].trigger('click')
    expect(w.find('.pal-empty').exists()).toBe(false)
    expect(w.find('.pal-search input').exists()).toBe(true)
  })

  it('分组渲染：category 路径末段组名 / 空类别归「通用」/ cnt 计数 / ico+code 行渲染', async () => {
    specLoad.mockResolvedValue({
      items: [
        item({
          type: 'mysql.source',
          identity: { displayName: 'MySQL 数据源', code: 'mysql' },
          description: { summary: '读取 MySQL 库表', category: '批处理与同步/数据源' },
          visual: { icon: '▤', color: '#0ea5e9' },
        }),
        item({
          type: 'py.batch',
          identity: { displayName: 'Python 计算' },
          description: { summary: '脚本批处理', category: '批处理与同步/计算' },
          visual: { icon: '𝑥', color: '#f59e0b' },
        }),
        item({ type: 'noop.node', identity: { displayName: '空操作' }, description: {} }),
      ],
      etag: '"aa"',
      source: 'network',
    })
    const w = mountPalette()
    await flushPromises()
    const cats = w.findAll('.pal-cat')
    expect(cats).toHaveLength(3)
    // 组名 = 路径末段（不含「批处理与同步/」前缀）；.pal-cat-head 文本含 ▼ 前缀
    expect(cats[0].find('.pal-cat-head').text()).toContain('数据源')
    expect(cats[0].find('.pal-cat-head').text()).not.toContain('批处理与同步')
    expect(cats[1].find('.pal-cat-head').text()).toContain('计算')
    // 空类别归「通用」
    expect(cats[2].find('.pal-cat-head').text()).toContain('通用')
    // .cnt 计数
    expect(cats[0].find('.cnt').text()).toBe('1')
    expect(cats[2].find('.cnt').text()).toBe('1')
    // 行渲染：icon + color 内联背景 + code 徽标
    const row0 = cats[0].find('.pal-item')
    expect(row0.find('.p-ico').text()).toBe('▤')
    expect(row0.find('.p-ico').attributes('style')).toContain('background: #0ea5e9')
    expect(row0.find('.p-name').text()).toContain('MySQL 数据源')
    expect(row0.find('.p-code').text()).toBe('mysql')
  })

  it('paletteVisible===false 项过滤（normalizeSpec 契约 runtime-only 不进调色板）', async () => {
    specLoad.mockResolvedValue({
      items: [
        item({ type: 'a.ok', identity: { displayName: '可见组件' } }),
        item({ type: 'b.runtime', identity: { displayName: '运行态组件' }, visual: { paletteVisible: false } }),
      ],
      etag: '"bb"',
      source: 'network',
    })
    const w = mountPalette()
    await flushPromises()
    const items = w.findAll('.pal-item')
    expect(items).toHaveLength(1)
    expect(items[0].text()).toContain('可见组件')
    expect(items[0].text()).not.toContain('运行态组件')
  })

  it('搜索三通道：displayName / summary / type 命中，无命中渲染空态', async () => {
    specLoad.mockResolvedValue({
      items: [
        item({ type: 'a.type', identity: { displayName: 'MySQL 数据源' }, description: { summary: '连接数据库' } }),
        item({ type: 'b.type', identity: { displayName: 'CSV 读取' }, description: { summary: '解析 csv 文件' } }),
        item({ type: 'c.shell', identity: { displayName: '脚本' }, description: { summary: '自定义脚本' } }),
      ],
      etag: '"cc"',
      source: 'network',
    })
    const w = mountPalette()
    await flushPromises()
    const kw = w.find('.pal-search input')
    // label 通道
    await kw.setValue('mysql')
    expect(w.findAll('.pal-item')).toHaveLength(1)
    expect(w.findAll('.pal-item')[0].text()).toContain('MySQL 数据源')
    // desc 通道
    await kw.setValue('csv 文件')
    expect(w.findAll('.pal-item')).toHaveLength(1)
    expect(w.findAll('.pal-item')[0].text()).toContain('CSV 读取')
    // type 通道
    await kw.setValue('shell')
    expect(w.findAll('.pal-item')).toHaveLength(1)
    expect(w.findAll('.pal-item')[0].text()).toContain('脚本')
    // 无命中 → 空态（蓝本原文「无匹配组件」）
    await kw.setValue('xyz-无匹配')
    expect(w.findAll('.pal-item')).toHaveLength(0)
    expect(w.find('.pal-list').text()).toContain('无匹配组件')
  })

  it('分组折叠 toggle：点击 .pal-cat-head 加/去 .fold（▼ 旋转态由样式承接）', async () => {
    specLoad.mockResolvedValue({
      items: [
        item({ type: 'a.x', identity: { displayName: '甲' }, description: { category: '组/一' } }),
        item({ type: 'b.y', identity: { displayName: '乙' }, description: { category: '组/二' } }),
      ],
      etag: '"dd"',
      source: 'network',
    })
    const w = mountPalette()
    await flushPromises()
    const cat = w.find('.pal-cat')
    expect(cat.classes()).not.toContain('fold')
    await cat.find('.pal-cat-head').trigger('click')
    expect(cat.classes()).toContain('fold')
    await cat.find('.pal-cat-head').trigger('click')
    expect(cat.classes()).not.toContain('fold')
  })

  it('拖拽契约：dragstart setData(datara/node-type, type) + effectAllowed=copy', async () => {
    specLoad.mockResolvedValue({
      items: [item({ type: 'mysql.source', identity: { displayName: 'MySQL 数据源' } })],
      etag: '"ee"',
      source: 'network',
    })
    const w = mountPalette()
    await flushPromises()
    const fakeDT = { setData: vi.fn(), effectAllowed: '' }
    await w.find('.pal-item').trigger('dragstart', { dataTransfer: fakeDT })
    expect(fakeDT.setData).toHaveBeenCalledWith('datara/node-type', 'mysql.source')
    expect(fakeDT.effectAllowed).toBe('copy')
  })

  it('规格加载失败：console.warn + 空态「无匹配组件」（首载 fail-closed 不阻断宿主）', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    specLoad.mockRejectedValue(new Error('spec endpoint unreachable'))
    const w = mountPalette()
    await flushPromises()
    expect(warnSpy).toHaveBeenCalled()
    expect(w.find('.pal-list').text()).toContain('无匹配组件')
    warnSpy.mockRestore()
  })

  it('identity.code 非字符串不渲染 .p-code（badge 结构陷阱规避）', async () => {
    specLoad.mockResolvedValue({
      items: [
        item({ type: 'a.bad', identity: { displayName: '数字码', code: 123 } }),
        item({ type: 'b.good', identity: { displayName: '字符串码', code: 'csv' } }),
      ],
      etag: '"ff"',
      source: 'network',
    })
    const w = mountPalette()
    await flushPromises()
    const items = w.findAll('.pal-item')
    expect(items).toHaveLength(2)
    expect(items[0].find('.p-code').exists()).toBe(false)
    expect(items[1].find('.p-code').text()).toBe('csv')
  })

  it('规格未加载完成前不闪空态（loaded 门控：挂载瞬间不渲染「无匹配组件」）', async () => {
    specLoad.mockReturnValue(new Promise(() => {})) // 永不 resolve 模拟在途请求
    const w = mountPalette()
    // 不 flushPromises：同步断言挂载瞬间状态
    expect(w.find('.pal-list').text()).not.toContain('无匹配组件')
    expect(w.findAll('.pal-item')).toHaveLength(0)
  })
})

describe('INC4-FE-4 工作流目录树（三分类收窄 + 行操作 RED 降级）', () => {
  const POOL = [
    { id: 1, name: '同步一', tags: ['同步'], code: 1 },
    { id: 2, name: '流二', tags: ['流'] },
    { id: 3, name: '普通三', tags: [] },
    { id: 4, name: '旧ETL', tags: ['ETL'], code: 4 },
  ]

  it('目录树渲染：同步/流内置目录 + 根目录平铺（ETL 降级），.fold 默认收起 toggle，行操作门控', async () => {
    poolLoad.mockResolvedValue(POOL)
    const w = mountPalette({ defaultTab: 'wf', projectId: 7 })
    await flushPromises()
    // 候选池真端点调用（projectId 透传）
    expect(poolLoad).toHaveBeenCalledWith(7)
    // 内置目录两枚（同步/流），计数各 1；初始 .fold 收起（蓝本 !wfFolded 反转语义），点击表头展开
    const cats = w.findAll('.pal-cat')
    expect(cats).toHaveLength(2)
    expect(cats[0].find('.pal-cat-head').text()).toContain('同步')
    expect(cats[1].find('.pal-cat-head').text()).toContain('流')
    expect(cats[0].find('.cnt').text()).toBe('1')
    expect(cats[1].find('.cnt').text()).toBe('1')
    expect(cats[0].classes()).toContain('fold')
    await cats[0].find('.pal-cat-head').trigger('click')
    expect(cats[0].classes()).not.toContain('fold')
    // 根目录平铺：普通三（tags []）+ 旧ETL（tags ['ETL'] 无分支降级映射 wf，候裁披露③）
    const rootItems = w.findAll('.pal-task.wf-root-item')
    expect(rootItems).toHaveLength(2)
    expect(rootItems[0].text()).toContain('普通三')
    expect(rootItems[1].text()).toContain('旧ETL')
    // #code 徽标（d.code != null 门控）：#1 在同步目录行、#4 在根目录行，DOM 序一致
    const codes = w.findAll('.pal-tasks .p-code')
    expect(codes.map((c) => c.text())).toEqual(['#1', '#4'])
    // 真项目行操作在位（projectId 缺位时不渲染，见用例 11）
    expect(w.findAll('.pt-move')).toHaveLength(4)
    expect(w.findAll('.pt-del')).toHaveLength(4)
  })

  it('typeOf 三分类经 onLoad：tags[同步]→sync，wire id number→String 桥接 + code 直通，载入后勾选清空', async () => {
    poolLoad.mockResolvedValue([{ id: 1, name: '同步一', tags: ['同步'], code: 1 }])
    const w = mountPalette({ defaultTab: 'wf', projectId: 7 })
    await flushPromises()
    // 勾选行 → 已选计数 + 载入按钮解除 disabled
    await w.find('.pal-task').trigger('click')
    expect(w.find('.pal-hint b').text()).toBe('1')
    expect(w.find('.pal-load').attributes('disabled')).toBeUndefined()
    // 载入 → load-tasks emit（String(id) 桥接 + typeOf 推导 sync + code 直通）
    await w.find('.pal-load').trigger('click')
    const evt = w.emitted('load-tasks')?.[0]?.[0] as {
      items: Array<{ id: string; name: string; type: string; code?: number }>
    }
    expect(evt.items).toEqual([{ id: '1', name: '同步一', type: 'sync', code: 1 }])
    // 载入后勾选清空（跨分组保留在 FE-4 行为内不另设用例）
    expect(w.find('.pal-hint b').text()).toBe('0')
    expect(w.find('.pal-load').attributes('disabled')).toBeDefined()
  })

  it('kw 过滤：命中行过滤（目录/根目录同步收窄）+ 无命中「无匹配任务」', async () => {
    poolLoad.mockResolvedValue(POOL)
    const w = mountPalette({ defaultTab: 'wf', projectId: 7 })
    await flushPromises()
    await w.find('.pal-search input').setValue('流二')
    // 仅流目录 1 行（同步目录与根目录均被过滤为空、不再渲染）
    expect(w.findAll('.pal-cat')).toHaveLength(1)
    expect(w.findAll('.pal-cat')[0].find('.pal-cat-head').text()).toContain('流')
    expect(w.findAll('.pal-task')).toHaveLength(1)
    expect(w.find('.pal-empty').exists()).toBe(false)
    // 无命中 → 空态「无匹配任务」（三分支 kw 分支）
    await w.find('.pal-search input').setValue('xyz')
    expect(w.find('.pal-empty').text()).toBe('无匹配任务')
  })

  it('目录全选 toggle：.pal-all change → toggleAll 计数 + 行 .on 态 + 载入按钮 disabled 随动', async () => {
    poolLoad.mockResolvedValue([
      { id: 1, name: '同步一', tags: ['同步'] },
      { id: 2, name: '同步二', tags: ['同步'] },
    ])
    const w = mountPalette({ defaultTab: 'wf', projectId: 7 })
    await flushPromises()
    const all = w.find('.pal-cat .pal-all input')
    expect(w.find('.pal-load').attributes('disabled')).toBeDefined()
    await all.setValue(true)
    expect(w.find('.pal-hint b').text()).toBe('2')
    expect(w.findAll('.pal-task.on')).toHaveLength(2)
    expect(w.find('.pal-load').attributes('disabled')).toBeUndefined()
    await all.setValue(false)
    expect(w.find('.pal-hint b').text()).toBe('0')
    expect(w.findAll('.pal-task.on')).toHaveLength(0)
    expect(w.find('.pal-load').attributes('disabled')).toBeDefined()
  })

  it('行操作 RED：moveTo/newCategory 哨兵 reject → 候裁降级提示；内置名警告；deleteRow 确认后重拉', async () => {
    poolLoad.mockResolvedValue([{ id: 1, name: '同步一', tags: ['同步'], code: 1 }])
    const w = mountPalette({ defaultTab: 'wf', projectId: 7 })
    await flushPromises()
    // moveTo：select 换目标目录 → setWfTags 哨兵 reject → 候裁降级提示
    catsSetTags.mockRejectedValue(new Error('WF_CATEGORIES_NOT_WIRED: rebuild/workflow categories contract not connected yet'))
    await w.find('.pt-move').setValue('流')
    await flushPromises()
    expect(catsSetTags).toHaveBeenCalledWith(1, ['流'])
    expect(msgError).toHaveBeenCalledWith('分类系端点未接驳（候裁中），移动暂不可用')
    // newCategory：自定义名 → createCategory 哨兵 reject → 候裁降级提示
    catsCreate.mockRejectedValue(new Error('WF_CATEGORIES_NOT_WIRED: rebuild/workflow categories contract not connected yet'))
    boxPrompt.mockResolvedValue({ value: '新目录' })
    await w.find('.pal-mini').trigger('click')
    await flushPromises()
    expect(catsCreate).toHaveBeenCalledWith('新目录')
    expect(msgError).toHaveBeenCalledWith('分类系端点未接驳（候裁中），新建暂不可用')
    // newCategory：内置名 → warning 无需新建（不触 createCategory）
    boxPrompt.mockResolvedValue({ value: '同步' })
    await w.find('.pal-mini').trigger('click')
    await flushPromises()
    expect(msgWarning).toHaveBeenCalledWith('「同步」为内置、根目录，无需新建')
    // deleteRow：confirm（beforeEach 默认 resolve）→ 删除 → 成功提示 + 候选池重拉
    expect(poolLoad).toHaveBeenCalledTimes(1)
    await w.find('.pt-del').trigger('click')
    await flushPromises()
    expect(poolDelete).toHaveBeenCalledWith(7, 1)
    expect(msgSuccess).toHaveBeenCalledWith('已删除「同步一」')
    expect(poolLoad).toHaveBeenCalledTimes(2)
  })
})
