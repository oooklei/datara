import type { DataType } from '../model/portTypes'
import type { ComponentSpec } from '../../services/componentSpec'

export const EDGE_DATA_TYPE_VISUALS: Record<'table' | 'dataset' | 'stream' | 'file' | 'any', { label: string; color: string }> = {
  table: { label: 'Table', color: '#2563eb' },
  dataset: { label: 'Dataset', color: '#0891b2' },
  stream: { label: 'Stream', color: '#7c3aed' },
  file: { label: 'File', color: '#ea580c' },
  any: { label: 'Any', color: '#64748b' },
}

export type EdgeDataType = keyof typeof EDGE_DATA_TYPE_VISUALS

export function resolveEdgeDataType(sourceHandle: string | undefined, spec?: Pick<ComponentSpec, 'outputs' | 'ports'>): EdgeDataType {
  const declared = sourceHandle
    ? spec?.outputs?.find((output) => output.name === sourceHandle)
      ?? spec?.ports.outputs.find((output) => output.name === sourceHandle)
    : spec?.outputs?.[0] ?? spec?.ports.outputs[0]
  const type = declared?.type as DataType | undefined
  return type && type in EDGE_DATA_TYPE_VISUALS ? type as EdgeDataType : 'any'
}

export function edgeDataClass(type: EdgeDataType): string {
  return `edge-data edge-data-${type}`
}

export function capPreviewRows<T>(rows: T[], requestedLimit?: number): T[] {
  const limit = Number.isFinite(requestedLimit) && Number(requestedLimit) > 0
    ? Math.min(Math.floor(Number(requestedLimit)), 100)
    : 100
  return rows.slice(0, limit)
}

