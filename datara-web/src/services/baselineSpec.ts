export interface BaselineField {
  key: string
  label: string
  uiType: string
  [key: string]: unknown
}

export interface BaselineSpec {
  form: {
    inputs: BaselineField[]
    outputs: BaselineField[]
    params: BaselineField[]
    conditions: unknown[]
    constraints: unknown[]
    exclusions: unknown[]
    refs: unknown[]
    exports: unknown[]
  }
  lineage: { assets: unknown[] }
  meta?: Record<string, any>
  [key: string]: unknown
}

export interface DiffSummary {
  oldCount: number
  newCount: number
  migrated: string[]
  pending: string[]
}

const EMPTY_FORM = {
  inputs: [] as BaselineField[],
  outputs: [] as BaselineField[],
  params: [] as BaselineField[],
  conditions: [] as unknown[],
  constraints: [] as unknown[],
  exclusions: [] as unknown[],
  refs: [] as unknown[],
  exports: [] as unknown[],
}

function fields(v: unknown): BaselineField[] {
  return Array.isArray(v)
    ? v.map((x: any) => ({
      key: String(x?.key ?? ''),
      label: String(x?.label ?? x?.key ?? ''),
      uiType: String(x?.uiType ?? x?.type ?? 'text'),
      ...x,
    }))
    : []
}

export function normalizeBaselineSpec(raw: any): BaselineSpec {
  const r = raw && typeof raw === 'object' ? raw : {}
  const form = r.form && typeof r.form === 'object' ? r.form : {}
  return {
    ...r,
    form: {
      ...EMPTY_FORM,
      ...form,
      inputs: fields(form.inputs),
      outputs: fields(form.outputs),
      params: fields(form.params),
      conditions: Array.isArray(form.conditions) ? form.conditions : [],
      constraints: Array.isArray(form.constraints) ? form.constraints : [],
      exclusions: Array.isArray(form.exclusions) ? form.exclusions : [],
      refs: Array.isArray(form.refs) ? form.refs : [],
      exports: Array.isArray(form.exports) ? form.exports : [],
    },
    lineage: {
      assets: Array.isArray(r.lineage?.assets) ? r.lineage.assets : [],
    },
    meta: r.meta && typeof r.meta === 'object' ? r.meta : {},
  }
}

export function diffSummary(oldFields: unknown[], spec: BaselineSpec): DiffSummary {
  const oldKeys = oldFields
    .map((x: any) => String(x?.key ?? x?.name ?? ''))
    .filter(Boolean)
  const nextKeys = [
    ...spec.form.inputs,
    ...spec.form.outputs,
    ...spec.form.params,
  ].map((x) => x.key).filter(Boolean)
  const next = new Set(nextKeys)
  return {
    oldCount: oldKeys.length,
    newCount: nextKeys.length,
    migrated: oldKeys.filter((k) => next.has(k)),
    pending: oldKeys.filter((k) => !next.has(k)),
  }
}
