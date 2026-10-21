/**
 * INC4-FE-2（4.2b）验收测试：I11 画布多 Tab store。
 *
 * 覆盖（蓝本 datara-web/src/stores/dagTabs.ts 照抄语义 + §5A.2 三分类收窄）：
 *  - open：'ok'（新开+激活）/ 'dup'（同 docId 仅激活不重复）/ 'full'（MAX_DAG_TABS=5 拒绝）；
 *  - activate：存在才生效（非法 key 不篡改 activeKey）；
 *  - remove：激活中段 → 右邻落位（Math.min(idx, len-1) 语义）；末位 → 左邻；
 *    独 Tab → 无激活；非激活关闭 activeKey 不动；不存在 → null；
 *    返回被移除 docId（宿主清理草稿快照用）；
 *  - 收窄锁：DagProfileType 三分类无 'etl'（@ts-expect-error 编译期锁定，回潮即红）。
 */
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { MAX_DAG_TABS, useDagTabsStore, type DagProfileType } from '../dagTabs'

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('INC4-FE-2 dagTabs store（画布多 Tab 内核，蓝本照抄 + §5A.2 收窄）', () => {
  it('MAX_DAG_TABS=5（用户裁定上限锚）', () => {
    expect(MAX_DAG_TABS).toBe(5)
  })

  it('§5A.2 收窄锁：DagProfileType 三分类（wf/sync/stream）无 etl', () => {
    const ok: DagProfileType[] = ['wf', 'sync', 'stream']
    expect(ok).toHaveLength(3)
    // @ts-expect-error §5A.2：etl 已删，四类型回潮则此行编译报错
    const bad: DagProfileType = 'etl'
    expect(bad).toBe('etl')
  })

  it('初始态：空 tabs / 无激活 / count=0 / isOpen=false', () => {
    const s = useDagTabsStore()
    expect(s.tabs).toEqual([])
    expect(s.activeKey).toBe('')
    expect(s.activeTab).toBeNull()
    expect(s.count).toBe(0)
    expect(s.isOpen('d1')).toBe(false)
  })

  it("open 新开 → 'ok'：push + 激活，key=docId，code 承载", () => {
    const s = useDagTabsStore()
    const r = s.open({ docId: 'd1', name: '任务一', type: 'wf', code: 101 })
    expect(r).toBe('ok')
    expect(s.count).toBe(1)
    expect(s.activeKey).toBe('d1')
    expect(s.activeTab).toMatchObject({ key: 'd1', docId: 'd1', name: '任务一', type: 'wf', code: 101 })
    expect(s.isOpen('d1')).toBe(true)
  })

  it("open 同 docId → 'dup'：仅激活已有 Tab，不重复 push（同画布单实例裁定）", () => {
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '一', type: 'wf' })
    s.open({ docId: 'd2', name: '二', type: 'sync' })
    const r = s.open({ docId: 'd1', name: '一', type: 'wf' })
    expect(r).toBe('dup')
    expect(s.count).toBe(2)
    expect(s.activeKey).toBe('d1')
  })

  it("open 满 5 → 'full'：拒绝且不 push", () => {
    const s = useDagTabsStore()
    for (let i = 1; i <= MAX_DAG_TABS; i++) s.open({ docId: `d${i}`, name: `t${i}`, type: 'wf' })
    expect(s.count).toBe(MAX_DAG_TABS)
    expect(s.open({ docId: 'd6', name: 't6', type: 'stream' })).toBe('full')
    expect(s.count).toBe(MAX_DAG_TABS)
    expect(s.isOpen('d6')).toBe(false)
  })

  it('activate：不存在的 key 不生效', () => {
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '一', type: 'wf' })
    s.open({ docId: 'd2', name: '二', type: 'wf' })
    s.activate('nope')
    expect(s.activeKey).toBe('d2')
    s.activate('d1')
    expect(s.activeKey).toBe('d1')
  })

  it('remove 激活中段 Tab → 右邻落位（Math.min(idx, len-1)），返回被移除 docId', () => {
    const s = useDagTabsStore()
    for (const id of ['d1', 'd2', 'd3']) s.open({ docId: id, name: id, type: 'wf' })
    s.activate('d2')
    expect(s.remove('d2')).toBe('d2')
    expect(s.count).toBe(2)
    // splice 后 tabs=[d1,d3]，idx=1 → min(1, 1)=1 → 右邻 d3（蓝本落位语义）
    expect(s.activeKey).toBe('d3')
  })

  it('remove 末位激活 Tab → 左邻落位（min 收口到末位索引）', () => {
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '一', type: 'wf' })
    s.open({ docId: 'd2', name: '二', type: 'wf' })
    s.activate('d2')
    expect(s.remove('d2')).toBe('d2')
    // splice 后 tabs=[d1]，idx=1 → min(1, 0)=0 → 左邻 d1
    expect(s.activeKey).toBe('d1')
  })

  it('remove 最后一个 Tab → 无激活（activeKey 清空）', () => {
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '一', type: 'wf' })
    expect(s.remove('d1')).toBe('d1')
    expect(s.count).toBe(0)
    expect(s.activeKey).toBe('')
    expect(s.activeTab).toBeNull()
  })

  it('remove 非激活 Tab：activeKey 不变', () => {
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '一', type: 'wf' })
    s.open({ docId: 'd2', name: '二', type: 'wf' })
    s.activate('d1')
    expect(s.remove('d2')).toBe('d2')
    expect(s.count).toBe(1)
    expect(s.activeKey).toBe('d1')
  })

  it('remove 不存在 → null 且状态不变', () => {
    const s = useDagTabsStore()
    s.open({ docId: 'd1', name: '一', type: 'wf' })
    expect(s.remove('nope')).toBeNull()
    expect(s.count).toBe(1)
    expect(s.activeKey).toBe('d1')
  })
})
