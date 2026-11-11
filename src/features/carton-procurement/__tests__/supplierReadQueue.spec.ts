import { describe, expect, it, vi } from 'vitest'
import { createSupplierReadQueue } from '../supplierReadQueue'

describe('supplier read concurrency', () => {
  it('shares two slots and discards queued work after its context is cancelled', async () => {
    const queue = createSupplierReadQueue(), controller = new AbortController()
    let first!: () => void, second!: () => void
    const a = queue.run(() => new Promise<void>(resolve => { first = resolve }))
    const b = queue.run(() => new Promise<void>(resolve => { second = resolve }))
    const stale = vi.fn(async () => 'old factory')
    const c = queue.run(stale, controller.signal).catch(error => error.name)
    const fresh = vi.fn(async () => 'new factory')
    const d = queue.run(fresh)
    await Promise.resolve()
    expect(fresh).not.toHaveBeenCalled()
    controller.abort()
    expect(await c).toBe('AbortError')
    first(); await a
    expect(await d).toBe('new factory')
    expect(stale).not.toHaveBeenCalled()
    second(); await b
  })
  it('releases a slot after a failed request', async () => {
    const queue = createSupplierReadQueue(1)
    const failure = queue.run(async () => { throw new Error('offline') }).catch(error => error.message)
    const next = queue.run(async () => 'ready')
    expect(await failure).toBe('offline')
    expect(await next).toBe('ready')
  })
})
