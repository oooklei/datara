/**
 * 表单分组（长表单可读性）。
 *
 * 背景：157 个组件的 `schema.form` 此前全是**平铺数组**，`FieldSchema` 没有任何分组基元，
 * 于是 `stream_input`（47 字段 / 7 种来源）、`endpoint_select`（17 字段）等多态组件
 * 在属性面板里退化为一条无层级长列表——用户看不出「先配连接、再配位点、最后配解析」。
 * 本模块提供纯函数切分，渲染方（`FormSections.vue`）统一消费，Inspector 与拖入弹窗共用同一实现。
 *
 * 纯函数、无 IO、无组件依赖，可直接单测。
 */
import type { FieldSchema } from './types'

/** 一个表单分组（同 group 的相邻字段聚合） */
export interface FormSection {
  /** 分组标识（= 声明的 group 值；无分组的平铺段为 ''） */
  key: string
  /** 分组标题（无分组段为空串，由渲染方决定是否出标题） */
  title: string
  /** 分组副标题（取组内首个声明的 groupHint） */
  hint: string
  /** 组内字段（保持声明序） */
  fields: FieldSchema[]
}

/**
 * 把扁平 `schema.form` 按声明的 `group` 切成连续分组段。
 *
 * 口径：
 *  - **相邻同组**才合并：同 `group` 的字段若不相邻（A-B-A 交错）会切为两段，
 *    使每个分组永远对应一段连续视觉区块，渲染方无需处理「标题重复出现」的歧义。
 *  - 无 `group` 的字段自成平铺段（`key=''`），渲染方按无标题处理
 *    → 未声明分组的既有组件呈现**逐字不变**（纯增量，88 个组件零回归）。
 *  - 入参应是**已按 showIf 过滤**的 `visibleForm`：组内字段全部隐藏时该段自然不出现，
 *    多态组件因此只显示当前来源模式对应的分组卡。
 */
export function formSections(form: FieldSchema[]): FormSection[] {
  const out: FormSection[] = []
  for (const f of form) {
    const key = f.group ?? ''
    const last = out[out.length - 1]
    if (last && last.key === key) {
      last.fields.push(f)
      if (!last.hint && f.groupHint) last.hint = f.groupHint
    } else {
      out.push({ key, title: key, hint: f.groupHint ?? '', fields: [f] })
    }
  }
  return out
}

/** 该段是否需要渲染分组标题（平铺段为 false） */
export function hasGroupTitle(s: FormSection): boolean {
  return !!s.key
}

/**
 * 组件是否「有可配置内容」——模板向导据此跳过纯装饰节点（如 C1 开始 / C2 结束：
 * form 为空且六区块无数据，弹窗只能呈现 6 个空区块，逐一索要配置是纯摩擦）。
 *
 * 判定与 configure-first 口径一致：业务表单有任一可见字段，或六区块任一有值/引用。
 * 六区块数据键以 `SixBlocks.vue` 为准：`inputs` / `outputs` / `params` / `condition`
 * / `constraints` / `exclude`（`outputs` 为 `{params,tables}` 对象）。
 */
export function hasConfigurableContent(form: FieldSchema[], nodeData: Record<string, unknown>): boolean {
  if (form.length > 0) return true
  if (Array.isArray(nodeData.inputs) && nodeData.inputs.length > 0) return true
  if (Array.isArray(nodeData.params) && nodeData.params.length > 0) return true
  const out = nodeData.outputs as { params?: unknown[]; tables?: unknown[] } | undefined
  if (out && ((out.params?.length ?? 0) > 0 || (out.tables?.length ?? 0) > 0)) return true
  return ['condition', 'constraints', 'exclude'].some((k) => {
    const v = nodeData[k]
    if (Array.isArray(v)) return v.length > 0
    return v != null && v !== '' && v !== false
  })
}
