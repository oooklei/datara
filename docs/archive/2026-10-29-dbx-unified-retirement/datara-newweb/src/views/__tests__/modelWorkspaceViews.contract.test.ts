import { describe, expect, it } from 'vitest'
import designSource from '../dwmodel/ModelDesignView.vue?raw'
import versionSource from '../dwmodel/ModelVersionView.vue?raw'
import lineageSource from '../dwmodel/ModelLineageView.vue?raw'
import erSource from '../dwmodel/ErCanvasView.vue?raw'

describe('model workspace views', () => {
  it('模型设计覆盖字段保存、生命周期、DDL 与物理化', () => {
    expect(designSource).toContain('data-save-fields')
    expect(designSource).toContain('modelApi.updateFields')
    expect(designSource).toContain('modelApi.publish')
    expect(designSource).toContain('modelApi.redraft')
    expect(designSource).toContain('modelApi.ddl')
    expect(designSource).toContain('modelApi.physicalize')
  })

  it('模型版本覆盖快照、差异与回滚', () => {
    expect(versionSource).toContain('modelApi.createVersion')
    expect(versionSource).toContain('modelApi.diffVersion')
    expect(versionSource).toContain('modelApi.rollbackVersion')
    expect(versionSource).toContain('data-version-diff-dialog')
  })

  it('模型血缘同时呈现声明/运行来源和下游影响', () => {
    expect(lineageSource).toContain('modelApi.lineage')
    expect(lineageSource).toContain('modelApi.impact')
    expect(lineageSource).toContain('data-lineage-canvas')
    expect(lineageSource).toContain('data-impact-list')
  })

  it('ER 画布支持拖拽、关系展示和布局保存', () => {
    expect(erSource).toContain('@pointermove="onMove"')
    expect(erSource).toContain('data-er-edge')
    expect(erSource).toContain('modelApi.getEr')
    expect(erSource).toContain('modelApi.putEr')
  })
})
