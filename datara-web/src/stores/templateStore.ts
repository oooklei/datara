import { defineStore } from 'pinia'
import { ref } from 'vue'
import { confirmTemplateUpgrade, getUpgradeStatus, instantiateTemplate, listTemplates, previewTemplateUpgrade, type TemplateDiff, type UpgradeStatus, type WorkflowTemplate } from '../services/templateApi'

export const useTemplateStore = defineStore('workflow-templates', () => {
  const templates = ref<WorkflowTemplate[]>([])
  const loading = ref(false)
  const upgradeNotice = ref<UpgradeStatus | null>(null)
  const upgradePreview = ref<TemplateDiff | null>(null)
  async function load() { loading.value = true; try { templates.value = await listTemplates() } finally { loading.value = false } }
  const instantiate = (id: number, name?: string) => instantiateTemplate(id, name)
  async function checkUpgrade(wfId: string) { upgradeNotice.value = await getUpgradeStatus(wfId); upgradePreview.value = null }
  async function previewUpgrade(wfId: string) {
    await checkUpgrade(wfId)
    upgradePreview.value = await previewTemplateUpgrade(wfId)
  }
  async function confirmUpgrade(wfId: string) {
    const notice = upgradeNotice.value
    const preview = upgradePreview.value
    if (notice?.templateId == null || !preview) return null
    /* CAS 三参：baseVersion 取 diff 预览时的工作流版本（预览后草稿再变动会被后端 409 拒绝），
       未预览时兜底为 notice.currentVersion；templateVersion/targetTemplateVersion 锁定升级模板版本区间。 */
    const body = {
      baseVersion: preview.workflowVersion,
      templateVersion: preview.currentVersion,
      targetTemplateVersion: preview.latestVersion,
    }
    const doc = await confirmTemplateUpgrade(notice.templateId, wfId, body)
    await checkUpgrade(wfId)
    return doc
  }
  return { templates, loading, upgradeNotice, upgradePreview, load, instantiate, checkUpgrade, previewUpgrade, confirmUpgrade }
})
