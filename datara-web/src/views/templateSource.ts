import type { GraphDocument } from '../graph/model'

export async function resolveTemplateSourceDoc(
  activeDoc: GraphDocument | null | undefined,
  workflowId: string,
  load: (id: string) => Promise<GraphDocument | null | undefined>,
): Promise<GraphDocument | null | undefined> {
  if (activeDoc?.id === workflowId) return structuredClone(activeDoc)
  return load(workflowId)
}
