/** Stream API contract surface (node environment, no component mounting). */
import { describe, expect, it } from 'vitest'
import {
  I8_CONTRACT_METHODS,
  createStreamContract,
} from '../../../../services/rebuild/streamApi'

describe('I8 streamApi contract', () => {
  it('contract method list is frozen to the stream job/attempt/checkpoint/metric/observation/recovery subset', () => {
    expect(I8_CONTRACT_METHODS).toHaveLength(6)
    expect(I8_CONTRACT_METHODS).toEqual(
      expect.arrayContaining([
        'listStreamJobs',
        'listStreamAttempts',
        'listStreamCheckpoints',
        'listStreamMetrics',
        'queryStreamObservation',
        'listStreamRecoveryEvents',
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
