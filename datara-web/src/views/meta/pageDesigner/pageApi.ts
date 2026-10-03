/**
 * 页面设计器服务层（Task 9）：
 * - GET  /page-designer/resources 资源目录（绑定候选来源，后端 api/page_designer.py）
 * - POST /page-designer/preview   数据预览（后端每查询硬编码 LIMIT 100 → rowCap=100，§8 不配置化）
 * - POST /components/{type}/refresh-refs 发布即刷新引用（api/component_design.py §9，幂等）
 * mock 模式与 componentApi 同款：if (isMock) 内联分支；资源目录 mock 集中在 services/mock/api.ts。
 */
import { http } from '../../../services/http'
import { isMock } from '../../../services/apiMode'
import { mockPageDesignerResources } from '../../../services/mock/api'

/** GET /page-designer/resources 响应（五键，与后端 resources() 同形） */
export interface ResourcesResp {
  datasources: { id: number; name: string; type: string; db: string }[]
  workflows: { code: number; name: string; vars: { path: string; label: string; type: string }[] }[]
  globalParams: { path: string; label: string }[]
  timeParams: { path: string; label: string; sample: string }[]
  components: { type: string; name: string; state: string; publishedVersion: number | null }[]
}

/** 单查询预览结果（后端 _run_readonly 每项四字段；id 以 results 键承载不重复进字段） */
export interface PreviewResult { columns: string[]; rows: string[][]; truncated: boolean; error: string }

/** POST /page-designer/preview 响应（widgetErrors：失败组件聚合 [{id,error}]，按 queries 顺序，成功项不进） */
export interface PreviewResp {
  results: Record<string, PreviewResult>
  rowCap: number
  widgetErrors: { id: string; error: string }[]
}

/** POST /components/{type}/refresh-refs 响应（§9：命中图批量升级至 published_version） */
export interface RefreshRefsResult {
  refreshed: number
  publishedVersion: number
  items: { wfId: string; wfName: string }[]
}

export interface PreviewQuery { id: string; datasourceId: number; sql: string; db?: string }

export const pageApi = {
  /** 系统资源目录：数据源 / 工作流及变量 / 全局参数 / 时间参数 / 组件清单 */
  async getResources(): Promise<ResourcesResp> {
    if (isMock) return mockPageDesignerResources()
    return http.get<ResourcesResp>('/page-designer/resources')
  },

  /** 数据预览（SELECT/WITH 校验由后端 422 承载；仅连接型数据源可执行，其余入 error 不抛；widgetErrors 汇总失败组件） */
  async preview(queries: PreviewQuery[]): Promise<PreviewResp> {
    if (isMock) {
      const results: Record<string, PreviewResult> = {}
      for (const q of queries) results[q.id] = { columns: [], rows: [], truncated: false, error: '' }
      return { results, rowCap: 100, widgetErrors: [] }
    }
    return http.post<PreviewResp>('/page-designer/preview', { queries })
  },

  /** 刷新引用（仅 published 组件，draft 409 由后端承载）；publish 成功后端已自动执行 */
  async refreshRefs(type: string): Promise<RefreshRefsResult> {
    if (isMock) return { refreshed: 0, publishedVersion: 1, items: [] }
    return http.post<RefreshRefsResult>(`/components/${encodeURIComponent(type)}/refresh-refs`)
  },
}
