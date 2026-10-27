import { describe, expect, it } from 'vitest'

import source from '../WorkflowGraphWorkbench.vue?raw'


describe('WorkflowGraphWorkbench layout contract', () => {
  it('fills the task-center flex canvas so VueFlow receives a non-zero height', () => {
    const workbenchRule = source.match(/\.wf-workbench\s*\{([^}]*)\}/)?.[1] ?? ''
    const flowRule = source.match(/\.wf-flow\s*\{([^}]*)\}/)?.[1] ?? ''
    const vueFlowRule = source.match(/\.wf-flow\s+:deep\(\.vue-flow\)\s*\{([^}]*)\}/)?.[1] ?? ''

    expect(workbenchRule).toMatch(/flex:\s*1 1 0/)
    expect(workbenchRule).toMatch(/min-height:\s*0/)
    expect(workbenchRule).not.toMatch(/height:\s*100%/)
    expect(flowRule).toMatch(/flex:\s*1/)
    expect(flowRule).toMatch(/min-height:\s*0/)
    expect(vueFlowRule).toMatch(/height:\s*100%/)
  })

  it('keeps SQL, Python, Shell, and dependency editors reachable from node selection', () => {
    expect(source).toContain('v-for="component in availableComponents"')
    expect(source).toContain('@click="onAddNode(component)"')
    expect(source).toMatch(/label:\s*`\$\{n\.nodeCode\} \$\{n\.nodeType\}/)
    expect(source).toContain('@node-click="onNodeClick"')
    expect(source).toMatch(/if \(type === 'sql'\) return 'sql'/)
    expect(source).toMatch(/if \(type === 'python' \|\| type === 'shell'\) return 'script'/)
    expect(source).toMatch(/type === 'sql' \|\| type === 'python' \|\| type === 'shell' \? type : null/)
    expect(source).toContain('v-else-if="nodeParameterKey && scriptResourceKind"')
    expect(source).toContain(':kind="scriptResourceKind"')
    expect(source).toMatch(/nodeType \?\? ''\)\.toLowerCase\(\) === 'dependent'/)
    expect(source).toContain('v-show="activeInspectorTab === \'dependencies\'"')
    expect(source).toContain('v-if="selectedNodeRecord && isDependentNode"')
  })

  it('keeps palette, canvas, and inspector reachable below the 768px breakpoint', () => {
    const narrow = source.match(/@media\s*\(max-width:\s*767px\)\s*\{([\s\S]*)\}\s*<\/style>/)?.[1] ?? ''

    expect(narrow).toMatch(/\.wf-body\s*\{[^}]*grid-template-rows:/s)
    expect(narrow).toMatch(/\.wf-flow\s*\{[^}]*min-height:\s*360px/s)
    expect(narrow).toMatch(/\.wf-aside\s*\{[^}]*width:\s*auto/s)
    expect(narrow).toMatch(/\.wf-splitter\s*\{[^}]*display:\s*none/s)
  })

  it('uses dagre when persisted node coordinates overlap', () => {
    expect(source).toContain("from '@dagrejs/dagre'")
    expect(source).toContain('layoutFlowNodes(')
    expect(source).toMatch(/graph\.setGraph\(\{\s*rankdir:\s*'LR'/)
  })
})
