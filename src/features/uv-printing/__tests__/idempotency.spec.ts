import { describe, expect, it } from 'vitest'
import { operationForPayload } from '../composables/useUvRequest'

describe('快速报工幂等键', () => {
  it('同一表单在超时后重试保留 operation_id，修改内容才换新键', () => {
    const create = (() => {
      let index = 0
      return () => `op-${++index}`
    })()
    const first = operationForPayload(null, '{"qty":10}', create)
    const retry = operationForPayload(first, '{"qty":10}', create)
    const changed = operationForPayload(retry, '{"qty":11}', create)

    expect(first.id).toBe('op-1')
    expect(retry).toEqual(first)
    expect(changed).toEqual({ fingerprint: '{"qty":11}', id: 'op-2' })
  })
})
