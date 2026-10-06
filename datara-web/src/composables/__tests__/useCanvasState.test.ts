// @vitest-environment happy-dom
/**
 * Task 14（方案§3.7/§4.5）：useCanvasState 画布状态持久化单测。
 * happy-dom 提供真实 Storage/localStorage（默认 node 环境无 Storage 原型，
 * 隐私模式用例需 spyOn(Storage.prototype, 'setItem')）。
 * 写侧 500ms 防抖：统一用 vi.useFakeTimers 推进时钟验证落盘时机。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { loadCanvasState, saveCanvasState } from '../useCanvasState'

/** 最小可用状态构造器（视口 x/y 固定，zoom 作区分位；version 随写入恒为 1） */
function st(zoom: number, selectedIds: string[] = [], activeTab = '', floats: Record<string, boolean> = {}) {
  return { version: 1 as const, viewport: { x: 1, y: 2, zoom }, selectedIds, activeTab, floats }
}

describe('useCanvasState（方案§3.7 localStorage canvas-state:{docId}）', () => {
  beforeEach(() => { localStorage.clear() })
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks() })

  it('保存后可恢复视口/选中/Tab/浮窗（500ms 防抖落盘）', () => {
    vi.useFakeTimers()
    saveCanvasState('doc1', { version: 1, viewport: { x: 1, y: 2, zoom: 0.8 }, selectedIds: ['n1'], activeTab: '依赖', floats: { legend: true } })
    vi.advanceTimersByTime(500)
    expect(loadCanvasState('doc1')).toMatchObject({
      viewport: { x: 1, y: 2, zoom: 0.8 },
      selectedIds: ['n1'],
      activeTab: '依赖',
      floats: { legend: true },
    })
  })

  it('防抖：窗口内重复保存只落最后一次', () => {
    vi.useFakeTimers()
    saveCanvasState('doc1', st(0.8))
    vi.advanceTimersByTime(300)
    saveCanvasState('doc1', st(1.1)) // 重置本 docId 的防抖窗口
    vi.advanceTimersByTime(300) // 首个 500ms 到期但已被重置，不应落盘
    expect(localStorage.getItem('canvas-state:doc1')).toBeNull()
    vi.advanceTimersByTime(200)
    expect(loadCanvasState('doc1')).toMatchObject({ viewport: { zoom: 1.1 } })
  })

  it('多实例交叉保存：不同 docId 防抖互不覆盖（keep-alive 多画布共存，模块级单槽会互相冲掉）', () => {
    vi.useFakeTimers()
    saveCanvasState('docA', st(0.8))
    vi.advanceTimersByTime(200)
    saveCanvasState('docB', st(1.2)) // docA 未落盘时 docB 开启自己的独立窗口
    vi.advanceTimersByTime(300) // docA 到期落盘，docB 尚余 200ms
    expect(localStorage.getItem('canvas-state:docA')).not.toBeNull()
    expect(localStorage.getItem('canvas-state:docB')).toBeNull()
    vi.advanceTimersByTime(200) // docB 到期落盘
    expect(loadCanvasState('docA')).toMatchObject({ viewport: { zoom: 0.8 } })
    expect(loadCanvasState('docB')).toMatchObject({ viewport: { zoom: 1.2 } })
  })

  it('load 先 flush 再读：未满 500ms 的最新值立即可读，且旧定时器已清不再回写', () => {
    vi.useFakeTimers()
    saveCanvasState('doc3', st(0.9))
    expect(loadCanvasState('doc3')).toMatchObject({ viewport: { zoom: 0.9 } }) // Task 14 审查修复：防抖窗口内先 flush 落盘再读，不再丢 ≤500ms 增量
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')
    vi.advanceTimersByTime(500)
    expect(setItemSpy).not.toHaveBeenCalled() // flush 已清掉旧定时器：恢复后无回写覆盖
    expect(loadCanvasState('doc3')).toMatchObject({ viewport: { zoom: 0.9 } })
  })

  it('隐私模式写失败不抛错（落盘触发时同样静默）', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    vi.useFakeTimers()
    expect(() => {
      saveCanvasState('doc2', st(1))
      vi.advanceTimersByTime(500)
    }).not.toThrow()
  })

  it('损坏数据读容错：返回 null 不抛错', () => {
    localStorage.setItem('canvas-state:doc4', '{oops')
    expect(loadCanvasState('doc4')).toBeNull()
  })
})
