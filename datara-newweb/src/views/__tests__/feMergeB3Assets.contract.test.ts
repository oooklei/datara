import { describe, expect, it } from 'vitest'
import ledgerSource from '/COPY_LEDGER.md?raw'
import filterPanelSource from '../../components/FilterPanel.vue?raw'
import variableDialogSource from '../../components/VariableManagementDialog.vue?raw'
import { LLM_PROVIDERS } from '../../services/rebuild/llmApi'
import routesSource from '../../router/routes.ts?raw'
import governanceHubSource from '../GovernanceHubView.vue?raw'
import apiKeyManagementSource from '../ApiKeyManagementView.vue?raw'
import apiManagementSource from '../ApiManagementView.vue?raw'
import qualityAlarmSource from '../qc/QualityAlarmView.vue?raw'
import qualityExceptionSource from '../qc/QualityExceptionView.vue?raw'
import qualityReportSource from '../qc/QualityReportView.vue?raw'
import accessAuditSource from '../sec/AccessAuditView.vue?raw'
import llmModelFormDialogSource from '../system/llm-models/LlmModelFormDialog.vue?raw'
import llmModelsSource from '../system/llm-models/LlmModelsView.vue?raw'

const assets = [
  ['components/FilterPanel.vue', filterPanelSource],
  ['components/VariableManagementDialog.vue', variableDialogSource],
  ['views/GovernanceHubView.vue', governanceHubSource],
  ['views/qc/QualityAlarmView.vue', qualityAlarmSource],
  ['views/qc/QualityExceptionView.vue', qualityExceptionSource],
  ['views/qc/QualityReportView.vue', qualityReportSource],
  ['views/sec/AccessAuditView.vue', accessAuditSource],
  ['views/ApiManagementView.vue', apiManagementSource],
  ['views/ApiKeyManagementView.vue', apiKeyManagementSource],
  ['views/system/llm-models/LlmModelsView.vue', llmModelsSource],
  ['views/system/llm-models/LlmModelFormDialog.vue', llmModelFormDialogSource],
] as const

describe('FE-MERGE-B3 asset intake', () => {
  it('statically resolves every approved new view and shared component', () => {
    for (const [asset, source] of assets) expect(source.length, asset).toBeGreaterThan(0)
  })

  it('keeps rebuild API contracts and excludes legacy/demo data layers', () => {
    for (const [asset, source] of assets) {
      expect(source, asset).not.toMatch(/(?:services\/(?!rebuild\/)|mock(?:Data|Service)|demoData|fixtureData)/i)
    }
  })

  it('retains one routed resource-management implementation', () => {
    expect(routesSource).toContain("../views/resources/ResourceManagementView.vue")
    expect(routesSource).not.toContain("../views/ResourceManagementView.vue")
  })

  it('binds the B5-normalized LLM and access-audit canonical views', () => {
    expect(routesSource).toContain("../views/sec/AccessAuditView.vue")
    expect(routesSource).toContain("../views/system/llm-models/LlmModelsView.vue")
    expect(ledgerSource).toContain('FE-MERGE-B5 冲突件并集')
  })

  it('keeps one canonical API/API-Key view with the approved feature union', () => {
    const retiredOpenCopies = import.meta.glob('../open/*.vue')
    expect(Object.keys(retiredOpenCopies)).toEqual([])
    expect(routesSource).toContain("../views/ApiManagementView.vue")
    expect(routesSource).toContain("../views/ApiKeyManagementView.vue")

    for (const marker of ['data-create', 'data-edit', 'data-publish', 'data-disable', 'data-enable', 'data-delete', 'data-goto-key', 'data-api-count']) {
      expect(apiManagementSource, marker).toContain(marker)
    }
    for (const marker of ['data-issue', 'data-rotate', 'data-revoke', 'data-copy-key', 'data-goto-api', 'data-apikey-count']) {
      expect(apiKeyManagementSource, marker).toContain(marker)
    }
  })

  it('never persists or places one-time API keys in browser storage or URLs', () => {
    expect(apiKeyManagementSource).not.toMatch(/localStorage|sessionStorage|indexedDB|URLSearchParams/)
    expect(apiKeyManagementSource).toContain('data-plain-key')
    expect(apiKeyManagementSource).toContain('data-close-key')
  })

  it('records the D-drive source root, relative paths and SHA-256 for all 11 assets', () => {
    expect(ledgerSource).toContain('D:\\需求\\数据治理工具\\Datara')
    for (const [index, [asset]] of assets.entries()) {
      const row = ledgerSource.split('\n').find((line: string) => line.startsWith(`| B3-${index + 1} |`))
      expect(row, asset).toBeTruthy()
      expect(row, asset).toContain(`\`datara-newweb/src/${asset}\``)
      expect(row, asset).toMatch(/\| `[a-f0-9]{64}` \|/)
    }
  })

  it('renders a label for every provider, including longcat', () => {
    expect(LLM_PROVIDERS).toEqual(['siliconflow', 'volcengine', 'longcat'])
    expect(llmModelFormDialogSource).toContain("longcat: 'LongCat'")
    expect(llmModelFormDialogSource).toContain('v-for="opt in LLM_PROVIDERS"')
  })
})
