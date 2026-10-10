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
  async function previewUpgrade(wfId: string) { upgradePreview.value = await previewTemplateUpgrade(wfId) }
  async function confirmUpgrade(wfId: string) {
    if (upgradeNotice.value?.templateId == null) return null
    const doc = await confirmTemplateUpgrade(upgradeNotice.value.templateId, wfId)
    await checkUpgrade(wfId)
    return doc
  }
  return { templates, loading, upgradeNotice, upgradePreview, load, instantiate, checkUpgrade, previewUpgrade, confirmUpgrade }
})
