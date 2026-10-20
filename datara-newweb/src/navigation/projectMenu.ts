/**
 * L3-03 定稿：项目工作区七段菜单配置（NAV 段名定稿权落点，s251 派令）。
 *
 * 段名沿用 L3-06 已验收 ProjectWorkbenchView 快捷导航七段（data-nav 锚零破坏，
 * 验收信 s249 候定稿注记随本票关闭）。
 *
 * 承载方式：独立配置，不并入 menuGroups A–G 组——menu.ts scope 字段预留语义
 * 「项目管理不入 A–G 组，进入项目后再渲染项目内菜单」（归增量 3.3 消费）；
 * 项目内菜单与全局菜单互斥分流（AppShell 按 /p/ 前缀切换），R-15 快照锚定面
 * （menuGroups 组序列、逐项配置、BATCH_SWITCHES）零触碰。
 *
 * 段 key 与 `/p/:projectId/<seg>` 路由段一一对齐（routes.ts project-segment 承载），
 * 同时为 AppShell 侧栏 data-seg 稳定锚。
 */
export interface ProjectMenuSection {
  /** 路由段 key：/p/:projectId/<key>；同时为 DOM data-seg 稳定锚 */
  key: string
  label: string
}

export const PROJECT_MENU_SECTIONS: readonly ProjectMenuSection[] = [
  { key: 'dag', label: '任务中心' },
  { key: 'datasource', label: '数据源' },
  { key: 'resources', label: '资源管理' },
  { key: 'ide', label: 'SQL IDE' },
  { key: 'meta', label: '数据治理' },
  { key: 'dep', label: '部署运维' },
  { key: 'system', label: '系统管理' },
] as const
