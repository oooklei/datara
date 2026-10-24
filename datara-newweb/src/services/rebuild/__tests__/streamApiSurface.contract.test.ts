/** Stream API contract surface (node environment, no component mounting). */
import { describe, expect, it } from 'vitest'
import {
  I8_CONTRACT_METHODS,
  createStreamContract,
} from '../streamApi'

describe('I8 streamApi contract', () => {
  it('contract method list includes live production and fusion operations', () => {
    expect(I8_CONTRACT_METHODS).toHaveLength(8)
    expect(I8_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'listStreamJobs',
        'listStreamAttempts',
        'listStreamCheckpoints',
        'listStreamMetrics',
        'queryStreamObservation',
        'listStreamRecoveryEvents',
        'produceStreamEvents',
        'fuseStreamEvents',
      ]),
    )
  })

  it('factory exposes every contract method', () => {
    const contract = createStreamContract()
    for (const method of I8_CONTRACT_METHODS) {
      expect(contract, method).toHaveProperty(method)
      expect(typeof contract[method]).toBe('function')
    }
  })

})
