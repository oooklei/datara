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
    expect(source).toContain('v-if="projectId !== undefined && scriptResourceKind"')
    expect(source).toContain(':kind="scriptResourceKind"')
    expect(source).toMatch(/nodeType \?\? ''\)\.toLowerCase\(\) === 'dependent'/)
    expect(source).toContain('v-if="selectedNodeRecord && isDependentNode && projectId !== undefined"')
  })
})
