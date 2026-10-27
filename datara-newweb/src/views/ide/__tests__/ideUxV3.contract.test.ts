import { describe, expect, it } from 'vitest'
import source from '../IdeView.vue?raw'
import editorSource from '../SqlCodeEditor.vue?raw'

describe('SQL IDE UX v3 contract', () => {
  it('uses CodeMirror 6 and persistent split panes', () => {
    expect(source).toContain("import SqlCodeEditor from './SqlCodeEditor.vue'")
    expect(source).toContain("from 'splitpanes'")
    expect(source).toContain('data-ide-workspace')
    expect(source).toContain('datara.ide.split.v1')
    expect(editorSource).toContain("from '@codemirror/lang-sql'")
    expect(editorSource).toContain('new EditorView')
  })

  it('keeps the real variable, history, format, export and lineage actions', () => {
    expect(source).toContain('<GlobalParamDrawer')
    expect(source).toContain('data-history-drawer')
    expect(source).toContain('data-format')
    expect(source).toContain('data-export')
    expect(source).toContain('data-lineage')
  })
})
