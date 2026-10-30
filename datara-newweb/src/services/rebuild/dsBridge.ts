/**
 * datara ↔ 海豚 iframe postMessage 桥（§10.4 嵌入机制）。
 *
 * 消息词形与 DS 侧 utils/datara-bridge.ts 严格对齐：
 *  - datara:ds-session  宿主 → DS：下发内部令牌/身份/项目编码（DS 据此切内部信任头）
 *  - datara:ds-ready    DS → 宿主：帧已挂载监听（首帧即发）+ 会话已生效（再发一次）
 *
 * 安全约束：双向都校验 origin（必须等于本页 origin，DS 经同源反代嵌入）与
 * message.source（必须是目标 iframe 的 contentWindow），拒绝跨源/跨帧注入。
 */

import type { OrchestrationSession } from './orchestrationApi'

export const DS_SESSION_MESSAGE = 'datara:ds-session'
export const DS_READY_MESSAGE = 'datara:ds-ready'

/** 消息目标源 = 本页 origin（datara 与 DS 同源反代，见 nginx /dolphinscheduler/）。 */
function targetOrigin(): string {
  return window.location.origin
}

/**
 * 下发会话给 DS 帧。
 *
 * 必须把载荷复制成普通对象：Vue 的 reactive/ref Proxy 经结构化克隆会抛
 * DataCloneError（与 dbxVariableBridge 同源教训）。字段白名单直取，
 * 不带入任何响应式包装。
 */
export function sendSessionToDs(frame: HTMLIFrameElement | null, session: OrchestrationSession): boolean {
  const win = frame?.contentWindow
  if (!win) return false
  const payload: OrchestrationSession = {
    token: session.token,
    user: session.user,
    projectCode: session.projectCode,
    projectName: session.projectName,
    projectId: session.projectId,
    apiBaseUrl: session.apiBaseUrl,
    userToken: session.userToken,
    ...(session.environmentGroupId !== undefined ? { environmentGroupId: session.environmentGroupId } : {}),
    ...(session.environmentCode !== undefined ? { environmentCode: session.environmentCode } : {}),
  }
  win.postMessage({ type: DS_SESSION_MESSAGE, payload }, targetOrigin())
  return true
}

/**
 * 监听 DS 帧的 ready 信号，首帧即返回（DS 侧 initDataraBridge 注册后立即发送）。
 * 返回取消函数。
 */
export function listenDsReady(frame: HTMLIFrameElement | null, onReady: () => void): () => void {
  if (!frame) return () => {}
  const handler = (event: MessageEvent): void => {
    if (event.origin !== targetOrigin()) return
    if (event.source !== frame.contentWindow) return
    const data = event.data as { type?: string } | null
    if (!data || data.type !== DS_READY_MESSAGE) return
    onReady()
  }
  window.addEventListener('message', handler)
  return () => window.removeEventListener('message', handler)
}

/**
 * 由项目编码拼 DS embed 路由（DS UI 生产 base = `/dolphinscheduler/ui/`）。
 *
 * `path` 必填且必须是**单个 DAG 画布路由**（§10.4：`src` 指向单个画布并带
 * `?embed=1`；工作流定义列表由 datara 自建页承载，不得把 DS 列表页塞进 iframe）。
 * 占位符 `{code}` 会被替换为 URL 编码后的海豚项目编码。
 */
export function dsEmbedUrl(projectCode: string, path: string): string {
  return `/dolphinscheduler/ui${path.replace('{code}', encodeURIComponent(projectCode))}?embed=1`
}
