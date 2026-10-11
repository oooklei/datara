import type { GraphDocument } from '../graph/model'
import { cloneDoc } from '../graph/model'

export async function resolveTemplateSourceDoc(
  activeDoc: GraphDocument | null | undefined,
  workflowId: string,
  load: (id: string) => Promise<GraphDocument | null | undefined>,
): Promise<GraphDocument | null | undefined> {
  // Pinia/Vue exposes the active document as a reactive proxy. structuredClone
  // rejects proxies with DataCloneError; cloneDoc intentionally crosses the
  // persistence boundary through JSON because GraphDocument is JSON data.
  if (activeDoc?.id === workflowId) return cloneDoc(activeDoc)
  return load(workflowId)
}
