/**
 * 菜单配置唯一源（增量 2 / 票 2-01）
 *
 * 蓝本：0.8 方案 §2.1 数据结构契约 + §3 逐项落位表（0.8 L92-109 逐行忠实转译）
 * 裁定锚：
 *  - R-15（s213-ruling-broadcast）：快照测试锚定配置对象；批次开关初始值保守关闭
 *  - R-28（s215b-ruling3-broadcast）：增2-Q3 脱敏·审计纳入（增量 15 后追加立项，可复议）
 *  - R-29（s215b-ruling3-broadcast）：增2-Q4 future 预留 routeName 字段、路由表不注册
 * 字段纪律（0.8 L57-68）：id 稳定键禁中文；TBD 不进运行时配置（资源管理/LLM 不落 path）；
 *  source 必填指向权威设计 §3 功能清单 / I 增量 / 用户裁定；decisionGate 存在未决形态时必填。
 * 边界：deleted 处置仅用于迁移审计清单（0.8 L66），本配置不含 deleted 项，审计清单归票 2-03。
 */

export type MenuDisposition = 'formal' | 'future' | 'embedded' | 'deleted'

export interface MenuItemConfig {
  /** 稳定键，不用中文标签或路径充当持久标识（0.8 L61） */
  id: string
  label: string
  routeName?: string
  path?: string
  icon?: string
  children?: MenuItemConfig[]
  disposition: MenuDisposition
  /** 必填：指向 §3 功能清单 / I 增量 / 用户裁定（0.8 L67，满足权威设计 §4.4 登记前置红线 2） */
  source: string
  /** 所属交付批次，批次开关（BATCH_SWITCHES）的「当前批次已启用」门消费键 */
  batch?: string
  permission?: string
  /** 存在未决产品形态时必填；门未闭合不渲染独立菜单（0.8 L68） */
  decisionGate?: string
}

export type MenuGroupId =
  | 'overview'
  | 'task-center'
  | 'integration'
  | 'development'
  | 'governance'
  | 'operations'
  | 'system'
  | 'future'

export interface MenuGroupConfig {
  id: MenuGroupId
  label: string
  items: MenuItemConfig[]
  /** B 组一级直达：空组名不渲染组标题（权威设计 §4.2 B 行，F56a 裁定 2A/3B） */
  direct?: boolean
  foldable?: boolean
  defaultFolded?: boolean
  /**
   * 增2-建3 / R2 预留：项目作用域维度（0.8 L109 项目管理不入 A–G 组，进入项目后再渲染项目内菜单）。
   * 仅预留字段不实现项目逻辑，归增量 3.3 消费。
   */
  scope?: 'global' | 'project'
}

/**
 * 批次开关常量表（R-15：初始值保守关闭）。
 * 「当前批次已启用」门的数据源（0.8 §2.2 formal 五门之三），随下游增量逐项开启。
 */
export const BATCH_SWITCHES: Readonly<Record<string, boolean>> = Object.freeze({
  inc3: false,
  inc4: false,
  inc10: false,
  inc11: false,
  inc14: false,
  inc15: false,
  'inc15-post': false,
  inc17: false,
})

/**
 * §4.2 七组 A–G + future 机制组逐行落位（0.8 §3 表逐行转译）。
 * future 组为「后续批次」折叠机制组：静态 items 留空，运行时由过滤函数按四纳入门
 * 从各组 future 项收集（0.8 §5.1-§5.2；机制实现归票 2-02/2-04）。
 */
export const menuGroups: readonly MenuGroupConfig[] = [
  {
    id: 'overview',
    label: '总览',
    items: [
      {
        id: 'workbench',
        label: '工作台',
        path: '/',
        routeName: 'home',
        disposition: 'formal',
        batch: 'inc3',
        source: '§4.2 A 行；旧 routes.ts L11 已实证',
      },
    ],
  },
  {
    id: 'task-center',
    label: '',
    direct: true,
    items: [
      {
        id: 'task-center-entry',
        label: '任务中心',
        path: '/dag',
        disposition: 'formal',
        batch: 'inc4',
        source: '§4.2 B 行；旧 routes.ts L12 已实证；工作流/运行实例/调度/变量/依赖均在任务中心内部承载',
      },
    ],
  },
  {
    id: 'integration',
    label: '数据集成',
    items: [
      {
        id: 'ds-list',
        label: '数据源管理',
        path: '/ds/list',
        disposition: 'formal',
        batch: 'inc10',
        source: '§4.2 C 行；旧 routes.ts L38 已实证',
      },
      {
        id: 'sync-task',
        label: '同步任务',
        disposition: 'embedded',
        source: '§4.2 C 行 v3 裁定移出菜单；由 /dag 同步工作流 tab 承载（0.8 §3 L97）',
      },
      {
        id: 'stream-process',
        label: '流数据处理',
        disposition: 'embedded',
        source: '§4.2 C 行；§5A.2 由 /dag 流处理工作流 tab 承载（0.8 §3 L98）',
      },
      {
        id: 'resource-mgmt',
        label: '资源管理',
        disposition: 'formal',
        batch: 'inc10',
        decisionGate: 'route-frozen-inc10',
        source: '§4.2 C 行；0.8 §3 L99 路径待路由契约，增量 10 冻结，此前不显示空壳',
      },
    ],
  },
  {
    id: 'development',
    label: '数据开发',
    items: [
      {
        id: 'sql-ide',
        label: '数据开发IDE',
        path: '/ide',
        disposition: 'formal',
        batch: 'inc11',
        source: '§4.2 D 行；旧 routes.ts L52 已实证；I5 只读态可按交付批次启用（0.8 §3 L100）',
      },
      {
        id: 'dw-modeling',
        label: '数仓建模',
        path: '/model/list',
        routeName: 'dwModeling',
        disposition: 'future',
        batch: 'inc17',
        source: '§4.2 D 行；STATE S175/S179 裁定纳入增量 17（0.8 §3 L101）；routeName 为 R-29 字段预留，路由表不注册',
      },
    ],
  },
  {
    id: 'governance',
    label: '数据治理',
    items: [
      {
        id: 'meta-lineage',
        label: '血缘分析',
        path: '/meta/lineage',
        disposition: 'formal',
        batch: 'inc14',
        source: '§4.2 E 行；旧 routes.ts L21-34 已实证',
      },
      {
        id: 'meta-map',
        label: '资产地图',
        path: '/meta/map',
        disposition: 'formal',
        batch: 'inc14',
        source: '§4.2 E 行；旧 routes.ts L21-34 已实证',
      },
      {
        id: 'meta-catalog',
        label: '元数据目录',
        path: '/meta/catalog',
        disposition: 'formal',
        batch: 'inc14',
        source: '§4.2 E 行；旧 routes.ts L21-34 已实证',
      },
      {
        id: 'meta-tag',
        label: '标签',
        path: '/meta/tag',
        disposition: 'formal',
        batch: 'inc14',
        source: '§4.2 E 行；旧 routes.ts L21-34 已实证',
      },
      {
        id: 'std-element',
        label: '标准',
        path: '/std/element',
        disposition: 'formal',
        batch: 'inc14',
        source: '§4.2 E 行；旧 routes.ts L21-34 已实证',
      },
      {
        id: 'ind-list',
        label: '指标目录',
        path: '/ind/list',
        disposition: 'formal',
        batch: 'inc14',
        source: '§4.2 E 行；旧 routes.ts L21-34 已实证',
      },
      {
        id: 'ind-board',
        label: '指标看板',
        path: '/ind/board',
        disposition: 'formal',
        batch: 'inc14',
        source: '§4.2 E 行；旧 routes.ts L21-34 已实证',
      },
      {
        id: 'ind-consistency',
        label: '一致性检查',
        path: '/ind/consistency',
        disposition: 'formal',
        batch: 'inc14',
        source: '§4.2 E 行；旧 routes.ts L82-95 已实证',
      },
      {
        id: 'qc-rule',
        label: '质量规则',
        path: '/qc/rule',
        disposition: 'future',
        batch: 'inc14',
        source: '§4.3 #3；从旧演示组迁入正式语义组，未到批次先收纳后续批次组（0.8 §3 L103 / §4 L117）',
      },
      {
        id: 'qc-task',
        label: '检查任务',
        path: '/qc/task',
        disposition: 'future',
        batch: 'inc14',
        source: '§4.3 #4；同 #3 迁移口径',
      },
      {
        id: 'qc-exception',
        label: '异常数据核查',
        path: '/qc/exception',
        disposition: 'future',
        batch: 'inc14',
        source: '§4.3 #5；同 #3 迁移口径',
      },
      {
        id: 'qc-report',
        label: '质量报告',
        path: '/qc/report',
        disposition: 'future',
        batch: 'inc14',
        source: '§4.3 #6；同 #3 迁移口径',
      },
      {
        id: 'qc-alarm',
        label: '质量告警',
        path: '/qc/alarm',
        disposition: 'future',
        batch: 'inc14',
        source: '§4.3 #7；同 #3 迁移口径',
      },
    ],
  },
  {
    id: 'operations',
    label: '部署运维',
    items: [
      {
        id: 'dep-runtime',
        label: '运行时节点',
        path: '/dep/runtime',
        routeName: 'depRuntime',
        disposition: 'future',
        batch: 'inc17',
        source: '§4.2 F 行；STATE S175/S179 裁定纳入增量 17（0.8 §3 L104）；routeName 为 R-29 字段预留',
      },
      {
        id: 'dep-monitor',
        label: '集群监控',
        path: '/dep/monitor',
        routeName: 'depMonitor',
        disposition: 'future',
        batch: 'inc17',
        source: '§4.2 F 行；STATE S175/S179 裁定纳入增量 17（0.8 §3 L104）；routeName 为 R-29 字段预留',
      },
    ],
  },
  {
    id: 'system',
    label: '系统管理',
    items: [
      {
        id: 'sec-perm',
        label: '权限管理',
        path: '/sec/perm',
        disposition: 'formal',
        batch: 'inc15',
        source: '§4.3 #9（I1/RBAC）；旧 routes.ts L91 已实证',
      },
      {
        id: 'sec-mask',
        label: '脱敏规则',
        path: '/sec/mask',
        disposition: 'future',
        batch: 'inc15-post',
        source: '§4.3 #10；R-28 裁定纳入（增量 15 后追加立项，可复议）',
      },
      {
        id: 'sec-audit',
        label: '访问审计',
        path: '/sec/audit',
        disposition: 'future',
        batch: 'inc15-post',
        source: '§4.3 #11；R-28 裁定纳入（增量 15 后追加立项，可复议）',
      },
      {
        id: 'open-api',
        label: 'API 管理',
        path: '/open/api',
        disposition: 'future',
        batch: 'inc15',
        source: '§4.3 #12；已裁定纳入但新后端待建模，实现并验收后转正式（0.8 §4 L126）',
      },
      {
        id: 'open-key',
        label: 'API-Key 管理',
        path: '/open/key',
        disposition: 'future',
        batch: 'inc15',
        source: '§4.3 #13；同 #12 口径',
      },
      {
        id: 'api-call-log',
        label: '调用日志',
        disposition: 'embedded',
        decisionGate: 'api-call-log-form',
        source: '§4.3 #14 并入 #12；独立页签/附属列未确认前禁止恢复独立菜单（0.8 §4 L128）',
      },
      {
        id: 'llm-config',
        label: 'LLM 模型配置',
        disposition: 'future',
        batch: 'inc15',
        decisionGate: 'route-frozen-inc15',
        source: '§4.2 G 行；0.8 §3 L109 已登记 G 组随增量 15 实现，本方案不为其编造路径',
      },
    ],
  },
  {
    id: 'future',
    label: '后续批次',
    foldable: true,
    defaultFolded: true,
    items: [],
  },
]

/**
 * H 全局挂载（无菜单组）：AI 悬浮助手（0.8 §3 L107 + §6 挂载规则）。
 * 挂载点位于认证后全局应用布局、与 <RouterView /> 同级，不增加一级菜单；
 * 挂载结构归 AppShell（票 2-05），本处仅登记配置语义行。
 */
export const globalMountedItems: readonly MenuItemConfig[] = [
  {
    id: 'ai-assistant',
    label: 'AI 助手',
    disposition: 'embedded',
    source: '§4.2 H 行 + §4.5；AppShell 全局挂载、单实例、登录页不挂载（0.8 §6 L182-189；增量 1 占位 / 增量 15 激活）',
  },
]
