import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

const legacyProjectScopedViews = [
  'datasource/DataSourceListView.vue',
  'ide/IdeView.vue',
  'ind/ConsistencyCheckView.vue',
  'ind/IndicatorBoardView.vue',
  'ind/IndicatorListView.vue',
  'meta/AssetMapView.vue',
  'meta/LineageAnalysisView.vue',
  'meta/MetadataCatalogView.vue',
  'meta/TagManagementView.vue',
  'qc/QualityAlarmView.vue',
  'qc/QualityExceptionView.vue',
  'qc/QualityReadOnlyView.vue',
  'qc/QualityReportView.vue',
  'qc/QualityRuleView.vue',
  'qc/QualityTaskView.vue',
  'resources/ResourceManagementView.vue',
  'sec/AccessAuditView.vue',
  'std/StandardManagementView.vue',
]

describe('global project context contract', () => {
  it('keeps project selection exclusively in the workspace shell', () => {
    const offenders = legacyProjectScopedViews.filter((path) =>
      readFileSync(resolve(process.cwd(), 'src/views', path), 'utf8').includes('data-project-select'),
    )

    expect(offenders).toEqual([])
  })
})
