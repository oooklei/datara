/**
 * datara → dbx IDE 变量桥（postMessage）。
 *
 * datara 不再自研 IDE，改为 iframe 集成 dbx（同源子路径 `/ide/`）。宿主页职责：
 * 拉取当前项目/环境组下的变量现值，经 `datara:variables` 消息下发给 iframe；
 * dbx 侧就绪后回发 `datara:bridge-ready`，宿主据此补发一次（覆盖 iframe 晚于宿主就绪的时序）。
 *
 * 安全约定：敏感变量的真值绝不出宿主页——`buildVariableEntries` 在构造载荷时即脱敏，
 * 面板与消息共用同一份脱敏结果，避免两处显示口径分叉。
 */

import type { VariableCompletionItem } from './variableApi'

/**
 * 下发目标 origin：iframe 以相对路径 `/ide/` 加载，与宿主页同源，
 * 故直接取当前页 origin，避免硬编码在部署地址变化时失配。
 */
export const DBX_IFRAME_ORIGIN = window.location.origin

/** datara → dbx 变量下发消息类型。 */
export const DATARA_VARIABLES_MESSAGE = 'datara:variables'

/** 下发给 dbx 的变量条目（值已按敏感性处理）。 */
export interface ExternalVariableEntry {
  scope: string
  name: string
  valueType: string
  value: string | null
  sensitive: boolean
  unavailableReason?: string
  description?: string
}

/** 敏感变量掩码：宿主侧与 dbx 侧看到的都只能是掩码。 */
export function maskSensitiveValue(): string {
  return '***'
}

/** 把变量补全项映射为外发条目：敏感值替换为掩码，其余保持现时值原样。 */
export function buildVariableEntries(items: VariableCompletionItem[]): ExternalVariableEntry[] {
  return items.map((item) => ({
    scope: item.scope,
    name: item.name,
    valueType: item.valueType,
    value: item.sensitive ? maskSensitiveValue() : item.currentValue,
    sensitive: item.sensitive === true,
    ...(item.unavailableReason === undefined ? {} : { unavailableReason: item.unavailableReason }),
    ...(item.description === undefined ? {} : { description: item.description }),
  }))
}

/** 向 `#dbx-ide-frame` 下发变量；iframe 未挂载时返回 false（由 bridge-ready 补发兜底）。 */
export function sendVariablesToDbx(entries: ExternalVariableEntry[]): boolean {
  const target = document.querySelector<HTMLIFrameElement>('#dbx-ide-frame')?.contentWindow
  if (!target) return false
  // entries 通常来自 Vue 的 ref，读取时是响应式 Proxy；postMessage 的结构化克隆无法处理
  // Proxy，会抛 DataCloneError 导致 dbx 永远收不到变量。下发前复制成普通对象数组，
  // 展开运算符只复制自有可枚举字段，保持可选字段「缺失」而非 undefined 的语义。
  const plainEntries = entries.map((entry) => ({ ...entry }))
  target.postMessage({ type: DATARA_VARIABLES_MESSAGE, entries: plainEntries }, DBX_IFRAME_ORIGIN)
  return true
}
