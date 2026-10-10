import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

describe('template center integration', () => {
  it('offers save-as-template, create-from-template, optional upgrade and diff confirmation controls', () => {
    const taskCenter = readFileSync(fileURLToPath(new URL('../../TaskCenterView.vue', import.meta.url)), 'utf8')
    const center = readFileSync(fileURLToPath(new URL('../TemplateCenter.vue', import.meta.url)), 'utf8')
    expect(taskCenter).toContain('模板中心')
    expect(taskCenter).toContain('另存为模板')
    expect(center).toContain('从模板新建')
    expect(center).toContain('可选升级')
    expect(center).toContain('diff')
    expect(center).toContain('确认升级')
  })
})
