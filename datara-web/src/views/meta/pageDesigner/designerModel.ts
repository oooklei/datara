/**
 * 组件页面设计器 Task 6：PageDSL 类型 + 归一化 + 校验。
 * 红线 2 前端镜像，与后端 api/component_design.py _validate_page_spec 同口径：
 * widget kind 白名单 43 项 / 绑定 fallback 必填（placeholder 即默认值）/
 * 画布尺寸钳制 宽 140-520 / 高 320-1200（设计文档 §4，同 DAG 面板约束）。
 */
export interface Rect { x: number; y: number; w: number; h: number }
export interface BackgroundStyle { fill: string; image?: string; size?: string }
export interface BindingRef {
  kind: 'metadata' | 'variable' | 'query' | 'static'
  path?: string; query?: string; datasourceId?: number; fallback: string
}
export interface WidgetNode {
  id: string; kind: string; rect: Rect
  props: Record<string, unknown>
  style: Record<string, string | number>
  bindings: Record<string, BindingRef>
  children?: WidgetNode[]
}
export interface PageDSL {
  version: 1; name: string; icon: string; color: string
  canvas: { width: number; height: number; background: BackgroundStyle }
  widgets: WidgetNode[]
}

export const CANVAS_DEFAULT = { width: 288, height: 520 }   // GraphWorkbench Inspector 规格
export const CANVAS_W = { min: 140, max: 520 }
export const CANVAS_H = { min: 320, max: 1200 }

let seq = 0
export function genId(_kind: string): string {
  seq = (seq + 1) % 1e6
  return `w_${Date.now().toString(36)}${seq.toString(36)}`
}

export function normalizePage(raw: unknown): PageDSL {
  const p = (raw as { page?: Record<string, unknown> })?.page ?? (raw as Record<string, unknown>) ?? {}
  const canvas = (p.canvas ?? {}) as Record<string, unknown>
  const bg = (canvas.background ?? {}) as BackgroundStyle
  return {
    version: 1,
    name: (p.name as string) ?? '未命名组件',
    icon: (p.icon as string) ?? 'block',
    color: (p.color as string) ?? '#1677ff',
    canvas: {
      // 钳制式回退：缺省/非法值回退默认规格，旧草稿越界值钳入新口径，保证加载后合法
      width: Math.min(CANVAS_W.max, Math.max(CANVAS_W.min, Number(canvas.width) || CANVAS_DEFAULT.width)),
      height: Math.min(CANVAS_H.max, Math.max(CANVAS_H.min, Number(canvas.height) || CANVAS_DEFAULT.height)),
      background: { fill: bg.fill ?? '#ffffff', image: bg.image, size: bg.size ?? 'cover' },
    },
    widgets: ((p.widgets as Record<string, unknown>[]) ?? []).map((w) => ({
      id: (w.id as string) || genId(String(w.kind ?? 'w')),
      kind: String(w.kind ?? 'text'),
      rect: (w.rect ?? { x: 0, y: 0, w: 120, h: 32 }) as Rect,
      props: (w.props ?? {}) as Record<string, unknown>,
      style: (w.style ?? {}) as Record<string, string | number>,
      bindings: (w.bindings ?? {}) as Record<string, BindingRef>,
      ...(Array.isArray(w.children) ? { children: (w.children as WidgetNode[]).map((c) => normalizeWidget(c)) } : {}),
    })),
  }
}
function normalizeWidget(w: WidgetNode | Record<string, unknown>): WidgetNode {
  return normalizePage({ page: { version: 1, widgets: [w] } }).widgets[0]
}

export const WIDGET_KINDS = new Set<string>([
  'grid-row', 'card', 'tabs', 'collapse', 'divider', 'spacer',
  'text', 'heading', 'rich-text', 'image', 'icon', 'button', 'badge', 'link',
  'input', 'number', 'select', 'date', 'date-range', 'switch', 'slider', 'radio', 'checkbox', 'cascader', 'textarea', 'upload',
  'table', 'list', 'descriptions', 'statistic', 'progress', 'timeline', 'tree',
  'chart-bar', 'chart-line', 'chart-pie', 'chart-area', 'chart-gauge', 'chart-scatter',
  'meta-field', 'var-label', 'query-result', 'sys-status',
])
export type WidgetKind = string

export function validatePage(p: PageDSL): string[] {
  const vs: string[] = []
  if (p.canvas.width < CANVAS_W.min || p.canvas.width > CANVAS_W.max) vs.push('canvas: 宽越界')
  if (p.canvas.height < CANVAS_H.min || p.canvas.height > CANVAS_H.max) vs.push('canvas: 高越界')
  const kinds = WIDGET_KINDS
  const walk = (ws: WidgetNode[]) => {
    ws.forEach((w) => {
      if (!kinds.has(w.kind)) vs.push(`widget.kind: 未知 ${w.kind}`)
      if (w.rect.w <= 0 || w.rect.h <= 0) vs.push(`widget.rect: 尺寸非法 ${w.id}`)
      Object.entries(w.bindings).forEach(([k, b]) => {
        if (!b?.fallback) vs.push(`bindings.${k}.fallback: 缺失（placeholder 即默认值）`)
        // 数据集绑定形状镜像后端：kind=query 允许 数据源引用（datasourceId）或显式 SQL（query）二者有其一
        if (b?.kind === 'query' && !b.query && b.datasourceId == null) vs.push(`bindings.${k}.query: 需 datasourceId 或 query 其一`)
      })
      walk(w.children ?? [])
    })
  }
  walk(p.widgets)
  return vs
}

/** 工厂：由模板创建 widget（templates.ts 注册，避免循环依赖用注入）。 */
export type TemplateOf = (kind: string) => { props: Record<string, unknown>; style: Record<string, string | number>; rect: Rect; bindings?: Record<string, BindingRef> } | undefined
let _templateOf: TemplateOf | undefined
export function bindTemplates(fn: TemplateOf): void { _templateOf = fn }
export function newWidget(kind: string, at: { x: number; y: number }): WidgetNode {
  const t = _templateOf?.(kind)
  return {
    id: genId(kind), kind,
    rect: t?.rect ? { ...t.rect, x: at.x, y: at.y } : { ...at, w: 120, h: 32 },
    props: { ...(t?.props ?? {}) },
    style: { ...(t?.style ?? {}) },
    bindings: {},
  }
}
