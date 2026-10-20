/**
 * 菜单迁移审计清单（增量 2 / 票 2-03）
 *
 * 蓝本：0.8 方案 §4「§4.3 扩展演示组 18 项逐项转译」表（L113-134）逐行忠实转译。
 * 纪律：deleted 项仅存在于本审计清单，构建时不得进入 MenuGroupConfig.items（0.8 L66，
 *       menu.ts 已由测试负断言保证）；deleted ≠ 永久拒绝，未来裁定纳入须按 §4.4 作为
 *       新菜单重新登记（0.8 L131），不复活旧演示项。
 * 计数校验（0.8 L134）：迁入正式语义组 10 项（#3~#7、#9~#13）+ #14 并入 #12 + 删除 7 项（#1、#2、#8、#15~#18）。
 */
import type { MenuDisposition } from './menu'

export interface MenuAuditEntry {
  /** 0.8 §4 表序号（1-18） */
  no: number
  /** 旧项名（权威设计 §4.3） */
  legacyLabel: string
  /** 旧路径实证 */
  legacyPath: string
  /** 转译结果（0.8 §4「配置结果」列；#3~#7 为 future 态、验收转正后改 formal） */
  disposition: MenuDisposition
  /** 新承载位置（0.8 §4「新承载位置」列） */
  target: string
  /** 与 menu.ts 配置的衔接锚（去向 item id；deleted 项缺省） */
  targetItemId?: string
  /** 运行时要求注记（0.8 §4「运行时要求」列） */
  note: string
}

export const MENU_AUDIT_18: readonly MenuAuditEntry[] = [
  {
    no: 1,
    legacyLabel: '脚本任务',
    legacyPath: '/script/list',
    disposition: 'deleted',
    target: '任务中心 DAG 的 SQL/Python/Shell 三脚本组件',
    note: '不保留旧路由菜单；能力不废（0.8 L115）',
  },
  {
    no: 2,
    legacyLabel: '参数配置',
    legacyPath: '/param/global',
    disposition: 'deleted',
    target: '任务中心的变量管理按钮/抽屉',
    note: '不保留旧路由菜单，避免与 R2 变量管理重复（0.8 L116）',
  },
  {
    no: 3,
    legacyLabel: '质量规则',
    legacyPath: '/qc/rule',
    disposition: 'future',
    target: 'E 数据治理组',
    targetItemId: 'qc-rule',
    note: '去除演示标识；批次、路由、权限齐备才显示（0.8 L117）',
  },
  {
    no: 4,
    legacyLabel: '检查任务',
    legacyPath: '/qc/task',
    disposition: 'future',
    target: 'E 数据治理组',
    targetItemId: 'qc-task',
    note: '同 #3 口径（0.8 L118）',
  },
  {
    no: 5,
    legacyLabel: '异常数据核查',
    legacyPath: '/qc/exception',
    disposition: 'future',
    target: 'E 数据治理组',
    targetItemId: 'qc-exception',
    note: '同 #3 口径（0.8 L119）',
  },
  {
    no: 6,
    legacyLabel: '质量报告',
    legacyPath: '/qc/report',
    disposition: 'future',
    target: 'E 数据治理组',
    targetItemId: 'qc-report',
    note: '同 #3 口径（0.8 L120）',
  },
  {
    no: 7,
    legacyLabel: '质量告警',
    legacyPath: '/qc/alarm',
    disposition: 'future',
    target: 'E 数据治理组',
    targetItemId: 'qc-alarm',
    note: '同 #3 口径（0.8 L121）',
  },
  {
    no: 8,
    legacyLabel: '评分总览',
    legacyPath: '/qc/score',
    disposition: 'deleted',
    target: '无',
    note: '功能清单无出处；路由即使残留也不生成菜单（0.8 L122）',
  },
  {
    no: 9,
    legacyLabel: '权限管理',
    legacyPath: '/sec/perm',
    disposition: 'formal',
    target: 'G 系统管理组',
    targetItemId: 'sec-perm',
    note: 'I1/RBAC 出处；仍需路由存在和权限过滤（0.8 L123）',
  },
  {
    no: 10,
    legacyLabel: '脱敏规则',
    legacyPath: '/sec/mask',
    disposition: 'future',
    target: 'G 系统管理组',
    targetItemId: 'sec-mask',
    note: '承载域/批次未闭合前不进正式组；R-28 裁定纳入（增量 15 后追加立项）（0.8 L124）',
  },
  {
    no: 11,
    legacyLabel: '访问审计',
    legacyPath: '/sec/audit',
    disposition: 'future',
    target: 'G 系统管理组',
    targetItemId: 'sec-audit',
    note: '同 #10 口径（0.8 L125）',
  },
  {
    no: 12,
    legacyLabel: 'API 管理',
    legacyPath: '/open/api',
    disposition: 'future',
    target: 'G 系统管理组',
    targetItemId: 'open-api',
    note: '已裁定纳入但新后端待建模；实现并验收后转正式（0.8 L126）',
  },
  {
    no: 13,
    legacyLabel: 'API-Key 管理',
    legacyPath: '/open/key',
    disposition: 'future',
    target: 'G 系统管理组',
    targetItemId: 'open-key',
    note: '同 #12 口径（0.8 L127）',
  },
  {
    no: 14,
    legacyLabel: '调用日志',
    legacyPath: '/open/log',
    disposition: 'embedded',
    target: 'API 管理的页签或附属区域',
    targetItemId: 'api-call-log',
    note: 'decisionGate=api-call-log-form；独立页签/附属列未确认前禁止恢复独立菜单（0.8 L128）',
  },
  {
    no: 15,
    legacyLabel: '部署中心',
    legacyPath: '/dep/center',
    disposition: 'deleted',
    target: '无',
    note: '节点能力由 F 组已裁定条目承接，不保留部署中心壳（0.8 L129）',
  },
  {
    no: 16,
    legacyLabel: '组件日志',
    legacyPath: '/dep/log',
    disposition: 'deleted',
    target: '任务中心的运行实例与日志页签',
    note: '不保留重复入口（0.8 L130）',
  },
  {
    no: 17,
    legacyLabel: '告警管理',
    legacyPath: '/dep/alarm',
    disposition: 'deleted',
    target: '无',
    note: '当前无出处；未来若裁定纳入按 §4.4 新登记，不复活旧演示项（0.8 L131）',
  },
  {
    no: 18,
    legacyLabel: '运维操作',
    legacyPath: '/dep/ops',
    disposition: 'deleted',
    target: '无',
    note: '功能清单无出处（0.8 L132）',
  },
]

/** 计数校验常量（0.8 L134 与权威设计 §4.3 小结一致） */
export const AUDIT_COUNTS = { grouped: 10, embedded: 1, deleted: 7 } as const

/** 双重负断言的 8 条旧路径（拆票登记 2-03 验收锚；WBS 退出标准 2 口径） */
export const DELETED_LEGACY_PATHS: readonly string[] = [
  '/sync/list',
  '/script/list',
  '/param/global',
  '/qc/score',
  '/dep/center',
  '/dep/log',
  '/dep/alarm',
  '/dep/ops',
]
