/**
 * ViewProfile 契约：菜单即视角。
 * 每个菜单用例 = 一个 Profile（节点类型/边语义/元件库/布局/校验器/表单 schema 组合）。
 */
import type { Component } from 'vue'
import type { GEdge, GEdgeKind, GNode, GraphDocument, Validator } from '../model'

/** Inspector 属性表单字段类型（B3 收敛：9 基元闭合联合，差异经独立参数字段声明，不再膨胀 type 枚举） */
export type FieldKind =
  | 'text'      // 单行 input / 多行 textarea（multiline）/ 脚本库互通控件（language 存在）
  | 'number'    // 数值输入（change 时字符串转数值存储）
  | 'bool'      // 开关
  | 'select'    // 下拉（options 静态候选；selectFrom 声明动态候选源）
  | 'expr'      // 表达式输入 + 变量引用弹窗（readonly=true 时为变量引用选择器，原 var-ref）
  | 'hint'      // 纯提示文案（text(data) 动态产出或 placeholder 静态）
  | 'rows'      // 行编辑表（rowsKind 区分形态）
  | 'resource'  // 资源选择器（cap.mode 区分：数据源/库表/字段/topic/目录/运行时节点/上游引用）
  | 'mapEditor' // 映射/插入/探测编辑器（mapMode 区分：columnMap/columnInsert/schemaProbe）

/** resource/mapEditor 差异参数（B3 归并原 pick 17 键 + probe 探测配置 + dsTypes 顶层声明） */
export interface ResourcePick {
  /** 选择器目标形态（'columnMap'/'columnInsert'/'schemaProbe' 属 mapEditor，其余属 resource） */
  mode:
    | 'datasource'      // 数据源中心下拉（real 拉 listDataSources；dsTypes 过滤类型）
    | 'table'           // 表级联选择：数据源→库→表两级级联（写回纯表名或 {schema, table}）
    | 'column'          // 字段多选/单选：列枚举写回（本节点表或直接上游流输入，C19 join 键）
    | 'topic'           // Kafka topic 下拉：经 ds_id 枚举 topic
    | 'dir'             // 目录浏览：懒加载子目录写回完整路径
    | 'runtimeNode'     // 运行时节点选择器（C14 SSH 远程执行；取值=节点名）
    | 'upstreamNodes'   // 上游节点引用（C25：选项=画布直接上游节点，选中写回节点 id）
    | 'upstreamOutputs' // 上游节点输出多选（field_map/condition_set 的 inputs/outputs 引用）
    | 'schemaProbe'     // C17 反选探测：探测源库与目标表同名/前缀匹配的表，勾选回填 schemas
    | 'columnInsert'    // I12 T12 库/表侧栏选择器（C11）：点选表把 SELECT 骨架插入目标字段，不替代手写
    | 'columnMap'       // 字段映射编辑器：源字段→目标字段（左右两列下拉），支持转换表达式
  /** 依赖的数据源字段名（table/column 缺省 'datasource'；topic 缺省 'dsRef'；取值为数据源名） */
  dsKey?: string
  /** column 依赖的表字段名（缺省 'table'；值可为纯表名或 {schema, table}） */
  tableKey?: string
  /** dir 依赖的运行时节点字段名（缺省 'runtimeNode'，取值为节点名） */
  nodeKey?: string
  /** datasource 类型过滤（如 ['mysql','greatdb'] / ['file']；mock 种子无类型码时不过滤） */
  dsTypes?: string[]
  /** column 候选来源：'dsTable'=本节点数据源+表字段（缺省，C25 ruleColumns）；'upstream'=直接上游流输入节点（C19 join 键：取上游 cdcDs+tablesText 首表列枚举，无 CDC 上游降级为可直接输入） */
  src?: 'dsTable' | 'upstream'
  /** src='upstream' 时取第 N 个直接上游（按画布位置左→右排序：0=左流/1=右流，缺省 0；位置缺失回退连线序） */
  upstreamIndex?: number
  /** column 多选开关：true=写回字符串数组（缺省）；false=单选写回字符串（C19 joinKeyLeft/Right 对齐 worker ops.py 单键契约） */
  multi?: boolean
  /** table 写回形态：'table'=纯表名（缺省）；'schemaTable'=写回 {schema, table} 对象 */
  writeAs?: 'table' | 'schemaTable'
  /** columnInsert 点选插入目标字段（缺省 'sql'） */
  insertKey?: string
  /** schemaProbe 排除其默认库的数据源字段（防目标表自写自读；缺省 writerDs） */
  excludeDsKey?: string
  /** columnMap 源节点类型（从文档中查找此类型节点，读取其 ds/table 字段获取源列枚举；缺省 endpoint_select） */
  srcNodeType?: string
  /** columnMap 目标节点类型（从文档中查找此类型节点，读取其 ds/table 字段获取目标列枚举；缺省 endpoint_select） */
  tgtNodeType?: string
  /** columnMap 源数据源字段名（从查找到的源节点读取此字段，缺省 'ds'） */
  srcDsKey?: string
  /** columnMap 源表字段名（从查找到的源节点读取此字段，缺省 'table'） */
  srcTableKey?: string
  /** columnMap 目标数据源字段名（从查找到的目标节点读取此字段，缺省 'ds'） */
  tgtDsKey?: string
  /** columnMap 目标表字段名（从查找到的目标节点读取此字段，缺省 'table'） */
  tgtTableKey?: string
  /** upstreamOutputs 最大可选数量（缺省 1） */
  upstreamMax?: number
  /** columnMap 源字段取 inputs 的索引（缺省 0） */
  fmSrcIndex?: number
  /** columnMap 目标字段取 inputs 的索引（缺省 1） */
  fmTgtIndex?: number
}

/** F3 数据驱动值域声明（dataScope 四域）：候选来自 DataContext 对应集合，域空禁用并说明原因 */
export type DataScope = 'upstream-columns' | 'upstream-tables' | 'workflow-vars' | 'time-params'

/** Inspector 属性表单字段 schema */
export interface FieldSchema {
  key: string
  label: string
  type: FieldKind
  /* —— text 差异 —— */
  /** 多行 textarea（缺省单行 input；原 textarea） */
  multiline?: boolean
  /** textarea 行数（缺省 4） */
  rows?: number
  /** 脚本库互通语言标记：存在 ⇒ 渲染脚本库 select + 载入/回存/另存控件（'txt'=内联脚本内容，原 script） */
  language?: 'sql' | 'py' | 'sh' | 'txt'
  /* —— select 差异 —— */
  /** 动态候选来源（'exec-node-tags'=ssh-nodes 标签并集，C14 F53） */
  selectFrom?: 'exec-node-tags'
  /* —— expr 差异 —— */
  /** true=变量引用选择器（下拉已注册变量写回 ${var}，无手输与弹窗；原 var-ref） */
  readonly?: boolean
  /* —— 数据驱动值域（F3，UI 裁定 2：值域由上下文决定） —— */
  /** 声明后候选值域只来自 DataContext 对应域（select/expr readonly 消费）；域空 → 字段禁用并说明原因。
   *  声明式纯数据（红线 2），与 B3 收敛协同——取代散落 pick 动态候选变体 */
  dataScope?: DataScope
  /* —— rows 差异 —— */
  /** 行编辑表形态：params=键/值/来源五选一（F60）｜kv=键/值/说明（F60）｜args=键/方向/值（I4 C15）｜var=变量表（I7 C21）｜deps=依赖项列表（I7 C9）｜branches=动态分支端点（F60） */
  rowsKind?: 'params' | 'kv' | 'args' | 'var' | 'deps' | 'branches'
  /* —— mapEditor 差异 —— */
  /** 编辑器形态：'map'=字段映射（原 field-map）｜'insert'=库表点选插入（原 token-insert）｜'probe'=反选探测（原 probe） */
  mapMode?: 'map' | 'insert' | 'probe'
  /* —— 表单分组（长表单可读性；多态组件按来源模式分卡）—— */
  /** 分组标题（如「数据源连接」「消费位点」「解析规则」）。相邻同组字段归入同一分组渲染；
   *  缺省=不分组（平铺，与既有组件行为一致，纯增量）。分组随 showIf 自动隐现：
   *  组内字段全部隐藏时整个分组不渲染，故多态组件只显示当前模式对应的卡。 */
  group?: string
  /** 分组副标题（渲染于分组标题下，一句话说明该组要解决什么） */
  groupHint?: string
  /* —— resource/mapEditor 差异参数 —— */
  cap?: ResourcePick
  options?: { value: string; label: string }[]
  placeholder?: string
  /** 必填（在 showIf 通过的分型下值为空即「未配置」；requiredMissing 统一判定，画布角标/校验面板/保存闸门共用） */
  required?: boolean
  /** 条件展示（表单联动，如 C22 来源模式/保留策略分支；缺省恒显示） */
  showIf?: (data: Record<string, unknown>) => boolean
  /** 值变更联动（select/bool 场景，如 C22 来源模式切换清空对方参数） */
  onChange?: (data: Record<string, unknown>, value: unknown) => void
  /** hint 动态文案（如 ${tmp.*} 可用性提示；缺省用 placeholder）：字符串或函数 */
  text?: string | ((data: Record<string, unknown>) => string)
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

/** §11 组件初始化模板（页面设计器 Task 14）：拖入设计器的单节点默认形态。
 *  PageDSL 风格**纯数据**片段（禁函数/表达式字符串，后端 FORBIDDEN_SNIPPETS 红线同口径），
 *  经 scripts/export_dag_catalog.py 导入 common/dag_catalog.json 只读下发。
 *  与 F63 template（聚合展开模板，含 build 函数、落图即展开为节点链）正交：
 *  本字段描述单节点落图默认值，template 描述多节点链展开。 */
export interface ComponentInitTemplate {
  /** 节点默认尺寸（设计器画布坐标） */
  rect: { w: number; h: number }
  /** 默认 props（节点 data 同名键：取 defaults 值或 label 语义的安全中文示例） */
  props: Record<string, unknown>
  /** 推荐绑定（主数据槽 → 绑定声明：kind=query/static/variable + fallback 空态文案） */
  bindings?: Record<string, unknown>
  /** 空态示例数据（可选） */
  sample?: unknown
}

/** F1 configure-first 拖入策略（治理设计 §11，纯数据——禁函数/表达式字符串） */
export interface DropPolicy {
  /** drop 时一次性快照预填的字段 key 列表（§11 划界语义：取逻辑上游节点 data 同名非空值写入；与 Inspector pick 实时联动并存、语义不同） */
  prefillFromUpstream?: string[]
  /** 单工作流内同组件实例数上限（0 = 不限；超限拒绝拖入并 toast，不静默替换） */
  maxInstances?: number
}

/** I12 R1 组件分类（可多类归属）：T7 CAT_LABEL / T11 新组件复用此别名，获得键穷尽编译检查 */
export type ComponentCategory = 'sync' | 'etl' | 'stream' | 'general'

/** 条件显示控制（M-B2 迁移：showIf → conditions） */
export interface ConditionDef {
  id: string
  when: { field: string; op: string; value?: unknown }
  show: string[]
}

/** 节点副标题分型模板规则（M-B2 决策 2：summary 函数 → render.summaryRules 声明化；按声明序取首条命中） */
export interface SummaryRule {
  /** 满足时套用 template；null/缺省 = 兜底规则 */
  when: { field: string; op: string; value?: unknown } | null
  /** 副标题模板（${key} 以节点 data 同名值插值，缺失置空） */
  template: string
}

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
  /** §11 初始化模板（页面设计器拖入默认形态，纯数据可导出） */
  initTemplate?: ComponentInitTemplate
  /** F1 拖入策略（缺省 = 默认策略：必弹配置弹窗、不限实例） */
  dropPolicy?: DropPolicy
  /** 新建节点 data 默认值 */
  defaults?: Record<string, unknown>
  /** 属性表单 schema（节点名称固定渲染，不入 schema） */
  form: FieldSchema[]
  /** 节点副标题（摘要渲染）：字符串或函数 */
  summary?: string | ((data: Record<string, unknown>) => string)
  /** 条件显示控制（M-B2 迁移：showIf → conditions） */
  conditions?: ConditionDef[]
  /** 渲染配置（M-B2 迁移：summary 函数 → render.summary 字符串 / render.summaryRules 分型模板） */
  render?: { summary?: string; summaryRules?: SummaryRule[]; [key: string]: unknown }
  /** 节点渲染形态：card=任务框（默认）；device=设备图标卡片（拓扑视角专用） */
  shape?: 'card' | 'device'
  /** 动态源端点（条件分支等）：非空时节点按分支渲染多个输出端点 */
  ports?: (data: Record<string, unknown>) => NodePort[]
  /** 同步编排端点合一：具名输出端口（静态声明，如 endpoint_select 的 sourceRef/targetRef；下游按端口引用取数） */
  outputs?: NodePort[]
  /** 同步编排设计态/运行态分离：运行态执行组件标记（true = 不进 palette、不进设计态画布、画布校验排除；schema 保留供运行实例详情渲染） */
  runtimeOnly?: boolean
  /** G-22：渲染分类第三类别——非执行节点（不产生任务实例、不参与 _execute_node，只提供页面）；与 runtimeOnly 正交 */
  nonExecutable?: boolean
  /** G-22：输入契约——声明该节点消费的上游输出端口（用于画布连通性校验 + 拖边即引用推导） */
  inputs?: NodePort[]
  /** G-22：单工作流内同组件实例数上限（true = 全局仅允许一个实例；超限拒绝拖入） */
  singleInstance?: boolean
  /** G-22：最大出边数（0 = 禁止出边，如 end 节点；undefined = 不限） */
  maxOut?: number
  /** G-22：逐组件自定义校验器（在 profile 级 validators 之后追加执行） */
  validators?: (node: GNode, doc: GraphDocument) => { level: 'error' | 'warn'; msg: string }[]
  /** G-22：组件版本号（用于版本迁移/兼容性判定；缺省 '1.0.0'） */
  version?: string
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
  /** Task 7 血缘交互：声明本视角支持「以此为中心」——节点双击/右键菜单上抛 center-node 事件（宿主重拉） */
  nodeCenter?: boolean
}
