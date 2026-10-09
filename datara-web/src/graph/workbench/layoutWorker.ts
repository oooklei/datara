import { dagreLayout } from '../layout/dagre'
import type { GraphDocument } from '../model'

interface LayoutRequest {
  id: number
  doc: GraphDocument
  dir: 'TB' | 'LR'
}

interface LayoutResponse {
  id: number
  doc?: GraphDocument
  error?: string
}

self.onmessage = (event: MessageEvent<LayoutRequest>) => {
  const { id, doc, dir } = event.data
  try {
    const result: LayoutResponse = { id, doc: dagreLayout(doc, { dir }) }
    self.postMessage(result)
  } catch (error) {
    self.postMessage({ id, error: error instanceof Error ? error.message : String(error) } satisfies LayoutResponse)
  }
}

export {}
