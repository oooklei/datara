/**
 * §0.3 灰度开关登记表（方案 §11.5）：统一挂 localStorage 键 `datara.flags`，运行时可改。
 * 读取即时生效（每次调用重读 + 解析容错），setFlags 写入后同页与跨页（storage 事件）均可感知。
 *
 * 使用示例（浏览器控制台）：
 *   localStorage.setItem('datara.flags', '{"sseSource":"pubsub","undoCommandStack":true}')
 */
import { ref } from 'vue'

/** Vue 响应式版本号：setFlags / 跨页 storage 变更自增，供 computed 订阅开关翻转 */
const version = ref(0)

export type SseSource = 'polling' | 'pubsub'

export interface DataraFlags {
  /** SSE 推送源：polling（默认，node_event SSE 订阅关闭，走既有轮询/实例流/总线通道）| pubsub（runEventSource 启用，Task 17/18） */
  sseSource: SseSource
  /** undo 历史：off（默认，快照栈，现状不动）| on（命令栈，Task 22） */
  undoCommandStack: boolean
}

const KEY = 'datara.flags'

const DEFAULTS: DataraFlags = {
  sseSource: 'polling',
  undoCommandStack: false,
}

/** 读取灰度开关（缺省/脏数据一律回落默认，隐私模式等异常吞掉） */
export function getFlags(): DataraFlags {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return { ...DEFAULTS }
    const parsed = JSON.parse(raw) as Partial<DataraFlags> | null
    return {
      sseSource: parsed?.sseSource === 'pubsub' ? 'pubsub' : 'polling',
      undoCommandStack: parsed?.undoCommandStack === true,
    }
  } catch {
    return { ...DEFAULTS }
  }
}

/** 合并写入（运行时可改；写入即自增响应式版本号） */
export function setFlags(patch: Partial<DataraFlags>): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...getFlags(), ...patch }))
    version.value += 1
  } catch { /* 隐私模式等存储不可用：开关维持默认，容忍 */ }
}

export function getSseSource(): SseSource {
  return getFlags().sseSource
}

export function isUndoCommandStackOn(): boolean {
  return getFlags().undoCommandStack
}

/** 供 computed 依赖订阅：flagsVersion() 变化触发重算（运行时改开关即刻反映到 UI 态） */
export function flagsVersion(): number {
  return version.value
}

/* 跨页同步：其他标签页改了 datara.flags → 本页版本号自增（无 window 环境跳过） */
if (typeof window !== 'undefined') {
  window.addEventListener('storage', (e) => {
    if (e.key === KEY) version.value += 1
  })
}
