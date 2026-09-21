import type { ViewProfile } from './types'
import { dagProfile } from './dag'
import { topoProfile } from './topo'
import { etlProfile } from './etl'
import { streamProfile } from './stream'
import { erProfile } from './er'
import { lineageProfile } from './lineage'
import { relationProfile } from './relation'

/** Profile 注册表：A 类图主视角 7 用例全部就绪 */
const registry: Record<string, ViewProfile> = {
  dag: dagProfile,
  topo: topoProfile,
  etl: etlProfile,
  stream: streamProfile,
  er: erProfile,
  lineage: lineageProfile,
  relation: relationProfile,
}

export function getProfile(id: string): ViewProfile {
  const p = registry[id]
  if (!p) throw new Error(`未注册的视角 Profile: ${id}`)
  return p
}

export {
  dagProfile, topoProfile,
  etlProfile, streamProfile, erProfile, lineageProfile, relationProfile,
}
export type { ViewProfile, NodeSchema, EdgeSchema, PaletteCategory, LaneDef, FieldSchema } from './types'
