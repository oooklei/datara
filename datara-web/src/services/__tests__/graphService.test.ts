/**
 * graphService 回归测试（code review 修复验证）：
 * - get 深克隆：修改返回值不污染缓存与种子
 * - save 记录版本快照，rollback 恢复对应版本内容并同步持久层
 * - listVersions 随 save 累积
 * node 环境无 localStorage，lsGet/lsSet 静默降级为内存兜底，行为一致。
 */
import { describe, it, expect } from 'vitest'
import { graphService } from '../mock/graphService'
import type { GraphDocument } from '../../graph/model'

function bareDoc(id: string): GraphDocument {
  return { id, name: '', version: 0, meta: { profile: 'dag' }, nodes: [], edges: [] }
}

describe('graphService 克隆与版本回滚', () => {
  it('get 返回深克隆，修改返回值不污染后续读取', async () => {
    const id = 'ut_clone_doc'
    const d1 = (await graphService.get(id))!
    d1.name = 'MUTATED'
    d1.nodes.push({ id: 'x', type: 'x', position: { x: 0, y: 0 }, data: { name: 'x' } })
    const d2 = (await graphService.get(id))!
    expect(d2.name).not.toBe('MUTATED')
    expect(d2.nodes).toHaveLength(0)
  })

  it('save 记录快照，rollback 恢复对应版本内容并同步持久层', async () => {
    const id = 'ut_rollback_doc'
    const d1 = bareDoc(id)
    d1.name = 'v1内容'
    d1.nodes = [{ id: 'n1', type: 't', position: { x: 0, y: 0 }, data: { name: 'n1' } }]
    const v1 = (await graphService.save(d1)).version

    const d2 = (await graphService.get(id))!
    d2.name = 'v2内容'
    d2.nodes = []
    const v2 = (await graphService.save(d2)).version
    expect(v2).toBe(v1 + 1)

    const rolled = await graphService.rollback(id, v1)
    expect(rolled.version).toBe(v1)
    expect(rolled.name).toBe('v1内容')
    expect(rolled.nodes).toHaveLength(1)

    const after = (await graphService.get(id))!
    expect(after.version).toBe(v1)
    expect(after.name).toBe('v1内容')
    expect(after.nodes).toHaveLength(1)
  })

  it('listVersions 随 save 累积且新版本在前', async () => {
    const id = 'ut_versions_doc'
    const v1 = (await graphService.save(bareDoc(id))).version
    const v2 = (await graphService.save({ ...bareDoc(id), version: v1 })).version
    const vs = await graphService.listVersions(id)
    expect(vs.length).toBeGreaterThanOrEqual(2)
    expect(vs[0]!.version).toBe(v2)
  })
})
