/**
 * Task 14（方案§3.7/§4.5）：画布状态持久化（localStorage 键 `canvas-state:{docId}`）。
 *
 * - CanvasState：结构版本（演进位）/ 视口 / 多选集 / 激活 Tab / 浮窗开合（导航面板、错误面板）；
 * - 写侧 500ms 防抖：move-end / 选区与浮窗开合为高频触发，静默期后只落最后一次；
 * - 按 docId 独立防抖槽（Map）：keep-alive 后多画布实例共存，500ms 窗口内不同
 *   docId 交叉保存互不覆盖（模块级单槽 pending/timer 会互相冲掉对方状态）；
 * - 隐私模式 / 禁用 localStorage：try/catch 静默吞异常（与工作台快照同口径）；
 * - loadCanvasState：读侧容错（无记录 / 损坏 JSON 返回 null）；读前先 flush 该 docId
 *   未落盘的 pending（Task 14 审查修复：替代原先直接取消——取消会丢 ≤500ms 的增量，
 *   先落盘再读既保住最新状态，也同步清掉旧定时器，不存在恢复后被旧定时器回写覆盖）。
 */

/** 画布持久化状态（结构版本 + 视口 + 选区 + 激活 Tab + 浮窗开合） */
export interface CanvasState {
  /** 结构版本（写入恒为 1）：未来字段迁移/语义变更时递增，读侧按版本分流；当前读侧不强制校验（旧记录无 version 仍可读） */
  version: 1
  viewport: { x: number; y: number; zoom: number }
  selectedIds: string[]
  activeTab: string
  floats: Record<string, boolean>
}

/** 写侧防抖窗口（ms） */
const DEBOUNCE_MS = 500

const KEY = (docId: string) => `canvas-state:${docId}`

/** per-docId 防抖槽：pending 存最新待写状态，timers 存对应定时器句柄（落盘/flush 后即清，不常驻） */
const pendings = new Map<string, CanvasState>()
const timers = new Map<string, ReturnType<typeof setTimeout>>()

/** flush 某 docId 的 pending：立即落盘最新状态并清掉定时器（写失败静默——隐私模式） */
function flushPending(docId: string): void {
  const t = timers.get(docId)
  if (t) { clearTimeout(t); timers.delete(docId) }
  const pending = pendings.get(docId)
  if (!pending) return
  pendings.delete(docId)
  try { localStorage.setItem(KEY(docId), JSON.stringify(pending)) } catch { /* 隐私模式等写失败：静默 */ }
}

/** 保存画布状态（500ms 防抖、按 docId 隔离） */
export function saveCanvasState(docId: string, st: CanvasState): void {
  pendings.set(docId, st)
  const prev = timers.get(docId)
  if (prev) clearTimeout(prev)
  timers.set(docId, setTimeout(() => flushPending(docId), DEBOUNCE_MS))
}

/** 读取画布状态：无记录 / 损坏数据返回 null；读前先 flush 未落盘 pending（先落再读，保住 ≤500ms 增量） */
export function loadCanvasState(docId: string): CanvasState | null {
  flushPending(docId)
  try {
    const raw = localStorage.getItem(KEY(docId))
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return null
    return parsed as CanvasState
  } catch { return null }
}
