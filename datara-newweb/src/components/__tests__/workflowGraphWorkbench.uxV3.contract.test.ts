import { describe, expect, it } from 'vitest'
import source from '../WorkflowGraphWorkbench.vue?raw'

describe('WorkflowGraphWorkbench UX v3 three-pane contract', () => {
  it('uses the real Palette, canvas and Inspector as one resizable workspace', () => {
    expect(source).toContain("import Palette from './Palette.vue'")
    expect(source).toContain('data-dag-palette')
    expect(source).toContain('data-dag-canvas')
    expect(source).toContain('data-dag-inspector')
    expect(source).toContain('role="separator"')
    expect(source).toContain('datara.dag.split.v1')
  })

  it('keeps all real node editors inside the Inspector instead of below the canvas', () => {
    const inspector = source.slice(source.indexOf('data-dag-inspector'), source.indexOf('</aside>', source.indexOf('data-dag-inspector')))
    expect(inspector).toContain('<NodeConfigPanel')
    expect(inspector).toContain('<ScriptResourceEditor')
    expect(inspector).toContain('<DependencyNodeEditor')
    expect(inspector).toContain('<SyncMappingEditor')
    expect(inspector).toContain('<StreamObservationPanel')
    expect(inspector).toContain('选择一个节点以编辑配置')
  })
})
