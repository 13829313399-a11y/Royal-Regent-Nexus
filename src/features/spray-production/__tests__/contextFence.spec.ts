import { describe, expect, it } from 'vitest'
import { ContextFence } from '../contextFence'

describe('spray request context', () => {
  const context = { userId: 'u1', factory: 'huaxing', authorizationVersion: 1 }
  it('rejects A → B → A responses even when factory and user match again', () => {
    const fence = new ContextFence()
    fence.switch(context)
    const old = fence.begin('demands')
    fence.switch({ ...context, factory: 'huakang-a' })
    fence.switch(context)
    const fresh = fence.begin('demands')
    expect(fence.current(old)).toBe(false)
    expect(fence.current(fresh)).toBe(true)
  })
  it('rejects reads started before a successful write and authorization changes', () => {
    const fence = new ContextFence()
    fence.switch(context)
    const preWrite = fence.begin('stock')
    fence.wrote()
    expect(fence.current(preWrite)).toBe(false)
    const preRevocation = fence.begin('payroll')
    fence.switch({ ...context, authorizationVersion: 2 })
    expect(fence.current(preRevocation)).toBe(false)
  })
  it('accepts only the latest request for a collection and independent queries coexist', () => {
    const fence = new ContextFence()
    fence.switch(context)
    const slow = fence.begin('demands')
    const stock = fence.begin('stock')
    const latest = fence.begin('demands')
    expect(fence.current(slow)).toBe(false)
    expect(fence.current(stock)).toBe(true)
    expect(fence.current(latest)).toBe(true)
  })
})
