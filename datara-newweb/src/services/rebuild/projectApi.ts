/**
 * 增量 3 L3-02（项目上下文层 §5A.11 方案 A）项目域契约层 — 首页项目列表。
 *
 * 端点实证：datara-backend/rebuild/api/app.py `GET /api/v1/rebuild/projects`
 *   → `{code:0, msg:'success', data:{total, list:[{id, name}]}}`；
 *   归属语义：admin=list_all、其他=list_for_user（后端裁定，前端透传不加工）。
 * 列表项当前仅 id+name；`ownOrJoined` 为 S243 注记（随 3.2 后端最小补交付）的
 * 可选兼容位——前端不假设未交付字段，后端返回时原样透出。
 */

import { getJson } from '../http'

export interface ProjectSummary {
  id: number
  name: string
  /** 归属面标记（wire 词形以后端 3.2 最小补为准）；当前端点未返回时为 undefined。 */
  ownOrJoined?: 'owner' | 'joined'
}

export interface ProjectListPage {
  total: number
  list: ProjectSummary[]
}

/** 拉取「我拥有/参与」的项目列表（登录后首页卡片数据源，§5A.11）。 */
export function listProjects(): Promise<ProjectListPage> {
  return getJson<ProjectListPage>('/rebuild/projects')
}
