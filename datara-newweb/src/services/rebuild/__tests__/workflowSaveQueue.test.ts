import { describe, expect, it, vi } from 'vitest'

import { WorkflowSaveQueue, type WorkflowSaveDelta } from '../workflowSaveQueue'

function delta(
  key: string,
  current: { value: string },
  next: string,
  overrides: Partial<WorkflowSaveDelta<string>> = {},
): WorkflowSaveDelta<string> {
  const previous = current.value
  return {
    key,
    previous,
    next,
    write: async (value) => { current.value = value },
    read: async () => current.value,
    compensate: async (value) => { current.value = value },
    ...overrides,
  }
}

describe('WorkflowSaveQueue partial-success compensation model', () => {
  it('keeps successful fields and leaves a failed unchanged field dirty/retryable', async () => {
    const name = { value: 'old-name' }
    const params = { value: 'old-params' }
    const compensateName = vi.fn()

    const result = await new WorkflowSaveQueue().save([
      delta('node:a:name', name, 'new-name', { compensate: compensateName }),
      delta('node:a:params', params, 'new-params', {
        write: async () => { throw new Error('HTTP 503') },
      }),
    ])

    expect(name.value).toBe('new-name')
    expect(params.value).toBe('old-params')
    expect(compensateName).not.toHaveBeenCalled()
    expect(result.savedKeys).toEqual(['node:a:name'])
    expect(result.dirtyKeys).toEqual(['node:a:params'])
    expect(result.outcomes.map((item) => item.status)).toEqual(['saved', 'retryable-failed'])
  })

  it('continues after a failure so later independent fields can succeed', async () => {
    const first = { value: 'a' }
    const second = { value: 'b' }
    const third = { value: 'c' }
    const result = await new WorkflowSaveQueue().save([
      delta('first', first, 'A'),
      delta('second', second, 'B', { write: async () => { throw new Error('rejected') } }),
      delta('third', third, 'C'),
    ])

    expect([first.value, second.value, third.value]).toEqual(['A', 'b', 'C'])
    expect(result.savedKeys).toEqual(['first', 'third'])
    expect(result.dirtyKeys).toEqual(['second'])
  })

  it('treats a timed-out write as saved when authoritative readback has next value', async () => {
    const current = { value: 'old' }
    const result = await new WorkflowSaveQueue().save([
      delta('node:a:x', current, 'new', {
        write: async (value) => {
          current.value = value
          throw new Error('response lost')
        },
      }),
    ])

    expect(result.complete).toBe(true)
    expect(result.outcomes[0]?.status).toBe('saved')
  })

  it('compensates only the mismatched item and keeps prior success', async () => {
    const first = { value: 'old-a' }
    const second = { value: 'old-b' }
    const compensateFirst = vi.fn()
    const compensateSecond = vi.fn(async (value: string) => { second.value = value })
    const result = await new WorkflowSaveQueue().save([
      delta('a', first, 'new-a', { compensate: compensateFirst }),
      delta('b', second, 'new-b', {
        write: async () => { second.value = 'partial-b' },
        compensate: compensateSecond,
      }),
    ])

    expect(first.value).toBe('new-a')
    expect(second.value).toBe('old-b')
    expect(compensateFirst).not.toHaveBeenCalled()
    expect(compensateSecond).toHaveBeenCalledWith('old-b')
    expect(result.outcomes.map((item) => item.status)).toEqual(['saved', 'compensated'])
    expect(result.dirtyKeys).toEqual(['b'])
  })

  it('marks failed compensation for manual recovery and disables automatic retry', async () => {
    const current = { value: 'old' }
    const item = delta('edge:a:b', current, 'new', {
      write: async () => { current.value = 'partial' },
      compensate: async () => { throw new Error('rollback failed') },
    })
    const queue = new WorkflowSaveQueue()
    const result = await queue.save([item])
    const retryWrite = vi.fn()
    const retried = await queue.retry([{ ...item, write: retryWrite }], result)

    expect(result.manualRecoveryKeys).toEqual(['edge:a:b'])
    expect(result.outcomes[0]).toMatchObject({ status: 'recovery-failed', dirty: true, retryable: false })
    expect(retryWrite).not.toHaveBeenCalled()
    expect(retried.outcomes).toEqual([])
  })

  it('retry submits only dirty retryable fields', async () => {
    const clean = { value: 'old-a' }
    const dirty = { value: 'old-b' }
    const cleanWrite = vi.fn(async (value: string) => { clean.value = value })
    let fail = true
    const dirtyWrite = vi.fn(async (value: string) => {
      if (fail) throw new Error('first attempt failed')
      dirty.value = value
    })
    const items = [
      delta('a', clean, 'new-a', { write: cleanWrite }),
      delta('b', dirty, 'new-b', { write: dirtyWrite }),
    ]
    const queue = new WorkflowSaveQueue()
    const first = await queue.save(items)
    fail = false
    const retried = await queue.retry(items, first)

    expect(cleanWrite).toHaveBeenCalledTimes(1)
    expect(dirtyWrite).toHaveBeenCalledTimes(2)
    expect(retried.complete).toBe(true)
    expect(retried.savedKeys).toEqual(['b'])
  })

  it('serializes concurrent batches for the same draft', async () => {
    const order: string[] = []
    let release!: () => void
    const gate = new Promise<void>((resolve) => { release = resolve })
    const queue = new WorkflowSaveQueue()
    const first = queue.save([{
      key: 'first', previous: 0, next: 1,
      write: async () => { order.push('first:start'); await gate; order.push('first:end') },
      read: async () => 1,
      compensate: async () => undefined,
    }])
    const second = queue.save([{
      key: 'second', previous: 0, next: 1,
      write: async () => { order.push('second:start') },
      read: async () => 1,
      compensate: async () => undefined,
    }])

    await Promise.resolve()
    expect(order).toEqual(['first:start'])
    release()
    await Promise.all([first, second])
    expect(order).toEqual(['first:start', 'first:end', 'second:start'])
  })

  it('rejects duplicate keys before executing writes', async () => {
    const current = { value: 'old' }
    const write = vi.fn()
    const item = delta('same', current, 'new', { write })
    await expect(new WorkflowSaveQueue().save([item, item])).rejects.toThrow('non-empty and unique')
    expect(write).not.toHaveBeenCalled()
  })
})
