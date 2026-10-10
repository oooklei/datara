import { http } from './http'
import type { GraphDocument } from '../graph/model'

export interface WorkflowTemplate { id: number; name: string; category: string; description: string; version: number; updatedAt: string; templateJson?: GraphDocument }
export interface UpgradeStatus { upgradeAvailable: boolean; templateId: number | null; currentVersion: number; latestVersion: number }
export interface TemplateDiff { currentVersion: number; latestVersion: number; diff: Array<{ path: string; before: unknown; after: unknown }> }

export const listTemplates = () => http.get<WorkflowTemplate[]>('/workflow-templates')
export const getTemplate = (id: number) => http.get<WorkflowTemplate>(`/workflow-templates/${id}`)
export const createTemplate = (body: { name: string; category?: string; description?: string; templateJson: GraphDocument }) => http.post<WorkflowTemplate>('/workflow-templates', body)
export const updateTemplate = (id: number, body: { name: string; category?: string; description?: string; templateJson: GraphDocument }) => http.put<WorkflowTemplate>(`/workflow-templates/${id}`, body)
export const deleteTemplate = (id: number) => http.delete<boolean>(`/workflow-templates/${id}`)
export const listTemplateVersions = (id: number) => http.get<WorkflowTemplate[]>(`/workflow-templates/${id}/versions`)
export const instantiateTemplate = (id: number, name?: string) => http.post<{ id: string; code: number; version: number }>(`/workflow-templates/${id}/instantiate`, name?.trim() ? { name: name.trim() } : {})
export const getUpgradeStatus = (wfId: string) => http.get<UpgradeStatus>(`/workflow-templates/upgrade-status/${encodeURIComponent(wfId)}`)
export const previewTemplateUpgrade = async (wfId: string) => {
  const status = await getUpgradeStatus(wfId)
  if (status.templateId == null) return { currentVersion: status.currentVersion, latestVersion: status.latestVersion, diff: [] }
  return http.get<TemplateDiff>(`/workflow-templates/${status.templateId}/diff/${encodeURIComponent(wfId)}`)
}
export const confirmTemplateUpgrade = (templateId: number, wfId: string) => http.post<GraphDocument>(`/workflow-templates/${templateId}/upgrade/${encodeURIComponent(wfId)}`, {})
