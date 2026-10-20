import { describe, expect, it } from 'vitest'
import { API_BASE } from '../src/services/http'

describe('engineering skeleton',()=>{it('uses the single API base',()=>{expect(API_BASE).toBe('/api/v1')})})
