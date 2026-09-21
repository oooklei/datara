import type { GraphDocument } from '../model'
import type { ViewProfile } from '../profiles/types'
import { dagreLayout } from './dagre'
import { laneLayout } from './lane'
import { forceLayout } from './force'
import type { ForceLayoutOptions } from './force'
import { erGridLayout } from './er'
import type { ErGridLayoutOptions } from './er'

export { forceLayout } from './force'
export type { ForceLayoutOptions } from './force'
export { erGridLayout } from './er'
export type { ErGridLayoutOptions } from './er'

/** 按 profile 指定的布局算法重排节点坐标（返回新文档） */
export function applyLayout(doc: GraphDocument, profile: ViewProfile): GraphDocument {
  if (profile.layout === 'lane' && profile.lanes) {
    return laneLayout(doc, { lanes: profile.lanes })
  }
  if (profile.layout === 'force') {
    return forceLayout(doc, profile.force as ForceLayoutOptions | undefined)
  }
  if (profile.layout === 'er') {
    return erGridLayout(doc, profile.erGrid as ErGridLayoutOptions | undefined)
  }
  return dagreLayout(doc, { dir: profile.layoutDir ?? 'TB' })
}
