import { describe, expect, it } from 'vitest'
import type { GEdge, GNode, GraphDocument } from '../../model'
import {
  addNodeCommand,
  connectCommand,
  deleteNodesCommand,
  disconnectCommand,
  moveNodesCommand,
  updatePropsCommand,
} from '../commands'

const node = (id: string, x = 0): GNode => ({ id, type: 'sql', position: { x, y: 0 }, data: { name: id } })
const edge = (id: string, source: string, target: string): GEdge => ({ id, source, target, kind: 'flow' })
const base = (): GraphDocument => ({
  id: 'wf', name: 'workflow', version: 1, meta: { profile: 'dag' },
  nodes: [node('a'), node('b', 80)], edges: [edge('ab', 'a', 'b')], groups: [{ id: 'g', name: 'group', nodeIds: ['a', 'b'] }],
})

describe('graph commands', () => {
  it('adds, connects, disconnects and updates properties reversibly', () => {
    const original = base()
    const cases = [
      addNodeCommand(original, node('c')),
      connectCommand(original, edge('ba', 'b', 'a')),
      disconnectCommand(original, ['ab']),
      updatePropsCommand(original, 'a', { name: 'renamed', limit: 100 }),
    ]
    for (const command of cases) {
      const changed = command.apply(original)
      expect(command.undo(changed)).toEqual(original)
      expect(changed).not.toBe(original)
    }
  })

  it('restores deleted nodes, incident edges and group membership exactly', () => {
    const original = base()
    const command = deleteNodesCommand(original, ['a'])
    const changed = command.apply(original)

    expect(changed.nodes.map((item) => item.id)).toEqual(['b'])
    expect(changed.edges).toEqual([])
    expect(changed.groups).toEqual([{ id: 'g', name: 'group', nodeIds: ['b'] }])
    expect(command.undo(changed)).toEqual(original)
  })

  it('moves nodes without mutating its source document', () => {
    const original = base()
    const command = moveNodesCommand(original, { a: { x: 48, y: 24 } })
    const changed = command.apply(original)

    expect(changed.nodes.find((item) => item.id === 'a')?.position).toEqual({ x: 48, y: 24 })
    expect(original.nodes.find((item) => item.id === 'a')?.position).toEqual({ x: 0, y: 0 })
    expect(command.undo(changed)).toEqual(original)
  })

  it('has apply/undo duality across ten deterministic edit sequences', () => {
    for (let index = 0; index < 10; index += 1) {
      const original = base()
      let document = original
      const commands = []
      const move = moveNodesCommand(document, { a: { x: index * 10, y: index } })
      commands.push(move); document = move.apply(document)
      const update = updatePropsCommand(document, 'b', { name: `node-${index}` })
      commands.push(update); document = update.apply(document)
      const final = index % 2 ? disconnectCommand(document, ['ab']) : addNodeCommand(document, node(`n${index}`))
      commands.push(final); document = final.apply(document)
      for (const command of [...commands].reverse()) document = command.undo(document)
      expect(document).toEqual(original)
    }
  })
})
