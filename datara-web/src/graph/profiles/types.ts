/**
 * ViewProfile 契约：菜单即视角。
 * 每个菜单用例 = 一个 Profile（节点类型/边语义/元件库/布局/校验器/表单 schema 组合）。
 */
import type { Component } from 'vue'
import type { GEdge, GEdgeKind, GNode, GraphDocument, Validator } from '../model'

/** Inspector 属性表单字段 schema */
export interface FieldSchema {
  key: string
  label: string
  type: 'text' | 'number' | 'select' | 'textarea' | 'script' | 'branches'
    /* F60 六区块扩展类型（§8.1） */
    | 'params-table'  // 键/值/来源（全局变量|工作流变量|环境组|字面量|时间变量）行编辑表
    | 'kv-table'      // 键/值/说明 通用行编辑表
    | 'expr'          // 表达式输入 + 变量引用弹窗（下拉常用变量 + 插入 ${var}）
    | 'var-ref'       // 变量引用选择器（下拉已注册变量）
    | 'bool'          // 开关
    | 'runtime-node'  // 运行时节点选择器（C14 SSH 远程执行；real 模式拉取 listRuntimeNodes）
    /* I4 扩展类型（§9）：表单控件联动 */
    | 'args-table'    // 过程参数行编辑表（键/方向 IN|OUT/值，C15）
    | 'datasource'    // 数据源中心下拉（real 拉 listDataSources；dsTypes 过滤类型）
    | 'hint'          // 纯提示文案（text(data) 动态产出或 placeholder 静态）
    /* I7 扩展类型（设计 §3.1/§3.2） */
    | 'var-table'     // C21 变量表行编辑（名/值/类型[字面量|表达式|时间变量]/覆盖开关）
    | 'deps-list'     // C9 依赖项列表编辑器（工作流+节点级联+可选变量条件）
    | 'exec-node-tag' // C14 执行节点标签下拉（F53：选项=ssh-nodes 标签并集）
    | 'probe'         // C17 反选探测：按钮调 GET /datasources/{id}/tree 探测源库与目标表同名/前缀匹配的表，勾选回填 schemas
    /* I12 T10 动态控件扩展（「选择代替填空」：元数据/路径选择，依赖字段联动复用 showIf/onChange 既有机制） */
    | 'table-picker'  // 表级联选择：依赖 datasource 字段（pick.dsKey），数据源→库→表两级级联
    | 'field-select'  // 字段多选：依赖 datasource+table 字段（pick.dsKey/pick.tableKey），列枚举写回数组
    | 'topic-select'  // Kafka topic 下拉：依赖流源引用字段（pick.dsKey 缺省 dsRef），经 ds_id 枚举 topic
    | 'dir-select'    // 目录浏览：依赖 runtimeNode 字段（pick.nodeKey），懒加载子目录写回完整路径
    | 'token-insert'  // I12 T12 库/表侧栏选择器（C11）：点选表把 SELECT 骨架插入 pick.insertKey 目标字段，不替代手写
    | 'upstream-ref'  // I12 T11 C25 上游节点引用：选项=画布直接上游节点（label+类型），选中写回节点 id
  options?: { value: string; label: string }[]
  /** probe 探测配置：dsKey=源数据源字段（缺省 readerDs），tableKey=目标表字段（缺省 writerTable），excludeDsKey=排除其默认库的数据源（缺省 writerDs，防目标表自写） */
  probe?: { dsKey?: string; tableKey?: string; excludeDsKey?: string }
  /** I12 T10 动态控件依赖声明（依赖字段为空时控件禁用+行内提示；失败态=候选置空+行内错误，不阻塞表单其余字段） */
  pick?: {
    /** 依赖的数据源字段名（table-picker/field-select 缺省 'datasource'；topic-select 缺省 'dsRef'；取值为数据源名） */
    dsKey?: string
    /** field-select 依赖的表字段名（缺省 'table'；值可为纯表名或 {schema, table}） */
    tableKey?: string
    /** dir-select 依赖的运行时节点字段名（缺省 'runtimeNode'，取值为节点名） */
    nodeKey?: string
    /** table-picker 写回形态：'table'=纯表名（缺省）；'schemaTable'=写回 {schema, table} 对象 */
    writeAs?: 'table' | 'schemaTable'
    /** field-select 候选来源：'dsTable'=本节点数据源+表字段（缺省，C25 ruleColumns）；'upstream'=直接上游流输入节点（C19 join 键：取上游 cdcDs+tablesText 首表列枚举，无 CDC 上游降级为可直接输入） */
    src?: 'dsTable' | 'upstream'
    /** src='upstream' 时取第 N 个直接上游（按画布位置左→右排序：0=左流/1=右流，缺省 0；位置缺失回退连线序） */
    upstreamIndex?: number
    /** field-select 多选开关：true=写回字符串数组（缺省）；false=单选写回字符串（C19 joinKeyLeft/Right 对齐 worker ops.py 单键契约） */
    multiple?: boolean
    /** token-insert 点选插入目标字段（缺省 'sql'） */
    insertKey?: string
  }
  placeholder?: string
  /** 必填（在 showIf 通过的分型下值为空即「未配置」；requiredMissing 统一判定，画布角标/校验面板/保存闸门共用） */
  required?: boolean
  /** datasource 类型过滤（如 ['mysql','greatdb'] / ['file']；mock 种子无类型码时不过滤） */
  dsTypes?: string[]
  /** 条件展示（表单联动，如 C22 来源模式/保留策略分支；缺省恒显示） */
  showIf?: (data: Record<string, unknown>) => boolean
  /** 值变更联动（select 场景，如 C22 来源模式切换清空对方参数） */
  onChange?: (data: Record<string, unknown>, value: unknown) => void
  /** hint 动态文案（如 ${tmp.*} 可用性提示；缺省用 placeholder） */
  text?: (data: Record<string, unknown>) => string
}

/** I7 C21 变量组件行（设计 §0①）：type=字面量|表达式(运行时求值)|时间变量(F49 模板)；override=覆盖开关 */
export interface VarDef {
  name: string
  value: string
  type: 'literal' | 'expr' | 'time'
  /** 开=覆盖定义级同名工作流变量；关=仅当未定义时生效 */
  override: boolean
}

/** I7 C9 依赖项行（设计 §0②）：wf=定义 id，node=节点 id；cond=可选变量条件（如 wf.period=${wf.period}） */
export interface DependentDef {
  wf: string
  node: string
  cond: string
  /** 展示名冗余存储（摘要/后端日志可读，解析以 id 为准） */
  wfName?: string
  nodeName?: string
}

/** 动态分支（条件分支/多路分支等）：每分支一个独立输出端点 */
export interface BranchDef {
  /** 端点稳定 id（重命名不失效，删分支时按此清理边） */
  id: string
  /** 分支名（连线文本标注来源） */
  name: string
  /** 条件表达式 / 匹配值 */
  expr: string
}

/** 动态源端点（按节点 data 派生） */
export interface NodePort {
  /** 对应 vue-flow Handle id（= BranchDef.id） */
  id: string
  label: string
}

/** Inspector「关联信息」条目（schema.related 产出） */
export interface RelatedItem {
  text: string
  /** 圆点颜色（如绑定结果染色） */
  color?: string
}

/** F61 页面化展示声明（§9）：节点可打开独立页面/浮窗展示运行态信息 */
export interface PageDef {
  title: string
  /** 页面组件（Pinia 外注入 props {node, doc}；注册时以 markRaw 包装由浮窗框架处理） */
  comp: Component
  w?: number
  h?: number
  /** 出现的模式，缺省 both */
  mode?: 'edit' | 'view'
}

/** F63 模板模式：设计时物化展开（§10.1），返回要插入的普通节点+边（引擎零改动） */
export interface TemplateModeDef {
  key: string
  label: string
  desc?: string
  build: (ctx: { doc: GraphDocument; pos: { x: number; y: number } }) => { nodes: GNode[]; edges: GEdge[] }
}

/** F63 聚合模板声明：拖入 → 模式选择 → build 物化插入（聚合占位节点不保留） */
export interface TemplateDef {
  modes: TemplateModeDef[]
}

/** I12 R1 组件分类（可多类归属）：T7 CAT_LABEL / T11 新组件复用此别名，获得键穷尽编译检查 */
export type ComponentCategory = 'sync' | 'etl' | 'stream' | 'general'

/** 节点类型定义：图元 + 元件库条目 + 属性表单 */
export interface NodeSchema {
  type: string
  label: string
  /** 字符图标（palette 与节点共用） */
  icon: string
  color: string
  desc?: string
  /** 组件编号（02 文档 C1~C26），palette 与 Inspector 显示编号徽标 */
  code?: string
  /** I12 R1：组件分类归属（可多类）；palette 基本盘全域可用，仅决定优先展示与徽标 */
  categories?: ComponentCategory[]
  /** 落地阶段提示（灰置组件 tooltip，如「I3/I4 注册」） */
  phase?: string
  /** F61 页面化展示声明 */
  page?: PageDef
  /** F63 聚合模板声明 */
  template?: TemplateDef
  /** 新建节点 data 默认值 */
  defaults?: Record<string, unknown>
  /** 属性表单 schema（节点名称固定渲染，不入 schema） */
  form: FieldSchema[]
  /** 节点副标题（摘要渲染） */
  summary?: (data: Record<string, unknown>) => string
  /** 节点渲染形态：card=任务框（默认）；device=设备图标卡片（拓扑视角专用） */
  shape?: 'card' | 'device'
  /** 动态源端点（条件分支等）：非空时节点按分支渲染多个输出端点 */
  ports?: (data: Record<string, unknown>) => NodePort[]
  /** Inspector 关联信息（表→已绑规则 / 规则→绑定表等视角语义） */
  related?: (node: GNode, doc: GraphDocument) => RelatedItem[]
}

/** Profile 预置浮窗按钮（工具栏按 mode 过滤渲染） */
export interface FloatDef {
  id: string
  label: string
  comp: Component
  w: number
  h: number
  /** 出现的模式，缺省 both */
  mode?: 'edit' | 'view'
  /** 动态 props（如 ETL 字段映射浮窗需要当前选中算子 id） */
  propsOf?: (ctx: { selectedId: string | null }) => Record<string, unknown>
}

/** 边语义：颜色/线型/箭头 */
export interface EdgeSchema {
  kind: string
  label: string
  color: string
  dashed?: boolean
  animated?: boolean
  /** 边路径类型（ER 关系常用 smoothstep） */
  edgeType?: 'default' | 'smoothstep' | 'step' | 'straight'
}

/** palette 条目：type + 可选灰置（I1 后续增量组件占位，tooltip=落地阶段） */
export interface PaletteItem {
  type: string
  /** true = 灰置禁用（不可拖拽），tooltip 显示 phase */
  disabled?: boolean
  /** 落地阶段提示（如「I3/I4 注册」） */
  phase?: string
}

export interface PaletteCategory {
  name: string
  /** 既有写法：全部可用（兼容 etl/stream 等 profile） */
  types?: string[]
  /** 扩展写法：支持灰置条目 */
  items?: PaletteItem[]
}

export interface LaneDef {
  key: string
  name: string
  color?: string
}

export type LayoutKind = 'dagre' | 'lane' | 'force' | 'er'

export interface ViewProfile {
  id: string
  name: string
  mode: 'edit' | 'view'
  nodeTypes: Record<string, NodeSchema>
  edgeKinds: Record<string, EdgeSchema>
  defaultEdge: GEdgeKind
  /** view 模式可为空数组 */
  palette: PaletteCategory[]
  layout: LayoutKind
  layoutDir?: 'TB' | 'LR'
  /** 泳道定义（layout=lane 时必填） */
  lanes?: LaneDef[]
  /** 力导向布局参数（layout=force 时可选） */
  force?: import('../layout/force').ForceLayoutOptions
  /** ER 分层列布局参数（layout=er 时可选） */
  erGrid?: import('../layout/er').ErGridLayoutOptions
  /** 自定义节点渲染组件（缺省 DataNode；ER 实体等用） */
  nodeComp?: Component
  validators: Validator[]
  /** view 模式周期回调（如拓扑健康刷新），返回可选事件负载 */
  onTick?: (doc: import('../model').GraphDocument) => void
  /** 周期刷新勾选框文案（缺省为拓扑健康语义） */
  tickLabel?: string
  /** 预置浮窗（工具栏按 mode 过滤） */
  floats?: FloatDef[]
  /** 质检类视角：异步运行检查（提交即返回，边结果异步翻转），返回总结文案 */
  onRunCheck?: (doc: GraphDocument) => Promise<string | void>
  /** 边点击（如 QC fail 边 → 异常单联动浮窗） */
  onEdgeClick?: (edge: GEdge, doc: GraphDocument) => void
}
