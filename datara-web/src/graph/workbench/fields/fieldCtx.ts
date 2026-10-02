import type { ComputedRef, Ref } from 'vue'
import type { GNode } from '../../model'
import type { NodeSchema } from '../../profiles/types'
import type { DataContext } from '../../profiles/formLinkage'

export interface FieldCtx {
  upstream: ComputedRef<GNode[]>
  upSchema: (node: GNode) => NodeSchema
  upstreamOpts: ComputedRef<Array<{ label: string; value: string }>>
  upstreamOuts: ComputedRef<Array<{ label: string; value: string }>>
  epProbe: ComputedRef<unknown>
  dsRows: Ref<unknown[]>
  scripts: Ref<unknown[]>
  runtimeNodes: Ref<unknown[]>
  tagOptions: ComputedRef<Array<{ label: string; value: string }>>
  varOptions: Ref<unknown[]>
  dataCtx: ComputedRef<DataContext>
  pickTrees: Ref<Record<string, unknown>>
  pickTreeErr: Ref<Record<string, unknown>>
  pickTreeBusy: Ref<Record<string, unknown>>
  topicOpts: Ref<Record<string, unknown>>
  topicErr: Ref<Record<string, unknown>>
  topicBusy: Ref<Record<string, unknown>>
  dirNavs: Ref<Record<string, unknown>>
  ensureTree: (...args: any[]) => Promise<unknown>
  ensureTopics: (...args: any[]) => Promise<void>
  lsDir: (...args: any[]) => void
  loadScriptCode: (...args: any[]) => void
  saveToScript: (...args: any[]) => void
  saveAsNewScript: (...args: any[]) => Promise<void>
  markDirty: (...args: any[]) => void
  schema: ComputedRef<unknown>
}
