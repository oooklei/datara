/**
 * 组件页面设计器 Task 7：每个 palette widget 一个初始化模板
 * （props/style/rect 默认值）+ 页面级模板。
 * kind 清单与 designerModel.ts WIDGET_KINDS 43 项双向一致（测试锁定防漂移）。
 * 模块顶层 bindTemplates 注入，newWidget 即刻可用真实模板。
 */
import { bindTemplates, newWidget, type PageDSL, type Rect } from './designerModel'

export interface WidgetTemplate {
  kind: string
  label: string
  icon: string
  props: Record<string, unknown>
  style: Record<string, string | number>
  rect: Rect
}
export interface WidgetGroup { key: string; label: string; items: WidgetTemplate[] }

const T = (
  kind: string, label: string, icon: string, w: number, h: number,
  props: Record<string, unknown> = {}, style: Record<string, string | number> = {},
): WidgetTemplate => ({ kind, label, icon, rect: { x: 0, y: 0, w, h }, props, style })

export const widgetGroups: WidgetGroup[] = [
  {
    key: 'layout', label: '布局容器', items: [
      T('grid-row', '栅格行', 'table', 264, 64, { columns: 2, gap: 8 }, { border: '1px dashed #d9d9d9' }),
      T('card', '卡片', 'border', 264, 120, { title: '卡片标题' }, { radius: 12, fill: '#ffffff' }),
      T('tabs', '标签页', 'folder', 264, 160, { tabs: ['标签一', '标签二'] }),
      T('collapse', '折叠面板', 'unfold', 264, 96, { panels: [{ title: '面板一' }] }),
      T('divider', '分隔线', 'minus', 264, 1, {}, { color: '#f0f0f0' }),
      T('spacer', '间距', 'arrows-alt-v', 264, 16, { h: 16 }),
    ],
  },
  {
    key: 'basic', label: '基础元素', items: [
      T('text', '文本', 'font-size', 120, 24, { text: '文本内容' }, { fontSize: 13, color: '#1f2329' }),
      T('heading', '标题', 'bold', 200, 32, { text: '标题', level: 3 }, { fontSize: 20, fontWeight: 600 }),
      T('rich-text', '富文本', 'editor', 264, 96, { html: '<p>富文本内容</p>' }),
      T('image', '图片插图', 'picture', 160, 96, { src: '', fit: 'cover' }, { radius: 8 }),
      T('icon', '图标', 'smile', 24, 24, { name: 'smile' }),
      T('button', '按钮', 'action', 88, 32, { text: '按钮', type: 'primary' }, { radius: 8 }),
      T('badge', '徽标', 'tag', 64, 22, { text: 'NEW', color: '#ff4d4f' }),
      T('link', '链接', 'link', 96, 22, { text: '链接', href: '#' }, { color: '#1677ff' }),
    ],
  },
  {
    key: 'form', label: '表单输入', items: [
      T('input', '输入框', 'edit', 200, 32, { label: '名称', placeholder: '请输入名称' }),
      T('number', '数字输入', 'number', 160, 32, { label: '数量', min: 0, max: 9999, placeholder: '0' }),
      T('select', '选择器', 'down', 200, 32, { label: '类型', placeholder: '请选择', options: ['选项一', '选项二'] }),
      T('date', '日期', 'calendar', 180, 32, { label: '日期', placeholder: '请选择日期' }),
      T('date-range', '日期范围', 'calendar', 280, 32, { label: '起止', placeholder: '开始 ~ 结束日期' }),
      T('switch', '开关', 'check', 64, 32, { label: '启用', checked: false }),
      T('slider', '滑块', 'sliders', 200, 32, { label: '进度', min: 0, max: 100, value: 50 }),
      T('radio', '单选', 'check-circle', 220, 32, { label: '单选', options: ['是', '否'], value: '是' }),
      T('checkbox', '复选', 'check-square', 220, 32, { label: '多选', options: ['选项A', '选项B'], value: [] }),
      T('cascader', '级联选择', 'apartment', 220, 32, { label: '地区', placeholder: '请选择' }),
      T('textarea', '文本域', 'align-left', 264, 72, { label: '备注', placeholder: '请输入备注' }),
      T('upload', '上传', 'upload', 200, 32, { label: '附件', maxCount: 1 }),
    ],
  },
  {
    key: 'data', label: '数据展示', items: [
      T('table', '表格', 'table', 264, 160, {
        columns: [
          { title: '名称', dataIndex: 'name' },
          { title: '状态', dataIndex: 'status' },
        ],
        emptyText: '暂无数据',
      }),
      T('list', '列表', 'unordered-list', 264, 160, { emptyText: '暂无数据' }),
      T('descriptions', '描述列表', 'profile', 264, 140, {
        items: [
          { label: '名称', value: '-' },
          { label: '状态', value: '-' },
        ],
      }),
      T('statistic', '统计数值', 'dashboard', 140, 64, { title: '指标', value: '0' }),
      T('progress', '进度条', 'loading', 200, 24, { percent: 0 }),
      T('timeline', '时间线', 'clock-circle', 240, 120, { items: ['事件一', '事件二'] }),
      T('tree', '树', 'apartment', 220, 160, { treeData: [{ title: '节点一', children: [{ title: '子节点' }] }] }),
    ],
  },
  {
    key: 'chart', label: '图表', items: [
      T('chart-bar', '柱状图', 'bar-chart', 264, 160, { seriesType: 'bar', emptyText: '暂无数据' }),
      T('chart-line', '折线图', 'line-chart', 264, 160, { seriesType: 'line', emptyText: '暂无数据' }),
      T('chart-pie', '饼图', 'pie-chart', 200, 160, { seriesType: 'pie', emptyText: '暂无数据' }),
      T('chart-area', '面积图', 'area-chart', 264, 160, { seriesType: 'area', emptyText: '暂无数据' }),
      T('chart-gauge', '仪表盘', 'dashboard', 180, 160, { seriesType: 'gauge', value: 0 }),
      T('chart-scatter', '散点图', 'scatter-chart', 264, 160, { seriesType: 'scatter', emptyText: '暂无数据' }),
    ],
  },
  {
    key: 'binding', label: '绑定元素', items: [
      T('meta-field', '元数据字段', 'database', 180, 24, { path: '', fallback: '元数据字段' }),
      T('var-label', '变量标签', 'tag', 140, 24, { path: '', fallback: '变量' }),
      T('query-result', '查询结果集', 'search', 264, 120, { fallback: '查询结果' }),
      T('sys-status', '系统状态徽标', 'cloud', 140, 24, { fallback: '正常', color: '#52c41a' }),
    ],
  },
]

export function widgetTemplate(kind: string): WidgetTemplate | undefined {
  return widgetGroups.flatMap((g) => g.items).find((t) => t.kind === kind)
}

bindTemplates((kind) => widgetTemplate(kind))   // 模块顶层注入：newWidget 即刻可用真实模板

// ---------- 页面级模板 ----------

function blank(): PageDSL {
  return {
    version: 1, name: '未命名组件', icon: 'block', color: '#1677ff',
    canvas: { width: 288, height: 520, background: { fill: '#ffffff', size: 'cover' } },
    widgets: [],
  }
}

function fromWidgets(kinds: string[]): PageDSL {
  const page = blank()
  let y = 8
  for (const k of kinds) {
    const w = newWidget(k, { x: 12, y })
    page.widgets.push(w)
    y += w.rect.h + 8
  }
  return page
}

export const pageTemplates = [
  { name: '空白页', page: (): PageDSL => blank() },
  { name: '数据看板', page: (): PageDSL => fromWidgets(['heading', 'statistic', 'statistic', 'chart-bar', 'table']) },
  { name: '表单页', page: (): PageDSL => fromWidgets(['heading', 'input', 'select', 'date', 'textarea', 'button']) },
  { name: '列表页', page: (): PageDSL => fromWidgets(['heading', 'table', 'progress']) },
]
