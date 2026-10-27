import { describe, expect, it } from 'vitest'

import apiKeyManagement from '../ApiKeyManagementView.vue?raw'
import apiManagement from '../ApiManagementView.vue?raw'
import modelList from '../dwmodel/ModelListView.vue?raw'
import home from '../HomeView.vue?raw'
import consistencyCheck from '../ind/ConsistencyCheckView.vue?raw'
import indicatorBoard from '../ind/IndicatorBoardView.vue?raw'
import assetMap from '../meta/AssetMapView.vue?raw'
import metadataCatalog from '../meta/MetadataCatalogView.vue?raw'
import projectSegment from '../ProjectSegmentView.vue?raw'
import qualityReadOnly from '../qc/QualityReadOnlyView.vue?raw'
import resourceManagement from '../resources/ResourceManagementView.vue?raw'
import systemAdmin from '../system/SystemAdminView.vue?raw'
import taskCenter from '../TaskCenterView.vue?raw'
import variableManagerDrawer from '../variables/VariableManagerDrawer.vue?raw'

const liveViews = {
  ApiKeyManagementView: apiKeyManagement,
  ApiManagementView: apiManagement,
  ModelListView: modelList,
  HomeView: home,
  ConsistencyCheckView: consistencyCheck,
  IndicatorBoardView: indicatorBoard,
  AssetMapView: assetMap,
  MetadataCatalogView: metadataCatalog,
  ProjectSegmentView: projectSegment,
  QualityReadOnlyView: qualityReadOnly,
  ResourceManagementView: resourceManagement,
  SystemAdminView: systemAdmin,
  TaskCenterView: taskCenter,
  VariableManagerDrawer: variableManagerDrawer,
} as const

describe('T-A design token closure', () => {
  it('keeps the two M2b views and remaining twelve LIVE views free of hardcoded hex colors', () => {
    expect(Object.keys(liveViews)).toHaveLength(14)

    for (const [name, source] of Object.entries(liveViews)) {
      expect(source, `${name} must use shared theme tokens`).not.toMatch(/#[\da-f]{3,8}\b/i)
    }
  })
})
